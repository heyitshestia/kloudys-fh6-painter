#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "forza_generator_v2.py"
BENCH_ROOT = ROOT / "runtime" / "benchmarks"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    shape_mode: str
    luma: bool
    force_opaque: bool
    posterize: int
    detail_mode: str
    detail_weighting: bool
    prefilter_keep_ratio: float
    prefilter_min_keep: int
    score_size_base: int
    mr_factor: float
    mr_min: int
    mr_max: int
    anchors: dict[int, tuple[int, int, int]]


@dataclass(frozen=True)
class Tier:
    key: str
    label: str
    random_factor: float
    mutation_factor: float
    mr_factor: float
    score_factor: float
    prefilter_factor: float


STYLES: dict[str, Style] = {
    "flat": Style(
        key="flat",
        label="Flat Colors / Logos",
        shape_mode="mixed_edge_bias",
        luma=True,
        force_opaque=True,
        posterize=64,
        detail_mode="normal",
        detail_weighting=True,
        prefilter_keep_ratio=0.22,
        prefilter_min_keep=4096,
        score_size_base=720,
        mr_factor=0.85,
        mr_min=900,
        mr_max=1700,
        anchors={
            500: (1000, 280000, 12000),
            1000: (1200, 380000, 16000),
            2000: (1400, 520000, 22000),
            3000: (1600, 650000, 28000),
        },
    ),
    "shaded": Style(
        key="shaded",
        label="Shaded Character Art",
        shape_mode="mixed_smart_detail",
        luma=False,
        force_opaque=True,
        posterize=96,
        detail_mode="normal",
        detail_weighting=True,
        prefilter_keep_ratio=0.25,
        prefilter_min_keep=4096,
        score_size_base=960,
        mr_factor=1.05,
        mr_min=1100,
        mr_max=2300,
        anchors={
            500: (1200, 320000, 14000),
            1000: (1500, 430000, 20000),
            2000: (1800, 560000, 26000),
            3000: (2100, 720000, 34000),
        },
    ),
    "gradient": Style(
        key="gradient",
        label="Smooth Gradients",
        shape_mode="mixed_soft_detail",
        luma=False,
        force_opaque=False,
        posterize=128,
        detail_mode="normal",
        detail_weighting=True,
        prefilter_keep_ratio=0.28,
        prefilter_min_keep=4096,
        score_size_base=1100,
        mr_factor=1.20,
        mr_min=1300,
        mr_max=2700,
        anchors={
            500: (1400, 380000, 18000),
            1000: (1800, 520000, 24000),
            2500: (2200, 680000, 32000),
            3000: (2500, 860000, 42000),
        },
    ),
}


TIERS: dict[str, Tier] = {
    "fast": Tier("fast", "Fast", 0.52, 0.58, 0.88, 0.82, 0.70),
    "balanced": Tier("balanced", "Balanced", 0.76, 0.82, 0.96, 0.94, 0.86),
    "high": Tier("high", "High", 1.00, 1.00, 1.00, 1.00, 1.00),
    "extreme": Tier("extreme", "Extreme", 1.35, 1.28, 1.12, 1.12, 1.15),
}


CSV_FIELDS = [
    "run_id",
    "status",
    "image",
    "image_profile",
    "style",
    "tier",
    "target_layers",
    "maxResolution",
    "randomSamples",
    "mutatedSamples",
    "score_size",
    "shapeMode",
    "detailMode",
    "v2PreprocessMode",
    "forceOpaqueShapes",
    "posterizeLevels",
    "prefilterKeepRatio",
    "prefilterMinKeep",
    "runtime_sec",
    "returncode",
    "best_error",
    "best_raw_drawables",
    "best_final_drawables",
    "best_json",
    "best_preview",
    "latest_error",
    "latest_final_drawables",
    "repair_applied",
    "covered_removed",
    "source_width",
    "source_height",
    "alpha_coverage",
    "edge_density",
    "luma_std",
    "white_fraction",
    "run_dir",
    "settings_file",
    "log_file",
]


def parse_csv_list(value: str, valid: set[str] | None = None) -> list[str]:
    out = []
    for part in re.split(r"[,;\s]+", value.strip()):
        if not part:
            continue
        key = part.strip().lower()
        if valid is not None and key not in valid:
            raise SystemExit(f"Unknown value {part!r}. Valid: {', '.join(sorted(valid))}")
        out.append(key)
    return out


def parse_layers(value: str) -> list[int]:
    layers = []
    for part in re.split(r"[,;\s]+", value.strip()):
        if not part:
            continue
        try:
            layer = int(part)
        except ValueError as exc:
            raise SystemExit(f"Invalid layer count: {part}") from exc
        if layer < 1:
            raise SystemExit("Layer counts must be positive.")
        layers.append(layer)
    return sorted(set(layers))


def round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def interpolate_anchor(anchors: dict[int, tuple[int, int, int]], layer: int) -> tuple[int, int, int]:
    points = sorted(anchors)
    if layer <= points[0]:
        return anchors[points[0]]
    if layer >= points[-1]:
        return anchors[points[-1]]
    lower = points[0]
    upper = points[-1]
    for idx in range(len(points) - 1):
        if points[idx] <= layer <= points[idx + 1]:
            lower = points[idx]
            upper = points[idx + 1]
            break
    t = (layer - lower) / float(upper - lower)
    lv = anchors[lower]
    uv = anchors[upper]
    return tuple(int(round(lv[i] + (uv[i] - lv[i]) * t)) for i in range(3))  # type: ignore[return-value]


def calculated_settings(style: Style, tier: Tier, layers: int, smoke: bool = False) -> dict[str, str]:
    anchor_mr, anchor_random, anchor_mutated = interpolate_anchor(style.anchors, layers)
    formula_mr = (650.0 + 24.0 * math.sqrt(float(layers))) * style.mr_factor
    max_resolution = int(round((anchor_mr * 0.72 + formula_mr * 0.28) * tier.mr_factor))
    max_resolution = clamp_int(round_to(max_resolution, 50), style.mr_min, style.mr_max)

    random_samples = round_to(anchor_random * tier.random_factor, 1000)
    mutated_samples = round_to(anchor_mutated * tier.mutation_factor, 500)
    score_size = int(round(style.score_size_base * tier.score_factor))
    score_size = clamp_int(round_to(score_size, 32), 512, 1280)
    prefilter_keep = max(512, int(round(style.prefilter_min_keep * tier.prefilter_factor)))
    prefilter_ratio = max(0.08, min(0.45, style.prefilter_keep_ratio * tier.prefilter_factor))

    if smoke:
        max_resolution = min(max_resolution, 500)
        random_samples = min(random_samples, 2500)
        mutated_samples = min(mutated_samples, 512)
        score_size = min(score_size, 320)
        prefilter_keep = min(prefilter_keep, 512)

    return {
        "description": f"Benchmark {style.label} / {tier.label} / {layers} layers",
        "maxPreviewSize": "500",
        "maxResolution": str(max_resolution),
        "maxThreads": "0",
        "mutatedSamples": str(mutated_samples),
        "forceOpaqueShapes": "true" if style.force_opaque else "false",
        "posterizeLevels": str(style.posterize),
        "previewEvery": "50",
        "randomSamples": str(random_samples),
        "saveAt": str(layers),
        "saveEvery": str(max(50, min(250, layers))),
        "shapeMode": style.shape_mode,
        "stopAt": str(layers),
        "useWorkGroupEval": "true",
        "fastPrefilter": "true",
        "prefilterScale": "4",
        "prefilterKeepRatio": f"{prefilter_ratio:.4f}",
        "prefilterMinKeep": str(prefilter_keep),
        "detailMode": style.detail_mode,
        "detailWeighting": "true" if style.detail_weighting else "false",
        "v2PreprocessMode": "luma_bands" if style.luma else "none",
        "v2EnableRepair": "true",
        "_scoreSize": str(score_size),
    }


def apply_scales(
    values: dict[str, str],
    *,
    sample_scale: float = 1.0,
    mutation_scale: float = 1.0,
    resolution_scale: float = 1.0,
    score_size_scale: float = 1.0,
) -> dict[str, str]:
    out = dict(values)
    if sample_scale <= 0 or mutation_scale <= 0 or resolution_scale <= 0 or score_size_scale <= 0:
        raise SystemExit("Scale values must be positive.")
    out["randomSamples"] = str(max(1, round_to(float(out["randomSamples"]) * sample_scale, 1000)))
    out["mutatedSamples"] = str(max(0, round_to(float(out["mutatedSamples"]) * mutation_scale, 500)))
    out["maxResolution"] = str(max(64, round_to(float(out["maxResolution"]) * resolution_scale, 50)))
    out["_scoreSize"] = str(max(64, round_to(float(out["_scoreSize"]) * score_size_scale, 32)))
    return out


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("._-") or "item"


def image_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


def discover_images(paths: list[str]) -> list[Path]:
    images: list[Path] = []
    for item in paths:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if candidate.suffix.lower() in IMAGE_EXTS and candidate.is_file():
                    images.append(candidate)
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            images.append(path)
    seen = set()
    out = []
    for image in images:
        key = str(image.resolve())
        if key not in seen:
            seen.add(key)
            out.append(image)
    return out


def profile_image(path: Path) -> dict[str, float | int | str]:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    px = list(img.getdata())
    total = max(1, len(px))
    visible = [p for p in px if p[3] > 16]
    visible_count = max(1, len(visible))
    alpha_coverage = len(visible) / float(total)
    lumas = [0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in visible]
    mean_luma = sum(lumas) / float(visible_count)
    luma_std = math.sqrt(sum((v - mean_luma) ** 2 for v in lumas) / float(visible_count))
    white_fraction = sum(1 for v in lumas if v > 232.0) / float(visible_count)

    # Fast edge estimate on a small grayscale copy.
    small = img.resize((min(256, w), max(1, round(h * min(256, w) / max(1, w)))), Image.Resampling.BICUBIC)
    gray = small.convert("L")
    gp = gray.load()
    sw, sh = gray.size
    edge_hits = 0
    samples = max(1, (sw - 1) * (sh - 1))
    for y in range(sh - 1):
        for x in range(sw - 1):
            if abs(int(gp[x + 1, y]) - int(gp[x, y])) + abs(int(gp[x, y + 1]) - int(gp[x, y])) > 42:
                edge_hits += 1
    edge_density = edge_hits / float(samples)

    if alpha_coverage < 0.25 and white_fraction > 0.40:
        profile = "sparse_line_art"
    elif edge_density > 0.22 and luma_std > 52:
        profile = "flat_logo_like"
    elif edge_density < 0.16 and luma_std < 62:
        profile = "soft_gradient_like"
    else:
        profile = "shaded_or_general"

    return {
        "source_width": w,
        "source_height": h,
        "alpha_coverage": round(alpha_coverage, 5),
        "edge_density": round(edge_density, 5),
        "luma_std": round(luma_std, 5),
        "white_fraction": round(white_fraction, 5),
        "image_profile": profile,
    }


def write_ini(path: Path, values: dict[str, str]) -> None:
    ordered = [
        "description",
        "detailMode",
        "detailWeighting",
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
        "useWorkGroupEval",
        "fastPrefilter",
        "prefilterScale",
        "prefilterKeepRatio",
        "prefilterMinKeep",
        "v2PreprocessMode",
        "v2EnableRepair",
    ]
    lines = []
    seen = set()
    for key in ordered:
        if key in values:
            lines.append(f"{key} = {values[key]}")
            seen.add(key)
    for key in sorted(values):
        if key not in seen and not key.startswith("_"):
            lines.append(f"{key} = {values[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = CSV_FIELDS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_one(image: Path, style: Style, tier: Tier, layers: int, values: dict[str, str], bench_dir: Path, timeout_minutes: float) -> dict:
    img_profile = profile_image(image)
    run_id = f"{safe_name(image.stem)}_{image_hash(image)}_{style.key}_{tier.key}_{layers}"
    run_dir = bench_dir / "runs" / run_id
    settings_dir = bench_dir / "settings"
    logs_dir = bench_dir / "logs"
    settings_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / f"{run_id}.ini"
    log_file = logs_dir / f"{run_id}.log"
    write_ini(settings_file, values)

    cmd = [
        sys.executable,
        "-u",
        str(GENERATOR),
        str(image),
        "--settings",
        str(settings_file),
        "--out-dir",
        str(run_dir),
        "--target-shapes",
        str(layers),
        "--checkpoint-step",
        str(layers),
        "--live-preview-every",
        "50",
        "--score-size",
        values["_scoreSize"],
        "--preprocess-mode",
        values["v2PreprocessMode"],
        "--enable-repair",
    ]

    started = time.perf_counter()
    status = "ok"
    returncode = -999
    try:
        with log_file.open("w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=max(1, int(timeout_minutes * 60)),
            )
        returncode = int(proc.returncode)
        if returncode != 0:
            status = "failed"
    except subprocess.TimeoutExpired:
        status = "timeout"
    runtime_sec = round(time.perf_counter() - started, 3)

    row = {
        "run_id": run_id,
        "status": status,
        "image": str(image),
        "style": style.key,
        "tier": tier.key,
        "target_layers": layers,
        "maxResolution": values["maxResolution"],
        "randomSamples": values["randomSamples"],
        "mutatedSamples": values["mutatedSamples"],
        "score_size": values["_scoreSize"],
        "shapeMode": values["shapeMode"],
        "detailMode": values["detailMode"],
        "v2PreprocessMode": values["v2PreprocessMode"],
        "forceOpaqueShapes": values["forceOpaqueShapes"],
        "posterizeLevels": values["posterizeLevels"],
        "prefilterKeepRatio": values["prefilterKeepRatio"],
        "prefilterMinKeep": values["prefilterMinKeep"],
        "runtime_sec": runtime_sec,
        "returncode": returncode,
        "run_dir": str(run_dir),
        "settings_file": str(settings_file),
        "log_file": str(log_file),
        **img_profile,
    }

    reports = sorted((run_dir / "reports").glob("*.v2.report.json"))
    if reports:
        try:
            report = json.loads(reports[-1].read_text(encoding="utf-8"))
            best = report.get("best_accuracy") or {}
            latest = report.get("latest_checkpoint_v2") or {}
            row.update(
                {
                    "best_error": best.get("error", ""),
                    "best_raw_drawables": best.get("raw_drawables", ""),
                    "best_final_drawables": best.get("final_drawables", ""),
                    "best_json": best.get("v2_json", ""),
                    "best_preview": best.get("v2_preview", ""),
                    "latest_error": latest.get("error", ""),
                    "latest_final_drawables": latest.get("final_drawables", ""),
                    "repair_applied": best.get("repair_applied", ""),
                }
            )
            covered_removed = 0
            for candidate in report.get("candidates_by_accuracy") or []:
                if candidate.get("candidate") == best.get("candidate"):
                    cleanup = (((candidate.get("refinement") or {}).get("covered_layer_cleanup")) or {})
                    covered_removed = cleanup.get("removed", 0)
                    break
            row["covered_removed"] = covered_removed
        except Exception as exc:
            row["status"] = "report_parse_failed"
            row["best_error"] = f"{type(exc).__name__}: {exc}"
    return row


def numeric(row: dict, key: str, default: float = math.inf) -> float:
    try:
        value = row.get(key, "")
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def rank_results(bench_dir: Path) -> None:
    rows = [row for row in read_csv(bench_dir / "benchmark_runs.csv") if row.get("status") == "ok" and row.get("best_error")]
    if not rows:
        return
    max_runtime = max(1.0, max(numeric(row, "runtime_sec", 0.0) for row in rows))
    max_layers = max(1.0, max(numeric(row, "target_layers", 0.0) for row in rows))
    for row in rows:
        err = numeric(row, "best_error")
        runtime = numeric(row, "runtime_sec", 0.0)
        layers = numeric(row, "target_layers", 0.0)
        row["balanced_rank_score"] = f"{err * (1.0 + 0.055 * runtime / max_runtime + 0.025 * layers / max_layers):.8f}"

    def best_for(group_key):
        grouped: dict[tuple, list[dict]] = {}
        for row in rows:
            key = tuple(row[item] for item in group_key)
            grouped.setdefault(key, []).append(row)
        best_rows = []
        for key_rows in grouped.values():
            best_rows.append(min(key_rows, key=lambda item: (numeric(item, "balanced_rank_score"), numeric(item, "best_error"))))
        return sorted(best_rows, key=lambda item: tuple(item[k] for k in group_key) + (numeric(item, "balanced_rank_score"),))

    ranked = sorted(rows, key=lambda item: (numeric(item, "balanced_rank_score"), numeric(item, "best_error")))
    fields = CSV_FIELDS + ["balanced_rank_score"]
    write_csv(bench_dir / "best_overall.csv", ranked[:50], fields)
    write_csv(bench_dir / "best_by_image.csv", best_for(["image"]), fields)
    write_csv(bench_dir / "best_by_style_layer.csv", best_for(["style", "target_layers"]), fields)
    write_csv(bench_dir / "best_by_image_style.csv", best_for(["image", "style"]), fields)
    write_json_summary(bench_dir, ranked)
    make_contact_sheet(bench_dir, ranked[:24], "best_overall_contact_sheet.jpg")


def write_json_summary(bench_dir: Path, ranked: list[dict]) -> None:
    summary = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "bench_dir": str(bench_dir),
        "best_overall": ranked[0] if ranked else None,
        "top_10": ranked[:10],
        "notes": [
            "balanced_rank_score = final error with small runtime/layer penalties",
            "Use visual contact sheets before changing shipped presets.",
            "Do not overfit to one image; look for repeated winners across styles.",
        ],
    }
    (bench_dir / "best_settings_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def make_contact_sheet(bench_dir: Path, rows: list[dict], filename: str) -> None:
    previews = []
    for row in rows:
        preview = Path(row.get("best_preview") or "")
        if preview.is_file():
            previews.append((row, preview))
    if not previews:
        return

    thumb_w, thumb_h = 260, 190
    label_h = 76
    cols = 4
    rows_count = math.ceil(len(previews) / cols)
    sheet = Image.new("RGB", (cols * thumb_w, rows_count * (thumb_h + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for idx, (row, preview) in enumerate(previews):
        col = idx % cols
        yrow = idx // cols
        x = col * thumb_w
        y = yrow * (thumb_h + label_h)
        try:
            img = Image.open(preview).convert("RGBA")
            img.thumbnail((thumb_w - 12, thumb_h - 12), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (thumb_w - 12, thumb_h - 12), (235, 235, 235))
            bg.paste(img, ((bg.width - img.width) // 2, (bg.height - img.height) // 2), img)
            sheet.paste(bg, (x + 6, y + 6))
        except Exception:
            pass
        label = (
            f"{row.get('style')} / {row.get('tier')} / {row.get('target_layers')}\n"
            f"err {row.get('best_error')} | {row.get('runtime_sec')}s\n"
            f"MR {row.get('maxResolution')} RS {row.get('randomSamples')}"
        )
        draw.multiline_text((x + 8, y + thumb_h + 4), label, fill=(0, 0, 0), font=font, spacing=2)
    sheet.save(bench_dir / filename, quality=92)


def make_smoke_images(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    images = []

    logo = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.rectangle((28, 34, 212, 86), fill=(20, 30, 200, 255))
    d.rectangle((52, 48, 188, 72), fill=(255, 255, 255, 255))
    d.ellipse((170, 26, 218, 74), fill=(255, 40, 40, 255))
    path = out_dir / "smoke_flat_logo.png"
    logo.save(path)
    images.append(path)

    gradient = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
    gp = gradient.load()
    for y in range(180):
        for x in range(180):
            dx = x - 90
            dy = y - 90
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= 76:
                t = dist / 76.0
                gp[x, y] = (int(255 * (1 - t) + 60 * t), int(140 * (1 - t) + 40 * t), int(220 * (1 - t) + 130 * t), 255)
    path = out_dir / "smoke_gradient_orb.png"
    gradient.save(path)
    images.append(path)

    return images


def build_plan(
    images: list[Path],
    styles: list[str],
    tiers: list[str],
    layers: list[int],
    smoke: bool,
    max_runs: int,
    sample_scale: float,
    mutation_scale: float,
    resolution_scale: float,
    score_size_scale: float,
) -> list[dict]:
    planned = []
    for image in images:
        for style_key in styles:
            for tier_key in tiers:
                for layer in layers:
                    style = STYLES[style_key]
                    tier = TIERS[tier_key]
                    values = apply_scales(
                        calculated_settings(style, tier, layer, smoke=smoke),
                        sample_scale=sample_scale,
                        mutation_scale=mutation_scale,
                        resolution_scale=resolution_scale,
                        score_size_scale=score_size_scale,
                    )
                    planned.append({
                        "image": str(image),
                        "style": style_key,
                        "tier": tier_key,
                        "target_layers": layer,
                        "maxResolution": values["maxResolution"],
                        "randomSamples": values["randomSamples"],
                        "mutatedSamples": values["mutatedSamples"],
                        "score_size": values["_scoreSize"],
                        "v2PreprocessMode": values["v2PreprocessMode"],
                        "shapeMode": values["shapeMode"],
                    })
                    if max_runs and len(planned) >= max_runs:
                        return planned
    return planned


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Kloudy's FH6 generator style/speed/layer settings.")
    parser.add_argument("--images", nargs="*", default=[], help="Image files or folders. Defaults to sibling Images then local Images if present.")
    parser.add_argument("--styles", default="flat,shaded,gradient", help="Comma list: flat, shaded, gradient")
    parser.add_argument("--tiers", default="fast,balanced,high,extreme", help="Comma list: fast, balanced, high, extreme")
    parser.add_argument("--layers", default="500,1000,2000,3000", help="Comma list of target layer counts")
    parser.add_argument("--profile", choices=("smoke", "quick", "full", "exhaustive"), default="full")
    parser.add_argument("--max-runs", type=int, default=0, help="Stop after N planned runs. Useful for spot checks.")
    parser.add_argument("--timeout-minutes", type=float, default=45.0, help="Per-run timeout.")
    parser.add_argument("--plan-only", action="store_true", help="Write planned_runs.csv and exit without generation.")
    parser.add_argument("--make-smoke-images", action="store_true", help="Create small synthetic smoke-test images.")
    parser.add_argument("--bench-dir", default="", help="Existing/new benchmark output folder. Defaults to runtime/benchmarks/<timestamp>.")
    parser.add_argument("--resume", action="store_true", help="Skip run IDs already present in benchmark_runs.csv.")
    parser.add_argument("--sample-scale", type=float, default=1.0, help="Multiply randomSamples. Default: 1.0")
    parser.add_argument("--mutation-scale", type=float, default=1.0, help="Multiply mutatedSamples. Default: 1.0")
    parser.add_argument("--resolution-scale", type=float, default=1.0, help="Multiply maxResolution. Default: 1.0")
    parser.add_argument("--score-size-scale", type=float, default=1.0, help="Multiply V2 score size. Default: 1.0")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not GENERATOR.is_file():
        print(f"Missing generator wrapper: {GENERATOR}", file=sys.stderr)
        return 1

    if args.profile == "smoke":
        args.make_smoke_images = True
        args.layers = "24"
        args.styles = "flat,gradient"
        args.tiers = "fast"
        args.timeout_minutes = min(args.timeout_minutes, 8.0)
    elif args.profile == "quick":
        args.layers = "500,1000"
        args.tiers = "fast,balanced"
    elif args.profile == "exhaustive":
        args.layers = "250,500,1000,1500,2000,2500,3000"
        args.tiers = "fast,balanced,high,extreme"

    bench_dir = Path(args.bench_dir).expanduser() if args.bench_dir else BENCH_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    if not bench_dir.is_absolute():
        bench_dir = (ROOT / bench_dir).resolve()
    bench_dir.mkdir(parents=True, exist_ok=True)

    image_paths = list(args.images)
    if args.make_smoke_images:
        image_paths.extend(str(path) for path in make_smoke_images(bench_dir / "smoke-images"))
    if not image_paths:
        for candidate in (ROOT.parent / "Images", ROOT / "Images"):
            if candidate.exists():
                image_paths.append(str(candidate))
                break

    images = discover_images(image_paths)
    if not images:
        print("No images found. Pass --images <folder> or use --make-smoke-images.", file=sys.stderr)
        return 1

    styles = parse_csv_list(args.styles, set(STYLES))
    tiers = parse_csv_list(args.tiers, set(TIERS))
    layers = parse_layers(args.layers)
    plan = build_plan(
        images,
        styles,
        tiers,
        layers,
        smoke=(args.profile == "smoke"),
        max_runs=max(0, args.max_runs),
        sample_scale=args.sample_scale,
        mutation_scale=args.mutation_scale,
        resolution_scale=args.resolution_scale,
        score_size_scale=args.score_size_scale,
    )
    write_csv(
        bench_dir / "planned_runs.csv",
        plan,
        ["image", "style", "tier", "target_layers", "maxResolution", "randomSamples", "mutatedSamples", "score_size", "v2PreprocessMode", "shapeMode"],
    )
    print(f"Benchmark folder: {bench_dir}")
    print(f"Images: {len(images)}")
    print(f"Planned runs: {len(plan)}")
    if args.plan_only:
        print(f"Plan written: {bench_dir / 'planned_runs.csv'}")
        return 0

    done = set()
    runs_csv = bench_dir / "benchmark_runs.csv"
    if args.resume:
        done = {row.get("run_id") for row in read_csv(runs_csv) if row.get("run_id")}

    for index, item in enumerate(plan, start=1):
        image = Path(item["image"])
        style = STYLES[str(item["style"])]
        tier = TIERS[str(item["tier"])]
        layers_value = int(item["target_layers"])
        values = apply_scales(
            calculated_settings(style, tier, layers_value, smoke=(args.profile == "smoke")),
            sample_scale=args.sample_scale,
            mutation_scale=args.mutation_scale,
            resolution_scale=args.resolution_scale,
            score_size_scale=args.score_size_scale,
        )
        run_id = f"{safe_name(image.stem)}_{image_hash(image)}_{style.key}_{tier.key}_{layers_value}"
        if run_id in done:
            print(f"[{index}/{len(plan)}] skip existing {run_id}")
            continue
        print(f"[{index}/{len(plan)}] {image.name} | {style.key} | {tier.key} | {layers_value} layers")
        row = run_one(image, style, tier, layers_value, values, bench_dir, args.timeout_minutes)
        append_csv(runs_csv, [row])
        rank_results(bench_dir)
        print(f"  status={row.get('status')} error={row.get('best_error', '')} time={row.get('runtime_sec')}s")

    rank_results(bench_dir)
    print(f"Results: {runs_csv}")
    print(f"Best overall: {bench_dir / 'best_overall.csv'}")
    print(f"Contact sheet: {bench_dir / 'best_overall_contact_sheet.jpg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
