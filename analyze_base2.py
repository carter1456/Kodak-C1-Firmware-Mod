#!/usr/bin/env python3
"""Smarter base hunt: try known Novatek maps + vector math + LDR literal pools."""
import struct
from collections import Counter

dec = open("out/rtos_decompressed.bin", "rb").read()
print(f"size={len(dec)} first words:")
for i in range(0, 32, 4):
    w = struct.unpack_from("<I", dec, i)[0]
    print(f"  [0x{i:X}] 0x{w:08X}")

# Reset branch target if loaded at file-offset==VA (base 0)
reset = struct.unpack_from("<I", dec, 0)[0]
if (reset & 0xFF000000) == 0xEA000000:
    imm24 = reset & 0xFFFFFF
    if imm24 & 0x800000:
        imm24 -= 0x1000000
    target = (0 + 8 + imm24 * 4) & 0xFFFFFFFF
    print(f"Reset B target if base=0: 0x{target:08X}")

STRINGS = {
    "KODAKPIXPRO C1": 0x75DA1C,
    "A:\\C110.bin": 0x76C8A8,
    "logo_bs": 0x76C094,
    "System_OnStrg_UploadFW": 0x76CA94,
    "Do FW Update": 0x76CED0,
    "xFwSrv_CmdBinUpdateAllInOne": 0x23B1C,
    "CheckSumOKCb": 0x76CA84,
    "Display_ShowSplash": 0x76C2B0,
    "UI_ShowJPG": 0x76C2A4,
    "ENGINEER": 0xA6F08C,
}

# verify a few newly found
for name, off in STRINGS.items():
    raw = name.encode()
    ok = dec[off : off + len(raw)] == raw
    print(f"  {'OK' if ok else 'MISS'} {name} @ 0x{off:X}")

CANDIDATE_BASES = [
    0x00000000,
    0x00001000,
    0x00010000,
    0x00100000,
    0x00200000,
    0x01000000,
    0x02000000,
    0x04000000,
    0x08000000,
    0x0C000000,
    0x10000000,
    0x20000000,
    0x40000000,
    0x60000000,
    0x80000000,
    0xA0000000,
    0xC0000000,
    0xE0000000,
    0xF0000000,
    0xF0100000,
    0xF0C00000,
    0xFFE00000,
    # from handoff mistaken value neighborhood
    0x68200000,
    0x6823B000,
]

print("\n=== fixed base probe (how many string VAs appear as aligned words) ===")
for base in CANDIDATE_BASES:
    hits = {}
    for name, soff in STRINGS.items():
        va = (base + soff) & 0xFFFFFFFF
        needle = struct.pack("<I", va)
        locs = []
        start = 0
        while True:
            p = dec.find(needle, start)
            if p < 0:
                break
            if p % 4 == 0:
                locs.append(p)
            start = p + 1
            if len(locs) >= 3:
                break
        if locs:
            hits[name] = locs
    if hits:
        print(f"  base=0x{base:08X} hits {len(hits)}/{len(STRINGS)}: {list(hits)}")

# Scan literal pools: after ARM functions, pools of addresses. Look for clusters
# where several nearby words point into the same image under one base.
print("\n=== sliding window: 8 consecutive words, consensus base across known strings ===")
soffs = list(STRINGS.values())
names = list(STRINGS.keys())
best = Counter()
examples = {}
for i in range(0, len(dec) - 32, 4):
    words = [struct.unpack_from("<I", dec, i + j)[0] for j in range(0, 32, 4)]
    # for each word, see if word-soff is same base for >=2 strings
    for w in words:
        for soff in soffs:
            base = (w - soff) & 0xFFFFFFFF
            if base & 0xFF:
                continue
            if base > 0xF8000000 or (base and base < 0x1000):
                continue
            matched = []
            for w2 in words:
                for n, s in STRINGS.items():
                    if w2 == ((base + s) & 0xFFFFFFFF):
                        matched.append(n)
            matched = sorted(set(matched))
            if len(matched) >= 2:
                best[base] += 1
                if base not in examples:
                    examples[base] = (i, matched)

for base, n in best.most_common(15):
    i, matched = examples[base]
    print(f"  base=0x{base:08X} window_hits={n} eg@0x{i:X} strings={matched}")
