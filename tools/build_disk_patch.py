#!/usr/bin/env python3
"""
디스크 패치 빌더 (2026-07-13) — 세이브스테이트가 아닌 **영구 디스크 패치(xdelta)**.

검증된 구조 (state28 실기 통과):
  1) X2SAMPLE.MES  : 고정폰트 글리프 슬롯을 한글 비트맵으로 교체 (file off 0xC+(idx-0x20)*32).
                     → 부팅 시 0x00218000에 로드되어 글리프표가 곧 한글. **런타임 글리프주입 불필요**
                       (런타임 주입은 크래시 유발 — 폐기).
  2) X07.BIN       : 마지막 섹터 패딩(제로)에 훅 코드 배치. X07은 0x0609D000 로드 & forest 상주 확인.
                     디렉토리 size만 키워 훅까지 로드되게 함(섹터수 불변 → 파일 시프트 없음).
  3) X02.BIN       : 메시지렌더의 DECODE 리터럴 3개(0x7a94/0x7b24/0x8994)를 훅 주소로 리다이렉트.
  4) 수정 섹터 EDC/ECC 재계산(Mode1) → xdelta.

전부 섹터 내 바이트패치라 ISO 재구성 불필요.
"""
import struct, sys, os, shutil, subprocess, importlib.util

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, '..', 'scripts'))
from survey_iso import get_iso_files, sec_off, SECTOR, USER, HDR  # noqa

_spec = importlib.util.spec_from_file_location(
    "cdrom_ecc", r"C:\claude\project\terra-kr-patch\tools\cdrom_ecc.py")
ECC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ECC)

DISC = r"F:\hospi\roms\ss roms\Shining the Holy Ark (Japan) (3M)\patch\Shining the Holy Ark (Japan) (3M) (Track 1).bin"
XDELTA = r"C:\claude\utils\xdelta.exe"

HOOK_ADDR = 0x060af120        # WRAM: X07 sector-padding (검증됨 state28)
X07_LOAD = 0x0609D000
X2S_LOAD = 0x00218000
GLYPH_TBL_FOFF = 0xC          # X2SAMPLE.MES 내 글리프테이블 시작 (= [0]값 - 0x218000)
LIT_OFFS = (0x7a94, 0x7b24, 0x8994)   # X02.BIN 내 DECODE 리터럴 3개


def file_to_bin(lba, foff):
    """파일 내 오프셋 → BIN 절대 오프셋 (2352/2048 Mode1)."""
    return sec_off(lba + foff // USER) + (foff % USER)


def write_file_bytes(f, lba, foff, data):
    """파일 오프셋에 data 기록(섹터 경계 넘김 처리). 수정된 BIN 구간 리스트 반환."""
    ranges = []
    pos = 0
    while pos < len(data):
        cur = foff + pos
        room = USER - (cur % USER)
        n = min(room, len(data) - pos)
        bo = file_to_bin(lba, cur)
        f.seek(bo); f.write(data[pos:pos + n])
        ranges.append((bo, n))
        pos += n
    return ranges


def find_dir_record(f, name):
    """루트 디렉토리에서 name의 디렉토리 레코드 BIN 오프셋을 찾음(size 필드 패치용)."""
    from survey_iso import get_root_dir, read_sectors
    root_lba, root_size = get_root_dir(f)
    data = read_sectors(f, root_lba, root_size)
    pos = 0
    while pos < len(data):
        rl = data[pos]
        if rl == 0:
            pos = (pos + USER) & ~(USER - 1)
            if pos >= len(data):
                break
            continue
        nl = data[pos + 32]
        nm = data[pos + 33:pos + 33 + nl].decode('ascii', 'replace').split(';')[0]
        if nm.upper() == name.upper():
            return file_to_bin(root_lba, pos), rl
        pos += rl
    raise SystemExit('dir record not found: ' + name)


def build(hook_bytes, glyph_block, glyph_start_idx, out_bin, out_xdelta):
    shutil.copyfile(DISC, out_bin)
    dirty = []
    with open(out_bin, 'r+b') as f:
        files = get_iso_files(f)
        def lookup(n):
            for k, v in files.items():
                if k.rsplit('/', 1)[-1].upper() == n.upper():
                    return v
            raise SystemExit('no file ' + n)
        x02_lba, x02_sz = lookup('X02.BIN')
        x07_lba, x07_sz = lookup('X07.BIN')
        x2s_lba, x2s_sz = lookup('X2SAMPLE.MES')
        print(f"X02.BIN LBA={x02_lba} size={x02_sz}")
        print(f"X07.BIN LBA={x07_lba} size={x07_sz}")
        print(f"X2SAMPLE.MES LBA={x2s_lba} size={x2s_sz}")

        # (1) 폰트: X2SAMPLE.MES + 모든 *.MDX (맵마다 폰트 사본이 있어 씬 로드 시 글리프표를 덮어씀)
        #     각 파일에서 원본 글리프 시그니처를 검색해 그 자리에 한글 블록을 기록.
        from survey_iso import read_sectors
        x2s_data = read_sectors(f, x2s_lba, x2s_sz)
        sig_off = GLYPH_TBL_FOFF + (glyph_start_idx - 0x20) * 32
        sig = x2s_data[sig_off:sig_off + 128]        # 원본 글리프 4개 = 고유 시그니처
        assert len(sig) == 128

        targets = [('X2SAMPLE.MES', x2s_lba, x2s_sz)]
        for k, (lba, sz) in sorted(files.items()):
            nm = k.rsplit('/', 1)[-1]
            if nm.upper().endswith('.MDX'):
                targets.append((nm, lba, sz))

        patched, skipped = 0, []
        for nm, lba, sz in targets:
            data = read_sectors(f, lba, sz)
            hits = []
            i = data.find(sig)
            while i >= 0:
                hits.append(i); i = data.find(sig, i + 1)
            if len(hits) != 1:
                skipped.append((nm, len(hits))); continue
            # glyph_block = pack_scene 페이로드([번역데이터][한글글리프]) — 슬롯 0x100부터 통째로
            dirty += write_file_bytes(f, lba, hits[0], glyph_block)
            patched += 1
        print(f"  [1] 폰트블록 페이로드: {patched}/{len(targets)} 파일 "
              f"({len(glyph_block)}B, 슬롯 0x{glyph_start_idx:x}~)")
        if skipped:
            print(f"      스킵({len(skipped)}): {skipped[:6]}")

        # (2) X07.BIN: 훅 코드 (섹터 패딩)
        hfoff = HOOK_ADDR - X07_LOAD
        need = hfoff + len(hook_bytes)
        secs = (x07_sz + USER - 1) // USER
        cap = secs * USER
        assert hfoff >= x07_sz, '훅이 X07 실데이터를 덮어씀!'
        assert need <= cap, f'훅이 X07 섹터용량 초과 ({need} > {cap})'
        dirty += write_file_bytes(f, x07_lba, hfoff, hook_bytes)
        print(f"  [2] X07.BIN @0x{hfoff:x} (WRAM 0x{HOOK_ADDR:08x}): {len(hook_bytes)}B 훅 "
              f"(패딩 {x07_sz}..{cap}, 여유 {cap - need}B)")

        # (2b) X07 디렉토리 size 확대 (섹터수 불변)
        new_sz = (need + 3) & ~3
        rec_off, rl = find_dir_record(f, 'X07.BIN')
        f.seek(rec_off); rec = bytearray(f.read(rl))
        old_le = struct.unpack('<I', rec[10:14])[0]
        assert old_le == x07_sz
        struct.pack_into('<I', rec, 10, new_sz)       # little-endian size
        struct.pack_into('>I', rec, 14, new_sz)       # big-endian size (both-endian 필드)
        f.seek(rec_off); f.write(rec)
        dirty.append((rec_off, rl))
        assert (new_sz + USER - 1) // USER == secs, '섹터수 변함 — 파일 시프트 발생!'
        print(f"  [2b] X07.BIN 디렉토리 size {x07_sz} -> {new_sz} (섹터수 {secs} 유지)")

        # (3) X02.BIN: DECODE 리터럴 3개 -> 훅
        for lo in LIT_OFFS:
            bo = file_to_bin(x02_lba, lo)
            f.seek(bo); cur = struct.unpack('>I', f.read(4))[0]
            assert cur == 0x0606ce88, f'literal 0x{lo:x} = 0x{cur:08x} (expect 0x0606ce88)'
            dirty += write_file_bytes(f, x02_lba, lo, struct.pack('>I', HOOK_ADDR))
        print(f"  [3] X02.BIN 리터럴 3개 (0x7a94/0x7b24/0x8994) -> 0x{HOOK_ADDR:08x}")

        # (4) EDC/ECC 재계산
        n = ECC.fix_sectors(f, dirty)
        print(f"  [4] EDC/ECC 재계산: {n} 섹터")

    subprocess.run([XDELTA, '-f', '-e', '-s', DISC, out_bin, out_xdelta], check=True)
    print(f"\nxdelta -> {out_xdelta} ({os.path.getsize(out_xdelta)} bytes)")
    return out_xdelta
