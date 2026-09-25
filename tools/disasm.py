#!/usr/bin/env python3
"""SH-2 디스어셈블 + 리터럴 풀 값 해석 래퍼 (terra sh2_disasm 코어 사용).
사용: disasm.py <bin> <file_off_hex> <n_instr> [load_base_hex]
"""
import sys, os, struct
sys.path.insert(0, r"C:\claude\project\terra-kr-patch\tools")
from sh2_disasm import disasm_sh2

def hwlabel(v):
    tbl = [(0x05C00000,0x05C80000,"VDP1_VRAM"),(0x05C80000,0x05CC0000,"VDP1_FB"),
           (0x05D00000,0x05D00040,"VDP1_reg"),(0x05E00000,0x05E80000,"VDP2_VRAM"),
           (0x05F00000,0x05F01000,"VDP2_CRAM"),(0x05F80000,0x05F80120,"VDP2_reg"),
           (0x05FE0000,0x05FE0100,"SCU/DMA"),(0x05A00000,0x05B00000,"SCSP"),
           (0x05890000,0x058A0000,"CDblk"),(0x06000000,0x06100000,"WRAM-Hi"),
           (0x00200000,0x00300000,"WRAM-Lo")]
    for lo,hi,l in tbl:
        if lo<=v<hi or lo+0x20000000<=v<hi+0x20000000: return l
    return ""

def main():
    path=sys.argv[1]; foff=int(sys.argv[2],16); n=int(sys.argv[3])
    base=int(sys.argv[4],16) if len(sys.argv)>4 else 0x06004000
    data=open(path,'rb').read()
    code=data[foff:foff+n*2+64]
    lines=disasm_sh2(code, base+foff, max_instr=n)
    for addr,w,ins in lines:
        extra=""
        # PC상대 리터럴 로드면 값 읽어서 표시
        if ';@0x' in ins:
            tgt=int(ins.split(';@0x')[1].strip(),16)
            fo=tgt-base
            if 0<=fo<=len(data)-4:
                if 'MOV.L' in ins:
                    v=struct.unpack('>I',data[fo:fo+4])[0]
                    extra=f"   => 0x{v:08X} {hwlabel(v)}"
                elif 'MOV.W' in ins:
                    v=struct.unpack('>H',data[fo:fo+2])[0]
                    sv=v-0x10000 if v>=0x8000 else v
                    extra=f"   => 0x{v:04X} ({sv})"
        print(f"{addr:08X}: {w:04X}  {ins}{extra}")

if __name__=='__main__':
    main()
