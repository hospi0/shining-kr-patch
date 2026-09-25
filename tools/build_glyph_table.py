#!/usr/bin/env python3
"""
Shining the Holy Ark — 씬 글리프표 자동 생성 (2026-07-12).

핵심: 글리프 비트맵(32B)은 **씬 무관 안정 식별자**(같은 한자=같은 비트맵, 인덱스만 씬마다 다름).
따라서 식별된 글리프들의 **비트맵→문자 DB**를 만들면, 새 씬의 글리프 슬롯을 비트맵 매칭으로 자동 식별.
- 고정폰트(0x20-0x34F)는 씬 공유, 동적캐시(0x350+)는 씬마다 인덱스 다름 — 둘 다 비트맵으로 잡힘.
- DB에 없는 비트맵(처음 보는 한자)만 수작업 렌더+식별 → docs/glyph_bitmap_db.txt에 추가.

DB 포맷(docs/glyph_bitmap_db.txt): `<32B hex>\t<char>` 줄들.

사용:
  # DB 구축(기존 씬 표들에서): build_glyph_table.py builddb <base_tbl> <lwram1:tbl1> ...
  # 씬 표 자동생성: build_glyph_table.py gen <scene_lwram.bin> [db] > scene_table.txt
"""
import sys, os, struct, importlib.util

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location("font", os.path.join(_here, "font.py"))
_F = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_F)

DB_PATH = os.path.join(_here, '..', 'docs', 'glyph_bitmap_db.txt')


def glyph_base(lwram):
    return struct.unpack('>I', lwram[0x18000:0x18004])[0]


def glyph_bytes(lwram, base, idx):
    a = base + (idx - 0x20) * 32
    return lwram[a - 0x200000:a - 0x200000 + 32]


def load_table(path):
    d = {}
    for L in open(path, encoding='utf-8'):
        if L.startswith('0x'):
            k, v = L.split(':'); d[int(k, 16)] = v.strip()
    return d


def load_db(path=DB_PATH):
    db = {}
    if os.path.exists(path):
        for L in open(path, encoding='utf-8'):
            if '\t' in L:
                h, c = L.rstrip('\n').split('\t', 1)
                db[bytes.fromhex(h)] = c
    return db


def save_db(db, path=DB_PATH):
    with open(path, 'w', encoding='utf-8') as o:
        for h, c in sorted(db.items(), key=lambda x: x[1]):
            o.write('%s\t%s\n' % (h.hex(), c))


def add_table_to_db(db, lwram, table):
    """씬 lwram + 그 씬 글리프표(idx→char) → DB에 비트맵→char 추가. 빈 비트맵/충돌 스킵."""
    base = glyph_base(lwram)
    conflicts = []
    for idx, ch in table.items():
        if idx < 0x20:
            continue
        b = glyph_bytes(lwram, base, idx)
        if b == b'\x00' * 32 or len(b) < 32:
            continue
        # width word 0인 빈 글리프 스킵
        if struct.unpack('>H', b[0:2])[0] == 0 and b[2:] == b'\x00' * 30:
            continue
        if b in db and db[b] != ch:
            conflicts.append((db[b], ch)); continue
        db[b] = ch
    return conflicts


def gen_table(lwram, db):
    """씬 lwram + DB → idx→char 표. DB에 없는 글리프는 제외(미식별)."""
    base = glyph_base(lwram)
    out = {}
    unknown = []
    for idx in range(0x20, 0x400):
        b = glyph_bytes(lwram, base, idx)
        if len(b) < 32:
            continue
        w = struct.unpack('>H', b[0:2])[0]
        if w == 0 and b[2:] == b'\x00' * 30:
            continue  # 빈 슬롯
        if b in db:
            out[idx] = db[b]
        else:
            unknown.append(idx)
    return out, unknown


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'builddb':
        # builddb base.txt lwram1.bin:table1.txt lwram2.bin:table2.txt ...
        db = {}
        for arg in sys.argv[2:]:
            lwp, tp = arg.split(':')
            lw = open(lwp, 'rb').read(); tbl = load_table(tp)
            conf = add_table_to_db(db, lw, tbl)
            if conf:
                sys.stderr.write('conflicts in %s: %s\n' % (arg, conf[:5]))
        save_db(db)
        sys.stderr.write('DB entries: %d -> %s\n' % (len(db), DB_PATH))
    elif cmd == 'gen':
        import io
        lw = open(sys.argv[2], 'rb').read()
        db = load_db(sys.argv[3] if len(sys.argv) > 3 else DB_PATH)
        tbl, unk = gen_table(lw, db)
        w = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        w.write('# auto-generated scene glyph table (bitmap DB lookup). unknown=%d\n' % len(unk))
        for k in sorted(tbl):
            w.write('0x%03x: %s\n' % (k, tbl[k]))
        if unk:
            w.write('# UNKNOWN idx (bitmap not in DB, need manual ID): %s\n' % ' '.join('%03x' % u for u in unk))
        w.flush()
