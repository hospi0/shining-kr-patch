#!/usr/bin/env python3
"""
전체 게임 그룹별 디스크 빌드 (2026-07-13) — 지역마다 자기 번역 페이로드.

translation/regions/*.json (각 지역 대사 + kr 번역) → 각 지역 MDX 폰트블록에 그 지역 페이로드.
번역 안 된 지역은 원본 폰트 유지(JP). 훅/X02리터럴/X07/ECC는 전역 공통.

파이프라인:
  region JSON(boxes: addr,jp,kr) → MDX에서 토큰 재추출해 jp_hash 계산
    → kr 텍스트 → 토큰(음절=글리프, 공백0x20/줄바꿈0x03/종료0x08)
    → 유니크 음절 글리프(hangul_font) → pack_scene 페이로드
    → 그 지역 maps[] 전 MDX 폰트블록(0x80c+)에 기록
  전역: X07 훅(외부테이블 0x219c0c), X02 리터럴 3개, EDC/ECC → xdelta.

사용: build_full.py [out.xdelta]   (kr 채워진 지역만 반영)
"""
import sys, os, io, json, struct, glob, shutil, subprocess, importlib.util

_here = os.path.dirname(os.path.abspath(__file__))


def _Ld(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


em = _Ld("extract_mdx"); es = _Ld("extract_script"); ps = _Ld("pack_scene")
hf = _Ld("hangul_font"); bh3 = _Ld("build_hook_v3"); bdp = _Ld("build_disk_patch")
sys.path.insert(0, os.path.join(_here, '..', 'scripts'))
from survey_iso import get_iso_files, read_sectors, sec_off, USER  # noqa
ECC = bdp.ECC

MDX_BASE = 0x217800
STORY_START_REC = 55


def hook_hash(toks):
    h = 0
    for t in toks:
        if t in (0x0008, 0x0004):
            break
        h = ((h * 33) + (t & 0xffff)) & 0xffffffff
    return h


_glyph_cache = {}


def glyph_of(ch):
    if ch not in _glyph_cache:
        _glyph_cache[ch] = hf.glyph_for(ch)[0]
    return _glyph_cache[ch]


import re as _re
_TOK_RE = _re.compile(r'\[([0-9a-fA-F]{2,4})\]|\{(br|sp)\}')


def kr_to_tokens(kr):
    """한글 텍스트 → pack_scene 토큰열. 공백/줄바꿈=제어, 나머지=글리프. 끝에 0x08.
    특수: `[XXX]`(16진 글리프인덱스) = 원본 글리프 토큰 그대로 통과(식별/한자 유지용).
          `{br}`=줄바꿈, `{sp}`=공백. 리터럴 대괄호는 `[[` `]]`... 는 미지원(드묾)."""
    toks = []
    i = 0
    while i < len(kr):
        m = _TOK_RE.match(kr, i)
        if m:
            if m.group(1) is not None:            # [XXX] = 원본 글리프 토큰 통과
                toks.append(('t', int(m.group(1), 16)))
            elif m.group(2) == 'br':
                toks.append(('c', 0x03))
            else:
                toks.append(('c', 0x20))
            i = m.end(); continue
        ch = kr[i]; i += 1
        if ch == '\n':
            toks.append(('c', 0x03))
        elif ch in ' 　':
            toks.append(('c', 0x20))
        else:
            toks.append(('g', ch))
    toks.append(('c', 0x08))
    return toks


def build_region_payload(region_json):
    """set/region JSON → (payload, meta) 또는 None(번역 없음). pack v1(슬롯0x100 통째)."""
    boxes_tr = [b for b in region_json['boxes'] if b.get('kr', '').strip()]
    if not boxes_tr:
        return None
    rep = region_json.get('rep_map') or region_json.get('region')   # sets=rep_map, regions=region
    mdx = em.read_mdx(rep)
    s = es.Script(mdx, os.path.join(_here, '..', 'docs', 'glyph_table_forest.txt'), base=MDX_BASE)
    by_addr = {'0x%x' % (off + 1): toks for off, ln, toks in list(s.records(6))[STORY_START_REC:]}
    packed = []
    for b in boxes_tr:
        toks = by_addr.get(b['addr'])
        if toks is None:
            raise SystemExit('addr %s not found in %s' % (b['addr'], rep))
        packed.append((hook_hash(toks), kr_to_tokens(b['kr'])))
    payload, meta = ps.pack(packed, glyph_of)
    meta['n_tr'] = len(boxes_tr)
    return payload, meta


def build(out_xdelta):
    # 셋별 페이로드 (슬롯0x100 통째). translation/sets/ 우선, 없으면 regions/.
    set_dir = os.path.join(_here, '..', 'translation', 'sets')
    src_dir = set_dir if glob.glob(os.path.join(set_dir, '*.json')) else \
        os.path.join(_here, '..', 'translation', 'regions')
    region_files = sorted(glob.glob(os.path.join(src_dir, '*.json')))
    print(f"번역 소스: {os.path.basename(src_dir)}/ ({len(region_files)}개)")
    map_payload = {}   # MDX name -> payload bytes
    done = []
    skipped = []
    for rf in region_files:
        rj = json.load(open(rf, encoding='utf-8'))
        try:
            r = build_region_payload(rj)
        except SystemExit as e:
            rep = rj.get('rep_map') or rj.get('region')
            skipped.append((rep, str(e))); continue
        if r is None:
            continue
        payload, meta = r
        for mp in rj['maps']:
            map_payload[mp] = payload
        rep = rj.get('rep_map') or rj.get('region')
        done.append((rep, meta['n_tr'], meta['payload_size'], meta['spare']))
    if not map_payload:
        raise SystemExit('번역된 지역이 없음 (region JSON의 kr가 전부 비어있음)')
    print("번역 반영 지역:")
    for reg, ntr, sz, spare in done:
        print(f"  {reg:12} 번역 {ntr}박스, 페이로드 {sz}B (여유 {spare}B)")
    if skipped:
        print("[예산초과로 스킵 %d]: %s" % (len(skipped), ", ".join(r for r, _ in skipped)))

    # 훅 (테이블 = 고정주소 0x219c0c 직접)
    hook, _ = bh3.build([], b'', 0x100, bdp.HOOK_ADDR, inject=False, table_addr=ps.DATA_ADDR)

    out_bin = os.path.join(_here, '..', 'build', 'shining_kr_full.bin')
    os.makedirs(os.path.dirname(out_bin), exist_ok=True)
    shutil.copyfile(bdp.DISC, out_bin)
    dirty = []
    with open(out_bin, 'r+b') as f:
        files = get_iso_files(f)
        name2lba = {k.rsplit('/', 1)[-1].upper(): v for k, v in files.items()}

        # (1) 지역 MDX 폰트블록에 writes 기록. 폰트블록 시작(슬롯0x20)을 고정폰트 시그니처로
        #     찾은 뒤, 각 write를 slot→블록내오프셋으로 환산해 기록.
        # 슬롯0x100 위치를 그 슬롯 원본글리프(정적폰트, 전맵 동일)로 검색해 페이로드 기록
        x2s_lba, x2s_sz = name2lba['X2SAMPLE.MES']
        x2s_data = read_sectors(f, x2s_lba, x2s_sz)
        sig_off = 0xC + (0x100 - 0x20) * 32     # X2SAMPLE 내 슬롯0x100 = 0x1c0c
        sig = x2s_data[sig_off:sig_off + 128]
        npatch = 0
        for mp, payload in map_payload.items():
            lba, sz = name2lba[mp.upper()]
            data = read_sectors(f, lba, sz)
            hits = [i for i in range(len(data)) if data[i:i + 128] == sig]
            if len(hits) != 1:
                print(f"  ⚠️{mp}: 시그니처 {len(hits)}개 — 스킵"); continue
            dirty += bdp.write_file_bytes(f, lba, hits[0], payload)
            npatch += 1
        print(f"  [1] 폰트 페이로드: {npatch}/{len(map_payload)} MDX (슬롯0x100 통째)")

        # (2) X07 훅 + 디렉토리 size
        x07_lba, x07_sz = name2lba['X07.BIN']
        hfoff = bdp.HOOK_ADDR - bdp.X07_LOAD
        dirty += bdp.write_file_bytes(f, x07_lba, hfoff, hook)
        new_sz = (hfoff + len(hook) + 3) & ~3
        rec_off, rl = bdp.find_dir_record(f, 'X07.BIN')
        f.seek(rec_off); rec = bytearray(f.read(rl))
        struct.pack_into('<I', rec, 10, new_sz); struct.pack_into('>I', rec, 14, new_sz)
        f.seek(rec_off); f.write(rec); dirty.append((rec_off, rl))
        print(f"  [2] X07 훅 {len(hook)}B @0x{bdp.HOOK_ADDR:x}, dir size->{new_sz}")

        # (3) X02 리터럴
        x02_lba, x02_sz = name2lba['X02.BIN']
        for lo in bdp.LIT_OFFS:
            dirty += bdp.write_file_bytes(f, x02_lba, lo, struct.pack('>I', bdp.HOOK_ADDR))
        print(f"  [3] X02 리터럴 3개 -> 0x{bdp.HOOK_ADDR:x}")

        # (4) ECC
        n = ECC.fix_sectors(f, dirty)
        print(f"  [4] EDC/ECC 재계산: {n} 섹터")

    subprocess.run([bdp.XDELTA, '-f', '-e', '-s', bdp.DISC, out_bin, out_xdelta], check=True)
    os.remove(out_bin)
    print(f"\nxdelta -> {out_xdelta} ({os.path.getsize(out_xdelta)} bytes). patched BIN 삭제.")


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'shining_kr.xdelta'
    build(out)
