import importlib.util
spec=importlib.util.spec_from_file_location("dc","tools/decompress.py")
dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
lw=open('extract/state2/lwram_s0.bin','rb').read()
d=dc.Decompressor(lw)
def rd(a,n): o=a-0x200000; return lw[o:o+n]
GT={}
for L in open('docs/glyph_table_confirmed.txt',encoding='utf-8'):
    if L.startswith('0x'):
        k,v=L.split(':'); GT[int(k,16)]=v.strip()
DK={'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご','さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ','た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど','は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ','カ':'ガ','サ':'ザ','タ':'ダ','ハ':'バ','ヒ':'ビ','フ':'ブ','ケ':'ゲ','ウ':'ゔ'}
def tok2s(t): return {0x03:'/',0x20:'　',0x08:'■',0x00:'·',0xde:'゛'}.get(t,GT.get(t,f'[{t:03x}]'))
def render(toks):
    o=[]
    for t in toks:
        c=tok2s(t)
        if c=='゛' and o and o[-1] in DK: o[-1]=DK[o[-1]]
        else: o.append(c)
    return ''.join(o)
def decode_bounded(data,end):
    sb=d.bits(data,0x80); idx=0; toks=[]
    while sb.ptr<end and len(toks)<200:
        hi=d.decode_byte(idx,sb);idx=hi; lo=d.decode_byte(idx,sb);idx=lo
        toks.append((hi<<8)|lo)
    return toks
base=0x225b2c; p=base
i=0
while p<0x225f60:
    ln=rd(p,1)[0]; data=p+1; end=p+1+ln
    toks=decode_bounded(data,end)
    star=' <<<' if 0x225ec0<=data<=0x225f10 else ''
    print(f"rec{i:2d} @0x{p:x} len={ln:2d}: {render(toks)}{star}")
    p=end; i+=1
