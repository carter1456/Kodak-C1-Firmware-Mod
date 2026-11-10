# Kodak PixPro C1 firmware toolkit

Offline reverse-engineering and repack tools for Kodak PixPro C1 (`C110.bin` v1.04).

**Start here for agents:** [`AGENTS.md`](AGENTS.md) → [`NOTES.md`](NOTES.md) → [`c1-cursor-handoff.md`](c1-cursor-handoff.md)

```bash
python c1_unpack.py C110.bin out
python nvt_sum.py
```

Stock `C110.bin` is included. Rebuilt images are checksum-correct on disk; do not flash them. `AGENTS.md` lists what is still unproven on the camera.
