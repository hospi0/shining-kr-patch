snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
HB=0x57F3D7
hw=[deswap(s[HB:HB+0x100000]) for s in snaps]
def A(a): return a-0x6000000
ptrs=[0x604a56e,0x604a592,0x604a5b6,0x604a5e8]
for si in range(4):
    print(f"--- state{si} ptr=0x{ptrs[si]:x} ---")
    for off in range(A(0x604a540),A(0x604a600),16):
        row=hw[si][off:off+16]
        addr=off+0x6000000
        print(f"0x{addr:07x}: "+' '.join(f'{b:02x}' for b in row))
