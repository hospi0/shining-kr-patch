import importlib.util
spec=importlib.util.spec_from_file_location("dc","tools/decompress.py")
dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
lw=open('extract/state2/lwram_s0.bin','rb').read()
d=dc.Decompressor(lw)
GT={}
for L in open('docs/glyph_table_confirmed.txt',encoding='utf-8'):
    if L.startswith('0x'):
        k,v=L.split(':'); GT[int(k,16)]=v.strip()
DK={'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご','さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ','た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど','は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ','カ':'ガ','キ':'ギ','ク':'グ','ケ':'ゲ','コ':'ゴ','サ':'ザ','シ':'ジ','ス':'ズ','セ':'ゼ','ソ':'ゾ','タ':'ダ','チ':'ヂ','ツ':'ヅ','テ':'デ','ト':'ド','ハ':'バ','ヒ':'ビ','フ':'ブ','ヘ':'ベ','ホ':'ボ'}
def tok2s(t):
    if t==0x03: return '\n'
    if t==0x20: return '　'
    if t==0x08: return '⟨END⟩'
    if t==0x00: return '⟨00⟩'
    if t==0xde: return '゛'
    return GT.get(t, f'[{t:03x}]')
def render(toks):
    out=[]
    for t in toks:
        c=tok2s(t)
        if c=='゛' and out and out[-1] in DK: out[-1]=DK[out[-1]]
        else: out.append(c)
    return ''.join(out)

def decode_msg(ptr,mask):
    sb=d.bits(ptr,mask); idx=0; toks=[]
    for _ in range(200):
        hi=d.decode_byte(idx,sb); idx=hi
        lo=d.decode_byte(idx,sb); idx=lo
        t=(hi<<8)|lo; toks.append(t)
        if t==0x0008: break
    return toks, sb.ptr, sb.mask

# msg1..msgN, idx reset each, bit-contiguous
ptr,mask=0x225ec6,0x80
for n in range(1,9):
    toks,ptr,mask=decode_msg(ptr,mask)
    print(f"=== msg{n}  (end ptr=0x{ptr:x} m=0x{mask:02x}) ===")
    print("  toks:",' '.join(f'{t:03x}' for t in toks))
    print("  text:",render(toks))
