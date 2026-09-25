#!/usr/bin/env python3
"""훅 재빌드+주입 — 렌더 truncation(0x0000 기록) 수정판.
렌더러가 0x0000에서 멈추는 것을 이용: 한글 복사 직후 0x0000을 써서 JP 잔상 제거.
s16의 짧은 배열 그대로 사용(패딩 없음=크래시 회피). 훅 코드에 mov#0,r0;mov.w r0,@r1 2명령 추가.
사용: build_hook_state.py SRC.state OUT.state
"""
import struct, zlib, sys

DECODE = 0x0606ce88
BUF = 0x0607b390
HBASE = 0x060b5a00
INSTALL_LITS = (0x0606ca94, 0x0606cb24, 0x0606d994)
S16_TABLE = 0x060b5a84


def parse(raw):
    total = struct.unpack('<Q', raw[12:20])[0]
    out = bytearray(); pos = 20
    while pos + 4 <= len(raw) and len(out) < total:
        clen = struct.unpack('<I', raw[pos:pos + 4])[0]; pos += 4
        if clen == 0 or pos + clen > len(raw):
            break
        out += zlib.decompress(raw[pos:pos + clen]); pos += clen
    return bytes(out)


def deswap(b):
    b = bytearray(b); n = len(b) & ~1
    b[0:n:2], b[1:n:2] = b[1:n:2], b[0:n:2]
    return bytes(b)


def build_hook(entries):
    base = HBASE
    prog = []

    def emit(word=None, br=None, lit=None, label=None):
        prog.append({'w': word, 'br': br, 'lit': lit, 'label': label})

    emit(word=0x4f22)                         # sts.l pr,@-r15
    emit(lit=(1, DECODE))                     # mov.l #DECODE,r1
    emit(word=0x410b)                         # jsr @r1
    emit(word=0x0009)                         # nop
    for rn in range(8):
        emit(word=0x2f06 | (rn << 4))         # mov.l r0..r7,@-r15
    emit(lit=(5, BUF))                        # mov.l #BUF,r5
    emit(word=0xe600)                         # mov #0,r6
    emit(word=0xe760)                         # mov #0x60,r7
    emit(label='hashloop', word=0x6051)       # mov.w @r5,r0
    emit(word=0x7502)                         # add #2,r5
    emit(word=0x600d)                         # extu.w r0,r0
    emit(word=0xe108)                         # mov #8,r1
    emit(word=0x3010)                         # cmp/eq r1,r0
    emit(br=('bt', 'dolookup'))
    emit(word=0xe104)                         # mov #4,r1
    emit(word=0x3010)                         # cmp/eq r1,r0
    emit(br=('bt', 'dolookup'))
    emit(word=0x6163)                         # mov r6,r1
    emit(word=0x4608)                         # shll2 r6
    emit(word=0x4608)                         # shll2 r6
    emit(word=0x4600)                         # shll r6
    emit(word=0x361c)                         # add r1,r6
    emit(word=0x360c)                         # add r0,r6
    emit(word=0x77ff)                         # add #-1,r7
    emit(word=0x2778)                         # tst r7,r7
    emit(br=('bf', 'hashloop'))
    emit(br=('bra', 'done'))
    emit(word=0x0009)                         # nop
    emit(label='dolookup', lit=(3, 'TABLE'))  # mov.l #TABLE,r3
    emit(label='lookuploop', word=0x6132)     # mov.l @r3,r1
    emit(word=0x2118)                         # tst r1,r1
    emit(br=('bt', 'done'))
    emit(word=0x3160)                         # cmp/eq r6,r1
    emit(br=('bt', 'matched'))
    emit(word=0x7308)                         # add #8,r3
    emit(br=('bra', 'lookuploop'))
    emit(word=0x0009)                         # nop
    emit(label='matched', word=0x7304)        # add #4,r3
    emit(word=0x6332)                         # mov.l @r3,r3
    emit(lit=(1, BUF))                        # mov.l #BUF,r1
    emit(label='copyloop', word=0x6031)       # mov.w @r3,r0
    emit(word=0x2101)                         # mov.w r0,@r1
    emit(word=0x7302)                         # add #2,r3
    emit(word=0x7102)                         # add #2,r1
    emit(word=0x600d)                         # extu.w r0,r0
    emit(word=0xe208)                         # mov #8,r2
    emit(word=0x3020)                         # cmp/eq r2,r0
    emit(br=('bt', 'truncate'))
    emit(word=0xe204)                         # mov #4,r2
    emit(word=0x3020)                         # cmp/eq r2,r0
    emit(br=('bf', 'copyloop'))
    emit(label='truncate', word=0xe000)       # mov #0,r0     NEW
    emit(word=0x2101)                         # mov.w r0,@r1  NEW (write 0x0000)
    emit(label='done', word=0x67f6)           # mov.l @r15+,r7
    for rn in [6, 5, 4, 3, 2, 1, 0]:
        emit(word=0x60f6 | (rn << 8))         # pop r6..r0
    emit(word=0x4f26)                         # lds.l @r15+,pr
    emit(word=0x000b)                         # rts
    emit(word=0x0009)                         # nop

    # pass1: addresses + labels
    labels = {}
    addr = base
    for p in prog:
        if p['label']:
            labels[p['label']] = addr
        p['addr'] = addr; addr += 2
    code_end = addr
    pool_base = (code_end + 3) & ~3
    # literal pool
    poolmap = {}; pool = []
    for p in prog:
        if p['lit']:
            _, val = p['lit']
            if val not in poolmap:
                poolmap[val] = pool_base + len(pool) * 4; pool.append(val)
    pool_end = pool_base + len(pool) * 4
    TABLE = pool_end
    real_pool = [TABLE if v == 'TABLE' else v for v in pool]
    labels['TABLE'] = TABLE
    poolmap_resolved = dict(poolmap)
    poolmap_resolved['TABLE'] = poolmap['TABLE']
    # table + arrays
    tbl_addr = TABLE
    arr_area = tbl_addr + (3 * 8 + 4)
    arr_ptrs = []; cur = arr_area; arrbytes = bytearray()
    for hh, arr in entries:
        arr_ptrs.append(cur)
        for t in arr:
            arrbytes += struct.pack('>H', t)
        cur += len(arr) * 2
    tblbytes = bytearray()
    for (hh, arr), ptr in zip(entries, arr_ptrs):
        tblbytes += struct.pack('>I', hh) + struct.pack('>I', ptr)
    tblbytes += struct.pack('>I', 0)

    # pass2: emit
    out = bytearray()
    for p in prog:
        at = p['addr']
        if p['w'] is not None:
            word = p['w']
        elif p['lit']:
            rn, val = p['lit']
            la = poolmap_resolved[val]; disp = (la - ((at & ~3) + 4)) // 4
            assert 0 <= disp < 256, disp
            word = 0xd000 | (rn << 8) | (disp & 0xff)
        elif p['br']:
            kind, tgt = p['br']; d = (labels[tgt] - (at + 4)) // 2
            if kind == 'bra':
                assert -2048 <= d < 2048; word = 0xa000 | (d & 0xfff)
            elif kind == 'bt':
                assert -128 <= d < 128, (tgt, d); word = 0x8900 | (d & 0xff)
            elif kind == 'bf':
                assert -128 <= d < 128, (tgt, d); word = 0x8b00 | (d & 0xff)
        out += struct.pack('>H', word)
    while len(out) < (pool_base - base):
        out += b'\x00\x00'
    for v in real_pool:
        out += struct.pack('>I', v)
    out += tblbytes + arrbytes
    return bytes(out), arr_ptrs, TABLE


def main():
    SRC, OUT = sys.argv[1], sys.argv[2]
    raw = open(SRC, 'rb').read()
    block = struct.unpack('<I', raw[8:12])[0]
    snap = bytearray(parse(raw))
    m = snap.find(b'MAIN'); HW = m + 0x105 + 0x10000D
    base = 0x6000000
    hw = bytearray(deswap(snap[HW:HW + 0x100000]))

    def L(a):
        return struct.unpack('>I', hw[a - base:a - base + 4])[0]

    def W(a):
        return struct.unpack('>H', hw[a - base:a - base + 2])[0]

    # extract s16 arrays
    entries = []
    for e in range(3):
        hh = L(S16_TABLE + e * 8); ptr = L(S16_TABLE + e * 8 + 4)
        arr = []; a = ptr
        for _ in range(60):
            t = W(a); arr.append(t); a += 2
            if t in (0x0008, 0x0004):
                break
        entries.append((hh, arr))
        print(f"box{e}: hash=0x{hh:08x} len={len(arr)} end=0x{arr[-1]:04x}")

    hook, arr_ptrs, TABLE = build_hook(entries)
    print(f"hook {len(hook)}B, ends 0x{HBASE + len(hook):08x}, TABLE=0x{TABLE:08x}, arrs={[hex(x) for x in arr_ptrs]}")

    for a in range(0x060b5a00, 0x060b6200):
        hw[a - base] = 0
    hw[HBASE - base:HBASE - base + len(hook)] = hook
    for LIT in INSTALL_LITS:
        assert L(LIT) == HBASE, hex(LIT)
    print("install literals OK")

    snap[HW:HW + 0x100000] = deswap(bytes(hw))
    outp = bytearray(raw[:20]); pp = 0
    while pp < len(snap):
        ch = bytes(snap[pp:pp + block]); comp = zlib.compress(ch, 9)
        outp += struct.pack('<I', len(comp)) + comp; pp += block
    open(OUT, 'wb').write(outp)
    print("wrote", OUT, len(outp))


if __name__ == '__main__':
    main()
