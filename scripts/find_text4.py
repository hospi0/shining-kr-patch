import collections
snaps = {i: open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)}

def triple_word_pos(data):
    d=collections.defaultdict(list)
    n=len(data)-6
    for i in range(0,n,2):
        w0=data[i:i+2]
        if w0==b'\x00\x00': continue
        if data[i+2:i+4]==w0 and data[i+4:i+6]==w0:
            d[w0].append(i)
    return d

tp={i:triple_word_pos(snaps[i]) for i in range(4)}
# values whose triple-position SETS are identical across all 4, count 2..12
common=[]
for v,p0 in tp[0].items():
    if v in tp[1] and v in tp[2] and v in tp[3]:
        if tp[1][v]==p0 and tp[2][v]==p0 and tp[3][v]==p0 and 2<=len(p0)<=15:
            common.append((v,p0))
print(f"{len(common)} word-values with identical triple-pos across all 4, count 2..15")
for v,p0 in common[:60]:
    print(v.hex(), len(p0), [hex(x) for x in p0])
