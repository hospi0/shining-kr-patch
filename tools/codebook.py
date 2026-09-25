#!/usr/bin/env python3
"""
Shining the Holy Ark — order-1 문맥 Huffman **코드북 빌더** (2026-07-13).

기존 코드북(table1)은 JP 심볼만 커버해서 한글 인덱스를 인코딩할 수 없다(추가32: 전이제약).
→ 메시지 전체(블록0~6 + 한글 대사)를 재인코딩하려면 **코드북 자체를 새로 만들어야** 한다.

## 디코더 규격 (tools/decompress.py, 런타임 0x0606cbd4 역공학)
table1 @ [0x218004] = 256엔트리 × 8B = (symbase_ptr, treeA_ptr).   idx = 직전 출력 바이트(문맥).
decode_byte(idx):
    sa = treeA 비트리더(mask 0x80, **매 호출 리셋**);  R8 = 0
    loop: a = sa.bit()
          if a == 1: return symbase[R8]              # 리프
          b = sb.bit()                               # 입력 비트
          if b == 0: continue                        # 왼쪽 자식으로 하강(다음 pre-order 비트)
          cnt = 0                                    # b == 1: 왼쪽 서브트리를 건너뛴다
          while True:
              if sa.bit() == 1: R8 += 1; cnt -= 1    #   (리프 수만큼 R8 전진)
              else:             cnt += 1
              if cnt < 0: break

→ **treeA = pre-order 비트열**(1 = 리프, 0 = 내부노드 뒤에 [왼쪽][오른쪽]),
  **symbase = 리프 심볼을 왼→오 순서로 나열**, **코드 = 경로 비트**(0 = 왼쪽, 1 = 오른쪽).
  심볼이 1개뿐인 문맥은 트리가 리프 하나 → 입력 비트를 **하나도 안 먹고** 그 심볼을 낸다.

## 사용
    cb = Codebook.from_records(records)      # records = [[심볼바이트...], ...] (각 레코드 idx=0으로 시작)
    data = cb.encode(syms)                   # 심볼열 → 압축 바이트 (MSB-first)
    blob, table1 = cb.emit(base_addr)        # 코드북 본문(트리+symbase) + table1 2048B
"""
import struct, heapq
from collections import Counter, defaultdict


class _Node:
    __slots__ = ('f', 'sym', 'l', 'r', 'seq')

    def __init__(self, f, sym=None, l=None, r=None, seq=0):
        self.f, self.sym, self.l, self.r, self.seq = f, sym, l, r, seq


def _huffman(freq):
    """{sym: count} → 트리 루트. 심볼 1개면 단일 리프."""
    items = sorted(freq.items())
    if not items:
        return _Node(0, sym=0)
    if len(items) == 1:
        return _Node(items[0][1], sym=items[0][0])
    h = []
    for i, (s, f) in enumerate(items):
        heapq.heappush(h, (f, i, _Node(f, sym=s, seq=i)))
    nxt = len(items)
    while len(h) > 1:
        f1, s1, n1 = heapq.heappop(h)
        f2, s2, n2 = heapq.heappop(h)
        heapq.heappush(h, (f1 + f2, nxt, _Node(f1 + f2, l=n1, r=n2, seq=nxt)))
        nxt += 1
    return h[0][2]


def _walk(node, path, out_paths, out_syms, out_bits):
    """pre-order emit: 리프=1, 내부=0+[왼][오]. 동시에 심볼 경로 수집."""
    if node.sym is not None:
        out_bits.append(1)
        out_syms.append(node.sym)
        out_paths[node.sym] = path
        return
    out_bits.append(0)
    _walk(node.l, path + (0,), out_paths, out_syms, out_bits)
    _walk(node.r, path + (1,), out_paths, out_syms, out_bits)


def _pack_bits(bits):
    out = bytearray()
    for i in range(0, len(bits), 8):
        b = 0
        for j, v in enumerate(bits[i:i + 8]):
            if v:
                b |= 1 << (7 - j)
        out.append(b)
    return bytes(out)


class Codebook:
    def __init__(self, freqs):
        """freqs: {ctx(0~255): {sym: count}}"""
        self.paths = {}      # ctx -> {sym: bit tuple}
        self.trees = {}      # ctx -> (tree_bytes, symbase_bytes)
        for ctx in range(256):
            f = freqs.get(ctx) or {0: 1}
            root = _huffman(f)
            paths, syms, bits = {}, [], []
            _walk(root, (), paths, syms, bits)
            self.paths[ctx] = paths
            self.trees[ctx] = (_pack_bits(bits), bytes(syms))

    @classmethod
    def from_records(cls, records):
        freqs = defaultdict(Counter)
        for syms in records:
            ctx = 0
            for s in syms:
                freqs[ctx][s] += 1
                ctx = s
        return cls(freqs)

    def can_encode(self, ctx, sym):
        return sym in self.paths[ctx]

    def encode(self, syms):
        """심볼열 → 압축 바이트. 레코드마다 ctx=0으로 시작(디코더와 동일)."""
        bits = []
        ctx = 0
        for s in syms:
            p = self.paths[ctx].get(s)
            if p is None:
                raise KeyError("ctx 0x%02x 에서 심볼 0x%02x 인코딩 불가" % (ctx, s))
            bits += p
            ctx = s
        return _pack_bits(bits)

    def emit(self, base_addr):
        """코드북 본문(중복 제거)과 table1(256×8B)을 만든다.
        반환 (blob, table1). blob 은 base_addr 에 놓인다고 가정."""
        blob = bytearray()
        pos = {}                       # bytes -> offset (트리/symbase 중복 제거)

        def put(b):
            if b not in pos:
                pos[b] = len(blob)
                blob.extend(b)
            return base_addr + pos[b]

        t1 = bytearray()
        for ctx in range(256):
            tree, sym = self.trees[ctx]
            sb = put(sym)              # symbase 먼저(바이트 배열)
            ta = put(tree)
            t1 += struct.pack('>II', sb, ta)
        return bytes(blob), bytes(t1)

    def size(self, base_addr=0):
        blob, t1 = self.emit(base_addr)
        return len(blob) + len(t1)


def selftest():
    """실제 디코더(decompress.py)로 라운드트립 검증."""
    import os, importlib.util, random
    _here = os.path.dirname(os.path.abspath(__file__))
    sp = importlib.util.spec_from_file_location("decompress", os.path.join(_here, "decompress.py"))
    dc = importlib.util.module_from_spec(sp); sp.loader.exec_module(dc)

    random.seed(7)
    # 한글 토큰 같은 분포(hi=0x01/0x02, lo 광범위) + 제어코드
    recs = []
    for _ in range(40):
        toks = []
        for _ in range(random.randint(5, 40)):
            t = random.choice([0x0020, 0x0003] + [0x0100 + random.randint(0, 0xff) for _ in range(6)]
                              + [0x0200 + random.randint(0, 0x50)])
            toks.append(t)
        toks.append(0x0008)
        syms = []
        for t in toks:
            syms += [(t >> 8) & 0xff, t & 0xff]
        recs.append(syms)

    cb = Codebook.from_records(recs)
    BASE = 0x220000
    blob, t1 = cb.emit(BASE)
    T1_ADDR = BASE + len(blob)

    # 가짜 LWRAM: [0x218004]=table1 주소, table1/blob/데이터 배치
    lw = bytearray(0x100000)

    def put(addr, b):
        lw[addr - 0x200000:addr - 0x200000 + len(b)] = b

    struct.pack_into('>I', lw, 0x18004, T1_ADDR)
    put(BASE, blob)
    put(T1_ADDR, t1)

    DATA = T1_ADDR + len(t1)
    p = DATA
    packed = []
    for syms in recs:
        enc = cb.encode(syms)
        put(p, enc); packed.append((p, len(enc))); p += len(enc)

    D = dc.Decompressor(bytes(lw), 0x200000)
    bad = 0
    for (addr, ln), syms in zip(packed, recs):
        sb = D.bits(addr, 0x80)
        idx = 0; out = []
        for _ in range(len(syms)):
            s = D.decode_byte(idx, sb); out.append(s); idx = s
        if out != syms:
            bad += 1
    total = sum(len(s) for s in recs)
    print("코드북 %dB(blob %d + table1 %d), 데이터 %dB (심볼 %d → %.2f bit/sym)"
          % (len(blob) + len(t1), len(blob), len(t1), p - DATA, total, 8.0 * (p - DATA) / total))
    print("라운드트립: %d/%d 레코드 %s" % (len(recs) - bad, len(recs), "OK" if bad == 0 else "실패!"))
    return bad == 0


if __name__ == '__main__':
    import sys
    sys.exit(0 if selftest() else 1)
