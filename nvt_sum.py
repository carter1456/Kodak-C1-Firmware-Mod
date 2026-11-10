#!/usr/bin/env python3
"""Novatek checksum helpers (VERIFIED on C110.bin)."""
from __future__ import annotations

import struct
from array import array


def ntk_checksum16(data: bytes | bytearray, start: int, length: int, ignore_relative: int) -> int:
    """Position-weighted signed-word two's-complement checksum (NVTPACK_FW_HDR2 / BCL1).

    Matches OpenIPC nvtpack_calc_nvt_sum / Suntek patch_ae.ntk_checksum16 / NTKFWinfo.
    Odd trailing byte is ignored. `ignore_relative` is offset within the range of the
    u16 field that is zeroed during calculation.
    """
    word_count = length // 2
    even_length = word_count * 2
    if start < 0 or start + even_length > len(data) or word_count == 0:
        raise ValueError(f"checksum range outside data: start=0x{start:x} length={length}")
    if ignore_relative < 0 or ignore_relative + 2 > even_length or ignore_relative % 2:
        raise ValueError(f"invalid ignore offset +0x{ignore_relative:x}")

    words = array("h")
    words.frombytes(bytes(data[start : start + even_length]))
    words[ignore_relative // 2] = 0
    total = (sum(words) + (word_count - 1) * word_count // 2) & 0xFFFF
    return (-total) & 0xFFFF


def nvt_sum(data: bytes) -> int:
    """Raw sum of (index + LE_u16) mod 65536 over complete words (no two's complement)."""
    s = 0
    n = len(data) // 2
    for i in range(n):
        w = data[i * 2] | (data[i * 2 + 1] << 8)
        s = (s + i + w) & 0xFFFF
    return s


def patch_bcl1_checksum(blob: bytes | bytearray) -> bytes:
    """Set BCL1 bytes 4..5 so nvt_sum(container)==0. Algo field at 6..7 is preserved."""
    out = bytearray(blob)
    if out[:4] != b"BCL1":
        raise ValueError("not a BCL1 blob")
    csize = struct.unpack(">I", out[12:16])[0]
    out = out[: 16 + csize]
    out[4:6] = b"\x00\x00"
    csum = ntk_checksum16(out, 0, len(out), 4)
    struct.pack_into("<H", out, 4, csum)
    if nvt_sum(out) != 0:
        raise RuntimeError("BCL1 checksum patch failed self-check")
    return bytes(out)


# VERIFIED: U-Boot memcmp's the first 16 bytes of an all-in-one image against this
# constant (part_4_uboot.bin file offset 0x458DC) and only then checks the u16 sum.
# It is a format magic, not a digest of the payload. HDR1 is the older 16-byte magic
# the same parser scans for if the HDR2 magic misses.
NVTPACK_FW_HDR2_MAGIC = bytes.fromhex("072e01d6bc10914fb28a352f82261a50")
NVTPACK_FW_HDR1_MAGIC = bytes.fromhex("90be2788cd36c24fa98773a8484e84b1")
NVTPACK_FW_HDR2_VERSION = 0x16071515


def patch_hdr2_file_checksum(fw: bytes | bytearray) -> bytes:
    """Set NVTPACK_FW_HDR2 whole-file checksum at offset 0x24 (VERIFIED on C110.bin)."""
    out = bytearray(fw)
    struct.pack_into("<H", out, 0x24, 0)
    csum = ntk_checksum16(out, 0, len(out), 0x24)
    struct.pack_into("<H", out, 0x24, csum)
    return bytes(out)


if __name__ == "__main__":
    from pathlib import Path

    fw = Path("C110.bin").read_bytes()
    magic = fw[:16]
    print(
        f"HDR2 magic @0x00 {magic.hex()} "
        f"ok={magic == NVTPACK_FW_HDR2_MAGIC} (fixed GUID, not a payload MD5)"
    )
    version = struct.unpack_from("<I", fw, 0x10)[0]
    print(f"HDR2 version @0x10 0x{version:08X} ok={version == NVTPACK_FW_HDR2_VERSION}")
    stored = struct.unpack_from("<H", fw, 0x24)[0]
    calc = ntk_checksum16(fw, 0, len(fw), 0x24)
    print(f"HDR2 @0x24 stored=0x{stored:04X} calc=0x{calc:04X} ok={stored == calc}")

    rtos = Path("out/part_6_rtos.bin").read_bytes()
    csize = struct.unpack(">I", rtos[12:16])[0]
    blob = rtos[: 16 + csize]
    print(f"BCL1 sum={nvt_sum(blob):04X} (expect 0)")
    patched = patch_bcl1_checksum(blob)
    print(f"BCL1 repatch field=0x{struct.unpack_from('<H', patched, 4)[0]:04X} match={patched[4:6] == blob[4:6]}")
