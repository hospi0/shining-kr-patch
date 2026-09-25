#!/usr/bin/env python3
"""
시스템 텍스트(블록0~5 + 블록6 rec0~54 이름) 추출 → translation/system.json (2026-07-13).

## 왜 필요한가
MDX 섹션0 예산에서 **블록0~5가 쓰는 JP 한자 576~610종(≈19KB)** 이 글리프표를 점유해,
큰 지역의 한글 대사가 안 들어간다. 이 텍스트를 한글로 번역하면 그 한자가 통째로 사라져
예산이 13KB 이상 남고, 덤으로 아이템·마법·전투 메시지까지 한글이 된다.

## 전 맵 공통 (실측)
레코드 끝 패딩 쓰레기를 잘라내고 비트맵으로 대조하면 **시스템 레코드는 전 맵 100% 동일**
(M511 ↔ M118 교집합 1,381/1,381). → **한 번만 번역하면 104맵 전부 커버.**
이름(블록6 rec0~54, 몬스터/아이템)은 맵마다 조금 다르므로 따로 뽑는다.

## 표기
· `{br}` 줄바꿈, 공백은 스페이스
· `[XX]` = 제어코드/미식별 글리프 — **그대로 두면 원본 토큰이 그대로 나간다**(건드리지 말 것)
· 나머지는 번역 대상 텍스트

사용: extract_system.py   → translation/system.json, translation/names/<MAP>.json
"""
import os, sys, json, glob, importlib.util
from collections import OrderedDict

_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


br = _L("build_recompress")
DK = _L("extract_script").DK
# 반탁점(゜, 글리프 0xdf)도 앞 글자와 결합해야 한다 — 안 하면 バックアッフ゜ 처럼 깨져 보인다.
HAN = dict(zip('はひふへほハヒフヘホ', 'ぱぴぷぺぽパピプペポ'))


def load_db():
    db = {}
    p = os.path.join(_here, '..', 'docs', 'glyph_bitmap_db.txt')
    for L in open(p, encoding='utf-8'):
        parts = L.rstrip('\n').split('\t')
        if len(parts) == 2 and parts[0].strip():
            db[parts[0].strip()] = parts[1]
    return db


def render(mdx, toks, db):
    out = []
    for t in toks:
        if t in br.CUT:
            break
        if t == 0x03:
            out.append('{br}'); continue
        if t == 0x20:
            out.append(' '); continue
        if t < 0x20:
            out.append('[%02x]' % t); continue
        g = mdx.rd(mdx.glyph_addr + (t - 0x20) * 32, 32).hex()
        c = db.get(g)
        if c is None:
            out.append('[%03x]' % t); continue
        if c == '゛' and out and out[-1] in DK:      # 탁점 결합
            out[-1] = DK[out[-1]]; continue
        if c == '゜' and out and out[-1] in HAN:     # 반탁점 결합
            out[-1] = HAN[out[-1]]; continue
        out.append(c)
    return ''.join(out)


def main():
    db = load_db()
    sets = sorted(glob.glob(os.path.join(_here, '..', 'translation', 'sets', '*.json')))
    reps = [json.load(open(p, encoding='utf-8'))['rep_map'] for p in sets]

    sysrec = OrderedDict()      # 순번 → {jp, kr}
    names_dir = os.path.join(_here, '..', 'translation', 'names')
    os.makedirs(names_dir, exist_ok=True)

    for ri, rep in enumerate(reps):
        mdx = br.Mdx(rep)
        items, _ = mdx.scan_records()
        b6 = mdx.s.block_base(6)
        si = [i for i, it in enumerate(items) if it[0] == 'rec' and it[1] >= b6]
        names = si[:br.STORY_START_REC]
        story = set(si[br.STORY_START_REC:])

        # 이름 (맵마다 다름)
        nl = [{'rec': k, 'jp': render(mdx, items[i][2], db), 'kr': ''}
              for k, i in enumerate(names)]
        json.dump(nl, open(os.path.join(names_dir, rep.replace('.MDX', '') + '.json'), 'w',
                           encoding='utf-8'), ensure_ascii=False, indent=1)

        # 시스템 (전 맵 동일 — 첫 맵에서만 채우고, 이후 맵은 일치 검증)
        k = 0
        for i, it in enumerate(items):
            if it[0] != 'rec' or i in story or i in set(names):
                continue
            jp = render(mdx, it[2], db)
            if ri == 0:
                sysrec[k] = {'id': k, 'jp': jp, 'kr': ''}
            elif k in sysrec and sysrec[k]['jp'] != jp:
                sysrec[k]['diff'] = True
            k += 1

    out = list(sysrec.values())
    diffs = sum(1 for r in out if r.get('diff'))
    p = os.path.join(_here, '..', 'translation', 'system.json')
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    chars = sum(len(r['jp']) for r in out)
    print("시스템 레코드 %d개 (%d자) → %s" % (len(out), chars, p))
    print("  맵 간 불일치 %d개 (0이면 전 맵 공통)" % diffs)
    print("  이름 파일 %d개 → translation/names/" % len(reps))


if __name__ == '__main__':
    main()
