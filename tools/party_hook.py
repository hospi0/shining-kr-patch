#!/usr/bin/env python3
"""
파티명 한글화 — struct-rewrite 훅 (2026-07-15).

## 왜 struct-rewrite 인가
파티명은 대사([0b])·메뉴(0x06071726)·전투가 **각각 struct(0x6020660+i*0xCC 이름12B)를 1바이트로**
읽어 렌더한다. 이름 음절을 ≤0xFF 완성형 슬롯으로 구웠으므로(name_kr), **struct 를 한글 ≤0xFF 로
덮어쓰면 세 경로 전부 한글**이 된다(추가 렌더 패치 불필요).

## 훅 = [0b] 핸들러(0x0606CFA4) 리다이렉트, 트램폴린이:
  Part A: 고정 base 0x6020660 의 8슬롯을 순회, 각 이름을 테이블(JP12→KR12)로 매칭→한글 ≤0xFF 덮어쓰기.
          (idempotent — 이미 한글이면 매칭 실패로 스킵. 메뉴/전투는 이 덮어쓴 struct 를 읽어 한글.)
  Part B: 현재 대사 멤버 = 작업버퍼 r4(JP 12B) 를 테이블 매칭→한글 ≤0xFF 를 byte→word 로 @r15 주입
          (매칭 실패면 JP 그대로 byte→word = 원본 동작). → INJECT(0x0606D15A) 로 점프.

install: build_names.py 와 동일(X07 패딩에 훅+테이블, X02 [0b] file 0x7FA4 리다이렉트).
⚠️ struct 는 첫 [0b] 대사에서 덮어써짐 → 그 전에 메뉴 열면 JP(실기 확인 필요, 인트로에 [0b] 있음).
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(__file__))
import sh2asm
import name_kr as nk

STRUCT = 0x06020660           # 파티 마스터 struct base (stride 0xCC, 이름 struct+0 12B)
INJECT = 0x0606D15A           # [0b] 토큰 주입 진입점
X02_0B_FOFF = 0x7FA4          # [0b] 핸들러 패치 지점 (=0x0606CFA4)

# 파티 8명 JP struct 이름(원본 카타카나 바이트, JIS X0201 반각) → 한글 이름
PARTY = [
    (bytes([0xb1, 0xb0, 0xbb, 0xb0]), '아서'),        # アーサー
    (bytes([0xd2, 0xdb, 0xc3, 0xde, 0xa8]), '멜로디'),  # メロディ
    (bytes([0xdb, 0xb0, 0xc3, 0xde, 0xa8]), '로디'),    # ローディ
    (bytes([0xca, 0xde, 0xaf, 0xbf]), '밧소'),          # バッソ
    (bytes([0xb1, 0xb6, 0xc8]), '아카네'),              # アカネ
    (bytes([0xcc, 0xab, 0xd9, 0xc3]), '포르테'),        # フォルテ
    (bytes([0xc4, 0xde, 0xb2, 0xd9]), '도일'),          # ドイル
    (bytes([0xd8, 0xbb]), '리사'),                      # リサ
]

# ⚠️ NPC(사바트/휴돌/가름/리릭스/엘리제/팬서/성주님)는 이 훅으로 처리 안 함 —
#    실기 확인(2026-07-15): NPC 이름 [0b] 는 파티 struct 가 아니라 **시스템 레코드(688~694)를
#    직접 렌더**(Part B 작업버퍼 안 거침, サバト/リリクス 카타카나로 나옴). → NPC 는
#    build_recompress.NPC_NAME_SLOTS 로 **레코드 토큰을 ≤0xFF 한글슬롯으로 교체**해 해결.
#    이 훅은 **파티 8명 전용**(struct = 커스텀 주인공명 + 메뉴/전투 경로라 훅 필요).


def build_table():
    """[jp12][kr12] * 파티8 + 0xFFFFFFFF 종료."""
    out = b''
    for jp, kr in PARTY:
        jp12 = (jp + b'\x00' * 12)[:12]
        kr12 = nk.party_name_bytes(kr)
        assert len(kr12) == 12
        out += jp12 + kr12
    return out + b'\xff\xff\xff\xff'


def build_hook(hook_addr):
    """트램폴린 어셈블 → (code_bytes, table_addr)."""
    # 테이블은 코드 뒤 4정렬 위치
    asm = f"""
      ; ---- Part A: 8슬롯 struct 이름 덮어쓰기 ----
      mov.l #0x{STRUCT:08x}, r6
      mov #8, r7
    a_slot:
      mov.l #__TBL__, r5
    a_tbl:
      mov r5, r2
      mov r6, r3
      mov.l @r2+, r0
      mov #-1, r1
      cmp/eq r1, r0
      bt a_next
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf a_miss
      mov.l @r2+, r0
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf a_miss
      mov.l @r2+, r0
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf a_miss
      mov.l @r2+, r0
      mov.l r0, @r6
      mov r6, r3
      add #4, r3
      mov.l @r2+, r0
      mov.l r0, @r3
      add #4, r3
      mov.l @r2+, r0
      mov.l r0, @r3
      bra a_next
      nop
    a_miss:
      add #24, r5
      bra a_tbl
      nop
    a_next:
      add #0x66, r6
      add #0x66, r6
      add #-1, r7
      tst r7, r7
      bf a_slot
      ; ---- Part B: 현재 대사 멤버(r4) 매칭→byte→word @r15 ----
      mov.l #__TBL__, r5
    b_tbl:
      mov r5, r2
      mov r4, r3
      mov.l @r2+, r0
      mov #-1, r1
      cmp/eq r1, r0
      bt b_jp
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf b_miss
      mov.l @r2+, r0
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf b_miss
      mov.l @r2+, r0
      mov.l @r3+, r1
      cmp/eq r0, r1
      bf b_miss
      mov r15, r3
      mov #12, r1
    b_cl:
      mov.b @r2+, r0
      extu.b r0, r0
      mov.w r0, @r3
      add #2, r3
      add #-1, r1
      tst r1, r1
      bf b_cl
      bra tr_done
      nop
    b_miss:
      add #24, r5
      bra b_tbl
      nop
    b_jp:
      mov r4, r2
      mov r15, r3
      mov #12, r1
    b_jl:
      mov.b @r2+, r0
      extu.b r0, r0
      mov.w r0, @r3
      add #2, r3
      add #-1, r1
      tst r1, r1
      bf b_jl
    tr_done:
      mov.l #0x{INJECT:08x}, r0
      jmp @r0
      nop
    """
    # 2패스: 코드 길이 확정 후 테이블 주소 결정, 리터럴 치환
    code0 = sh2asm.assemble(asm.replace('__TBL__', '0x%08x' % hook_addr), hook_addr)
    tbl_addr = (hook_addr + len(code0) + 3) & ~3
    code = sh2asm.assemble(asm.replace('__TBL__', '0x%08x' % tbl_addr), hook_addr)
    tbl_addr = (hook_addr + len(code) + 3) & ~3       # 길이 안정(리터럴 크기 동일)
    pad = b'\x00' * (tbl_addr - (hook_addr + len(code)))
    return code + pad, tbl_addr


def hook_block(hook_addr):
    code, tbl_addr = build_hook(hook_addr)
    return code + build_table(), tbl_addr


if __name__ == '__main__':
    HOOK = 0x060af120
    blk, tbl = hook_block(HOOK)
    print('트램폴린+테이블 %dB, HOOK=0x%08x, TBL=0x%08x' % (len(blk), HOOK, tbl))
    print('테이블 엔트리 %d(파티 전용) + 종료. 바이트:' % len(PARTY))
    for jp, kr in PARTY:
        print('  %-6s %s -> %s' % (kr, jp.hex(), nk.party_name_bytes(kr).hex()))
