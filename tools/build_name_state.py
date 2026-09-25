#!/usr/bin/env python3
"""
한글 이름입력 **실기 PoC** 스테이트 빌더 (≤0xFF 완성형, 2026-07-15).

베이스 = state32(이름입력 화면). 편집 3가지:
  1) 완성형 이름 음절 42개를 글리프표 ≤0xFF 슬롯(name_kr.SLOTS)에 주입.
  2) 히라 그리드 테이블(X02 WRAM 0x06079638)을 한글 반절표 테이블로 교체.
  3) 모드는 0(히라) 그대로 → 그 자리에 한글 그리드가 뜬다.

append/렌더 **코드 무패치**(전부 1바이트 경로). 선택하면 슬롯 인덱스가 이름버퍼에 1바이트로
들어가고, 이름박스도 1바이트로 렌더 → 그대로 완성형 표시.

⚠️ 로드 직후 그리드는 이미 VRAM에 그려져 있을 수 있음(잔상). **커서를 움직이거나
   가타카나↔히라가나 모드를 한 번 토글**하면 한글 그리드로 재렌더된다.

사용: build_name_state.py <base.state> <out.state>
"""
import sys, os, struct, zlib, importlib.util

_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


bhs = _L("build_hook_state")
nk = _L("name_kr")

GRID_ADDR = 0x06079638      # X02 히라 그리드 테이블 (WRAM-High)
HW_BASE = 0x06000000
LW_BASE = 0x00200000


def main():
    base_state, out_state = sys.argv[1], sys.argv[2]
    raw = open(base_state, 'rb').read()
    block = struct.unpack('<I', raw[8:12])[0]
    snap = bytearray(bhs.parse(raw))

    m = snap.find(b'MAIN')
    LW = m + 0x105
    HW = LW + 0x10000D
    lw = bytearray(bhs.deswap(snap[LW:LW + 0x100000]))
    hw = bytearray(bhs.deswap(snap[HW:HW + 0x100000]))

    gbase = struct.unpack('>I', lw[0x18000:0x18004])[0]
    assert gbase == 0x21800c, "글리프표 위치 오인식 0x%08x" % gbase

    # 1) 완성형 글리프 주입 (≤0xFF 슬롯)
    G = nk.glyphs()
    for slot, g in G.items():
        assert len(g) == 32 and slot <= 0xFF
        o = (gbase - LW_BASE) + (slot - 0x20) * 32
        lw[o:o + 32] = g
    print("완성형 글리프 %d개 주입 (슬롯 0x%02x~0x%02x)" % (len(G), min(G), max(G)))

    # 2) 그리드 테이블 교체
    gt = nk.grid_table()
    assert len(gt) == 108
    o = GRID_ADDR - HW_BASE
    orig = bytes(hw[o:o + 5])
    assert orig == bytes([0x91, 0x92, 0x93, 0x94, 0x95]), "그리드 테이블 시그니처 불일치 %s" % orig.hex()
    hw[o:o + 108] = gt
    print("그리드 테이블 교체 @0x%08x (한글 반절표 %d음절)" % (GRID_ADDR, len(nk.SYLL)))

    # 3) 모드 0 확인(이름박스 버퍼는 그대로 — 플레이어가 지우고 한글 입력)
    mode = struct.unpack('>H', hw[0x7BD1C:0x7BD1E])[0]
    print("현재 모드=%d (0=히라 자리에 한글 그리드)" % mode)

    # 재조립
    snap[LW:LW + 0x100000] = bhs.deswap(bytes(lw))
    snap[HW:HW + 0x100000] = bhs.deswap(bytes(hw))
    out = bytearray(raw[:20]); pp = 0
    while pp < len(snap):
        c = zlib.compress(bytes(snap[pp:pp + block]), 9)
        out += struct.pack('<I', len(c)) + c; pp += block
    open(out_state, 'wb').write(out)
    print("-> %s (%dB)" % (out_state, len(out)))
    print("\n실기: 로드 -> 커서 이동/모드 토글로 한글 그리드 재렌더 ->")
    print("      기존 이름 지우고 한글 음절 선택 -> 이름박스 완성형 확인 ->")
    print("      이름 끝내기 후 대사/메뉴에서 한글 이름 나오는지 확인.")


if __name__ == '__main__':
    main()
