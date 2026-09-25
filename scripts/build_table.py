import struct
snaps=[open(f'extract/state2/s{i}.bin','rb').read() for i in range(4)]
def deswap(b):
    b=bytearray(b); n=len(b)&~1
    b[0:n:2],b[1:n:2]=b[1:n:2],b[0:n:2]; return bytes(b)
HB=0x57F3D7
hw=[deswap(s[HB:HB+0x100000]) for s in snaps]
def A(a): return a-0x6000000
start=A(0x607b390)

# known lines (space= full-width gap between words -> 0x20 ; newline between rows -> 0x03)
known=[
 "ああ 間違いなくヤツだった\n太刀を背負って 走り込んでいった\n隊長たちも 後を追っていったが・・・。",
 "どおりで・・・オレたちが来た時\nお前しか 見あたらなかったわけだ。",
 "隊長たち まさか・・・\nオレたちを 呼びに来ないかな？",
 "鉱山が閉鎖されて だいぶ経つから\n色々な魔物も 住みついてるだろうな。",
]
DAKU={'が':'か','ぎ':'き','ぐ':'く','げ':'け','ご':'こ','ざ':'さ','じ':'し','ず':'す','ぜ':'せ','ぞ':'そ',
 'だ':'た','ぢ':'ち','づ':'つ','で':'て','ど':'と','ば':'は','び':'ひ','ぶ':'ふ','べ':'へ','ぼ':'ほ',
 'ガ':'カ','ギ':'キ','グ':'ク','ゲ':'ケ','ゴ':'コ','ザ':'サ','ジ':'シ','ズ':'ス','ゼ':'セ','ゾ':'ソ',
 'ダ':'タ','ヂ':'チ','ヅ':'ツ','デ':'テ','ド':'ト','バ':'ハ','ビ':'ヒ','ブ':'フ','ベ':'ヘ','ボ':'ホ'}
HANDAKU={'ぱ':'は','ぴ':'ひ','ぷ':'ふ','ぺ':'へ','ぽ':'ほ','パ':'ハ','ピ':'ヒ','プ':'フ','ペ':'ヘ','ポ':'ホ'}

table={}  # char -> set of indices
conflicts=[]
for si,line in enumerate(known):
    # read words until terminator 0x0008
    ws=[]
    for k in range(120):
        w=struct.unpack('>H',hw[si][start+2*k:start+2*k+2])[0]
        if w==0x0008: break
        ws.append(w)
    # build expected token stream: each char -> 1 index, voiced -> base + DAKUTEN(0xde)
    exp=[]  # list of ('char', maybe 'daku')
    for ch in line:
        if ch==' ': exp.append(('SPC',0x20))
        elif ch=='\n': exp.append(('NL',0x03))
        elif ch in DAKU: exp.append((ch,None)); exp.append(('゛',0xde))
        elif ch in HANDAKU: exp.append((ch,None)); exp.append(('゜',None))
        else: exp.append((ch,None))
    if len(exp)!=len(ws):
        print(f"s{si}: LEN MISMATCH exp={len(exp)} got={len(ws)}")
        print("  chars:",''.join(c if isinstance(c,str) else c[0] for c,_ in exp))
    for (tok,fixed),w in zip(exp,ws):
        base = DAKU.get(tok,tok) if fixed is None and tok in DAKU else tok
        if fixed is not None:
            if w!=fixed and tok not in ('゛','゜'):
                conflicts.append((si,tok,hex(w),hex(fixed)))
            table.setdefault('゛' if tok=='゛' else tok,set()).add(w)
        else:
            key = DAKU.get(tok, tok)  # store under base kana for voiced
            if tok in DAKU:
                table.setdefault(DAKU[tok],set()).add(w)  # base
            else:
                table.setdefault(tok,set()).add(w)

# print resolved table sorted by index
inv={}
for ch,s in table.items():
    for w in s:
        inv.setdefault(w,set()).add(ch)
print("\n=== index -> char(s) ===")
for w in sorted(inv):
    print(f"0x{w:04x}: {' '.join(sorted(inv[w]))}")
if conflicts: print("\nCONFLICTS:",conflicts)

with open('docs/glyph_table_confirmed.txt','w',encoding='utf-8') as f:
    f.write("Shining the Holy Ark — decoded-buffer glyph index table (confirmed from 4 states)\n")
    f.write("16-bit BE indices. Voiced kana = base + 0x00de (dakuten).\n\n")
    for w in sorted(inv):
        chs=' '.join(sorted(inv[w]))
        f.write(f"0x{w:04x}: {chs}\n")
print("wrote docs/glyph_table_confirmed.txt", "conflicts=",len(conflicts))
