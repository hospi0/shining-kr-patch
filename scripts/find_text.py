import sys

snaps = {i: open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)}

def swap16(b):
    b = bytearray(b)
    b[0:len(b)&~1:2], b[1:len(b)&~1:2] = b[1:len(b)&~1:2], b[0:len(b)&~1:2]
    return bytes(b)

# Find runs of 3 consecutive equal 16-bit words (candidate for ・・・ if 2-byte enc)
def find_triple_word(data):
    res=[]
    n=len(data)-6
    for i in range(0,n,2):
        w0=data[i:i+2]
        if w0==b'\x00\x00': continue
        if data[i+2:i+4]==w0 and data[i+4:i+6]==w0:
            res.append(i)
    return res

# Find runs of 3 consecutive equal bytes (candidate if 1-byte enc), nonzero
def find_triple_byte(data):
    res=[]
    for i in range(len(data)-3):
        b=data[i]
        if b==0: continue
        if data[i+1]==b and data[i+2]==b:
            res.append(i)
    return res

for i in range(4):
    d=snaps[i]
    # search only in WRAM-plausible region; but do whole thing for word-triples (cheap enough? 6.8M/2=3.4M iters)
    tw=find_triple_word(d)
    print(f's{i}: triple-word count={len(tw)}')

