#!/usr/bin/env python3
"""
Shining the Holy Ark — script decompressor (order-1 context Huffman).
검증됨(2026-07-11): forest 씬 대사 스테이트 4장의 알려진 텍스트와 msg1~3 정확히 일치.

알고리즘 (런타임 디코더 HWRAM 0x0606cbd4 역공학):
- 상태: idx = 직전 출력 바이트(order-1 문맥, 초기 0). 입력 비트스트림 sb(ptr,mask, MSB-first).
- 코드북 = table1 @ [0x218004] (256 엔트리 × 8B): entry[idx] = (symbase_ptr, treeA_ptr).
- decode_byte(idx):
    symbase, treeA = entry[idx]
    sa = 트리 비트리더(treeA, mask 0x80)   # 문맥별 트리모양(파일내 고정), 매 호출 리셋
    R8 = 0
    loop:
      a = sa.bit()
      if a==1: return symbase[R8]            # leaf
      b = sb.bit()                           # 입력 비트
      if b==0: continue
      # b==1: 카운트 섹션 (트리 하강)
      cnt=0
      loop2:
        if sa.bit()==1: R8+=1; cnt-=1
        else: cnt+=1
        if cnt<0: break
    # loop2 후 main loop로 복귀
- 16비트 토큰 = decode_byte 2회(hi,lo). 토큰 인코딩은 docs/04_encoding.md.
- ⚠️ 메시지 헤더/제어코드(0x0c01 등)에 홀수바이트 프레이밍이 있어 텍스트박스 경계는 별도 분석 필요.

주의: 입력·테이블은 LWRAM(base 0x200000), 스냅샷서 swap16 저장 → de-swap 필수.
"""
import struct, sys

class Decompressor:
    def __init__(self, lwram, base=0x200000):
        self.lw = lwram; self.base = base
        self.TBL1 = self.be32(0x218004)
    def rd(self, a, n): o=a-self.base; return self.lw[o:o+n]
    def be32(self, a): return struct.unpack('>I', self.rd(a,4))[0]
    def entry(self, idx):
        a=self.TBL1+idx*8; return self.be32(a), self.be32(a+4)

    class _Bits:
        def __init__(s, owner, ptr, mask): s.o=owner; s.ptr=ptr; s.mask=mask
        def bit(s):
            b=1 if (s.o.rd(s.ptr,1)[0] & s.mask) else 0
            s.mask>>=1
            if s.mask==0: s.ptr+=1; s.mask=0x80
            return b

    def decode_byte(self, idx, sb):
        symbase, tA = self.entry(idx)
        sa = self._Bits(self, tA, 0x80); R8=0
        while True:
            if sa.bit()==1: return self.rd(symbase+R8,1)[0]
            if sb.bit()==0: continue
            cnt=0
            while True:
                if sa.bit()==1: R8+=1; cnt-=1
                else: cnt+=1
                if cnt<0: break

    def bits(self, ptr, mask=0x80): return self._Bits(self, ptr, mask)

    def decode_tokens(self, sb, maxtok=400, stop=0x0008):
        idx=0; toks=[]
        for _ in range(maxtok):
            hi=self.decode_byte(idx,sb); idx=hi
            lo=self.decode_byte(idx,sb); idx=lo
            t=(hi<<8)|lo; toks.append(t)
            if t==stop: break
        return toks

if __name__=='__main__':
    # usage: decompress.py LWRAM.bin PTR_HEX [MASK_HEX]
    lw=open(sys.argv[1],'rb').read()
    d=Decompressor(lw)
    ptr=int(sys.argv[2],16); mask=int(sys.argv[3],16) if len(sys.argv)>3 else 0x80
    sb=d.bits(ptr,mask)
    for n in range(6):
        toks=d.decode_tokens(sb)
        print(f"msg{n}: "+' '.join(f'{t:03x}' for t in toks))
