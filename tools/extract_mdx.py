#!/usr/bin/env python3
"""
MDX 대사 직접 추출 (2026-07-13) — 런타임 스냅샷 불필요.

각 맵파일 M*.MDX는 자기 지역의 폰트(off 0x800)+대사(table2 블록)를 통째로 담은 자기완결 파일.
MDX는 LWRAM **base 0x217800**에 매핑된다(file off X ↔ LWRAM 0x217800+X; 폰트 file0x80c↔0x21800c,
대사 file0xe62a↔LWRAM0x225e2a 실측 — 델타 0x217800). 따라서 extract_script를 base=0x217800으로
MDX 파일에 그대로 돌리면 대사가 나온다(M511.MDX=forest 오프닝, 런타임과 완전일치 검증).

블록6 = 스토리 대사(table2_flat[6]). 씬(지역) 대사는 특정 addr 범위. 같은 지역 맵은 대사 공유
(104맵=~67 고유지역). → MDX(또는 지역대표 1맵)만 추출·번역하면 그 지역 전체 커버.

사용:
  extract_mdx.py <M###.MDX|파일경로> [block_hi=6] [start_hex] [end_hex] [glyph_table]
    → JSON 리스트 [{box,addr,len,jp,kr:""}] stdout (start~end 범위, 없으면 블록 전체)
  extract_mdx.py --group   → 104 MDX를 대사지문으로 그룹핑(지역 목록) 출력
"""
import sys, os, io, json, struct, importlib.util, hashlib
from collections import defaultdict

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, '..', 'scripts'))
from survey_iso import get_iso_files, read_sectors  # noqa

_es = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("extract_script", os.path.join(_here, "extract_script.py")))
_es.__loader__.exec_module(_es) if hasattr(_es, '__loader__') else None
_spec = importlib.util.spec_from_file_location("extract_script", os.path.join(_here, "extract_script.py"))
_es = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_es)

DISC = r"F:\hospi\roms\ss roms\Shining the Holy Ark (Japan) (3M)\patch\Shining the Holy Ark (Japan) (3M) (Track 1).bin"
MDX_BASE = 0x217800          # MDX file off X ↔ LWRAM 0x217800+X


def read_mdx(name_or_path):
    if os.path.exists(name_or_path):
        return open(name_or_path, 'rb').read()
    with open(DISC, 'rb') as f:
        files = get_iso_files(f)
        for k, (lba, sz) in files.items():
            if k.rsplit('/', 1)[-1].upper() == name_or_path.upper():
                return read_sectors(f, lba, sz)
    raise SystemExit('MDX 없음: ' + name_or_path)


def extract(mdx_bytes, block_hi=6, start=None, end=None,
            glyph_path=None):
    gp = glyph_path or os.path.join(_here, '..', 'docs', 'glyph_table_forest.txt')
    s = _es.Script(mdx_bytes, gp, base=MDX_BASE)
    out = []
    i = 0
    for off, ln, toks in s.records(block_hi):
        data = off + 1
        if start is not None and data < start:
            continue
        if end is not None and data > end:
            break
        out.append({'box': i, 'addr': '0x%x' % data, 'len': ln,
                    'jp': _es.render(toks, s.GT), 'kr': ''})
        i += 1
    return out


def group_maps():
    """104 MDX를 대사영역 지문으로 그룹핑 → {fp: [map...]}."""
    with open(DISC, 'rb') as f:
        files = get_iso_files(f)
        mdx = sorted((k.rsplit('/', 1)[-1], v) for k, v in files.items()
                     if k.rsplit('/', 1)[-1].upper().endswith('.MDX'))
        groups = defaultdict(list)
        for nm, (lba, sz) in mdx:
            if sz < 0x11000:
                groups['<small:%s>' % nm].append(nm); continue
            d = read_sectors(f, lba, 0x11000)
            fp = hashlib.md5(d[0xe000:0x11000]).hexdigest()[:8]
            groups[fp].append(nm)
    return groups


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--group':
        g = group_maps()
        w = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        w.write('# %d 지역 (대사영역 0xe000~0x11000 지문)\n' % len(g))
        for fp, ms in sorted(g.items(), key=lambda x: -len(x[1])):
            w.write('%s\t%d맵\t%s\n' % (fp, len(ms), ' '.join(ms)))
        w.flush(); sys.exit()
    name = sys.argv[1]
    block_hi = int(sys.argv[2], 0) if len(sys.argv) > 2 else 6
    start = int(sys.argv[3], 16) if len(sys.argv) > 3 and sys.argv[3] != '-' else None
    end = int(sys.argv[4], 16) if len(sys.argv) > 4 and sys.argv[4] != '-' else None
    gp = sys.argv[5] if len(sys.argv) > 5 else None
    res = extract(read_mdx(name), block_hi, start, end, gp)
    w = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    json.dump(res, w, ensure_ascii=False, indent=1); w.flush()
