# Kodak PixPro C1 Custom Firmware: Handoff to Cursor

Written 2026-11-09. Everything below was learned in a long Claude session. Items are labeled **VERIFIED** (reproduced by running code on the real C110.bin), **STRINGS ONLY** (text exists in the binary, behavior unproven), or **UNVERIFIED** (an assumption). Where an earlier claim in the session turned out wrong, it is listed in the Corrections section. Trust this document over the earlier chat.

---

## 1. Goal

Make the Kodak PixPro C1 feel like a 2000s digital camera while staying modern. The owner does not care if the camera gets bricked.

Priority feature list:

**Needs (first)**
- Camera lock screen with a PIN entered using the up/down/left/right wheel, with a "Lock" entry on the mode menu
- Stronger flash
- Unlock hidden or disabled features (the firmware has a hidden-features flag and an ENGINEER mode)
- Custom UI strings, date stamp on photos, longer auto-off, wider EV range

**Wants**
- Retro 2000s UI theme and icons, custom boot splash, custom shutter and UI sounds
- Check whether WiFi, RTSP live view, and UVC webcam mode are really usable on this hardware
- Long exposure, manual ISO, AE/AF lock, macro toggle, grid overlay, LCD brightness, timelapse intervals

**Reaches**
- RAW (Bayer) capture, film-emulation color profiles (ISP tuning lives in the fdt.app partition), film-roll counter with rewind animation, double exposure, shared community config file on the SD card

---

## 2. Environment

- Owner machine: Windows, PowerShell, Python 3.14 (use `python`, not `python3`)
- Firmware file: `C:\Users\carte\OneDrive\Desktop\C110.bin` (6,996,860 bytes, firmware v1.04)
- Camera mounts over USB-C as drive `D:` (contains `DCIM` and a copy of `C110.bin` in the root)
- Files from this session: `c1_unpack.py` (working unpacker), `kodak_c1_patch.py` (old, see Corrections, do not reuse as-is)

---

## 3. Hardware and platform (mostly VERIFIED)

- SoC: Novatek NA51089 family (NT96565 / FW96565 strings), ARM Cortex-A9, FreeRTOS, no Linux
- 16 MB SPI NOR flash
- LCD: ST7789V ("rt28qv090a"), 2.8", 240x320 portrait panel
- Sensor: OV13B10 (13 MP)
- UI: LVGL, exported from LVGLBuilder (source path `SrcCode/UIWnd/LVGL_SPORTCAM`)
- Build path in binary: `/home/nvt03406/na51055_bsp/221215_56x_sdk/ivot`
- Model strings: `KODAKPIXPRO C1`, `KODC1`

Flash partition map (from the boot device tree):

| Partition | Flash range | Size |
|---|---|---|
| loader | 0x000000-0x010000 | 64 KB |
| fdt | 0x010000-0x050000 | 256 KB |
| fdt.restore | 0x080000-0x0C0000 | 256 KB |
| fdt.app | 0x0C0000-0x100000 | 256 KB |
| uboot | 0x100000-0x170000 | 448 KB |
| uenv | 0x170000-0x1B0000 | 256 KB |
| rtos | 0x1B0000-0xF00000 | about 13.3 MB |
| pstore | 0xF00000-0xFF0000 | 960 KB |
| usr | 0xFF0000-0x1000000 | 64 KB |

---

## 4. Firmware file format (VERIFIED)

`C110.bin` is an NVTPACK all-in-one image.

```
0x00  16 B   header checksum (looks like MD5, algorithm NOT solved, see section 8)
0x10   4 B   0x16071515 (version/date tag)
0x14   4 B   partition table offset = 0x80
0x18   4 B   partition count = 5
0x1C   4 B   total file size = 0x6AC37C
0x80   5 x 12 B entries, little-endian: offset, size, partition id
```

| id | name | file offset | size |
|---|---|---|---|
| 1 | fdt | 0x0000BC | 0x457E |
| 3 | fdt.app (ISP/IQ tables) | 0x00463C | 0x3CC18 |
| 4 | uboot | 0x04127C | 0x5BD34 |
| 6 | rtos | 0x09CFBC | 0x60EF7C |
| 8 | usr | 0x6ABF3C | 0x40F (contains `OTAVERNUM:1.04;`) |

### The RTOS partition is compressed (this was the big discovery)

The 16-byte header on the rtos partition is **not** a load-address header. It is:

```
'BCL1' | u32 BE 0xF5B20009 (unknown, maybe checksum) | u32 BE 11,608,936 (uncompressed) | u32 BE 6,352,748 (compressed)
```

The payload is a Marcus Geelnard BCL "LZ" stream. First payload byte is the marker (0xA6). `marker 0x00` means a literal marker byte. `marker, varint length, varint offset` means copy from earlier output. Varints are 7-bit big-endian with the high bit meaning "more bytes follow". `c1_unpack.py` implements this and produces exactly 11,608,936 bytes whose first words are a valid ARM vector table (0xEA006E5E, 0xEA000027, 0xE59FF014...).

This explains why everything before it was confusing: 0xA6 was 10% of all bytes, strings appeared in literal runs, pixel data and pointers looked like noise or pointed past the end of the file.

---

## 5. Corrections to earlier claims

1. **All "RTOS+0x..." offsets from earlier were offsets into the compressed stream.** They are not valid for patching meaning. Use the decompressed offsets in section 6.
2. **"Load address 0x6823B100" was a misread.** That number came from reading the header at the wrong alignment. The real base address of the decompressed image is not yet known (section 9 explains how to find it).
3. **The `$UseHiddenF` to `$UseHiddenT` patch was a guess.** It edited a text string in the compressed stream, never reached any code, and its checksum was a guess. It could not have worked. Do not reuse `kodak_c1_patch.py`.
4. **The `$` in front of names like `$UseHiddenF` was an artifact** of compressed-stream bytes. In the decompressed image the string is `UseHiddenF`.
5. **The "20 LVGL image descriptors at 0x600340" are unreliable**, found in compressed data. Redo that search on the decompressed image.
6. **Feature claims (WiFi stack, RTSP, RAW, beauty mode, etc.) are STRINGS ONLY.** Code strings exist. Nothing proves the hardware (WiFi chip, flash driver) is present or that menus can reach them.
7. **"Flash can be boosted 20-30% safely" is UNVERIFIED.** It is not known whether the flash is a duty-cycle LED driver or a charge/capacitor circuit. Treat any flash change as an experiment.
8. The statement that the camera "never bricks from a rejected update" was an assumption about U-Boot behavior, not tested.

---

## 6. Key offsets in the DECOMPRESSED RTOS image (VERIFIED, from `rtos_decompressed.bin`)

| Item | Offset |
|---|---|
| `KODAKPIXPRO C1` | 0x75DA1C |
| `UseHiddenF` | 0xA9CB27 |
| `ENGINEER` | 0xA6F08C |
| `KeyLock` | 0xA6B7BF |
| `AutoFuncTestFlashlvl` | 0xA6618C |
| `lv_plugin_install_resource` | 0xA643B4 |
| `xSound` (several) | 0xA6BF59, 0xA6C101, 0xA6C151, 0xA6C16D |
| `logo_bs` | 0x76C094 |
| `datastamp` (several) | 0x20E227, 0x20E264, ... |
| `A:\C110.bin` | 0x76C8A8, 0xAECAA4 |
| `A:\testcard` | 0x76DC18 |
| `A:\bootlang` | 0xA678F0 |
| `A:\iqTestFw` | 0xA6AAA0 |
| `A:\auto` | 0xA681D8, 0xA68294 |
| `A:\FW96565T.BIN` / `T.BIN` | near 0x77230A |
| Boot logo JPEG frames (320x240) | 0x776C3C, 0x778364, 0x778A8C, 0x77A1B4, 0x77B7B8, 0x77CAF0, 0x77DC40, 0x77ED90 (+2 more; run the script) |

The 10 extracted JPEGs are the boot-logo animation: a red/white "KODAK PIXPRO C1 / DIGITAL CAMERA" wordmark sliding in on black, 320x240. This is the first real UI asset recovered and a direct target for the retro splash.

Other evidence worth knowing (all STRINGS ONLY unless noted):
- RTOS update code: `A:\C110.bin`, `cannot find %s`, `Alloc Temp Mem is NULL(uiFwSize=%d)`, `UPDATE OK`, `AllInOne_Step2`
- Second update path over USB: `MsdcNvtCb_UpdFwSetBlock: Invalid Key`, `Delete firmware in A:\`, `A:\FW96565T.BIN` (Novatek's PC tool talks to the camera over MSDC vendor commands)
- U-Boot strings: `All-in-one image MD5 sum is not match`, `wrong all-in-one bin version`, `nvt_process_all_in_one: TotalRes = %d`, `Your image size ... is larger than all-in-one size`, `CONFIG_NVT_ALL_IN_ONE_IMG_SIZE`, `RUNFW: Ignore T.bin loader`
- Input: `DrvKey_DetNormalKey`, `NVT_KEY_EVENT`, `KeyLock`, `indev_keypad_group`
- Persistence: `SysGetFlag`/`SysSetFlag` style flags, `pstore`, `xsave pstore info`
- UI: `UIFlowWnd`, `ShowBG`, `lv_msgbox`, `lv_font`, `LV_PLUGIN_EVENT_SCR_OPEN`
- Features: TIMELAPSE, HDR/SHDR, NIGHTMOD, color effects (MONO, Retro, Cool, Warm), WDR, beauty/portrait, long exposure, Bayer/RAW encode, UVC/PC camera, RTSP, FTP, WiFi/AP strings
- Hidden-feature gating: `UseHiddenF`, `[ENGINEER]` mode (references NT98560/NT98562)

---

## 7. What has been tried on the real camera and the results

- Copied the (invalid) patched `C110.bin` to the SD card root over USB mass storage. File size correct (6,996,860 bytes), in the root next to `DCIM`. **Camera booted normally, no update screen, no error, firmware version in settings unchanged.**
- Held SHUTTER, DOWN, MODE, MENU, and MODE+SHUTTER during power-on: **no reaction.**
- The SD probe files (`testcard`, `bootlang`, `iqTestFw`, `auto`) were planned but **results were never reported.** Treat them as untested.
- Button-combo and menu-tree surveys were requested but **never reported.**

Why the camera ignored `C110.bin` is **unknown.** Candidates:
1. The update runs only from a menu item or button-at-boot combination that has not been found
2. A version or content check rejects it silently (`wrong all-in-one bin version`, MD5 header)
3. The trigger depends on state (battery level, file timestamp, firmware version in `usr`)

---

## 8. Open problems

1. **Update trigger.** Find the code that reads `A:\C110.bin` and what must be true for it to run.
2. **Header checksum.** NVTPACK bytes 0x00-0x0F are likely MD5, but none of these matched: MD5 of `fw[0x10:]`, of the whole file with the header zeroed, of all partitions concatenated, of header bytes 0x10-0x7F plus partitions, and of the file with checksum and size fields zeroed. The BCL1 field `0xF5B20009` also matched none of: CRC32, inverted CRC32, Adler32, or 32-bit word sum of either the compressed or decompressed data.
3. **Recompression.** Patching code means regenerating a BCL1 stream. Option A: write a real BCL LZ compressor. Option B (UNVERIFIED): emit a literal-only stream (marker byte, then every byte raw, with each 0xA6 written as `A6 00`). The decoder accepts this, but it is about 11.6 MB, and the firmware size limit (`CONFIG_NVT_ALL_IN_ONE_IMG_SIZE`) and partition size (about 13.3 MB) must allow it.
4. **Load base address** of the decompressed image (needed for Ghidra).
5. **Where LVGL pixel data actually lives** (descriptors need to be re-found in the decompressed image).

---

## 9. Recommended plan, in order

**Step 0. Back up the flash first.** The only real safety net if a flash goes wrong is a clean 16 MB SPI dump (CH341A programmer plus SOIC-8 clip, read the chip three times and compare hashes). Without that, a bad RTOS flash may be unrecoverable. Do this before any attempted update that might succeed.

**Step 1. Reproduce the unpack.**
```
python c1_unpack.py C110.bin out
```
Confirm `rtos_decompressed.bin` is 11,608,936 bytes and 10 JPEGs appear.

**Step 2. Ghidra on the decompressed image.**
- Language: ARM v7 little-endian, load `rtos_decompressed.bin` (it begins at the vector table)
- Find the base address: look at literal-pool words in code that point to known strings (`KODAKPIXPRO C1`, `UseHiddenF`, `A:\C110.bin`). Subtract each string's file offset from the pointer value; the consistent difference is the base. Rebase the program to it.
- Then run auto-analysis and bookmark the strings in section 6.

**Step 3. Solve the update path.**
- Cross-reference `A:\C110.bin` (0x76C8A8, 0xAECAA4) to find the update function; read what it checks before reading the file
- In `part_4_uboot.bin` (also ARM), cross-reference `All-in-one image MD5 sum is not match` to find the checksum routine and its exact input range. That also answers the header checksum question.
- Check how the BCL1 field `0xF5B20009` is used by the loader.

**Step 4. Easiest first mod: boot logo.** Replace the 10 boot JPEGs (same dimensions, equal or smaller byte size per frame, pad with zeros) in the decompressed image, recompress (or literal-encode), fix BCL1 sizes, fix checksums, flash.

**Step 5. PIN lock.** Design below.

**Step 6. Hidden features.** Find code that reads `UseHiddenF` in Ghidra, then patch the branch (not the string).

**Step 7. Flash.** Find where the flash level used for normal captures is set, compare with `AutoFuncTestFlashlvl`, and change one value at a time with a flash backup in hand.

Quick things to ask the owner to run (they were never reported): the four SD probe files, a USB-mode check (Mass Storage vs PC Camera, and whether a webcam appears), a full menu-tree photo, and Settings screen version info.

---

## 10. PIN lock design

Intended behavior:
- On boot, after LVGL is up and before the main camera UI (`UIFlowWnd`, around `ShowBG`), check a stored PIN hash. If unset, boot normally. If set, show a 4-digit screen.
- Wheel UP/DOWN changes the digit, LEFT/RIGHT moves the cursor, SHUTTER confirms.
- Cooldown after repeated wrong tries (for example 30 s after 3, longer after more).
- Setup and disable entries under the mode menu ("Camera Lock" with Set PIN / Change PIN / Disable PIN).
- Storage: a few bytes in `pstore` through the camera's existing flag/save mechanism, or in `usr` (about 1 KB free). The `usr` partition is rewritten by firmware updates, so `pstore` is safer.

Existing building blocks (STRINGS ONLY until read in Ghidra): `KeyLock`, `DrvKey_DetNormalKey`, `NVT_KEY_EVENT`, `lv_msgbox`, `indev_keypad_group`, `xsave pstore info`.

Honest scope: this needs injected ARM code plus new LVGL objects and a hook in the boot flow. It is real work, not a flag flip, and it depends on solving recompression and the checksum first. A physically cheaper variant: reuse the existing `KeyLock` and make a long-press sequence unlock it (no on-screen PIN UI), as a stepping stone.

---

## 11. Safety notes

- U-Boot appears to verify the MD5 before flashing, but this was not tested.
- Do not create a file named `NVTDELFW` on the SD card (string suggests it triggers a firmware wipe).
- Do not power off during a real update.
- A flash backup (Step 0) is the difference between a recoverable and an unrecoverable mistake.

---

## 12. Files to bring into the Cursor project

- `C110.bin` (the original, never edit it in place)
- `c1_unpack.py`
- This document
- After running the script: `out/rtos_decompressed.bin`, `out/part_4_uboot.bin`, `out/part_3_fdt_app.bin`, `out/jpegs/`

---

## 13. Paste this as your first message in Cursor

> I'm reverse engineering and modding the Kodak PixPro C1 (Novatek NA51089, ARM Cortex-A9, FreeRTOS, LVGL UI) firmware `C110.bin`. Read `c1-cursor-handoff.md` fully first. The RTOS partition is BCL LZ77-compressed (see `c1_unpack.py`). Goals in order: (1) find why the camera ignores `A:\C110.bin` and the real header checksum by analyzing the RTOS and U-Boot in Ghidra, (2) build a repack tool (BCL compressor or literal-encoder, BCL1 header, NVTPACK header and checksum), (3) swap the boot-logo JPEGs, (4) add a PIN lock screen driven by the D-pad wheel, (5) unlock hidden features and test a flash change. Be explicit about what is verified versus assumed, and do not assume anything in the "STRINGS ONLY" list works until you've read the code.
