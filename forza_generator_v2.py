#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import json
import math
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image
import cv2


ROOT = Path(__file__).resolve().parent
BUNDLED_WINDOWS_GENERATOR = ROOT / "forza-painter-geometrize-go.exe"
LOCAL_LINUX_GENERATOR = Path("/home/hestia/.local/share/forza-painter-geometrize-gpu/forza-painter-geometrize-go-linux-arm64")
GENERATOR_BIN = BUNDLED_WINDOWS_GENERATOR if os.name == "nt" else (LOCAL_LINUX_GENERATOR if LOCAL_LINUX_GENERATOR.is_file() else BUNDLED_WINDOWS_GENERATOR)
LD_LIBRARY_PATH = f"/home/hestia/.local/lib:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":")
FH6_RESERVED_BOUNDARY_LAYERS = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Forza Generator V2: generate target checkpoints, "
            "optionally prune low-contribution ellipse layers, and write manual-pick "
            "V2 JSON outputs for each usable checkpoint."
        )
    )
    parser.add_argument("image", help="Source image path")
    parser.add_argument("--settings", required=True, help="Base generator settings .ini")
    parser.add_argument("--out-dir", required=True, help="Output directory for this run")
    parser.add_argument(
        "--stop-file",
        default="",
        help="Optional stop-request marker path. If created during generation, V2 stops the raw generator and finalizes from existing checkpoints.",
    )
    parser.add_argument(
        "--target-shapes",
        type=int,
        default=0,
        help="Final drawable target. Defaults to stopAt from settings.",
    )
    parser.add_argument(
        "--overshoot-ratio",
        type=float,
        default=1.0,
        help="Optional overshoot ratio before pruning. Default: 1.0 (disabled)",
    )
    parser.add_argument(
        "--overshoot-max-extra",
        type=int,
        default=0,
        help="Maximum extra shapes above target when overshoot is enabled. Default: 0",
    )
    parser.add_argument(
        "--checkpoint-step",
        type=int,
        default=250,
        help="Checkpoint interval used in the V2 temp settings. Default: 250",
    )
    parser.add_argument(
        "--score-size",
        type=int,
        default=640,
        help="Maximum scoring resolution for candidate evaluation/pruning. Default: 640",
    )
    parser.add_argument(
        "--efficiency-tolerance",
        type=float,
        default=0.0,
        help=(
            "Pick the smallest shape count whose error is within this fraction of the "
            "best candidate. Default: 0.0 (disabled)"
        ),
    )
    parser.add_argument(
        "--enable-prune",
        action="store_true",
        help="Enable contribution-based cleanup/pruning. Disabled by default.",
    )
    parser.add_argument(
        "--keep-temp-settings",
        action="store_true",
        help="Keep the generated V2 temp settings file in the output directory.",
    )
    parser.add_argument(
        "--preprocess-mode",
        choices=("none", "luma_bands"),
        default="none",
        help="Optional preprocess mode to simplify the source before generation/scoring.",
    )
    parser.add_argument(
        "--enable-repair",
        action="store_true",
        help="Enable the targeted local repair pass on the selected final candidate.",
    )
    parser.add_argument(
        "--repair-candidate-limit",
        type=int,
        default=4,
        help=(
            "Only run targeted repair on the best N scored checkpoints plus the latest checkpoint. "
            "Use 0 to repair every checkpoint. Default: 4"
        ),
    )
    parser.add_argument(
        "--preview-candidate-limit",
        type=int,
        default=4,
        help=(
            "Only render full V2 preview PNGs for the best N scored checkpoints plus the latest checkpoint. "
            "Use 0 to render every preview. JSON browser can still preview unrendered files on demand. Default: 4"
        ),
    )
    parser.add_argument(
        "--disable-refine",
        action="store_true",
        help="Deprecated alias. Keeps repair disabled.",
    )
    parser.add_argument(
        "--run-metadata",
        default="",
        help="Optional JSON metadata from the UI describing selected presets, overrides, and toggles.",
    )
    return parser.parse_args()


def parse_ini(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_run_metadata(path: str) -> dict:
    if not path:
        return {}
    metadata_path = Path(path).expanduser()
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "metadata_path": str(metadata_path),
            "metadata_load_error": True,
        }
    if isinstance(payload, dict):
        payload.setdefault("metadata_path", str(metadata_path))
        return payload
    return {
        "metadata_path": str(metadata_path),
        "metadata_load_error": True,
    }


def sorted_mapping(value):
    if isinstance(value, dict):
        return {key: sorted_mapping(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [sorted_mapping(item) for item in value]
    return value


def build_save_points(target: int, stop_at: int, checkpoint_step: int) -> str:
    points = set()
    step = max(1, checkpoint_step)
    n = step
    while n < stop_at:
        points.add(n)
        n += step
    points.add(target)
    points.add(stop_at)
    return ",".join(str(n) for n in sorted(points))


def write_v2_settings(base_settings: dict[str, str], out_path: Path, target: int, stop_at: int, checkpoint_step: int) -> None:
    values = dict(base_settings)
    values["description"] = f"V2 settings targeting {target} template layers"
    values["shapeMode"] = "mixed_ellipses"
    values["stopAt"] = str(stop_at)
    values["saveAt"] = build_save_points(target, stop_at, checkpoint_step)
    values["saveEvery"] = str(max(1, checkpoint_step))
    values["previewEvery"] = str(max(1, checkpoint_step))

    ordered_keys = [
        "description",
        "detailMode",
        "maxPreviewSize",
        "maxResolution",
        "maxThreads",
        "mutatedSamples",
        "forceOpaqueShapes",
        "posterizeLevels",
        "previewEvery",
        "randomSamples",
        "saveAt",
        "saveEvery",
        "shapeMode",
        "stopAt",
    ]
    lines = []
    seen = set()
    for key in ordered_keys:
        if key in values:
            lines.append(f"{key} = {values[key]}")
            seen.add(key)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key} = {value}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resize_source_for_generation(image_path: Path, max_resolution: int) -> np.ndarray:
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    max_dim = max(w, h)
    if max_resolution > 0 and max_dim > max_resolution:
        scale = max_resolution / float(max_dim)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        img = img.resize((nw, nh), Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32)


def apply_preprocess(rgba: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return rgba

    rgb = np.clip(rgba[..., :3], 0, 255).astype(np.uint8)
    alpha = np.clip(rgba[..., 3], 0, 255).astype(np.uint8)

    if mode == "luma_bands":
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        l = lab[..., 0].astype(np.float32)
        levels = 24.0
        step = 256.0 / levels
        lq = np.floor(l / step) * step + step * 0.5
        # Keep the band separation, but blend some original luminance back in
        # so the result stays closer to the source and avoids overly harsh steps.
        l_out = lq * 0.82 + l * 0.18
        # Restore a touch of local contrast so the pass doesn't feel slightly washed.
        l_mid = 128.0
        l_out = (l_out - l_mid) * 1.06 + l_mid
        lab[..., 0] = np.clip(l_out, 0, 255).astype(np.uint8)
        rgb_out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    else:
        raise ValueError(f"unsupported preprocess mode: {mode}")

    out = np.dstack([rgb_out, alpha]).astype(np.float32)
    return out


def downscale_rgba(arr: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = arr.shape[:2]
    if max_dim <= 0 or max(h, w) <= max_dim:
        return arr
    scale = max_dim / float(max(h, w))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA")
    img = img.resize((nw, nh), Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32)


def normalize_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "shapes" not in payload:
        raise ValueError(f"{path} is not a generator geometry JSON")
    return payload


def drawable_shapes(payload: dict) -> list[dict]:
    out = []
    for shape in payload.get("shapes", [])[1:]:
        color = shape.get("color", [0, 0, 0, 0])
        if len(color) < 4 or int(color[3]) <= 0:
            continue
        out.append(shape)
    return out


def background_shape(payload: dict) -> dict:
    shapes = payload.get("shapes", [])
    if not shapes:
        raise ValueError("geometry payload has no shapes")
    return shapes[0]


def canvas_size_from_payload(payload: dict) -> tuple[int, int]:
    bg = background_shape(payload)
    data = bg.get("data", [])
    if len(data) >= 4:
        return max(1, int(data[2])), max(1, int(data[3]))
    raise ValueError("background shape is missing canvas size")


def raw_checkpoint_number(path: Path, stem: str) -> int | None:
    core = path.stem
    if not core.startswith(f"{stem}."):
        return None
    tag = core[len(stem) + 1 :]
    if not tag.isdigit():
        return None
    return int(tag)


def collect_candidate_jsons(out_dir: Path, stem: str, max_checkpoint: int | None = None) -> list[Path]:
    paths = []
    for path in out_dir.glob(f"{stem}*.json"):
        name = path.name
        if ".v2." in name or ".fh6." in name or ".report." in name or re.search(r"\.\d+v2\.json$", name) or name.endswith(".v2.json"):
            continue
        checkpoint = raw_checkpoint_number(path, stem)
        if max_checkpoint is not None and checkpoint is not None and checkpoint > max_checkpoint:
            print(
                f"Found overflow-named checkpoint {name}: checkpoint {checkpoint} > requested raw stop {max_checkpoint}; "
                "V2 will validate and cap it before writing import outputs.",
                flush=True,
            )
        paths.append(path)
    return sorted(set(paths))


def scale_shape(shape: dict, sx: float, sy: float) -> dict:
    scaled = {
        "type": int(shape.get("type", 16)),
        "color": list(shape.get("color", [0, 0, 0, 255])),
    }
    data = list(shape.get("data", []))
    if len(data) < 5:
        raise ValueError("ellipse shape missing data")
    cx, cy, rx, ry, rot = data[:5]
    scaled["data"] = [
        float(cx) * sx,
        float(cy) * sy,
        max(0.5, float(rx) * sx),
        max(0.5, float(ry) * sy),
        float(rot),
    ]
    return scaled


def ellipse_bbox(cx: float, cy: float, rx: float, ry: float, rot_deg: float, width: int, height: int) -> tuple[int, int, int, int]:
    theta = math.radians(rot_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    ex = math.sqrt((rx * rx * cos_t * cos_t) + (ry * ry * sin_t * sin_t))
    ey = math.sqrt((rx * rx * sin_t * sin_t) + (ry * ry * cos_t * cos_t))
    x0 = max(0, int(math.floor(cx - ex - 1)))
    x1 = min(width - 1, int(math.ceil(cx + ex + 1)))
    y0 = max(0, int(math.floor(cy - ey - 1)))
    y1 = min(height - 1, int(math.ceil(cy + ey + 1)))
    return x0, x1, y0, y1


def ellipse_mask(shape: dict, width: int, height: int) -> tuple[tuple[int, int, int, int], np.ndarray]:
    cx, cy, rx, ry, rot_deg = [float(v) for v in shape["data"][:5]]
    rx, ry = compensated_ellipse_size(rx, ry)
    x0, x1, y0, y1 = ellipse_bbox(cx, cy, rx, ry, rot_deg, width, height)
    xs = np.arange(x0, x1 + 1, dtype=np.float32) + 0.5
    ys = np.arange(y0, y1 + 1, dtype=np.float32) + 0.5
    xx, yy = np.meshgrid(xs, ys)
    theta = math.radians(rot_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    dx = xx - cx
    dy = yy - cy
    xr = dx * cos_t + dy * sin_t
    yr = -dx * sin_t + dy * cos_t
    mask = (xr * xr) / max(1e-6, rx * rx) + (yr * yr) / max(1e-6, ry * ry) <= 1.0
    return (x0, x1, y0, y1), mask


def compensated_ellipse_size(w: float, h: float) -> tuple[float, float]:
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


def render_and_score(background: dict, shapes: list[dict], target_rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    height, width = target_rgba.shape[:2]
    bg_rgba = np.array(list(background.get("color", [0, 0, 0, 0]))[:4], dtype=np.float32)
    top_rgb = np.empty((height, width, 3), dtype=np.float32)
    top_rgb[:] = bg_rgba[:3]
    under_rgb = np.empty((height, width, 3), dtype=np.float32)
    under_rgb[:] = bg_rgba[:3]
    top_alpha = np.full((height, width), max(0.0, min(1.0, float(bg_rgba[3]) / 255.0)), dtype=np.float32)
    under_alpha = np.full((height, width), max(0.0, min(1.0, float(bg_rgba[3]) / 255.0)), dtype=np.float32)
    top_idx = np.full((height, width), -1, dtype=np.int32)

    for idx, shape in enumerate(shapes):
        rgba = list(shape.get("color", [0, 0, 0, 255]))[:4]
        color = np.array(rgba[:3], dtype=np.float32)
        alpha = float(rgba[3]) / 255.0 if len(rgba) >= 4 else 1.0
        alpha = max(0.0, min(1.0, alpha))
        bbox, mask = ellipse_mask(shape, width, height)
        x0, x1, y0, y1 = bbox
        if x1 < x0 or y1 < y0 or not np.any(mask):
            continue
        top_sub = top_rgb[y0 : y1 + 1, x0 : x1 + 1]
        under_sub = under_rgb[y0 : y1 + 1, x0 : x1 + 1]
        top_alpha_sub = top_alpha[y0 : y1 + 1, x0 : x1 + 1]
        under_alpha_sub = under_alpha[y0 : y1 + 1, x0 : x1 + 1]
        idx_sub = top_idx[y0 : y1 + 1, x0 : x1 + 1]
        old_top = top_sub.copy()
        old_alpha = top_alpha_sub.copy()
        under_sub[mask] = old_top[mask]
        under_alpha_sub[mask] = old_alpha[mask]
        if alpha >= 1.0:
            top_sub[mask] = color
        elif alpha > 0.0:
            top_sub[mask] = old_top[mask] * (1.0 - alpha) + color * alpha
        if alpha > 0.0:
            top_alpha_sub[mask] = old_alpha[mask] + alpha * (1.0 - old_alpha[mask])
        idx_sub[mask] = idx

    target_rgb = target_rgba[..., :3].astype(np.float32)
    target_alpha = np.clip(target_rgba[..., 3].astype(np.float32) / 255.0, 0.0, 1.0)
    rgb_weight = np.maximum(target_alpha, 0.08)
    transparent_boost = np.where(target_alpha < 0.02, 3.25, np.where(target_alpha < 0.15, 2.35, 1.0)).astype(np.float32)
    rgb_top = np.square(top_rgb - target_rgb).sum(axis=2) * rgb_weight
    rgb_under = np.square(under_rgb - target_rgb).sum(axis=2) * rgb_weight
    alpha_scale = float(255.0 * 255.0 * 3.0 * 1.10)
    spill_scale = float(255.0 * 255.0 * 3.0 * 0.95)
    alpha_top = np.square(top_alpha - target_alpha) * alpha_scale
    alpha_under = np.square(under_alpha - target_alpha) * alpha_scale
    spill_top = np.square(np.maximum(0.0, top_alpha - target_alpha)) * transparent_boost * spill_scale
    spill_under = np.square(np.maximum(0.0, under_alpha - target_alpha)) * transparent_boost * spill_scale
    diff_top = rgb_top + alpha_top + spill_top
    diff_under = rgb_under + alpha_under + spill_under
    contrib_map = diff_under - diff_top
    valid = top_idx >= 0
    if np.any(valid):
        contributions = np.bincount(
            top_idx[valid].ravel(),
            weights=contrib_map[valid].ravel(),
            minlength=len(shapes),
        ).astype(np.float64)
    else:
        contributions = np.zeros(len(shapes), dtype=np.float64)
    pixel_weights = np.where(target_alpha > 0.02, 1.0, 0.35).astype(np.float32)
    total_error = float((diff_top * pixel_weights).sum())
    scored_pixels = float(pixel_weights.sum())
    return top_rgb, top_alpha, top_idx, diff_top, contributions, total_error, scored_pixels


def bbox_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax0, ax1, ay0, ay1 = a
    bx0, bx1, by0, by1 = b
    return ax0 <= bx1 and ax1 >= bx0 and ay0 <= by1 and ay1 >= by0


def render_and_score_region(
    background: dict,
    shapes: list[dict],
    target_rgba: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    x0, x1, y0, y1 = bbox
    if x1 < x0 or y1 < y0:
        return render_and_score(background, [], target_rgba[:1, :1])

    height, width = target_rgba.shape[:2]
    x0 = max(0, min(width - 1, int(x0)))
    x1 = max(0, min(width - 1, int(x1)))
    y0 = max(0, min(height - 1, int(y0)))
    y1 = max(0, min(height - 1, int(y1)))
    if x1 < x0 or y1 < y0:
        return render_and_score(background, [], target_rgba[:1, :1])

    crop_bbox = (x0, x1, y0, y1)
    crop_w = x1 - x0 + 1
    crop_h = y1 - y0 + 1
    crop_shapes = []
    for shape in shapes:
        sx, sy, rx, ry, rot = [float(v) for v in shape["data"][:5]]
        shape_bbox = ellipse_bbox(sx, sy, *compensated_ellipse_size(rx, ry), rot, width, height)
        if not bbox_intersects(shape_bbox, crop_bbox):
            continue
        shifted = copy_shape(shape)
        shifted["data"] = list(shifted["data"])
        shifted["data"][0] = float(shifted["data"][0]) - x0
        shifted["data"][1] = float(shifted["data"][1]) - y0
        crop_shapes.append(shifted)

    crop_bg = dict(background)
    crop_bg["data"] = [0, 0, crop_w, crop_h]
    return render_and_score(crop_bg, crop_shapes, target_rgba[y0 : y1 + 1, x0 : x1 + 1])


def prune_to_target(background: dict, shapes: list[dict], target_rgba: np.ndarray, target_count: int) -> tuple[list[dict], float]:
    working = list(shapes)
    if len(working) <= target_count:
        _, _, _, _, _, total_error, scored_pixels = render_and_score(background, working, target_rgba)
        return working, normalized_error(total_error, scored_pixels)

    while len(working) > target_count:
        _, _, _, _, contributions, total_error, scored_pixels = render_and_score(background, working, target_rgba)
        excess = len(working) - target_count
        order = np.argsort(contributions)
        zeroish = int(np.count_nonzero(contributions[order] <= 1e-6))
        if zeroish > 0:
            remove_count = min(excess, zeroish)
        else:
            # Overshoot checkpoints can be hundreds of shapes over the FH-safe
            # budget. Remove low-contribution shapes in larger batches so V2
            # does not spend most of its time re-rendering nearly identical
            # oversized candidates.
            remove_count = min(excess, max(1, min(160, excess // 3 if excess > 6 else 1)))
        remove_idx = set(int(i) for i in order[:remove_count])
        working = [shape for idx, shape in enumerate(working) if idx not in remove_idx]

    _, _, _, _, _, total_error, scored_pixels = render_and_score(background, working, target_rgba)
    return working, normalized_error(total_error, scored_pixels)


def normalized_error(total_error: float, scored_pixels: float) -> float:
    denom = max(1.0, scored_pixels * 4.0)
    return total_error / float(denom)


def render_import_preview(background: dict, shapes: list[dict], width: int, height: int) -> Image.Image:
    checker = np.zeros((height, width, 3), dtype=np.float32)
    bg_rgba = [int(v) for v in list(background.get("color", [0, 0, 0, 0]))[:4]]
    if len(bg_rgba) < 4:
        bg_rgba += [0] * (4 - len(bg_rgba))
    bg_r, bg_g, bg_b, bg_a = bg_rgba
    premul = np.zeros((height, width, 3), dtype=np.float32)
    alpha_canvas = np.zeros((height, width), dtype=np.float32)
    if bg_a > 0:
        base_alpha = max(0.0, min(1.0, bg_a / 255.0))
        premul[:, :] = np.array((bg_r, bg_g, bg_b), dtype=np.float32) * base_alpha
        alpha_canvas[:, :] = base_alpha
        checker[:, :] = (38, 38, 38)
    else:
        checker[:, :] = (38, 38, 38)
        tile = 32
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                if ((x // tile) + (y // tile)) % 2 == 0:
                    checker[y : y + tile, x : x + tile] = (58, 58, 58)

    for shape in shapes:
        color = [int(v) for v in list(shape.get("color", [0, 0, 0, 255]))[:4]]
        if len(color) < 4 or color[3] <= 0:
            continue
        r, g, b, a = color
        x, y, w, h, rot_deg = [float(v) for v in shape["data"][:5]]
        adj_w, adj_h = compensated_ellipse_size(w, h)
        mask = np.zeros((height, width), dtype=np.uint8)
        center = (int(round(x)), int(round(y)))
        axes = (max(1, int(round(adj_h))), max(1, int(round(adj_w))))
        cv2.ellipse(mask, center, axes, -90 + float(rot_deg), 0.0, 360.0, 255, thickness=-1)
        alpha = max(0.0, min(1.0, a / 255.0))
        if alpha <= 0.0:
            continue
        src_rgb = np.array((r, g, b), dtype=np.float32)
        shape_mask = mask > 0
        old_alpha = alpha_canvas[shape_mask]
        premul[shape_mask] = src_rgb * alpha + premul[shape_mask] * (1.0 - alpha)
        alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)

    out = premul + checker * (1.0 - alpha_canvas[..., None])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


def copy_shape(shape: dict) -> dict:
    return {
        "type": int(shape.get("type", 16)),
        "color": list(shape.get("color", [0, 0, 0, 255])),
        "data": list(shape.get("data", [])),
        "score": shape.get("score", 0),
    }


def unscale_shape(shape: dict, sx: float, sy: float) -> dict:
    x, y, rx, ry, rot = [float(v) for v in shape["data"][:5]]
    return {
        "type": int(shape.get("type", 16)),
        "color": list(shape.get("color", [0, 0, 0, 255])),
        "data": [
            int(round(x / max(sx, 1e-6))),
            int(round(y / max(sy, 1e-6))),
            max(1, int(round(rx / max(sx, 1e-6)))),
            max(1, int(round(ry / max(sy, 1e-6)))),
            int(round(rot)) % 360,
        ],
        "score": shape.get("score", 0),
    }


def local_error_value(diff_map: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    x0, x1, y0, y1 = bbox
    if x1 < x0 or y1 < y0:
        return 0.0
    sub = diff_map[y0 : y1 + 1, x0 : x1 + 1]
    if sub.size == 0:
        return 0.0
    return float(sub.mean())


def shape_homogeneity_penalty(shape: dict, target_rgba: np.ndarray) -> float:
    height, width = target_rgba.shape[:2]
    bbox, mask = ellipse_mask(shape, width, height)
    x0, x1, y0, y1 = bbox
    if x1 < x0 or y1 < y0 or not np.any(mask):
        return 0.0
    target_mask = target_rgba[..., 3] > 0.5
    sub_target_mask = target_mask[y0 : y1 + 1, x0 : x1 + 1]
    valid = mask & sub_target_mask
    if not np.any(valid):
        return 0.0
    sub_rgb = target_rgba[y0 : y1 + 1, x0 : x1 + 1, :3].astype(np.float32)
    pixels = sub_rgb[valid]
    if len(pixels) < 4:
        return 0.0
    mean = pixels.mean(axis=0)
    sq = np.square(pixels - mean).sum(axis=1)
    return float(sq.mean())


def expanded_shape_bbox(shape: dict, width: int, height: int, move_step: float, radius_step: float) -> tuple[int, int, int, int]:
    cx, cy, rx, ry, rot_deg = [float(v) for v in shape["data"][:5]]
    rx, ry = compensated_ellipse_size(rx + radius_step, ry + radius_step)
    x0, x1, y0, y1 = ellipse_bbox(cx, cy, rx + move_step, ry + move_step, rot_deg, width, height)
    margin = max(4, int(math.ceil(max(move_step, radius_step))))
    return (
        max(0, x0 - margin),
        min(width - 1, x1 + margin),
        max(0, y0 - margin),
        min(height - 1, y1 + margin),
    )


def rank_repair_targets(shapes: list[dict], top_idx: np.ndarray, diff_top: np.ndarray, top_alpha: np.ndarray, target_rgba: np.ndarray, max_shapes: int) -> list[int]:
    target_alpha = np.clip(target_rgba[..., 3].astype(np.float32) / 255.0, 0.0, 1.0)
    valid = top_idx >= 0
    if not np.any(valid):
        return []
    shape_error = np.bincount(top_idx[valid].ravel(), weights=diff_top[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    visible_pixels = np.bincount(top_idx[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    spill = np.maximum(0.0, top_alpha - target_alpha)
    spill_pixels = np.bincount(top_idx[valid].ravel(), weights=spill[valid].ravel(), minlength=len(shapes)).astype(np.float64)
    area = np.array([max(1.0, float(shape["data"][2]) * float(shape["data"][3])) for shape in shapes], dtype=np.float64)
    homogeneity = np.array([shape_homogeneity_penalty(shape, target_rgba) for shape in shapes], dtype=np.float64)
    index = np.arange(len(shapes), dtype=np.float64)
    early_weight = np.where(index < 250, 1.8 - (index / 250.0) * 0.8, 1.0)
    size_weight = np.sqrt(np.maximum(1.0, area))
    score = (
        (shape_error * 1.05)
        + (spill_pixels * size_weight * 9500.0 * early_weight)
        + (homogeneity * size_weight * early_weight)
    ) * (1.0 + np.sqrt(np.maximum(1.0, visible_pixels)) / 6.0) / np.sqrt(area)
    ranked = np.argsort(score)[::-1]
    ranked = [int(idx) for idx in ranked if (shape_error[idx] > 0 or homogeneity[idx] > 0 or spill_pixels[idx] > 0) and visible_pixels[idx] > 0]
    return ranked[:max_shapes]


def repair_shapes(background: dict, shapes: list[dict], target_rgba: np.ndarray, max_shapes: int = 8, rounds: int = 1) -> tuple[list[dict], float, dict]:
    if not shapes:
        _, _, _, _, _, total_error, scored_pixels = render_and_score(background, shapes, target_rgba)
        error = normalized_error(total_error, scored_pixels)
        return shapes, error, {"enabled": True, "touched": 0, "improvements": 0, "before": error, "after": error}

    working = [copy_shape(shape) for shape in shapes]
    render_rgb, top_alpha, top_idx, diff_top, _, total_error, scored_pixels = render_and_score(background, working, target_rgba)
    best_error = normalized_error(total_error, scored_pixels)
    before_error = best_error

    improvements = 0
    touched_indices: set[int] = set()
    for _round in range(rounds):
        ranked = rank_repair_targets(working, top_idx, diff_top, top_alpha, target_rgba, max_shapes)
        changed = False
        for idx in ranked:
            if idx >= len(working):
                continue
            touched_indices.add(idx)
            shape = working[idx]
            x, y, rx, ry, rot = [float(v) for v in shape["data"][:5]]
            move_step = max(1.0, round(max(rx, ry) * 0.014))
            radius_step = max(1.0, round(max(rx, ry) * 0.03))
            rot_step = 2.0
            local_bbox = expanded_shape_bbox(shape, target_rgba.shape[1], target_rgba.shape[0], move_step, radius_step)
            local_best_score = local_error_value(diff_top, local_bbox)
            alpha0 = float(shape.get("color", [0, 0, 0, 255])[3])
            alpha_step = max(10.0, round(alpha0 * 0.12))
            proposals = [
                (False,  move_step, 0.0, 0.0, 0.0, 0.0),
                (False, -move_step, 0.0, 0.0, 0.0, 0.0),
                (False, 0.0,  move_step, 0.0, 0.0, 0.0),
                (False, 0.0, -move_step, 0.0, 0.0, 0.0),
                (False,  move_step * 0.5, 0.0, 0.0, 0.0, 0.0),
                (False, -move_step * 0.5, 0.0, 0.0, 0.0, 0.0),
                (False, 0.0,  move_step * 0.5, 0.0, 0.0, 0.0),
                (False, 0.0, -move_step * 0.5, 0.0, 0.0, 0.0),
                (False, 0.0, 0.0, -radius_step, 0.0, 0.0),
                (False, 0.0, 0.0, 0.0, -radius_step, 0.0),
                (False, 0.0, 0.0, -radius_step, -radius_step, 0.0),
                (False, 0.0, 0.0, 0.0, 0.0,  rot_step),
                (False, 0.0, 0.0, 0.0, 0.0, -rot_step),
                (False, 0.0, 0.0, -radius_step, 0.0, rot_step),
                (False, 0.0, 0.0, 0.0, -radius_step, -rot_step),
                (False, 0.0, 0.0, -radius_step, -radius_step, 0.0, -alpha_step),
                (False, 0.0, 0.0, 0.0, 0.0, 0.0, -alpha_step),
                (False, 0.0, 0.0, 0.0, 0.0, 0.0, -alpha_step * 2.0),
                (False,  move_step * 0.5, 0.0, -radius_step, 0.0, 0.0, -alpha_step),
                (False, -move_step * 0.5, 0.0, -radius_step, 0.0, 0.0, -alpha_step),
                (False, 0.0,  move_step * 0.5, 0.0, -radius_step, 0.0, -alpha_step),
                (False, 0.0, -move_step * 0.5, 0.0, -radius_step, 0.0, -alpha_step),
            ]

            local_best = copy_shape(shape)
            original_local_score = local_best_score
            local_best_deleted = False
            for proposal in proposals:
                if len(proposal) == 6:
                    delete_shape, dx, dy, drx, dry, drot = proposal
                    dalpha = 0.0
                else:
                    delete_shape, dx, dy, drx, dry, drot, dalpha = proposal
                if delete_shape:
                    trial = None
                else:
                    trial = copy_shape(shape)
                    trial["data"] = [
                        x + dx,
                        y + dy,
                        max(1.0, rx + drx),
                        max(1.0, ry + dry),
                        (rot + drot) % 360.0,
                    ]
                    trial["color"] = list(trial.get("color", [0, 0, 0, 255]))
                    if len(trial["color"]) < 4:
                        trial["color"] += [255] * (4 - len(trial["color"]))
                    trial["color"][3] = int(max(0, min(255, round(alpha0 + dalpha))))
                prev = working[idx]
                if trial is None:
                    del working[idx]
                else:
                    working[idx] = trial
                _, _, _, trial_diff, _, _, _ = render_and_score_region(background, working, target_rgba, local_bbox)
                trial_local_score = float(trial_diff.mean()) if trial_diff.size else local_best_score
                if trial_local_score + 1e-9 < local_best_score:
                    local_best_score = trial_local_score
                    local_best = None if trial is None else copy_shape(trial)
                    local_best_deleted = trial is None
                if trial is None:
                    working.insert(idx, prev)
                else:
                    working[idx] = prev

            if local_best_score + 1e-9 < original_local_score:
                prev = working[idx]
                if local_best_deleted:
                    del working[idx]
                else:
                    working[idx] = local_best
                trial_render_rgb, trial_alpha, trial_top_idx, trial_diff, _, trial_total_error, trial_scored_pixels = render_and_score(background, working, target_rgba)
                trial_error = normalized_error(trial_total_error, trial_scored_pixels)
                if trial_error <= best_error + 1e-6 or trial_error + 1e-9 < best_error:
                    best_error = trial_error
                    render_rgb = trial_render_rgb
                    top_alpha = trial_alpha
                    top_idx = trial_top_idx
                    diff_top = trial_diff
                    improvements += 1
                    changed = True
                else:
                    if local_best_deleted:
                        working.insert(idx, prev)
                    else:
                        working[idx] = prev

        if not changed:
            break

    summary = {
        "enabled": True,
        "touched": len(touched_indices),
        "improvements": improvements,
        "before": before_error,
        "after": best_error,
    }
    return working, best_error, summary


def preview_path_for_candidate(candidate_path: Path, stem: str) -> Path:
    name = candidate_path.name
    if name == f"{stem}.json":
        return candidate_path.with_name(f"{stem}.preview.png")
    suffix = f".json"
    if not name.endswith(suffix):
        return candidate_path.with_suffix(candidate_path.suffix + ".preview.png")
    core = name[: -len(suffix)]
    if core.startswith(f"{stem}."):
        checkpoint = core[len(stem) + 1 :]
        return candidate_path.with_name(f"{stem}.preview.{checkpoint}.png")
    return candidate_path.with_name(f"{core}.preview.png")


def checkpoint_tag_for_candidate(candidate_path: Path, stem: str) -> str:
    core = candidate_path.stem
    if core == stem:
        return "final"
    if core.startswith(f"{stem}."):
        return core[len(stem) + 1 :]
    return core


def v2_json_path_for_candidate(out_dir: Path, stem: str, candidate_path: Path) -> Path:
    return v2_json_path_for_tag(out_dir, stem, checkpoint_tag_for_candidate(candidate_path, stem))


def v2_json_path_for_tag(out_dir: Path, stem: str, tag: str) -> Path:
    tag = re.sub(r"[^A-Za-z0-9_-]+", "", tag).strip() or "final"
    return out_dir / f"{stem}.{tag}v2.json"


def v2_preview_path_for_candidate(out_dir: Path, stem: str, candidate_path: Path) -> Path:
    return v2_preview_path_for_tag(out_dir, stem, checkpoint_tag_for_candidate(candidate_path, stem))


def v2_preview_path_for_tag(out_dir: Path, stem: str, tag: str) -> Path:
    tag = re.sub(r"[^A-Za-z0-9_-]+", "", tag).strip() or "final"
    return out_dir / f"{stem}.preview.{tag}v2.png"


def stem_from_image(path: Path) -> str:
    # The Go generator treats dots in the output base as extension separators.
    # A source like "Untitled_16.01.36.png" otherwise produces
    # "Untitled_16.01.5.json" instead of "...16.01.36.5.json", and V2 cannot
    # find its checkpoints. Keep the run stem extension-safe.
    return re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem).strip("_") or "image"


def run_generator(image: Path, settings_path: Path, out_dir: Path, out_stem: str, stop_file: Path | None = None) -> bool:
    out_base = out_dir / out_stem
    preview_path = out_dir / f"{out_stem}.preview.png"
    env = dict(os.environ)
    if os.name != "nt":
        env["LD_LIBRARY_PATH"] = LD_LIBRARY_PATH
    cmd = [
        str(GENERATOR_BIN),
        str(image),
        "-settings",
        str(settings_path),
        "-output",
        str(out_base),
        "-preview",
        str(preview_path),
    ]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    proc = subprocess.Popen(
        cmd,
        env=env,
        creationflags=flags,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    interrupted = False
    def _forward_output():
        try:
            if proc.stdout is None:
                return
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\r\n")
                if line:
                    print(line, flush=True)
        finally:
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

    reader = threading.Thread(target=_forward_output, daemon=True)
    reader.start()
    while proc.poll() is None:
        if stop_file is not None and stop_file.exists():
            interrupted = True
            print("Stop requested. Ending raw generation after the latest saved checkpoint...", flush=True)
            try:
                proc.terminate()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            break
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue
    reader.join(timeout=2)
    if not interrupted and proc.returncode not in (0, None):
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    return interrupted


def select_candidate(results: list[dict], tolerance: float) -> tuple[dict, dict]:
    best_accuracy = min(results, key=lambda item: item["error"])
    if tolerance <= 0:
        return best_accuracy, best_accuracy
    threshold = best_accuracy["error"] * (1.0 + max(0.0, tolerance))
    within = [item for item in results if item["error"] <= threshold]
    selected = min(within, key=lambda item: (item["final_drawables"], item["error"]))
    return best_accuracy, selected


def select_top_checkpoint_indices(records: list[dict], limit: int) -> set[int]:
    if limit <= 0 or len(records) <= limit:
        return set(range(len(records)))
    selected = {
        int(item["index"])
        for item in sorted(records, key=lambda item: (item["base_error"], item["raw_drawables"]))[:limit]
    }
    latest = max(records, key=lambda item: (item["raw_drawables"], item["candidate"]))
    selected.add(int(latest["index"]))
    return selected


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_source_copy(source_path: Path, out_dir: Path) -> Path | None:
    dest = out_dir / source_path.name
    if dest.exists():
        return dest
    try:
        shutil.copy2(source_path, dest)
        return dest
    except OSError:
        return None


def main() -> int:
    args = parse_args()
    image_path = Path(args.image).expanduser().resolve()
    settings_path = Path(args.settings).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not image_path.is_file():
        print(f"Missing image: {image_path}", file=sys.stderr)
        return 1
    if not settings_path.is_file():
        print(f"Missing settings file: {settings_path}", file=sys.stderr)
        return 1
    if not GENERATOR_BIN.is_file():
        print(f"Missing generator binary: {GENERATOR_BIN}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem_from_image(image_path)
    source_copy_path = ensure_source_copy(image_path, out_dir)
    stop_file = Path(args.stop_file).expanduser().resolve() if args.stop_file else None
    if stop_file is not None:
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        if stop_file.exists():
            try:
                stop_file.unlink()
            except OSError:
                pass

    base_settings = parse_ini(settings_path)
    run_metadata = load_run_metadata(args.run_metadata)
    target_shapes = args.target_shapes or int(base_settings.get("stopAt", "3000"))
    if target_shapes < 1:
        print("target shape count must be positive", file=sys.stderr)
        return 1

    drawable_target_shapes = max(1, target_shapes - FH6_RESERVED_BOUNDARY_LAYERS)
    overshoot_extra = min(args.overshoot_max_extra, max(0, int(math.ceil(target_shapes * max(0.0, args.overshoot_ratio - 1.0)))))
    if overshoot_extra == 0 and args.overshoot_ratio > 1.0:
        overshoot_extra = min(args.overshoot_max_extra, max(1, int(round(target_shapes * 0.08))))
    raw_stop = target_shapes + overshoot_extra

    v2_settings_path = out_dir / f"{stem}.v2.settings.ini"
    write_v2_settings(base_settings, v2_settings_path, target_shapes, raw_stop, args.checkpoint_step)

    max_resolution = int(base_settings.get("maxResolution", "0") or 0)
    source_rgba = resize_source_for_generation(image_path, max_resolution)
    processed_rgba = apply_preprocess(source_rgba, args.preprocess_mode)
    generation_image_path = image_path
    preprocess_output_path = None
    if args.preprocess_mode != "none":
        preprocess_output_path = out_dir / f"{stem}.v2.preprocess.{args.preprocess_mode}.png"
        Image.fromarray(np.clip(processed_rgba, 0, 255).astype(np.uint8), mode="RGBA").save(preprocess_output_path)
        generation_image_path = preprocess_output_path

    print(f"Generating raw V2 candidates for {image_path.name}")
    print(f"Target template layers: {target_shapes}")
    print(f"Target drawable shapes: {drawable_target_shapes} ({target_shapes} - {FH6_RESERVED_BOUNDARY_LAYERS} FH bounds layers)")
    if raw_stop > target_shapes:
        print(f"Raw generator stop:     {raw_stop} ({target_shapes} target + {overshoot_extra} overshoot)")
    else:
        print(f"Raw generator stop:     {raw_stop}")
    print(f"Using settings:         {settings_path}")
    print(f"Preprocess mode:        {args.preprocess_mode}")
    if preprocess_output_path is not None:
        print(f"Preprocessed image:     {preprocess_output_path}")
    interrupted = run_generator(generation_image_path, v2_settings_path, out_dir, stem, stop_file=stop_file)

    raw_candidates = collect_candidate_jsons(out_dir, stem, max_checkpoint=raw_stop)
    if not raw_candidates:
        print("No generator JSON outputs found after V2 run.", file=sys.stderr)
        return 1
    if interrupted:
        print("Continuing V2 finalization from interrupted checkpoints.")

    score_rgba = downscale_rgba(processed_rgba, args.score_size)

    candidate_records = []
    repair_enabled = bool(args.enable_repair and not args.disable_refine)
    for index, candidate_path in enumerate(raw_candidates):
        try:
            payload = normalize_payload(candidate_path)
            background = background_shape(payload)
            drawables = drawable_shapes(payload)
            raw_count = len(drawables)
            checkpoint_number = raw_checkpoint_number(candidate_path, stem)
            checkpoint_tag = checkpoint_tag_for_candidate(candidate_path, stem)
            if checkpoint_number is not None and checkpoint_number > raw_stop:
                if checkpoint_number == raw_stop + 1 and raw_count <= raw_stop:
                    checkpoint_tag = str(raw_stop)
                    print(
                        f"Normalizing checkpoint name {candidate_path.name} to {checkpoint_tag} "
                        f"because it contains {raw_count} drawable layers.",
                        flush=True,
                    )
                else:
                    print(
                        f"Checkpoint {candidate_path.name} is above requested raw stop {raw_stop}; "
                        "V2 will cap the import output.",
                        flush=True,
                    )

            full_w, full_h = canvas_size_from_payload(payload)
            score_h, score_w = score_rgba.shape[:2]
            sx = score_w / float(max(1, full_w))
            sy = score_h / float(max(1, full_h))

            scaled_bg = dict(background)
            bg_color = list(background.get("color", [0, 0, 0, 0]))
            scaled_bg["color"] = bg_color

            if raw_count > raw_stop:
                print(
                    f"Checkpoint {candidate_path.name} has {raw_count} drawable layers, above raw stop {raw_stop}; "
                    "V2 will cap it before import output.",
                    flush=True,
                )

            scaled_drawables = [scale_shape(shape, sx, sy) for shape in drawables]
            should_prune = args.enable_prune or raw_count > drawable_target_shapes
            if should_prune:
                kept_scaled, error = prune_to_target(scaled_bg, scaled_drawables, score_rgba, drawable_target_shapes)
                kept_indices = []
                scaled_map = {id(shape): idx for idx, shape in enumerate(scaled_drawables)}
                for kept_shape in kept_scaled:
                    kept_indices.append(scaled_map[id(kept_shape)])
                kept_original = [drawables[idx] for idx in kept_indices]
                final_count = len(kept_original)
            else:
                _, _, _, _, _, total_error, scored_pixels = render_and_score(scaled_bg, scaled_drawables, score_rgba)
                error = normalized_error(total_error, scored_pixels)
                kept_original = list(drawables)
                final_count = len(kept_original)
        except Exception as exc:
            print(
                f"Skipping candidate {candidate_path.name}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            continue
        candidate_records.append(
            {
                "index": index,
                "candidate_path": candidate_path,
                "candidate": candidate_path.name,
                "background": background,
                "drawables": drawables,
                "raw_drawables": raw_count,
                "base_drawables": final_count,
                "base_shapes": kept_original,
                "base_error": error,
                "canvas_size": [full_w, full_h],
                "scale": [sx, sy],
                "checkpoint_tag": checkpoint_tag,
            }
        )
    if not candidate_records:
        print("No usable generator JSON checkpoints remained after V2 validation.", file=sys.stderr)
        return 1

    repair_indices = select_top_checkpoint_indices(candidate_records, args.repair_candidate_limit) if repair_enabled else set()
    preview_indices = select_top_checkpoint_indices(candidate_records, args.preview_candidate_limit)
    if repair_enabled:
        skipped = len(candidate_records) - len(repair_indices)
        if skipped > 0:
            print(
                f"Smart repair: repairing {len(repair_indices)}/{len(candidate_records)} checkpoints "
                f"(best scored + latest), skipping {skipped} lower-ranked checkpoints.",
                flush=True,
            )
        else:
            print(f"Smart repair: repairing all {len(candidate_records)} checkpoints.", flush=True)
    skipped_previews = len(candidate_records) - len(preview_indices)
    if skipped_previews > 0:
        print(
            f"Smart previews: rendering {len(preview_indices)}/{len(candidate_records)} preview PNGs; "
            "other JSONs preview on demand in the browser.",
            flush=True,
        )

    results = []
    for record in candidate_records:
        candidate_path = record["candidate_path"]
        background = record["background"]
        raw_count = record["raw_drawables"]
        full_w, full_h = record["canvas_size"]
        sx, sy = record["scale"]
        refinement = {
            "enabled": False,
            "touched": 0,
            "improvements": 0,
            "before": record["base_error"],
            "after": record["base_error"],
        }
        final_shapes = list(record["base_shapes"])
        final_error = record["base_error"]
        repair_applied = repair_enabled and int(record["index"]) in repair_indices
        if repair_applied:
            try:
                scaled_bg = dict(background)
                scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
                scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
                refined_scaled, refined_error, refinement = repair_shapes(scaled_bg, scaled_selected, score_rgba)
                final_shapes = [unscale_shape(shape, sx, sy) for shape in refined_scaled]
                final_error = refined_error
            except Exception as exc:
                refinement = dict(refinement)
                refinement.update({
                    "enabled": True,
                    "failed": True,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                print(
                    f"Targeted repair failed for {candidate_path.name}: {type(exc).__name__}: {exc}. "
                    "Using the pruned base candidate.",
                    file=sys.stderr,
                    flush=True,
                )
        if len(final_shapes) > drawable_target_shapes:
            try:
                scaled_bg = dict(background)
                scaled_bg["color"] = list(background.get("color", [0, 0, 0, 0]))
                scaled_selected = [scale_shape(shape, sx, sy) for shape in final_shapes]
                capped_scaled, capped_error = prune_to_target(scaled_bg, scaled_selected, score_rgba, drawable_target_shapes)
                final_shapes = [unscale_shape(shape, sx, sy) for shape in capped_scaled]
                final_error = capped_error
            except Exception as exc:
                final_shapes = final_shapes[:drawable_target_shapes]
                final_error = record["base_error"]
                refinement = dict(refinement)
                refinement["hard_cap_failed"] = f"{type(exc).__name__}: {exc}"
            refinement = dict(refinement)
            refinement["after_hard_cap"] = final_error
        checkpoint_tag = record["checkpoint_tag"]
        final_json_path = v2_json_path_for_tag(out_dir, stem, checkpoint_tag)
        final_preview_path = v2_preview_path_for_tag(out_dir, stem, checkpoint_tag)
        final_payload = {"shapes": [background] + final_shapes}
        save_json(final_json_path, final_payload)
        preview_written = int(record["index"]) in preview_indices
        if preview_written:
            preview = render_import_preview(background, final_shapes, full_w, full_h)
            preview.save(final_preview_path)
        results.append(
            {
                "candidate": candidate_path.name,
                "candidate_path": str(candidate_path),
                "raw_drawables": raw_count,
                "final_drawables": len(final_shapes),
                "error": final_error,
                "base_error": record["base_error"],
                "background": background,
                "kept_shapes": final_shapes,
                "canvas_size": [full_w, full_h],
                "scale": [sx, sy],
                "refinement": refinement,
                "repair_applied": repair_applied,
                "v2_json": str(final_json_path),
                "v2_preview": str(final_preview_path),
                "preview_written": preview_written,
                "checkpoint_tag": checkpoint_tag,
            }
        )
        repair_label = "repaired" if repair_applied else ("repair skipped" if repair_enabled else "repair off")
        preview_label = "preview" if preview_written else "on-demand preview"
        print(
            f"Candidate {candidate_path.name}: raw={raw_count} final={len(final_shapes)} "
            f"error={final_error:.6f} ({repair_label}, {preview_label})"
        )

    best_accuracy = min(results, key=lambda item: item["error"])
    latest_checkpoint = max(results, key=lambda item: (item["raw_drawables"], item["candidate"]))

    report_path = out_dir / f"{stem}.v2.report.json"
    preset = run_metadata.get("selected_profile") or {
        "path": str(settings_path),
        "values": dict(base_settings),
    }
    base_preset = run_metadata.get("base_profile")
    ui_overrides = run_metadata.get("ui_overrides", {})
    effective_settings = run_metadata.get("effective_settings", dict(base_settings))
    run_toggles = run_metadata.get("toggles", {
        "luma_bands": args.preprocess_mode == "luma_bands",
        "quality_overshoot": overshoot_extra > 0,
        "targeted_repair": repair_enabled,
    })
    generator_command_options = run_metadata.get("generator_command_options", {
        "target_shapes": str(target_shapes),
        "checkpoint_step": str(args.checkpoint_step),
        "preprocess_mode": args.preprocess_mode,
        "overshoot_ratio": str(args.overshoot_ratio),
        "overshoot_max_extra": str(args.overshoot_max_extra),
        "repair_enabled": repair_enabled,
    })

    def report_candidate(item: dict) -> dict:
        return {
            "checkpoint_tag": item["checkpoint_tag"],
            "candidate": item["candidate"],
            "raw_drawables": item["raw_drawables"],
            "final_drawables": item["final_drawables"],
            "error": item["error"],
            "base_error": item["base_error"],
            "repair_applied": item["repair_applied"],
            "preview_written": item["preview_written"],
            "v2_json": item["v2_json"],
            "v2_preview": item["v2_preview"],
            "refinement": sorted_mapping(item["refinement"]),
        }

    candidates_by_checkpoint = [
        report_candidate(item)
        for item in sorted(results, key=lambda item: (item["raw_drawables"], item["candidate"]))
    ]
    candidates_by_accuracy = [
        report_candidate(item)
        for item in sorted(results, key=lambda item: (item["error"], item["final_drawables"], item["raw_drawables"]))
    ]

    report = {
        "source_image": str(image_path),
        "source_copy": str(source_copy_path) if source_copy_path is not None else None,
        "settings": {
            "preset": sorted_mapping(preset),
            "base_preset": sorted_mapping(base_preset),
            "ui_overrides": sorted_mapping(ui_overrides),
            "effective_settings": sorted_mapping(effective_settings),
            "toggles": sorted_mapping(run_toggles),
            "command_options": sorted_mapping(generator_command_options),
            "settings_path": str(settings_path),
            "v2_settings_path": str(v2_settings_path),
            "run_metadata": sorted_mapping(run_metadata),
        },
        "preprocess": {
            "mode": args.preprocess_mode,
            "output": str(preprocess_output_path) if preprocess_output_path is not None else None,
        },
        "preprocess_mode": args.preprocess_mode,
        "preprocess_output": str(preprocess_output_path) if preprocess_output_path is not None else None,
        "base_settings": str(settings_path),
        "v2_settings": str(v2_settings_path),
        "target_shapes": target_shapes,
        "drawable_target_shapes": drawable_target_shapes,
        "raw_stop": raw_stop,
        "overshoot_extra": overshoot_extra,
        "interrupted": interrupted,
        "score_size": args.score_size,
        "efficiency_tolerance": args.efficiency_tolerance,
        "prune_enabled": args.enable_prune,
        "refine_enabled": repair_enabled,
        "repair_candidate_limit": args.repair_candidate_limit,
        "preview_candidate_limit": args.preview_candidate_limit,
        "best_accuracy": {
            "candidate": best_accuracy["candidate"],
            "checkpoint_tag": best_accuracy["checkpoint_tag"],
            "raw_drawables": best_accuracy["raw_drawables"],
            "final_drawables": best_accuracy["final_drawables"],
            "error": best_accuracy["error"],
            "base_error": best_accuracy["base_error"],
            "repair_applied": best_accuracy["repair_applied"],
            "v2_json": best_accuracy["v2_json"],
            "v2_preview": best_accuracy["v2_preview"],
            "preview_written": best_accuracy["preview_written"],
        },
        "latest_checkpoint_v2": {
            "candidate": latest_checkpoint["candidate"],
            "checkpoint_tag": latest_checkpoint["checkpoint_tag"],
            "raw_drawables": latest_checkpoint["raw_drawables"],
            "final_drawables": latest_checkpoint["final_drawables"],
            "error": latest_checkpoint["error"],
            "base_error": latest_checkpoint["base_error"],
            "repair_applied": latest_checkpoint["repair_applied"],
            "v2_json": latest_checkpoint["v2_json"],
            "v2_preview": latest_checkpoint["v2_preview"],
            "preview_written": latest_checkpoint["preview_written"],
        },
        "candidates": candidates_by_checkpoint,
        "candidates_by_accuracy": candidates_by_accuracy,
    }
    save_json(report_path, report)

    print()
    print(f"Best accuracy: {best_accuracy['candidate']} -> {best_accuracy['final_drawables']} shapes, error {best_accuracy['error']:.6f}")
    print(f"Latest checkpoint V2: {latest_checkpoint['candidate']} -> {latest_checkpoint['final_drawables']} shapes, error {latest_checkpoint['error']:.6f}")
    for item in sorted(results, key=lambda entry: (entry["raw_drawables"], entry["candidate"])):
        print(f"V2 JSON:        {item['v2_json']}")
        print(f"V2 preview:     {item['v2_preview']}")
    print(f"Report:         {report_path}")
    if interrupted:
        print("Stopped early by request. Every usable checkpoint was finalized, including the latest saved checkpoint.")
    else:
        print("V2 outputs written for every usable checkpoint. Pick the one you want in the JSON browser.")

    if not args.keep_temp_settings:
        try:
            v2_settings_path.unlink()
        except OSError:
            pass
    if stop_file is not None and stop_file.exists():
        try:
            stop_file.unlink()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
