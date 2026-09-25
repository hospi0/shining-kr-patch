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
DK={'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご','さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ','た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど','は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ','カ':'ガ','サ':'ザ','タ':'ダ','ハ':'バ','ヒ':'ビ','フ':'ブ','ケ':'ゲ'}
def tok2s(t): return {0x03:'/',0x20:'　',0x08:'■',0x00:'0',0xde:'゛'}.get(t,GT.get(t,f'[{t:03x}]'))
def render(toks):
    o=[]
    for t in toks:
        c=tok2s(t)
        if c=='゛' and o and o[-1] in DK: o[-1]=DK[o[-1]]
        else: o.append(c)
    return ''.join(o)
def decode_record(ptr):  # byte-aligned, idx=0, mask=0x80
    sb=d.bits(ptr,0x80); idx=0; toks=[]
    for _ in range(120):
        hi=d.decode_byte(idx,sb);idx=hi; lo=d.decode_byte(idx,sb);idx=lo
        t=(hi<<8)|lo; toks.append(t)
        if t==0x0008: break
    return toks

# parse length-prefixed records from block base 0x225b2c
base=0x225b2c
p=base
print(f"length-prefixed records from 0x{base:x}:")
for i in range(30):
    ln=rd(p,1)[0]
    data=p+1
    toks=decode_record(data)
    print(f" rec{i:2d} @0x{p:x} len={ln:3d} data=0x{data:x}: {render(toks)[:46]}")
    p+=ln+1
    if p-base>0x400: break
