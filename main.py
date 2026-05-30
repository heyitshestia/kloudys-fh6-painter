# Discord: A-Dawg#0001 (AE)
# Supports: Forza Horizon 5 / Forza Horizon 6 profile probing
# Officially: MS Store/XBOX PC App, Steam.
# Unofficially: Every version that isn't running on a console of via cloud gaming should work.
# License: MIT
# Year: 2022

import sys
import argparse
import ctypes, sys
import psutil
import ctypes
import struct
import subprocess
#from geometrize.geometrize import geometrize_image
#from geometrize.internal_classes import ThreadManager
from native import *
from internal_classes import *
from game_profiles import iter_profiles, PROFILES
from geometry_json import ELLIPSE, RECTANGLE, ROTATED_RECTANGLE, ROTATED_ELLIPSE, load_normalized_geometry
import colorsys
import os

FH6_DISCOVERED_TABLE_POINTER_DELTA = 0x1E
FH6_GROUP_TABLE_BEGIN_OFFSET = 0x78
FH6_GROUP_TABLE_END_OFFSET = 0x80
FH6_GROUP_TABLE_CAPACITY_OFFSET = 0x88
_CV2_CACHE = None
_CV2_ERROR = None

# FH's built-in ellipse primitive does not map perfectly to the generator's
# mathematical ellipse, especially for very large / elongated base shapes.
# These compensation values intentionally make imported ellipses a little
# smaller, with extra shrink on the major axis for long thin blobs.
ELLIPSE_IMPORT_BASE_DIVISOR = 63.0
# Generated geometry rectangles use the legacy geometrize coordinate scale.
# Using the square primitive's direct type-code calibration here makes
# rectangle-heavy generated JSONs import at half size.
RECTANGLE_IMPORT_BASE_DIVISOR = 127.0
DEFAULT_MASK_BUDGET = 4


def parse_int(value):
    if value is None or value == "":
        return None
    return int(str(value), 0)


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def load_cv2():
    global _CV2_CACHE, _CV2_ERROR
    if _CV2_CACHE is not None:
        return _CV2_CACHE
    if _CV2_ERROR is not None:
        return None
    try:
        import cv2
        import numpy as np
        _CV2_CACHE = (cv2, np)
        return _CV2_CACHE
    except BaseException as exc:
        _CV2_ERROR = exc
        return None

def show_image(image):
    print("External preview windows are disabled. Use the desktop app preview panel instead.")

def compensated_ellipse_size(w, h):
    w = float(w)
    h = float(h)
    major = max(w, h)
    minor = max(1.0, min(w, h))
    aspect = major / minor

    uniform_scale = 1.0
    if major >= 220:
        uniform_scale *= 0.985
    if major >= 300:
        uniform_scale *= 0.975

    major_axis_scale = 1.0
    if aspect >= 2.0:
        major_axis_scale *= 0.985
    if aspect >= 3.5:
        major_axis_scale *= 0.970
    if aspect >= 6.0:
        major_axis_scale *= 0.955

    if w >= h:
        sx = uniform_scale * major_axis_scale
        sy = uniform_scale
    else:
        sx = uniform_scale
        sy = uniform_scale * major_axis_scale

    return max(1.0, w * sx), max(1.0, h * sy)


def shape_bbox(shape: Shape):
    if shape.type_id in (ELLIPSE, ROTATED_ELLIPSE, ROTATED_RECTANGLE):
        if shape.type_id in (ELLIPSE, ROTATED_ELLIPSE):
            w, h = compensated_ellipse_size(shape.w, shape.h)
        else:
            w, h = float(shape.w), float(shape.h)
        angle = abs(float(shape.rot_deg)) % 180.0
        if angle > 90.0:
            angle = 180.0 - angle
        import math
        rad = math.radians(angle)
        half_w = abs(math.cos(rad)) * w / 2.0 + abs(math.sin(rad)) * h / 2.0
        half_h = abs(math.sin(rad)) * w / 2.0 + abs(math.cos(rad)) * h / 2.0
    else:
        half_w = float(shape.w) / 2.0
        half_h = float(shape.h) / 2.0
    return (
        float(shape.x) - half_w,
        float(shape.y) - half_h,
        float(shape.x) + half_w,
        float(shape.y) + half_h,
    )


def geometry_bounds(shapes, image_w, image_h):
    visible = [shape_bbox(shape) for shape in shapes if shape.color.a > 0 and not shape.is_mask]
    if not visible:
        return (0.0, 0.0, float(image_w), float(image_h))
    min_x = min(item[0] for item in visible)
    min_y = min(item[1] for item in visible)
    max_x = max(item[2] for item in visible)
    max_y = max(item[3] for item in visible)
    pad = max(8.0, min(float(image_w), float(image_h)) * 0.025)
    return (
        max(0.0, min_x - pad),
        max(0.0, min_y - pad),
        min(float(image_w), max_x + pad),
        min(float(image_h), max_y + pad),
    )


def side_risk_scores(shapes, image_w, image_h):
    margin_x = max(10.0, float(image_w) * 0.08)
    margin_y = max(10.0, float(image_h) * 0.08)
    scores = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    for shape in shapes:
        if shape.color.a <= 0 or shape.is_mask:
            continue
        x0, y0, x1, y1 = shape_bbox(shape)
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        major = max(width, height)
        minor = max(1.0, min(width, height))
        aspect = major / minor
        alpha_weight = max(0.25, float(shape.color.a) / 255.0)
        risk = alpha_weight * (1.0 + max(0.0, aspect - 2.0) * 0.55 + min(3.0, major / max(1.0, min(image_w, image_h))))
        if x0 <= margin_x:
            scores["left"] += risk * (1.0 + max(0.0, margin_x - x0) / margin_x)
        if x1 >= image_w - margin_x:
            scores["right"] += risk * (1.0 + max(0.0, x1 - (image_w - margin_x)) / margin_x)
        if y0 <= margin_y:
            scores["top"] += risk * (1.0 + max(0.0, margin_y - y0) / margin_y)
        if y1 >= image_h - margin_y:
            scores["bottom"] += risk * (1.0 + max(0.0, y1 - (image_h - margin_y)) / margin_y)
    return scores


def build_mask_shape(kind, bounds):
    min_x, min_y, max_x, max_y = bounds
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)
    mid_x = (min_x + max_x) / 2.0
    mid_y = (min_y + max_y) / 2.0
    specs = {
        "left": (min_x - width * 0.25, mid_y, width * 0.50, height * 1.50),
        "right": (max_x + width * 0.25, mid_y, width * 0.50, height * 1.50),
        "top": (mid_x, min_y - height * 0.25, width * 1.50, height * 0.50),
        "bottom": (mid_x, max_y + height * 0.25, width * 1.50, height * 0.50),
        "top_left": (min_x - width * 0.25, min_y - height * 0.25, width * 0.50, height * 0.50),
        "top_right": (max_x + width * 0.25, min_y - height * 0.25, width * 0.50, height * 0.50),
        "bottom_left": (min_x - width * 0.25, max_y + height * 0.25, width * 0.50, height * 0.50),
        "bottom_right": (max_x + width * 0.25, max_y + height * 0.25, width * 0.50, height * 0.50),
    }
    x, y, w, h = specs[kind]
    return Shape(1, int(round(x)), int(round(y)), int(round(w)), int(round(h)), 0, Color(0, 0, 0, 255), True)


def merge_intervals(intervals, gap=8.0):
    if not intervals:
        return []
    ordered = sorted((float(a), float(b)) for a, b in intervals if b > a)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def build_overhang_mask(side, interval, depth, image_w, image_h):
    pad = max(3.0, min(float(image_w), float(image_h)) * 0.006)
    inside_overlap = max(2.0, min(8.0, min(float(image_w), float(image_h)) * 0.006))
    depth = max(1.0, min(float(depth) + pad, max(float(image_w), float(image_h)) * 0.12))
    a, b = interval
    if side in ("left", "right"):
        a = max(0.0, a - pad)
        b = min(float(image_h), b + pad)
        h = max(1.0, b - a)
        w = depth + inside_overlap
        x = (-depth + inside_overlap) / 2.0 if side == "left" else float(image_w) + (depth - inside_overlap) / 2.0
        y = (a + b) / 2.0
    else:
        a = max(0.0, a - pad)
        b = min(float(image_w), b + pad)
        w = max(1.0, b - a)
        h = depth + inside_overlap
        x = (a + b) / 2.0
        y = (-depth + inside_overlap) / 2.0 if side == "top" else float(image_h) + (depth - inside_overlap) / 2.0
    return Shape(1, int(round(x)), int(round(y)), int(round(w)), int(round(h)), 0, Color(0, 0, 0, 255), True)


def choose_overhang_masks(shapes, image_w, image_h, max_masks=DEFAULT_MASK_BUDGET):
    side_data = {
        "left": {"depth": 0.0, "intervals": []},
        "right": {"depth": 0.0, "intervals": []},
        "top": {"depth": 0.0, "intervals": []},
        "bottom": {"depth": 0.0, "intervals": []},
    }
    min_depth = max(0.75, min(float(image_w), float(image_h)) * 0.001)
    for shape in shapes:
        if shape.color.a <= 0 or shape.is_mask:
            continue
        x0, y0, x1, y1 = shape_bbox(shape)
        clipped_x0 = max(0.0, min(float(image_w), x0))
        clipped_x1 = max(0.0, min(float(image_w), x1))
        clipped_y0 = max(0.0, min(float(image_h), y0))
        clipped_y1 = max(0.0, min(float(image_h), y1))
        if x0 < -min_depth and clipped_y1 > clipped_y0:
            side_data["left"]["depth"] = max(side_data["left"]["depth"], -x0)
            side_data["left"]["intervals"].append((clipped_y0, clipped_y1))
        if x1 > float(image_w) + min_depth and clipped_y1 > clipped_y0:
            side_data["right"]["depth"] = max(side_data["right"]["depth"], x1 - float(image_w))
            side_data["right"]["intervals"].append((clipped_y0, clipped_y1))
        if y0 < -min_depth and clipped_x1 > clipped_x0:
            side_data["top"]["depth"] = max(side_data["top"]["depth"], -y0)
            side_data["top"]["intervals"].append((clipped_x0, clipped_x1))
        if y1 > float(image_h) + min_depth and clipped_x1 > clipped_x0:
            side_data["bottom"]["depth"] = max(side_data["bottom"]["depth"], y1 - float(image_h))
            side_data["bottom"]["intervals"].append((clipped_x0, clipped_x1))

    candidates = []
    for side, data in side_data.items():
        merged = merge_intervals(data["intervals"])
        if not merged:
            continue
        # Prefer the largest continuous spill span per side. This keeps mask
        # usage bounded and avoids returning to full-border masks.
        interval = max(merged, key=lambda item: item[1] - item[0])
        span = interval[1] - interval[0]
        score = float(data["depth"]) * max(1.0, span)
        candidates.append((score, side, interval, float(data["depth"]), len(merged)))

    candidates.sort(reverse=True)
    selected = candidates[: max(0, int(max_masks))]
    masks = [build_overhang_mask(side, interval, depth, image_w, image_h) for _score, side, interval, depth, _parts in selected]
    report = {
        "mode": "precise",
        "scores": {side: score for score, side, _interval, _depth, _parts in candidates},
        "needed": [side for _score, side, _interval, _depth, _parts in candidates],
        "selected": [side for _score, side, _interval, _depth, _parts in selected],
        "overhangs": [
            {
                "side": side,
                "interval": [round(interval[0], 3), round(interval[1], 3)],
                "depth": round(depth, 3),
                "merged_spans": parts,
            }
            for _score, side, interval, depth, parts in selected
        ],
        "budget": max_masks,
        "bounds": geometry_bounds(shapes, image_w, image_h),
    }
    return masks, report


def choose_boundary_masks(shapes, image_w, image_h, mode="full", max_masks=DEFAULT_MASK_BUDGET):
    if mode == "off" or max_masks <= 0:
        return [], {"mode": mode, "scores": {}, "needed": [], "selected": [], "budget": max_masks}

    bounds = geometry_bounds(shapes, image_w, image_h)
    if mode == "full":
        selected = ["left", "right", "top", "bottom"][:max(0, int(max_masks))]
        return [build_mask_shape(kind, bounds) for kind in selected], {
            "mode": mode,
            "scores": {},
            "needed": selected,
            "selected": selected,
            "budget": max_masks,
            "bounds": bounds,
        }

    if mode == "precise":
        masks, report = choose_overhang_masks(shapes, image_w, image_h, max_masks=max_masks)
        if masks:
            return masks, report
        return [], {"mode": mode, "scores": {}, "needed": [], "selected": [], "budget": max_masks, "bounds": bounds, "overhangs": []}

    scores = side_risk_scores(shapes, image_w, image_h)
    threshold = 1.2
    needed = {side for side, score in scores.items() if score >= threshold}
    if not needed:
        return [], {"mode": mode, "scores": scores, "needed": [], "selected": [], "budget": max_masks, "bounds": bounds}

    candidates = [
        ("top_left", {"top", "left"}),
        ("top_right", {"top", "right"}),
        ("bottom_left", {"bottom", "left"}),
        ("bottom_right", {"bottom", "right"}),
        ("left", {"left"}),
        ("right", {"right"}),
        ("top", {"top"}),
        ("bottom", {"bottom"}),
    ]
    selected = []
    covered = set()
    budget = max(0, int(max_masks))
    while len(selected) < budget and not needed.issubset(covered):
        best = None
        best_score = 0.0
        for name, sides in candidates:
            if name in selected:
                continue
            new_sides = (sides & needed) - covered
            if not new_sides:
                continue
            score = sum(scores[side] for side in new_sides) / float(len(sides))
            if len(new_sides) > 1:
                score *= 1.25
            if score > best_score:
                best = (name, sides)
                best_score = score
        if best is None:
            break
        selected.append(best[0])
        covered.update(best[1] & needed)

    return [build_mask_shape(kind, bounds) for kind in selected], {
        "mode": mode,
        "scores": scores,
        "needed": sorted(needed),
        "selected": selected,
        "covered": sorted(covered),
        "budget": max_masks,
        "bounds": bounds,
    }

def get_pid(game_key=None, pid_override=None):
    if pid_override:
        try:
            proc = psutil.Process(pid_override)
            proc_name = proc.name()
            for profile in iter_profiles(game_key):
                if proc_name.lower() in [name.lower() for name in profile.process_names]:
                    print("{} detected as {} (pid {})".format(profile.label, proc_name, pid_override))
                    return pid_override, profile
            if game_key:
                profile = next(iter_profiles(game_key))
                print("{} selected for {} (pid {})".format(profile.label, proc_name, pid_override))
                return pid_override, profile
            print("PID {} is running as {}, but it does not match a supported profile.".format(pid_override, proc_name))
        except psutil.Error as exc:
            print("Unable to inspect pid {}: {}".format(pid_override, exc))
        return -1, None

    process_lookup = {}
    for proc in psutil.process_iter():
        try:
            process_lookup[proc.name().lower()] = proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    for profile in iter_profiles(game_key):
        for process_name in profile.process_names:
            pid = process_lookup.get(process_name.lower())
            if pid:
                print("{} detected as {} (pid {})".format(profile.label, process_name, pid))
                return pid, profile
    if game_key:
        profile_names = ", ".join(next(iter_profiles(game_key)).process_names)
        print("{} is not running ({})".format(game_key.upper(), profile_names))
    else:
        names = ", ".join(name for profile in iter_profiles() for name in profile.process_names)
        print("No supported Forza Horizon process is running ({})".format(names))
    return -1, None

def find_livery_signature(pid, base_addr, profile):
    for start_offset, block_size in profile.scan_regions:
        start_address = base_addr + start_offset
        for signature in profile.signature_patterns:
            print("Scanning {} Base+{:x}..Base+{:x}".format(
                profile.label, start_offset, start_offset + block_size))
            relative_address = scan_block(pid, start_address, block_size, signature)
            if relative_address != -1:
                return start_address + relative_address, signature
    return -1, None

def calculate_CLivery(pid, profile):
    base_addr = get_base_address(pid)
    print("Attempting to scan for {} livery address:".format(profile.label))
    preAddrA, signature = find_livery_signature(pid, base_addr, profile)
    if preAddrA == -1:
        print("Unsupported {} version and cannot find a matching pattern.".format(profile.label))
        print("FH6 support may need a new signature or offsets for this game build.")
        return -1
    print("Signature {} found at Base+{:x}".format(signature.hex(" "), preAddrA - base_addr))
    if read_long(pid, preAddrA) != read_long(pid, preAddrA + profile.validation_mirror_offset):
        print("Matching signature failed validation at Base+{:x}".format(preAddrA - base_addr))
        return -1
    addrA = dereference_pointer(pid, preAddrA + profile.livery_root_pointer_offset)
    print("Found livery root pointer at Base+{0:x}".format(preAddrA + profile.livery_root_pointer_offset - base_addr))
    addrB = dereference_pointer(pid, addrA + profile.editor_pointer_offset)
    if addrB == 0:
        print("Create Vinyl Group menu not detected")
        return -1
    cLivery = dereference_pointer(pid, addrB + profile.livery_pointer_offset)
    if cLivery == 0:
        print("Create Vinyl Group menu not detected")
        return -1
    return cLivery

def diagnose_livery(pid, profile):
    try:
        base_addr = get_base_address(pid)
    except Exception as exc:
        print("Unable to open process {}. Try running as administrator. {}".format(pid, exc))
        return False

    print("{} diagnostics for pid {}".format(profile.label, pid))
    print("Base address: 0x{:x}".format(base_addr))
    found_valid = False
    for start_offset, block_size in profile.scan_regions:
        start_address = base_addr + start_offset
        for signature in profile.signature_patterns:
            relative_address = scan_block(pid, start_address, block_size, signature)
            if relative_address == -1:
                print("No match in Base+{:x}..Base+{:x}".format(start_offset, start_offset + block_size))
                continue
            absolute_address = start_address + relative_address
            print("Signature {} found at Base+{:x}".format(signature.hex(" "), absolute_address - base_addr))
            try:
                mirror_equal = read_long(pid, absolute_address) == read_long(pid, absolute_address + profile.validation_mirror_offset)
                root = dereference_pointer(pid, absolute_address + profile.livery_root_pointer_offset)
                editor = dereference_pointer(pid, root + profile.editor_pointer_offset) if root else 0
                livery = dereference_pointer(pid, editor + profile.livery_pointer_offset) if editor else 0
                print("Validation mirror: {}".format("OK" if mirror_equal else "FAILED"))
                print("Root pointer: 0x{:x}".format(root))
                print("Editor pointer: 0x{:x}".format(editor))
                print("Livery pointer: 0x{:x}".format(livery))
                found_valid = found_valid or (mirror_equal and root != 0 and editor != 0 and livery != 0)
            except Exception as exc:
                print("Pointer chain failed: {}".format(exc))
    if not found_valid:
        print("No validated livery pointer chain found.")
    return found_valid

def draw_memory_shape(pid: int, profile, shape: Shape, index: int, cLiveryLayerTable: int, liveryCount: int):
    if index >= liveryCount:
        return True
    current_layer_address = dereference_pointer(pid, cLiveryLayerTable + (index * 0x8))
    if current_layer_address == 0:
        print("ERROR: FH6 layer slot {} resolved to a null pointer.".format(index + 1))
        print("The located template table is stale or invalid. Stay in Vinyl Group Editor and run Auto Locate again.")
        return False
    pos_data = struct.pack('f', shape.x) + struct.pack('f', -shape.y)
    try:
        write_process_memory(pid, current_layer_address + profile.layer_position_offset, pos_data)
        if shape.type_id in (ELLIPSE, ROTATED_ELLIPSE):
            adj_w, adj_h = compensated_ellipse_size(shape.w, shape.h)
            scale_data = struct.pack('f', adj_w / ELLIPSE_IMPORT_BASE_DIVISOR) + struct.pack('f', adj_h / ELLIPSE_IMPORT_BASE_DIVISOR)
        else:
            scale_data = struct.pack('f', shape.w / RECTANGLE_IMPORT_BASE_DIVISOR) + struct.pack('f', shape.h / RECTANGLE_IMPORT_BASE_DIVISOR)
        write_process_memory(pid, current_layer_address + profile.layer_scale_offset, scale_data)
        rot_data = struct.pack('f', 360 - shape.rot_deg)
        write_process_memory(pid, current_layer_address + profile.layer_rotation_offset, rot_data)
        color_data = shape.color.get_struct()
        write_process_memory(pid, current_layer_address + profile.layer_color_offset, color_data)
        if shape.type_id in (ELLIPSE, ROTATED_ELLIPSE):
            shape_id_data = struct.pack('B', 102)
            write_process_memory(pid, current_layer_address + profile.layer_shape_id_offset, shape_id_data)
        elif shape.type_id in (RECTANGLE, ROTATED_RECTANGLE):
            shape_id_data = struct.pack('B', 101)
            write_process_memory(pid, current_layer_address + profile.layer_shape_id_offset, shape_id_data)
        mask_flag = struct.pack('B', 1 if shape.is_mask else 0)
        write_process_memory(pid, current_layer_address + profile.layer_mask_offset, mask_flag)
    except Exception as exc:
        print("ERROR: Failed to write FH6 layer {} at 0x{:x}: {}".format(index + 1, current_layer_address, exc))
        if index == 0:
            print("FH6 rejected writes to the first template slot.")
            print("This usually means the located layer table/editor state is stale, not that later layers are still grouped.")
            print("Reload the ungrouped template, stay in Vinyl Group Editor, and run Auto Locate again.")
            return False
        if index > 0:
            print("Detected grouped vinyl in slot " + str(index+1))
        print("ERROR: You probably forgot to ungroup one of your vinyls.")
        print("Also ensure you are in the Vinyl Group Editor, not applying the vinyl or a livery to the car.")
        return False
    return True
    

def trim_fh6_group_count(pid, profile, group_address, table_address, old_count, new_count):
    if profile.key != "fh6":
        return
    if not group_address or not table_address:
        print("Layer count culling skipped: missing FH6 group/table address.")
        return
    new_count = max(0, min(int(new_count), int(old_count)))
    if new_count >= int(old_count):
        print("Layer count culling skipped: imported count already matches the template.")
        return
    count_address = int(group_address) + profile.livery_count_offset
    table_end_address = int(group_address) + FH6_GROUP_TABLE_END_OFFSET
    new_table_end = int(table_address) + new_count * 8
    write_process_memory(pid, count_address, struct.pack("<H", new_count))
    write_process_memory(pid, table_end_address, struct.pack("<Q", new_table_end))
    print(
        "Culled FH6 layer count: {} -> {} layers; table end -> 0x{:x}".format(
            old_count,
            new_count,
            new_table_end,
        )
    )


def read_u16_le(pid, address):
    raw = read_process_memory(pid, int(address), 2)
    return int.from_bytes(raw, byteorder="little") if len(raw) == 2 else None


def read_u64_le(pid, address):
    raw = read_process_memory(pid, int(address), 8)
    return int.from_bytes(raw, byteorder="little") if len(raw) == 8 else None


def validate_fh6_live_group(pid, profile, group_address, table_address, expected_count=None):
    if profile.key != "fh6":
        return True, None
    if not group_address or not table_address:
        print("ERROR: Missing FH6 group/table address.")
        return False, None
    actual_count = read_u16_le(pid, int(group_address) + profile.livery_count_offset)
    if actual_count is None:
        print("ERROR: Could not read the live FH6 group layer count.")
        return False, None
    if expected_count is not None and int(expected_count) != int(actual_count):
        print(
            "ERROR: Located FH6 group count is {}, but the open template count was set to {}.".format(
                actual_count,
                expected_count,
            )
        )
        print("This is a stale template address. Reload the saved/reopened template and import again.")
        return False, None
    table_begin = read_u64_le(pid, int(group_address) + FH6_GROUP_TABLE_BEGIN_OFFSET)
    table_end = read_u64_le(pid, int(group_address) + FH6_GROUP_TABLE_END_OFFSET)
    table_capacity = read_u64_le(pid, int(group_address) + FH6_GROUP_TABLE_CAPACITY_OFFSET)
    expected_end = int(table_address) + int(actual_count) * 8
    if table_begin != int(table_address):
        print(
            "ERROR: Located FH6 table does not match the active group table. group table=0x{:x}, located table=0x{:x}".format(
                int(table_begin or 0),
                int(table_address),
            )
        )
        print("This is a stale or wrong editor table. No layers were written.")
        return False, None
    if table_end != expected_end or table_capacity is None or table_capacity < table_end:
        print(
            "ERROR: FH6 group vector metadata is not safe. begin=0x{:x}, end=0x{:x}, cap=0x{:x}, expected_end=0x{:x}".format(
                int(table_begin or 0),
                int(table_end or 0),
                int(table_capacity or 0),
                int(expected_end),
            )
        )
        print("This is a stale or already-trimmed template table. No layers were written.")
        return False, None
    return True, actual_count


def load_geometry(
    path,
    game_key=None,
    preview_enabled=True,
    pid_override=None,
    layer_count_address=None,
    layer_table_address=None,
    layer_count_value=None,
    boundary_mask_mode="off",
    boundary_mask_budget=DEFAULT_MASK_BUDGET,
):
    try:
        data = load_normalized_geometry(path)
    except Exception as exc:
        print("Not a valid generated geometry .json file: {}".format(exc))
        return

    # validation and build our collection of shapes
    image_w, image_h = data['shapes'][0]['data'][2:]
    bg_r, bg_g, bg_b, bg_a = data['shapes'][0]['color']
    shapes = []
    
    # If the exported geometry has a visible rectangle background, add it.
    # Transparent PNG exports often include an alpha=0 background rectangle;
    # writing that layer can turn into a visible fallback color in-game.
    if bg_a > 0:
        shapes.append(Shape(1, int(image_w//2), int(image_h//2), image_w, image_h, 0, Color(bg_r,bg_g,bg_b,bg_a), False))

    for shape in data['shapes'][1:]:
        #shape.color = [r,g,b,a]
        #shape.data = [x,y,w,h,rot_deg]
        if len(shape.get('color', [])) == 4 and int(shape['color'][3]) <= 0:
            continue
        if shape['type'] in (ELLIPSE, ROTATED_ELLIPSE):
            x,y,w,h = shape['data'][:4]
            rot_deg = shape['data'][4] if shape['type'] == ROTATED_ELLIPSE and len(shape['data']) >= 5 else 0
            r,g,b,a = shape['color']
            shapes.append(Shape(shape['type'], x, y, w, h, rot_deg, Color(r,g,b,a), False))
        elif shape['type'] == RECTANGLE:
            x,y,w,h = shape['data'][:4]
            r,g,b,a = shape['color']
            shapes.append(Shape(shape['type'], x, y, w, h, 0, Color(r,g,b,a), False))
        elif shape['type'] == ROTATED_RECTANGLE:
            x,y,w,h,rot_deg = shape['data']
            r,g,b,a = shape['color']
            shapes.append(Shape(shape['type'], x, y, w, h, rot_deg, Color(r,g,b,a), False))
        else:
            print("Skipping unsupported shape type {}.".format(shape.get("type")))
    if len(shapes) == 0:
        print("No shapes were loaded. Check your exported geometry .json")
        return
    
    loaded = load_cv2()
    if loaded:
        cv2, np = loaded
        checker = np.zeros((image_h, image_w, 3), np.float32)
        premul = np.zeros((image_h, image_w, 3), np.float32)
        alpha_canvas = np.zeros((image_h, image_w), np.float32)
        if bg_a > 0:
            base_alpha = max(0.0, min(1.0, float(bg_a) / 255.0))
            premul[:, :] = np.array((bg_b, bg_g, bg_r), dtype=np.float32) * base_alpha
            alpha_canvas[:, :] = base_alpha
            checker[:, :] = (38, 38, 38)
        else:
            checker[:, :] = (38, 38, 38)
        for shape in shapes:
            if shape.color.a <= 0:
                continue
            if shape.type_id in (ELLIPSE, ROTATED_ELLIPSE):
                adj_w, adj_h = compensated_ellipse_size(shape.w, shape.h)
                mask = np.zeros((image_h, image_w), np.uint8)
                cv2.ellipse(mask, (shape.x, shape.y), (int(round(adj_h)), int(round(adj_w))), -90 + shape.rot_deg, 0., 360, 255, thickness=-1)
                alpha = max(0.0, min(1.0, float(shape.color.a) / 255.0))
                if alpha > 0.0:
                    shape_mask = mask > 0
                    src = np.array((shape.color.b, shape.color.g, shape.color.r), dtype=np.float32)
                    old_alpha = alpha_canvas[shape_mask]
                    premul[shape_mask] = src * alpha + premul[shape_mask] * (1.0 - alpha)
                    alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)
            elif shape.type_id in (RECTANGLE, ROTATED_RECTANGLE):
                alpha = max(0.0, min(1.0, float(shape.color.a) / 255.0))
                if alpha > 0.0:
                    mask = np.zeros((image_h, image_w), np.uint8)
                    if shape.type_id == ROTATED_RECTANGLE and shape.rot_deg % 360:
                        rect = ((float(shape.x), float(shape.y)), (max(1.0, float(shape.w)), max(1.0, float(shape.h))), float(shape.rot_deg))
                        box = cv2.boxPoints(rect).astype(np.int32)
                        cv2.fillConvexPoly(mask, box, 255)
                    else:
                        x0 = int(round(shape.x - shape.w / 2))
                        y0 = int(round(shape.y - shape.h / 2))
                        x1 = int(round(shape.x + shape.w / 2))
                        y1 = int(round(shape.y + shape.h / 2))
                        cv2.rectangle(mask, (x0, y0), (x1, y1), 255, thickness=-1)
                    shape_mask = mask > 0
                    src = np.array((shape.color.b, shape.color.g, shape.color.r), dtype=np.float32)
                    old_alpha = alpha_canvas[shape_mask]
                    premul[shape_mask] = src * alpha + premul[shape_mask] * (1.0 - alpha)
                    alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)

        if preview_enabled:
            print("Here is a preview of your image, click it then press any key to start!")
            preview = premul + checker * (1.0 - alpha_canvas[..., None])
            preview_u8 = np.clip(preview, 0, 255).astype(np.uint8)
            show_image(preview_u8)
            cv2.imwrite("preview.png", preview_u8)
    elif preview_enabled:
        print("Preview unavailable because OpenCV/Numpy could not be loaded. Import will continue.")
    
    # Finding the game PID
    pid, profile = get_pid(game_key, pid_override)
    if pid == -1:
        return

    cLiveryGroup = None
    if layer_count_address:
        if profile.key == "fh6":
            cLiveryGroup = int(layer_count_address) - int(profile.livery_count_offset)
            actual_count = read_u16_le(pid, layer_count_address)
            if actual_count is None:
                print("ERROR: Could not read manual FH6 layer count address 0x{0:x}.".format(layer_count_address))
                return
            current_livery_count = int(actual_count)
            print("Manual FH6 layer count address 0x{0:x} -> {1}".format(layer_count_address, current_livery_count))
            if layer_count_value and int(layer_count_value) != current_livery_count:
                print(
                    "ERROR: Open FH6 template count is {}, but the importer expected {}.".format(
                        current_livery_count,
                        int(layer_count_value),
                    )
                )
                print("The located count/table is stale. Reload a fresh ungrouped template and import again.")
                return
        elif layer_count_value:
            current_livery_count = int(layer_count_value)
            print("Manual layer count address 0x{0:x}; using template layer count {1}".format(layer_count_address, current_livery_count))
        else:
            current_livery_count = read_int(pid, layer_count_address)
            print("Manual layer count address 0x{0:x} -> {1}".format(layer_count_address, current_livery_count))
        if not layer_table_address:
            table_pointer_field = layer_count_address + FH6_DISCOVERED_TABLE_POINTER_DELTA
            layer_table_address = dereference_pointer(pid, table_pointer_field)
            print("Manual table pointer field 0x{0:x} -> 0x{1:x}".format(table_pointer_field, layer_table_address))
        cLiveryLayerTable = layer_table_address
        ok, live_count = validate_fh6_live_group(pid, profile, cLiveryGroup, cLiveryLayerTable, current_livery_count if profile.key == "fh6" else None)
        if not ok:
            return
        if live_count is not None:
            current_livery_count = live_count
    else:
        # Calculate the pointer chain to the cLiveryLayerTable
        cLivery = calculate_CLivery(pid, profile)
        if cLivery == -1:
            return
        print("CLivery found at {0:x}".format(cLivery))
        cLiveryGroup = dereference_pointer(pid, cLivery + profile.livery_group_offset)
        if cLiveryGroup == 0:
            print("cLiveryGroup is invalid...")
            print("You are probably not in `Create Vinyl Group` menu...")
            return
        print("CLiveryGroup found at {0:x}".format(cLiveryGroup))
        current_livery_count = read_int(pid, cLiveryGroup + profile.livery_count_offset)
        cLiveryLayerTable = dereference_pointer(pid, cLiveryGroup + profile.layer_table_offset)

    # If we have less than 100 shapes, user has likely made a mistake
    if current_livery_count < 100:
        print("READ THE INSTRUCTIONS")
        print("You must load a vinyl group (ALL SPHERES) with your desired shape count (minimum 100) first!")
        print("500, 1000, 1500, 2000 or 3000 is recommended")
        print("Make sure to ungroup the vinyl before starting 1also!")
        return

    if cLiveryLayerTable == 0:
        print("cLiveryLayer table is invalid...")
        print("You are probably not in `Create Vinyl Group` menu..")
        return
    print("CLiveryLayer table found at {0:x}".format(cLiveryLayerTable))
    first_slot = dereference_pointer(pid, cLiveryLayerTable)
    if first_slot == 0:
        print("ERROR: The discovered FH6 layer table does not point to a valid first slot.")
        print("Reload the ungrouped template, stay in Vinyl Group Editor, and run Auto Locate again.")
        return

    mask_budget = max(0, min(4, int(boundary_mask_budget)))
    mask_mode = str(boundary_mask_mode or "off").strip().lower()
    if mask_mode not in ("precise", "full", "off"):
        mask_mode = "off"

    requested_drawable_count = len(shapes)
    target_total_layers = max(0, min(int(current_livery_count), 3000, requested_drawable_count))
    preliminary_reserved = mask_budget if mask_mode == "full" else 0
    preliminary_capacity = max(0, target_total_layers - preliminary_reserved)
    if len(shapes) > preliminary_capacity:
        print(
            "Geometry has {} drawable layers but FH mask budget reserves up to {} layers; trimming to {} drawable layers before mask selection.".format(
                len(shapes), preliminary_reserved, preliminary_capacity
            )
        )
        shapes = shapes[:preliminary_capacity]

    boundary_masks, mask_report = choose_boundary_masks(shapes, image_w, image_h, mode=mask_mode, max_masks=mask_budget)
    reserved_mask_layers = len(boundary_masks)
    drawable_capacity = max(0, target_total_layers - reserved_mask_layers)
    if shapes and drawable_capacity == 0:
        drawable_capacity = 1

    if len(shapes) > drawable_capacity:
        print(
            "Geometry has {} drawable layers but selected {} FH mask layers; trimming to {} drawable layers to keep {} total layers.".format(
                len(shapes), reserved_mask_layers, drawable_capacity, target_total_layers
            )
        )
        shapes = shapes[:drawable_capacity]
        boundary_masks, mask_report = choose_boundary_masks(shapes, image_w, image_h, mode=mask_mode, max_masks=mask_budget)
        reserved_mask_layers = len(boundary_masks)
        drawable_capacity = max(0, target_total_layers - reserved_mask_layers)
        if shapes and drawable_capacity == 0:
            drawable_capacity = 1
        if len(shapes) > drawable_capacity:
            shapes = shapes[:drawable_capacity]

    shapes.extend(boundary_masks)
    imported_layer_count = len(shapes)

    print(
        "Drawable layers to import: {} + {} FH mask layers / template layers: {}".format(
            max(0, len(shapes) - reserved_mask_layers),
            reserved_mask_layers,
            current_livery_count,
        )
    )
    print(
        "FH mask strategy: mode={} budget={} selected={} needed={}".format(
            mask_report.get("mode"),
            mask_report.get("budget"),
            ",".join(mask_report.get("selected") or ["none"]),
            ",".join(mask_report.get("needed") or ["none"]),
        )
    )
    print("FH6 import scale: ellipse divisor={}, rectangle divisor={}".format(
        ELLIPSE_IMPORT_BASE_DIVISOR,
        RECTANGLE_IMPORT_BASE_DIVISOR,
    ))
    
    # Enumerate every template slot. Any unused slot is hidden so larger templates
    # do not leave their original spheres visible after importing smaller JSON.
    clear_shape = Shape(1, 0, 0, 0, 0, 0, Color(0, 0, 0, 0), False)
    for i in range(current_livery_count):
        shape = shapes[i] if i < len(shapes) else clear_shape
        if i == 0 or (i + 1) % 100 == 0 or i + 1 == current_livery_count:
            print("Writing layer {}/{}".format(i + 1, current_livery_count), flush=True)
        if not draw_memory_shape(pid, profile, shape, i, cLiveryLayerTable, current_livery_count):
            return

    trim_fh6_group_count(pid, profile, cLiveryGroup, cLiveryLayerTable, current_livery_count, imported_layer_count)
    
    print("DONE!")

    # Show the background color as the ideal car color in HSV format
    h,s,v = colorsys.rgb_to_hsv(bg_r / float(255), bg_g / float(255), bg_b / float(255))
    print("The ideal background color for the car is:\n{:.2f},{:.2f},{:.2f}".format(h,s,v))

def parse_args(args):
    parser = argparse.ArgumentParser(description="Import generated geometry into Forza Horizon vinyl editor.")
    parser.add_argument("--game", choices=PROFILES.keys(), default=os.environ.get("FORZA_PAINTER_GAME"),
                        help="Target game profile. Defaults to auto-detecting a running supported game.")
    parser.add_argument("--pid", type=int, default=None, help="Use a specific running game process id.")
    parser.add_argument("--no-preview", action="store_true", help="Skip the OpenCV preview prompt.")
    parser.add_argument("--diagnose", action="store_true", help="Run read-only process signature diagnostics.")
    parser.add_argument("--layer-count-address", type=parse_int, default=None,
                        help="Manual live layer-count address, e.g. 0x16debce3a9a. Bypasses signature chain.")
    parser.add_argument("--layer-table-address", type=parse_int, default=None,
                        help="Manual live layer-table address. If omitted with --layer-count-address, uses count+0x1e pointer field.")
    parser.add_argument("--layer-count-value", type=int, default=None,
                        help="Known template layer count. Used by FH6 because the live count field is u16 inside a larger structure.")
    parser.add_argument("--fh-boundary-mask-mode", choices=("precise", "full", "off"), default="off",
                        help="FH6 bounds mask strategy: off by default, full legacy 4-mask frame, or precise/adaptive test mode.")
    parser.add_argument("--fh-boundary-mask-budget", type=int, default=DEFAULT_MASK_BUDGET,
                        help="Maximum FH6 bounds mask layers to spend in precise/full mode. Default: 4.")
    parser.add_argument("geometry_path", nargs="*", help="Generated .json geometry file path.")
    parsed = parser.parse_args(args[1:])
    parsed.geometry_path = " ".join(parsed.geometry_path)
    return parsed

def main(args):
    if not is_64bit():
        print("Your Python version is 32-bit. Please install 64-bit Python.\nThis is required for IPC with Forza Horizon as it is a 64-bit process.")
        return
    parsed = parse_args(args)
    if parsed.diagnose:
        pid, profile = get_pid(parsed.game, parsed.pid)
        if pid != -1:
            diagnose_livery(pid, profile)
        return
    if not parsed.geometry_path:
        print("You must drag in a generated geometry .json file!")
        return
    path = parsed.geometry_path

    if not os.path.isfile(path):
        print("{} is not a valid file path!".format(path))
        return
    ext = path.split('.')[-1].lower()
    #accepted_image_formats = ["jpg", "jpeg", "png", "bmp"]
    is_geometry = ext == "json"
    if not is_geometry:# and not ext in accepted_image_formats:
        print("Expected 1 file as the only argument.")
        print("An image file, or an generated .json geometry file.")
        return
    if is_geometry:
        load_geometry(
            path,
            parsed.game,
            not parsed.no_preview,
            parsed.pid,
            parsed.layer_count_address,
            parsed.layer_table_address,
            parsed.layer_count_value,
            parsed.fh_boundary_mask_mode,
            parsed.fh_boundary_mask_budget,
        )
    # else:
    #     geometrize_image(path)

if __name__ == "__main__":
    if is_admin() or os.environ.get("FORZA_PAINTER_NO_ELEVATE") == "1":
        # Capture any exceptions
        try:
            main(sys.argv)
        except Exception:
            print(sys.exc_info()[0])
            import traceback
            print(traceback.format_exc())
        finally:
            #ThreadManager.ensure_all_threads_killed()
            if os.environ.get("FORZA_PAINTER_NO_PAUSE") != "1":
                print("Press Enter to continue ...")
                try:
                    input()
                except EOFError:
                    pass
    else:
        # Run as admin
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, subprocess.list2cmdline(sys.argv), None, 1)
