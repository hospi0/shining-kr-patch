#!/usr/bin/env python3
"""RetroArch Beetle Saturn 세이브스테이트(RZIP) 파서.
포맷(Terra 프로젝트에서 역공학, 문서 기록):
  0x00  6B  매직 "#RZIPv"
  0x06  1B  버전
  0x07  1B  (용도 미상)
  0x08  4B  LE block_size (=0x20000)
  0x0C  8B  BE total_size (필드값은 못 믿음 — 끝까지 청크 순차 해제)
  0x14+     청크들. 첫 청크는 프리픽스 없이 바로 zlib 스트림,
            둘째 청크부터 각 청크 앞에 4B LE 압축길이.
해제하면 새턴 전체 메모리 스냅샷(~6.8MB, VDP1/VDP2 VRAM·Work RAM 포함).
사용: parse_state.py in.state out.bin
"""
import sys, struct, zlib

def parse_rzip(raw):
    # 포맷(2026-07-11 재도출): 6B "#RZIPv" + 1B ver + 1B unk + 4B LE block_size
    #   + 8B LE total_size, 이후 청크들 [4B LE clen][zlib data] 반복(첫 청크 포함).
    assert raw[:6] == b'#RZIPv', f'RZIP 매직 아님: {raw[:6]!r}'
    ver = raw[6]
    block_size = struct.unpack('<I', raw[8:12])[0]
    total = struct.unpack('<Q', raw[12:20])[0]
    print(f'  RZIP v{ver} block_size=0x{block_size:X} total=0x{total:X} ({total}B)')
    out = bytearray()
    pos = 20
    while pos + 4 <= len(raw) and len(out) < total:
        clen = struct.unpack('<I', raw[pos:pos+4])[0]
        pos += 4
        if clen == 0 or pos + clen > len(raw):
            break
        out += zlib.decompress(raw[pos:pos+clen])
        pos += clen
    assert len(out) == total, f'해제 {len(out)} != total {total}'
    return bytes(out)

def parse_maybe_plain(raw):
    """RZIP가 아니면(비압축 .state) 그대로 반환."""
    if raw[:6] == b'#RZIPv':
        return parse_rzip(raw)
    print('  RZIP 아님 — 원본 그대로 사용')
    return raw

def main():
    raw = open(sys.argv[1], 'rb').read()
    print(f'입력 {len(raw)}B')
    snap = parse_maybe_plain(raw)
    out = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1] + '.snap.bin'
    open(out, 'wb').write(snap)
    print(f'스냅샷 {len(snap)}B -> {out}')
    # Mednafen 섹션 태그 위치 힌트 (VDP1/VDP2 VRAM 찾기용)
    for tag in (b'VDP1', b'VDP2', b'SH2', b'MAIN', b'VRAM', b'CRAM'):
        i = snap.find(tag)
        print(f'  태그 {tag.decode():5}: {"@0x%X"%i if i>=0 else "없음"}')

if __name__ == '__main__':
    main()
