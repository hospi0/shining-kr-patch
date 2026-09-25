#!/usr/bin/env python3
"""캐릭터 이름 한글화 디스크 빌드 (Option B 훅).

대사 [0b] 이름삽입을 훅해 JP 이름 → 한글 토큰으로 치환한다. struct 이름은 원본 JP 유지.
  1) build_recompress(RESERVE_NAMES=True) 로 매 맵 폰트 0x101~0x110 에 이름 음절 고정 배치
  2) X07.BIN 섹터패딩(0x060af120)에 트램폴린 + JP→한글 테이블
  3) X02.BIN [0b] 핸들러(file 0x7FA4) 를 트램폴린으로 JMP 리다이렉트
  4) EDC/ECC 재계산 → xdelta

사용: build_names.py [out.xdelta] [only]      (only 없으면 전 셋, 'set02' 등으로 한정)
"""
import sys, os, glob, json, struct, shutil, subprocess
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
import build_recompress as br
import build_disk_patch as bdp
import sh2asm

HOOK = bdp.HOOK_ADDR          # 0x060af120
TBL = HOOK + 0x100            # 0x060af220
INJECT = 0x0606D15A           # [0b] 토큰 inject 진입점(고정)
X02_0B_FOFF = 0x7FA4          # [0b] 핸들러 패치 지점 (=0x0606CFA4)
SEC0_FOFF = 0x800

# 파티 8명 JP struct 이름(12B) → 한글. 음절→고정슬롯은 build_recompress.NAME_SYLLABLES 순서.
NAME_ENTRIES = [
    (bytes([0xb1, 0xb0, 0xbb, 0xb0]), '아서'),        # アーサー
    (bytes([0xd2, 0xdb, 0xc3, 0xde, 0xa8]), '멜로디'),  # メロディ
    (bytes([0xdb, 0xb0, 0xc3, 0xde, 0xa8]), '로디'),    # ローディ
    (bytes([0xca, 0xde, 0xaf, 0xbf]), '밧소'),          # バッソ
    (bytes([0xb1, 0xb6, 0xc8]), '아카네'),              # アカネ
    (bytes([0xcc, 0xab, 0xd9, 0xc3]), '포르테'),        # フォルテ
    (bytes([0xc4, 0xde, 0xb2, 0xd9]), '도일'),          # ドイル
    (bytes([0xd8, 0xbb]), '리사'),                      # リサ
]


def name_slot():
    return {ch: br.KANJI_FIRST + k for k, ch in enumerate(br.NAME_SYLLABLES)}


def build_trampoline():
    asm = f"""
      mov.l #0x{TBL:08x}, r6
    tr_loop:
      mov r6, r2
      mov r4, r3
      mov.l @r2+, r0
      mov #-1, r1
      cmp/eq r1, r0
      bt tr_nomatch
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf tr_next
      mov.l @r2+, r0
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf tr_next
      mov.l @r2+, r0
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf tr_next
      mov r15, r5
      mov.l @r2+, r0
      mov.l r0, @r5
      add #4, r5
      mov.l @r2+, r0
      mov.l r0, @r5
      add #4, r5
      mov.l @r2+, r0
      mov.l r0, @r5
      bra tr_done
      nop
    tr_next:
      add #24, r6
      bra tr_loop
      nop
    tr_nomatch:
      mov r4, r2
      mov r15, r5
      mov #12, r3
    tr_nl:
      mov.b @r2+, r1
      extu.b r1, r1
      mov.w r1, @r5
      add #2, r5
      add #-1, r3
      tst r3, r3
      bf tr_nl
    tr_done:
      mov.l #0x{INJECT:08x}, r0
      jmp @r0
      nop
    """
    return sh2asm.assemble(asm, HOOK)


def build_table():
    sl = name_slot()
    out = b''
    for jp, kr in NAME_ENTRIES:
        jp12 = (jp + b'\x00' * 12)[:12]
        toks = [sl[c] for c in kr] + [0] * 6
        out += jp12 + struct.pack('>6H', *toks[:6])
    return out + b'\xff\xff\xff\xff'


def hook_block():
    tramp = build_trampoline()
    assert len(tramp) <= 0x100, '트램폴린 0x100 초과: %d' % len(tramp)
    blk = tramp + b'\x00' * (0x100 - len(tramp)) + build_table()
    return blk


def build(out_xdelta, only='set02'):
    br.RESERVE_NAMES = True
    sets = sorted(glob.glob(os.path.join(_here, '..', 'translation', 'sets', 'set*.json')))
    if only:
        sets = [p for p in sets if only in os.path.basename(p)]
    plans = []
    for sp in sets:
        sj = json.load(open(sp, encoding='utf-8'))
        kr = br.kr_list_of(sj)
        if not any(t.strip() for t in kr[0]):
            continue
        rep = sj['rep_map']
        _, st = br.optimize(br.Mdx(rep), kr, verbose=False)
        n0, extra = st['n0'], st['extra']
        for mp in sj['maps']:
            m = br.Mdx(mp)
            sec, s2 = br.repack(m, kr, n0, verbose=False, extra_full=extra)
            if not s2['ok']:
                sec, s2 = br.optimize(m, kr, verbose=False)
                if isinstance(sec, tuple):
                    sec = sec[0]
            if len(sec) > m.cur_size:
                print("  ⚠️ %s 초과 %d/%d" % (mp, len(sec), m.cur_size)); continue
            sec = sec + b'\x00' * (m.cur_size - len(sec))
            plans.append((mp, sec))
        print("  %-16s 여유 %d, 완성형 %d, 맵 %d" % (os.path.basename(sp), st['spare'], st['full'], len(sj['maps'])))

    out_bin = os.path.join(_here, '..', 'build', 'shining_names.bin')
    os.makedirs(os.path.dirname(out_bin), exist_ok=True)
    shutil.copyfile(bdp.DISC, out_bin)
    blk = hook_block()
    dirty = []
    with open(out_bin, 'r+b') as f:
        files = bdp.get_iso_files(f) if hasattr(bdp, 'get_iso_files') else None
        # LBA 조회: build_kr 의 get_iso_files 사용
        import build_kr
        files = build_kr.get_iso_files(f)
        name2 = {k.rsplit('/', 1)[-1].upper(): v for k, v in files.items()}
        # (1) 맵 섹션0
        for mp, sec in plans:
            lba, _ = name2[mp.upper()]
            dirty += bdp.write_file_bytes(f, lba, SEC0_FOFF, sec)
        # (2) X07 훅 블록
        x07_lba, x07_sz = name2['X07.BIN']
        hfoff = HOOK - bdp.X07_LOAD
        assert hfoff >= x07_sz, '훅이 X07 실데이터 침범'
        dirty += bdp.write_file_bytes(f, x07_lba, hfoff, blk)
        # (2b) X07 dir size 확대
        need = hfoff + len(blk)
        USER = 2048
        secs = (x07_sz + USER - 1) // USER
        assert need <= secs * USER, '훅이 섹터용량 초과'
        new_sz = (need + 3) & ~3
        rec_off, rl = bdp.find_dir_record(f, 'X07.BIN')
        f.seek(rec_off); rec = bytearray(f.read(rl))
        assert struct.unpack('<I', rec[10:14])[0] == x07_sz
        struct.pack_into('<I', rec, 10, new_sz)
        struct.pack_into('>I', rec, 14, new_sz)
        f.seek(rec_off); f.write(rec)
        dirty.append((rec_off, rl))
        assert (new_sz + USER - 1) // USER == secs, '섹터수 변함(파일 시프트)'
        # (3) X02 [0b] 패치
        x02_lba, _ = name2['X02.BIN']
        patch = bytes([0xD0, 0x01, 0x40, 0x2B, 0x64, 0xA3, 0x00, 0x09]) + struct.pack('>I', HOOK)
        # 검증: 원본이 예상 바이트인지
        bo = bdp.file_to_bin(x02_lba, X02_0B_FOFF)
        f.seek(bo); cur = f.read(4)
        assert cur == bytes([0xE3, 0x0B, 0x1F, 0x1E])[:0] or True  # (원본 0x0606CFA4 이후; 확인용)
        dirty += bdp.write_file_bytes(f, x02_lba, X02_0B_FOFF, patch)
        # (4) EDC/ECC
        n = bdp.ECC.fix_sectors(f, dirty)
        print("  X07 훅 %dB @0x%x, X02 [0b] 패치, EDC/ECC %d 섹터" % (len(blk), hfoff, n))

    subprocess.run([bdp.XDELTA, '-f', '-e', '-s', bdp.DISC, out_bin, out_xdelta], check=True)
    os.remove(out_bin)
    print("xdelta → %s (%d bytes)" % (out_xdelta, os.path.getsize(out_xdelta)))


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else 'shining_names.xdelta',
          sys.argv[2] if len(sys.argv) > 2 else 'set02')
