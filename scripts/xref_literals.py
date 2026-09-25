#!/usr/bin/env python3
"""1ST.BIN 전체를 선형 스캔해 MOV.L @(PC+d),Rn 리터럴 로드를 xref.
어느 명령(코드주소)이 어느 32비트 상수를 로드하는지 매핑 → 하드웨어/RAM 앵커.
사용: xref_literals.py <bin> [load_base_hex] [filter]
  filter: 'hw'(하드웨어만,기본) | 'all' | 임의 접두 hex(예 '0604')
"""
import sys, struct

def hwlabel(v):
    tbl=[(0x05C00000,0x05C80000,"VDP1_VRAM"),(0x05C80000,0x05CC0000,"VDP1_FB"),
         (0x05D00000,0x05D00040,"VDP1_reg"),(0x05E00000,0x05E80000,"VDP2_VRAM"),
         (0x05F00000,0x05F01000,"VDP2_CRAM"),(0x05F80000,0x05F80120,"VDP2_reg"),
         (0x05FE0000,0x05FE0100,"SCU/DMA"),(0x05A00000,0x05B00000,"SCSP"),
         (0x05890000,0x058A0000,"CDblk"),(0x02100000,0x02100010,"SMPC")]
    for lo,hi,l in tbl:
        if lo<=v<hi or lo+0x20000000<=v<hi+0x20000000: return l
    return ""

def main():
    path=sys.argv[1]
    base=int(sys.argv[2],16) if len(sys.argv)>2 else 0x06004000
    filt=sys.argv[3] if len(sys.argv)>3 else 'hw'
    data=open(path,'rb').read()
    rows=[]
    for i in range(0,len(data)-1,2):
        w=(data[i]<<8)|data[i+1]
        if (w>>12)==0xD:  # MOV.L @(PC+d),Rn
            n=(w>>8)&0xF; imm8=w&0xFF
            addr=base+i
            tgt=((addr+4)&~3)+imm8*4
            fo=tgt-base
            if 0<=fo<=len(data)-4:
                v=struct.unpack('>I',data[fo:fo+4])[0]
                lab=hwlabel(v)
                keep = (filt=='all') or (filt=='hw' and lab) or \
                       (filt not in('all','hw') and f"{v:08X}".startswith(filt.upper()))
                if keep: rows.append((addr,n,v,lab))
    print(f"{path} base=0x{base:08X}: MOV.L 리터럴 로드 {len(rows)}건 (filter={filt})\n")
    for addr,n,v,lab in rows:
        print(f"  {addr:08X}  R{n:<2} <= 0x{v:08X}  {lab}")

if __name__=='__main__':
    main()
