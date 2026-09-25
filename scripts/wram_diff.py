snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]

def deswap(b):
    b=bytearray(b)
    n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]
    return bytes(b)

# LWRAM 1MB @0x200000 -> snapshot ~0x47F3CA ; HWRAM 1MB @0x6000000 -> ~0x57F3D7
regions={
 'LWRAM': (0x47F3CA, 0x100000, 0x200000),
 'HWRAM': (0x57F3D7, 0x100000, 0x6000000),
}
for name,(so,sz,base) in regions.items():
    wr=[deswap(s[so:so+sz]) for s in snaps]
    # find differing byte offsets across the 4
    diffs=[]
    a,b,c,d=wr
    i=0
    while i<sz:
        if not(a[i]==b[i]==c[i]==d[i]):
            j=i
            while j<sz and not(a[j]==b[j]==c[j]==d[j]):
                j+=1
            diffs.append((i,j))
            i=j
        else:
            i+=1
    # merge close diffs (gap<16)
    merged=[]
    for s,e in diffs:
        if merged and s-merged[-1][1]<16:
            merged[-1]=(merged[-1][0],e)
        else:
            merged.append((s,e))
    print(f"=== {name}: {len(merged)} differing runs (merged gap<16) ===")
    for s,e in merged:
        if e-s>=3:  # skip tiny
            print(f"  addr 0x{base+s:08x}  len {e-s}")
