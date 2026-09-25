import struct
lw=open('extract/state2/lwram_s0.bin','rb').read()  # base 0x200000
def rd(a,n): o=a-0x200000; return lw[o:o+n]
def be32(a): return struct.unpack('>I',rd(a,4))[0]
TBL1=be32(0x218004)  # 0x227844
def entry(idx):
    a=TBL1+idx*8
    return be32(a), be32(a+4)   # symbase, treeA_ptr

class Bits:
    def __init__(self, ptr, mask): self.ptr=ptr; self.mask=mask
    def bit(self):
        b = 1 if (rd(self.ptr,1)[0] & self.mask) else 0
        self.mask >>= 1
        if self.mask==0: self.ptr+=1; self.mask=0x80
        return b

def decode_byte(idx, sb):
    symbase, tA = entry(idx)
    sa = Bits(tA, 0x80)   # stream A: per-context tree bits (fresh each call)
    R8 = 0
    while True:
        a = sa.bit()
        if a==1:            # leaf
            return rd(symbase+R8,1)[0]
        b = sb.bit()        # input bit
        if b==0:
            continue
        # b==1: count section
        cnt=0
        while True:
            a2 = sa.bit()
            if a2==1: R8+=1; cnt-=1
            else: cnt+=1
            if cnt<0: break
        # back to main loop

# TEST: from s0 state decode line1 (should match s1 buffer tokens)
sb=Bits(0x225ec4, 0x40)
idx=0x00
out=[]
for _ in range(80):
    ob=decode_byte(idx, sb)
    out.append(ob)
    idx=ob
    if sb.ptr>=0x225ee9 and sb.mask<=0x40 and sb.ptr==0x225ee9: 
        pass
    if len(out)>=76: break
print("decoded bytes:")
print(' '.join(f'{b:02x}' for b in out[:76]))
# expected line1 tokens
exp=[0x0e4,0xde,0x95,0xf8,0xe3,0xde,0xa5,0xa5,0xa5,0xb5,0xda,0xe0,0xe1,0x96,0xde,0x233,0xe0,0x182,0x03,0x95,0x175,0x9c,0x96,0x20,0x1cd,0x91,0xe0,0xf7,0xe5,0x96,0x8f,0xe0,0xfc,0x99,0xe0,0xde,0xa1,0x08]
expb=[]
for t in exp: expb+=[t>>8, t&0xff]
print("\nexpected bytes:")
print(' '.join(f'{b:02x}' for b in expb))
print("\nfinal sb.ptr=0x%x mask=0x%02x (want ptr=0x225ee9 mask=0x40)"%(sb.ptr,sb.mask))
match=out[:len(expb)]==expb
print("MATCH:",match)
if not match:
    for i,(g,e) in enumerate(zip(out,expb)):
        if g!=e: print(f"  first diff at byte {i}: got {g:02x} exp {e:02x}"); break

print("\n=== brute-force start position ===")
def decode_run(ptr0,mask0,nbytes):
    sb=Bits(ptr0,mask0); idx=0; out=[]
    for _ in range(nbytes):
        ob=decode_byte(idx,sb); out.append(ob); idx=ob
    return out,sb
target=expb  # 76 bytes
for p in range(0x225ec0,0x225ec8):
    for m in [0x80,0x40,0x20,0x10,0x08,0x04,0x02,0x01]:
        out,sb=decode_run(p,m,len(target))
        if out==target:
            print(f"  EXACT MATCH start ptr=0x{p:x} mask=0x{m:02x} -> end ptr=0x{sb.ptr:x} mask=0x{sb.mask:02x}")
