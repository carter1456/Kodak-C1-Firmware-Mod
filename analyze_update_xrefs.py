#!/usr/bin/env python3
"""Dump code-ish context around update-related strings + nearby ARM pointers."""
import struct

dec = open("out/rtos_decompressed.bin", "rb").read()
ub = open("out/part_4_uboot.bin", "rb").read()


def dump_ascii_neighbors(blob, off, radius=0x80):
    start = max(0, off - radius)
    end = min(len(blob), off + radius)
    chunk = blob[start:end]
    # extract printable runs
    runs = []
    cur = []
    cur_at = None
    for i, b in enumerate(chunk):
        if 32 <= b < 127:
            if cur_at is None:
                cur_at = start + i
            cur.append(chr(b))
        else:
            if len(cur) >= 4:
                runs.append((cur_at, "".join(cur)))
            cur, cur_at = [], None
    if len(cur) >= 4:
        runs.append((cur_at, "".join(cur)))
    return runs


def find_all(blob, needle):
    out, start = [], 0
    while True:
        p = blob.find(needle, start)
        if p < 0:
            return out
        out.append(p)
        start = p + 1


TARGETS = [
    (dec, "RTOS", b"A:\\C110.bin"),
    (dec, "RTOS", b"AllInOne_Step2"),
    (dec, "RTOS", b"UPDATE OK"),
    (dec, "RTOS", b"cannot find %s"),
    (dec, "RTOS", b"Alloc Temp Mem is NULL(uiFwSize=%d)"),
    (dec, "RTOS", b"MsdcNvtCb_UpdFwSetBlock: Invalid Key"),
    (dec, "RTOS", b"Delete firmware in A:\\"),
    (dec, "RTOS", b"A:\\FW96565T.BIN"),
    (dec, "RTOS", b"A:\\testcard"),
    (dec, "RTOS", b"A:\\bootlang"),
    (dec, "RTOS", b"A:\\iqTestFw"),
    (dec, "RTOS", b"A:\\auto"),
    (dec, "RTOS", b"UseHiddenF"),
    (dec, "RTOS", b"UseHiddenT"),
    (ub, "UBOOT", b"All-in-one image MD5 sum is not match"),
    (ub, "UBOOT", b"wrong all-in-one bin version"),
    (ub, "UBOOT", b"nvt_process_all_in_one"),
]

for blob, label, s in TARGETS:
    locs = find_all(blob, s)
    print(f"\n=== [{label}] {s!r} @ {[hex(x) for x in locs]} ===")
    for off in locs:
        runs = dump_ascii_neighbors(blob, off, 0x100)
        for at, text in runs:
            mark = ">>" if at == off else "  "
            print(f"  {mark} 0x{at:08X}: {text}")
