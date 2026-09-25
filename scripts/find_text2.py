import collections
snaps = {i: open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)}

def triple_word_positions(data):
    # map value -> list of positions where VVV occurs (V nonzero 2-byte)
    d=collections.defaultdict(list)
    n=len(data)-6
    for i in range(0,n,2):
        w0=data[i:i+2]
        if w0==b'\x00\x00': continue
        if data[i+2:i+4]==w0 and data[i+4:i+6]==w0:
            d[w0].append(i)
    return d

tp={i:triple_word_positions(snaps[i]) for i in range(4)}
# candidate ・ code: present in s0,s1,s2 ; count relatively low
cands=[]
for v,pos0 in tp[0].items():
    if v in tp[1] and v in tp[2]:
        c0,c1,c2 = len(pos0),len(tp[1][v]),len(tp[2].get(v,[]))
        c3 = len(tp[3].get(v,[]))
        # prefer moderate counts
        if c0<200 and c1<200 and c2<200:
            cands.append((c0+c1+c2, v.hex(), c0,c1,c2,c3))
cands.sort()
print("val  s0 s1 s2 s3")
for tot,vh,c0,c1,c2,c3 in cands[:40]:
    print(vh, c0,c1,c2,c3)

print("\n=== c3==0 (triple in s0,s1,s2 but NOT s3) ===")
for v,pos0 in tp[0].items():
    if v in tp[1] and v in tp[2] and v not in tp[3]:
        print(v.hex(), len(pos0), len(tp[1][v]), len(tp[2][v]),
              "pos0=",[hex(p) for p in pos0[:5]])
