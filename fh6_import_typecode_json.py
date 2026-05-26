#!/usr/bin/env python3
"""Import a type-code handmade JSON into FH6 using save-safe primitive-byte writes."""

from __future__ import annotations

import argparse
import ctypes
import json
import struct
import time
from ctypes import wintypes
from pathlib import Path


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
LAYER_SIZE = 0x140
CLEAR_REQUIRED_SIZE = 0x80

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
k32.WriteProcessMemory.restype = wintypes.BOOL
k32.WriteProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPCVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hx(value):
    return f"0x{int(value):x}"


def parse_int(value):
    return int(str(value), 0)


def open_process(pid, write):
    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    if write:
        access |= PROCESS_VM_OPERATION | PROCESS_VM_WRITE
    handle = k32.OpenProcess(access, False, int(pid))
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


def write_memory(handle, address, raw, write):
    if not write:
        return
    buf = ctypes.create_string_buffer(raw)
    written = ctypes.c_size_t(0)
    ok = k32.WriteProcessMemory(handle, int(address), buf, len(raw), ctypes.byref(written))
    if not ok or written.value != len(raw):
        raise ctypes.WinError(ctypes.get_last_error())


def ptr_at(handle, table, index):
    return struct.unpack("<Q", read_memory(handle, table + index * 8, 8))[0]


def try_read_memory(handle, address, size):
    try:
        return read_memory(handle, address, size)
    except Exception:
        return b""


def decode(raw):
    return {
        "shape_id_byte": raw[0x7A],
        "color_rgba": list(raw[0x74:0x78]),
        "position": list(struct.unpack_from("<ff", raw, 0x18)),
        "scale": list(struct.unpack_from("<ff", raw, 0x28)),
        "rotation": struct.unpack_from("<f", raw, 0x50)[0],
        "resource_ptr_0xa8": hx(struct.unpack_from("<Q", raw, 0xA8)[0]),
    }


def decode_partial(raw):
    out = {
        "bytes_read": len(raw),
    }
    if len(raw) > 0x7A:
        out["shape_id_byte"] = raw[0x7A]
    if len(raw) >= 0x78:
        out["color_rgba"] = list(raw[0x74:0x78])
    if len(raw) >= 0x20:
        out["position"] = list(struct.unpack_from("<ff", raw, 0x18))
    if len(raw) >= 0x30:
        out["scale"] = list(struct.unpack_from("<ff", raw, 0x28))
    if len(raw) >= 0x54:
        out["rotation"] = struct.unpack_from("<f", raw, 0x50)[0]
    if len(raw) >= 0xB0:
        out["resource_ptr_0xa8"] = hx(struct.unpack_from("<Q", raw, 0xA8)[0])
    return out


def clamp_color(values):
    vals = list(values or [255, 255, 255, 255])
    if len(vals) == 3:
        vals.append(255)
    if len(vals) != 4:
        raise ValueError(f"invalid color: {values}")
    return bytes(max(0, min(255, int(v))) for v in vals)


def shape_mask_flag(shape, data):
    for key in ("mask", "is_mask", "isMask"):
        if key in shape:
            return bool(shape.get(key))
    if len(data) > 6:
        try:
            return bool(int(float(data[6])))
        except (TypeError, ValueError):
            return bool(data[6])
    return False


SUPPORTED_PAGE1_CODES = {
    1048677,  # Square
    1048678,  # Circle
    1048679,  # Triangle
    1048688,  # Circle Border
    1048712,  # Ellipse
}


def load_shapes(path, allow_unknown_low_byte=False):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    shapes = payload.get("shapes")
    if not isinstance(shapes, list) or not shapes:
        raise ValueError("JSON must contain non-empty shapes list.")
    out = []
    skipped = []
    for i, shape in enumerate(shapes):
        code = int(shape["type"])
        if code not in SUPPORTED_PAGE1_CODES and not allow_unknown_low_byte:
            skipped_item = {
                "source_index": i,
                "source_layer": i + 1,
                "type_code": code,
                "hex": f"0x{code:x}",
                "reason": "unsupported non-page-1 primitive code",
            }
            skipped.append(skipped_item)
            print(f"[skip] unsupported type code {code} / 0x{code:x} at source layer {i + 1}", flush=True)
            continue
        data = shape["data"]
        if len(data) < 5:
            raise ValueError(f"shape {i} data must have x,y,sx,sy,rotation")
        out.append({
            "index": i,
            "type_code": code,
            "shape_byte": code & 0xFF,
            "shape_word": code & 0xFFFF,
            "page_byte": (code >> 8) & 0xFF,
            "x": float(data[0]),
            "y": float(data[1]),
            "sx": float(data[2]),
            "sy": float(data[3]),
            "rotation": float(data[4]),
            "skew": float(data[5]) if len(data) > 5 else 0.0,
            "extra_data": list(data[5:]),
            "color": list(clamp_color(shape.get("color"))),
            "mask": shape_mask_flag(shape, data),
            "score": shape.get("score"),
        })
    return out, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--template-count", type=int, default=None)
    parser.add_argument("--clear-unused", action="store_true")
    parser.add_argument(
        "--compact-supported-layers",
        action="store_true",
        help="Pack supported source shapes into consecutive target layers, removing holes from skipped unsupported shapes.",
    )
    parser.add_argument("--allow-unknown-low-byte", action="store_true")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    shapes, skipped_shapes = load_shapes(args.json, allow_unknown_low_byte=args.allow_unknown_low_byte)
    if args.limit is not None:
        shapes = shapes[: args.limit]
    table = parse_int(args.table)
    handle = open_process(args.pid, args.write)
    backup_layers = []
    report_layers = []
    failures = []
    partial_clears = []
    try:
        used_indices = set()
        for target_idx, item in enumerate(shapes):
            idx = target_idx if args.compact_supported_layers else item["index"]
            used_indices.add(idx)
            ptr = ptr_at(handle, table, idx)
            before = try_read_memory(handle, ptr, LAYER_SIZE)
            if len(before) != LAYER_SIZE:
                failure = {
                    "phase": "import",
                    "index": idx,
                    "ptr": hx(ptr),
                    "reason": f"unreadable layer blob, read {len(before)} bytes",
                }
                failures.append(failure)
                report_layers.append({**failure, "shape": item, "target_index": idx})
                log(f"FAILED import layer {idx + 1}: {failure['reason']} ptr={hx(ptr)}")
                continue
            backup_layers.append({"index": idx, "ptr": hx(ptr), "raw_hex": before.hex(), "decoded": decode(before)})
            writes = [
                (0x18, struct.pack("<ff", item["x"], item["y"])),
                (0x28, struct.pack("<ff", item["sx"], item["sy"])),
                (0x50, struct.pack("<f", item["rotation"])),
                (0x70, struct.pack("<f", item["skew"])),
                (0x74, bytes(item["color"])),
                (0x78, b"\x01" if item.get("mask") else b"\x00"),
                (0x7A, struct.pack("<H", item["shape_word"])),
            ]
            for offset, raw in writes:
                write_memory(handle, ptr + offset, raw, args.write)
            after = try_read_memory(handle, ptr, LAYER_SIZE) if args.write else before
            if len(after) != LAYER_SIZE:
                after = before
            report_layers.append({
                "index": idx,
                "target_index": idx,
                "source_index": item["index"],
                "ptr": hx(ptr),
                "shape": item,
                "before": decode(before),
                "after": decode(after),
            })
            if target_idx == 0 or (target_idx + 1) % 10 == 0 or target_idx == len(shapes) - 1:
                log(
                    f"{'wrote' if args.write else 'would write'} "
                    f"target {idx + 1}, source {item['index'] + 1} "
                    f"({target_idx + 1}/{len(shapes)}) code={item['type_code']} "
                    f"word=0x{item['shape_word']:04x} byte={item['shape_byte']} page={item['page_byte']}"
                )
        if args.clear_unused:
            if not args.template_count:
                raise ValueError("--clear-unused requires --template-count")
            clear_writes = [
                (0x18, struct.pack("<ff", 0.0, 0.0)),
                (0x28, struct.pack("<ff", 0.001, 0.001)),
                (0x50, struct.pack("<f", 0.0)),
                (0x74, bytes([0, 0, 0, 0])),
                (0x78, b"\x00"),
            ]
            first_clear = None
            for idx in range(int(args.template_count)):
                if idx in used_indices:
                    continue
                if first_clear is None:
                    first_clear = idx
                ptr = ptr_at(handle, table, idx)
                before = try_read_memory(handle, ptr, LAYER_SIZE)
                partial = False
                if len(before) != LAYER_SIZE:
                    prefix = try_read_memory(handle, ptr, CLEAR_REQUIRED_SIZE)
                    if len(prefix) >= CLEAR_REQUIRED_SIZE:
                        before = prefix
                        partial = True
                    else:
                        failure = {
                            "phase": "clear",
                            "index": idx,
                            "ptr": hx(ptr),
                            "reason": f"unreadable layer clear prefix, full read {len(before)} bytes, prefix read {len(prefix)} bytes",
                        }
                        failures.append(failure)
                        if idx == first_clear or (idx + 1) % 100 == 0 or idx == int(args.template_count) - 1:
                            log(f"FAILED clear unused layer {idx + 1}/{args.template_count}: {failure['reason']} ptr={hx(ptr)}")
                        continue
                if partial:
                    partial_item = {
                        "phase": "clear",
                        "index": idx,
                        "ptr": hx(ptr),
                        "reason": f"full layer read crossed unreadable memory; cleared writable prefix {len(before)} bytes",
                    }
                    partial_clears.append(partial_item)
                    backup_layers.append({"index": idx, "ptr": hx(ptr), "raw_hex": before.hex(), "decoded": decode_partial(before), "partial": True})
                else:
                    backup_layers.append({"index": idx, "ptr": hx(ptr), "raw_hex": before.hex(), "decoded": decode(before)})
                for offset, raw in clear_writes:
                    write_memory(handle, ptr + offset, raw, args.write)
                if partial:
                    log(f"{'cleared' if args.write else 'would clear'} unreadable-tail layer {idx + 1}/{args.template_count}: writable prefix only")
                elif idx == first_clear or (idx + 1) % 100 == 0 or idx == int(args.template_count) - 1:
                    log(f"{'cleared' if args.write else 'would clear'} unused layer {idx + 1}/{args.template_count}")
    finally:
        close_handle(handle)

    backup = {"format": "fh6_typecode_json_import_backup_v1", "pid": args.pid, "table": args.table, "source_json": args.json, "layers": backup_layers}
    report = {
        "format": "fh6_typecode_json_import_report_v1",
        "pid": args.pid,
        "table": args.table,
        "source_json": args.json,
        "write": args.write,
        "compact_supported_layers": args.compact_supported_layers,
        "unsupported_shape_count": len(skipped_shapes),
        "unsupported_shapes": skipped_shapes,
        "imported_layer_count": sum(1 for row in report_layers if "after" in row),
        "import_failure_count": sum(1 for row in failures if row.get("phase") == "import"),
        "clear_failure_count": sum(1 for row in failures if row.get("phase") == "clear"),
        "partial_clear_count": len(partial_clears),
        "partial_clears": partial_clears,
        "failure_count": len(failures),
        "failures": failures,
        "layers": report_layers,
    }
    Path(args.backup).write_text(json.dumps(backup, indent=2), encoding="utf-8")
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"backup: {args.backup}")
    log(f"report: {args.report}")
    log(f"failures: {len(failures)}")


if __name__ == "__main__":
    main()
