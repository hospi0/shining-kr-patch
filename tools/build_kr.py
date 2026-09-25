#!/usr/bin/env python3
"""
Shining the Holy Ark — **한글 패치 디스크 빌드** (재압축 방식, 2026-07-13).

translation/sets/*.json 의 kr → 각 지역 MDX 의 **섹션0을 통째로 재구성**해 디스크에 기록.
훅·X02 리터럴·X07 패딩 전부 불필요(대사가 원본 자리에 한글로 압축돼 들어감).

맵당 처리:
  1) build_recompress.optimize → 새 섹션0 바이트(글리프표+코드북+블록0~6+table1/table2)
  2) 파일 오프셋 0x800 에 기록
  3) **MDX 파일 헤더의 섹션0 크기(word[1]) 갱신** — 섹션이 커졌으므로 로더가 더 읽어야 함
     (다음 섹션 오프셋을 넘지 않으므로 파일 크기·ISO 레이아웃은 그대로)
  4) 수정 섹터 EDC/ECC 재계산 → xdelta

사용: build_kr.py [out.xdelta]
"""
import sys, os, json, glob, struct, shutil, subprocess, importlib.util
sys.stdout.reconfigure(encoding='utf-8')

_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


br = _L("build_recompress")
bdp = _L("build_disk_patch")
nk = _L("name_kr")
ph = _L("party_hook")
wk = _L("worldmap_kr")
sys.path.insert(0, os.path.join(_here, '..', 'scripts'))
from survey_iso import get_iso_files  # noqa

SEC0_FOFF = br.SEC0_FOFF
GRID_FOFF = 0x14638            # X02.BIN 히라 그리드 → 한글 1(ㄱㄴㄷㄹㅁㅂㅅ)
GRID2_FOFF = 0x146a4           # X02.BIN 카타 그리드 → 한글 2(ㅇㅈㅊㅋㅌㅎ). 카타 입력모드 폐지.
HERO_NAME_FOFF = 0xd400        # X02.BIN 기본 히어로명 テーブル entry0(8B) = アーサー → 공백


WORLD_PX = 16                  # 월드맵 지역명 한글 글자 크기(굴림 임베디드 비트맵 상한)

# --disc 로 패치된 Track 1 을 **바로 플레이 가능한 자리**에 놓는다.
#   · bdp.DISC (…/patch/…Track 1.bin) = **원본 무수정 사본**(MD5 d9849fd1…) = xdelta 소스. 절대 덮지 말 것.
#   · PLAY_DISC (한 단계 위, .cue 가 가리키는 것) = 이전 빌드 산출물. 여기를 덮어쓴다.
PLAY_DISC = os.path.join(os.path.dirname(os.path.dirname(bdp.DISC)),
                         os.path.basename(bdp.DISC))


def build(out_xdelta, only=None, names=False, world=True, dry=False, disc=False):
    """dry=True 면 맵별 예산만 재고 ISO/xdelta 는 만들지 않는다(용량 사전 점검용)."""
    """only: 셋 파일명 부분문자열(예: 'set02') — 지정하면 그 셋만 패치(원인 분리용).
    names=True: 한글 이름입력(≤0xFF 완성형) 통합 — 매 맵 폰트에 완성형 음절 굽고
                X02 그리드 테이블을 한글 반절표로 교체(코드 무패치, 예산 0).
    world=True: 월드맵 지역명(WORLD_MN.BIN) 11개 스프라이트를 한글 비트맵으로 교체.
                ⚠️ 스프라이트 치수는 VDP1 커맨드 테이블(코드) 소관 → **크기 w×16 유지, 내용만 교체**."""
    if names:
        br.NAME_INPUT_GLYPHS = nk.glyphs()     # 매 맵 섹션0 재구성 시 ≤0xFF 슬롯에 완성형 주입
        print("한글 이름입력: 완성형 %d음절 → ≤0xFF 슬롯 (전 맵 폰트)" % len(nk.SYLL))
        # 캐릭터 이름 레코드(680~694) → ≤0xFF 한글 슬롯 (system.json kr, name_kr 슬롯)
        #  🔑 680~687 = 파티 8명. **파티 struct 이름의 진짜 출처가 이 레코드다**(2026-07-16 실기 규명):
        #     레코드가 Huffman 압축돼 있어 디스크 바이트스캔(b1b0bbb0)엔 안 잡혔고, 그래서 오랫동안
        #     "struct 는 X02 0xd400 이 소스"로 오판했다. 실제로는 레코드 680 = `00b1 00b0 00bb 00b0`
        #     (アーサー) 가 디코드돼 struct slot0 에 들어간다 → **레코드를 한글로 바꿔야 이름이 한글**.
        #  🔑 688~694 = NPC(대사 [0b] 가 이 레코드를 직접 렌더).
        _sysj = json.load(open(os.path.join(_here, '..', 'translation', 'system.json'),
                               encoding='utf-8'))
        _krid = {r['id']: r.get('kr', '') for r in _sysj}
        br.NPC_NAME_SLOTS = {
            sid: [nk.SYL2SLOT[c] for c in _krid[sid]]
            for sid in range(680, 695)
            if _krid.get(sid) and all(c in nk.SYL2SLOT for c in _krid[sid])}
        _miss = [s for s in range(680, 695) if s not in br.NPC_NAME_SLOTS]
        print("캐릭터 이름 레코드 한글화 %d개: %s" % (len(br.NPC_NAME_SLOTS),
              ', '.join('%d=%s' % (s, _krid[s]) for s in sorted(br.NPC_NAME_SLOTS))))
        assert not _miss, '슬롯 없는 이름 레코드: %s' % [(s, _krid.get(s)) for s in _miss]
    sets = sorted(glob.glob(os.path.join(_here, '..', 'translation', 'sets', 'set*.json')))
    if only:
        sets = [p for p in sets if only in os.path.basename(p)]
    plans = []          # (map_name, sec_bytes)
    skipped = []
    for sp in sets:
        sj = json.load(open(sp, encoding='utf-8'))
        kr = br.kr_list_of(sj)          # (번역문 리스트, 재번역 플래그) 튜플
        if not any(t.strip() for t in kr[0]):
            continue
        name = os.path.basename(sp)
        rep = sj['rep_map']
        # 몬스터/아이템·마법명(block6 rec0~54): 셋 대표맵 names/<rep>.json → 순번 리스트
        nf = os.path.join(_here, '..', 'translation', 'names',
                          rep.rsplit('.', 1)[0] + '.json')
        nkr = [''] * 55
        if os.path.exists(nf):
            for r in json.load(open(nf, encoding='utf-8')):
                if 0 <= r['rec'] < 55:
                    nkr[r['rec']] = r.get('kr', '')
        br.NAMES_KR = nkr
        try:
            _, st = br.optimize(br.Mdx(rep), kr, verbose=False)
        except SystemExit as e:
            skipped.append((name, str(e))); continue
        n0, extra = st['n0'], st['extra']
        done = 0
        for mp in sj['maps']:
            m = br.Mdx(mp)
            sec, s2 = br.repack(m, kr, n0, verbose=False, extra_full=extra)
            if not s2['ok']:                       # 이 맵은 용량이 달라 실패 → 개별 최적화
                try:
                    sec, s2 = br.optimize(m, kr, verbose=False)
                except SystemExit as e:
                    skipped.append((mp, str(e))); continue
            # ⚠️ **섹션0 크기는 원본과 정확히 같게 유지**(남는 만큼 0 패딩), 헤더는 손대지 않는다.
            #    크기를 바꾸면 뒤 섹션들이 LWRAM에서 밀려 0x0022C000 의 포인터가 깨진다
            #    (M801 단독 패치로 재현: 타이틀 START 시 X01 0x06044BFC 에서 ADDRESS ERROR).
            if len(sec) > m.cur_size:
                skipped.append((mp, '원본 섹션0(%d) 초과 %d' % (m.cur_size, len(sec)))); continue
            sec = sec + b'\x00' * (m.cur_size - len(sec))
            plans.append((mp, sec)); done += 1
        print("  %-16s %-9s 맵 %2d/%2d  완성형 %3d  %6d/%6d B (여유 %d)"
              % (name[:16], rep, done, len(sj['maps']), st['full'],
                 st['total'], st['cap'], st['spare']))
    if not plans:
        raise SystemExit("빌드할 것이 없음")
    print("총 %d 맵 패치" % len(plans))
    if skipped:
        print("⚠️ 스킵 %d: %s" % (len(skipped), ", ".join(m for m, _ in skipped[:8])))

    if dry:
        print("(--dry) 예산 점검만 하고 종료 - ISO/xdelta 안 만듦")
        return

    out_bin = os.path.join(_here, '..', 'build', 'shining_kr.bin')
    os.makedirs(os.path.dirname(out_bin), exist_ok=True)
    shutil.copyfile(bdp.DISC, out_bin)
    dirty = []
    with open(out_bin, 'r+b') as f:
        files = get_iso_files(f)
        name2 = {k.rsplit('/', 1)[-1].upper(): v for k, v in files.items()}
        for mp, sec in plans:
            lba, size = name2[mp.upper()]
            dirty += bdp.write_file_bytes(f, lba, SEC0_FOFF, sec)
            # 헤더(섹션0 크기)는 **건드리지 않는다** — 원본 크기 그대로 쓰므로 갱신 불필요.
        if names:
            lba, size = name2['X02.BIN']
            dirty += bdp.write_file_bytes(f, lba, GRID_FOFF, nk.grid_table(1))
            dirty += bdp.write_file_bytes(f, lba, GRID2_FOFF, nk.grid_table(2))
            print("X02 그리드 → 한글 입력 %d음절(반절표 %d + 파티/NPC %d), 히라(0x%X)·카타(0x%X) 동일표"
                  % (len(nk.SYLL), len(nk.GRID_SYLL), len(nk._EXTRA), GRID_FOFF, GRID2_FOFF))
            # 기본 히어로명 アーサー → 한글. init(0x06072708)은 0x06072400 에서 **5바이트만** 복사
            # (`MOV.L @R1+,R2` 4B → struct+0, `MOV.B @R1,R1` 1B → struct+4) → 4자 + 종료자.
            hero = nk.hero_name_bytes()
            dirty += bdp.write_file_bytes(f, lba, HERO_NAME_FOFF, hero)
            print("기본 히어로명 アーサー → '%s' (X02 file 0x%X = %s)"
                  % (nk.HERO_NAME, HERO_NAME_FOFF, hero.hex()))
            x02_lba = lba          # 뒤에서 lba 가 재할당되므로 검증용으로 보관
            # ── 파티명 struct-rewrite 훅 ──
            blk, tbl = ph.hook_block(bdp.HOOK_ADDR)
            USER = 2048
            x07_lba, x07_sz = name2['X07.BIN']
            hfoff = bdp.HOOK_ADDR - bdp.X07_LOAD
            assert hfoff >= x07_sz, '훅이 X07 실데이터 침범'
            need = hfoff + len(blk)
            secs = (x07_sz + USER - 1) // USER
            assert need <= secs * USER, '훅이 X07 섹터용량 초과(%d>%d)' % (need, secs * USER)
            dirty += bdp.write_file_bytes(f, x07_lba, hfoff, blk)
            new_sz = (need + 3) & ~3
            rec_off, rl = bdp.find_dir_record(f, 'X07.BIN')
            f.seek(rec_off); rec = bytearray(f.read(rl))
            assert struct.unpack('<I', rec[10:14])[0] == x07_sz
            struct.pack_into('<I', rec, 10, new_sz)
            struct.pack_into('>I', rec, 14, new_sz)
            f.seek(rec_off); f.write(rec)
            dirty.append((rec_off, rl))
            assert (new_sz + USER - 1) // USER == secs, '섹터수 변함(파일 시프트)'
            patch = bytes([0xD0, 0x01, 0x40, 0x2B, 0x64, 0xA3, 0x00, 0x09]) \
                + struct.pack('>I', bdp.HOOK_ADDR)
            dirty += bdp.write_file_bytes(f, lba, ph.X02_0B_FOFF, patch)
            print("파티명 훅: X07 %dB @0x%x (TBL 0x%x), X02 [0b] file 0x%X 리다이렉트"
                  % (len(blk), hfoff, tbl, ph.X02_0B_FOFF))
        if world:
            # 월드맵 지역명: 11 스프라이트를 한글로 다시 그림(파일 크기·스프라이트 치수 불변).
            lba, size = name2['WORLD_MN.BIN']
            new = wk.patched_bytes(WORLD_PX)
            assert len(new) == size, '월드맵 크기 변함 %d != %d' % (len(new), size)
            dirty += bdp.write_file_bytes(f, lba, 0, new)
            print("월드맵 지역명: %d개 스프라이트 한글화 (굴림 %dpx)" % (len(wk.LABELS), WORLD_PX))
        if names:
            # ⚠️ **되읽기 검증** — 쓴 줄 알았는데 안 써졌던 사고(2026-07-16 기본 히어로명)를 막는다.
            #    로그가 찍혔다고 바이트가 들어간 게 아니다. 실제 BIN 에서 읽어 대조할 것.
            for foff, want, what in ((HERO_NAME_FOFF, nk.hero_name_bytes(), '기본 히어로명'),
                                     (GRID_FOFF, nk.grid_table(1), '한글 그리드1'),
                                     (GRID2_FOFF, nk.grid_table(2), '한글 그리드2')):
                f.seek(bdp.file_to_bin(x02_lba, foff))
                got = f.read(len(want))
                assert got == want, ('%s 기록 실패 @X02 0x%X\n  기대 %s\n  실제 %s'
                                     % (what, foff, want[:16].hex(), got[:16].hex()))
            print("되읽기 검증 OK: 히어로명·그리드 2종")
        n = bdp.ECC.fix_sectors(f, dirty)
        print("EDC/ECC 재계산: %d 섹터" % n)

    subprocess.run([bdp.XDELTA, '-f', '-e', '-s', bdp.DISC, out_bin, out_xdelta], check=True)
    print("\nxdelta → %s (%d bytes)" % (out_xdelta, os.path.getsize(out_xdelta)))
    if disc:
        assert os.path.abspath(PLAY_DISC) != os.path.abspath(bdp.DISC), '원본을 덮으려 함'
        shutil.move(out_bin, PLAY_DISC)
        print("패치 디스크 → %s (%d bytes)" % (PLAY_DISC, os.path.getsize(PLAY_DISC)))
    else:
        os.remove(out_bin)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    names = '--names' in sys.argv
    build(args[0] if len(args) > 0 else 'shining_kr.xdelta',
          args[1] if len(args) > 1 else None, names=names,
          world='--no-world' not in sys.argv, dry='--dry' in sys.argv,
          disc='--disc' in sys.argv)
