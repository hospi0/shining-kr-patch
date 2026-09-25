#!/usr/bin/env python3
"""Shining the Holy Ark (JP) — ISO 9660 파일시스템 조사.
Mode1/2352 raw BIN 기준. sec_off(lba) = lba*2352 + 16.
초기 조사 산출물: 파일 목록 + LBA/크기 + 역할 가설 단서(확장자·크기·엔트로피).
"""
import struct, sys, math, os

SECTOR = 2352
USER = 2048
HDR = 16

def sec_off(lba):
    return lba * SECTOR + HDR

def read_sectors(f, lba, size):
    buf = bytearray()
    for i in range((size + USER - 1) // USER):
        f.seek(sec_off(lba + i))
        buf += f.read(USER)
    return bytes(buf[:size])

def get_root_dir(f):
    f.seek(16 * SECTOR + HDR)
    pvd = f.read(USER)
    assert pvd[1:6] == b'CD001', 'PVD 시그니처 없음'
    root_lba = struct.unpack('<I', pvd[158:162])[0]
    root_size = struct.unpack('<I', pvd[166:170])[0]
    return root_lba, root_size

def get_iso_files(f):
    files = {}
    root_lba, root_size = get_root_dir(f)
    def parse_dir(data, parent=''):
        pos = 0
        while pos < len(data):
            rl = data[pos]
            if rl == 0:
                pos = (pos + USER) & ~(USER - 1)
                if pos >= len(data): break
                continue
            if pos + rl > len(data): break
            lba = struct.unpack('<I', data[pos+2:pos+6])[0]
            sz = struct.unpack('<I', data[pos+10:pos+14])[0]
            flags = data[pos+25]
            nl = data[pos+32]
            name = data[pos+33:pos+33+nl].decode('ascii', 'replace')
            if name not in ('', '\x00', '\x01'):
                clean = name.split(';')[0]
                if flags & 2:
                    parse_dir(read_sectors(f, lba, sz), parent + clean + '/')
                else:
                    files[parent + clean] = (lba, sz)
            pos += rl
    parse_dir(read_sectors(f, root_lba, root_size))
    return files

def entropy(b):
    if not b: return 0.0
    from collections import Counter
    c = Counter(b); n = len(b)
    return -sum((v/n) * math.log2(v/n) for v in c.values())

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r"C:\claude\ss\Shining the Holy Ark (Japan) (3M)\Shining the Holy Ark (Japan) (3M) (Track 1).bin"
    with open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        total_sectors = f.tell() // SECTOR
        files = get_iso_files(f)
        rows = []
        for name, (lba, sz) in sorted(files.items(), key=lambda kv: kv[1][0]):
            head = read_sectors(f, lba, min(sz, 2048)) if sz else b''
            ent = entropy(head[:2048])
            rows.append((name, lba, sz, ent, head[:8]))
    print(f"총 섹터 {total_sectors}, 파일 {len(files)}개\n")
    print(f"{'파일명':32} {'LBA':>7} {'크기':>10} {'ent':>5}  선두8B")
    for name, lba, sz, ent, head in rows:
        print(f"{name:32} {lba:7} {sz:10} {ent:5.2f}  {head.hex()}")
    # 확장자별 집계
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0])
    for name, (lba, sz) in files.items():
        ext = name.rsplit('.', 1)[-1] if '.' in name else '(none)'
        agg[ext][0] += 1; agg[ext][1] += sz
    print("\n=== 확장자별 ===")
    for ext, (cnt, tot) in sorted(agg.items(), key=lambda kv: -kv[1][1]):
        print(f"  .{ext:8} {cnt:4}개  {tot:12,}B")

if __name__ == '__main__':
    main()
