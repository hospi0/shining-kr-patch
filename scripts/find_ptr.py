snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
import struct
HB=0x57F3D7; SZ=0x100000; base=0x6000000
hw=[deswap(s[HB:HB+SZ]) for s in snaps]

def be32(b,i): return struct.unpack('>I',b[i:i+4])[0]

# pointer ranges to accept
def inrange(v):
    return (0x00200000<=v<0x00300000) or (0x06000000<=v<0x06100000) or (0x25e40000<=v<0x25e80000)

hits=[]
for i in range(0,SZ-4,2):  # word-aligned pointers
    v=[be32(h,i) for h in hw]
    if all(inrange(x) for x in v):
        # strictly increasing and same range
        r0=v[0]>>20
        if all((x>>20)==r0 for x in v) and v[0]<v[1]<v[2]<v[3]:
            # reasonable deltas (line lengths, say 4..400)
            if all(4<=v[k+1]-v[k]<=600 for k in range(3)):
                hits.append((i,v))
print(f"{len(hits)} monotonic pointer candidates")
for i,v in hits[:60]:
    print(f"  hwram+0x{i:05x} (addr 0x{base+i:08x}): "+" ".join(f"{x:08x}" for x in v)
          +"  d="+",".join(str(v[k+1]-v[k]) for k in range(3)))
