#!/usr/bin/env python3
"""Locate U-Boot MD5 routine and guess what it hashes for all-in-one images."""
import struct
import hashlib
import re

ub = open("out/part_4_uboot.bin", "rb").read()
fw = open("C110.bin", "rb").read()
hdr = fw[:16]

# MD5 IV words
IV = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476]
for v in IV:
    p = ub.find(struct.pack("<I", v))
    print(f"IV 0x{v:08X} @ {hex(p) if p>=0 else 'missing'}")

# Dump nearby strings around MD5 match message for function names
print("\nStrings near MD5 messages:")
for m in re.finditer(rb"[ -~]{8,90}", ub[0x43000:0x44500]):
    print(f"  0x{0x43000+m.start():X}: {m.group().decode()}")

# Broader MD5-related strings
print("\nMD5-related strings in uboot:")
for s in [b"MD5", b"md5", b"checksum", b"nvtpack", b"all-in-one", b"all_in_one"]:
    i = 0
    while True:
        p = ub.find(s, i)
        if p < 0:
            break
        # show surrounding ascii
        ctx = ub[max(0, p - 20) : p + 60]
        ascii = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
        print(f"  {hex(p)}: {ascii}")
        i = p + 1

# Try more exotic header checksum ideas used by Novatek SDK
print("\n=== more checksum probes ===")


def check(label, digest):
    hit = digest == hdr
    print(f"  {'HIT' if hit else 'miss'} {label}: {digest.hex()}")


# Maybe MD5 of partition payloads only, excluding rtos compression? unlikely
# Maybe checksum is MD5 of bytes 0x10..0x1F + table + ... 
check("md5(0x10:0x20)", hashlib.md5(fw[0x10:0x20]).digest())
check("md5(0x10:0xBC)", hashlib.md5(fw[0x10:0xBC]).digest())

# NVTPACK: sometimes header is {md5, uiVersion, uiOffset, uiTotalSize?} 
# Try md5 over from table start
table_off, nparts, total = struct.unpack_from("<III", fw, 0x14)
check("md5(table..eof)", hashlib.md5(fw[table_off:]).digest())
check("md5(0x80:total)", hashlib.md5(fw[0x80:total]).digest())

# Zero out checksum, keep rest of header, hash whole file
z = bytearray(fw)
z[:16] = b"\x00" * 16
check("md5(zero16 + rest)", hashlib.md5(z).digest())

# Hash only resource headers: each 12-byte entry
entries = fw[0x80 : 0x80 + nparts * 12]
check("md5(entries)", hashlib.md5(entries).digest())
check("md5(hdr0x10-7F+entries)", hashlib.md5(fw[0x10:0x80] + entries).digest())

# Per-partition: size||data
blob = b""
for i in range(nparts):
    off, size, pid = struct.unpack_from("<III", fw, 0x80 + i * 12)
    blob += struct.pack("<III", off, size, pid) + fw[off : off + size]
check("md5(entry+data each)", hashlib.md5(blob).digest())

# Same but only data in order
blob = b"".join(fw[off : off + size] for off, size, pid in (struct.unpack_from("<III", fw, 0x80 + i * 12) for i in range(nparts)))
check("md5(part data ordered)", hashlib.md5(blob).digest())

# Try SHA1 first 16
check("sha1[:16] fw[0x10:]", hashlib.sha1(fw[0x10:]).digest()[:16])
check("sha1[:16] zero16", hashlib.sha1(z).digest()[:16])

# CRC-style 16-byte? unlikely

# Maybe the "MD5" is of the all-in-one WITHOUT the usr partition or WITHOUT rtos
for skip in [8, 6, 1, 3, 4]:
    blob = b""
    for i in range(nparts):
        off, size, pid = struct.unpack_from("<III", fw, 0x80 + i * 12)
        if pid == skip:
            continue
        blob += fw[off : off + size]
    check(f"md5(parts except id {skip})", hashlib.md5(blob).digest())

# Byte-swapped MD5 compare
d = hashlib.md5(fw[0x10:]).digest()
check("md5(0x10:) byteswapped32", b"".join(d[i : i + 4][::-1] for i in range(0, 16, 4)))
