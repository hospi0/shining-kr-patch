#!/usr/bin/env python3
"""
번역 구멍(kr에 남은 일본어 한자 `[XXX]`) 추출/반영 도구 (2026-07-13).

## 왜 구멍을 메워야 하나
1) 품질 — 한글 문장 사이에 일본어 한자가 그대로 박혀 있다(예: `성의 [350]모집으로` = 城の徴集).
2) **예산** — kr에 남은 `[XXX]` 한자는 글리프표에 그 한자를 계속 실어야 해서 슬롯을 먹는다.
   (구멍 많은 셋은 JP 한자 212종, 다 메운 셋은 53종 — 셋당 최대 5KB 차이)

## 표기
· `[XX]` 2자리(≤0xFF) = 제어코드/이름변수 → **그대로 두세요**(원본 토큰이 그대로 나갑니다)
· `[XXX]` 3자리(>0xFF) = **미번역 한자** → 이게 메울 대상. 한 글자도 남기지 마세요.
· `{br}` = 줄바꿈, 공백은 스페이스

사용:
  holes.py dump              → translation/holes.json (남은 구멍만, jp+kr)
  holes.py apply             → holes.json 의 kr 을 translation/sets/*.json 에 반영 + 검증
"""
import sys, os, json, glob, re

_here = os.path.dirname(os.path.abspath(__file__))
SETS = os.path.join(_here, '..', 'translation', 'sets')
HOLES = os.path.join(_here, '..', 'translation', 'holes.json')
PAT = re.compile(r'\[([0-9a-fA-F]{2,4})\]')


def kanji_in(s):
    """kr 에 남은 한자 글리프 토큰(>0xFF). [135](」)은 정상 글리프라 제외."""
    return [m.group(1) for m in PAT.finditer(s)
            if int(m.group(1), 16) > 0xFF and m.group(1) != '135']


def dump():
    out = []
    per = {}
    for p in sorted(glob.glob(os.path.join(SETS, 'set*.json'))):   # ⚠️ sets/ 에 섞인 다른 json 배제
        sj = json.load(open(p, encoding='utf-8'))
        n = 0
        for b in sj['boxes']:
            if kanji_in(b.get('kr', '')):
                out.append({'set': os.path.basename(p), 'box': b['box'],
                            'jp': b['jp'], 'kr': b['kr']})
                n += 1
        if n:
            per[os.path.basename(p)] = n
    json.dump(out, open(HOLES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print("구멍 %d박스 → %s" % (len(out), HOLES))
    for k, v in sorted(per.items(), key=lambda x: -x[1]):
        print("  %-16s %3d" % (k, v))


def apply_():
    holes = json.load(open(HOLES, encoding='utf-8'))
    by_set = {}
    for h in holes:
        by_set.setdefault(h['set'], {})[h['box']] = h['kr']
    changed = 0
    left = 0
    for name, m in by_set.items():
        p = os.path.join(SETS, name)
        sj = json.load(open(p, encoding='utf-8'))
        for b in sj['boxes']:
            if b['box'] in m and m[b['box']] != b['kr']:
                b['kr'] = m[b['box']]; changed += 1
        json.dump(sj, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # 검증
    bad = []
    for p in sorted(glob.glob(os.path.join(SETS, 'set*.json'))):
        sj = json.load(open(p, encoding='utf-8'))
        for b in sj['boxes']:
            k = kanji_in(b.get('kr', ''))
            if k:
                left += 1
                if len(bad) < 8:
                    bad.append((os.path.basename(p), b['box'], k[:3]))
    print("반영 %d박스. 남은 구멍 %d박스" % (changed, left))
    for x in bad:
        print("  %s #%d %s" % x)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'dump'
    (dump if cmd == 'dump' else apply_)()
