#!/usr/bin/env python3
"""한글 이름입력 디스크 빌드 검증: xdelta 적용본에서
  (1) X02.BIN 그리드 테이블 = 한글 반절표
  (2) 맵(M511) 폰트 슬롯에 완성형 글리프
사용: verify_names.py shining_kr_names.xdelta
"""
import sys, os, shutil, subprocess, importlib.util

_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


bdp = _L("build_disk_patch")
nk = _L("name_kr")
sys.path.insert(0, os.path.join(_here, '..', 'scripts'))
from survey_iso import get_iso_files  # noqa


def rd(f, lba, foff, n):
    out = b''
    while len(out) < n:
        bo = bdp.file_to_bin(lba, foff + len(out))
        room = bdp.USER - ((foff + len(out)) % bdp.USER)
        f.seek(bo); out += f.read(min(room, n - len(out)))
    return out


def main():
    xd = sys.argv[1]
    tmp = os.path.join(_here, '..', 'build', 'verify.bin')
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    subprocess.run([bdp.XDELTA, '-f', '-d', '-s', bdp.DISC, xd, tmp], check=True)
    with open(tmp, 'rb') as f:
        files = get_iso_files(f)
        n2 = {k.rsplit('/', 1)[-1].upper(): v for k, v in files.items()}
        # (1) X02 grid table
        lba, _ = n2['X02.BIN']
        gt = rd(f, lba, 0x14638, 108)
        want = nk.grid_table()
        print("X02 그리드:", "OK" if gt == want else "MISMATCH")
        print("  first15:", gt[:15].hex(), "| want", want[:15].hex())
        # (2) M511 font slot for '가' (nk.SLOTS[0])
        lba, _ = n2['M511.MDX']
        slot = nk.SLOTS[0]
        g = rd(f, lba, 0x80c + (slot - 0x20) * 32, 32)
        want_g = nk.glyph_for_syllable('가')
        print("M511 슬롯 0x%02x(가):" % slot, "OK" if g == want_g else "MISMATCH")
        print("  got :", g[:8].hex())
        print("  want:", want_g[:8].hex())
    os.remove(tmp)


if __name__ == '__main__':
    main()
