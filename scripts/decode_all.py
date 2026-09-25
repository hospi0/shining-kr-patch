import struct
lw=open('extract/state2/lwram_s0.bin','rb').read()
def rd(a,n): o=a-0x200000; return lw[o:o+n]
def be32(a): return struct.unpack('>I',rd(a,4))[0]
TBL1=be32(0x218004)
def entry(idx):
    a=TBL1+idx*8; return be32(a), be32(a+4)
class Bits:
    def __init__(s,ptr,mask): s.ptr=ptr; s.mask=mask
    def bit(s):
        b=1 if (rd(s.ptr,1)[0]&s.mask) else 0
        s.mask>>=1
        if s.mask==0: s.ptr+=1; s.mask=0x80
        return b
def decode_byte(idx,sb):
    symbase,tA=entry(idx); sa=Bits(tA,0x80); R8=0
    while True:
        if sa.bit()==1: return rd(symbase+R8,1)[0]
        if sb.bit()==0: continue
        cnt=0
        while True:
            if sa.bit()==1: R8+=1; cnt-=1
            else: cnt+=1
            if cnt<0: break

# glyph table (confirmed) for pretty-print
GT={}
for line in open('docs/glyph_table_confirmed.txt',encoding='utf-8'):
    if line.startswith('0x'):
        k,v=line.split(':'); GT[int(k,16)]=v.strip()
def tok2str(t):
    if t==0x03: return '\n'
    if t==0x20: return ' '
    if t==0x08: return '⟨END⟩'
    if t==0xde: return '゛'
    return GT.get(t, f'[{t:03x}]')

def decode_msg(sb, maxtok=200):
    idx=0; toks=[]
    for _ in range(maxtok):
        hi=decode_byte(idx,sb); idx=hi
        lo=decode_byte(idx,sb); idx=lo
        t=(hi<<8)|lo; toks.append(t)
        if t==0x0008: break
    return toks

# decode line1,2,3 chained from validated start
sb=Bits(0x225ec6,0x80)
for n in range(1,6):
    toks=decode_msg(sb)
    s=''.join(tok2str(t) for t in toks)
    print(f"--- msg{n} (end ptr=0x{sb.ptr:x} m=0x{sb.mask:02x}) ---")
    print(s)

# --- combine dakuten and write to file ---
DK={'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご','さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ',
 'た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど','は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ',
 'カ':'ガ','キ':'ギ','ク':'グ','ケ':'ゲ','コ':'ゴ','サ':'ザ','シ':'ジ','ス':'ズ','セ':'ゼ','ソ':'ゾ',
 'タ':'ダ','チ':'ヂ','ツ':'ヅ','テ':'デ','ト':'ド','ハ':'バ','ヒ':'ビ','フ':'ブ','ヘ':'ベ','ホ':'ボ'}
def render(toks):
    out=[]
    for t in toks:
        c=tok2str(t)
        if c=='゛' and out and out[-1] in DK: out[-1]=DK[out[-1]]
        else: out.append(c)
    return ''.join(out)
sb=Bits(0x225ec6,0x80)
with open('extract/state2/decoded_msgs.txt','w',encoding='utf-8') as f:
    for n in range(1,9):
        toks=decode_msg(sb)
        f.write(f"--- msg{n} (end ptr=0x{sb.ptr:x} m=0x{sb.mask:02x}) ---\n")
        f.write(render(toks)+"\n\n")
print("wrote extract/state2/decoded_msgs.txt")
