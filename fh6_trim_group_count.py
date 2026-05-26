#!/usr/bin/env python3
"""Experimental FH6 group count trim. High risk; prototype only."""

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
COUNT_OFF = 0x5A
TABLE_BEGIN_OFF = 0x78
TABLE_END_OFF = 0x80
TABLE_CAP_OFF = 0x88
HEADER_SIZE = 0x120

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--new-count", type=int, required=True)
    parser.add_argument("--table", default=None)
    parser.add_argument("--trim-vector-end", action="store_true")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    group = parse_int(args.group)
    handle = open_process(args.pid, args.write)
    try:
        before = read_memory(handle, group, HEADER_SIZE)
        old_u16 = struct.unpack_from("<H", before, COUNT_OFF)[0]
        old_u32 = struct.unpack_from("<I", before, COUNT_OFF)[0]
        old_begin = struct.unpack_from("<Q", before, TABLE_BEGIN_OFF)[0]
        old_end = struct.unpack_from("<Q", before, TABLE_END_OFF)[0]
        old_cap = struct.unpack_from("<Q", before, TABLE_CAP_OFF)[0]
        table = parse_int(args.table) if args.table else old_begin
        old_vector_count = (old_end - old_begin) // 8 if old_end >= old_begin else None
        payload = {
            "format": "fh6_trim_group_count_backup_v1",
            "pid": args.pid,
            "group": hx(group),
            "count_offset": hx(COUNT_OFF),
            "old_count_u16": old_u16,
            "old_count_u32_at_count_offset": old_u32,
            "new_count": args.new_count,
            "old_table_begin": hx(old_begin),
            "old_table_end": hx(old_end),
            "old_table_capacity": hx(old_cap),
            "old_vector_count": old_vector_count,
            "new_table_end": hx(table + int(args.new_count) * 8),
            "header_size": HEADER_SIZE,
            "header_raw_hex": before.hex(),
        }
        Path(args.backup).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log(f"backup: {args.backup}")
        raw = struct.pack("<H", int(args.new_count))
        write_memory(handle, group + COUNT_OFF, raw, args.write)
        log(f"{'wrote' if args.write else 'would write'} count {old_u16} -> {args.new_count} at {hx(group + COUNT_OFF)}")
        if args.trim_vector_end:
            new_end = table + int(args.new_count) * 8
            write_memory(handle, group + TABLE_END_OFF, struct.pack("<Q", new_end), args.write)
            log(
                f"{'wrote' if args.write else 'would write'} table end "
                f"{hx(old_end)} -> {hx(new_end)} at {hx(group + TABLE_END_OFF)} "
                f"(old vector count={old_vector_count})"
            )
    finally:
        close_handle(handle)


if __name__ == "__main__":
    main()
