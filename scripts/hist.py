snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
LB=0x47F3CA
lw=deswap(snaps[0][LB:LB+0x100000])
import collections
reg=lw[0x25000:0x27000]
h=collections.Counter(reg)
distinct=len(h)
print(f"region 0x225000-0x227000: {len(reg)}B, {distinct} distinct byte values")
top=h.most_common(12)
print("top:",[(hex(b),c) for b,c in top])
# entropy
import math
tot=len(reg); ent=-sum((c/tot)*math.log2(c/tot) for c in h.values())
print(f"entropy={ent:.2f} bits/byte (8=random)")
# compare: X2SAMPLE.MES area 0x218000
reg2=lw[0x18000:0x1a000]
h2=collections.Counter(reg2); ent2=-sum((c/len(reg2))*math.log2(c/len(reg2)) for c in h2.values())
print(f"\n0x218000 area: {len(h2)} distinct, entropy={ent2:.2f}")
print("first 64B @0x218000:",' '.join(f'{b:02x}' for b in lw[0x18000:0x18040]))
