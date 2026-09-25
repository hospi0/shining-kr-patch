# 코드 분석 — 1ST.BIN (정적 디스어셈블)

날짜 2026-07-11. LOAD_BASE `0x06004000` (SH-2 BE). 도구: `scripts/xref_literals.py`, `tools/disasm.py`
(terra `sh2_disasm.py` 코어 재사용). ⚠️ 전부 정적 분석 가설 — 동적/실측 확정 전 사실로 굳히지 말 것.

## 확정 함수 (가설명)

| CPU 주소 | 파일 off | 가설 기능 | 근거 |
|---|---|---|---|
| `0x0600CE60` | 0x8E60 | **DMA 전송 프리미티브** `dma(src=R4,dst=R5,cnt=R6)` | DMAC ch0 레지스터 0xFFFFFF80(SAR)/84(DAR)/88(TCR)/8C(CHCR=0x5601)에 씀, 이전 DMA busy 대기 |
| `0x0600CE50` | 0x8E50 | dma 진입 래퍼 (동일) | 동상 |
| `0x0600CE20` | 0x8E20 | **PND(타일맵) 생성기** | 바이트 읽어 6/4비트 분할→16비트 PND 워드, base(R7=(b<<8)\|b) 가산, `MOV.W R0,@R6` 순차 기록 |
| `0x0600CDF0` | 0x8DF0 | VRAM 블록 전송(src=R4,cnt=R5,dst=R6) | 위 dma 계열 호출, VDP2 VRAM 대상 |
| `0x0600CCE0` | 0x8CE0 | **VDP2 VRAM 레이아웃 초기화** | 25E00000/40000/60000/63F40/76000/78000/3FF00 대량 로드, GBR 전역에 VRAM 포인터 기록 |
| `0x0600CEB4` | 0x8EB4 | (초기화 보조, BSR 다수) | 미확정 |
| `0x0600E894` | 0xA894 | **범용 블록복사/DMA** `copy(src=R4,dst=R5,cnt=R6,mode=R7)` | 0x060166xx 로더가 512KB를 VDP2/VDP1/CRAM로 나를 때 반복 호출 |
| `0x060166C0` | 0x126C0 | **화면 그래픽 로더** | WRAM 스테이징 버퍼 0x06084000 채운 뒤 VDP2 VRAM(0x25E00000, 0x80000B)+VDP1 VRAM(0x25C00100)+CRAM(0x25F00000) 일괄 전송 |

## 아키텍처 결론 (그래픽 로드 경로)

`(CD/압축) → WRAM 스테이징 버퍼 0x06084000 → DMA 프리미티브(0x0600E894 / 0x0600CE60) → VDP2/VDP1 VRAM·CRAM`.
**폰트도 이 경로로 VDP2 캐릭터 베이스에 적재될 것.** 폰트를 찾으려면: 0x06084000 버퍼를 채우는 소스(JSR 0x0600EE18/EE28 등)를 역추적하거나, 특정 VDP2 캐릭터 베이스로 가는 전송의 소스를 추적한다.

## GBR 전역 변수 블록 (VRAM 레이아웃 레코드)

게임은 GBR을 전역 변수 베이스로 사용. VDP2 init이 기록하는 값:

| GBR 오프셋 | 값 | 의미 가설 |
|---|---|---|
| @(0x1E0,GBR) | 0x060FFE1C (WRAM-Hi) | 작업 버퍼 포인터 |
| @(0x1E4,GBR) | 0x25E60000 (VDP2 VRAM) | VRAM 영역 포인터 A |
| @(0x1E8,GBR) | 0x25E60000 | VRAM 영역 포인터 B |
| @(0x214,GBR) | 0x25E3FF00 | VRAM 영역 포인터 C |
| @(0x80,GBR) | (DMA 상태/락) | dma 루틴에서 참조 |

→ **GBR 전역 블록이 VRAM 메모리 맵의 단일 진실 원천.** 폰트 캐릭터 베이스도 이 블록 어딘가에 있을 가능성. GBR 초기값 자체는 아직 미확인(startup에서 LDC Rn,GBR 찾아야 함).

## 1ST.BIN 내부 데이터 테이블 (VRAM 셋업 소스)

- `0x0600D188` (file 0x9188) → VDP2 VRAM 0x25E60000으로 전송
- `0x0600D588` (file 0x9588), `0x0600D5A0` (file 0x95A0) → PND 생성기 입력
이들은 타이틀/메뉴 배경 타일맵·소형 그래픽 추정 (대사 폰트인지는 미확정).

## 하드웨어 앵커 xref (요약)

`scripts/xref_literals.py extract/1ST.BIN` 전체 결과 참조. VDP2 VRAM 로드 명령 주요 위치:
`0x0600CD00~CDD6`(VRAM init), `0x060166D4~1699A`(그래픽 로드+CRAM 팔레트 — 폰트/타일 로더 후보),
`0x0601465C`, `0x06016240`(CRAM). VDP1: `0x0600EE36`, `0x0600FB32`, `0x06016xxx` 다수.

## 다음 앵커 (폰트 추적)

1. **0x060166D4~1699A 함수** — VDP2 VRAM(25E5BE00,25E00000,25E20000,25E42000) + CRAM(25F00000) 동시 기록 → 그래픽+팔레트 로더. 폰트 로딩일 가능성 조사.
2. GBR 초기값 확인 → 전역 블록 실제 주소 → 폰트 캐릭터 베이스 포인터 슬롯 탐색.
3. 텍스트 렌더 엔진(타일코드→PND, 0xFEFF 경계 비교, FFxx 제어코드 디스패치)은 1ST.BIN 또는 오버레이(X01 등)에 있을 것 — 별도 추적.
4. 막히면 동적(Mednafen VRAM write-watch)으로 폰트 전송 지점 직접 포착 — saturn.md §9.
