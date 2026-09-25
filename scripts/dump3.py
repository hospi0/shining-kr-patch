snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
HB=0x57F3D7
hw=[deswap(s[HB:HB+0x100000]) for s in snaps]
def A(a): return a-0x6000000
for a0,a1,label in [(0x6046940,0x60469e0,"46960/469a0 (2x48)"),
                    (0x607b380,0x607b3f0,"7b388 (90)"),
                    (0x6001dd0,0x6001e10,"1ddf (29)")]:
    print(f"===== {label} =====")
    for si in range(4):
        print(f" s{si}: "+' '.join(f'{hw[si][o]:02x}' for o in range(A(a0),A(a1))))
