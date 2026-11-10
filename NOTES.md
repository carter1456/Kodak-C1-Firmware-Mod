# Kodak PixPro C1 — working notes (Cursor session)

Evidence log. The short overview and the path to a running mod are in [`README.md`](README.md).
Prefer this file over [`c1-cursor-handoff.md`](c1-cursor-handoff.md) where they disagree.
Labels: **VERIFIED** / **STRINGS ONLY** / **UNVERIFIED**.

## Done this session

### Unpack (VERIFIED)
```
python c1_unpack.py C110.bin out
```
- `rtos_decompressed.bin` = 11,608,936 bytes
- 10 boot-logo JPEGs 320x240 under `out/jpegs/`

### BCL1 header (VERIFIED — corrects handoff)
Was misread as one BE u32 `0xF5B20009`. Actual layout:

| Off | Field |
|---|---|
| 0 | `BCL1` |
| 4 | u16 LE checksum (`nvtpack_calc_nvt_sum` / `ntk_checksum16`) |
| 6 | u16 BE algorithm (`0x0009` = LZ) |
| 8 | u32 BE uncompressed size |
| 12 | u32 BE compressed size |

On stock C110: checksum `0xB2F5`, and `nvt_sum(header+payload) == 0`.

### NVTPACK_FW_HDR2 outer checksum (VERIFIED)
- Version tag `@0x10 = 0x16071515` (same family as Suntek HDR2 tools)
- **Whole-file checksum is u16 LE at offset `0x24`**, algorithm `ntk_checksum16` (same as BCL1)
- Stock value `0xD4C1` matches calc over the entire file with `@0x24` zeroed during sum
- Bytes `0x00–0x0F` are the **fixed HDR2 magic**, not a digest. See below.

### Load addresses (VERIFIED from FDT `nvt_memory_cfg`)
| Region | Address | Size |
|---|---|---|
| dram | `0x00000000` | `0x08000000` (128 MB) |
| **rtos** | **`0x00010000`** | `0x01170000` |
| loader | `0x01000000` | `0x00080000` |
| uboot | `0x07140000` | `0x000EC000` |

Ghidra: load `rtos_decompressed.bin` at **`0x00010000`** (ARM LE v7). Many absolute pointers land in that window; **string absolute xrefs are scarce** (likely pool/GOT style — still usable for code).

U-Boot binary: load `part_4_uboot.bin` at **`0x07140000`**.

### Update path (STRINGS + partial code read)
Ignored `A:\C110.bin` on the camera was never a silent brick — likely never entered the update UI path.

Key RTOS names near the SD update cluster (`~0x76C8A8`):
- `System_OnStrg_UploadFW`, `System_OnStrgInit_FWS`
- `CheckSumOKCb` / `CheckSumOKCb: rename %s`
- `A:\FW96565A.BIN`, `FW96565A.BIN`, `A:\NVTDELFW` (**dangerous**)
- UI: `Do FW Update` (Setup), `FW UPDATE OK and Delay 2000ms…`, `C110FwUpdate`
- Gate file: `A:\iqTestFwUpdate.txt` next to `IQTestIsFwUpdate` / charging UI
- Low-level: `xFwSrv_CmdBinUpdateAllInOne` (also: `wrong all-in-one bin version`, `uboot/rtos checksumm failed`, `ERROR BCF Header`)

USB vendor path: `MsdcNvtCb_UpdFwAllInOne_Step1/Step2`, `A:\FW96565T.BIN`.

### Correction: `UseHiddenF` (VERIFIED)
Not a hidden-features flag. It is a substring of  
`ImageApp_MovieMulti_SetUseHiddenFirst` @ `0xA9CB10`.  
Do not patch that string expecting engineer menus.

### Bytes `0x00–0x0F` (VERIFIED — not an MD5)
U-Boot `nvtpack` parser at file `0xA674` (called from `nvt_process_all_in_one` at file `0x959C`):

1. `memcmp` of the first 16 image bytes against the constant at U-Boot file `0x458DC`.
2. Stock `C110.bin` matches that constant exactly:
   `07 2e 01 d6 bc 10 91 4f b2 8a 35 2f 82 26 1a 50`
3. On match it sets the format enum to **2** and reads the partition count from offset `0x18`.
4. It then requires `nvt_sum(image) == 0` (function at file `0xA5D4`: sum of each little-endian u16 plus its index). That is the `@0x24` checksum, over the buffer length the caller passed in.
5. If the 16 bytes do not match, the same function scans for the older HDR1 magic
   `90 be 27 88 cd 36 c2 4f a9 87 73 a8 48 4e 84 b1` (U-Boot file `0x458CC`).
   A miss there is “wrong all-in-one bin version” (the enum is not 2).

The string “All-in-one image MD5 sum is not match” is a **different** check, at the end of file `0x959C`. It `md5_wd`s the in-memory image (chunk `0x10000`, digest at `fp-0x44`), writes and reads the partitions back, `md5_wd`s the same buffer again (digest at `fp-0x54`), and `memcmp`s the two 16-byte digests. It does not read bytes `0x00–0x0F`. Copying the magic through a repack is the correct fix for this field.

### Repack tool status
- `nvt_sum.py` — BCL1 + HDR2 `@0x24`, and the HDR2 magic constant
- `bcl_lz.py` — real BCL LZ compressor (marker = least-frequent byte, match only when it shrinks the stream). Defaults (window 262144, chain 48, lazy) round-trip the stock RTOS and compress it to **6,228,160** bytes, under the stock payload 6,352,748 and under the `0xD50000` flash window.
- `c1_repack.py` — rebuild with that compressor, `@0x24` fix, magic preserved, optional in-place boot-logo swap
- `--literal` still exists and is still too big for the flash RTOS window (`0x1B0000–0xF00000` = `0xD50000`)

**On-disk rebuild (VERIFIED, not flashed).** `c1_repack.py --rtos-decompressed out/rtos_decompressed.bin -o C110_mod.bin --verify-roundtrip` wrote 6,872,168 bytes. Magic matches the HDR2 GUID, `@0x24` is `0x8D84` and `nvt_sum` of the file is 0. The BCL1 container is 6,228,176 bytes (`0xD50000` is 13,959,168), checksums to 0, and decompresses to the original 11,608,936-byte RTOS. Partitions 1, 3, 4, and 8 are byte-identical to stock. The packer aligns to 4 bytes, so the gaps after partitions 3 and 4 are smaller than in the stock file (stock pads 40 and 12; the rebuild pads 0). U-Boot reads those offsets from the table at `0x80`.

A second rebuild with `--boot-logo` (959-byte 320x240 JPEG, under the 1,827-byte smallest frame) wrote 6,859,048 bytes, `@0x24 = 0x5CCF`, `nvt_sum` 0. All ten frames were replaced and zero-padded inside their original spans. Against the stock decompressed RTOS, 37,789 bytes changed and none of them sit outside those spans. The 28 gap bytes between frames were unchanged. Each replaced frame still decodes as 320x240. Both outputs are gitignored (`C110_mod*.bin`). Neither is a reason to flash.

### SD / menu update trigger (VERIFIED from RTOS disassembly)
RTOS is PIC: string addresses are `add rd, pc, rd` plus a literal delta, not absolute words. Load base `0x00010000` still holds.

`System_OnStrg_UploadFW` is file `0x404D18`. It is the function that opens `A:\C110.bin` (rodata `0x76C8A8`).

| Return | When |
|---|---|
| 5 | open fails (“cannot find %s”), read fails, or alloc fails (“Alloc Temp Mem is NULL”) |
| 6 | “update failed, start to use loader update mechanism.” |
| 3 | “FW bin check failed %d” |
| 0 | “update finished!” |

Open mode on that path is `r1 = 1`. After a successful check, if the word at file `0xB1824C` is non-zero, it renames `C110.bin` to `A:\FW96565A.BIN` (source pointer is `A:\C110.bin` plus 3, so the `A:\` prefix is skipped) and deletes `A:\NVTDELFW`, then still returns 0.

**Who calls it (only two direct calls):**

1. **Setup menu handler**, file `0x407620`, UISetupObj event `0x14080000` (handler table starts at file `0xAECB08`; this entry is at `0xAECB30`). The handler logs `Do FW Update` (string file `0x76CED0`) and calls `System_OnStrg_UploadFW`. No instruction in the image builds the immediate `0x14080000`; that constant lives in this table.
2. **`BackgroundFWUpdate`**, file `0x42286C`. It calls the uploader with `r0 = 0` and, on a non-zero return, logs `System_OnStrg_UploadFW() fail(%d)`.

**Background task id (const table VERIFIED; live RAM copy UNVERIFIED).** `BKG_PostEvent`’s entry is file `0x5413FC` (the `push` at `0x541404` is the body after two literal loads). It saves `r0` and stores that word as message word 0, then sends a `0x14`-byte message. There are 19 direct `BL`s to `0x5413FC` and none to `0x541404`.

`UIBackgroundTsk` / `BKG_DispatchMessage` (file `0x541080`) waits for that message, takes word 0 as the key, walks `(key, function)` pairs with stride 8, stops on key 0, and `BLX`es the word at `entry+4`. It loads the table pointer from the word at file `0xB08EC4`, whose stored value is `0x00C2BC18` (BSS, past the end of the image). `BKG_Open` (file `0x541520`) has one direct caller, file `0x3F7D6C`, which passes `{0, 0x8107}` and does not install this const table.

The const `(id, function)` array that matches the walk starts at file `0xAEE7DC` (the old note started one word later, at `0xAEE7E0`) and ends on a 0 key at `0xAEE85C`. Function slots are VAs (file + `0x10000`). Log strings are the PIC targets inside each handler:

| Id | Handler file | Name from its log string |
|---|---|---|
| `0x01` | `0x422BDC` | `BackgroundDelAll`, `Background_DeleteAll` |
| `0x02` | `0x422CFC` | no log string (calls file `0x422CE4` with `r0=1`, `r1=0`) |
| `0x05` | `0x422B40` | `BackgroundFormat` |
| `0x06` | `0x422E5C` | `BackgroundFormatCard` |
| `0x07` | `0x422AA0` | no log string |
| `0x08` | `0x422920` | `BackgroundNumReset` |
| `0x0A` | `0x422C6C` | `Background_ProtectAll` |
| `0x0B` | `0x4227A4` | no log string |
| `0x0C` | `0x42286C` | `BackgroundFWUpdate` (string file `0x77216C`). Calls `System_OnStrg_UploadFW` with `r0=0` |
| `0x0D` | `0x422858` | no log in the stub. Calls `PhotoExe_DZoomInBK` (file `0x414840`) and returns 1 |
| `0x0E` | `0x422844` | no log in the stub. Calls `PhotoExe_DZoomOutBK` (file `0x414F70`) and returns 1 |
| `0x0F` | `0x422770` | tail-calls the `0x13` handler |
| `0x10` | `0x422720` | returns 0 |
| `0x11` | `0x422780` | posts UI event `0x14080092` |
| `0x12` | `0x422828` | no log string |
| `0x13` | `0x422738` | no log string. Posts UI event `0x14001002` |

`BackgroundFWUpdate` is id **`0x0C`** in this array. `AppBKW_SetData` (file `0x772180`) sits in the same string cluster and is not the log line of any of these handlers.

The dispatcher does not point at `0xAEE7DC`. One absolute word `0x00AFE7DC` (the const array’s VA) is stored at file `0x1E588`, in a mixed data region. No PIC `add rd, pc, rd` computes `0xAEE7DC`, and no instruction was found that loads the slot at `0x1E588` or copies the array to `0xC2BC18`. So “the live table is this const array” is **UNVERIFIED**. What is verified is the array’s own layout, and that the immediates below are the keys those posters send.

**Who posts `0x0C` and `0x0D` (VERIFIED immediates).** Every direct caller of `0x5413FC` was disassembled. Two of them put the constant `0x0C` in `r0`:

- File `0x427D08`, function `0x427D04`. `UIWifiCmdObj` (name at file `0xAEEEFC`) points at a handler table at file `0xAEED9C`. That table has the same `(event, function)` stride as `UISetupObj` (the object’s table pointer is 0x14 bytes after the name, and the first word is event `0x14020001`, not a code address). In that alignment the function at `0xAEEEA8` belongs to event **`0x1402001F`** (the event word is at `0xAEEEA4`). Event `0x14020020` (word at `0xAEEEAC`) calls file `0x427D60`, which does not post id `0x0C`. There is no direct `BL` to `0x427D04`; the call is through this table. The same event constant also appears at file `0xAEF21C`.
- File `0x498278`, inside `C110FwUpdate` (file `0x4981EC`). After `A:\C110.bin` opens (mode 5) it calls file `0x436B88` with `r0=1` and then posts `0x0C`. The charging-screen function at file `0x4982D8` (log names `UIFlowCharging_ChildScrClose` and `UIFlowCharging_ScrOpen`) branches to `C110FwUpdate` from file `0x4984F8` when `IQTestIsFwUpdate`’s return value, stored through `r5`, is non-zero, `[r6]` was non-zero, and another word is not 5. `IQTestIsFwUpdate` (file `0x498190`) returns non-zero when `A:\iqTestFwUpdate.txt` opens.

No other `BL` to `BKG_PostEvent` uses `mov r0, #0xc`. Four callers pass `r0` from memory rather than an immediate: files `0x4553E4`, `0x455448`, `0x464E7C`, and `0x46530C`. Each of those loads a BSS word (or a register that points at one). Those values are runtime, so they are not evidence for id `0x0C` or `0x0D`.

Id `0x0D` does have an immediate poster: file `0x412560`, `mov r0, #0xd`, inside `PhotoExe_OnZoom`. It is switch case 1 (`r2 == 1` at file `0x4124F4`). That runs `PhotoExe_DZoomInBK`, the digital-zoom path. Card insert still does not call the uploader. Whether a normal boot delivers WiFi event `0x1402001F`, or takes the charging branch above, is **UNVERIFIED**.

**On-screen copy (strings VERIFIED, link to the event UNVERIFIED).** The English UI records around file `0xAF5854` are `(pointer, strlen)` pairs, not `(string id, pointer)`. The word `0x2B` at file `0xAF5858` is the length of the previous string, `Reset camera settings to  factory defaults.` (43 bytes). It is not an id for `FW Version`.

| File | Record |
|---|---|
| `0xAF585C` | `FW Version` (VA `0x9C756C`, length `0x0A` at `0xAF5860`) |
| `0xAF5864` | `Current Ver: ` (length `0x0D`) |
| `0xAF586C` | `New Ver: ` (length `0x09`) |
| `0xAF5874` | `Update Firmware?` (length `0x10`) |
| `0xAF5B64` | `Please update firmware after  full charged!` (length `0x2B`) |
| `0xAF5B6C` | `Warning! Do not turn off your  camera during update!` |

Event `0x14080000` occurs once in the image, as the key at file `0xAECB30`. No ARM `mov`/`movw`/`movt` and no Thumb `movt` builds that constant. No absolute dword and no PIC `add rd, pc, rd` computes the address of the `FW Version`, `Update Firmware?`, or “full charged” records. The handler at `0x407620` loads `Do FW Update` and nothing else. Those English strings sit next to each other in the resource table. That does not make any of them the LCD label for event `0x14080000`. The label is **UNVERIFIED**.

**`A:\NVTDELFW` (VERIFIED, still do not create it):**
- `System_OnStrgAttach` (around file `0x4048D0`) opens it with mode `5` only if a bit on the storage object is set. If the open works it logs `Detected %s, delete %s`, deletes `A:\FW96565A.BIN`, then deletes `A:\NVTDELFW`. This is a file delete, not a flash erase, and it still destroys the staged firmware file.
- `CheckSumOKCb` (file `0x403F50`) calls the file API with mode `0xA` on `A:\NVTDELFW`. A zero return logs `create indication %s failed`. A non-zero return renames `FW96565A.BIN` to the embedded `A:\C110.bin` at file `0xAECAA4` and sets the word at `0xB1824C`.

**Other paths (not the SD menu trigger):**
- `A:\iqTestFwUpdate.txt` is opened by file `0x498198` (`IQTestIsFwUpdate`). `C110FwUpdate` at file `0x4981EC` then opens `A:\C110.bin` and, if present, calls file `0x436B88` and posts background id `0x0C`. Factory/IQ path.
- USB staging at file `0x423CB0` names `A:\FW96565T.BIN` and `A:\FW96565A.BIN`.
- Mode name `UPDFW` (file `0x42F7A0` open / `0x42F750` close) and shell command `updfw` (`0x42FA0C`, string `update firmware mode`) are a mode switch, not the SD-file reader.

### Boot logo (tooling VERIFIED, not flashed)
Ten 320x240 JPEGs, first at file `0x776C3C`. Absolute pointers (base `0x10000`) land on those offsets, so a swap has to keep each frame’s span. `c1_repack.py --boot-logo` writes a JPEG over every 320x240 frame it fits in and zero-pads the rest of that span.

### All-in-one RAM cap (VERIFIED)
U-Boot file `0xA1F0` is `ldrd r2, r3, [fp, #-0x3c]` (the image size as a u64). File `0xA1F4` is `mov r0, #0x02000000`, then `mov r1, #0`, `cmp r0, r2`, `sbcs`, and `bge` to file `0xA230` when the size is less than or equal to that limit. The fall-through prints and returns `-3` (`mvn r3, #2`). The `ldr r0, [pc, #0x1a8]` at file `0xA220` reads the pool at file `0xA3D0`, which holds VA `0x07183E5C`, the string at file `0x43E5C`: `%sYour image size %lld is larger than all-in-one size with %d %s`. The `%d` argument is the same immediate, `mov r1, #0x02000000` / `str r1, [sp]` at file `0xA214`. So `CONFIG_NVT_ALL_IN_ONE_IMG_SIZE` is **0x02000000 (33,554,432 bytes, 32 MiB)**, from this disassembly, not from a Kconfig file. Stock `C110.bin` is 6,996,860 bytes. The on-disk rebuilds are 6,872,168 and 6,859,048. All three sit under this cap and under the flash RTOS window `0xD50000`.

A later check in the same function (`movt r3, #0x494` at file `0xA240`, limit `0x04940000`) prints the `CONFIG_NVT_RUNFW_SDRAM_BASE` overlap string. That is a different limit.

## Open (priority order)

1. On-camera check that Setup reaches `UISetupObj` event `0x14080000`, and whether a normal boot posts background id `0x0C` (WiFi event `0x1402001F`, or the IQ file plus `C110FwUpdate`). The English strings `FW Version` and `Update Firmware?` are in the resource table only; the LCD label for that event is **UNVERIFIED**.
2. PIN lock / hidden features, only after a real update has been shown to run. `UseHiddenF` is still not a feature flag.
3. SPI NOR dump before any flash. A checksum-correct file under the 32 MiB cap is not a reason to flash.

## Safety
- SPI dump before any successful flash attempt (handoff Step 0).
- Never create `A:\NVTDELFW`.
- Do not power-cut a real update.
