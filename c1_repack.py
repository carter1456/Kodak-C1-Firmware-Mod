#!/usr/bin/env python3
"""
c1_repack.py - rebuild C110.bin from modified partitions / decompressed RTOS

Usage:
  python c1_repack.py --rtos-decompressed out/rtos_decompressed.bin -o C110_mod.bin --verify-roundtrip
  python c1_repack.py --boot-logo splash.jpg -o C110_logo.bin

Verified:
  - BCL LZ compressor (bcl_lz.py); literal mode remains available with --literal
  - BCL1 header: magic | u16 LE checksum | u16 BE algo | u32 BE usize | u32 BE csize
  - NVTPACK_FW_HDR2 whole-file checksum at offset 0x24 (ntk_checksum16)
  - Bytes 0x00-0x0F are the fixed HDR2 magic GUID (U-Boot memcmp). Copied unchanged.
    The "MD5 sum" strings in U-Boot are a flash read-back compare, not this field.

Not flash advice: a rebuilt image can be checksum-correct and still be rejected by
the menu update path, and a bad flash can brick the camera. See NOTES.md.
"""
from __future__ import annotations

import argparse
import io
import struct
import sys
from pathlib import Path

from bcl_lz import bcl_lz_compress, bcl_lz_decompress
from nvt_sum import (
    NVTPACK_FW_HDR2_MAGIC,
    patch_bcl1_checksum,
    patch_hdr2_file_checksum,
)

NAMES = {1: "fdt", 3: "fdt_app", 4: "uboot", 6: "rtos", 8: "usr"}
MARKER = 0xA6
BCL_ALGO_LZ = 0x0009


def bcl_lz_compress_literal(data: bytes, marker: int = MARKER) -> bytes:
    out = bytearray([marker])
    for b in data:
        if b == marker:
            out.append(marker)
            out.append(0)
        else:
            out.append(b)
    return bytes(out)


def build_bcl1(
    uncompressed: bytes,
    algo: int = BCL_ALGO_LZ,
    marker: int | None = None,
    literal: bool = False,
    window: int = 262144,
    chain: int = 48,
    lazy: bool = True,
) -> bytes:
    if literal:
        comp = bcl_lz_compress_literal(uncompressed, marker=MARKER if marker is None else marker)
    else:
        comp = bcl_lz_compress(
            uncompressed,
            marker=marker,
            max_offset=window,
            max_chain=chain,
            lazy=lazy,
        )
    hdr = bytearray(16)
    hdr[0:4] = b"BCL1"
    struct.pack_into("<H", hdr, 4, 0)  # checksum filled below
    struct.pack_into(">H", hdr, 6, algo & 0xFFFF)
    struct.pack_into(">I", hdr, 8, len(uncompressed))
    struct.pack_into(">I", hdr, 12, len(comp))
    return patch_bcl1_checksum(bytes(hdr) + comp)


def iter_jpegs(dec: bytes):
    """Yield (offset, size, width, height) for JPEGs Pillow can decode.

    Same scan as c1_unpack.py. Boot-logo frames are the 320x240 hits.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow is required to locate boot-logo JPEGs (pip install pillow)") from exc
    pos = 0
    while True:
        pos = dec.find(b"\xff\xd8\xff", pos)
        if pos < 0:
            return
        end = dec.find(b"\xff\xd9", pos + 3)
        while end != -1 and end - pos < 400000:
            blob = dec[pos : end + 2]
            try:
                im = Image.open(io.BytesIO(blob))
                im.load()
                yield pos, len(blob), im.size[0], im.size[1]
                break
            except Exception:
                end = dec.find(b"\xff\xd9", end + 2)
        pos += 3


def replace_boot_logos(dec: bytes, jpeg: bytes, index: int | None) -> bytes:
    """Overwrite 320x240 boot JPEGs in place. Shorter files are zero-padded.

    The span of each original JPEG is preserved so later pointers stay valid.
    """
    frames = [j for j in iter_jpegs(dec) if j[2] == 320 and j[3] == 240]
    if not frames:
        raise SystemExit("no 320x240 JPEGs found in the decompressed RTOS")
    if index is None:
        chosen = list(range(len(frames)))
    else:
        if index < 0 or index >= len(frames):
            raise SystemExit(f"--boot-logo-index {index} outside 0..{len(frames) - 1}")
        chosen = [index]
    out = bytearray(dec)
    for i in chosen:
        off, size, _w, _h = frames[i]
        if len(jpeg) > size:
            raise SystemExit(
                f"boot JPEG {i} at 0x{off:X} is {size} bytes; replacement is {len(jpeg)}"
            )
        out[off : off + len(jpeg)] = jpeg
        if len(jpeg) < size:
            out[off + len(jpeg) : off + size] = b"\x00" * (size - len(jpeg))
        print(f"boot JPEG {i} @ 0x{off:X}: {size} -> {len(jpeg)} bytes (padded to {size})")
    return bytes(out)


def parse_nvtpack(fw: bytes):
    table_off, nparts, total = struct.unpack_from("<III", fw, 0x14)
    parts = []
    for i in range(nparts):
        off, size, pid = struct.unpack_from("<III", fw, table_off + i * 12)
        parts.append({"id": pid, "off": off, "size": size, "data": fw[off : off + size]})
    return {
        "md5_or_unknown": fw[:16],
        "tag": struct.unpack_from("<I", fw, 0x10)[0],
        "table_off": table_off,
        "nparts": nparts,
        "total": total,
        "parts": parts,
    }


def _align(n: int, a: int) -> int:
    return (n + a - 1) & ~(a - 1)


def rebuild_nvtpack(
    tag: int,
    parts: list[dict],
    header16: bytes,
    align: int = 4,
    pad_tail: int = 4,
) -> bytes:
    """Rebuild NVTPACK_FW_HDR2. Fixes u16 checksum at 0x24. Copies the HDR2 magic at 0x00-0x0F."""
    if len(header16) != 16:
        raise ValueError("header16 must be 16 bytes")
    table_off = 0x80
    data_off = table_off + len(parts) * 12
    entries = []
    cur = data_off
    for p in parts:
        cur = _align(cur, align)
        entries.append((cur, len(p["data"]), p["id"], p["data"]))
        cur += len(p["data"])
    total = _align(cur, pad_tail) if pad_tail else cur
    out = bytearray(total)
    out[0:16] = header16
    struct.pack_into("<I", out, 0x10, tag)
    struct.pack_into("<I", out, 0x14, table_off)
    struct.pack_into("<I", out, 0x18, len(parts))
    struct.pack_into("<I", out, 0x1C, total)
    for i, (off, size, pid, data) in enumerate(entries):
        struct.pack_into("<III", out, table_off + i * 12, off, size, pid)
        out[off : off + size] = data
    out = bytearray(patch_hdr2_file_checksum(out))
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", default="C110.bin")
    ap.add_argument("--rtos-decompressed", help="replace RTOS with a BCL1 image of this file")
    ap.add_argument("--boot-logo", help="320x240 JPEG written over the boot-logo frames")
    ap.add_argument(
        "--boot-logo-index",
        type=int,
        help="replace only this 320x240 frame (0-based). Default: every frame that fits",
    )
    ap.add_argument("--algo", type=lambda x: int(x, 0), default=BCL_ALGO_LZ)
    ap.add_argument("--literal", action="store_true", help="literal BCL (decoder-legal, too big to flash)")
    ap.add_argument("--window", type=int, default=262144, help="BCL match window (default 262144)")
    ap.add_argument("--chain", type=int, default=48, help="hash-chain limit per position (default 48)")
    ap.add_argument("--no-lazy", action="store_true")
    ap.add_argument("--marker", type=lambda x: int(x, 0), help="force the BCL marker byte")
    ap.add_argument(
        "--header16-hex",
        help="override bytes 0x00-0x0F (32 hex chars). Default: HDR2 magic from the original",
    )
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--verify-roundtrip", action="store_true")
    args = ap.parse_args()

    fw = Path(args.original).read_bytes()
    meta = parse_nvtpack(fw)
    parts = []
    for p in meta["parts"]:
        data = p["data"]
        if p["id"] == 6 and (args.rtos_decompressed or args.boot_logo):
            if args.rtos_decompressed:
                dec = Path(args.rtos_decompressed).read_bytes()
            else:
                csize = struct.unpack(">I", data[12:16])[0]
                dec = bcl_lz_decompress(data[16 : 16 + csize])
                usize = struct.unpack(">I", data[8:12])[0]
                dec = dec[:usize]
            if args.boot_logo:
                jpeg = Path(args.boot_logo).read_bytes()
                if jpeg[:3] != b"\xff\xd8\xff":
                    raise SystemExit(f"{args.boot_logo} does not look like a JPEG")
                dec = replace_boot_logos(dec, jpeg, args.boot_logo_index)
            mode = "literal" if args.literal else "LZ"
            print(f"RTOS: BCL {mode} compress {len(dec)} bytes, algo=0x{args.algo:04X}")
            data = build_bcl1(
                dec,
                algo=args.algo,
                marker=args.marker,
                literal=args.literal,
                window=args.window,
                chain=args.chain,
                lazy=not args.no_lazy,
            )
            print(f"RTOS partition size {len(data)} (was {p['size']})")
            # Flash RTOS window from the boot FDT map: 0x1B0000..0xF00000.
            if len(data) > 0xD50000:
                print("WARNING: RTOS exceeds the flash partition (0xD50000)", file=sys.stderr)
            if args.verify_roundtrip:
                csize = struct.unpack(">I", data[12:16])[0]
                got = bcl_lz_decompress(data[16 : 16 + csize])[: len(dec)]
                if got != dec:
                    raise SystemExit("BCL roundtrip mismatch")
                print("BCL roundtrip OK")
        parts.append({"id": p["id"], "data": data})

    if args.header16_hex:
        header16 = bytes.fromhex(args.header16_hex)
    else:
        header16 = meta["md5_or_unknown"]
        if header16 != NVTPACK_FW_HDR2_MAGIC:
            print("WARNING: original bytes 0x00-0x0F are not the known HDR2 magic", file=sys.stderr)

    out = rebuild_nvtpack(meta["tag"], parts, header16=header16)
    Path(args.output).write_bytes(out)
    csum = struct.unpack_from("<H", out, 0x24)[0]
    print(
        f"wrote {args.output} ({len(out)} bytes), "
        f"magic={out[:16].hex()} HDR2 checksum @0x24=0x{csum:04X}"
    )
    if out[:16] != NVTPACK_FW_HDR2_MAGIC:
        print("WARNING: output magic is not the HDR2 GUID U-Boot compares", file=sys.stderr)


if __name__ == "__main__":
    main()
