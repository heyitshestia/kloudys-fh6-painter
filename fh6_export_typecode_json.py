#!/usr/bin/env python3
"""Export the currently loaded FH6 layer table into importer-compatible JSON."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import struct
import sys
import time
from collections import Counter
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
FULL_LAYER_SIZE = 0x140
GROUPED_SAFE_LAYER_SIZE = 0xC0
MIN_LAYER_DECODE_SIZE = 0x7C
TYPE_CODE_BASE = 0x100000
GROUP_HEADER_READ_SIZE = 0x300
GROUP_COUNT_OFFSET = 0x5A
GROUP_TABLE_BEGIN_OFFSET = 0x78
GROUP_TABLE_END_OFFSET = 0x80
GROUP_TABLE_CAPACITY_OFFSET = 0x88
MIN_NORMAL_GROUP_ADDRESS = 0x100000000
EXPORT_REFUSAL_MESSAGE = (
    "Export refused: this does not appear to be a normal editable user-owned FH6 group. "
    "Kloudy's FH6 Painter will not export locked/community-highlight work. "
    "The FH creator community does not condone copying or redistributing another creator's design without permission."
)

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


def read_group_metadata(handle, group):
    raw = read_memory(handle, group, GROUP_HEADER_READ_SIZE)
    begin = struct.unpack_from("<Q", raw, GROUP_TABLE_BEGIN_OFFSET)[0]
    end = struct.unpack_from("<Q", raw, GROUP_TABLE_END_OFFSET)[0]
    capacity = struct.unpack_from("<Q", raw, GROUP_TABLE_CAPACITY_OFFSET)[0]
    vector_count = (end - begin) // 8 if begin and end >= begin else None
    capacity_count = (capacity - begin) // 8 if begin and capacity >= begin else None
    return {
        "group": hx(group),
        "count_u16_0x5a": struct.unpack_from("<H", raw, GROUP_COUNT_OFFSET)[0],
        "count_u32_0x58": struct.unpack_from("<I", raw, GROUP_COUNT_OFFSET - 2)[0],
        "table_begin_0x78": hx(begin),
        "table_end_0x80": hx(end),
        "table_capacity_0x88": hx(capacity),
        "vector_count": vector_count,
        "capacity_count": capacity_count,
    }


def validate_editable_group(metadata, requested_count, expected_table):
    reasons = []
    try:
        begin = parse_int(metadata.get("table_begin_0x78", "0"))
        end = parse_int(metadata.get("table_end_0x80", "0"))
        capacity = parse_int(metadata.get("table_capacity_0x88", "0"))
    except Exception:
        begin = end = capacity = 0
        reasons.append("group vector addresses could not be parsed")
    if int(metadata.get("count_u16_0x5a") or -1) != int(requested_count):
        reasons.append(f"group layer count does not match requested count ({metadata.get('count_u16_0x5a')} != {requested_count})")
    if parse_int(metadata.get("group", "0")) < MIN_NORMAL_GROUP_ADDRESS:
        reasons.append("group header address is outside the normal FH6 editable group range")
    if not begin or not end or not capacity:
        reasons.append("group vector begin/end/capacity is missing")
    elif not (begin < capacity and begin <= end <= capacity):
        reasons.append("group vector begin/end/capacity is not ordered like a readable layer table")
    capacity_count = metadata.get("capacity_count")
    if capacity_count is None or int(capacity_count) < int(requested_count):
        reasons.append(f"group vector capacity is smaller than requested count ({capacity_count} < {requested_count})")
    if int(expected_table) != begin:
        reasons.append(f"located table does not match group vector table ({hx(expected_table)} != {hx(begin)})")
    return not reasons, reasons


def validate_probe_report(probe_report, requested_count, selected_group, selected_table):
    reasons = []
    try:
        probe = json.loads(Path(probe_report).read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"locator validation report could not be read: {exc}"]
    if int(probe.get("count") or -1) != int(requested_count):
        reasons.append(f"locator report count does not match requested count ({probe.get('count')} != {requested_count})")
    candidates = probe.get("candidates") or []
    min_sample_ok = min(8, int(requested_count))
    strong_count = 0
    selected_seen = False
    selected_strong = False
    for index, candidate in enumerate(candidates, start=1):
        group = candidate.get("group")
        table = candidate.get("table")
        valid_ptrs = int(candidate.get("valid_ptrs") or 0)
        invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, int(requested_count) - valid_ptrs))
        sample_ok = int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)
        capacity_count = candidate.get("capacity_count")
        is_selected = bool(
            group
            and table
            and parse_int(group) == int(selected_group)
            and parse_int(table) == int(selected_table)
        )
        if is_selected:
            selected_seen = True
        is_strong = bool(
            group
            and table
            and (capacity_count is None or int(capacity_count) >= int(requested_count))
            and valid_ptrs >= int(requested_count)
            and invalid_ptrs == 0
            and sample_ok >= min_sample_ok
        )
        if is_strong:
            strong_count += 1
            if is_selected:
                selected_strong = True
    if strong_count <= 0:
        reasons.append("locator report contains no strong editable group candidate")
    if not selected_seen:
        reasons.append("selected group/table was not confirmed by the locator report")
    elif not selected_strong:
        reasons.append("selected group/table did not pass full pointer/vector validation")
    return not reasons, reasons


def write_refusal_report(args, table, group, report_path, metadata=None, reasons=None):
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report = {
        "format": "fh6_typecode_json_export_report_v1",
        "created_utc": created,
        "refused": True,
        "refusal_reason": EXPORT_REFUSAL_MESSAGE,
        "validation_reasons": list(reasons or []),
        "pid": int(args.pid),
        "group": hx(group) if group is not None else None,
        "table": hx(table),
        "requested_count": int(args.count),
        "editable_group_check": {
            "passed": False,
            "metadata": metadata,
            "reasons": list(reasons or []),
        },
        "exported_shape_count": 0,
        "read_layer_count": 0,
        "failure_count": 0,
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(EXPORT_REFUSAL_MESSAGE)
    if reasons:
        log("Validation details: " + "; ".join(str(reason) for reason in reasons[:4]))


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


def rounded_values(values, digits=6):
    return [round(float(value), digits) for value in values]


def layer_fingerprint_item(shape):
    data = list(shape.get("data") or [])
    return {
        "type": int(shape.get("type") or 0),
        "data": rounded_values(data[:7]),
        "color": [int(value) for value in shape.get("color") or []],
        "mask": bool(shape.get("mask")),
    }


def content_hash(shapes):
    digest = hashlib.sha256()
    for shape in shapes:
        digest.update(json.dumps(layer_fingerprint_item(shape), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def summarize_export(shapes, layers):
    type_counts = Counter(str(shape.get("type")) for shape in shapes)
    color_counts = Counter(" ".join(str(int(value)) for value in shape.get("color", [])) for shape in shapes)
    mask_count = sum(1 for shape in shapes if shape.get("mask"))
    read_size_counts = Counter(str(layer.get("read_size")) for layer in layers)
    resource_counts = Counter(str(layer.get("resource_ptr_0xa8")) for layer in layers if layer.get("resource_ptr_0xa8"))
    uniform_template = False
    if shapes:
        first = layer_fingerprint_item(shapes[0])
        uniform_template = all(layer_fingerprint_item(shape) == first for shape in shapes)
    return {
        "content_hash_sha256": content_hash(shapes),
        "type_counts": dict(type_counts.most_common(32)),
        "color_counts": dict(color_counts.most_common(32)),
        "mask_layer_count": mask_count,
        "read_size_counts": dict(read_size_counts.most_common()),
        "resource_ptr_0xa8_counts": dict(resource_counts.most_common(16)),
        "uniform_layer_template": uniform_template,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--group", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--probe-report", default=None)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--skip-transparent", action="store_true")
    args = parser.parse_args()

    table = parse_int(args.table)
    group = parse_int(args.group) if args.group else None
    report_path = Path(args.report) if args.report else Path(args.out).with_suffix(".report.json")
    handle = open_process(args.pid)
    shapes = []
    layers = []
    failures = []
    try:
        if not args.probe_report:
            write_refusal_report(args, table, group, report_path, reasons=["export requires a locator validation report"])
            sys.exit(2)
        probe_ok, probe_reasons = validate_probe_report(args.probe_report, int(args.count), group or 0, table)
        if not probe_ok:
            write_refusal_report(args, table, group, report_path, reasons=probe_reasons)
            sys.exit(2)
        if group is None:
            write_refusal_report(args, table, group, report_path, reasons=["export requires a located FH6 group header"])
            sys.exit(2)
        try:
            group_metadata = read_group_metadata(handle, group)
        except Exception as exc:
            write_refusal_report(args, table, group, report_path, reasons=[f"group header could not be read: {exc}"])
            sys.exit(2)
        editable_ok, editable_reasons = validate_editable_group(group_metadata, int(args.count), table)
        if not editable_ok:
            write_refusal_report(args, table, group, report_path, metadata=group_metadata, reasons=editable_reasons)
            sys.exit(2)
        for index in range(int(args.count)):
            ptr = ptr_at(handle, table, index)
            raw = try_read_memory(handle, ptr, FULL_LAYER_SIZE)
            layer_size = FULL_LAYER_SIZE
            if len(raw) != FULL_LAYER_SIZE:
                raw = try_read_memory(handle, ptr, GROUPED_SAFE_LAYER_SIZE)
                layer_size = GROUPED_SAFE_LAYER_SIZE
            if len(raw) < MIN_LAYER_DECODE_SIZE:
                failures.append({
                    "index": index,
                    "layer": index + 1,
                    "ptr": hx(ptr),
                    "reason": f"short read {len(raw)}",
                })
                continue
            shape, layer = decode_layer(raw, index, ptr, include_raw=args.include_raw)
            layer["read_size"] = layer_size
            if len(raw) >= 0xB0:
                layer["resource_ptr_0xa8"] = hx(struct.unpack_from("<Q", raw, 0xA8)[0])
            layers.append(layer)
            if args.skip_transparent and int(shape["color"][3]) <= 0:
                continue
            shapes.append(shape)
    finally:
        close_handle(handle)

    summary = summarize_export(shapes, layers)
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
            "editable_group_check": {
                "passed": True,
                "metadata": group_metadata,
            },
        },
        "summary": summary,
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
        "editable_group_check": {
            "passed": True,
            "metadata": group_metadata,
        },
        "preferred_layer_read_size": hx(FULL_LAYER_SIZE),
        "fallback_layer_read_size": hx(GROUPED_SAFE_LAYER_SIZE),
        "minimum_decode_size": hx(MIN_LAYER_DECODE_SIZE),
        "exported_shape_count": len(shapes),
        "read_layer_count": len(layers),
        "failure_count": len(failures),
        "summary": summary,
        "output_json": str(out),
        "layers": layers,
        "failures": failures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    log(f"Exported {len(shapes)} layer(s) to {out}")
    log(f"Report: {report_path}")
    if failures:
        log(f"Failures: {len(failures)} unreadable layer(s)")


if __name__ == "__main__":
    main()
