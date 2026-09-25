#!/usr/bin/env python3
"""
Shining the Holy Ark — 씬 대사 추출기 v2 (2026-07-12, 레코드 기반=정확 경계).

⚠️ extract_dialogue.py(brute-force 경계추측)는 복잡한 박스에서 drift/desync/병합 발생 → 폐기.
   씬 대사도 table2_flat 블록의 **길이프리픽스 레코드**([len:1][data:len])로 정확히 프레이밍된다
   (extract_script.py와 동일 메커니즘). box 경계가 명시적이라 추측 불필요.

검증(2026-07-12): forest = block6, 레코드 data-offset 0x225ec6부터. rec59=box0(どおりで) 등
   런타임 디코드버퍼와 완전 일치. 예전 brute-force forest.json의 box5 병합깨짐이 이걸로 해결됨.

사용: extract_scene.py <lwram_deswap.bin> <block_hi> <start_addr_hex> [end_addr_hex] [glyph_table]
  → JSON 리스트 [{addr, len, jp, kr:""}] 를 stdout. start~end(포함) 범위의 레코드만.
"""
import sys, os, io, json, importlib.util

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location("extract_script", os.path.join(_here, "extract_script.py"))
_es = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_es)


def extract(lwram, block_hi, start_addr, end_addr, glyph_path):
    s = _es.Script(lwram, glyph_path)
    out = []
    for off, ln, toks in s.records(block_hi):
        data = off + 1
        if data < start_addr:
            continue
        if end_addr is not None and data > end_addr:
            break
        out.append({'addr': '0x%x' % data, 'len': ln,
                    'jp': _es.render(toks, s.GT), 'kr': ''})
    return out


if __name__ == '__main__':
    lwram = open(sys.argv[1], 'rb').read()
    block_hi = int(sys.argv[2], 0)
    start_addr = int(sys.argv[3], 16)
    end_addr = int(sys.argv[4], 16) if len(sys.argv) > 4 and sys.argv[4] != '-' else None
    gp = sys.argv[5] if len(sys.argv) > 5 else os.path.join(_here, '..', 'docs', 'glyph_table_forest.txt')
    res = extract(lwram, block_hi, start_addr, end_addr, gp)
    w = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    json.dump(res, w, ensure_ascii=False, indent=1)
    w.flush()
