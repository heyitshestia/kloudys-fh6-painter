#!/usr/bin/env python3
"""Targeted read-only FH6 group probe for the 1000-circle control template."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import struct
import time
import zlib
from collections import Counter
from ctypes import wintypes
from pathlib import Path

import psutil


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
RW_MASK = 0xCC

GROUP_COUNT_OFF = 0x5A
GROUP_TABLE_OFF = 0x78
GROUP_TABLE_END_OFF = 0x80
GROUP_TABLE_CAPACITY_OFF = 0x88
LAYER_SIZE = 0xC0


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wintypes.LPVOID),
        ("AllocationBase", wintypes.LPVOID),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
k32.CloseHandle.argtypes = (wintypes.HANDLE,)
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
)
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.POINTER(MBI),
    ctypes.c_size_t,
)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hx(value):
    return f"0x{int(value):x}"


def finite(value, limit=100000.0):
    return math.isfinite(value) and -limit <= value <= limit


def find_pid(pid=None):
    if pid:
        return int(pid)
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info.get("name") or "").lower() == "forzahorizon6.exe":
                return int(proc.info["pid"])
        except psutil.Error:
            pass
    raise RuntimeError("forzahorizon6.exe not found")


def open_process(pid):
    handle = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle):
    if handle:
        k32.CloseHandle(handle)


def read_memory(handle, address, size):
    if size <= 0:
        return b""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, int(address), buf, int(size), ctypes.byref(read))
    if not ok or read.value <= 0:
        return b""
    return buf.raw[: read.value]


def read_u64(handle, address):
    raw = read_memory(handle, address, 8)
    return struct.unpack("<Q", raw)[0] if len(raw) == 8 else 0


def is_rw(protect):
    return not (protect & PAGE_GUARD or protect & PAGE_NOACCESS) and bool(protect & RW_MASK)


def iter_regions(handle):
    addr = 0x10000
    max_addr = 0x7FFFFFFFFFFF
    info = MBI()
    while addr < max_addr:
        if not k32.VirtualQueryEx(handle, addr, ctypes.byref(info), ctypes.sizeof(info)):
            addr += 0x10000
            continue
        base = int(info.BaseAddress)
        size = int(info.RegionSize)
        if int(info.State) == MEM_COMMIT and int(info.Type) == MEM_PRIVATE and is_rw(int(info.Protect)):
            yield {"base": base, "end": base + size, "size": size}
        nxt = base + size
        if nxt <= addr:
            break
        addr = nxt


def build_contains(regions):
    ranges = sorted((r["base"], r["end"]) for r in regions)

    def contains(value):
        value = int(value)
        if not (0x10000 <= value <= 0x7FFFFFFFFFFF):
            return False
        lo, hi = 0, len(ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end = ranges[mid]
            if value < start:
                hi = mid - 1
            elif value >= end:
                lo = mid + 1
            else:
                return True
        return False

    return contains


def layer_summary(handle, ptr, index):
    raw = read_memory(handle, ptr, LAYER_SIZE)
    if len(raw) < 0xB0:
        return {"index": index, "ptr": hx(ptr), "ok": False, "reason": f"short read {len(raw)}"}
    px, py = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rot = struct.unpack_from("<f", raw, 0x50)[0]
    res = struct.unpack_from("<Q", raw, 0xA8)[0]
    ok = finite(px) and finite(py) and finite(sx) and finite(sy) and finite(rot, 1000000.0)
    return {
        "index": index,
        "ptr": hx(ptr),
        "ok": ok,
        "position": [px, py],
        "scale": [sx, sy],
        "rotation": rot,
        "color_rgba": list(raw[0x74:0x78]),
        "mask": raw[0x78],
        "shape_id_byte": raw[0x7A],
        "resource_ptr_0xa8": hx(res) if 0x10000 <= res <= 0x7FFFFFFFFFFF else None,
        "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
        "bytes_0x38_0x7c": raw[0x38:0x7C].hex(),
        "raw_hex": raw.hex(),
    }


def validate_candidate(handle, contains, group, table, count, report_layers):
    if not contains(group):
        return None
    if not contains(table):
        return None
    table_end = read_u64(handle, group + GROUP_TABLE_END_OFF)
    table_capacity = read_u64(handle, group + GROUP_TABLE_CAPACITY_OFF)
    expected_end = int(table) + int(count) * 8
    if table_end != expected_end:
        return None
    if table_capacity < table_end:
        return None
    if (table_end - table) % 8 != 0 or (table_capacity - table) % 8 != 0:
        return None
    if not contains(table_end - 1) or not contains(table_capacity - 1):
        return None
    vector_count = (table_end - table) // 8
    capacity_count = (table_capacity - table) // 8
    if vector_count != count:
        return None
    if capacity_count < count or capacity_count > max(count + 10000, count * 16):
        return None
    ptr_raw = read_memory(handle, table, count * 8)
    if len(ptr_raw) != count * 8:
        return None
    ptrs = list(struct.unpack(f"<{count}Q", ptr_raw))
    valid_ptrs = [p for p in ptrs if contains(p)]
    if len(valid_ptrs) < max(32, count // 4):
        return None
    sample = []
    shape_counts = Counter()
    colors = Counter()
    ok_count = 0
    for i, ptr in enumerate(ptrs[: min(count, report_layers)]):
        if not contains(ptr):
            sample.append({"index": i, "ptr": hx(ptr), "ok": False, "reason": "not private rw"})
            continue
        item = layer_summary(handle, ptr, i)
        sample.append(item)
        if item.get("ok"):
            ok_count += 1
        if "shape_id_byte" in item:
            shape_counts[item["shape_id_byte"]] += 1
        if "color_rgba" in item:
            colors[tuple(item["color_rgba"])] += 1
    # Count all shape bytes cheaply.
    all_shape_counts = Counter()
    square_like = []
    for i, ptr in enumerate(ptrs):
        if not contains(ptr):
            continue
        raw = read_memory(handle, ptr + 0x7A, 1)
        if len(raw) == 1:
            all_shape_counts[raw[0]] += 1
            if raw[0] == 101:
                square_like.append(i)
    score = len(valid_ptrs) + ok_count * 4 + all_shape_counts.get(102, 0) + all_shape_counts.get(101, 0) * 8
    return {
        "score": score,
        "group": hx(group),
        "table": hx(table),
        "table_end": hx(table_end),
        "table_capacity": hx(table_capacity),
        "count": count,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
        "vector_ok": True,
        "valid_ptrs": len(valid_ptrs),
        "sample_ok_count": ok_count,
        "shape_id_counts_sample": dict(shape_counts.most_common(24)),
        "shape_id_counts_all": dict(all_shape_counts.most_common(24)),
        "square_byte_indices": square_like[:50],
        "color_counts_sample": {" ".join(map(str, k)): v for k, v in colors.most_common(12)},
        "layers": sample,
    }


def scan_count_groups(handle, count, max_seconds, report_layers):
    regions = list(iter_regions(handle))
    contains = build_contains(regions)
    pattern = struct.pack("<H", count)
    candidates = []
    seen = set()
    start_time = time.time()
    scanned_mb = 0.0
    for idx, region in enumerate(regions, 1):
        if max_seconds and time.time() - start_time > max_seconds:
            log("Time limit reached.")
            break
        raw = read_memory(handle, region["base"], min(region["size"], 128 * 1024 * 1024))
        if not raw:
            continue
        scanned_mb += len(raw) / (1024 * 1024)
        pos = 0
        while True:
            hit = raw.find(pattern, pos)
            if hit < 0:
                break
            pos = hit + 1
            count_addr = region["base"] + hit
            group = count_addr - GROUP_COUNT_OFF
            if group in seen or group < region["base"]:
                continue
            seen.add(group)
            table = read_u64(handle, group + GROUP_TABLE_OFF)
            item = validate_candidate(handle, contains, group, table, count, report_layers)
            if item:
                candidates.append(item)
                candidates.sort(key=lambda x: x["score"], reverse=True)
                del candidates[20:]
        if idx % 200 == 0:
            log(f"Scanned {idx}/{len(regions)} regions, {scanned_mb:.0f} MB, candidates={len(candidates)}")
    log(f"Scan complete: {scanned_mb:.0f} MB, candidates={len(candidates)}")
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--max-seconds", type=int, default=90)
    parser.add_argument("--report-layers", type=int, default=120)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    pid = find_pid(args.pid)
    proc = psutil.Process(pid)
    log(f"Opening pid={pid} {proc.name()}")
    handle = open_process(pid)
    try:
        candidates = scan_count_groups(handle, args.count, args.max_seconds, args.report_layers)
    finally:
        close_handle(handle)
    payload = {
        "format": "fh6_group1000_probe_v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": pid,
        "process": {"name": proc.name(), "exe": proc.exe()},
        "count": args.count,
        "candidates": candidates,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"fh6-group{args.count}-probe-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(f"Wrote {out}")


if __name__ == "__main__":
    main()
