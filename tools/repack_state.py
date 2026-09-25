#!/usr/bin/env python3
"""
RetroArch Beetle Saturn 세이브스테이트(RZIP) 리팩 — 편집한 스냅샷을 다시 .state로.
포맷: 20B 헤더(6B "#RZIPv"+1B ver+1B unk+4B LE block_size+8B LE total) + 청크들[4B LE clen][zlib].
원본 .state의 헤더 20바이트를 그대로 보존(ver/unk/block_size/total), 스냅샷을 block_size 단위로 zlib 재압축.

사용: repack_state.py <원본.state> <편집snap.bin> <출력.state>
검증: parse_state로 재파싱해 스냅샷 바이트 동일 확인(roundtrip).
"""
import sys, struct, zlib


def repack(orig_state_path, snap, out_path):
    hdr = open(orig_state_path, 'rb').read()[:20]
    assert hdr[:6] == b'#RZIPv', 'RZIP 아님'
    block_size = struct.unpack('<I', hdr[8:12])[0]
    total = struct.unpack('<Q', hdr[12:20])[0]
    assert len(snap) == total, f'스냅샷 {len(snap)} != 헤더 total {total}'
    out = bytearray(hdr)
    pos = 0
    while pos < len(snap):
        chunk = snap[pos:pos + block_size]
        comp = zlib.compress(chunk, 9)
        out += struct.pack('<I', len(comp))
        out += comp
        pos += block_size
    open(out_path, 'wb').write(out)
    return len(out)


if __name__ == '__main__':
    orig, snapf, outp = sys.argv[1], sys.argv[2], sys.argv[3]
    snap = open(snapf, 'rb').read()
    n = repack(orig, snap, outp)
    print(f'리팩 완료: {n}B -> {outp}')
