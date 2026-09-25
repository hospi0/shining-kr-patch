#!/usr/bin/env python3
"""
훅 v3 (2026-07-12) — 디스크 패치용. 토큰치환 + **런타임 한글 글리프 주입**.
v2(build_hook_state truncation)에 추가: 매치 시 한글 글리프 블록을 글리프표에 memcpy.
  (디스크 부팅은 메시지컴파일러가 JP글리프로 글리프표를 빌드 → 훅이 한글비트맵을 직접 써야 함.)

글리프표 dst = [0x00218000]값(=glyph_base) + (START_IDX-0x20)*32.  한글 idx는 연속(START_IDX..)이라 블록복사.
데이터: 훅코드 + 리터럴풀 + 번역테이블([jp_hash:4][kr_ptr:4]…0) + 한글토큰배열들 + 한글글리프블록.

빌드: build(entries, glyph_block, start_idx, hbase) -> (bytes, meta).
  entries=[(jp_hash, [kr tokens...ending 0x08]) ...]; glyph_block=32B*N (idx START_IDX..).
세이브스테이트 주입 검증은 inject_state()로.
"""
import struct, zlib, sys, os

DECODE = 0x0606ce88
BUF = 0x0607b390
GBASE_PTR = 0x00218000   # [여기]=glyph_base


def build(entries, glyph_block, start_idx, hbase, inject=True, table_addr=None,
          table_indirect=False):
    """table_addr 지정 시: 번역테이블을 훅 내부가 아닌 **외부 고정주소**에서 읽는다.
    table_indirect=True 면 table_addr는 **테이블 주소가 든 포인터의 주소**(간접) — 훅이
    [table_addr]를 읽어 실제 테이블로 감(맵마다 테이블 위치가 다를 때). 훅 = 코드+풀만."""
    prog = []

    def emit(word=None, br=None, lit=None, label=None):
        prog.append({'w': word, 'br': br, 'lit': lit, 'label': label})

    glyph_dst_off = (start_idx - 0x20) * 32
    glyph_words = len(glyph_block) // 4   # long count

    emit(word=0x4f22)                          # sts.l pr,@-r15
    emit(lit=(1, DECODE)); emit(word=0x410b); emit(word=0x0009)  # jsr DECODE
    for rn in range(8):
        emit(word=0x2f06 | (rn << 4))          # push r0..r7
    # hash loop
    emit(lit=(5, BUF)); emit(word=0xe600); emit(word=0xe760)     # r5=BUF r6=0 r7=0x60
    emit(label='hashloop', word=0x6051)        # mov.w @r5,r0
    emit(word=0x7502); emit(word=0x600d)       # add #2,r5; extu.w r0,r0
    emit(word=0xe108); emit(word=0x3010); emit(br=('bt', 'dolookup'))   # ==8?
    emit(word=0xe104); emit(word=0x3010); emit(br=('bt', 'dolookup'))   # ==4?
    emit(word=0x6163); emit(word=0x4608); emit(word=0x4608); emit(word=0x4600)  # hash*33
    emit(word=0x361c); emit(word=0x360c)
    emit(word=0x77ff); emit(word=0x2778); emit(br=('bf', 'hashloop'))
    emit(br=('bra', 'done')); emit(word=0x0009)
    # lookup
    emit(label='dolookup', lit=(3, 'TABLE'))   # r3 = TABLE (또는 간접: 포인터 주소)
    if table_indirect:
        emit(word=0x6332)                      # mov.l @r3,r3  → r3 = [TABLE] = 실제 테이블
    emit(label='lookuploop', word=0x6132)      # mov.l @r3,r1
    emit(word=0x2118); emit(br=('bt', 'done'))
    emit(word=0x3160); emit(br=('bt', 'matched'))
    emit(word=0x7308); emit(br=('bra', 'lookuploop')); emit(word=0x0009)
    # matched: (optionally) inject glyph block; r3=table entry ptr must be PRESERVED
    if inject:
        emit(label='matched', lit=(0, GBASE_PTR))  # r0 = &glyph_base
        emit(word=0x6002)                      # mov.l @r0,r0  -> r0=glyph_base
        emit(lit=(1, glyph_dst_off))           # r1 = dst offset
        emit(word=0x301c)                      # add r1,r0  -> r0=dst
        emit(lit=(1, 'GLYPHDATA'))             # r1 = src
        emit(lit=(2, glyph_words))             # r2 = long count
        emit(label='gcopy', word=0x6416)       # mov.l @r1+,r4
        emit(word=0x2042)                      # mov.l r4,@r0
        emit(word=0x7004)                      # add #4,r0
        emit(word=0x4210)                      # dt r2
        emit(br=('bf', 'gcopy'))
        emit(word=0x7304)                      # add #4,r3  (-> ptr field)
    else:
        emit(label='matched', word=0x7304)     # add #4,r3  (glyph inject disabled)
    emit(word=0x6332)                          # mov.l @r3,r3  (r3=korean ptr)
    emit(lit=(1, BUF))                         # r1=dst
    emit(label='copyloop', word=0x6031)
    emit(word=0x2101); emit(word=0x7302); emit(word=0x7102); emit(word=0x600d)
    emit(word=0xe208); emit(word=0x3020); emit(br=('bt', 'truncate'))
    emit(word=0xe204); emit(word=0x3020); emit(br=('bf', 'copyloop'))
    emit(label='truncate', word=0xe000); emit(word=0x2101)   # write 0x0000
    # epilogue
    emit(label='done', word=0x67f6)
    for rn in [6, 5, 4, 3, 2, 1, 0]:
        emit(word=0x60f6 | (rn << 8))
    emit(word=0x4f26); emit(word=0x000b); emit(word=0x0009)

    # pass1 addresses
    labels = {}; addr = hbase
    for p in prog:
        if p['label']:
            labels[p['label']] = addr
        p['addr'] = addr; addr += 2
    code_end = addr
    pool_base = (code_end + 3) & ~3
    poolmap = {}; pool = []
    for p in prog:
        if p['lit']:
            _, val = p['lit']
            if val not in poolmap:
                poolmap[val] = pool_base + len(pool) * 4; pool.append(val)
    pool_end = pool_base + len(pool) * 4
    if table_addr is not None:
        # 테이블/배열/글리프는 훅 밖(LWRAM 글리프표 안). 훅 = 코드+풀만.
        TABLE = table_addr
        labels['TABLE'] = TABLE
        entries = []; glyph_block = b''
    else:
        TABLE = pool_end
    labels.setdefault('TABLE', TABLE); poolmap['TABLE'] = None
    # table + arrays + glyphdata
    tbl_addr = pool_end if table_addr is None else pool_end
    arr_area = tbl_addr + (len(entries) * 8 + 4)
    arr_ptrs = []; cur = arr_area; arrbytes = bytearray()
    for hh, arr in entries:
        arr_ptrs.append(cur)
        for t in arr:
            arrbytes += struct.pack('>H', t)
        cur += len(arr) * 2
    glyph_addr = cur
    labels['GLYPHDATA'] = glyph_addr; poolmap['GLYPHDATA'] = None
    real_pool = []
    for v in pool:
        if v == 'TABLE':
            real_pool.append(TABLE)
        elif v == 'GLYPHDATA':
            real_pool.append(glyph_addr)
        else:
            real_pool.append(v)
    tblbytes = bytearray()
    for (hh, arr), ptr in zip(entries, arr_ptrs):
        tblbytes += struct.pack('>I', hh) + struct.pack('>I', ptr)
    tblbytes += struct.pack('>I', 0)

    # pass2 emit
    out = bytearray()
    for p in prog:
        at = p['addr']
        if p['w'] is not None:
            word = p['w']
        elif p['lit']:
            rn, val = p['lit']
            la = poolmap[val] if val not in ('TABLE', 'GLYPHDATA') else (TABLE if val == 'TABLE' else glyph_addr)
            # locate pool addr
            la = None
            for i, pv in enumerate(pool):
                if pv == val:
                    la = pool_base + i * 4; break
            disp = (la - ((at & ~3) + 4)) // 4
            assert 0 <= disp < 256, (val, disp)
            word = 0xd000 | (rn << 8) | (disp & 0xff)
        elif p['br']:
            kind, tgt = p['br']; dd = (labels[tgt] - (at + 4)) // 2
            if kind == 'bra':
                assert -2048 <= dd < 2048; word = 0xa000 | (dd & 0xfff)
            elif kind == 'bt':
                assert -128 <= dd < 128, (tgt, dd); word = 0x8900 | (dd & 0xff)
            elif kind == 'bf':
                assert -128 <= dd < 128, (tgt, dd); word = 0x8b00 | (dd & 0xff)
        out += struct.pack('>H', word)
    while len(out) < (pool_base - hbase):
        out += b'\x00\x00'
    for v in real_pool:
        out += struct.pack('>I', v)
    out += tblbytes + arrbytes + glyph_block
    meta = {'size': len(out), 'table': TABLE, 'arr_ptrs': arr_ptrs, 'glyph_addr': glyph_addr,
            'end': hbase + len(out), 'code_end': code_end}
    return bytes(out), meta


if __name__ == '__main__':
    # self-test assemble only
    import json
    glyphs = open(sys.argv[1], 'rb').read() if len(sys.argv) > 1 else b'\0' * 608
    ents = [(0x193fe56a, [0x100, 0x101, 0x0008])]
    hb = 0x060af120
    b, meta = build(ents, glyphs, 0x100, hb)
    print('hook v3 size', meta['size'], 'end', hex(meta['end']))
    print('code_end', hex(meta['code_end']), 'table', hex(meta['table']), 'glyph', hex(meta['glyph_addr']))
