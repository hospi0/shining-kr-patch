import struct
snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
HB=0x57F3D7
hw=deswap(snaps[0][HB:HB+0x100000])  # HWRAM base 0x6000000
# search for literal constants 0x0607bb94, 0x0607b390, 0x0607b388 (as 4-byte BE, since deswapped)
targets={'srcptr@0x0607bb94':0x0607bb94,'decbuf@0x0607b390':0x0607b390,
         'decbuf_hdr@0x0607b388':0x0607b388,'srcptr_slot':0x0607bb90}
for name,val in targets.items():
    vb=struct.pack('>I',val)
    hits=[i for i in range(0,len(hw)-4,2) if hw[i:i+4]==vb]
    # also allow near values (pool constants often exact)
    print(f"{name} (0x{val:08x}): {len(hits)} exact refs -> "+', '.join(f'0x{0x6000000+h:08x}' for h in hits[:12]))
