snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
LB=0x47F3CA
lw=deswap(snaps[0][LB:LB+0x100000])  # identical across states
def A(a): return a-0x200000
# ptr values from candidate #1
ptrs=[0x225ec4,0x225ee9,0x225f07,0x225f31]
print("Region 0x225e40 .. 0x225f60:")
start=A(0x225e40); end=A(0x225f70)
for off in range(start,end,16):
    row=lw[off:off+16]
    addr=off+0x200000
    hexs=' '.join(f'{b:02x}' for b in row)
    mark=''.join('|' if (0x200000+off+k) in ptrs else ' ' for k in range(16))
    print(f"0x{addr:06x}: {hexs}")
    print(f"          {mark}")
print("\nPointer positions:",[hex(p) for p in ptrs])
