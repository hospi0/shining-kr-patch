#!/usr/bin/env python3
"""
Shining the Holy Ark — 한글 이름입력 (≤0xFF 완성형 최소 해법, 2026-07-15).

## 핵심 아이디어
이름 음절을 **≤0xFF 슬롯**(1바이트)에 굽는다 → 이름 저장·표시가 전부 1바이트 경로.
→ 대사([0b])·메뉴(0x06071726)·전투가 **전부 그냥 작동**(16비트 패치·조합 오토마타·2차 훅 불필요).
→ 이름 필드 12B = **최대 12음절**(16비트였으면 6, 자모였으면 2~3).
트레이드오프: 이름 어휘가 **엄선된 ~43음절**로 제한(임의 아무 음절 불가).

## 왜 이 슬롯들이 안전한가 (build_recompress 로 전 101맵 실측, 2026-07-15)
· 최종(번역 후) 빌드의 어느 맵 레코드에서도 안 쓰임(kept-JP·[XXX] 통과 포함 union).
· 이름입력 그리드 kata/alpha 테이블에도 안 쓰임(히라 모드는 한글 모드로 교체).
· 숫자(0x30~0x39)는 이름·UI 가 쓰므로 제외.
→ 전 맵 폰트에서 이 슬롯에 완성형을 구워도 아무것도 안 깨진다(rule3 의 신중한 예외).
⚠️ 그래도 **PoC 실기로 UI 잔재 확인**할 것(직접그리기 UI 가 쓸 가능성 낮지만 있음).

## 렌더 근거
idx ≤ 0x100 → 커서 += 고정폭 12px(호출자 R6=0x0C) = 완성형에 딱 맞음. 폭 필드 무관.
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(__file__))
import hangul_font as hf

# ── 안전 슬롯 풀 (2026-07-16 확장: 카타카나 입력모드 폐지 → 62슬롯, tools/measure_slots.py) ──
#    ⚠️ UI 직접그리기 슬롯 회피: 0x2f('/')=HP구분자, 0x5f('_')=이름커서. 비-ASCII(0x80+)는 UI 무관.
#    ⚠️ 입력 그리드 3종 슬롯(X02, off 0x14638/0x146a4/0x14710):
#       히라(0x86~9f, e0~fd) = **한글 1 페이지로 교체** → 재사용 안전.
#       카타(0xa6~dd)        = **한글 2 페이지로 교체**(2026-07-16, 사용자 결정) → 재사용 안전.
#                              한글 패치에 카타카나 이름 입력은 쓸모가 없고, 기본 파티명도 이미 한글이다.
#       기호/알파(0x21~7a, a1, a4) = 유지 → ASCII·a4 회피.
#    실측(101맵): 레코드가 안 쓰는 여유 비-ASCII 51개 = GRID_SAFE 24 + 카타대역 26 + 0xa4(알파그리드, 제외).
# ① 레코드·전그리드 안전 — 파티·NPC 우선 배정 (24)
_GRID_SAFE = [0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c,
              0x8d, 0x8e, 0x90, 0xa0, 0xa2, 0xa3, 0xe8, 0xee, 0xf1, 0xf5, 0xfe, 0xff]
# ② 카타 그리드 대역(0xa6~dc) 중 레코드가 안 쓰는 전부 — 카타 입력 폐지로 통째 확보 (26)
_KATA = [0xa6, 0xa7, 0xa9, 0xaa, 0xac, 0xae, 0xb3, 0xb7, 0xb9, 0xba, 0xbc, 0xc0, 0xc1,
         0xc5, 0xc6, 0xc7, 0xc9, 0xcd, 0xce, 0xcf, 0xd0, 0xd3, 0xd5, 0xd6, 0xd7, 0xdc]
# ③ 저위험 저-ASCII(기호그리드 0x21~7a 의 빈칸 = 게임 미사용, 기존 실기 검증본) (12)
_LOWASCII = [0x22, 0x40, 0x5b, 0x5c, 0x5d, 0x5e, 0x60, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f]
# 배정 순서: 파티·NPC(대사·메뉴·전투에 항상 보임)를 GRID_SAFE 우선 → 나머지는 카타 → 저-ASCII.
_POOL = _GRID_SAFE + _KATA + _LOWASCII                                           # 24+26+12 = 62

# ── 파티 8명 + 대사전용 NPC 6명(카타카나) 이름 음절 — 전(全)그리드 안전 슬롯 우선 ──
PARTY_NAMES = ['아서', '멜로디', '로디', '밧소', '아카네', '포르테', '도일', '리사']
#    NPC 7명(성주님 포함): [0b] 대사에만. **struct 아닌 레코드(688~694) 경유** → 레코드를 ≤0xFF 한글로.
#    성주님(お屋形様)도 레코드 방식이면 한글 가능(한자여도 레코드 토큰을 한글슬롯으로 교체).
NPC_NAMES = ['사바트', '휴돌', '가름', '리릭스', '엘리제', '팬서', '성주님']
PARTY_SYLL = list(dict.fromkeys(''.join(PARTY_NAMES)))          # 16 유니크
NPC_SYLL = [c for c in dict.fromkeys(''.join(NPC_NAMES)) if c not in PARTY_SYLL]  # +11

# ── 입력 그리드 = 14 초성 × 3 모음(ㅏㅣㅡ) = 42 음절, 초성 기준 2페이지(7/7) ──
#    (카타 그리드를 한글 2로 돌려 풀이 44→62 가 되며 21→42 로 확장. 2026-07-16 사용자 결정.)
#    ⚠️ union 62 / 풀 62 = **여유 0**. 슬롯은 전부 검증된 안전 풀(GRID_SAFE+카타+LOWASCII)이라 안전하지만,
#       **음절을 하나라도 더 늘리려면 슬롯을 먼저 확보해야 한다**(NPC 추가 등).
#    ⚠️ 남는 후보 11개(24 25 28 29 2a 2c 2d 2e 3a 3d 3e)는 **쓰지 말 것** — ASCII 기호는 레코드 스캔에
#       안 잡히는 **UI 직접그리기**에 쓰인다(실기: 0x2f '/'=HP구분자, 0x5f '_'=이름커서가 깨졌음). 0x3a(':')는 특히 UI 기호.
_CHO1 = [0, 2, 3, 5, 6, 7, 9]                 # 한글 1: ㄱㄴㄷㄹㅁㅂㅅ (7)
_CHO2 = [11, 12, 14, 15, 16, 17, 18]          # 한글 2: ㅇㅈㅊㅋㅌㅍㅎ (7)
_CHO = _CHO1 + _CHO2                          # 14
_JUNG = [0, 20, 18]                           # ㅏ ㅣ ㅡ


def _syl(ci, ji):
    return chr(0xAC00 + (ci * 21 + ji) * 28)


GRID_SYLL = [_syl(c, j) for c in _CHO for j in _JUNG]           # 39

# 전체 유니크 = 파티 + NPC + 그리드-only. 대사에 항상 보이는 파티·NPC 를 전(全)그리드 안전슬롯 우선.
_grid_only = [g for g in GRID_SYLL if g not in PARTY_SYLL and g not in NPC_SYLL]
SYLL = PARTY_SYLL + NPC_SYLL + _grid_only                      # 16 + 11 + 29 = 56
assert len(SYLL) == len(set(SYLL)) and len(SYLL) <= len(_POOL), (len(SYLL), len(_POOL))
SYL2SLOT = dict(zip(SYLL, _POOL))
SLOTS = [SYL2SLOT[ch] for ch in SYLL]

# ── 그리드 배치 (15열×7행) — **커서가 닿는 72칸을 빈칸 없이 꽉 채운다** ──
#    🔑 커서 이동(0x06073240~ 열 / 0x060732D4~ 행)은 **범용 빈칸 스킵이 아니라 원본 배치에 하드코딩**
#       (열 0~9, row0만 0~11, 행 0~6, `열>9면 행+=2` 같은 원본 전용 예외). 따라서 도달 가능 칸 =
#       **row0의 0~11열(12) + row1~6의 0~9열(60) = 72칸**(원본의 채움 범위와 동일).
#    🔑 원본도 row2/row4 의 col6·8 이 빈칸이고 커서가 거기 착지 → 그 자리서 A = **공백 입력**(버그 아님).
#       우리는 72칸을 전부 채워 **빈칸 착지 자체를 없앤다**(= 코드 패치 불요, 공백 입력은 포기).
#    🔑 음절 62 + 숫자 10 = **정확히 72** → 한 페이지에 딱 맞음. 두 페이지를 채우려면 124음절이 필요해
#       (슬롯 상한 62) 불가능 → **단일 페이지**, 카타 자리엔 같은 표를 복제하고 메뉴는 둘 다 '한글 입력'.
#    ⚠️ cols 12+ 는 우측 메뉴 침범(추가49 실기). row0 의 10·11 열은 원본이 ゛゜로 쓰던 자리라 안전.
GAP = ''
_DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'] + [GAP] * 5

# ⚠️ row0 의 10·11열은 **원본 3개 그리드 전부 ゛゜(0x3b/0x3c)** 자리다. 여기에 한글을 넣으면
#    영자 모드로 전환할 때 ゛゜(작은 마크)가 한글 픽셀을 못 덮어 **잔상**이 남는다(실기 확인 2026-07-16:
#    영자 화면 우상단에 '서'/'멜' 잔상, 커서는 가지만 ゛는 결합대상이 없어 입력도 안 됨).
#    → 원본과 동일하게 ゛゜ 를 유지해 세 그리드의 그 자리를 일치시킨다(잔상 0).
_DAKUTEN = [0x3b, 0x3c]

# 반절표 = 초성 가로 × 모음 세로(고전 반절표 꼴). 파티·NPC 음절이 남는 칸을 메운다.
_EXTRA_ALL = [c for c in PARTY_SYLL + NPC_SYLL if c not in GRID_SYLL]      # 20
_EXTRA = _EXTRA_ALL[:18]          # 그리드에 놓을 18개(60칸 = 반절표42 + 18)
_EXTRA_OFF = _EXTRA_ALL[18:]      # 못 놓은 2개 — 글리프는 있으니 NPC 이름 표시엔 지장 없음


def _build_grid():
    """커서 도달 칸을 빈칸 없이 채운다.
    row0 = 음절10 + ゛゜ / row1~5 = 음절10 씩 / row6 = 숫자10. 음절 60 + ゛゜2 + 숫자10 = 72."""
    ex = list(_EXTRA)
    rows = []
    # rows0~2 cols0~9 : 초성 10개(ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊ) × 모음 3
    top, rest = _CHO[:10], _CHO[10:]
    for j in _JUNG:
        rows.append([_syl(c, j) for c in top])
    rows[0] += list(_DAKUTEN)                            # row0 의 10·11열 = 원본 그대로 ゛゜
    # rows3~5 cols0~3 : 남은 초성 4개(ㅋㅌㅍㅎ) × 모음 3, cols4~9 는 파티·NPC 음절
    for j in _JUNG:
        rows.append([_syl(c, j) for c in rest] + [ex.pop(0) for _ in range(6)])
    assert not ex, '남은 음절 %s' % ex
    rows.append(list(_DIGITS[:10]))
    return [r + [GAP] * (15 - len(r)) for r in rows]


GRID1 = _build_grid()
GRID2 = GRID1                  # 카타 자리 = 같은 표(메뉴 둘 다 '한글 입력')
GRID = GRID1                   # 하위호환(기존 목업 코드)
assert all(len(r) == 15 for r in GRID1)
# 커서 도달 칸(row0:0~11, row1~6:0~9)에 빈칸이 없어야 한다
for _r, _row in enumerate(GRID1):
    _reach = 12 if _r == 0 else 10
    assert all(_row[_c] != GAP for _c in range(_reach)), 'row%d 에 빈칸 착지 가능' % _r

NUM_SLOT = {str(d): 0x30 + (d if d else 0) for d in range(10)}   # '1'->0x31 .. '0'->0x30
NUM_SLOT['0'] = 0x30


def glyph_for_syllable(ch):
    """음절 → 32B 게임 글리프(폭 12 고정)."""
    _, w, rows = hf.glyph_for(ch, px=12)
    return hf.encode_glyph(12, rows)


def glyphs():
    """{slot: 32B glyph} — 그리드 + 파티 음절 전체(≤0xFF)."""
    return {SYL2SLOT[ch]: glyph_for_syllable(ch) for ch in SYLL}


def party_name_bytes(kr):
    """파티 이름(예 '멜로디') → struct 12바이트(≤0xFF 슬롯 인덱스 + 0 패딩)."""
    return bytes([SYL2SLOT[ch] for ch in kr]) + b'\x00' * (12 - len(kr))


HERO_NAME = '아서'          # 신규게임 기본 히어로명(원본 アーサー)


def hero_name_bytes(kr=HERO_NAME):
    """기본 히어로명 → X02 0xd400 엔트리 8바이트.
    🔑 init(0x06072708)은 **5바이트만** 복사한다: `MOV.L @R1+,R2` (앞 4B → struct+0)
       + `MOV.B @R1,R1` (5번째 B → struct+4). → 이름 ≤4자 + 종료자 1B 구조.
    """
    assert len(kr) <= 4, '기본 히어로명은 4자 이하(init 이 4B+종료자 1B 만 복사)'
    return (bytes([SYL2SLOT[ch] for ch in kr]) + b'\x00' * 8)[:8]


def grid_table(page=1):
    """108B 한글 그리드 테이블. page1 → 히라 자리(0x14638), page2 → 카타 자리(0x146a4).
    셀 = 슬롯 인덱스, 빈칸 = 0x20, 종료 3B = 0x00."""
    out = bytearray()
    for row in (GRID1 if page == 1 else GRID2):
        assert len(row) == 15
        for ch in row:
            if isinstance(ch, int):          # 원본 슬롯 그대로(゛゜ 등)
                out.append(ch)
            elif ch == GAP:
                out.append(0x20)
            elif ch.isdigit():
                out.append(NUM_SLOT[ch])
            else:
                out.append(SYL2SLOT[ch])
    out += b'\x00\x00\x00'
    return bytes(out)


# ─────────────────────── 목업 ───────────────────────
def _bitmap(entry):
    return [[1 if struct.unpack('>H', entry[2 + r * 2:4 + r * 2])[0] & (0x8000 >> c) else 0
             for c in range(16)] for r in range(15)]


def mockup(path):
    from PIL import Image
    G = glyphs()
    numg = {str(d): hf.glyph_for(str(d), px=12)[0] for d in range(10)}
    cell = 18
    W, H = 15 * cell + 40, 9 * cell
    img = Image.new('L', (W, H), 30)
    px = img.load()

    def blit(entry, cx, cy):
        for r, row in enumerate(_bitmap(entry)):
            for c, p in enumerate(row):
                if p and 0 <= cx + c < W and 0 <= cy + r < H:
                    px[cx + c, cy + r] = 255

    # 상단 이름박스: 예시 "가지"(반절표 음절)
    ox = cell
    for ch in '가지':
        blit(glyph_for_syllable(ch), ox, cell // 2)
        ox += 13
    for c in range(12):
        px[ox + c, cell // 2 + 14] = 180

    gy0 = cell * 3
    for r, row in enumerate(GRID):
        for c, ch in enumerate(row):
            if ch == GAP:
                continue
            entry = numg[ch] if ch.isdigit() else glyph_for_syllable(ch)
            blit(entry, c * cell, gy0 + r * cell)

    img = img.resize((W * 5, H * 5), Image.NEAREST)
    img.save(path)
    print('한글 이름입력 목업 →', path)
    print('음절 %d개, 슬롯 %d개, 이름박스 예시=김민준' % (len(SYLL), len(SLOTS)))


if __name__ == '__main__':
    out = os.path.join(os.path.dirname(__file__), '..', 'extract', 'state2', 'name_kr_mockup.png')
    mockup(out)
