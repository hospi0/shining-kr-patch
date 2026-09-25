#!/usr/bin/env python3
"""≤0xFF 글리프 슬롯 여유 재측정 (스토리 완역 반영).
repack 의 used_lo(=JP유지 레코드가 쓰는 ≤0xFF 슬롯) 수집 로직을 복제.
전 맵에서 한 번이라도 쓰이면 '점유' → 여유 = 모든 맵에서 안 쓰이는 슬롯."""
import os, json, glob, importlib.util
_here = os.path.dirname(os.path.abspath(__file__))


def _L(m):
    s = importlib.util.spec_from_file_location(m, os.path.join(_here, m + ".py"))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


br = _L("build_recompress")
Mdx = br.Mdx

union_lo = set()          # 전 맵 통합 점유 ≤0xFF
maps_done = 0
sets = sorted(glob.glob(os.path.join(_here, '..', 'translation', 'sets', 'set*.json')))
_kr_sys, _done_sys = br.load_system_kr()

for sp in sets:
    sj = json.load(open(sp, encoding='utf-8'))
    kr = br.kr_list_of(sj)
    if not any(t.strip() for t in kr[0]):
        continue
    rep = sj['rep_map']
    nf = os.path.join(_here, '..', 'translation', 'names', rep.rsplit('.', 1)[0] + '.json')
    nkr = [''] * 55
    if os.path.exists(nf):
        for r in json.load(open(nf, encoding='utf-8')):
            if 0 <= r['rec'] < 55:
                nkr[r['rec']] = r.get('kr', '')
    br.NAMES_KR = nkr
    _kl, _kd = kr if isinstance(kr, tuple) else (kr, [False] * len(kr))

    for mp in sj['maps']:
        try:
            m = Mdx(mp)
        except Exception:
            continue
        items, start = m.scan_records()
        b6 = m.s.block_base(6)
        story_i = [i for i, it in enumerate(items) if it[0] == 'rec' and it[1] >= b6]
        story_recs = story_i[br.STORY_START_REC:]
        name_recs = story_i[:br.STORY_START_REC]
        sys_recs = [i for i, it in enumerate(items) if it[0] == 'rec' and it[1] < b6]
        story_set = set(story_recs)
        name_map = {name_recs[k]: (nkr[k] if k < len(nkr) else '') for k in range(len(name_recs))}
        kr_texts = [(_kl[j] if j < len(_kl) else '') for j in range(len(story_recs))]
        story_done = {ri: (_kd[j] if j < len(_kd) else False) for j, ri in enumerate(story_recs)}
        sys_texts = [(_kr_sys[j] if j < len(_kr_sys) else '') for j in range(len(sys_recs))]
        sys_done = {ri: (_done_sys[k] if k < len(_done_sys) else False)
                    for k, ri in enumerate(sys_recs)}
        sys_map = {ri: sys_texts[k] for k, ri in enumerate(sys_recs)}

        def kr_of(i):
            if i in story_set:
                return kr_texts[story_recs.index(i)]
            if i in name_map:
                return name_map[i]
            return sys_map.get(i, '')

        def ok(i, toks):
            if not kr_of(i).strip():
                return False
            if i in name_map:
                return True
            if i in story_set:
                if story_done.get(i):
                    return True
                return not Mdx.was_truncated(toks)
            if sys_done.get(i):
                return True
            return not Mdx.was_truncated(toks, br.WAITS)

        translated = {i for i, it in enumerate(items)
                      if it[0] == 'rec' and ok(i, it[2])}
        for i, it in enumerate(items):
            if it[0] != 'rec' or i in translated:
                continue
            for t in it[2]:
                if 0x20 <= t <= 0xFF:
                    union_lo.add(t)
        maps_done += 1

# [XXX] 통과 토큰이 가리키는 ≤0xFF 도 살려야 하지만 그건 맵별이라 여기선 보수적으로 제외 표시
union_lo.add(0x20)   # 공백

# UI 예약(그리드가 인덱스로 직접 찍는 ASCII 슬롯) — 실기 확인분
UI_RESERVED = {0x2f, 0x5f}   # / (HP구분) , _ (커서). 이건 MDX 점유와 무관하게 피해야 함

free_all = [s for s in range(0x20, 0x100) if s not in union_lo and s not in UI_RESERVED]
free_hi = [s for s in free_all if s >= 0x80]           # 비-ASCII(가나 영역)
free_lo = [s for s in free_all if s < 0x80]            # 저-ASCII
print("측정 맵 수: %d" % maps_done)
print("점유 ≤0xFF 슬롯: %d" % len(union_lo))
print("─" * 40)
print("여유 비-ASCII(0x80~0xFF): %d" % len(free_hi))
print("  ", ' '.join('%02x' % s for s in free_hi))
print("여유 저-ASCII(0x20~0x7F): %d" % len(free_lo))
print("  ", ' '.join('%02x' % s for s in free_lo))
print("─" * 40)
print("총 여유(UI예약 제외): %d" % len(free_all))
print("현재 name_kr 풀 필요량: 파티16 + NPC6명음절 + 그리드21 = union 확인 필요")
