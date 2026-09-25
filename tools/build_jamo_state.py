#!/usr/bin/env python3
"""
자모 조합형 **실기 PoC** 스테이트 빌더 (2026-07-13).

목적: 한 칸에 자모 3개를 겹쳐 그리는 게 실기에서 되는지 판별한다.
  · 글리프 idx > 0x100 → 커서 += word0 + 1  → 초성/중성 폭 -1(전진 0), 종성 폭 11(전진 12)
  · 1bpp→8bpp 전개는 투명 블릿(0비트 미기록) → 겹치면 OR 합성
  ⚠️ 단, 드로우 앞 셀 클리어(0x0606C2F4)가 호출되면 2번째 자모가 1번째를 지운다.
     → **두 스테이트를 만들어 실기로 판별**:
        OUT.a  = 코드패치 없음  (클리어가 꺼져 있으면 이것만으로 정상)
        OUT.b  = X02 클리어 스킵 패치(0x0606D42E: BT/S 8D06 → BRA A006)

베이스 = state20(검증된 truncation 훅: box0/1/2 한글, 크래시無·JP잔상無).
훅 테이블의 jp_hash 3개는 그대로 두고, **한글 토큰배열만 자모 인코딩으로 교체** + 자모 글리프를
스냅샷 LWRAM 글리프표(슬롯 0x101~)에 기록한다.
⚠️ box0는 스테이트 로드 시 훅을 안 거친다 → **판별은 반드시 box1/box2 진행해서 볼 것.**

사용: build_jamo_state.py <base.state> <out_prefix>
"""
import sys, os, struct, zlib, json, re, importlib.util

_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


bhs = _L("build_hook_state")
jf = _L("jamo_font")
hf = _L("hangul_font")
em = _L("extract_mdx")
es = _L("extract_script")

HBASE = bhs.HBASE                 # 0x060b5a00
S16_TABLE = bhs.S16_TABLE         # 0x060b5a84
LW_BASE = 0x200000
HW_BASE = 0x06000000
JAMO_FIRST = 0x101                # ⚠️ 반드시 > 0x100 (그 이하는 커서 전진이 고정폭)
CLEAR_PATCH_ADDR = 0x0606D42E     # BT/S 0x8D06 → BRA 0xA006 (셀 클리어 스킵)
MDX_BASE = 0x217800
STORY_START_REC = 55
_TOK = re.compile(r'\[([0-9a-fA-F]{2,4})\]|\{(br|sp)\}')


def hook_hash(toks):
    h = 0
    for t in toks:
        if t in (0x0008, 0x0004):
            break
        h = ((h * 33) + (t & 0xffff)) & 0xffffffff
    return h


class GlyphAlloc:
    """자모 184개(고정) + 비한글 문자(완성형)에 슬롯 배정. = 하이브리드의 최소형."""

    def __init__(self):
        self.js = jf.JamoSet()
        self.keys = self.js.all_keys()
        self.idx = {k: JAMO_FIRST + i for i, k in enumerate(self.keys)}
        self.next = JAMO_FIRST + len(self.keys)
        self.extra = {}          # ch -> idx (완성형)

    def syllable_tokens(self, ch):
        return [self.idx[k] for k in self.js.keys_of(ch)]

    def extra_token(self, ch):
        if ch not in self.extra:
            self.extra[ch] = self.next; self.next += 1
        return self.extra[ch]

    def entries(self):
        """[(idx, 32B 글리프)] 전부."""
        out = [(self.idx[k], jf.encode_glyph(self.js.width_of(k), self.js.g[k])) for k in self.keys]
        for ch, i in self.extra.items():
            out.append((i, hf.glyph_for(ch)[0]))
        return out


def kr_to_tokens(kr, ga):
    toks = []
    i = 0
    while i < len(kr):
        m = _TOK.match(kr, i)
        if m:
            if m.group(1) is not None:
                toks.append(int(m.group(1), 16))
            elif m.group(2) == 'br':
                toks.append(0x03)
            else:
                toks.append(0x20)
            i = m.end(); continue
        ch = kr[i]; i += 1
        if ch == '\n':
            toks.append(0x03)
        elif ch in ' 　':
            toks.append(0x20)
        elif '가' <= ch <= '힣':
            toks += ga.syllable_tokens(ch)
        else:
            toks.append(ga.extra_token(ch))
    toks.append(0x08)
    return toks


def main():
    base_state, out_prefix = sys.argv[1], sys.argv[2]
    raw = open(base_state, 'rb').read()
    block = struct.unpack('<I', raw[8:12])[0]
    snap = bytearray(bhs.parse(raw))

    m = snap.find(b'MAIN')
    LW = m + 0x105                       # Work RAM Low  (1MB, swap16)
    HW = LW + 0x10000D                   # Work RAM High (1MB, swap16)
    lw = bytearray(bhs.deswap(snap[LW:LW + 0x100000]))
    hw = bytearray(bhs.deswap(snap[HW:HW + 0x100000]))

    gbase = struct.unpack('>I', lw[0x18000:0x18004])[0]
    assert gbase == 0x21800c, "LWRAM 위치 오인식: [0x218000]=0x%08x" % gbase
    print("LWRAM @snap 0x%x, 글리프표 base=0x%08x" % (LW, gbase))

    def HWL(a):
        return struct.unpack('>I', hw[a - HW_BASE:a - HW_BASE + 4])[0]

    for lit in bhs.INSTALL_LITS:
        assert HWL(lit) == HBASE, "install 리터럴 0x%x != 훅주소" % lit

    # 훅의 리터럴 풀에서 TABLE 주소를 찾는다(풀 = [DECODE][BUF][TABLE], 코드 크기에 따라 위치 이동).
    tbl = None
    for a in range(HBASE, HBASE + 0x400, 4):
        if HWL(a) == bhs.DECODE and HWL(a + 4) == bhs.BUF:
            tbl = HWL(a + 8); break
    assert tbl and HBASE <= tbl < HBASE + 0x800, "훅 테이블을 못 찾음"
    hashes = [HWL(tbl + e * 8) for e in range(3)]
    print("기존 훅 TABLE=0x%08x, 해시: %s" % (tbl, " ".join("0x%08x" % h for h in hashes)))

    # 이 해시가 set02(M511 forest)의 어느 박스인지 역매핑
    sj = json.load(open(os.path.join(_here, '..', 'translation', 'sets', 'set02_M511.json'),
                       encoding='utf-8'))
    mdx = em.read_mdx(sj['rep_map'])
    sc = es.Script(mdx, os.path.join(_here, '..', 'docs', 'glyph_table_forest.txt'), base=MDX_BASE)
    by_hash = {}
    for off, ln, toks in list(sc.records(6))[STORY_START_REC:]:
        by_hash[hook_hash(toks)] = '0x%x' % (off + 1)
    kr_by_addr = {b['addr']: b['kr'] for b in sj['boxes']}

    ga = GlyphAlloc()
    entries = []
    for h in hashes:
        addr = by_hash.get(h)
        kr = kr_by_addr.get(addr, '')
        if not kr:
            raise SystemExit("해시 0x%08x 에 대응하는 번역을 못 찾음 (addr=%s)" % (h, addr))
        toks = kr_to_tokens(kr, ga)
        entries.append((h, toks))
        print("  0x%08x %-9s %d토큰  %s" % (h, addr, len(toks), kr.replace('\n', '/')))

    # 글리프 주입 (LWRAM 글리프표)
    ge = ga.entries()
    for idx, g in ge:
        assert len(g) == 32
        a = gbase + (idx - 0x20) * 32
        lw[a - LW_BASE:a - LW_BASE + 32] = g
    print("글리프 %d개 주입 (자모 %d + 완성형 %d), 슬롯 0x%x~0x%x"
          % (len(ge), len(ga.keys), len(ga.extra), JAMO_FIRST, ga.next - 1))
    if ga.extra:
        print("  완성형 슬롯: " + " ".join("%s=0x%x" % (c, i) for c, i in ga.extra.items()))

    # 훅 재빌드
    hook, arr_ptrs, TABLE = bhs.build_hook(entries)
    for a in range(HBASE, HBASE + 0x800):
        hw[a - HW_BASE] = 0
    hw[HBASE - HW_BASE:HBASE - HW_BASE + len(hook)] = hook
    print("훅 %dB @0x%08x, TABLE=0x%08x" % (len(hook), HBASE, TABLE))

    def write_state(path, clear_patch):
        h2 = bytearray(hw)
        if clear_patch:
            o = CLEAR_PATCH_ADDR - HW_BASE
            cur = struct.unpack('>H', h2[o:o + 2])[0]
            assert cur == 0x8D06, "클리어 분기 0x%04x (0x8D06 기대)" % cur
            struct.pack_into('>H', h2, o, 0xA006)      # BT/S → BRA (클리어 항상 스킵)
        s2 = bytearray(snap)
        s2[LW:LW + 0x100000] = bhs.deswap(bytes(lw))
        s2[HW:HW + 0x100000] = bhs.deswap(bytes(h2))
        out = bytearray(raw[:20]); pp = 0
        while pp < len(s2):
            c = zlib.compress(bytes(s2[pp:pp + block]), 9)
            out += struct.pack('<I', len(c)) + c; pp += block
        open(path, 'wb').write(out)
        print("  -> %s (%dB)%s" % (path, len(out), " [클리어 스킵 패치]" if clear_patch else ""))

    write_state(out_prefix + 'a', False)
    write_state(out_prefix + 'b', True)
    print("\n실기: 두 스테이트를 로드해 **box1/box2까지 대사를 진행**해서 볼 것"
          " (box0는 스테이트 로드 시 훅을 안 거침).")


if __name__ == '__main__':
    main()
