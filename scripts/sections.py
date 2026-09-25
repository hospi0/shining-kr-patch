import struct
d=open('extract/state2/s0.bin','rb').read()
# Mednafen section: [namelen:1][name][size:4 LE][data]  — scan for known names
names=[b'MAIN', b'LWRAM', b'HWRAM', b'CART', b'VDP1', b'VDP2', b'CRAM', b'SCU', b'SMPC', b'SH2', b'M68K', b'SCSP']
found=[]
for nm in names:
    i=0
    while True:
        i=d.find(nm, i)
        if i<0: break
        # check if preceded by namelen byte == len(nm)
        if i>0 and d[i-1]==len(nm):
            sz=struct.unpack('<I', d[i+len(nm):i+len(nm)+4])[0]
            found.append((i-1, nm.decode(), sz))
        i+=1
found.sort()
for off,nm,sz in found:
    print(f"@0x{off:07x}  {nm:6} size=0x{sz:x} ({sz})  data@0x{off+1+len(nm)+4:07x}")
