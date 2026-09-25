#!/usr/bin/env python3
"""
Shining the Holy Ark — 월드맵 지역명(WORLD_MN.BIN) 한글화 (2026-07-16).

## 파일 구조 (추가65 에서 해독)
헤더·디렉토리 **없음**. 폭이 서로 다른 **스프라이트 11개가 그냥 이어붙어** 있고 전부 **높이 16**.
시작 바이트는 전부 0x100 정렬. 픽셀 = 16비트 RGB555 **MSB|B|G|R**(새턴), 5색만 사용.

## ⚠️ 절대 제약
스프라이트 치수(W/H)는 이 파일에 없다 — **VDP1 커맨드 테이블(코드) 소관**.
→ **각 스프라이트의 크기(w×16)를 그대로 유지**하고 내용만 다시 그릴 것.

## 글자 스타일 (원본 픽셀 실측)
`W g #` 순서 = 흰 본체 → 오른쪽 회색 1px → 우하단 검정 외곽선.
검정 픽셀의 **좌상단에 본체가 있는 경우 99%** = 빛이 좌상단에서 오는 입체 표현.
"""
import os, sys, struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hangul_font as hf
from PIL import Image, ImageFont, ImageDraw

_here = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(_here, '..', 'extract', 'WORLD_MN.BIN')

TR, BK, WH, GY = 0x0000, 0x8000, 0xffff, 0xd294   # 투명/검정외곽/흰본체/회색음영
H = 16                                            # 전 스프라이트 공통 높이

# (byte offset, 폭, 원문, 한글) — 한글 표기는 system.json id 840~854 및 대사와 통일
LABELS = [
    (0x0000, 136, 'ファーイースト村', '파 이스트 마을'),
    (0x1100,  96, '山脈の洞窟',       '산맥의 동굴'),
    (0x1d00,  88, '南のほこら',       '남쪽 사당'),
    (0x2800,  88, '西のほこら',       '서쪽 사당'),
    (0x3300,  88, '東のほこら',       '동쪽 사당'),
    (0x3e00, 128, 'アボリジンの森',   '아보리진의 숲'),
    (0x4e00, 144, 'エンリッチ城下町', '엔리치 성하마을'),
    (0x6000,  80, '迷いの森',         '미혹의 숲'),
    (0x6a00,  80, '森の洞窟',         '숲의 동굴'),
    (0x7400, 104, 'デザイア村',       '데자이어 마을'),
    (0x8100, 120, 'デザイア鉱山',     '데자이어 광산'),
]


def load():
    d = open(BIN, 'rb').read()
    return [struct.unpack('>H', d[i:i + 2])[0] for i in range(0, len(d), 2)], d


def sprite(words, off, w):
    """원본 스프라이트 → [H][w] 워드 2차원."""
    st = off // 2
    return [[words[st + r * w + c] for c in range(w)] for r in range(H)]


def text_mask(kr, px):
    """한글 문자열 → (mask[h][w] 0/1, 폭). 굴림 임베디드 비트맵."""
    font = ImageFont.truetype(hf.FONT_PATH, px)
    pad = 8
    img = Image.new('L', (px * len(kr) + pad * 2, px + pad * 2), 0)
    ImageDraw.Draw(img).text((pad, pad), kr, fill=255, font=font)
    a = img.load()
    W_, H_ = img.size
    m = [[1 if a[x, y] >= 128 else 0 for x in range(W_)] for y in range(H_)]
    # 잉크 바운딩박스로 크롭
    ys = [y for y in range(H_) if any(m[y])]
    xs = [x for x in range(W_) if any(m[y][x] for y in range(H_))]
    if not ys:
        return [], 0, 0
    m = [[m[y][x] for x in range(xs[0], xs[-1] + 1)] for y in range(ys[0], ys[-1] + 1)]
    return m, len(m[0]), len(m)


def stylize(mask, mw, mh, w):
    """본체 마스크 → 스프라이트 워드 2차원(원본 스타일 적용, 가로 중앙정렬).

    흰 본체 → 오른쪽 1px 회색 → 우/하/우하 1px 검정 외곽선."""
    # 스타일 적용 후 크기 = 본체 + 회색1 + 검정1 (우/하 방향으로만 자람)
    sw, sh = mw + 2, mh + 2
    g = [[TR] * sw for _ in range(sh)]

    def ink(r, c):
        return 0 <= r < mh and 0 <= c < mw and mask[r][c]

    for r in range(sh):
        for c in range(sw):
            if ink(r, c):
                g[r][c] = WH
            elif ink(r, c - 1):                        # 본체 오른쪽 → 회색
                g[r][c] = GY
            elif (ink(r - 1, c) or ink(r, c - 2) or ink(r - 1, c - 1)
                  or ink(r - 1, c - 2)):               # 그 바깥 우/하/우하 → 검정
                g[r][c] = BK

    if sw > w:
        raise SystemExit('폭 초과: 필요 %d > 스프라이트 %d' % (sw, w))
    if sh > H:
        raise SystemExit('높이 초과: 필요 %d > %d' % (sh, H))

    out = [[TR] * w for _ in range(H)]
    x0 = (w - sw) // 2
    y0 = (H - sh) // 2
    for r in range(sh):
        for c in range(sw):
            out[y0 + r][x0 + c] = g[r][c]
    return out


def render_label(kr, w, px):
    m, mw, mh = text_mask(kr, px)
    return stylize(m, mw, mh, w)


def rgb(v):
    if v == TR:
        return (255, 0, 255)                 # 투명 → 마젠타(목업 확인용)
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)


def mockup(px=14, path=None, scale=3):
    """원본 ↔ 한글 비교 목업 PNG."""
    words, _ = load()
    wmax = max(w for _, w, _, _ in LABELS)
    gap, blk = 3, H * 2 + 3
    im = Image.new('RGB', (wmax, (blk + gap) * len(LABELS)), (0, 0, 0))
    for i, (off, w, jp, kr) in enumerate(LABELS):
        top = i * (blk + gap)
        o = sprite(words, off, w)
        n = render_label(kr, w, px)
        for name, g2, y in (('jp', o, top), ('kr', n, top + H + 3)):
            sub = Image.new('RGB', (w, H))
            sub.putdata([rgb(g2[r][c]) for r in range(H) for c in range(w)])
            im.paste(sub, (0, y))
    p = path or os.path.join(_here, '..', 'extract', 'state2', 'worldmn', 'mockup_px%d.png' % px)
    im.resize((im.width * scale, im.height * scale), Image.NEAREST).save(p)
    return p


def patched_bytes(px=14):
    """WORLD_MN.BIN 전체를 한글로 교체한 바이트(크기 동일)."""
    words, raw = load()
    out = bytearray(raw)
    for off, w, jp, kr in LABELS:
        g = render_label(kr, w, px)
        for r in range(H):
            for c in range(w):
                i = off + (r * w + c) * 2
                struct.pack_into('>H', out, i, g[r][c])
    assert len(out) == len(raw)
    return bytes(out)


if __name__ == '__main__':
    px = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    for off, w, jp, kr in LABELS:
        m, mw, mh = text_mask(kr, px)
        print('  0x%04x %3dpx  %-8s → %-9s 필요 %3dx%-2d %s'
              % (off, w, jp, kr, mw + 2, mh + 2, 'OK' if mw + 2 <= w and mh + 2 <= H else '❌초과'))
    print('\n목업:', mockup(px))
