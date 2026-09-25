#!/usr/bin/env python3
"""
Shining the Holy Ark — 씬 대사 추출기 (2026-07-12, 비트연속 체이닝).

씬 대사(NPC 대화)는 시스템 메시지(X2SAMPLE 블록)와 달리 런타임 컴파일러가 메시지 영역 뒤에
주입한 압축 메시지 스트림이다(table2_flat에 없음).
- 각 박스 = order-1 Huffman 메시지, **바이트정렬 시작(mask=0x80)**, idx=0 리셋, 종료 0x0008(버튼대기)/0x0004(대화끝).
- **박스는 바이트정렬**이고, 박스 사이에 **0~2바이트 구분자/헤더**(raw, Huffman 아님)가 있다. 다음 박스는
  이전 종료 다음 바이트부터 몇 바이트 안에서 **정확한 바이트정렬 시작**을 브루트포스로 찾는다(head_score 최대).
  (교훈: "바이트+1" 순진 체이닝은 드리프트. 각 박스 시작을 클린점수로 재정렬해야 깔끔.)
- 텍스트 토큰 hi=0x00(가나/제어) 또는 0x01~0x03(한자 index 0x100~0x3ff). {xxxx}(hi바이트≠0, 한자아님)=오정렬 잔재.
- ⚠️ 소수 박스는 텍스트 중간 제어코드(후리가나/동적한자 로드 추정)가 hi/lo 페어링을 시프트 → {xxxx} 런 잔존(미해결).
- ⚠️ [xxx](한자 index 0x100~0x3ff)는 glyph_table_confirmed에 없는 씬 동적한자(0x354+). 런타임 글리프테이블 렌더로 보완 가능.

⚠️ 입력 = 런타임 스냅샷 LWRAM(디스왑). 씬 대사 시작 오프셋은 스냅샷별로 다름(포레스트 0x225ec6).
   디스크 전게임 추출은 컴파일러 입력 소스(동적분석) 미해결 — 현재는 씬 스냅샷 기반.

사용: python tools/extract_dialogue.py <lwram_deswap.bin> <approx_start_hex> [glyph_table] [n]
"""
import sys, os, importlib.util

_here = os.path.dirname(__file__)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_here, name + '.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


_dc = _load('decompress')
_es = _load('extract_script')

BOXEND = (0x08, 0x04)


def render(toks, GT, DK):
    o = []
    for t in toks:
        if t in BOXEND:
            break
        if t == 0x03:
            o.append('\n'); continue
        if t == 0x20:
            o.append(' '); continue
        if t < 0x20:
            continue  # 제어코드(0x00~0x1F): 렌더 스킵(글리프 아님)
        if t == 0xde:
            if o and o[-1] in DK:
                o[-1] = DK[o[-1]]
            else:
                o.append('゛')
            continue
        if (t & 0xff00) and not (0x100 <= t < 0x400):
            o.append('{%04x}' % t)
            continue
        o.append(GT.get(t, '[%03x]' % t))
    return ''.join(o)


class Dialogue:
    def __init__(self, lwram, glyph_path, base=0x200000):
        self.d = _dc.Decompressor(lwram, base)
        self.GT = _es.load_glyphs(glyph_path)
        self.DK = _es.DK

    def decode_box(self, ptr, maxt=400):
        """바이트정렬(mask=0x80) 박스 디코드 → (toks, 종료다음 바이트오프셋). 경계탐색용(페어링)."""
        sb = self.d.bits(ptr, 0x80); idx = 0; toks = []
        for _ in range(maxt):
            hi = self.d.decode_byte(idx, sb); idx = hi
            lo = self.d.decode_byte(idx, sb); idx = lo
            t = (hi << 8) | lo; toks.append(t)
            if t in BOXEND:
                break
        return toks, sb.ptr + (0 if sb.mask == 0x80 else 1)

    def decode_bytes(self, ptr, maxb=800):
        """박스를 decode_byte 스트림으로. 종료 = 0x00 뒤 0x08/0x04. (그리디 파싱용, desync 내성)."""
        sb = self.d.bits(ptr, 0x80); idx = 0; bs = []
        for _ in range(maxb):
            b = self.d.decode_byte(idx, sb); idx = b; bs.append(b)
            if len(bs) >= 2 and bs[-2] == 0x00 and bs[-1] in BOXEND:
                break
        return bs, sb.ptr + (0 if sb.mask == 0x80 else 1)

    def greedy(self, bs):
        """바이트 스트림 그리디 파싱: 00 XX=가나/제어, 01~03 XX=한자(0x100~0x3ff), 나머지 lead=제어 스킵.
        제어코드 홀수길이로 인한 hi/lo 페어링 desync에 내성(글리프만 추출)."""
        o = []; i = 0
        while i < len(bs) - 1:
            b = bs[i]
            if b == 0x00:
                c = bs[i + 1]; i += 2
                if c in BOXEND:
                    break
                if c == 0x03:
                    o.append('\n'); continue
                if c == 0x20:
                    o.append(' '); continue
                if c < 0x20:
                    continue
                if c == 0xde:
                    if o and o[-1] in self.DK:
                        o[-1] = self.DK[o[-1]]
                    else:
                        o.append('゛')
                    continue
                o.append(self.GT.get(c, '[%02x]' % c)); continue
            if b in (0x01, 0x02, 0x03):
                t = (b << 8) | bs[i + 1]; i += 2
                o.append(self.GT.get(t, '[%03x]' % t) if 0x100 <= t < 0x400 else '[%03x]' % t)
                continue
            i += 1  # 제어 lead 바이트 스킵
        return ''.join(o)

    @staticmethod
    def _head_score(toks, k=5):
        h = toks[:k]
        if not h:
            return 0.0
        return sum(1 for t in h if t in (0x03, 0x20, 0x00, 0xde, 0x08, 0x04) or 0x21 <= t < 0x400) / len(h)

    def find_start(self, lo, hi):
        """[lo,hi) 바이트 범위에서 head_score 최대인 박스 시작 바이트."""
        best, bs = None, -1.0
        for c in range(lo, hi):
            t, _ = self.decode_box(c, 12)
            if (t and t[-1] in BOXEND) or len(t) >= 8:
                s = self._head_score(t)
                if s > bs:
                    bs, best = s, c
        return best, bs

    def extract(self, approx_start, n=60, window=14):
        """박스 경계는 페어링(decode_box)으로 브루트포스 정렬, 텍스트는 그리디(desync 내성)."""
        addr = self.find_start(approx_start - 2, approx_start + 4)[0] or approx_start
        out = []
        for _ in range(n):
            _, endb = self.decode_box(addr)
            bs, _ = self.decode_bytes(addr)
            out.append((addr, self.greedy(bs)))
            nb, sc = self.find_start(endb - 1, endb + window)
            if nb is None or nb <= addr or sc < 0.6:
                break
            addr = nb
        return out


if __name__ == '__main__':
    import io
    lwram = open(sys.argv[1], 'rb').read()
    start = int(sys.argv[2], 16)
    gp = sys.argv[3] if len(sys.argv) > 3 else os.path.join(_here, '..', 'docs', 'glyph_table_full.txt')
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 60
    dlg = Dialogue(lwram, gp)
    w = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    for i, (ptr, txt) in enumerate(dlg.extract(start, n)):
        w.write('[%02d] @0x%x: %s\n' % (i, ptr, txt.replace('\n', '/')))
    w.flush()
