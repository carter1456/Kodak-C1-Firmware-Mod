#!/usr/bin/env python3
"""Find RTOS load base by correlating pointers to known strings."""
import struct
from collections import defaultdict

RTOS = open("out/rtos_decompressed.bin", "rb").read()

STRINGS = [
    ("KODAKPIXPRO C1", 0x75DA1C),
    ("UseHiddenF", 0xA9CB27),
    ("ENGINEER", 0xA6F08C),
    ("KeyLock", 0xA6B7BF),
    ("A:\\C110.bin", 0x76C8A8),
    ("A:\\C110.bin#2", 0xAECAA4),
    ("logo_bs", 0x76C094),
    ("AutoFuncTestFlashlvl", 0xA6618C),
    ("lv_plugin_install_resource", 0xA643B4),
]

print("String checks:")
for name, off in STRINGS:
    raw = name.split("#")[0].encode()
    found = RTOS[off : off + len(raw)]
    print(f"  {'OK' if found == raw else 'MISS'} 0x{off:X} {name!r}")

# base -> {canonical_name: [xref_file_offs]}
hits = defaultdict(lambda: defaultdict(list))

for i in range(0, len(RTOS) - 3, 4):
    (w,) = struct.unpack_from("<I", RTOS, i)
    for name, soff in STRINGS:
        base = (w - soff) & 0xFFFFFFFF
        if base & 0xFFF:
            continue
        if base < 0x10000 or base > 0xE0000000:
            continue
        file_off = (w - base) & 0xFFFFFFFF
        if file_off != soff:
            continue
        cname = name.split("#")[0]
        bucket = hits[base][cname]
        if len(bucket) < 8:
            bucket.append(i)

ranked = sorted(hits.items(), key=lambda kv: (-len(kv[1]), kv[0]))
print("\nCandidate bases covering >= 3 distinct strings:")
nshow = 0
canon_total = len({n.split("#")[0] for n, _ in STRINGS})
for base, by_name in ranked:
    if len(by_name) < 3:
        break
    print(f"\n  base=0x{base:08X}  covers {len(by_name)}/{canon_total}: {sorted(by_name)}")
    for name, soff in STRINGS:
        cname = name.split("#")[0]
        locs = by_name.get(cname)
        if not locs:
            continue
        # Only print once per canonical name
        if name.endswith("#2"):
            continue
        va = (base + soff) & 0xFFFFFFFF
        # For C110.bin show both string sites if both hit via same name key — handled below
        print(f"    {cname}: VA 0x{va:08X}  xrefs @ {[hex(x) for x in locs[:4]]}")
    # Extra: show both C110.bin sites under this base
    for name, soff in STRINGS:
        if not name.startswith("A:\\C110.bin"):
            continue
        target = (base + soff) & 0xFFFFFFFF
        needle = struct.pack("<I", target)
        locs = []
        start = 0
        while True:
            p = RTOS.find(needle, start)
            if p < 0:
                break
            if p % 4 == 0:
                locs.append(p)
            start = p + 1
            if len(locs) >= 4:
                break
        if locs:
            print(f"    {name} file 0x{soff:X} VA 0x{target:08X} xrefs {[hex(x) for x in locs]}")
    nshow += 1
    if nshow >= 10:
        break

if nshow == 0:
    print("  none with 4K alignment; retrying 4-byte alignment (top 10)")
    hits.clear()
    for i in range(0, len(RTOS) - 3, 4):
        (w,) = struct.unpack_from("<I", RTOS, i)
        for name, soff in STRINGS:
            base = (w - soff) & 0xFFFFFFFF
            if base & 3:
                continue
            if base < 0x1000 or base > 0xE0000000:
                continue
            if ((w - base) & 0xFFFFFFFF) != soff:
                continue
            cname = name.split("#")[0]
            bucket = hits[base][cname]
            if len(bucket) < 4:
                bucket.append(i)
    for base, by_name in sorted(hits.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f"  base=0x{base:08X} covers {len(by_name)}: {sorted(by_name)}")
