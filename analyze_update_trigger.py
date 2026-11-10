#!/usr/bin/env python3
"""Hunt strings/functions around the SD-card FW update trigger."""
import struct
import re

dec = open("out/rtos_decompressed.bin", "rb").read()
ub = open("out/part_4_uboot.bin", "rb").read()
fw = open("C110.bin", "rb").read()

needles = [
    b"C110FwUpdate",
    b"IQTestIsFwUpdate",
    b"FwUpdating",
    b"xFwSrv_CmdBinUpdateAllInOne",
    b"FW bin check",
    b"update finished",
    b"loader update",
    b"UIFlowWrnMsg",
    b"System_OnStrgInit",
    b"BinUpdate",
    b"AllInOne",
    b"nvtpack",
    b"0x16071515",
    b"16071515",
    b"OTAVERNUM",
    b"FW UPDATE",
    b"UseHidden",
    b"ENGINEER",
    b"KeyLock",
    b"UIFlowWnd",
    b"ShowBG",
]


def find_all(blob, s):
    out, i = [], 0
    while True:
        p = blob.find(s, i)
        if p < 0:
            return out
        out.append(p)
        i = p + 1


print("=== keyword hits in RTOS ===")
for s in needles:
    locs = find_all(dec, s)
    if locs:
        print(f"  {s!r}: {[hex(x) for x in locs[:12]]}{'...' if len(locs)>12 else ''}")

# Extract all printable strings near C110FwUpdate / update finished cluster
print("\n=== function-ish names containing Update/Fw/Bin near 0xA6AAF0 ===")
region = dec[0xA6A000:0xA6B500]
for m in re.finditer(rb"[ -~]{6,80}", region):
    t = m.group().decode()
    if any(k in t.lower() for k in ("update", "fw", "bin", "c110", "iq", "charg")):
        print(f"  0x{0xA6A000+m.start():X}: {t}")

print("\n=== names near 0x76C8A8 update cluster ===")
region = dec[0x76C000:0x76D200]
for m in re.finditer(rb"[ -~]{6,100}", region):
    t = m.group().decode()
    print(f"  0x{0x76C000+m.start():X}: {t}")

print("\n=== names near xFwSrv_CmdBinUpdateAllInOne @ 0x23B1C ===")
region = dec[0x23800:0x24500]
for m in re.finditer(rb"[ -~]{6,100}", region):
    t = m.group().decode()
    print(f"  0x{0x23800+m.start():X}: {t}")

# Version tag 0x16071515 as LE bytes in uboot/rtos (likely compared)
tag = struct.pack("<I", 0x16071515)
print(f"\n=== literal 0x16071515 LE occurrences ===")
print(f"  RTOS: {[hex(x) for x in find_all(dec, tag)[:20]]}")
print(f"  UBOOT: {[hex(x) for x in find_all(ub, tag)[:20]]}")
print(f"  FW file: {[hex(x) for x in find_all(fw, tag)[:20]]}")

# MD5 init constants in uboot (suggests real MD5 code present)
md5_k = struct.pack("<I", 0x67452301)  # A init
print(f"\n=== MD5 IV 0x67452301 in UBOOT: {[hex(x) for x in find_all(ub, md5_k)[:10]]}")
print(f"=== MD5 IV in RTOS: {[hex(x) for x in find_all(dec, md5_k)[:10]]}")

# Search usr partition
usr = open("out/part_8_usr.bin", "rb").read()
print(f"\n=== usr partition ({len(usr)} bytes) ===")
print(repr(usr[:200]))
for m in re.finditer(rb"[ -~]{4,80}", usr):
    print(f"  {m.group().decode()}")
