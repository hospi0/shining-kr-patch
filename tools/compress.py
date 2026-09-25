#!/usr/bin/env python3
"""
Shining the Holy Ark — order-1 문맥 Huffman **인코더** (2026-07-13). decompress.py의 역.

디코더(decompress.decode_byte)를 트리 DFS로 역산: 각 context(idx=직전바이트)의 코드북 트리를
따라가며 sb(입력) 비트 선택으로 심볼 도달. 심볼별 유일 비트경로 → (symbol→bits) 맵.
인코드: 심볼열을 순회, 현 context의 경로 붙이고 context=심볼 갱신. MSB-first 패킹(디코더와 동일).

코드북=MDX/스냅샷의 table1@[0x218004]. 인코더는 Decompressor 인스턴스(같은 base)로 초기화.
✅roundtrip 검증: JP 레코드 재압축=원본 바이트 일치.
"""
import struct, sys, importlib.util, os

_here = os.path.dirname(os.path.abspath(__file__))
_dc = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("decompress", os.path.join(_here, "decompress.py")))
importlib.util.spec_from_file_location("decompress", os.path.join(_here, "decompress.py")).loader.exec_module(_dc)


class Encoder:
    def __init__(self, D):
        self.D = D            # decompress.Decompressor (same buffer+base)
        self._cache = {}      # idx -> {symbol: bits tuple}

    def _tree_bit(self, st):
        ptr, mask = st
        b = 1 if (self.D.rd(ptr, 1)[0] & mask) else 0
        mask >>= 1
        if mask == 0:
            ptr += 1; mask = 0x80
        return b, (ptr, mask)

    def _paths(self, idx, maxsym=400, maxdepth=600):
        symbase, tA = self.D.entry(idx)
        out = {}
        sys.setrecursionlimit(20000)

        def walk(sa, R8, path, depth):
            if depth > maxdepth or len(out) > maxsym:
                return
            a, sa = self._tree_bit(sa)
            if a == 1:
                sym = self.D.rd(symbase + R8, 1)[0]
                if sym not in out:
                    out[sym] = path
                return
            walk(sa, R8, path + (0,), depth + 1)          # b=0: continue
            sa2 = sa; R8b = R8; cnt = 0                    # b=1: count section
            for _ in range(maxdepth):
                bit, sa2 = self._tree_bit(sa2)
                if bit == 1:
                    R8b += 1; cnt -= 1
                else:
                    cnt += 1
                if cnt < 0:
                    break
            walk(sa2, R8b, path + (1,), depth + 1)
        walk((tA, 0x80), 0, (), 0)
        return out

    def can_encode(self, idx, sym):
        if idx not in self._cache:
            self._cache[idx] = self._paths(idx)
        return sym in self._cache[idx]

    def encode_symbols(self, syms, idx0=0):
        """심볼(바이트) 리스트 → 비트리스트. 인코딩 불가시 (None, (idx,sym)) 반환."""
        bits = []; idx = idx0
        for sym in syms:
            if idx not in self._cache:
                self._cache[idx] = self._paths(idx)
            e = self._cache[idx]
            if sym not in e:
                return None, (idx, sym)
            bits += list(e[sym]); idx = sym
        return bits, None

    @staticmethod
    def pack_bits(bits):
        """MSB-first 바이트 패킹(디코더 mask 0x80→0x01 순서와 일치)."""
        out = bytearray()
        for i in range(0, len(bits), 8):
            chunk = bits[i:i + 8]
            b = 0
            for j, v in enumerate(chunk):
                if v:
                    b |= (1 << (7 - j))
            out.append(b)
        return bytes(out)

    def encode_tokens(self, toks, idx0=0):
        """16비트 토큰열 → 압축 바이트. 토큰=(hi,lo) 2심볼."""
        syms = []
        for t in toks:
            syms.append((t >> 8) & 0xff); syms.append(t & 0xff)
        bits, miss = self.encode_symbols(syms, idx0)
        if bits is None:
            return None, miss
        return self.pack_bits(bits), None
