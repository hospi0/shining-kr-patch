#!/usr/bin/env python3
"""
Shining the Holy Ark — 글리프 폰트 코덱 (2026-07-12 역공학·검증 완료).

폰트 포맷 (렌더러 0x606c9e4→0x606d408→블릿 0x606d4e0→디컴프 0x606d684 역공학):
- 글리프 테이블 = `[0x218000]값(런타임 0x21800c) + (glyph_index − 0x20) × 32`.
- 각 글리프 = **32바이트**: `[width:2B BE] + [15행 × 2B]`.
  - word0 = 글리프 폭(px). 예: を=12, 。=6, ？=9, 공백=8.
  - word1..15 = 15행, 각 16비트 BE 1bpp 비트맵(MSB=왼쪽 픽셀). 글리프는 보통 상단 정렬 ~12px.
- 렌더러가 이 1bpp를 글리프 팔레트색(0x16 등)으로 8bpp 전개해 staging(0x06084000+line×512)→VDP2 VRAM(0x25E44000) 블릿.
- **검증**: を(0x86)/あ(0x91)/？(0x3f)/た(0xe0)/。(0xa1) 32B 엔트리를 이 포맷으로 렌더→해당 문자 정확 표시.

한글 삽입: 12~15px 1bpp 한글 글리프를 이 32바이트 포맷으로 인코딩해 슬롯에 배치 + 우회훅으로 인덱스 주입.
"""
import struct, sys

GLYPH_BYTES = 32
ROWS = 15
WIDTH_PX = 16  # 비트맵 폭(픽셀), word당 16bit


def decode_glyph(entry: bytes):
    """32바이트 엔트리 → (width, [15행 × 16px 0/1 리스트])."""
    assert len(entry) >= GLYPH_BYTES, f'엔트리 {len(entry)}B < 32'
    width = struct.unpack('>H', entry[0:2])[0]
    rows = []
    for r in range(ROWS):
        w = struct.unpack('>H', entry[2 + r * 2:4 + r * 2])[0]
        rows.append([(w >> (15 - b)) & 1 for b in range(WIDTH_PX)])
    return width, rows


def encode_glyph(width: int, rows) -> bytes:
    """(width, [최대15행 × 최대16px 0/1]) → 32바이트 엔트리."""
    out = struct.pack('>H', width)
    for r in range(ROWS):
        row = rows[r] if r < len(rows) else []
        w = 0
        for b in range(WIDTH_PX):
            if b < len(row) and row[b]:
                w |= (1 << (15 - b))
        out += struct.pack('>H', w)
    assert len(out) == GLYPH_BYTES
    return out


def rows_from_art(art, on='#'):
    """ASCII 아트(문자열 리스트) → 0/1 행 리스트. 폭은 최장 행 길이."""
    rows = [[1 if ch == on else 0 for ch in line] for line in art]
    width = max((len(line) for line in art), default=0)
    return width, rows


def table_addr(glyph_base, idx):
    """글리프 테이블 절대주소 = base + (idx-0x20)*32. base=[0x218000]값."""
    return glyph_base + (idx - 0x20) * GLYPH_BYTES


if __name__ == '__main__':
    # 데모: LWRAM 스냅샷에서 글리프 추출·렌더(육안 검증)
    import importlib
    lw = open(sys.argv[1], 'rb').read() if len(sys.argv) > 1 else None
    if lw:
        base = struct.unpack('>I', lw[0x18000:0x18004])[0]
        print(f'glyph table base = 0x{base:x}')
        for idx in (0x86, 0x91, 0x3f):
            a = table_addr(base, idx)
            e = lw[a - 0x200000:a - 0x200000 + 32]
            w, rows = decode_glyph(e)
            print(f'\nglyph 0x{idx:03x} width={w}:')
            for row in rows:
                print('  ' + ''.join('#' if p else '.' for p in row[:w]))
