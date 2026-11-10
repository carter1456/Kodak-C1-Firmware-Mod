# Kodak PixPro C1 firmware tools

Offline tools for Kodak PixPro C1 stock firmware `C110.bin` v1.04 (6,996,860 bytes), Novatek NA51089. There is no full software rip and no ready-to-flash mod package. These scripts unpack that stock image, check it, and rebuild a file on a computer.

Start here. The evidence is in [`NOTES.md`](NOTES.md).

## Path to a running mod

### Done (offline, verified)

- Header bytes `0x00–0x0F` are the fixed HDR2 magic `072e01d6bc10914fb28a352f82261a50`, not an MD5. U-Boot `memcmp`s that GUID at U-Boot file `0x458DC`, then checks the u16 checksum at `0x24`.
- Real BCL LZ compressor. The stock RTOS (11,608,936 bytes) compresses to 6,228,160, under the stock payload (6,352,748) and under the flash window `0xD50000`. The round-trip matches.
- Identity rebuild: 6,872,168 bytes, `@0x24=0x8D84`. Boot-logo rebuild: 6,859,048 bytes, `@0x24=0x5CCF`. Ten 320x240 JPEGs; the smallest original frame is 1,827 bytes. A shorter replacement is zero-padded inside that span. The other partitions stay byte-identical. The packer aligns to 4 bytes, so the gaps differ from stock.
- `CONFIG_NVT_ALL_IN_ONE_IMG_SIZE = 0x02000000` (32 MiB), checked at U-Boot file `0xA1F4`. A later `0x04940000` check is `CONFIG_NVT_RUNFW_SDRAM_BASE` overlap, a different limit.
- Who can start an update, from the RTOS image: `System_OnStrg_UploadFW` at file `0x404D18` opens `A:\C110.bin`. Its direct callers are the `UISetupObj` event `0x14080000` handler at file `0x407620` (it logs `Do FW Update`, then calls the uploader) and `BackgroundFWUpdate` at file `0x42286C`. In the const `(id, fn)` table at file `0xAEE7DC`, id `0x0C` is that background uploader. Id `0x0D` is a stub that calls `PhotoExe_DZoomInBK`, not the uploader. Id `0x0C` is posted by `UIWifiCmdObj` event `0x1402001F` (file `0x427D08`) and by factory `C110FwUpdate` (file `0x4981EC`, post at `0x498278`) after `A:\C110.bin` opens. Card insert does not call the uploader. The live background table is a BSS pointer, and whether a normal boot posts `0x0C` is not proven. Details are in `NOTES.md`.

### Next (on the camera, before any modded flash)

- SPI NOR dump first. No dump, no flash.
- Prove the stock update path with unmodified `C110.bin`. The English strings are `FW Version`, `Current Ver: `, `New Ver: `, and `Update Firmware?`. The LCD row that sends event `0x14080000` is not proven. `Do FW Update` is only the handler log line. Find that Setup row on the camera and confirm the version flow runs. Do not create `A:\NVTDELFW`. Do not power-cut an update.
- Only after that stock update is shown to run: flash a logo-only rebuild (a 320x240 JPEG that fits in 1,827 bytes) and confirm the boot animation changed and the camera still boots.

### Later (the actual mod, only after a logo image has booted)

- A custom boot logo is the first shipped change.
- Then UI and feature work: PIN lock, hidden menus, other behavior. `UseHiddenF` is a substring of `ImageApp_MovieMulti_SetUseHiddenFirst`, not a feature flag. Do not patch that string.
- Each change stays inside the decompressed RTOS, is recompressed with `bcl_lz.py`, repacked with `c1_repack.py --verify-roundtrip`, and checked against the 32 MiB cap and the `0xD50000` RTOS window before anyone talks about flashing it.

## What you can do today

Commands use `python`. Windows hosts do not have `python3`.

```bash
python c1_unpack.py C110.bin out
python nvt_sum.py
python c1_repack.py --rtos-decompressed out/rtos_decompressed.bin -o C110_mod.bin --verify-roundtrip
python c1_repack.py --boot-logo splash.jpg -o C110_mod_logo.bin --verify-roundtrip
```

Unpack splits the pack and decompresses the RTOS. `nvt_sum.py` checks the HDR2 magic, the u16 at `0x24`, and the BCL1 sum (run the unpack first; it reads `out/part_6_rtos.bin`). The repack recompresses the RTOS and rebuilds the image. `--boot-logo` writes one 320x240 JPEG over each boot frame that can hold it.

Pillow is optional. It is only needed to extract JPEGs or to swap the boot logos: `pip install pillow`. Unpack, checksums, recompress, and an identity rebuild do not need it.

## Outputs

Rebuilds are `C110_mod*.bin`. Those names are gitignored, and so is `out/`.

The identity rebuild is 6,872,168 bytes (`@0x24=0x8D84`). The boot-logo rebuild is 6,859,048 bytes (`@0x24=0x5CCF`). Both are checksum-correct on disk and under the 32 MiB cap. They are not flash-safe.

## Files

| File | What it is |
|---|---|
| `C110.bin` | Stock firmware, v1.04, 6,996,860 bytes |
| `c1_unpack.py` | Split the pack, decompress the RTOS, optionally extract JPEGs |
| `nvt_sum.py` | HDR2 magic, `@0x24`, and the BCL1 checksum |
| `bcl_lz.py` | BCL LZ compress and decompress |
| `c1_repack.py` | Rebuild an image, fix `@0x24`, optional in-place boot-logo swap |
| `NOTES.md` | Reverse-engineering log. This is the evidence. |
| `AGENTS.md` | Handoff for coding agents |
| `c1-cursor-handoff.md` | Older session history. Where it disagrees with `NOTES.md`, NOTES wins. |
