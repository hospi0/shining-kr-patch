import importlib.util
spec=importlib.util.spec_from_file_location("dc","tools/decompress.py")
dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
lw=open('extract/state2/lwram_s0.bin','rb').read()
d=dc.Decompressor(lw)

def decode_tokens_from(ptr,mask,idx0,ntok):
    sb=d.bits(ptr,mask); idx=idx0; toks=[]
    for _ in range(ntok):
        hi=d.decode_byte(idx,sb); idx=hi
        lo=d.decode_byte(idx,sb); idx=lo
        toks.append((hi<<8)|lo)
    return toks,sb

# known lines (tokens), dakuten as separate 0xde after base
def line_tokens(s):
    T={'　':0x20,' ':0x20,'\n':0x03,'。':0xa1,'・':0xa5,'？':0x3f}
    import json
    GT={}
    for L in open('docs/glyph_table_confirmed.txt',encoding='utf-8'):
        if L.startswith('0x'):
            k,v=L.split(':'); GT[v.strip()]=int(k,16)
    DK={'が':'か','ぎ':'き','ぐ':'く','げ':'け','ご':'こ','ざ':'さ','じ':'し','ず':'す','ぜ':'せ','ぞ':'そ','だ':'た','ぢ':'ち','づ':'つ','で':'て','ど':'と','ば':'は','び':'ひ','ぶ':'ふ','べ':'へ','ぼ':'ほ','ガ':'カ','ギ':'キ','グ':'ク','ゲ':'ケ','ゴ':'コ','ザ':'サ','ジ':'シ','ズ':'ス','ゼ':'ゼ','ゾ':'ソ','ダ':'タ','ヅ':'ツ','デ':'テ','ド':'ト','バ':'ハ','ビ':'ヒ','ブ':'フ','ベ':'ヘ','ボ':'ホ'}
    out=[]
    for ch in s:
        if ch in T: out.append(T[ch])
        elif ch in DK: 
            base=DK[ch]; out.append(GT.get(base)); out.append(0xde)
        elif ch in GT: out.append(GT[ch])
        else: out.append(None)  # kanji unknown-index
    return out

# state2 core text (skip kanji-index matching by matching only kana/control run)
# Use a distinctive kana run: "まさか・・・" then NL then "オレたち"
s2run=line_tokens("まさか・・・\nオレ")   # ef 9b 96 a5 a5 a5 03 b5 da
s3run=line_tokens("されて　た")  # after 閉鎖: さ れ て sp  ... plus dakuten
print("s2 kana run tokens:",[hex(t) if t else '?' for t in s2run])
print("s3 kana run tokens:",[hex(t) if t else '?' for t in s3run])

# brute force search: decode long stream continuous, then find run as token subsequence at various alignments
# Simpler: for each candidate (ptr,mask,idx) near snapshot, decode 60 tokens and check if run appears
def search(runtokens, ptr_lo,ptr_hi):
    run=[t for t in runtokens if t is not None]
    hits=[]
    for p in range(ptr_lo,ptr_hi):
        for m in [0x80,0x40,0x20,0x10,0x08,0x04,0x02,0x01]:
            for idx0 in (0,):
                toks,_=decode_tokens_from(p,m,idx0,70)
                # find run subsequence
                for i in range(len(toks)-len(run)):
                    if toks[i:i+len(run)]==run:
                        hits.append((p,m,idx0,i)); break
            if hits and hits[-1][0]==p: break
    return hits

print("\nstate2 run search (ptr 0x225ee0..0x225f10):")
for h in search(s2run,0x225ee0,0x225f10)[:6]:
    print(f"  start ptr=0x{h[0]:x} m=0x{h[1]:02x} idx={h[2]} -> run at token {h[3]}")
print("state3 run search (ptr 0x225f00..0x225f40):")
for h in search(s3run,0x225f00,0x225f40)[:6]:
    print(f"  start ptr=0x{h[0]:x} m=0x{h[1]:02x} idx={h[2]} -> run at token {h[3]}")
