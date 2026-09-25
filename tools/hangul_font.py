#!/usr/bin/env python3
"""
Shining the Holy Ark — 한글 글리프 생성기 (2026-07-12).
임의 한글 음절/문자를 게임 32바이트 1bpp 글리프 포맷으로 변환(폰트=굴림, 임베디드 비트맵).

게임 글리프 포맷(font.py 참조): [width:2B BE] + [15행 × 16bit BE 1bpp]. 렌더러가 1bpp→8bpp 전개.
한글은 12px 안팎으로 렌더→1bpp 임계화→상단정렬로 셀 배치.

사용: python tools/hangul_font.py 가 한 글  (문자들의 게임 글리프 hex 출력 + 미리보기 PNG)
"""
import sys, struct
from PIL import Image, ImageFont, ImageDraw

FONT_PATH = r"C:\Windows\Fonts\gulim.ttc"
ROWS = 15
CELLW = 16


def _dot_rows(cols, rows_range):
    """직접 그리는 점 비트맵(ROWS×CELLW). cols/rows_range = (시작,끝) 포함."""
    g = [[0] * CELLW for _ in range(ROWS)]
    for r in range(rows_range[0], rows_range[1] + 1):
        for c in range(cols[0], cols[1] + 1):
            g[r][c] = 1
    return g


# 굴림 12px 가 글리프를 못 그려 속빈 □(.notdef 박스)로 내보내는 구두점 → 직접 점/막대로.
#  ・(U+30FB 중점) → 세로중앙 3×3 점(・・・ 말줄임표).  ー(U+30FC 장음) → 세로중앙 가로막대(—).
#  (剣 등 일본 한자는 글리프 대체가 아니라 번역으로 제거 — 후리가나 주석은 한글 읽기만 남긴다.)
SPECIAL_GLYPHS = {
    '・': (6, _dot_rows((1, 3), (6, 8))),
    'ー': (10, _dot_rows((1, 8), (7, 8))),
}


def render_char(ch, px=12, font_path=FONT_PATH, y_off=1, x_off=0, width=None):
    """문자 → (width, [ROWS × CELLW 0/1]). 굴림 임베디드 비트맵 크기(px)로 렌더 후 1bpp."""
    if ch in SPECIAL_GLYPHS:
        v = SPECIAL_GLYPHS[ch]
        if isinstance(v, str):
            ch = v                       # 이체자 치환 후 정상 렌더로 진행
        else:
            return v
    font = ImageFont.truetype(font_path, px)
    # 넉넉한 캔버스에 그린 뒤 크롭
    img = Image.new('L', (CELLW + 4, ROWS + 4), 0)
    d = ImageDraw.Draw(img)
    d.text((x_off, y_off), ch, fill=255, font=font)
    rows = []
    for r in range(ROWS):
        row = [1 if img.getpixel((c, r)) >= 96 else 0 for c in range(CELLW)]
        rows.append(row)
    if width is None:
        # 실제 사용 폭 = 마지막 1픽셀 열 +2 (자간)
        maxc = 0
        for row in rows:
            for c in range(CELLW):
                if row[c]:
                    maxc = max(maxc, c)
        width = min(CELLW, maxc + 2) if maxc else px
    return width, rows


def encode_glyph(width, rows):
    """(width, rows) → 32바이트 게임 글리프."""
    out = struct.pack('>H', width)
    for r in range(ROWS):
        row = rows[r] if r < len(rows) else []
        w = 0
        for b in range(CELLW):
            if b < len(row) and row[b]:
                w |= (1 << (15 - b))
        out += struct.pack('>H', w)
    return out


def glyph_for(ch, **kw):
    w, rows = render_char(ch, **kw)
    return encode_glyph(w, rows), w, rows


if __name__ == '__main__':
    chars = sys.argv[1:] or ['가', '한', '글', '안', '녕', '하', '세', '요']
    cell = 18
    img = Image.new('L', (len(chars) * cell, cell), 0)
    px = img.load()
    for gi, ch in enumerate(chars):
        entry, w, rows = glyph_for(ch)
        print('%s (w=%d): %s' % (ch, w, entry.hex()))
        for r, row in enumerate(rows):
            for b, p in enumerate(row):
                if p and gi * cell + b < img.width and r < cell:
                    px[gi * cell + b, r] = 255
    img = img.resize((img.width * 8, img.height * 8), Image.NEAREST)
    out = 'extract/state2/hangul_font_test.png'
    img.save(out)
    print('preview:', out)
