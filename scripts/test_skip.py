import importlib.util
spec=importlib.util.spec_from_file_location("dc","tools/decompress.py")
dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
lw=open('extract/state2/lwram_s0.bin','rb').read()
d=dc.Decompressor(lw)
GT={}
for L in open('docs/glyph_table_confirmed.txt',encoding='utf-8'):
    if L.startswith('0x'):
        k,v=L.split(':'); GT[int(k,16)]=v.strip()
DK={'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご','さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ','た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど','は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ','カ':'ガ','サ':'ザ','タ':'ダ','ハ':'バ','ヒ':'ビ','フ':'ブ'}
def tok2s(t):
    return {0x03:'\n',0x20:'　',0x08:'⟨END⟩',0x00:'⟨0⟩',0xde:'゛'}.get(t, GT.get(t,f'[{t:03x}]'))
def render(toks):
    o=[]
    for t in toks:
        c=tok2s(t)
        if c=='゛' and o and o[-1] in DK: o[-1]=DK[o[-1]]
        else: o.append(c)
    return ''.join(o)
def adv(mask,n):
    ptrd=0
    for _ in range(n):
        mask>>=1
        if mask==0: mask=0x80; ptrd+=1
    return ptrd,mask
def decode_msg(ptr,mask):
    sb=d.bits(ptr,mask); idx=0; toks=[]
    for _ in range(60):
        hi=d.decode_byte(idx,sb);idx=hi; lo=d.decode_byte(idx,sb);idx=lo
        t=(hi<<8)|lo; toks.append(t)
        if t==0x0008: break
    return toks,sb.ptr,sb.mask

# msg2 ended at 0x225f07 m=0x20 (from prior). Try skipping 0..10 bits then decode msg3.
base_ptr,base_mask=0x225f07,0x20
for skip in range(0,11):
    pd,m=adv(base_mask,skip)
    toks,_,_=decode_msg(base_ptr+pd,m)
    txt=render(toks)
    # check if starts with 鉱山... i.e., contains 閉鎖 clean and starts sane
    print(f"skip={skip:2d} (ptr=0x{base_ptr+pd:x} m=0x{m:02x}): {txt[:40]}")
