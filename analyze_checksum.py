#!/usr/bin/env python3
"""Probe NVTPACK header checksum and BCL1 field 0xF5B20009."""
import hashlib
import struct
import zlib

fw = open("C110.bin", "rb").read()
hdr_sum = fw[:16]
print(f"Header checksum bytes: {hdr_sum.hex()}")
print(f"Version tag @0x10: 0x{struct.unpack_from('<I', fw, 0x10)[0]:08X}")
print(f"Table @0x14: 0x{struct.unpack_from('<I', fw, 0x14)[0]:X}")
print(f"Nparts @0x18: {struct.unpack_from('<I', fw, 0x18)[0]}")
print(f"Size @0x1C: {struct.unpack_from('<I', fw, 0x1C)[0]} (file={len(fw)})")

table_off, nparts, total = struct.unpack_from("<III", fw, 0x14)
parts = []
for i in range(nparts):
    off, size, pid = struct.unpack_from("<III", fw, table_off + i * 12)
    parts.append((pid, off, size))
    print(f"  part id={pid} off=0x{off:X} size=0x{size:X}")

rtos = open("out/part_6_rtos.bin", "rb").read()
dec = open("out/rtos_decompressed.bin", "rb").read()
bcl_field = struct.unpack(">I", rtos[4:8])[0]
print(f"\nBCL1 field: 0x{bcl_field:08X}")


def md5(b):
    return hashlib.md5(b).digest()


def try_md5(label, b):
    d = md5(b)
    match = d == hdr_sum
    print(f"  {'HIT' if match else 'miss'} MD5 {label}: {d.hex()}")
    return match


print("\n=== NVTPACK header MD5 probes ===")
try_md5("fw[0x10:]", fw[0x10:])
try_md5("whole file", fw)
zeroed = bytearray(fw)
zeroed[:16] = b"\x00" * 16
try_md5("file with hdr zeroed", bytes(zeroed))
zeroed2 = bytearray(fw)
zeroed2[:16] = b"\x00" * 16
struct.pack_into("<I", zeroed2, 0x1C, 0)
try_md5("hdr+size zeroed", bytes(zeroed2))
try_md5("bytes 0x10-0x7F", fw[0x10:0x80])
concat = b"".join(fw[off : off + size] for _, off, size in parts)
try_md5("partitions concat", concat)
try_md5("0x10-0x7F + partitions", fw[0x10:0x80] + concat)
# zero checksum region only, hash 0x00-end
try_md5("full with only 0x00-0x0F zero", bytes(zeroed))
# some Novatek packs hash from 0x10 through end-of-declared-size
try_md5("fw[0x10:total]", fw[0x10:total])
try_md5("fw[0x10:len]", fw[0x10 : len(fw)])
# header fields after checksum + each partition individually then combine?
# Try MD5 of each partition then XOR / concat of digests
digests = [md5(fw[off : off + size]) for _, off, size in parts]
try_md5("concat of per-part MD5s", b"".join(digests))
xored = bytearray(16)
for d in digests:
    for i, b in enumerate(d):
        xored[i] ^= b
print(f"  {'HIT' if bytes(xored)==hdr_sum else 'miss'} XOR of per-part MD5s: {bytes(xored).hex()}")

# U-Boot partition may contain the verify routine — search for the header bytes nearby
ub = open("out/part_4_uboot.bin", "rb").read()
print("\n=== U-Boot string locations (checksum / all-in-one) ===")
for s in [
    b"All-in-one image MD5 sum is not match",
    b"wrong all-in-one bin version",
    b"nvt_process_all_in_one",
    b"CONFIG_NVT_ALL_IN_ONE_IMG_SIZE",
    b"Your image size",
    b"RUNFW: Ignore T.bin loader",
]:
    p = ub.find(s)
    print(f"  {s.decode('ascii','replace')!r}: {hex(p) if p>=0 else 'NOT FOUND'}")

print("\n=== RTOS string locations (update path) ===")
for s in [
    b"A:\\C110.bin",
    b"cannot find %s",
    b"Alloc Temp Mem is NULL(uiFwSize=%d)",
    b"UPDATE OK",
    b"AllInOne_Step2",
    b"MsdcNvtCb_UpdFwSetBlock: Invalid Key",
    b"Delete firmware in A:\\",
    b"A:\\FW96565T.BIN",
    b"NVTDELFW",
]:
    locs = []
    start = 0
    while True:
        p = dec.find(s, start)
        if p < 0:
            break
        locs.append(p)
        start = p + 1
    print(f"  {s.decode('ascii','replace')!r}: {[hex(x) for x in locs]}")

print("\n=== BCL1 field probes ===")
payload = rtos[16:]
csize = struct.unpack(">I", rtos[12:16])[0]
comp = rtos[16 : 16 + csize]


def u32be_match(label, val):
    print(f"  {'HIT' if val == bcl_field else 'miss'} {label}: 0x{val & 0xFFFFFFFF:08X}")


u32be_match("CRC32(comp)", zlib.crc32(comp) & 0xFFFFFFFF)
u32be_match("CRC32(comp) inverted", (~zlib.crc32(comp)) & 0xFFFFFFFF)
u32be_match("CRC32(dec)", zlib.crc32(dec) & 0xFFFFFFFF)
u32be_match("Adler32(comp)", zlib.adler32(comp) & 0xFFFFFFFF)
u32be_match("Adler32(dec)", zlib.adler32(dec) & 0xFFFFFFFF)
u32be_match("sum32(comp)", sum(comp) & 0xFFFFFFFF)
u32be_match("sum32(dec)", sum(dec) & 0xFFFFFFFF)
# word sum LE
ws = 0
for i in range(0, len(comp) - 3, 4):
    ws = (ws + struct.unpack_from("<I", comp, i)[0]) & 0xFFFFFFFF
u32be_match("wordsum LE(comp)", ws)
ws = 0
for i in range(0, len(dec) - 3, 4):
    ws = (ws + struct.unpack_from("<I", dec, i)[0]) & 0xFFFFFFFF
u32be_match("wordsum LE(dec)", ws)
# MD5 first 4 bytes
u32be_match("MD5(comp)[:4] BE", struct.unpack(">I", md5(comp)[:4])[0])
u32be_match("MD5(dec)[:4] BE", struct.unpack(">I", md5(dec)[:4])[0])
u32be_match("MD5(comp)[:4] LE", struct.unpack("<I", md5(comp)[:4])[0])
u32be_match("MD5(rtos whole)[:4] BE", struct.unpack(">I", md5(rtos)[:4])[0])
# size xor
u32be_match("usize^csize", 11608936 ^ 6352748)
u32be_match("usize+csize", (11608936 + 6352748) & 0xFFFFFFFF)
