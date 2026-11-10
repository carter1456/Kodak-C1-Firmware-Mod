# Firmware pack

Stock file: `C110.bin`, v1.04, 6,996,860 bytes. Every field below is **VERIFIED** on that file unless the line says otherwise. Offsets and the disassembly behind them are in [`NOTES.md`](../NOTES.md).

## All-in-one header

| Offset | Field | Stock value |
|---|---|---|
| `0x00–0x0F` | HDR2 magic GUID | `072e01d6bc10914fb28a352f82261a50` |
| `0x10` | version, u32 LE | `0x16071515` |
| `0x14` | partition table offset, u32 LE | `0x80` |
| `0x18` | partition count, u32 LE | 5 |
| `0x1C` | total size, u32 LE | 6,996,860 |
| `0x24` | whole-file checksum, u16 LE | `0xD4C1` |

U-Boot compares the 16-byte magic (U-Boot file `0x458DC`) and then requires the u16 at `0x24` to make the Novatek sum zero. The strings about an "MD5 sum" are a later read-back of the image buffer after the partitions are written. They are not a hash of those 16 bytes.

`python nvt_sum.py` prints the magic, the version, and the `@0x24` check. Run `python c1_unpack.py C110.bin out` first if you also want the BCL1 line. It reads `out/part_6_rtos.bin`.

The RAM cap is **0x02000000 (32 MiB)**, the immediate at U-Boot file `0xA1F4`. A later compare against `0x04940000` is the `CONFIG_NVT_RUNFW_SDRAM_BASE` overlap check, not this cap.

## Partitions

The table at `0x80` is 12-byte records: offset, size, id, all little-endian.

| Id | Name | Role |
|---|---|---|
| 1 | fdt | Boot device tree |
| 3 | fdt.app | App device tree |
| 4 | uboot | U-Boot, load VA `0x07140000` |
| 6 | rtos | FreeRTOS image, load VA `0x00010000` |
| 8 | usr | Small trailing partition |

The flash window for the RTOS partition is `0x1B0000–0xF00000`, which is `0xD50000` bytes (13,959,168).

## RTOS container (BCL1)

| Offset | Field | Stock |
|---|---|---|
| `0x00` | magic | `BCL1` |
| `0x04` | checksum, u16 LE | makes `nvt_sum` of the container 0 |
| `0x06` | algorithm, u16 BE | `0x0009` (LZ) |
| `0x08` | uncompressed size, u32 BE | 11,608,936 |
| `0x0C` | compressed size, u32 BE | 6,352,748 |

The payload is Marcus Geelnard's BCL LZ. The first byte is the marker (`0xA6` on stock). `marker 0x00` stores a literal marker. Otherwise a match is `marker`, a varint length, and a varint offset. Varints are 7-bit big-endian with the high bit meaning "continue."

`bcl_lz.py` defaults (window 262144, chain 48, lazy matching) compress that RTOS to 6,228,160 bytes and decompress back to the same 11,608,936 bytes. `c1_repack.py` wraps that payload in a new BCL1 header, copies the HDR2 magic, and rewrites `@0x24`.

A rebuilt image is smaller than stock because the RTOS payload is smaller and because the packer aligns partitions to 4 bytes. Partitions 1, 3, 4, and 8 stay byte-identical. The gaps between them do not.
