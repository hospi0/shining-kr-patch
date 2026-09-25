#!/usr/bin/env python3
"""줄바꿈(0x03)을 새로 넣는 레코드를 **실제 MDX 원본 토큰** 기준으로 열거·분류.

0x0606DD5C 줄바꿈 핸들러는 대사창 전용이다 — 텍스트창 구조체 포인터 [0x060792D4](=0xFFFFFFFF)를
역참조해 워드를 쓰므로 대사창이 없는 레코드에서 밟으면 ADDRESS ERROR.
2026-08-07 M137 크래시 스테이트로 확정: 디코드버퍼 = "누구의 장비를{br}주문하시겠습니까?"(set16 box8),
크래시 PC=0x0606DD6E, 저장 PR=0x0606D27A, r8=0x060792D4.

판정 기준(원본 JP 토큰):
  · has_br   = JP 에 0x0003 이 있다        → 대사창 레코드 확정(원본이 이미 줄바꿈을 쓴다)
  · has_wait = 마지막 글리프 뒤에 0x04/05/06/08 이 있다 → 버튼 대기 = 대사창 레코드
  둘 다 아니면 "한 줄 전용 후보"(메뉴 프롬프트·설명바 등) = 줄바꿈 금지 대상.

사용: wrap_risk.py [--px N] [--tsv out.tsv]
"""
import sys, os, json, glob

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'tools'))
import build_recompress as br

WAITS = (0x0004, 0x0005, 0x0006, 0x0008)


def jp_flags(toks):
    """(줄바꿈 있음, 끝 대기코드 있음)"""
    body = toks[:-1] if toks and toks[-1] == br.TERM else toks
    last_g = max((i for i, t in enumerate(body) if t >= 0x20), default=-1)
    tail = body[last_g + 1:]
    return (0x0003 in body), any(t in WAITS for t in tail)


def scan():
    rows = []
    for p in sorted(glob.glob(os.path.join(_ROOT, 'translation', 'sets', 'set*.json'))):
        sj = json.load(open(p, encoding='utf-8'))
        mdx = br.Mdx(sj['rep_map'])
        items, _ = mdx.scan_records()
        b6 = mdx.s.block_base(6)
        story_i = [i for i, it in enumerate(items) if it[0] == 'rec' and it[1] >= b6]
        story = story_i[br.STORY_START_REC:]
        kr_list, _done = br.kr_list_of(sj)
        for j, ri in enumerate(story):
            kr = kr_list[j] if j < len(kr_list) else ''
            if not kr.strip():
                continue
            out = br.paginate(br.rewrap(kr))
            if '{br}' not in out and '\n' not in out:
                continue                      # 줄바꿈 안 생김
            has_br, has_wait = jp_flags(items[ri][2])
            rows.append(dict(set=sj['set_id'], map=sj['rep_map'], box=j,
                             has_br=has_br, has_wait=has_wait,
                             px=br._line_px(kr.replace('{br}', ' ').replace('\n', ' ')),
                             kr=kr, out=out))
    return rows


def main():
    if '--px' in sys.argv:
        br.WRAP_PX = int(sys.argv[sys.argv.index('--px') + 1])
    rows = scan()
    risky = [r for r in rows if not r['has_br'] and not r['has_wait']]
    print(f'줄바꿈이 생기는 레코드 {len(rows)}건 중 '
          f'JP 무개행+무대기 = **한 줄 전용 후보 {len(risky)}건**\n')
    for r in risky:
        print(f"--- {r['set']} ({r['map']}) box{r['box']}  kr폭={r['px']}px")
        print(f"    KR : {r['kr']}")
        print(f"    → {r['out']!r}")
    if '--tsv' in sys.argv:
        out = sys.argv[sys.argv.index('--tsv') + 1]
        with open(out, 'w', encoding='utf-8') as f:
            f.write('set\tmap\tbox\tpx\tkr\n')
            for r in risky:
                f.write(f"{r['set']}\t{r['map']}\t{r['box']}\t{r['px']}\t"
                        f"{r['kr']}\n".replace('\n', '\\n').replace('\\n', '\\n', 1))
        print(f'\n{out} 저장')
    return risky


if __name__ == '__main__':
    main()
