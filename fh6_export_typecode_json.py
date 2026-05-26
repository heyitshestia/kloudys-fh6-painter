#!/usr/bin/env python3
"""Export the currently loaded FH6 layer table into importer-compatible JSON."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import struct
import time
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LAYER_SIZE = 0x140
TYPE_CODE_BASE = 0x100000

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


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hx(value):
    return f"0x{int(value):x}"


def parse_int(value):
    return int(str(value), 0)


def finite(value, limit=100000.0):
    return math.isfinite(value) and -limit <= value <= limit


def open_process(pid):
    handle = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle):
    if handle:
        k32.CloseHandle(handle)


def read_memory(handle, address, size):
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, int(address), buf, int(size), ctypes.byref(read))
    if not ok or read.value != size:
        raise RuntimeError(f"read failed at {hx(address)} wanted={size} got={read.value}")
    return buf.raw[: read.value]


def try_read_memory(handle, address, size):
    try:
        return read_memory(handle, address, size)
    except Exception:
        return b""


def ptr_at(handle, table, index):
    return struct.unpack("<Q", read_memory(handle, table + index * 8, 8))[0]


def decode_layer(raw, index, ptr, include_raw=False):
    x, y = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rotation = struct.unpack_from("<f", raw, 0x50)[0]
    skew = struct.unpack_from("<f", raw, 0x70)[0]
    color = list(raw[0x74:0x78])
    mask = bool(raw[0x78])
    shape_word = struct.unpack_from("<H", raw, 0x7A)[0]
    type_code = TYPE_CODE_BASE + int(shape_word)
    valid_numbers = all(finite(v, 1000000.0) for v in (x, y, sx, sy, rotation, skew))
    shape = {
        "type": type_code,
        "type_word": shape_word,
        "type_word_hex": hx(shape_word),
        "data": [x, y, sx, sy, rotation, skew, 1 if mask else 0],
        "color": color,
        "mask": mask,
        "score": 0,
    }
    layer = {
        "index": index,
        "layer": index + 1,
        "ptr": hx(ptr),
        "ok": valid_numbers,
        "type_code": type_code,
        "type_word": shape_word,
        "color": color,
        "mask": mask,
        "data": [x, y, sx, sy, rotation, skew],
    }
    if include_raw:
        layer["raw_hex"] = raw.hex()
    return shape, layer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--group", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--skip-transparent", action="store_true")
    args = parser.parse_args()

    table = parse_int(args.table)
    group = parse_int(args.group) if args.group else None
    handle = open_process(args.pid)
    shapes = []
    layers = []
    failures = []
    try:
        for index in range(int(args.count)):
            ptr = ptr_at(handle, table, index)
            raw = try_read_memory(handle, ptr, LAYER_SIZE)
            if len(raw) != LAYER_SIZE:
                failures.append({
                    "index": index,
                    "layer": index + 1,
                    "ptr": hx(ptr),
                    "reason": f"short read {len(raw)}",
                })
                continue
            shape, layer = decode_layer(raw, index, ptr, include_raw=args.include_raw)
            layers.append(layer)
            if args.skip_transparent and int(shape["color"][3]) <= 0:
                continue
            shapes.append(shape)
    finally:
        close_handle(handle)

    payload = {
        "format": "fh6_typecode_json_export_v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "game": "fh6",
            "pid": int(args.pid),
            "group": hx(group) if group is not None else None,
            "table": hx(table),
            "layer_count": int(args.count),
            "coordinate_model": "fh6_live_layer_offsets",
            "type_model": "type = 0x100000 + uint16_at_layer_0x7A; importer writes low uint16 back to 0x7A",
        },
        "shapes": shapes,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report = {
        "format": "fh6_typecode_json_export_report_v1",
        "created_utc": payload["created_utc"],
        "pid": int(args.pid),
        "group": payload["source"]["group"],
        "table": hx(table),
        "requested_count": int(args.count),
        "exported_shape_count": len(shapes),
        "read_layer_count": len(layers),
        "failure_count": len(failures),
        "output_json": str(out),
        "layers": layers,
        "failures": failures,
    }
    report_path = Path(args.report) if args.report else out.with_suffix(".report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    log(f"Exported {len(shapes)} layer(s) to {out}")
    log(f"Report: {report_path}")
    if failures:
        log(f"Failures: {len(failures)} unreadable layer(s)")


if __name__ == "__main__":
    main()
