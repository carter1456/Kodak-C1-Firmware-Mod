# Cursor Cloud / agent handoff — Kodak PixPro C1 firmware

Read this file first, then `NOTES.md`, then `c1-cursor-handoff.md` for history.
Prefer **NOTES.md** over the older handoff where they disagree.

## Goal

Custom firmware for a Kodak PixPro C1 (Novatek NA51089, ARM Cortex-A9, FreeRTOS, LVGL). Owner accepts brick risk. Camera may be offline — do offline analysis/tooling first.

Priority order:
1. Header bytes `0x00–0x0F` — **solved**: fixed HDR2 magic, not a digest (see NOTES)
2. BCL LZ compressor — `bcl_lz.py` (literal encoder remains too large for flash)
3. Boot-logo JPEG swap — `c1_repack.py --boot-logo` (on disk only)
4. SD/menu update trigger — **mapped**: `UISetupObj` event `0x14080000` calls the uploader directly. In the const background table, id **`0x0C`** is `BackgroundFWUpdate` and id `0x0D` is `PhotoExe_DZoomInBK`. Id `0x0C` is posted by `UIWifiCmdObj` event `0x1402001F` and by `C110FwUpdate` after `A:\C110.bin` opens. The live background table pointer is BSS `0xC2BC18`; that it is a copy of the const table is **UNVERIFIED**. The LCD label for `0x14080000` is **UNVERIFIED**. Card insert does not call the uploader.
5. PIN lock, hidden features — only after a real update has been shown to run

## Environment

- Python 3 (`python`, not `python3` on Windows hosts)
- Firmware: `C110.bin` in repo root (v1.04, 6,996,860 bytes)
- Unpack: `python c1_unpack.py C110.bin out` → expect `out/rtos_decompressed.bin` size **11608936** and **10** JPEGs in `out/jpegs/`
- Optional: `pip install pillow` for JPEG extraction

## Verified facts (do not re-litigate)

| Item | Fact |
|---|---|
| Pack format | NVTPACK_FW_HDR2, version `@0x10 = 0x16071515` |
| Outer checksum | **u16 LE @ `0x24`**, `ntk_checksum16` — see `nvt_sum.py` |
| Bytes `0x00–0x0F` | **Fixed HDR2 magic** `072e01d6bc10914fb28a352f82261a50`. U-Boot `memcmp`s it (file `0x458DC`). The “MD5 sum” strings are a flash read-back compare |
| RTOS container | BCL1: magic \| u16 LE csum \| u16 BE algo(`9`=LZ) \| u32 BE usize \| u32 BE csize |
| BCL1 csum | Same Novatek sum; whole container sums to 0 — `patch_bcl1_checksum` |
| RTOS load VA | **`0x00010000`** (from FDT `nvt_memory_cfg`) |
| U-Boot load VA | **`0x07140000`** |
| `UseHiddenF` | Substring of `SetUseHiddenFirst` — **not** a hidden-features flag |
| All-in-one RAM cap | **`CONFIG_NVT_ALL_IN_ONE_IMG_SIZE = 0x02000000` (32 MiB)**. U-Boot file `0xA1F4`. Stock and both rebuilds are under it |
| Background FW id | Const table at file `0xAEE7DC`: **`0x0C`** → `BackgroundFWUpdate` (file `0x42286C`). Posted by WiFi event `0x1402001F` and by `C110FwUpdate`. Id `0x0D` is `PhotoExe_DZoomInBK`. Live table pointer is BSS `0xC2BC18` (**UNVERIFIED** that it matches the const array) |

## Key tools

| File | Role |
|---|---|
| `c1_unpack.py` | Split NVTPACK + BCL LZ decompress + JPEG extract |
| `nvt_sum.py` | HDR2 magic + `@0x24` + BCL1 checksum (verified) |
| `bcl_lz.py` | BCL LZ compress and decompress |
| `c1_repack.py` | Rebuild pack (real LZ), `@0x24`, optional `--boot-logo` |
| `analyze_*.py` | One-off probes (safe to extend or delete) |

## Ghidra

- RTOS: `out/rtos_decompressed.bin`, ARM v7 LE, base **`0x00010000`**
- U-Boot: `out/part_4_uboot.bin`, base **`0x07140000`**
- MD5 verify path ~ file `0x959C` / MD5 impl `0x3614C` in U-Boot
- Update strings: `A:\C110.bin` @ RTOS file `0x76C8A8`; `System_OnStrg_UploadFW`, `Do FW Update`

## Safety

- No `A:\NVTDELFW`
- No flash advice without SPI NOR backup plan
- Never claim a patched image is flash-safe. Magic, `@0x24`, and the 32 MiB cap can all be satisfied while the on-camera menu path is still untested, and a bad flash can brick the camera.
- Be explicit VERIFIED vs STRINGS ONLY vs UNVERIFIED

## Suggested checks

1. `python c1_unpack.py C110.bin out` — decompressed RTOS is 11608936 bytes, 10 JPEGs
2. `python nvt_sum.py` — magic, `@0x24`, and BCL1 all print ok
3. `python c1_repack.py --rtos-decompressed out/rtos_decompressed.bin -o C110_mod.bin --verify-roundtrip`
4. Boot-logo repack stays on disk. Do not flash it.
