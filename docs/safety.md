# Safety

The owner of this camera accepts brick risk. This repo does not.

- Dump the SPI NOR before any flash. A checksum-correct file is not a backup.
- Do not flash `C110_mod.bin` or `C110_mod_logo.bin` because they verify on a computer. The Setup menu has not been shown to run an update, and there is no dump to restore from.
- Do not create `A:\NVTDELFW`. The firmware deletes the staged update file when it sees that name.
- Do not pull power while an update is running.
- Do not patch the string `UseHiddenF`. It is part of `ImageApp_MovieMulti_SetUseHiddenFirst`, not a hidden-features flag.
- The all-in-one RAM cap is 32 MiB and the RTOS flash window is `0xD50000`. Fitting both still leaves the menu path and the lack of a dump unresolved.

When a stock update has been shown to work, the first image worth trying is a logo-only rebuild whose JPEG fits in 1,827 bytes. That step is in [`ROADMAP.md`](../ROADMAP.md), after the dump and after the stock update.
