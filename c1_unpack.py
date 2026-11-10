#!/usr/bin/env python3
"""
c1_unpack.py - Kodak PixPro C1 (C110.bin) unpacker
Usage:  python c1_unpack.py C110.bin outdir

Does:
  1. Parses the NVTPACK header + 5-entry partition table (at 0x80, 12 bytes each: offset,size,id; LE)
  2. Writes each partition to outdir/part_<id>_<name>.bin
  3. Decompresses the RTOS partition (id 6). Its 16-byte "BCL1" header is:
        'BCL1' | u16 LE checksum | u16 BE algo (9 = LZ) | u32 BE uncompressed | u32 BE compressed
     Payload = Marcus Geelnard BCL "LZ" stream: first byte is the marker (0xA6 on stock),
     marker+0x00 = literal marker, marker+varlen+varoff = copy. Varints are 7-bit big-endian, high bit = continue.
  4. Extracts every valid JPEG from the decompressed image (boot-logo animation frames etc.)
Requires: Pillow (pip install pillow) for JPEG validation (optional).
"""
import struct, sys, os, io

NAMES = {1: "fdt", 3: "fdt_app", 4: "uboot", 6: "rtos", 8: "usr"}


def read_varsize(buf, pos):
    y = 0
    n = 0
    while True:
        x = buf[pos + n]
        y = (y << 7) | (x & 0x7F)
        n += 1
        if not (x & 0x80):
            break
    return y, n


def bcl_lz_decompress(inp):
    marker = inp[0]
    i = 1
    out = bytearray()
    while i < len(inp):
        s = inp[i]
        i += 1
        if s == marker:
            if inp[i] == 0:
                out.append(marker)
                i += 1
            else:
                length, n = read_varsize(inp, i); i += n
                offset, n = read_varsize(inp, i); i += n
                if offset == 0 or offset > len(out):
                    raise ValueError(f"bad offset {offset} (in={i}, out={len(out)})")
                for _ in range(length):
                    out.append(out[-offset])
        else:
            out.append(s)
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    fw = open(sys.argv[1], "rb").read()
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)

    table_off, nparts, total = struct.unpack_from("<III", fw, 0x14)
    print(f"NVTPACK: table@0x{table_off:X}, {nparts} partitions, size {total}")
    rtos = None
    for i in range(nparts):
        off, size, pid = struct.unpack_from("<III", fw, table_off + i * 12)
        name = NAMES.get(pid, f"id{pid}")
        data = fw[off:off + size]
        open(os.path.join(out, f"part_{pid}_{name}.bin"), "wb").write(data)
        print(f"  id {pid} {name:8s} off=0x{off:08X} size=0x{size:08X}")
        if pid == 6:
            rtos = data

    assert rtos[:4] == b"BCL1"
    csum = struct.unpack_from("<H", rtos, 4)[0]
    algo = struct.unpack_from(">H", rtos, 6)[0]
    usize, csize = struct.unpack_from(">II", rtos, 8)
    print(f"BCL1: checksum=0x{csum:04X} algo=0x{algo:04X} uncompressed={usize} compressed={csize}")
    dec = bcl_lz_decompress(rtos[16:16 + csize])[:usize]
    print(f"decompressed {len(dec)} bytes (expected {usize})")
    open(os.path.join(out, "rtos_decompressed.bin"), "wb").write(dec)

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skipping JPEG extraction")
        return
    jd = os.path.join(out, "jpegs")
    os.makedirs(jd, exist_ok=True)
    pos = 0
    n = 0
    while True:
        pos = dec.find(b"\xff\xd8\xff", pos)
        if pos < 0:
            break
        end = dec.find(b"\xff\xd9", pos + 3)
        while end != -1 and end - pos < 400000:
            try:
                im = Image.open(io.BytesIO(dec[pos:end + 2]))
                im.load()
                n += 1
                open(os.path.join(jd, f"img_{n:03d}_0x{pos:X}_{im.size[0]}x{im.size[1]}.jpg"), "wb").write(dec[pos:end + 2])
                break
            except Exception:
                end = dec.find(b"\xff\xd9", end + 2)
        pos += 3
    print(f"extracted {n} valid JPEGs to {jd}")


if __name__ == "__main__":
    main()
