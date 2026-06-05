#!/usr/bin/env python3
"""Read-only FH6 vinyl group research capture.

This is intentionally separate from the app importer/exporter. It gathers broad
memory evidence for offline locator work without writing to the game process.
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
import zlib
from collections import Counter, defaultdict
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
RW_MASK = 0xCC
READABLE_MASK = 0xFE

GROUP_COUNT_OFF = 0x5A
GROUP_TABLE_OFF = 0x78
GROUP_TABLE_END_OFF = 0x80
GROUP_TABLE_CAPACITY_OFF = 0x88
GROUP_HEADER_READ = 0x300
FULL_LAYER_SIZE = 0x140
SAFE_LAYER_SIZE = 0xC0
USER_MIN = 0x10000
USER_MAX = 0x7FFFFFFFFFFF

RAW_GROUP_PAD = 0x4000
RAW_TABLE_PAD = 0x4000
RAW_LAYER_PAD = 0x400
RAW_LAYER_MERGE_GAP = 0x1000
RAW_MAX_FILE_BYTES = 8 * 1024 * 1024
RAW_MAX_TOTAL_BYTES_PER_CANDIDATE = 64 * 1024 * 1024


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
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hx(value: int | None) -> str | None:
    return None if value is None else f"0x{int(value):x}"


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(text or "state")).strip()
    return re.sub(r"\s+", "_", text)[:80] or "state"


def finite(value: float, limit: float = 100000.0) -> bool:
    return math.isfinite(value) and -limit <= value <= limit


def open_process(pid: int, read: bool = True):
    access = PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION
    if read:
        access |= PROCESS_VM_READ
    handle = k32.OpenProcess(access, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle) -> None:
    if handle:
        k32.CloseHandle(handle)


def process_image_path(pid: int) -> str | None:
    handle = open_process(pid, read=False)
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        close_handle(handle)


def find_forza_pid() -> tuple[int, str | None]:
    # tasklist is available on every supported Windows install and avoids a
    # psutil dependency for this standalone capture tool.
    cmd = ["tasklist", "/FI", "IMAGENAME eq forzahorizon6.exe", "/FO", "CSV", "/NH"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    rows = list(csv.reader(result.stdout.splitlines()))
    pids = []
    for row in rows:
        if len(row) >= 2 and row[0].strip('"').lower() == "forzahorizon6.exe":
            try:
                pids.append(int(row[1]))
            except ValueError:
                pass
    if not pids:
        raise RuntimeError("forzahorizon6.exe was not found. Open FH6 and the vinyl editor first.")
    if len(pids) > 1:
        log(f"Multiple FH6 processes found; using the first detected process.")
    pid = pids[0]
    return pid, process_image_path(pid)


def is_rw(protect: int) -> bool:
    return not (protect & PAGE_GUARD or protect & PAGE_NOACCESS) and bool(protect & RW_MASK)


def is_readable(protect: int) -> bool:
    return not (protect & PAGE_GUARD or protect & PAGE_NOACCESS) and bool(protect & READABLE_MASK)


def iter_regions(handle, writable_only: bool = True) -> list[dict]:
    regions = []
    addr = USER_MIN
    info = MBI()
    while addr < USER_MAX:
        if not k32.VirtualQueryEx(handle, addr, ctypes.byref(info), ctypes.sizeof(info)):
            addr += 0x10000
            continue
        base = int(info.BaseAddress)
        size = int(info.RegionSize)
        protect = int(info.Protect)
        if (
            int(info.State) == MEM_COMMIT
            and int(info.Type) == MEM_PRIVATE
            and (is_rw(protect) if writable_only else is_readable(protect))
        ):
            regions.append(
                {
                    "base": base,
                    "end": base + size,
                    "size": size,
                    "protect": protect,
                    "type": int(info.Type),
                }
            )
        nxt = base + size
        if nxt <= addr:
            break
        addr = nxt
    return regions


def build_contains(regions: list[dict]):
    ranges = sorted((r["base"], r["end"]) for r in regions)

    def contains(value: int, size: int = 1) -> bool:
        value = int(value)
        if not (USER_MIN <= value <= USER_MAX) or size < 1:
            return False
        lo, hi = 0, len(ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end = ranges[mid]
            if value < start:
                hi = mid - 1
            elif value + size > end:
                lo = mid + 1
            else:
                return True
        return False

    return contains


def region_for(regions: list[dict], value: int) -> dict | None:
    for region in regions:
        if region["base"] <= value < region["end"]:
            return region
    return None


def read_memory(handle, address: int, size: int) -> bytes:
    if size <= 0:
        return b""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, int(address), buf, int(size), ctypes.byref(read))
    if not ok or read.value <= 0:
        return b""
    return buf.raw[: read.value]


def read_u16(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 2)
    return struct.unpack("<H", raw)[0] if len(raw) == 2 else None


def read_u32(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 4)
    return struct.unpack("<I", raw)[0] if len(raw) == 4 else None


def read_u64(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 8)
    return struct.unpack("<Q", raw)[0] if len(raw) == 8 else None


def read_layer_blob(handle, ptr: int) -> tuple[bytes, int]:
    raw = read_memory(handle, ptr, FULL_LAYER_SIZE)
    if len(raw) == FULL_LAYER_SIZE:
        return raw, FULL_LAYER_SIZE
    raw = read_memory(handle, ptr, SAFE_LAYER_SIZE)
    return raw, len(raw)


def common_float_hits(raw: bytes, limit: int = 24) -> list[dict]:
    hits = []
    for offset in range(0, max(0, min(len(raw), 0x140) - 8 + 1), 4):
        a, b = struct.unpack_from("<ff", raw, offset)
        if finite(a) and finite(b) and (abs(a) > 0.0001 or abs(b) > 0.0001):
            hits.append({"offset": offset, "a": a, "b": b})
            if len(hits) >= limit:
                break
    return hits


def decode_layer(raw: bytes, ptr: int, index: int, include_raw: bool = True) -> dict:
    item = {
        "index": index,
        "ptr": hx(ptr),
        "bytes_read": len(raw),
        "ok": False,
    }
    if len(raw) >= 0x20:
        px, py = struct.unpack_from("<ff", raw, 0x18)
        item["position"] = [px, py]
    if len(raw) >= 0x30:
        sx, sy = struct.unpack_from("<ff", raw, 0x28)
        item["scale"] = [sx, sy]
    if len(raw) >= 0x54:
        item["rotation"] = struct.unpack_from("<f", raw, 0x50)[0]
    if len(raw) >= 0x78:
        item["color_rgba"] = list(raw[0x74:0x78])
    if len(raw) > 0x78:
        item["mask_byte"] = raw[0x78]
    if len(raw) >= 0x7C:
        item["shape_byte"] = raw[0x7A]
        item["shape_word"] = struct.unpack_from("<H", raw, 0x7A)[0]
    if len(raw) >= 0xB0:
        res = struct.unpack_from("<Q", raw, 0xA8)[0]
        item["resource_ptr_0xa8"] = hx(res) if USER_MIN <= res <= USER_MAX else None
    px, py = item.get("position") or (None, None)
    sx, sy = item.get("scale") or (None, None)
    rot = item.get("rotation")
    item["ok"] = all(
        [
            isinstance(px, float) and finite(px),
            isinstance(py, float) and finite(py),
            isinstance(sx, float) and finite(sx),
            isinstance(sy, float) and finite(sy),
            isinstance(rot, float) and finite(rot, 1000000.0),
        ]
    )
    item["crc32"] = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}" if raw else None
    item["float_hits"] = common_float_hits(raw)
    if include_raw:
        item["raw_hex"] = raw.hex()
    return item


def summarize_numeric(values: list[float]) -> dict | None:
    values = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not values:
        return None
    return {"min": min(values), "max": max(values), "avg": sum(values) / len(values)}


def candidate_from_group(
    handle,
    regions: list[dict],
    contains,
    group: int,
    table: int | None,
    count: int,
    source: str,
    report_layers: int,
    include_raw: bool = False,
) -> dict | None:
    if table is None or not contains(group, GROUP_HEADER_READ) or not contains(table, max(8, count * 8)):
        return None
    table_end = read_u64(handle, group + GROUP_TABLE_END_OFF)
    table_capacity = read_u64(handle, group + GROUP_TABLE_CAPACITY_OFF)
    count_u16 = read_u16(handle, group + GROUP_COUNT_OFF)
    count_u32_before = read_u32(handle, group + GROUP_COUNT_OFF - 2)
    if table_end is None or table_capacity is None:
        return None
    vector_count = (table_end - table) // 8 if table_end >= table and (table_end - table) % 8 == 0 else None
    capacity_count = (table_capacity - table) // 8 if table_capacity >= table and (table_capacity - table) % 8 == 0 else None
    expected_end = table + count * 8
    reasons = []
    if count_u16 != count:
        reasons.append(f"count_u16={count_u16}")
    if vector_count != count:
        reasons.append(f"vector_count={vector_count}")
    if capacity_count is None or capacity_count < count:
        reasons.append(f"capacity_count={capacity_count}")
    if table_end != expected_end:
        reasons.append(f"table_end={hx(table_end)} expected={hx(expected_end)}")
    if not contains(table_end - 1) or not contains(table_capacity - 1):
        reasons.append("table end/capacity outside private rw regions")
    ptr_raw = read_memory(handle, table, count * 8)
    if len(ptr_raw) != count * 8:
        reasons.append(f"pointer table short read {len(ptr_raw)}/{count * 8}")
        ptrs = []
    else:
        ptrs = list(struct.unpack(f"<{count}Q", ptr_raw))
    valid_ptrs = [p for p in ptrs if contains(p, 0x7C)]
    duplicate_ptr_count = len(ptrs) - len(set(ptrs)) if ptrs else 0
    sample_indices = list(range(min(count, report_layers)))
    if count > report_layers:
        tail_start = max(report_layers, count - min(20, report_layers))
        sample_indices.extend(range(tail_start, count))
    sample_indices = sorted(set(sample_indices))
    layers = []
    full_shape_counts = Counter()
    full_color_counts = Counter()
    full_mask_counts = Counter()
    ok_count = 0
    positions_x, positions_y, scales_x, scales_y, rotations = [], [], [], [], []
    for i, ptr in enumerate(ptrs):
        if not contains(ptr, 0x7C):
            if i in sample_indices:
                layers.append({"index": i, "ptr": hx(ptr), "ok": False, "reason": "not private rw"})
            continue
        raw, _size = read_layer_blob(handle, ptr)
        decoded = decode_layer(raw, ptr, i, include_raw=include_raw or count <= 80 or i in sample_indices)
        if decoded.get("ok"):
            ok_count += 1
        if "shape_byte" in decoded:
            full_shape_counts[decoded["shape_byte"]] += 1
        if "color_rgba" in decoded:
            full_color_counts[tuple(decoded["color_rgba"])] += 1
        if "mask_byte" in decoded:
            full_mask_counts[decoded["mask_byte"]] += 1
        pos = decoded.get("position")
        scale = decoded.get("scale")
        if pos:
            positions_x.append(pos[0])
            positions_y.append(pos[1])
        if scale:
            scales_x.append(scale[0])
            scales_y.append(scale[1])
        if isinstance(decoded.get("rotation"), float):
            rotations.append(decoded["rotation"])
        if i in sample_indices:
            layers.append(decoded)
    score = (
        len(valid_ptrs) * 10
        + ok_count * 3
        + (1000 if vector_count == count else 0)
        + (800 if count_u16 == count else 0)
        - len(reasons) * 250
        - duplicate_ptr_count * 20
    )
    region = region_for(regions, group)
    return {
        "score": score,
        "source": source,
        "group": hx(group),
        "table": hx(table),
        "table_end": hx(table_end),
        "table_capacity": hx(table_capacity),
        "count_requested": count,
        "count_u16_0x5a": count_u16,
        "count_u32_0x58": count_u32_before,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
        "valid_ptrs": len(valid_ptrs),
        "invalid_ptrs": max(0, len(ptrs) - len(valid_ptrs)),
        "duplicate_ptr_count": duplicate_ptr_count,
        "layer_ok_count": ok_count,
        "reasons": reasons,
        "region": {"base": hx(region["base"]), "end": hx(region["end"]), "size": region["size"]} if region else None,
        "shape_id_counts_all": dict(full_shape_counts.most_common(64)),
        "mask_counts_all": dict(full_mask_counts.most_common(16)),
        "color_counts_all": {" ".join(map(str, k)): v for k, v in full_color_counts.most_common(32)},
        "position_x": summarize_numeric(positions_x),
        "position_y": summarize_numeric(positions_y),
        "scale_x": summarize_numeric(scales_x),
        "scale_y": summarize_numeric(scales_y),
        "rotation": summarize_numeric(rotations),
        "table_pointers": [hx(p) for p in ptrs],
        "layers": layers,
    }


def scan_count_headers(handle, regions, contains, count, max_seconds, report_layers) -> tuple[list[dict], dict]:
    pattern = struct.pack("<H", count)
    candidates = []
    seen = set()
    start = time.time()
    scanned_mb = 0.0
    hit_count = 0
    for idx, region in enumerate(regions, 1):
        if max_seconds and time.time() - start > max_seconds:
            break
        raw = read_memory(handle, region["base"], min(region["size"], 128 * 1024 * 1024))
        scanned_mb += len(raw) / (1024 * 1024)
        pos = 0
        while raw:
            hit = raw.find(pattern, pos)
            if hit < 0:
                break
            pos = hit + 1
            hit_count += 1
            group = region["base"] + hit - GROUP_COUNT_OFF
            if group in seen:
                continue
            seen.add(group)
            table = read_u64(handle, group + GROUP_TABLE_OFF)
            item = candidate_from_group(handle, regions, contains, group, table, count, "count_header", report_layers)
            if item:
                candidates.append(item)
                candidates.sort(key=lambda x: x["score"], reverse=True)
                del candidates[50:]
        if idx % 200 == 0:
            log(f"count-header scan {idx}/{len(regions)} regions, {scanned_mb:.0f} MB, candidates={len(candidates)}")
    return candidates, {"scanned_mb": scanned_mb, "count_hits": hit_count, "unique_groups": len(seen)}


def scan_vector_headers(handle, regions, contains, count, max_seconds, report_layers) -> tuple[list[dict], dict]:
    candidates = []
    seen = set()
    start = time.time()
    scanned_mb = 0.0
    triple_hits = 0
    expected_span = count * 8
    for idx, region in enumerate(regions, 1):
        if max_seconds and time.time() - start > max_seconds:
            break
        raw = read_memory(handle, region["base"], min(region["size"], 128 * 1024 * 1024))
        scanned_mb += len(raw) / (1024 * 1024)
        # group+0x78/0x80/0x88 are pointer-aligned in all captures so far.
        for off in range(0, max(0, len(raw) - 24), 8):
            begin, end, cap = struct.unpack_from("<QQQ", raw, off)
            if end - begin != expected_span:
                continue
            if not (begin <= end <= cap):
                continue
            if not contains(begin, max(8, expected_span)) or not contains(end - 1) or not contains(cap - 1):
                continue
            group = region["base"] + off - GROUP_TABLE_OFF
            if group in seen:
                continue
            seen.add(group)
            triple_hits += 1
            item = candidate_from_group(handle, regions, contains, group, begin, count, "vector_header", report_layers)
            if item:
                candidates.append(item)
                candidates.sort(key=lambda x: x["score"], reverse=True)
                del candidates[50:]
        if idx % 200 == 0:
            log(f"group-metadata scan {idx}/{len(regions)} regions, {scanned_mb:.0f} MB, candidates={len(candidates)}")
    return candidates, {"scanned_mb": scanned_mb, "vector_triple_hits": triple_hits, "unique_groups": len(seen)}


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    best = {}
    for item in candidates:
        key = (item.get("group"), item.get("table"))
        old = best.get(key)
        if old is None or item.get("score", 0) > old.get("score", 0):
            best[key] = item
    return sorted(best.values(), key=lambda x: x.get("score", 0), reverse=True)


def read_surrounding(handle, contains, address: int, before: int = 0x100, size: int = 0x500) -> dict | None:
    start = max(USER_MIN, int(address) - before)
    if not contains(start, 1):
        return None
    raw = read_memory(handle, start, size)
    return {"address": hx(start), "size": len(raw), "hex": raw.hex()}


def parse_hex_address(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return None


def clamp_range_to_region(regions: list[dict], start: int, end: int) -> tuple[int, int] | None:
    if end <= start:
        return None
    for region in regions:
        if start < region["end"] and end > region["base"]:
            clamped_start = max(start, region["base"])
            clamped_end = min(end, region["end"])
            if clamped_end > clamped_start:
                return clamped_start, clamped_end
    return None


def merge_ranges(ranges: list[tuple[int, int]], gap: int = 0) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def pointer_sample_for_raw_dump(ptrs: list[int], count: int) -> list[int]:
    valid = [p for p in ptrs if USER_MIN <= p <= USER_MAX]
    if count <= 256 or len(valid) <= 256:
        return valid
    indices = set(range(min(64, len(valid))))
    indices.update(range(max(0, len(valid) - 64), len(valid)))
    for i in range(128):
        indices.add(round(i * (len(valid) - 1) / 127))
    return [valid[i] for i in sorted(indices) if 0 <= i < len(valid)]


def write_raw_range(
    handle,
    chunk_dir: Path,
    rank: int,
    kind: str,
    start: int,
    end: int,
    notes: str = "",
) -> list[dict]:
    written = []
    offset = 0
    total = max(0, end - start)
    while offset < total:
        chunk_start = start + offset
        chunk_size = min(RAW_MAX_FILE_BYTES, total - offset)
        raw = read_memory(handle, chunk_start, chunk_size)
        if not raw:
            break
        suffix = f"_{offset // RAW_MAX_FILE_BYTES + 1}" if total > RAW_MAX_FILE_BYTES else ""
        name = f"candidate{rank:02d}_{kind}_{chunk_start:016x}_{len(raw):x}{suffix}.bin"
        path = chunk_dir / name
        path.write_bytes(raw)
        written.append(
            {
                "candidate_rank": rank,
                "kind": kind,
                "address": hx(chunk_start),
                "requested_size": chunk_size,
                "bytes_read": len(raw),
                "file": str(path.name),
                "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
                "notes": notes,
            }
        )
        offset += len(raw)
        if len(raw) < chunk_size:
            break
    return written


def dump_candidate_raw_chunks(
    handle,
    regions: list[dict],
    out_dir: Path,
    candidate: dict,
    count: int,
    rank: int,
) -> list[dict]:
    group = parse_hex_address(candidate.get("group"))
    table = parse_hex_address(candidate.get("table"))
    if group is None or table is None:
        return []

    chunk_dir = out_dir / "raw-region-chunks"
    chunk_dir.mkdir(exist_ok=True)
    ranges: list[tuple[str, int, int, str]] = []

    group_range = clamp_range_to_region(regions, group - RAW_GROUP_PAD, group + GROUP_HEADER_READ + RAW_GROUP_PAD)
    if group_range:
        ranges.append(("group", group_range[0], group_range[1], "group header plus surrounding bytes"))

    table_span = max(8, count * 8)
    table_range = clamp_range_to_region(regions, table - RAW_TABLE_PAD, table + table_span + RAW_TABLE_PAD)
    if table_range:
        ranges.append(("table", table_range[0], table_range[1], "pointer table/vector area plus surrounding bytes"))

    ptrs = [parse_hex_address(value) for value in candidate.get("table_pointers") or []]
    ptrs = [p for p in ptrs if p is not None]
    layer_ranges = []
    for ptr in pointer_sample_for_raw_dump(ptrs, count):
        clamped = clamp_range_to_region(regions, ptr - RAW_LAYER_PAD, ptr + FULL_LAYER_SIZE + RAW_LAYER_PAD)
        if clamped:
            layer_ranges.append(clamped)
    merged_layer_ranges = merge_ranges(layer_ranges, RAW_LAYER_MERGE_GAP)
    total_layers = sum(end - start for start, end in merged_layer_ranges)
    if total_layers > RAW_MAX_TOTAL_BYTES_PER_CANDIDATE:
        reduced = []
        used = 0
        for start, end in merged_layer_ranges:
            if used >= RAW_MAX_TOTAL_BYTES_PER_CANDIDATE:
                break
            keep_end = min(end, start + RAW_MAX_TOTAL_BYTES_PER_CANDIDATE - used)
            reduced.append((start, keep_end))
            used += keep_end - start
        merged_layer_ranges = reduced
    for index, (start, end) in enumerate(merged_layer_ranges, start=1):
        ranges.append((f"layers{index:02d}", start, end, "merged layer blobs from candidate pointer table"))

    metadata = []
    for kind, start, end, notes in ranges:
        metadata.extend(write_raw_range(handle, chunk_dir, rank, kind, start, end, notes))
    return metadata


def deepen_candidate(handle, regions, contains, candidate: dict, count: int, deep_layers: int, include_raw: bool) -> dict:
    group = int(str(candidate["group"]), 0)
    table = int(str(candidate["table"]), 0)
    deep = candidate_from_group(
        handle,
        regions,
        contains,
        group,
        table,
        count,
        candidate.get("source", "deep"),
        report_layers=max(1, min(count, deep_layers)),
        include_raw=include_raw,
    )
    if not deep:
        return candidate
    group_raw = read_memory(handle, group, GROUP_HEADER_READ)
    deep["group_raw_hex"] = group_raw.hex()
    deep["group_surrounding"] = read_surrounding(handle, contains, group)
    deep["table_surrounding"] = read_surrounding(handle, contains, table)
    return deep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True, help="Visible layer count shown in FH6 for the open vinyl/group.")
    parser.add_argument("--state-name", default="", help="Human label for this capture.")
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--out-root", default="captures")
    parser.add_argument("--max-seconds", type=int, default=45)
    parser.add_argument("--report-layers", type=int, default=32)
    parser.add_argument("--deep-layers", type=int, default=64)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--full", action="store_true", help="Store larger raw layer dumps. Default is compact for Discord sharing.")
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("--count must be greater than zero")
    pid, exe = (args.pid, process_image_path(args.pid)) if args.pid else find_forza_pid()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    state = safe_name(args.state_name or f"group_{args.count}")
    out_dir = Path(args.out_root) / f"{timestamp}_{state}_{args.count}layers"
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"Capturing FH6 state '{state}' count={args.count}")
    log(f"Output: {out_dir}")
    handle = open_process(pid, read=True)
    raw_chunk_metadata = []
    try:
        regions = iter_regions(handle, writable_only=True)
        contains = build_contains(regions)
        region_summary = {
            "count": len(regions),
            "total_mb": sum(r["size"] for r in regions) / (1024 * 1024),
            "largest": [
                {"base": hx(r["base"]), "end": hx(r["end"]), "size": r["size"], "mb": r["size"] / (1024 * 1024)}
                for r in sorted(regions, key=lambda item: item["size"], reverse=True)[:30]
            ],
        }
        log(f"RW private regions: {region_summary['count']} / {region_summary['total_mb']:.0f} MB")
        count_candidates, count_stats = scan_count_headers(handle, regions, contains, args.count, args.max_seconds, args.report_layers)
        vector_candidates, vector_stats = scan_vector_headers(handle, regions, contains, args.count, args.max_seconds, args.report_layers)
        candidates = dedupe_candidates(count_candidates + vector_candidates)
        log(f"Candidates found: {len(candidates)}")
        deep_candidates = []
        for index, candidate in enumerate(candidates[: max(1, args.top)], start=1):
            log(f"Deep dumping candidate {index}/{min(len(candidates), args.top)} score={candidate.get('score')}; metadata saved to files")
            deep = deepen_candidate(handle, regions, contains, candidate, args.count, args.deep_layers, args.full)
            deep_candidates.append(deep)
            raw_chunk_metadata.extend(dump_candidate_raw_chunks(handle, regions, out_dir, deep, args.count, index))
    finally:
        close_handle(handle)

    payload = {
        "format": "fh6_research_capture_v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state_name": args.state_name,
        "requested_count": args.count,
        "pid": pid,
        "process": {"name": "forzahorizon6.exe", "exe": exe},
        "scanner": {
            "count_header": count_stats,
            "vector_header": vector_stats,
            "max_seconds_each": args.max_seconds,
            "report_layers": args.report_layers,
            "deep_layers": args.deep_layers,
            "top_deep_candidates": args.top,
            "full_raw_mode": bool(args.full),
            "raw_chunk_files": len(raw_chunk_metadata),
        },
        "regions": region_summary,
        "candidates": candidates,
        "deep_candidates": deep_candidates,
        "raw_region_chunks": raw_chunk_metadata,
    }
    (out_dir / "capture.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "raw-region-chunks.json").write_text(json.dumps(raw_chunk_metadata, indent=2), encoding="utf-8")
    (out_dir / "candidate-summary.json").write_text(
        json.dumps(
            [
                {
                    "rank": i + 1,
                    "score": c.get("score"),
                    "source": c.get("source"),
                    "group": c.get("group"),
                    "table": c.get("table"),
                    "valid_ptrs": c.get("valid_ptrs"),
                    "layer_ok_count": c.get("layer_ok_count"),
                    "vector_count": c.get("vector_count"),
                    "capacity_count": c.get("capacity_count"),
                    "count_u16_0x5a": c.get("count_u16_0x5a"),
                    "reasons": c.get("reasons"),
                    "shape_id_counts_all": c.get("shape_id_counts_all"),
                    "color_counts_all": c.get("color_counts_all"),
                }
                for i, c in enumerate(candidates[:30])
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    notes = out_dir / "notes.txt"
    notes.write_text(
        "Fill this in before sending back if possible:\n"
        f"State name: {args.state_name}\n"
        f"Layer count entered: {args.count}\n"
        "Grouped/ungrouped/nested:\n"
        "Visible description:\n"
        "Expected shape count:\n"
        "Anything unusual:\n",
        encoding="utf-8",
    )
    log(f"Wrote {out_dir / 'capture.json'}")
    log(f"Wrote {out_dir / 'candidate-summary.json'}")
    log(f"Wrote {out_dir / 'raw-region-chunks.json'} with {len(raw_chunk_metadata)} raw chunk file(s)")
    log("Done. Zip the whole capture folder when sharing results.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"FAILED: {exc}")
        raise
