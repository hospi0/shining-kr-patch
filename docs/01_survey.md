# 초기 조사 — Shining the Holy Ark (JP)

날짜: 2026-07-11 (착수)

## 매체 (확정)

- 세가 새턴 CD, 멀티트랙 BIN/CUE. Track1 = Mode1/2352 데이터, Track2 = CD-DA 오디오.
- IP.BIN: 제품번호 **T-33101G**, V1.005, 1996-11-22, 리전 J, "SHINING THE HOLY ARK".
- 메인 실행 로드 주소: Work RAM High `0x06004000`대 (SH-2, big-endian, 고정 16비트 명령어).
- **원본 해시 (기준)**:
  - Track1 MD5 `d9849fd195dd1bfc417856f44774c12d`
  - Track2 MD5 `2cd8384f79ae17d58acd5944bcf63cfc`
- 디스크 총 109,940 섹터, ISO9660 파일 473개.

## 파일시스템 (확정) — 역할 가설표

확장자별: `scripts/survey_iso.py` → `docs/iso_filelist.txt`.

| 확장자 | 수 | 크기 | 역할 가설 | 텍스트? |
|---|---|---|---|---|
| .CPK | 20 | 94 MB | 무비/컷신 (선두 "FILM") | X |
| .CHR | 177 | 56 MB | 맵/캐릭터 그래픽 | 대사X (베이크드 가능) |
| .MDX | 104 | 47 MB | 맵 데이터 (엔트로피 ~0.12) | X |
| .CPX | 116 | 23 MB | 배경(BPC=BackgroundPiCture 추정)·효과(EFC) | 조사필요 |
| .SPR | 5 | 2 MB | 스프라이트 (EVFACES=대화초상, WIFACES, LOGOS) | 베이크드 가능 |
| **.BIN** | 32 | ~1 MB | **1ST.BIN(메인 실행) + 오버레이** | **1차 후보** |
| .TON/.MDT/.SEQ/.DRV | - | - | 사운드 (SCSP) | X |
| .MES | 1 | 54 KB | **X2SAMPLE.MES = 메시지?** | 후보 |
| .FNT | 1 | 8 KB | DEBUG.FNT (디버그 폰트, 본편 폰트 아님으로 추정) | - |
| .TXT | 3 | 539 B | 저작권/초록 (SJIS 평문) | - |

### .BIN 오버레이 세부 (텍스트 1차 타깃)

- `1ST.BIN` (112 KB) — 메인 실행. 로드 `0x06004000`.
- `X01~X16.BIN` — 공용 스크립트 오버레이. 선두가 `0x0600xxxx`/`0x0020xxxx` 포인터. FFxx 제어코드 분포는 산발적(주로 코드+포인터로 보임).
- `X6*.BIN` (X6DUN1/X6MORI/X6GRV/X6WTR/X6BOSSES 등 17개) — **전부 `0x0604e0ac`로 로드되는 지역별 이벤트 오버레이**. 이름=지역(MORI=森, GRV=무덤, WTR=물, BOSSES=보스). 대사 유력.
- `X78/X79.BIN`, `WORLD_MN.BIN`, `X08MINI.BIN` — 소형 특수 오버레이.

## 텍스트 인코딩 (부분 확정)

- **표준 Shift-JIS 아님** — X6MORI.BIN 전체 SJIS 스캔 0건. (Terra·마도물어와 같은 계열)
- 따라서 **커스텀/타일인덱스 직접 인코딩** 가설 (saturn.md §4). **폰트 배열 순서 = 인코딩 테이블**이므로 폰트 확보가 텍스트 디코딩의 전제.
- X6MORI/X01의 FFxx 분포가 Terra식 깔끔한 제어코드 패턴이 아님 → 이 오버레이들은 대사 블록이 아니라 코드일 수 있음. **실제 대사 텍스트 블록의 위치를 아직 못 박음** (미해결).

## 폰트 (미해결 — 최우선 과제)

- 본편 한자 폰트로 보이는 큰 폰트 파일이 파일 목록에 없음.
- `DEBUG.FNT`(8192 B, ent 0.40): 1bpp 8x8/8x16 렌더 모두 깨끗한 글리프 아님(상단 세로획 소수 + 노이즈) → 디버그 전용 폰트 추정, 본편 폰트 아님.
- 가능성: (a) 1ST.BIN 또는 오버레이에 내장, (b) .CHR/.CPX 그래픽에 포함, (c) 씬별 사용 글리프만 서브셋 로드, (d) 압축(.CPX?). **역방향 앵커(폰트 데이터 참조 코드)로 추적 필요.**

## 미해결 질문 (다음 단계)

1. **실제 대사 텍스트 블록 위치·인코딩 테이블** — X6* 오버레이 정밀 구조 분석 / .MES / .CPX 스캔.
2. **본편 폰트 위치·비트포맷** — 1ST.BIN 디스어셈블로 폰트 참조 코드 추적(SH-2), 또는 Mednafen write-watch로 VRAM 폰트 전송 앵커 잡기.
3. 대화 렌더 하드웨어 (VDP1 스프라이트 vs VDP2 NBG) — Mednafen 레이어 토글.

## 재사용 자산 (terra-kr-patch)

- `tools/sh2_disasm.py` — SH-2 디스어셈블러 (재사용)
- `tools/cdrom_ecc.py` — EDC/ECC 재계산 (재사용)
- `mxe_patch_common.get_iso_files` 등 ISO9660 리더 (본 프로젝트 scripts/survey_iso.py로 이식 완료)
- ⚠️ MXE 스크립트 포맷·CNX/VLZ2 압축·포인터 규약은 Terra 전용 — Shining에서 재실측 전까지 가정 이식 금지.
