import collections
snaps = {i: open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)}

def triple_byte_positions(data):
    d=collections.defaultdict(list)
    prev=-3
    i=0; n=len(data)-3
    while i<n:
        b=data[i]
        if b!=0 and data[i+1]==b and data[i+2]==b:
            d[b].append(i)
            i+=3
        else:
            i+=1
    return d

tp={i:triple_byte_positions(snaps[i]) for i in range(4)}
print("byte-triple present in s0,s1,s2 but NOT s3:")
for v,pos0 in sorted(tp[0].items()):
    if v in tp[1] and v in tp[2] and v not in tp[3]:
        print(f"0x{v:02x}", len(pos0), len(tp[1][v]), len(tp[2][v]),
              "pos0=",[hex(p) for p in pos0[:6]])
