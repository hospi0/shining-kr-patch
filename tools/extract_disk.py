#!/usr/bin/env python3
"""
Shining the Holy Ark — 디스크 스크립트 추출기 (2026-07-11 완성·검증).

X2SAMPLE.MES를 디스크 파일에서 직접 추출한다. 이 파일은 자기완결적:
파일이 런타임 0x218000에 로드되므로 `addr → file_off = addr - 0x218000`.
- 헤더 [+4]=table1(코드북), [+8]=table2_flat(블록 포인터 배열), [+c]=size(0x80000).
- 디스크 헤더는 런타임과 값이 다름(런타임은 씬 데이터 삽입으로 +0x2DF4 재배치).
  디스크 파일은 자기 헤더 포인터로 완결 디코드된다.

검증(2026-07-11): 디스크 block6가 런타임 forest_block6(state0~3 스크린샷 확정본)과
레코드 단위 내용 완전 일치(길이값만 패딩비트 차이).

⚠️ X2SAMPLE.MES = 공용 시스템/전투/아이템/스탯 메시지(7블록 1928레코드).
   NPC 스토리 대사는 여기 없음 → X6*.BIN 지역 오버레이(별도 미해독).

사용: python tools/extract_disk.py [X2SAMPLE.MES] [glyph_table] > script.txt
      (인자 없으면 extract/X2SAMPLE.MES, docs/glyph_table_confirmed.txt 기본)
"""
import sys, os, io, importlib.util

_here = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location("extract_script", os.path.join(_here, "extract_script.py"))
_es = importlib.util.module_from_spec(spec); spec.loader.exec_module(_es)

DISK_BASE = 0x218000

BLOCK_ROLE = {
    0: "제어/짧은코드",
    1: "스탯업 메시지 (XX가 올랐다)",
    2: "시스템 안내문",
    3: "아이템/번호",
    4: "방어구·마법 아이템명",
    5: "아이템명 (가타카나 계열)",
    6: "전투 메시지·아이템 획득",
}


def extract_all(mes_path, glyph_path):
    mes = open(mes_path, 'rb').read()
    s = _es.Script(mes, glyph_path, base=DISK_BASE)
    blocks = []
    for hi in range(7):
        base = s.block_base(hi)
        if not (DISK_BASE <= base < DISK_BASE + len(mes)):
            break
        recs = list(s.records(hi, maxbytes=0x4000))
        rendered = [(off, ln, _es.render(toks, s.GT)) for off, ln, toks in recs]
        blocks.append((hi, base, rendered))
    return s, blocks


if __name__ == '__main__':
    mes_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_here, '..', 'extract', 'X2SAMPLE.MES')
    glyph_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_here, '..', 'docs', 'glyph_table_confirmed.txt')
    out = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    s, blocks = extract_all(mes_path, glyph_path)
    tot = 0
    for hi, base, recs in blocks:
        role = BLOCK_ROLE.get(hi, '?')
        out.write(f"\n===== BLOCK hi={hi} base=0x{base:x} records={len(recs)}  [{role}] =====\n")
        for i, (off, ln, txt) in enumerate(recs):
            out.write(f"  [{i}] @0x{off:x} len={ln}: {txt.replace(chr(10), '\\n')}\n")
        tot += len(recs)
    out.write(f"\n# total {tot} records across {len(blocks)} blocks\n")
    out.flush()
