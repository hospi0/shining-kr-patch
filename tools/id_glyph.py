#!/usr/bin/env python3
"""
글리프 식별 등록기 (2026-07-12) — 스크린샷으로 읽은 동적한자를 **비트맵 DB에 등록**해
전 씬(forest/village/grave) 공유되게 한다.

핵심: 인덱스(0x35e 등)는 씬마다 다르지만 글리프 비트맵(32B)은 씬 무관(같은 한자=같은 비트맵).
  그래서 한 씬에서 idx→char를 확인하면 그 비트맵을 DB에 넣어 전 씬에 자동 적용(build_glyph_table gen).

사용:
  id_glyph.py <scene> <idx_hex> <char> [<idx_hex> <char> ...]
    scene = forest|village|grave (LWRAM은 extract/lwram/<scene>.bin)
  → 해당 씬 LWRAM에서 idx의 비트맵을 읽어 glyph_bitmap_db.txt에 <bitmap>→<char> 추가,
    그다음 3씬 테이블(docs/glyph_table_*.txt)을 DB로 재생성.

이후 tools/extract_scene.py로 각 씬 json 재추출하면 반영됨.
"""
import sys, os, struct, importlib.util

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location("bgt", os.path.join(_here, "build_glyph_table.py"))
_B = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_B)

LWRAM_DIR = os.path.join(_here, '..', 'extract', 'lwram')
SCENES = ['forest', 'village', 'grave']


def main():
    scene = sys.argv[1]
    lwp = os.path.join(LWRAM_DIR, scene + '.bin')
    lw = open(lwp, 'rb').read()
    base = _B.glyph_base(lw)
    db = _B.load_db()
    args = sys.argv[2:]
    added, conflict = [], []
    for i in range(0, len(args), 2):
        idx = int(args[i], 16); ch = args[i + 1]
        b = _B.glyph_bytes(lw, base, idx)
        if b in db and db[b] != ch:
            conflict.append((idx, db[b], ch)); continue
        db[b] = ch; added.append((idx, ch))
    _B.save_db(db)
    # regenerate all scene tables from DB
    for s in SCENES:
        p = os.path.join(LWRAM_DIR, s + '.bin')
        if not os.path.exists(p):
            continue
        tbl, unk = _B.gen_table(open(p, 'rb').read(), db)
        outp = os.path.join(_here, '..', 'docs', 'glyph_table_%s.txt' % s)
        import io
        with io.open(outp, 'w', encoding='utf-8') as o:
            o.write('# auto-generated scene glyph table (bitmap DB lookup). unknown=%d\n' % len(unk))
            for k in sorted(tbl):
                o.write('0x%03x: %s\n' % (k, tbl[k]))
    sys.stderr.write('added %d glyphs to DB (now %d): %s\n' % (
        len(added), len(db), ' '.join('0x%x=%s' % (i, c) for i, c in added)))
    if conflict:
        sys.stderr.write('CONFLICTS (DB kept existing): %s\n' % conflict)
    sys.stderr.write('regenerated scene tables. now re-run extract_scene.py per scene.\n')


if __name__ == '__main__':
    main()
