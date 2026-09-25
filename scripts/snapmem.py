#!/usr/bin/env python3
"""스냅샷에서 새턴 주소공간을 읽는다 (WRAM High/Low 자체 디스왑).
HWRAM(0x06000000) = snap 0x57F3D7, LWRAM(0x00200000) = snap 0x47F3CA, 각 1MB, swap16 저장.
사용: snapmem.py snap.bin ADDR LEN [--dis|--str]
"""
import sys

HI_OFF, LO_OFF = 0x57F3D7, 0x47F3CA
SIZE = 0x100000

def swap16(b):
    a = bytearray(b)
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)

class Snap:
    def __init__(self, path):
        s = open(path, 'rb').read()
        self.hi = swap16(s[HI_OFF:HI_OFF+SIZE])   # 0x06000000
        self.lo = swap16(s[LO_OFF:LO_OFF+SIZE])   # 0x00200000
        self.raw = s

    def read(self, addr, n):
        a = addr & 0x0FFFFFFF
        if 0x06000000 <= a < 0x06100000:
            o = a - 0x06000000
            return self.hi[o:o+n]
        if 0x00200000 <= a < 0x00300000:
            o = a - 0x00200000
            return self.lo[o:o+n]
        raise ValueError(f'주소 0x{addr:08X} 미지원')

if __name__ == '__main__':
    sn = Snap(sys.argv[1])
    addr = int(sys.argv[2], 16)
    n = int(sys.argv[3], 0)
    data = sn.read(addr, n)
    mode = sys.argv[4] if len(sys.argv) > 4 else '--hex'
    if mode == '--str':
        cur, start = b'', 0
        for i, c in enumerate(data):
            if 0x20 <= c < 0x7F:
                if not cur:
                    start = i
                cur += bytes([c])
            else:
                if len(cur) >= 3:
                    print(f'0x{addr+start:08X}  {cur.decode()}')
                cur = b''
        if len(cur) >= 3:
            print(f'0x{addr+start:08X}  {cur.decode()}')
    else:
        for i in range(0, len(data), 16):
            row = data[i:i+16]
            asc = ''.join(chr(c) if 0x20 <= c < 0x7F else '.' for c in row)
            print(f'0x{addr+i:08X}  {row.hex(" ")}  {asc}')
