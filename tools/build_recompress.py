#!/usr/bin/env python3
"""
Shining the Holy Ark — **MDX 섹션0 재압축 통합도구** (2026-07-13).

훅/폰트블록 방식(build_full.py)은 폰트블록 18.9KB 안에 [테이블+토큰배열+완성형 글리프]를 다 넣어야
해서 큰 지역(forest/village/성/마을)이 예산 초과로 못 들어갔다. 이 도구는 **섹션0 전체를 재구성**한다:

  글리프표(하이브리드) + 코드북(재빌드) + 블록0~6 전부 재인코딩 + table1 + table2_flat

훅·X02 리터럴·X07 전부 **불필요**(대사가 원본 자리에 한글로 압축돼 들어감).

## 구조 (실측)
· MDX 파일 헤더(file 0x0) = (파일오프셋, 크기) 섹션 테이블. **섹션0 = (0x800, size)** → LWRAM 0x218000.
  size = header[1]. **공짜 확장 한계 = 다음 섹션 오프셋 − 0x800**(맵당 220B~2KB).
· LWRAM 헤더(0x218000) = [글리프표주소][table1][table2_flat][0x80000].
· 메시지 = [len:1][data:len] 레코드의 플랫 스트림. 블록 사이에 len==0 종료자.
  table2_flat[hi] = 블록 hi가 시작하는 레코드의 주소(블록들은 같은 스트림을 공유·중첩).

## 글리프 인덱스 규칙 (X02 렌더러)
· 토큰 ≤ 0x1F = 컨트롤코드.  · idx ≤ 0x100 → 커서 += 고정폭(호출자).  · idx > 0x100 → 커서 += word0+1.
→ 가나/기호(≤0xFF)는 **원래 인덱스 그대로 유지**(고정폭 렌더). 한자는 0x101~로 압축 재배치.
  한글: 완성형(빈도 상위) + 자모 조합형(나머지) 전부 0x101~.

## 한글 인코딩 (jamo_font)
· 종성 있음: [초성(w=-1)][중성j1(w=-1)][종성(w=11)]  = 3토큰
· 종성 없음: [초성(w=-1)][중성j0(w=11)]              = 2토큰   ← 중성 j0 슬롯의 폭만 다름(글리프 추가 없음)
· 완성형 음절: 1토큰(w=11)
"""
import sys, os, json, struct, re, importlib.util
from collections import Counter

_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


em = _L("extract_mdx"); es = _L("extract_script"); cbm = _L("codebook")
jf = _L("jamo_font"); hf = _L("hangul_font")

MDX_BASE = 0x217800            # MDX file off X ↔ LWRAM 0x217800+X
SEC0_FOFF = 0x800
LW_HDR = 0x218000
GLYPH_LO = 0x20                # 글리프표 첫 슬롯
KANJI_FIRST = 0x101            # ⚠️ 0x100 이하는 고정폭 렌더 → 한자/한글은 0x101부터

# 캐릭터 이름 훅(Option B)용 고정 예약 음절 — 훅 테이블이 이 **고정 인덱스**(0x101~)를 가리킨다.
# RESERVE_NAMES=True 면 매 맵 폰트의 0x101~0x110 에 이 16음절 완성형을 고정 배치하고 동적할당은
# 0x111 부터 시작한다(예산 소폭 증가, 옵티마이저가 자모로 흡수). 파티 8명: 아서/멜로디/로디/밧소/
# 아카네/포르테/도일/리사 의 유니크 음절.
NAME_SYLLABLES = list('아서멜로디밧소카네포르테도일리사')
RESERVE_NAMES = False
# 한글 이름입력(≤0xFF 완성형) — {slot(≤0xFF): 32B 완성형 글리프}.
# 매 맵 폰트의 기존 가나/기호 슬롯을 완성형으로 **덮어쓴다**(같은 슬롯=예산 0). 슬롯은 전 맵
# 레코드·그리드 미사용분으로 골라야 안전(name_kr.SLOTS). 이름=1바이트라 대사/메뉴/전투 전부 작동.
NAME_INPUT_GLYPHS = {}
# NPC 이름 레코드(system.json id 688~694) → ≤0xFF 한글 슬롯 바이트열. build 가 name_kr 로 채운다.
# NPC 이름은 파티(struct)와 달리 **[0b] 가 이 시스템 레코드를 직접 렌더**(실기 확인: サバト/リリクス
# 가 카타카나로 나옴 = party_hook Part B 안 거침). 레코드 토큰을 한글슬롯으로 바꾸면 [0b]가 한글.
NPC_NAME_SLOTS = {}
# 몬스터/아이템·마법명(block6 rec0~54) 번역 — build 가 셋별 names/*.json 을 순번 리스트로 넣는다.
NAMES_KR = []
# 좁은 한글 띄어쓰기(B): 한국어는 단어 사이 공백이 있어 JP보다 줄이 넓다(대사창·초상화 침범).
# 공백을 12px(0x20 고정폭) 대신 폭 NSP_WIDTH 의 >0x100 빈 글리프로 렌더 → 줄 폭 축소.
# ⚠️ 좁은 공백은 실기서 안 먹힘(2026-07-15 추가53): 폰트 width=5·버퍼 토큰=0x101·플래그=0 다 맞는데
#    렌더가 12px로 그림(원인 미규명, 에뮬 디버거 필요). 켜면 rewrap 계산이 6px 가정→실제 12px라
#    덜 쪼갬. **False 로 두면 rewrap 이 12px 로 정확히 계산 + 슬롯/예산 확보.**
NARROW_SPACE = False
NSP_WIDTH = 5
STORY_START_REC = 55           # 블록6 rec0~54 = 몬스터/아이템 이름, rec55+ = 스토리 대사
# 🔑 **버퍼 종료자는 0x0000 하나뿐이다** (렌더러가 0x0000 에서 멈춤 — 추가19).
#    0x04/0x06/0x07/0x08 은 "대기/자동진행/대화끝" **인라인 컨트롤코드**이지 종료자가 아니다.
#    ⚠️ 실기 버그: 0x0007 에서 잘라 0x0000 을 버렸더니 렌더러가 안 멈추고 다음 박스와
#       디코드버퍼 잔재(깨진 한자)까지 계속 그렸다.
WAITS = (0x0004, 0x0006, 0x0007, 0x0008)
TERM = 0x0000
CUT = (TERM,)
_TOK = re.compile(r'\[([0-9a-fA-F]{2,4})\]|\{(br|sp)\}')

# ── 대사창 재줄바꿈(C) ── 좁은 공백(B) 적용 후에도 wrap 폭을 넘는 긴 줄만 단어경계로 쪼갠다.
#    이미 게임이 자동 wrap(단어 중간 끊김) 하던 줄이라 세로 줄 수 변화 없이 깔끔해진다.
# 🔑 2026-07-15: 스토리 완역으로 예산 확보 → rewrap 재활성(초상화 침범 해결, 실기제보).
#    게임은 전체폭(~240px)까지 자동 wrap 하는데 초상화(우측, 좌변 ~204px)를 덮어 침범.
#    **초상화 유무는 메시지에서 감지 불가**(이벤트 스크립트 소관) → 전 대사를 초상화 안전폭으로 wrap.
#    dry-run: WRAP_PX=192(16칸, 공백 12px)로 101맵 스킵0(최소여유 8B). 초상화 좌변 ~204px 앞 12px 여유.
#    (옛 9999=끔은 예산부족 시절. 좁은공백 NARROW_SPACE 는 실기 미작동이라 여전히 False.)
WRAP_PX = 192                  # 대사창 한 줄 최대 폭(초상화 안전). 공백 12px 계산.
#    ⚠️ **스토리 대사에만 적용된다**(tokens(wrap=True)). 시스템/이름 레코드에 줄바꿈을 넣으면
#    메뉴 렌더 경로가 줄바꿈 핸들러(0x0606DD5C)에서 ADDRESS ERROR 로 죽는다 — 2026-07-16 실기
#    (마법/소지품 메뉴 PC=0x0606D27A). 메뉴 레코드는 설계상 한 줄 전용이다.


NAME_EST_PX = 36        # [0b][id] 이름 삽입 렌더폭 추정(평균 3글자). 실제 2~4글자.
NID = ''          # [0b] 직후 줄바꿈(=이름 id, 게임이 소비)을 wrap 중 보호하는 센티넬


def _line_px(seg):
    """한 줄(줄바꿈 없음)의 렌더 픽셀 폭. 음절/구두점/글리프통과=12px, 공백=12px(NARROW_SPACE시 6).
    ⚠️ 컨트롤코드(<0x20: 대기 05/06/07/08 등)는 렌더 안 함=0px. [0b][id] 이름삽입은 이름폭 추정.
    ⚠️ NID 센티넬(=[0b] id로 소비되는 줄바꿈)은 0px."""
    sp = 6 if NARROW_SPACE else 12
    w = 0
    i = 0
    while i < len(seg):
        m = _TOK.match(seg, i)
        if m:
            if m.group(2) == 'sp':
                w += sp
            elif m.group(1) is not None:
                v = int(m.group(1), 16)
                if v == 0x0b:                       # 이름 삽입: [0b][id] 쌍
                    i = m.end()
                    m2 = _TOK.match(seg, i)         # 뒤따르는 id 토큰 흡수
                    if m2 and m2.group(1) is not None:
                        i = m2.end()
                    w += NAME_EST_PX
                    continue
                elif v >= 0x20:                     # 글리프 통과([XXX] 한자 등)
                    w += 12
                # else: <0x20 컨트롤코드 = 0px(렌더 안 함)
            i = m.end(); continue
        if seg[i] == NID:                           # [0b] id로 소비되는 줄바꿈 = 0px
            i += 1; continue
        w += sp if seg[i] in ' 　' else 12
        i += 1
    return w


def _wrap_line(line):
    if _line_px(line) <= WRAP_PX:
        return [line]
    words = line.replace('　', ' ').split(' ')
    segs, cur = [], ''
    for wd in words:
        trial = (cur + ' ' + wd) if cur else wd
        if not cur or _line_px(trial) <= WRAP_PX:
            cur = trial
        else:
            segs.append(cur); cur = wd
    if cur:
        segs.append(cur)
    return segs


_NID_RE = re.compile(r'(\[0*b\])\n')      # [0b] 직후 줄바꿈 = 이름 id(게임이 소비, 진짜 줄바꿈 아님)


def rewrap(kr):
    """긴 줄을 단어경계로 재줄바꿈. 짧은 줄은 그대로. {br}/\\n = 줄바꿈.
    ⚠️ [0b] 직후 줄바꿈은 이름삽입 id 라 게임이 소비(줄 안 바뀜) → NID 센티넬로 보호해
       그 자리서 안 쪼개고, 이름+뒷텍스트를 한 흐름으로 wrap. 끝에 \\n 복원(인코더가 br 방출)."""
    kr = _NID_RE.sub(r'\1' + NID, kr.replace('{br}', '\n'))
    out = []
    for line in kr.split('\n'):
        out += _wrap_line(line)
    return '\n'.join(out).replace(NID, '\n')


# ── 대사창 페이지 나누기(D) ──────────────────────────────────────
# 대사창은 **딱 3줄**이다. 원본 JP 는 3줄이 차는 자리마다 `[05]`(대기 후 창 비움)를 넣어
# 두었다 — 실측: 게임 wrap 폭(240px) 기준 JP 페이지의 97%가 3줄 이하.
# 한국어는 같은 내용이 더 길어져 한 페이지가 4~7줄이 되는데, `[05]` 는 JP 자리 그대로라
# **넘치는 줄이 대기 없이 흘러가 읽을 수가 없다**(2026-08-01 실기 제보).
# → rewrap 으로 줄이 확정된 뒤, 페이지가 3줄을 넘으면 그 자리에 `[05]` 를 새로 넣는다.
PAGE_LINES = 3
WAIT_TOK = '[05]'
_WAIT_RE = re.compile(r'\[0*5\]')


def _renders_more(s, j):
    """s[j:] 에 아직 **그려질 것**이 남았는가. 남은 게 줄바꿈·공백·대기코드뿐이면 False
    (그런 자리에 [05] 를 넣으면 빈 페이지가 생겨 버튼을 한 번 더 눌러야 한다)."""
    i = j
    while i < len(s):
        m = _TOK.match(s, i)
        if m:
            if m.group(2) == 'sp':
                i = m.end(); continue
            v = int(m.group(1), 16)
            if v >= 0x20:                       # 글리프 = 그려진다
                return True
            i = m.end(); continue               # 컨트롤코드는 안 그려진다
        if s[i] in ' 　\n' or s[i] == NID:
            i += 1; continue
        return True
    return False


def _next_is_wait(s, j):
    """s[j:] 에서 줄바꿈·공백만 건너뛰었을 때 곧바로 대기코드가 오는가.
    (원본이 `…\\n[05]` 처럼 줄바꿈 **뒤에** 대기를 둔 자리가 있다 — 거기 또 넣으면
     빈 페이지가 생겨 버튼을 한 번 더 눌러야 한다.)"""
    i = j
    while i < len(s) and (s[i] in ' 　\n' or s[i] == NID):
        i += 1
    return bool(_WAIT_RE.match(s, i))


def paginate(kr):
    """rewrap 된 문자열의 페이지(=`[05]` 사이)를 3줄 이하로 쪼갠다.

    ⚠️ `[0b]` 직후 줄바꿈은 **이름 id** 라 게임이 소비한다(줄이 안 바뀐다) — 줄 수에서 뺀다.
    ⚠️ `[05]` 바로 뒤의 줄바꿈은 새 페이지 첫 줄의 시작이지 줄 구분이 아니다.
    """
    s = _NID_RE.sub(r'\1' + NID, kr)
    out, lines, i, n = [], 0, 0, len(s)
    while i < n:
        m = _WAIT_RE.match(s, i)
        if m:
            out.append(m.group(0)); lines = 0; i = m.end()
            if i < n and s[i] == '\n':          # 새 페이지 첫 줄 시작 — 세지 않는다
                out.append('\n'); i += 1
            continue
        if s[i] == '\n':
            lines += 1
            if (lines >= PAGE_LINES and _renders_more(s, i + 1)
                    and not _next_is_wait(s, i + 1)):
                out.append(WAIT_TOK); lines = 0
            out.append('\n'); i += 1
            continue
        out.append(s[i]); i += 1
    return ''.join(out).replace(NID, '\n')


# ─────────────────────────── MDX 파싱 ───────────────────────────

def sections(d):
    """파일 헤더의 (오프셋, 크기) 섹션 목록."""
    out = []
    for i in range(0, 0x60, 8):
        off, size = struct.unpack('>II', d[i:i + 8])
        if off == 0 and size == 0:
            break
        out.append((off, size))
    return out


def sec0_capacity(d):
    """섹션0을 파일 시프트 없이 키울 수 있는 최대 크기 = 다음 섹션 오프셋 − 0x800."""
    secs = sections(d)
    return (secs[1][0] if len(secs) > 1 else len(d)) - SEC0_FOFF


class Mdx:
    def __init__(self, name):
        self.name = name
        self.data = em.read_mdx(name)
        self.hdr = struct.unpack('>4I', self.data[SEC0_FOFF:SEC0_FOFF + 16])
        self.glyph_addr, self.t1_addr, self.t2_addr, self.hdr3 = self.hdr
        self.s = es.Script(self.data, os.path.join(_here, '..', 'docs', 'glyph_table_forest.txt'),
                           base=MDX_BASE)
        self.cur_size = sections(self.data)[0][1]
        # ⚠️ 예산 = **원본 섹션0 크기**. 파일 패딩까지 쓸 수 있는 cap(다음 섹션 오프셋)이 아니다 —
        #    섹션0 크기를 바꾸면 뒤 섹션들이 LWRAM에서 밀려 0x0022C000 포인터가 깨진다(실기 확인).
        #    남는 공간은 0 패딩하고 헤더는 그대로 둔다.
        self.cap = self.cur_size
        self.file_cap = sec0_capacity(self.data)

    def rd(self, a, n):
        o = a - MDX_BASE
        return self.data[o:o + n]

    def decode_full(self, data, end):
        """레코드 디코드. **종료자는 0x0000 하나뿐**(전 레코드 실측: 1604/1604, 1760/1760).

        ⚠️ 0x04/0x06/0x07/0x08 은 **인라인 컨트롤코드**다(대기/자동진행 등). 레코드 **선두**에도 온다
           (M511 21개, M801 12개). 여기서 끊으면 그 레코드가 통째로 비어버린다 —
           실기 확인: 이름입력 메뉴 "名前おわり"(0009 0006 名前おわり 0012 0000)가 통째로 사라졌다."""
        d = self.s.d
        sb = d.bits(data, 0x80)
        idx = 0
        toks = []
        while sb.ptr < end and len(toks) < 400:
            hi = d.decode_byte(idx, sb); idx = hi
            lo = d.decode_byte(idx, sb); idx = lo
            t = (hi << 8) | lo
            toks.append(t)
            if t == TERM:
                break
        if not toks or toks[-1] != TERM:
            toks.append(TERM)
        return toks

    # 옛 추출기가 어디서 끊었는지가 코퍼스마다 다르다:
    #  · 스토리 kr: extract_script.decode_record 기준 → **0x07/0x08 에서만** 끊었다.
    #  · 시스템 jp: extract_system(구 CUT) 기준 → **0x04/06/07/08 전부**에서 끊었다.
    STORY_CUTS = (0x0007, 0x0008)

    @staticmethod
    def was_truncated(toks, cuts=STORY_CUTS):
        """그 추출기가 이 레코드를 잘라먹었는가? = 끊는 코드 뒤에 글리프가 더 있는가.
        잘렸다면 그 번역은 불완전하므로 적용하면 안 된다(원본 JP 유지)."""
        w = next((i for i, t in enumerate(toks) if t in cuts or t == TERM), None)
        if w is None:
            return False
        return any(t >= 0x20 for t in toks[w + 1:])

    def block_bases(self):
        return [self.s.block_base(h) for h in range(7)]

    def scan_records(self):
        """메시지 영역 전체를 순차 스캔 → [('rec', addr, toks) | ('term', addr)]

        ⚠️ 레코드 끝의 **패딩 비트도 토큰으로 디코드된다**(맵마다 다른 쓰레기 토큰이 나옴).
           게임은 종료토큰(0x08/0x07/0x06/0x04)에서 멈추므로 거기서 잘라야 한다.
           안 자르면 (1) 맵 간 동일 문장이 다른 토큰열로 보이고 (2) 재인코딩 시 쓰레기까지 압축된다."""
        bases = self.block_bases()
        start = min(b for b in bases if MDX_BASE <= b < MDX_BASE + len(self.data))
        stop = self.t1_addr
        items = []
        p = start
        self.no_term = 0
        while p < stop:
            ln = self.rd(p, 1)[0]
            if ln == 0:
                items.append(('term', p)); p += 1; continue
            toks = self.decode_full(p + 1, p + 1 + ln)
            items.append(('rec', p, toks))
            p += 1 + ln
        return items, start


# ─────────────────────────── 한글 인코딩 ───────────────────────────

class HangulEnc:
    """하이브리드: 완성형(빈도 상위) + 자모 조합형."""

    def __init__(self):
        self.js = jf.JamoSet()
        self.jamo_keys = self.js.all_keys()     # 기본값(전체) — set_used_jamo 로 실사용분만 남긴다
        self.jamo_idx = {}
        self.full_idx = {}       # 음절 -> idx (완성형)
        self.extra_idx = {}      # 비한글 문자(。？… 등) -> idx (완성형)
        self.kanji_map = {}      # 원본 한자 idx -> 재배치된 idx ([XXX] 통과용)

    def alloc(self, first, full_hi, full_low):
        """자모(0x101~) + 완성형. full_low = 0x20~0x100 빈 슬롯에 이미 배정된 완성형(공짜),
        full_hi = 거기 못 들어가 고슬롯을 새로 먹는 완성형. 다음 빈 idx 반환."""
        i = first
        # 이름 훅용 고정 예약(0x101~) — 동적 할당을 그 뒤로 밀어낸다.
        self.full_idx = {}
        for ch, idx in getattr(self, 'name_reserve', {}).items():
            self.full_idx[ch] = idx
            if idx >= i:
                i = idx + 1
        self.nsp_idx = None
        if NARROW_SPACE:
            self.nsp_idx = i; i += 1          # 좁은 공백 예약(>0x100, 폭 기반 전진)
        self.jamo_idx = {}
        for k in self.jamo_keys:
            self.jamo_idx[k] = i; i += 1
        for ch, idx in full_low.items():
            self.full_idx.setdefault(ch, idx)
        for ch in full_hi:
            if ch not in self.full_idx:
                self.full_idx[ch] = i; i += 1
        self.extra_idx = dict(self.extras_low)
        for ch in self.extras:
            if ch not in self.extra_idx and ch not in self.full_idx:
                self.extra_idx[ch] = i; i += 1
        return i

    def set_used_jamo(self, texts, full_set):
        """자모 조합으로 렌더될 음절(=완성형 슬롯을 못 받은 것)이 실제로 쓰는 자모만 남긴다.
        184개를 통째로 싣던 것 대비 슬롯이 크게 줄어든다(안 쓰는 겹받침 등)."""
        used = set()
        for t in texts:
            for ch in _TOK.sub('', t):
                if '가' <= ch <= '힣' and ch not in full_set:
                    used.update(self.js.keys_of(ch))
        self.jamo_keys = [k for k in self.js.all_keys() if k in used]
        return self.jamo_keys

    def scan_extras(self, texts):
        """번역문에 나오는 비한글·비제어 문자(구두점 등) 수집."""
        ex = []
        for t in texts:
            for ch in _TOK.sub('', t):
                if ch in ' \n　' or ('가' <= ch <= '힣'):
                    continue
                if ch not in ex:
                    ex.append(ch)
        self.extras = ex
        return ex

    def tokens(self, kr, wrap=False, allow_br=True):
        # ⚠️ wrap 은 **스토리 대사 전용**. 메뉴/설명바 레코드에 줄바꿈을 넣으면 실기 크래시한다.
        #    (원본 JP 도 메뉴 프롬프트 0/36·아이템 설명바 0/210 으로 줄바꿈을 절대 안 쓴다.)
        # ⚠️ allow_br=False 면 **번역문이 손으로 써 넣은 줄바꿈도** 공백으로 바꾼다 —
        #    rewrap 을 껐다고 안전한 게 아니다(0x03 이 나가면 경로가 같다). 2026-08-07 크래시 확정.
        if wrap:
            kr = rewrap(kr)             # C: 긴 줄 단어경계 재줄바꿈
            kr = paginate(kr)           # D: 3줄 넘는 페이지에 [05](대기) 재배정
        if not allow_br:
            kr = kr.replace('{br}', ' ').replace('\n', ' ')
        toks = []
        i = 0
        while i < len(kr):
            m = _TOK.match(kr, i)
            if m:
                if m.group(1) is not None:
                    v = int(m.group(1), 16)
                    toks.append(self.kanji_map.get(v, v) if v > 0xFF else v)
                elif m.group(2) == 'br':
                    toks.append(0x03)
                else:
                    toks.append(self.nsp_idx or 0x20)
                i = m.end(); continue
            ch = kr[i]; i += 1
            if ch == '\n':
                toks.append(0x03)
            elif ch in ' 　':
                toks.append(self.nsp_idx or 0x20)
            elif '가' <= ch <= '힣':
                if ch in self.full_idx:
                    toks.append(self.full_idx[ch])
                else:
                    toks += [self.jamo_idx[k] for k in self.js.keys_of(ch)]
            else:
                toks.append(self.extra_idx[ch])
        return toks                     # 종료/대기 코드는 호출부가 원본 꼬리로 붙인다

    def glyphs(self):
        """[(idx, 32B)] — 자모 + 완성형 + 기타 + 좁은 공백."""
        out = []
        if getattr(self, 'nsp_idx', None):
            out.append((self.nsp_idx, jf.encode_glyph(NSP_WIDTH, [[0] * 16 for _ in range(15)])))
        for k in self.jamo_keys:
            out.append((self.jamo_idx[k], jf.encode_glyph(self.js.width_of(k), self.js.g[k])))
        for ch, i in list(self.full_idx.items()) + list(self.extra_idx.items()):
            g, w, rows = hf.glyph_for(ch)
            out.append((i, jf.encode_glyph(jf.WIDTH_ADV, rows)))   # 폭 11 → 12px 전진
        return out


# ─────────────────────────── 재패킹 ───────────────────────────

# ⚠️ **캐릭터 이름은 JP 유지.** 이름은 8비트 버퍼(1바이트/글자)에 저장되므로 한글 글리프
#    인덱스(0x101 이상)를 넣으면 **하위 바이트만 남아** 엉뚱한 가나가 찍힌다(실기 확인:
#    파티 메뉴 이름칸이 ケ/り 등으로 깨짐). 한글 이름을 넣으려면 이름 저장 코드를 패치해야 한다.
NAME_KEEP_JP = set(range(680, 695))   # アーサー … パンサー (system.json id)


def load_system_kr():
    """translation/system.json → 시스템 레코드(블록0~5) 순번별 번역문."""
    p = os.path.join(_here, '..', 'translation', 'system.json')
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding='utf-8'))
    n = max(r['id'] for r in d) + 1
    out = [''] * n
    done = [False] * n                    # 온전한 jp 기준으로 재번역된 레코드
    for r in d:
        if r['id'] in NAME_KEEP_JP:
            continue                      # 캐릭터 이름 → JP 유지
        out[r['id']] = r.get('kr', '')
        done[r['id']] = bool(r.get('retranslated'))
    return out, done


_SYS_KR = None


def repack(mdx, kr_list, n_full, verbose=True, extra_full=()):
    """kr_list: 스토리 박스 **순번**(rec55+ 기준) 별 번역문. 주소가 아니라 순번으로 맞춘다 —
    같은 지역의 다른 맵은 대사 내용은 같아도 주소가 다를 수 있기 때문.
    n_full = 완성형으로 둘 음절 수(빈도 상위).
    extra_full = 추가로 완성형에 넣을 음절(긴 레코드 255B 초과 해소용 타겟 승격).
    반환 (bytes|None, stats). stats['ok']가 False면 bytes는 None."""
    items, start = mdx.scan_records()
    recs = [it for it in items if it[0] == 'rec']
    b6 = mdx.s.block_base(6)
    story_i = [i for i, it in enumerate(items)
               if it[0] == 'rec' and it[1] >= b6]
    story_recs = story_i[STORY_START_REC:]      # 스토리 대사 레코드 인덱스
    name_recs = story_i[:STORY_START_REC]       # block6 rec0~54 = 몬스터/아이템·마법명
    name_texts = [(NAMES_KR[k] if k < len(NAMES_KR) else '') for k in range(len(name_recs))]
    name_map = {name_recs[k]: name_texts[k] for k in range(len(name_recs))}
    # 시스템 레코드(블록0~5) = 블록6 앞의 모든 레코드. 전 맵 공통이라 번역 1벌로 커버된다.
    sys_recs = [i for i, it in enumerate(items) if it[0] == 'rec' and it[1] < b6]

    global _SYS_KR
    if _SYS_KR is None:
        _SYS_KR = load_system_kr()
    _kr, _done = _SYS_KR
    sys_texts = [(_kr[j] if j < len(_kr) else '') for j in range(len(sys_recs))]
    sys_done = {ri: (_done[k] if k < len(_done) else False) for k, ri in enumerate(sys_recs)}

    # 1) 한글 문자 빈도 → 완성형 후보 (시스템 + 스토리 전체 기준)
    _kl, _kd = kr_list if isinstance(kr_list, tuple) else (kr_list, [False] * len(kr_list))
    kr_texts = [(_kl[j] if j < len(_kl) else '') for j in range(len(story_recs))]
    story_done = {ri: (_kd[j] if j < len(_kd) else False) for j, ri in enumerate(story_recs)}
    all_texts = kr_texts + sys_texts + name_texts
    cnt = Counter()
    for t in all_texts:
        for ch in _TOK.sub('', t):
            if '가' <= ch <= '힣':
                cnt[ch] += 1
    enc = HangulEnc()
    enc.scan_extras(all_texts)
    full = [ch for ch, _ in cnt.most_common(n_full)]
    for ch in extra_full:                      # 타겟 승격(긴 레코드 해소)
        if ch not in full:
            full.append(ch)
    name_set = set(NAME_SYLLABLES) if RESERVE_NAMES else set()
    enc.set_used_jamo(all_texts, set(full) | name_set)   # 예약 음절은 완성형이라 자모 배정 제외

    # 2) JP 글리프 사용 조사 (한글로 대체되는 스토리 대사 제외)
    used_lo, used_hi = set(), set()          # ≤0xFF(가나·기호) / >0xFF(한자)
    story_set = set(story_recs)

    # 🔑 줄바꿈 허용 판정 — **원본 JP 레코드가 근거다**(2026-08-07 M137 크래시로 확정).
    #    줄바꿈 핸들러 0x0606DD5C 는 대사창 구조체 [0x060792D4] 를 역참조한다. 대사창 없이
    #    렌더되는 레코드(메뉴 프롬프트·설명바)에서 밟으면 0xFFFFFFFF+0xC = 0x0B 홀수 write
    #    → ADDRESS ERROR. 원본이 대사창 레코드임을 스스로 증명하는 신호 두 가지만 믿는다:
    #      · JP 에 줄바꿈 0x03 이 있다        → 원본이 이미 대사창을 전제하고 쪼개 놨다
    #      · 마지막 글리프 뒤에 대기코드가 있다 → 버튼 대기 = 대사창
    #    둘 다 없으면 한 줄 전용 레코드로 보고 줄바꿈을 **절대** 넣지 않는다.
    BR_WAITS = (0x0004, 0x0005, 0x0006, 0x0008)

    def _br_ok(toks):
        body = toks[:-1] if toks and toks[-1] == TERM else toks
        if 0x0003 in body:
            return True
        last_g = max((k for k, t in enumerate(body) if t >= 0x20), default=-1)
        return any(t in BR_WAITS for t in body[last_g + 1:])

    br_ok = {i: _br_ok(it[2]) for i, it in enumerate(items) if it[0] == 'rec'}
    sys_map = {ri: sys_texts[k] for k, ri in enumerate(sys_recs)}

    def kr_of(i):
        if i in story_set:
            return kr_texts[story_recs.index(i)]
        if i in name_map:
            return name_map[i]
        return sys_map.get(i, '')

    # ⚠️ **실제로 한글로 바뀌는 레코드만** '번역됨'이다. 잘렸던 레코드는 JP 를 그대로 쓰므로
    #    그 한자 글리프도 반드시 살려둬야 한다(안 그러면 흰 네모로 깨짐 — 실기 확인).
    def ok_to_translate(i, toks):
        if not kr_of(i).strip():
            return False
        if i in name_map:
            return True                                           # 몬스터/아이템·마법명(짧음, 잘림無)
        if i in story_set:
            if story_done.get(i):
                return True                                       # 온전한 원문으로 재번역됨
            return not Mdx.was_truncated(toks)                    # 0x07/0x08 기준
        if sys_done.get(i):
            return True                                           # 온전한 jp 로 재번역됨
        return not Mdx.was_truncated(toks, WAITS)                 # 0x04/06/07/08 기준

    translated = {i for i, it in enumerate(items)
                  if it[0] == 'rec' and ok_to_translate(i, it[2])}
    for i, it in enumerate(items):
        if it[0] != 'rec' or i in translated:
            continue
        for t in it[2]:
            if 0x20 <= t <= 0xFF:
                used_lo.add(t)
            elif t > 0xFF:
                used_hi.add(t)

    # 3) 인덱스 배정.
    #  · 가나·기호(≤0xFF)는 원래 인덱스 유지 — 이 구간은 **고정폭 12px 전진**(호출자 R6=0x0C).
    #  · 🔑 글리프표는 인덱스로 접근하므로 0x20~0x100 구간(225슬롯)은 어차피 잡힌다.
    #    가나가 안 쓰는 빈 슬롯에 **완성형 한글을 공짜로** 넣는다(고정폭 12px = 완성형에 딱 맞음).
    #    자모는 전진 0(폭 -1)이 필요해서 반드시 0x101 이상이어야 한다.
    #  · 한자는 0x101~ 로 압축 재배치, 그 뒤에 자모, 남는 완성형 순.
    used_lo.add(0x20)                                   # 공백 글리프
    # 🔑 kr 의 `[XXX]` 통과 표기가 가리키는 글리프도 살려둬야 한다(스토리는 사용조사에서 제외되므로).
    for t in all_texts:
        for m in _TOK.finditer(t):
            if m.group(1) is None:
                continue
            v = int(m.group(1), 16)
            if v > 0xFF:
                used_hi.add(v)
            elif v >= 0x20:
                used_lo.add(v)

    # ⚠️ **0x20~0x100 은 절대 건드리지 않는다.**
    #    메시지에 안 쓰이는 슬롯이라도 **이름 입력 그리드 등 UI 가 글리프를 인덱스로 직접 찍는다**
    #    (실기 확인: 거기에 완성형 한글을 넣었더니 かきくけ 사이에 한글이 박혀 나옴).
    #    한글·재배치 한자는 전부 0x101 이상에만 배치한다.
    enc.extras_low = {}
    full_low = {}

    # ⚠️ 자모는 0x101 바로 위(실기 검증된 구성). 0x350+ 는 게임 동적 글리프 캐시 구간이라 피한다.
    enc.name_reserve = ({ch: KANJI_FIRST + k for k, ch in enumerate(NAME_SYLLABLES)}
                        if RESERVE_NAMES else {})
    nxt = enc.alloc(KANJI_FIRST, full, full_low)
    kanji_map = {}
    i = nxt
    for t in sorted(used_hi):
        kanji_map[t] = i; i += 1
    enc.kanji_map = kanji_map          # kr 의 [XXX] 통과 토큰도 재배치된 인덱스로 바꿔야 함
    max_idx = i - 1

    # 4) 전 레코드 토큰 재작성
    new_toks = []
    for i, it in enumerate(items):
        if it[0] != 'rec':
            new_toks.append(None); continue
        kr = kr_of(i)
        if i in translated:
            # kr 에는 [XX] 제어코드가 이미 들어 있다(jp 렌더에 포함돼 번역됨).
            # 뒤에 **끝 제어코드 + 0x0000** 만 붙인다(마지막 글리프 이후의 원본 꼬리).
            last_g = max((j for j, t in enumerate(it[2]) if t >= 0x20), default=-1)
            tail = list(it[2][last_g + 1:]) if last_g >= 0 else [TERM]
            if not tail or tail[-1] != TERM:
                tail.append(TERM)
            ok_br = br_ok.get(i, False)
            new_toks.append(enc.tokens(kr, wrap=(i in story_set) and ok_br,
                                       allow_br=ok_br) + tail); continue
        out = []
        for t in it[2]:
            out.append(kanji_map.get(t, t) if t > 0xFF else t)
        new_toks.append(out)

    # 4b) NPC 이름 레코드(688~694)를 ≤0xFF 한글 슬롯 토큰으로 교체.
    #     [0b] 가 struct 아닌 이 시스템 레코드를 직접 렌더하므로, 토큰만 한글슬롯이면 한글로 나온다.
    for sid, slots in NPC_NAME_SLOTS.items():
        if sid < len(sys_recs):
            new_toks[sys_recs[sid]] = list(slots) + [TERM]

    # 5) 코드북 재빌드 (전 레코드의 심볼열)
    def syms_of(toks):
        s = []
        for t in toks:
            s += [(t >> 8) & 0xff, t & 0xff]
        return s

    records_syms = [syms_of(t) for t in new_toks if t is not None]
    cb = cbm.Codebook.from_records(records_syms)
    enc_data = [cb.encode(s) for s in records_syms]
    maxrec = max(len(e) for e in enc_data)      # ⚠️ 길이 프리픽스 1바이트 → 레코드는 ≤255B

    # 6) 레이아웃: [헤더 12B][글리프표][코드북 blob][table1][레코드][table2_flat]
    # ⚠️ **4바이트 정렬 필수**: SH-2는 MOV.L 을 정렬 안 된 주소에서 하면 ADDRESS ERROR.
    #    디코더는 table1[idx] 에서, seek 는 table2_flat[hi] 에서 롱워드를 읽는다.
    #    (실기 크래시로 확인: table1=0x2202c7, table2=0x2287a1 홀수 → ADDRESS ERROR @0x606D824)
    def a4(x):
        return (x + 3) & ~3

    glyph_addr = LW_HDR + 12                    # 0x21800c — 4정렬 OK (글리프 스트라이드 32B)
    n_slots = max_idx - GLYPH_LO + 1
    glyph_size = n_slots * 32
    cb_addr = glyph_addr + glyph_size
    blob, _ = cb.emit(cb_addr)
    t1_addr = a4(cb_addr + len(blob))           # ← table1 4정렬
    blob, t1 = cb.emit(cb_addr)                 # 주소 확정 후 재emit(동일)
    rec_addr = t1_addr + len(t1)                # table1 = 2048B → 정렬 유지

    msg_size = sum(1 + len(e) for e in enc_data) + sum(1 for it in items if it[0] == 'term')
    t2_addr = a4(rec_addr + msg_size)           # ← table2_flat 4정렬
    total = (t2_addr + 7 * 4) - LW_HDR
    ok = (total <= mdx.cap) and (maxrec <= 255)
    long_texts = [kr_texts[j] for j, ri in enumerate(story_recs)
                  if len(enc_data[[k for k, it in enumerate(items) if it[0] == 'rec'].index(ri)]) > 255]
    st = {'total': total, 'cap': mdx.cap, 'spare': mdx.cap - total, 'maxrec': maxrec, 'ok': ok,
          'long_texts': long_texts, 'full_set': set(full),
          'slots': max_idx - GLYPH_LO + 1, 'glyph': glyph_size, 'cb': len(blob) + len(t1),
          'msg': msg_size, 'kanji': len(kanji_map), 'jamo': len(enc.jamo_keys),
          'full': len(full), 'extra': len(enc.extras),
          'n_story': len(story_recs), 'n_tr': sum(1 for t in kr_texts if t.strip()),
          'n_sys': sum(1 for t in sys_texts if t.strip()),
          'max_idx': max_idx}
    if not ok:
        return None, st          # 실패 시엔 바이트를 만들지 않는다(레코드 255B 초과면 조립 불가)

    # 레코드 배치(종료자 위치 보존) + 옛 주소 → 새 주소
    addr_map = {}
    body = bytearray()
    p = rec_addr
    ei = 0
    for i, it in enumerate(items):
        if it[0] == 'term':
            addr_map[it[1]] = p; body.append(0); p += 1; continue
        e = enc_data[ei]; ei += 1
        addr_map[it[1]] = p
        body.append(len(e)); body += e; p += 1 + len(e)
    assert p <= t2_addr                      # 정렬 패딩(0)이 뒤에 붙을 수 있음 = 블록 종료자로 무해
    t2 = bytearray()
    for hi in range(7):
        ob = mdx.s.block_base(hi)
        t2 += struct.pack('>I', addr_map.get(ob, 0))

    # 7) 섹션0 바이트 조립
    sec = bytearray(total)
    struct.pack_into('>4I', sec, 0, glyph_addr, t1_addr, t2_addr, mdx.hdr3)
    # 글리프표: 원본(가나·기호) → 한자 재배치 → 한글
    for idx in range(GLYPH_LO, 0x101):
        src = mdx.glyph_addr + (idx - GLYPH_LO) * 32
        g = mdx.rd(src, 32)
        if len(g) == 32:
            o = (glyph_addr - LW_HDR) + (idx - GLYPH_LO) * 32
            sec[o:o + 32] = g
    # 한글 이름입력 완성형: 기존 ≤0xFF 가나/기호 슬롯을 덮어쓴다(예산 0).
    for slot, g in NAME_INPUT_GLYPHS.items():
        assert GLYPH_LO <= slot <= 0x100 and len(g) == 32
        o = (glyph_addr - LW_HDR) + (slot - GLYPH_LO) * 32
        sec[o:o + 32] = g
    for old, new in kanji_map.items():
        g = mdx.rd(mdx.glyph_addr + (old - GLYPH_LO) * 32, 32)
        o = (glyph_addr - LW_HDR) + (new - GLYPH_LO) * 32
        sec[o:o + 32] = g
    for idx, g in enc.glyphs():
        o = (glyph_addr - LW_HDR) + (idx - GLYPH_LO) * 32
        sec[o:o + 32] = g
    sec[cb_addr - LW_HDR:cb_addr - LW_HDR + len(blob)] = blob
    sec[t1_addr - LW_HDR:t1_addr - LW_HDR + len(t1)] = t1
    sec[rec_addr - LW_HDR:rec_addr - LW_HDR + len(body)] = body
    sec[t2_addr - LW_HDR:t2_addr - LW_HDR + len(t2)] = t2

    if verbose:
        print("  글리프 %d슬롯 %dB (가나 %d + 한자 %d + 자모 %d + 완성형 %d + 기타 %d)"
              % (st['slots'], glyph_size, 0xE0, st['kanji'], st['jamo'], st['full'], st['extra']))
        print("  코드북 %dB | 메시지 %dB (최장 rec %dB) | 합계 %dB / %dB (여유 %dB)"
              % (st['cb'], st['msg'], maxrec, total, mdx.cap, st['spare']))
    return bytes(sec), st


def optimize(mdx, kr_list, verbose=True):
    """예산 안에서 **완성형 음절 수를 최대화**(=품질 최대). 자모는 예산이 빠듯할 때의 안전판.

    · 0x20~0x100 의 빈 저슬롯에 들어가는 완성형은 **공짜**(고정폭 12px = 완성형에 딱 맞음).
    · 그 위로는 완성형 1음절 = 글리프 +32B 이지만 메시지는 줄어든다(자모 2~3토큰 → 1토큰).
    · 레코드는 ≤255B(길이 프리픽스 1B). 초과하면 **그 레코드에 쓰인 음절만** 완성형 승격.
    """
    cache = {}

    def T(n, extra=()):
        k = (n, tuple(extra))
        if k not in cache:
            cache[k] = repack(mdx, kr_list, n, verbose=False, extra_full=extra)
        return cache[k]

    # 1) 들어가는 최대 n_full 을 거친 스캔 + 정밀화로 찾는다
    feas = [n for n in range(0, 1401, 100) if T(n)[1]['ok']]
    if not feas:
        best = min((st for _, st in cache.values()), key=lambda x: x['total'])
        raise SystemExit("안 들어감: %dB/%dB, 최장rec %dB" % (best['total'], best['cap'], best['maxrec']))
    hi = max(feas)
    for n in range(hi + 20, hi + 120, 20):
        if T(n)[1]['ok']:
            hi = n
        else:
            break

    # 2) 레코드 255B 초과가 남으면 그 레코드의 음절만 타겟 승격
    extra = []
    for _ in range(30):
        sec, st = T(hi, extra)
        if st['ok']:
            break
        if st['maxrec'] > 255:
            cand = Counter()
            for txt in st['long_texts']:
                for ch in _TOK.sub('', txt):
                    if '가' <= ch <= '힣' and ch not in st['full_set']:
                        cand[ch] += 1
            add = [c for c, _ in cand.most_common(8)]
            if not add:
                break
            extra += add
        else:
            hi = max(0, hi - 40)
    sec, st = repack(mdx, kr_list, hi, verbose=verbose, extra_full=extra)
    st['n0'], st['extra'] = hi, extra
    if not st['ok']:
        raise SystemExit("안 들어감: %dB/%dB, 최장rec %dB" % (st['total'], st['cap'], st['maxrec']))
    return sec, st


def kr_list_of(sj):
    """셋 JSON → (스토리 박스 순번별 번역문, 재번역 여부).
    `retranslated`=True 는 **온전한 원문 기준으로 다시 번역된 박스**(옛 추출기가 잘라먹었던 것)."""
    n = max(b['box'] for b in sj['boxes']) + 1
    out = [''] * n
    done = [False] * n
    for b in sj['boxes']:
        out[b['box']] = b.get('kr', '')
        done[b['box']] = bool(b.get('retranslated'))
    return out, done


def verify(mdx, sec, boxes_kr):
    """재빌드된 섹션0을 진짜 디코더로 다시 읽어 토큰이 일치하는지 검증."""
    fake = bytearray(mdx.data)
    fake[SEC0_FOFF:SEC0_FOFF + len(sec)] = sec
    s2 = es.Script(bytes(fake), os.path.join(_here, '..', 'docs', 'glyph_table_forest.txt'),
                   base=MDX_BASE)
    n = 0
    for hi in range(7):
        for off, ln, toks in s2.records(hi):
            n += 1
            if n > 4000:
                break
    return n


if __name__ == '__main__':
    setf = sys.argv[1] if len(sys.argv) > 1 else 'set02_M511.json'
    sj = json.load(open(os.path.join(_here, '..', 'translation', 'sets', setf), encoding='utf-8'))
    mdx = Mdx(sj['rep_map'])
    boxes_kr = kr_list_of(sj)
    print("%s (%s): 섹션0 현재 %dB, 확장가능 %dB" % (setf, mdx.name, mdx.cur_size, mdx.cap))
    sec, st = optimize(mdx, boxes_kr)
    print("  → 완성형 %d음절, 자모 %d, 대사 %d/%d 번역"
          % (st['full'], st['jamo'], st['n_tr'], st['n_story']))
