#!/usr/bin/env python3
"""Mednafen 스냅샷에서 SH-2 마스터/슬레이브 레지스터 덤프.
섹션: [32B 이름][4B LE 크기] 안에 [1B 이름길이][이름][4B LE 크기][데이터] 반복.
사용: dump_regs.py snap.bin
"""
import sys, struct

def sections(snap):
    """(name, off, size) 리스트 — 'SH2-M' 같은 32B 태그를 찾아 나열."""
    out = []
    for tag in (b'SH2-M', b'SH2-S'):
        i = snap.find(tag)
        while i >= 0:
            # 32B 이름 필드인지: 이름 뒤가 널패딩이어야
            if snap[i+len(tag):i+32].strip(b'\0') == b'':
                size = struct.unpack('<I', snap[i+32:i+36])[0]
                out.append((tag.decode(), i+36, size))
                break
            i = snap.find(tag, i+1)
    return out

def variables(snap, off, size):
    end = off + size
    v = {}
    p = off
    while p < end:
        nl = snap[p]
        if nl == 0 or nl > 32 or p+1+nl+4 > end:
            break
        name = snap[p+1:p+1+nl].decode('latin1')
        p += 1 + nl
        sz = struct.unpack('<I', snap[p:p+4])[0]
        p += 4
        if sz > end - p:
            break
        v[name] = snap[p:p+sz]
        p += sz
    return v

def main():
    snap = open(sys.argv[1], 'rb').read()
    for name, off, size in sections(snap):
        print(f'=== {name} @0x{off-36:X} size=0x{size:X}')
        v = variables(snap, off, size)
        def u32(b, i=0):
            return struct.unpack('<I', b[i*4:i*4+4])[0]
        for k in sorted(v):
            b = v[k]
            if len(b) == 4:
                print(f'  {k:12} = 0x{u32(b):08X}')
            elif len(b) in (12, 64) :
                vals = [u32(b, i) for i in range(len(b)//4)]
                print(f'  {k:12} = ' + ' '.join(f'{x:08X}' for x in vals))
            else:
                print(f'  {k:12} ({len(b)}B) {b[:24].hex()}')

if __name__ == '__main__':
    main()
