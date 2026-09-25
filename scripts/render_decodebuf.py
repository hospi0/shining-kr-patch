#!/usr/bin/env python3
"""크래시 스냅샷의 디코드버퍼(0x0607b390) 토큰을 그 씬 글리프표로 렌더.
크래시 순간 어느 레코드를 그리고 있었는지 눈으로 확인하기 위한 도구.
사용: render_decodebuf.py snap.bin out.png [addr=0607b390] [count=96]
"""
import sys, struct, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font as F
from PIL import Image
from snapmem import Snap

def main():
    sn = Snap(sys.argv[1])
    out = sys.argv[2]
    addr = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x0607B390
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 96

    gbase = struct.unpack('>I', sn.read(0x00218000, 4))[0]
    print(f'글리프표 base = 0x{gbase:08X}')

    toks = [struct.unpack('>H', sn.read(addr + i*2, 2))[0] for i in range(n)]
    print('토큰:', ' '.join(f'{t:04x}' for t in toks))

    CW, CH, PAD = 17, 17, 2
    lines, cur = [], []
    for t in toks:
        if t == 0x0003:            # 줄바꿈
            lines.append(cur); cur = []
        elif t in (0x0004, 0x0005, 0x0006, 0x0007, 0x0008):
            lines.append(cur + [('CTL', t)]); cur = []
        elif t == 0x0000:
            lines.append(cur + [('END', t)]); cur = []
        else:
            cur.append(('G', t))
    if cur:
        lines.append(cur)
    W = max(len(l) for l in lines) * CW + PAD*2
    H = len(lines) * CH + PAD*2
    img = Image.new('RGB', (W, H), (20, 20, 30))
    px = img.load()
    for ly, line in enumerate(lines):
        for lx, (kind, t) in enumerate(line):
            ox, oy = PAD + lx*CW, PAD + ly*CH
            if kind != 'G':
                for y in range(15):
                    for x in range(3):
                        px[ox+x, oy+y] = (200, 60, 60)
                continue
            try:
                ent = sn.read(gbase + (t - 0x20) * 32, 32)
            except ValueError:
                continue
            w, rows = F.decode_glyph(ent)
            for y, row in enumerate(rows):
                for x, v in enumerate(row):
                    if v:
                        px[ox+x, oy+y] = (240, 240, 240)
    img = img.resize((W*2, H*2), Image.NEAREST)
    img.save(out)
    print(f'{out} 저장 ({len(lines)}줄)')

if __name__ == '__main__':
    main()
