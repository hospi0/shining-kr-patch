#!/usr/bin/env python3
"""ISO9660 파일을 raw로 추출. 사용: extract_file.py NAME [out_path]
NAME은 'X6MORI.BIN' 같은 파일명(대소문자 무시, ;1 생략).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from survey_iso import get_iso_files, read_sectors

DISC = r"C:\claude\ss\Shining the Holy Ark (Japan) (3M)\Shining the Holy Ark (Japan) (3M) (Track 1).bin"

def extract(name, out=None, disc=DISC):
    with open(disc, 'rb') as f:
        files = get_iso_files(f)
        key = None
        for k in files:
            if k.rsplit('/', 1)[-1].upper() == name.upper():
                key = k; break
        if key is None:
            raise SystemExit(f'파일 없음: {name}')
        lba, sz = files[key]
        data = read_sectors(f, lba, sz)
    out = out or os.path.join(os.path.dirname(__file__), '..', 'extract', name.upper())
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'wb') as g:
        g.write(data)
    print(f'{key}  LBA={lba} size={sz} -> {out}')
    return out

if __name__ == '__main__':
    extract(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
