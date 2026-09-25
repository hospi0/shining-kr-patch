import struct
snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
HB=0x57F3D7
hw=[deswap(s[HB:HB+0x100000]) for s in snaps]
def A(a): return a-0x6000000
# text words start at 0x607b390 (after 16B header). grab 130 words.
start=A(0x607b390)
for si in range(4):
    ws=[struct.unpack('>H',hw[si][start+2*k:start+2*k+2])[0] for k in range(130)]
    print(f"--- s{si} ---")
    out=[]
    for w in ws:
        if w==0x0003: out.append("<NL>")
        elif w==0x0020: out.append("_")
        elif w==0x0000: out.append(".")
        else: out.append(f"{w:03x}")
    print(' '.join(out))
