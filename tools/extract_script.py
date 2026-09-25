#!/usr/bin/env python3
"""
Shining the Holy Ark — 스크립트 추출기 (2026-07-11 완성).
메시지 구조: 블록(table2_flat[msgid_hi]) → 바이트정렬 길이프리픽스 레코드 [len:1][data:len].
각 레코드 = 한 텍스트박스, idx=0/mask=0x80으로 order-1 Huffman 독립 디코드(tools/decompress.py).
종료 토큰 0x0008(대기)/0x0007(대기없음). 이후 0x0000/공백은 패딩.

seek 함수(HWRAM 0x0606cb84): idx=0,mask=0x80 리셋; R3=table2_flat[msgid_hi];
  msgid_lo개 레코드 스킵(R3 += len+1); srcptr = R3+1(선택 레코드 data).
table2_flat = [0x218008]의 4바이트 포인터 배열(=table2 @0x228044를 flat하게).

⚠️ 한자 인덱스(0x100+): glyph_table_confirmed.txt에 있는 것만 문자화, 나머지는 [xxx].
   (한자 index→char 전체표는 폰트 추출 후 확장 — docs/04 미해결4)
⚠️ 입력=LWRAM(base 0x200000), 스냅샷은 swap16 → de-swap 필수(parse_state.py).
"""
import sys, struct, importlib.util, os

_here=os.path.dirname(__file__)
spec=importlib.util.spec_from_file_location("decompress",os.path.join(_here,"decompress.py"))
_dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(_dc)

def load_glyphs(path):
    GT={}
    for L in open(path,encoding='utf-8'):
        if L.startswith('0x'):
            k,v=L.split(':'); GT[int(k,16)]=v.strip()
    return GT
DK={'か':'が','き':'ぎ','く':'ぐ','け':'げ','こ':'ご','さ':'ざ','し':'じ','す':'ず','せ':'ぜ','そ':'ぞ',
 'た':'だ','ち':'ぢ','つ':'づ','て':'で','と':'ど','は':'ば','ひ':'び','ふ':'ぶ','へ':'べ','ほ':'ぼ',
 'カ':'ガ','キ':'ギ','ク':'グ','ケ':'ゲ','コ':'ゴ','サ':'ザ','シ':'ジ','ス':'ズ','セ':'ゼ','ソ':'ゾ',
 'タ':'ダ','チ':'ヂ','ツ':'ヅ','テ':'デ','ト':'ド','ハ':'バ','ヒ':'ビ','フ':'ブ','ヘ':'ベ','ホ':'ボ',
 'ウ':'ゔ'}
CTRL={0x03:'\n',0x20:'　',0x08:'',0x07:'',0x00:''}
def render(toks, GT):
    o=[]
    for t in toks:
        if t in (0x08,0x07,0x00): break   # 텍스트 종료
        if t==0x03: o.append('\n'); continue
        if t==0x20: o.append('　'); continue
        if t==0xde:
            if o and o[-1] in DK: o[-1]=DK[o[-1]]
            else: o.append('゛')
            continue
        o.append(GT.get(t, f'[{t:03x}]'))
    return ''.join(o)

class Script:
    def __init__(self, lwram, glyph_path, base=0x200000):
        self.d=_dc.Decompressor(lwram, base); self.lw=lwram; self.base=base
        self.GT=load_glyphs(glyph_path)
        self.tbl2_flat=self.d.be32(0x218008)  # 0x228044
    def rd(self,a,n): o=a-self.base; return self.lw[o:o+n]
    def block_base(self, hi): return self.d.be32(self.tbl2_flat + hi*4)
    def decode_record(self, data, end):
        sb=self.d.bits(data,0x80); idx=0; toks=[]
        while sb.ptr<end and len(toks)<300:
            hi=self.d.decode_byte(idx,sb); idx=hi
            lo=self.d.decode_byte(idx,sb); idx=lo
            t=(hi<<8)|lo; toks.append(t)
            if t in (0x0007,0x0008): break
        return toks
    def records(self, hi, maxbytes=0x2000):
        base=self.block_base(hi)
        if not (self.base<=base<self.base+len(self.lw)): return
        p=base
        while p-base<maxbytes:
            ln=self.rd(p,1)[0]
            if ln==0: break
            data=p+1; end=p+1+ln
            toks=self.decode_record(data,end)
            yield p, ln, toks
            p=end

if __name__=='__main__':
    lw=open(sys.argv[1],'rb').read()
    gp=sys.argv[2] if len(sys.argv)>2 else os.path.join(_here,'..','docs','glyph_table_confirmed.txt')
    hi=int(sys.argv[3],0) if len(sys.argv)>3 else 6
    s=Script(lw,gp)
    print(f"block hi={hi} base=0x{s.block_base(hi):x}")
    for off,ln,toks in s.records(hi):
        txt=render(toks,s.GT).replace('\n','\\n')
        print(f" @0x{off:x} len={ln:2d}: {txt}")
