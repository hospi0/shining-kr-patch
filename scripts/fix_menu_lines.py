#!/usr/bin/env python3
"""한 줄 전용(메뉴 프롬프트) 레코드의 번역문을 원본 JP 폭에 맞게 줄인다.

2026-08-07 M137 크래시 확정 후속: 이 레코드들은 이제 rewrap 대상에서 빠져 **한 줄로** 렌더된다
(줄바꿈 0x03 을 넣으면 대사창 없는 렌더 경로가 ADDRESS ERROR). 원본보다 훨씬 길면 메뉴 밖으로
삐져나가므로 JP 글리프 수 근처까지 줄인다. wrap_risk.py 가 뽑은 9건 중 8건.

사용: fix_menu_lines.py [--dry]
"""
import io, json, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#  파일          box   기존(부분일치 검증용)                  새 번역
FIXES = [
    ('set03_M118.json', 105, '동쪽 숲의 고대 유적을 알고 있는가?',
                             '동쪽 숲의 고대 유적을 아는가?'),
    ('set04_M551.json',  56, '[00c]은(는) 정상적인 상태로 돌아왔다!',
                             '[00c]은(는) 정상으로 돌아왔다!'),
    ('set06_M531.json',  31, '그 밖에 또 무슨 볼일이 있는가?',
                             '그 밖에 볼일이 있는가?'),
    ('set09_M111.json',  13, '전 왕궁현자 [00b][009]님을 아시나요?',
                             '전 왕궁현자 [00b][009]님을 아나요?'),
    ('set09_M111.json',  35, '동양의 주술 이야기, 알고 있나?',
                             '동양의 주술 이야기를 아나?'),
    ('set09_M111.json', 152, '자네, 우리 딸을 어떻게 생각하는가?',
                             '자네, 우리 딸을 어떻게 보나?'),
    ('set16_M137.json',   1, '대장장이인 나한테 무슨 볼일이지?',
                             '대장장이한테 무슨 볼일이지?'),
    ('set16_M137.json',   8, '누구의 장비를 주문하시겠습니까?',
                             '누구의 장비를 주문할까?'),
    # set15 box5 「뭔가 듣고 싶은 것이 있는가…?」 = JP 와 같은 17칸 → 그대로 둔다.
]


def main():
    dry = '--dry' in sys.argv
    by_file = {}
    for f, box, old, new in FIXES:
        by_file.setdefault(f, []).append((box, old, new))
    for f, edits in by_file.items():
        p = os.path.join(_ROOT, 'translation', 'sets', f)
        d = json.load(io.open(p, encoding='utf-8'))
        m = {b['box']: b for b in d['boxes']}
        for box, old, new in edits:
            cur = m[box]['kr']
            if cur == new:
                print(f'  = {f} box{box} 이미 적용됨'); continue
            assert cur == old, f'{f} box{box} 현재값이 예상과 다름:\n  {cur!r}\n  {old!r}'
            m[box]['kr'] = new
            print(f'  ✎ {f} box{box}\n      {old}\n   →  {new}')
        if not dry:
            with io.open(p, 'w', encoding='utf-8') as fp:
                json.dump(d, fp, ensure_ascii=False, indent=1)
                fp.write('\n')
    print('완료' + (' (dry-run)' if dry else ''))


if __name__ == '__main__':
    main()
