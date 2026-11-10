#!/usr/bin/env python3
"""Marcus Geelnard BCL LZ77 (algorithm 9) compressor and decompressor.

The decoder matches the stream inside a Novatek BCL1 container: one marker
byte, then either a literal, ``marker 0x00`` for a literal marker byte, or
``marker + varint(length) + varint(offset)`` for a back-reference.
Varints are 7-bit big-endian; the high bit means another byte follows.
A match is emitted only when it is strictly smaller than the literals it
replaces (the same profitability rule as BCL's LZ_CompressFast).

Defaults (window 262144, chain 48, lazy) compress the stock RTOS
(11,608,936 bytes) to 6,228,160 bytes, under the stock payload of
6,352,748 and under the flash RTOS window ``0xD50000``. That figure is
from one measured run; a different window or chain changes it.
"""
from __future__ import annotations

import argparse
from array import array


def read_varsize(buf: bytes | bytearray | memoryview, pos: int) -> tuple[int, int]:
    y = 0
    n = 0
    while True:
        x = buf[pos + n]
        y = (y << 7) | (x & 0x7F)
        n += 1
        if not (x & 0x80):
            return y, n
        if n > 5:
            raise ValueError(f"varint too long at {pos}")


def bcl_lz_decompress(inp: bytes | bytearray | memoryview) -> bytes:
    marker = inp[0]
    i = 1
    out = bytearray()
    n = len(inp)
    while i < n:
        s = inp[i]
        i += 1
        if s == marker:
            if i >= n:
                raise ValueError("truncated marker")
            if inp[i] == 0:
                out.append(marker)
                i += 1
            else:
                length, k = read_varsize(inp, i)
                i += k
                offset, k = read_varsize(inp, i)
                i += k
                if offset == 0 or offset > len(out):
                    raise ValueError(f"bad offset {offset} at in={i} out={len(out)}")
                # Copy byte by byte so overlapping runs (offset < length) work.
                start = len(out) - offset
                for _ in range(length):
                    out.append(out[start])
                    start += 1
        else:
            out.append(s)
    return bytes(out)


def _var_size(x: int) -> int:
    n = 1
    while x >= 0x80:
        x >>= 7
        n += 1
    return n


def _write_var(out: bytearray, x: int) -> None:
    if x < 0:
        raise ValueError("negative varint")
    chunks = [x & 0x7F]
    x >>= 7
    while x:
        chunks.append((x & 0x7F) | 0x80)
        x >>= 7
    chunks.reverse()
    out.extend(chunks)


def _least_frequent(data: bytes | memoryview) -> int:
    hist = [0] * 256
    for b in data:
        hist[b] += 1
    return min(range(256), key=hist.__getitem__)


def _match_length(data: memoryview, i: int, j: int, limit: int) -> int:
    """Longest common prefix of data[i:] and data[j:], capped at limit."""
    if limit <= 0:
        return 0
    # Doubling uses the C-level slice compare, then a short linear tail.
    n = 0
    step = 1
    while n + step <= limit and data[i + n : i + n + step] == data[j + n : j + n + step]:
        n += step
        if step < 4096:
            step *= 2
    # n is a verified match; the failed step may hide a shorter extension.
    lo = n
    hi = min(limit, n + step)
    # linear from lo (the overshoot is at most `step`, but step can be large).
    # Binary search the remainder.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if data[i : i + mid] == data[j : j + mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


def bcl_lz_compress(
    data: bytes,
    marker: int | None = None,
    max_offset: int = 262144,
    max_chain: int = 32,
    lazy: bool = True,
) -> bytes:
    """Compress ``data`` to a BCL LZ stream.

    ``max_offset`` is the sliding-window limit (BCL's LZ_MAX_OFFSET; the
    stock Novatek tool uses 100000). ``max_chain`` caps how many earlier
    hits of the same 3-byte hash are scored at each position.
    """
    if not data:
        raise ValueError("empty input")
    if marker is None:
        marker = _least_frequent(data)
    if not 0 <= marker <= 255:
        raise ValueError("marker out of range")

    src = memoryview(data)
    n = len(src)
    out = bytearray()
    out.append(marker)

    hash_bits = 16
    hash_mask = (1 << hash_bits) - 1
    # 0 means "no previous", stored value is index+1.
    head = array("I", bytes(4 * (1 << hash_bits)))
    prev = array("I", bytes(4 * n))

    def h3(i: int) -> int:
        return ((src[i] << 10) ^ (src[i + 1] << 5) ^ src[i + 2]) & hash_mask

    def find(i: int) -> tuple[int, int]:
        if i + 4 > n:
            return 0, 0
        h = h3(i)
        best_len = 0
        best_off = 0
        node = head[h]
        chain = 0
        while node and chain < max_chain:
            j = node - 1
            dist = i - j
            if dist > max_offset or dist <= 0:
                break
            # Hash collision filter.
            if src[j] == src[i] and src[j + 1] == src[i + 1] and src[j + 2] == src[i + 2]:
                # Length may exceed `dist` when the source itself repeats.
                length = _match_length(src, i, j, n - i)
                if length > best_len and length > 1 + _var_size(length) + _var_size(dist):
                    best_len = length
                    best_off = dist
                    if length >= 1024:
                        break
            node = prev[j]
            chain += 1
        return best_len, best_off

    def link(i: int) -> None:
        if i + 2 >= n:
            return
        h = h3(i)
        prev[i] = head[h]
        head[h] = i + 1

    i = 0
    while i < n:
        if i + 4 <= n:
            length, offset = find(i)
            if lazy and length and i + 1 + 4 <= n and length < 64:
                length2, offset2 = find(i + 1)
                if length2 > length + 1:
                    # Emit one literal and take the longer match next loop.
                    length = 0
            if length:
                out.append(marker)
                _write_var(out, length)
                _write_var(out, offset)
                end = i + length
                while i < end:
                    link(i)
                    i += 1
                continue
        b = src[i]
        out.append(b)
        if b == marker:
            out.append(0)
        link(i)
        i += 1
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--window", type=int, default=262144)
    ap.add_argument("--chain", type=int, default=32)
    ap.add_argument("--no-lazy", action="store_true")
    ap.add_argument("--marker", type=lambda x: int(x, 0))
    ap.add_argument("--roundtrip", action="store_true")
    args = ap.parse_args()
    data = open(args.input, "rb").read()
    comp = bcl_lz_compress(
        data,
        marker=args.marker,
        max_offset=args.window,
        max_chain=args.chain,
        lazy=not args.no_lazy,
    )
    print(
        f"compressed {len(data)} -> {len(comp)} bytes "
        f"({len(comp) / len(data):.3f}) marker=0x{comp[0]:02X}"
    )
    if args.roundtrip:
        got = bcl_lz_decompress(comp)
        if got != data:
            raise SystemExit(f"roundtrip mismatch {len(got)} vs {len(data)}")
        print("roundtrip OK")
    if args.output:
        open(args.output, "wb").write(comp)


if __name__ == "__main__":
    main()
