import struct
sys_lw=open('extract/state2/lwram_s0.bin','rb').read()
import importlib.util
spec=importlib.util.spec_from_file_location("dc","tools/decompress.py")
dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
d=dc.Decompressor(sys_lw)
sb=d.bits(0x225ec6,0x80)
idx=0; raw=[]
for _ in range(360):
    b=d.decode_byte(idx,sb); idx=b; raw.append(b)
# print as bytes with annotation; mark 0x00 hi-byte glyph pairs
print("raw decoded byte stream (360 bytes) from 0x225ec6:")
s=' '.join(f'{b:02x}' for b in raw)
# print in rows of 32
for i in range(0,len(raw),32):
    print(f'{i:03d}: '+' '.join(f'{b:02x}' for b in raw[i:i+32]))
