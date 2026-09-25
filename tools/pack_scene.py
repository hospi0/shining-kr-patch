#!/usr/bin/env python3
"""
씬 페이로드 패커 v1 (2026-07-13, 롤백판) — 슬롯 0x100부터 통째 배치. **실기 검증됨**.

⚠️free-slot 배치(v2)는 실기에서 대사 깨짐 → 폐기, 이 v1로 롤백.
폰트블록(슬롯0x20~0x34F) 맵로드 시 LWRAM 0x21800c 복사. 0x20~0xFF=가나/숫자/구두점 유지,
0x100~0x34F(592슬롯=18944B)를 [번역데이터+한글글리프]로 재구성. 슬롯0x350+ 사용금지.

레이아웃: 슬롯0x100(=고정주소 0x219c0c)부터
  [table:(jp_hash4,kr_ptr4)*N,0] + [토큰배열들] + (32B정렬) [글리프32B*음절].
훅 TABLE 리터럴 = DATA_ADDR(0x219c0c) 직접.
⚠️미해결: 이 슬롯들은 정적한자 자리라 미번역 대사가 그 한자 쓰면 일부 깨질 수 있음(완역시 소멸).
"""
import struct

GLYPH_BASE = 0x21800c
FIRST_FREE_SLOT = 0x100
LAST_SLOT = 0x34F
SLOT = 32
DATA_ADDR = GLYPH_BASE + (FIRST_FREE_SLOT - 0x20) * SLOT   # 0x219c0c
BUDGET = (LAST_SLOT + 1 - FIRST_FREE_SLOT) * SLOT          # 18944
PAD = 0x00


def pack(boxes, glyph_of):
    syls = []
    seen = set()
    for _, toks in boxes:
        for kind, v in toks:
            if kind == 'g' and v not in seen:
                seen.add(v); syls.append(v)
    tbl_size = len(boxes) * 8 + 4
    data_size = tbl_size + sum(len(toks) * 2 for _, toks in boxes)
    data_slots = (data_size + SLOT - 1) // SLOT
    first_glyph_slot = FIRST_FREE_SLOT + data_slots
    total = data_slots * SLOT + len(syls) * SLOT
    if total > BUDGET:
        raise SystemExit("예산 초과 %d>%dB (박스%d,음절%d)" % (total, BUDGET, len(boxes), len(syls)))
    idx_of = {s: first_glyph_slot + i for i, s in enumerate(syls)}
    arrs = bytearray()
    ptrs = []
    for _, toks in boxes:
        ptrs.append(DATA_ADDR + tbl_size + len(arrs))
        for kind, v in toks:
            arrs += struct.pack('>H', idx_of[v] if kind == 'g' else v)
    tbl = bytearray()
    for (h, _), p in zip(boxes, ptrs):
        tbl += struct.pack('>I', h) + struct.pack('>I', p)
    tbl += struct.pack('>I', 0)
    payload = bytearray(tbl + arrs)
    payload += bytes([PAD]) * (data_slots * SLOT - len(payload))
    for s in syls:
        g = glyph_of(s)
        assert len(g) == 32
        payload += g
    meta = {'n_boxes': len(boxes), 'n_syllables': len(syls), 'payload_size': len(payload),
            'first_glyph_slot': first_glyph_slot, 'budget': BUDGET, 'spare': BUDGET - len(payload),
            'data_addr': DATA_ADDR}
    return bytes(payload), meta
