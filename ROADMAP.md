# Path to a running mod

Kodak PixPro C1, stock `C110.bin` v1.04. There is no flashable mod package in this repo. The order below is the one that does not skip a backup or an untested menu.

Evidence for the "done" items is in [`NOTES.md`](NOTES.md). How an update starts is in [`docs/update-path.md`](docs/update-path.md). What not to do is in [`docs/safety.md`](docs/safety.md).

## Done (offline)

These are checked on a computer. None of them have been flashed.

- The first 16 bytes are the HDR2 magic `072e01d6bc10914fb28a352f82261a50`. U-Boot compares that GUID, then the u16 checksum at `0x24`.
- `bcl_lz.py` round-trips the stock RTOS (11,608,936 bytes) and compresses it to 6,228,160 bytes. That is under the stock payload and under the flash RTOS window `0xD50000`.
- An identity rebuild is 6,872,168 bytes (`@0x24=0x8D84`). A boot-logo rebuild is 6,859,048 bytes (`@0x24=0x5CCF`). A replacement JPEG has to fit in the smallest original frame, 1,827 bytes.
- U-Boot rejects an all-in-one image larger than `0x02000000` (32 MiB). Stock and both rebuilds are under that. A separate `0x04940000` check is the run-firmware memory overlap test.

## Next (camera, before any modded flash)

1. Dump the SPI NOR. No dump, no flash.
2. Update with the **unmodified** `C110.bin` from Setup. The English screen copy is `FW Version`, `Current Ver: `, `New Ver: `, and `Update Firmware?`. Which row sends the update event is not proven. `Do FW Update` is only a log line. Do not create `A:\NVTDELFW`. Do not pull power during the update.
3. After that stock update has changed the reported version, flash a logo-only rebuild whose JPEG fits in 1,827 bytes. Confirm the camera boots and the boot animation changed.

## Later (only after a logo image has booted)

- The custom boot logo is the first change worth keeping.
- PIN lock, hidden menus, and other behavior come after that, one change at a time.
- `UseHiddenF` is not a feature flag. Do not patch that string.
- Every change is made in the decompressed RTOS, recompressed, repacked with `--verify-roundtrip`, and checked against 32 MiB and the `0xD50000` window before anyone talks about flashing it.
