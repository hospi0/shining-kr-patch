#!/usr/bin/env python3
"""VRAM 블록을 4bpp 8x8 타일 그리드로 렌더(글리프 시트 육안 확인용).
사용: render_vram.py <snap.bin> <data_off_hex> <size_hex> <cols> <out.png> [bpp]
"""
import sys
from PIL import Image

def main():
    snap, off, size, cols, out = sys.argv[1], int(sys.argv[2],16), int(sys.argv[3],16), int(sys.argv[4]), sys.argv[5]
    bpp = int(sys.argv[6]) if len(sys.argv)>6 else 4
    d = open(snap,'rb').read()[off:off+size]
    tw=th=8
    bytes_per_tile = tw*th*bpp//8
    ntiles = len(d)//bytes_per_tile
    rows = (ntiles+cols-1)//cols
    img = Image.new('L',(cols*tw, rows*th),0)
    px = img.load()
    for t in range(ntiles):
        base=t*bytes_per_tile
        tx=(t%cols)*tw; ty=(t//cols)*th
        for row in range(th):
            for c in range(tw):
                if bpp==4:
                    b=d[base+row*(tw//2)+c//2]
                    v=(b>>4) if c%2==0 else (b&0xF)
                    px[tx+c,ty+row]=v*17
                else:  # 8bpp
                    v=d[base+row*tw+c]
                    px[tx+c,ty+row]=v
    img.save(out)
    print(f"{out}: {ntiles}타일 {cols}x{rows} ({img.width}x{img.height})")

if __name__=='__main__':
    main()
