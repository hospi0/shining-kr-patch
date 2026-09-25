#!/usr/bin/env python3
"""
Shining the Holy Ark — 한글 조합형(자모) 글리프 생성기 (2026-07-13).

## 왜 조합형인가 (예산)
MDX 섹션0(로드영역)은 이미 100% 차 있고, 블록0~5(아이템·마법·전투)가 쓰는 JP 한자 ~712종
(22.8KB)이 글리프표를 점유한다. 완성형 한글은 지역당 463~500음절 = 15KB가 필요해 자리가 없다.
자모로 쪼개면 글리프가 **184개 고정(5.9KB)** → 번역량과 무관해져 전 지역이 들어간다.

## 렌더러 근거 (X02 디스어셈블, 2026-07-13 확인)
· 글리프 idx > 0x100 → 커서 += word0(부호있는 폭) + 1        [0x0606D4A2]
  → word0 = -1 → 전진 0 = **같은 칸에 겹쳐 그림**, word0 = 11 → 전진 12.
· 1bpp→8bpp 전개(0x0606D684)는 **투명 블릿**(0비트는 목적지 미변경) → 겹치면 OR 합성.
· 폭 보정 모드 플래그(0x060792CD)는 렌더 시작 시 0으로 초기화됨 → 폭 그대로 사용.
⚠️ 드로우 앞 셀 클리어(0x0606C2F4)는 R7(메시지렌더 4번째 인자)≠0일 때만 호출.
   켜져 있으면 2번째 자모가 1번째를 지운다 → X02 `BT/S`(0x8D06)→`BRA`(0xA006) 2B 패치로 회피.
   (build_jamo_state.py가 패치 有/無 두 스테이트를 만들어 실기로 판별)

## 음절 = 항상 3토큰
[초성(w=-1)] [중성(w=-1)] [종성(w=11)]  → 총 12px 전진. 종성 없으면 '빈 종성'(빈 비트맵, w=11).

## 자모 비트맵 = 직접 설계
굴림 12px 완성형은 음절마다 손으로 다듬어져 있어 조합형 구조가 아니다(초성 잔차 17~20종 실측).
→ 역추출 불가. 대신 **호환 자모(ㄱ ㅏ ㄳ…)를 벌별 위치 상자에 스케일 렌더**하는 고전 조합형 방식.
벌 = (모음군 VERT/HORZ/MIX) × (종성 유무).
"""
import sys, struct, os
from PIL import Image, ImageFont, ImageDraw

GULIM = r"C:\Windows\Fonts\gulim.ttc"
SRC_FONT = r"C:\Windows\Fonts\malgun.ttf"      # 자모 원본(벡터, 대형 렌더 후 축소)
ROWS, CELLW, PX = 15, 16, 12
BIG = 96                                        # 자모를 크게 렌더 후 상자에 맞춰 축소

CHO = list('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ')             # 19
JUNG = list('ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ')        # 21
JONG = [''] + list('ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')  # 28

VERT, HORZ, MIX = 0, 1, 2
VCLASS = {i: (VERT if v in 'ㅏㅐㅑㅒㅓㅔㅕㅖㅣ' else
              HORZ if v in 'ㅗㅛㅜㅠㅡ' else MIX) for i, v in enumerate(JUNG)}

WIDTH_ADV = 11      # 종성 글리프 → 커서 += 12
WIDTH_OVL = -1      # 초성/중성 → 커서 += 0 (겹침)

# 벌별 배치 상자 (x0, y0, x1, y1) — 12x15 셀 기준 (x는 0~11, y는 0~14)
BOX = {
    # 종성 없음
    ('cho', VERT, 0): (0, 1, 8, 14),   ('jung', VERT, 0): (7, 0, 12, 15),
    ('cho', HORZ, 0): (1, 0, 11, 9),   ('jung', HORZ, 0): (0, 8, 12, 15),
    ('cho', MIX, 0): (0, 0, 8, 9),    ('jung', MIX, 0): (0, 0, 12, 15),
    # 종성 있음 (초성·중성을 위로 압축)
    ('cho', VERT, 1): (0, 0, 8, 11),   ('jung', VERT, 1): (7, 0, 12, 11),
    ('cho', HORZ, 1): (1, 0, 11, 7),   ('jung', HORZ, 1): (0, 6, 12, 11),
    ('cho', MIX, 1): (0, 0, 8, 7),    ('jung', MIX, 1): (0, 0, 12, 11),
    ('jong', VERT, 1): (0, 10, 12, 15),
    ('jong', HORZ, 1): (0, 10, 12, 15),
    ('jong', MIX, 1): (0, 10, 12, 15),
}

_srcfont = None
_gulim = None


def _render_big(ch):
    """호환 자모를 크게 렌더 → (ink bbox로 크롭된 L 이미지)."""
    global _srcfont
    if _srcfont is None:
        _srcfont = ImageFont.truetype(SRC_FONT, BIG)
    img = Image.new('L', (BIG * 2, BIG * 2), 0)
    ImageDraw.Draw(img).text((BIG // 2, BIG // 4), ch, fill=255, font=_srcfont)
    bb = img.getbbox()
    return img.crop(bb) if bb else img


_bigcache = {}


def jamo_cell(ch, box, thr=90, fit='stretch'):
    """자모 문자를 상자(box) 안에 **종횡비 유지**로 축소·중앙배치 → 15×16 셀 0/1 비트맵.

    ⚠️ bbox를 상자에 가로세로 따로 늘리면 ㅡ/ㅗ/ㅜ 같은 가로획이 두꺼운 덩어리가 된다.
       획 굵기를 지키려면 반드시 등비 축소해야 함."""
    if ch not in _bigcache:
        _bigcache[ch] = _render_big(ch)
    src = _bigcache[ch]
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    sw, sh = src.size
    if fit == 'aspect':          # 얇은 획(ㅡ ㅗ ㅜ)이 덩어리가 되지 않도록 등비 축소
        s = min(bw / sw, bh / sh)
        w, h = max(1, round(sw * s)), max(1, round(sh * s))
    else:                        # 자음은 2D 형태 → 상자에 맞춰 늘림(고전 조합형과 동일)
        w, h = bw, bh
    im = src.resize((w, h), Image.LANCZOS)
    ox, oy = x0 + (bw - w) // 2, y0 + (bh - h) // 2
    cell = [[0] * CELLW for _ in range(ROWS)]
    for r in range(h):
        for c in range(w):
            if 0 <= oy + r < ROWS and 0 <= ox + c < CELLW and im.getpixel((c, r)) >= thr:
                cell[oy + r][ox + c] = 1
    return cell


class JamoSet:
    def __init__(self):
        self.g = {}          # ('cho', c, k, j) / ('jung', m, j) / ('jong', t, k) -> bitmap
        for c in range(19):
            for k in (VERT, HORZ, MIX):
                for j in (0, 1):
                    self.g[('cho', c, k, j)] = jamo_cell(CHO[c], BOX[('cho', k, j)])
        for m in range(21):
            for j in (0, 1):
                k = VCLASS[m]
                self.g[('jung', m, j)] = jamo_cell(JUNG[m], BOX[('jung', k, j)], fit='aspect')
        for t in range(1, 28):
            self.g[('jong', t)] = jamo_cell(JONG[t], BOX[('jong', VERT, 1)])
        self.g[('jong', 0)] = [[0] * CELLW for _ in range(ROWS)]     # 빈 종성(전진 담당)

    def keys_of(self, ch):
        """음절 → 자모 키. **종성 없으면 2토큰**(중성 j0 글리프가 폭 11로 전진 담당) → 대사 압축 절감."""
        code = ord(ch) - 0xAC00
        c, m, t = code // 588, (code % 588) // 28, code % 28
        j = 1 if t else 0
        ks = [('cho', c, VCLASS[m], j), ('jung', m, j)]
        if t:
            ks.append(('jong', t))
        return ks

    def all_keys(self):
        return sorted(self.g, key=lambda k: (k[0], k[1:]))

    def width_of(self, key):
        """전진을 담당하는 마지막 자모만 폭 11(=12px). 앞 자모는 -1(=전진 0, 겹침).
        종성 없는 음절은 중성(j=0)이 마지막이므로 그 슬롯이 폭 11."""
        if key[0] == 'jong':
            return WIDTH_ADV
        if key[0] == 'jung' and key[2] == 0:
            return WIDTH_ADV
        return WIDTH_OVL

    def compose(self, ch):
        out = [[0] * CELLW for _ in range(ROWS)]
        for k in self.keys_of(ch):
            b = self.g[k]
            for r in range(ROWS):
                for c in range(CELLW):
                    out[r][c] |= b[r][c]
        return out


def encode_glyph(width, rows):
    out = struct.pack('>h', width)
    for r in range(ROWS):
        w = 0
        for b in range(CELLW):
            if rows[r][b]:
                w |= (1 << (15 - b))
        out += struct.pack('>H', w)
    return out


def gulim_bitmap(ch):
    global _gulim
    if _gulim is None:
        _gulim = ImageFont.truetype(GULIM, PX)
    img = Image.new('L', (CELLW + 4, ROWS + 4), 0)
    ImageDraw.Draw(img).text((0, 1), ch, fill=255, font=_gulim)
    return [[1 if img.getpixel((c, r)) >= 96 else 0 for c in range(CELLW)] for r in range(ROWS)]


if __name__ == '__main__':
    js = JamoSet()
    keys = js.all_keys()
    print("자모 글리프 %d개 = %d B" % (len(keys), len(keys) * 32))
    show = sys.argv[1:] or list('그래서우리가왔을때너밖에안보였던거군훌륭한검을쓰는군요')
    cell = 17
    img = Image.new('L', (len(show) * cell, cell * 2 + 3), 0)
    px = img.load()
    for i, ch in enumerate(show):
        for j, bm in enumerate((gulim_bitmap(ch), js.compose(ch))):
            for r in range(ROWS):
                for c in range(CELLW):
                    if bm[r][c]:
                        px[i * cell + c, j * (cell + 3) + r] = 255
    img = img.resize((img.width * 7, img.height * 7), Image.NEAREST)
    out = os.path.join(os.path.dirname(__file__), '..', 'extract', 'state2', 'jamo_compare.png')
    img.save(out)
    print("위=굴림 완성형 / 아래=자모 조합 →", out)
