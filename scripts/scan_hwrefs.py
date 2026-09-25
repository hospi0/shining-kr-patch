#!/usr/bin/env python3
"""바이너리에서 새턴 하드웨어 주소 상수(리터럴 풀)를 스캔.
BE u32가 VDP1/VDP2/CRAM/레지스터/SCU-DMA 범위에 들면 렌더·전송 코드 앵커.
사용: scan_hwrefs.py extract/1ST.BIN [load_base_hex]
"""
import sys, struct

# (lo, hi, 라벨) — 캐시통과 미러(+0x20000000)도 함께 검사
RANGES = [
    (0x05A00000, 0x05B00000, "SCSP sound"),
    (0x05C00000, 0x05C80000, "VDP1 VRAM"),
    (0x05C80000, 0x05CC0000, "VDP1 FB"),
    (0x05D00000, 0x05D00040, "VDP1 regs"),
    (0x05E00000, 0x05E80000, "VDP2 VRAM"),
    (0x05F00000, 0x05F01000, "VDP2 CRAM"),
    (0x05F80000, 0x05F80120, "VDP2 regs"),
    (0x05FE0000, 0x05FE0100, "SCU/DMA regs"),
    (0x05A00000, 0x05A00420, "SCSP regs"),
    (0x05890000, 0x058A0000, "CD block"),
    (0x02100000, 0x02100010, "SMPC/A-bus"),
]

def classify(v):
    for lo, hi, lab in RANGES:
        if lo <= v < hi: return lab
        if lo + 0x20000000 <= v < hi + 0x20000000: return lab + " (cache-thru)"
    return None

def main():
    path = sys.argv[1]
    base = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x06004000
    data = open(path, 'rb').read()
    hits = []
    for off in range(0, len(data) - 3, 4):  # 리터럴 풀은 4바이트 정렬
        v = struct.unpack('>I', data[off:off+4])[0]
        lab = classify(v)
        if lab:
            hits.append((off, v, lab))
    print(f"{path}  base=0x{base:08X}  {len(data)}B  히트 {len(hits)}개\n")
    print(f"{'파일off':>8} {'CPUaddr':>10}  {'값':>10}  하드웨어")
    for off, v, lab in hits:
        print(f"{off:8X} {base+off:10X}  {v:10X}  {lab}")
    # 라벨별 집계
    from collections import Counter
    c = Counter(l for _, _, l in hits)
    print("\n=== 하드웨어별 히트수 ===")
    for lab, n in c.most_common():
        print(f"  {lab:26} {n}")

if __name__ == '__main__':
    main()
