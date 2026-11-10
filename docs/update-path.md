# How an update starts

This is what the RTOS image does. It is not a procedure for flashing, and it has not been confirmed on a camera. Details and file offsets are in [`NOTES.md`](../NOTES.md).

## What does nothing by itself

Putting `A:\C110.bin` on the card does not call the updater. `System_OnStrgInsert` and `System_OnStrgAttach` do not call it. A normal boot also has no proven post of the background updater. That matches a camera that boots normally, with the file present and the version unchanged.

## The function that reads the file

`System_OnStrg_UploadFW` (file `0x404D18`) opens `A:\C110.bin`. Its returns, from the log strings next to the checks:

| Return | When |
|---|---|
| 5 | the file cannot be opened, the read fails, or the temp buffer cannot be allocated |
| 6 | the update failed and it falls through to a loader update |
| 3 | the firmware-bin check failed |
| 0 | it logs that the update finished |

Two functions call it directly.

1. The Setup handler for `UISetupObj` event `0x14080000` (file `0x407620`). It logs `Do FW Update`, then calls the uploader. That log line is not the on-screen label. The English resource strings next to each other are `FW Version`, `Current Ver: `, `New Ver: `, and `Update Firmware?`. Which Setup row sends event `0x14080000` is **UNVERIFIED**. The word `0x2B` beside those records is the length of the previous string (`Reset camera settings to  factory defaults.`), not an id for `FW Version`.

2. `BackgroundFWUpdate` (file `0x42286C`). In the const table at file `0xAEE7DC` this is background id `0x0C`. Id `0x0D` is `PhotoExe_DZoomInBK`, the digital-zoom path, not an update. The running dispatcher loads its table pointer from BSS at `0xC2BC18`. That the RAM table is a copy of the const table is **UNVERIFIED**.

## Who posts background id `0x0C`

Two sites pass the constant `0x0C` into `BKG_PostEvent`:

- `UIWifiCmdObj` event **`0x1402001F`** (handler file `0x427D04`). Event `0x14020020` is the next entry and does not post `0x0C`.
- Factory `C110FwUpdate` (file `0x4981EC`), after `A:\C110.bin` opens. That path is reached when `A:\iqTestFwUpdate.txt` is present.

A few other callers pass a value loaded from memory. Those values are not known from the image alone.

## `A:\NVTDELFW`

Do not create this file.

`System_OnStrgAttach` opens it only when a bit on the storage object is set. If the open works, it deletes `A:\FW96565A.BIN` and then deletes `A:\NVTDELFW`. That is a file delete, not a flash erase, and it destroys the staged firmware file. A checksum callback can also create that name and rename the staged file back to `A:\C110.bin`.
