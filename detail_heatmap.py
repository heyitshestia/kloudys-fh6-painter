from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def load_rgba(path: Path | str) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"), dtype=np.float32)


def normalize_map(values: np.ndarray, visible: np.ndarray | None = None) -> np.ndarray:
    data = np.nan_to_num(values.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if visible is not None and np.any(visible):
        sample = data[visible]
    else:
        sample = data.reshape(-1)
    high = float(np.percentile(sample, 97.5)) if sample.size else 1.0
    if high <= 1e-6:
        return np.zeros_like(data, dtype=np.float32)
    return np.clip(data / high, 0.0, 1.0).astype(np.float32)


def build_detail_heatmap(rgba: np.ndarray) -> np.ndarray:
    """Return a 0..1 map of likely detail-critical pixels.

    The map intentionally uses deterministic image cues instead of a model:
    hard alpha cuts, local contrast, RGB boundaries, linework, highlights, and
    saturated edges. It is fast enough for previews and stable enough to make
    generator A/B tests meaningful.
    """
    if rgba.ndim != 3 or rgba.shape[2] < 4:
        raise ValueError("detail heatmap expects an RGBA image")
    height, width = rgba.shape[:2]
    if height <= 0 or width <= 0:
        return np.zeros((max(1, height), max(1, width)), dtype=np.float32)

    rgb = np.clip(rgba[..., :3], 0, 255).astype(np.float32)
    alpha = np.clip(rgba[..., 3] / 255.0, 0.0, 1.0).astype(np.float32)
    visible = alpha > 0.04
    luma = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0
    maxc = rgb.max(axis=2) / 255.0
    minc = rgb.min(axis=2) / 255.0
    saturation = np.clip(maxc - minc, 0.0, 1.0)

    blur_luma = cv2.GaussianBlur(luma, (0, 0), 1.0)
    gx = cv2.Sobel(blur_luma, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur_luma, cv2.CV_32F, 0, 1, ksize=3)
    luma_edge = normalize_map(np.sqrt(gx * gx + gy * gy), visible)

    color_edges = []
    for channel in range(3):
        channel_data = cv2.GaussianBlur(rgb[..., channel] / 255.0, (0, 0), 0.85)
        cgx = cv2.Sobel(channel_data, cv2.CV_32F, 1, 0, ksize=3)
        cgy = cv2.Sobel(channel_data, cv2.CV_32F, 0, 1, ksize=3)
        color_edges.append(cgx * cgx + cgy * cgy)
    color_edge = normalize_map(np.sqrt(np.maximum.reduce(color_edges)), visible)

    agx = cv2.Sobel(alpha, cv2.CV_32F, 1, 0, ksize=3)
    agy = cv2.Sobel(alpha, cv2.CV_32F, 0, 1, ksize=3)
    alpha_edge = normalize_map(np.sqrt(agx * agx + agy * agy), alpha > 0.0)

    local_mean = cv2.GaussianBlur(luma, (0, 0), 3.0)
    local_contrast = normalize_map(np.abs(luma - local_mean), visible)
    linework = np.clip((0.62 - luma) / 0.62, 0.0, 1.0) * np.maximum(luma_edge, color_edge) * alpha
    highlights = np.clip((luma - 0.78) / 0.22, 0.0, 1.0) * np.maximum(luma_edge, color_edge) * alpha

    heat = (
        luma_edge * 0.28
        + color_edge * 0.24
        + alpha_edge * 0.20
        + local_contrast * 0.16
        + linework * 0.18
        + highlights * 0.10
        + saturation * np.maximum(luma_edge, color_edge) * 0.14
    )
    heat *= np.where(visible, 1.0, 0.15).astype(np.float32)

    # Expand single-pixel features just enough that scoring/pruning protects
    # nearby shapes. Too much dilation makes broad fields look noisy.
    kernel = np.ones((3, 3), np.uint8)
    heat = cv2.dilate(heat.astype(np.float32), kernel, iterations=1)
    heat = cv2.GaussianBlur(heat, (0, 0), 0.8)
    return normalize_map(heat, visible)


def heatmap_to_rgba(mask: np.ndarray, source_rgba: np.ndarray | None = None) -> np.ndarray:
    heat = np.clip(mask.astype(np.float32), 0.0, 1.0)
    height, width = heat.shape[:2]
    blue = np.clip((1.0 - heat) * 150.0, 0, 255)
    red = np.clip(heat * 255.0, 0, 255)
    green = np.clip(np.minimum(heat, 1.0 - heat) * 300.0, 0, 255)
    alpha = np.full((height, width), 255.0, dtype=np.float32)
    if source_rgba is not None and source_rgba.ndim == 3 and source_rgba.shape[:2] == heat.shape:
        src_alpha = np.clip(source_rgba[..., 3], 0, 255).astype(np.float32)
        alpha = np.where(src_alpha > 8, 255.0, 80.0)
    return np.dstack([red, green, blue, alpha]).astype(np.uint8)


def apply_detail_guidance(rgba: np.ndarray, mask: np.ndarray, strength: float = 0.32) -> np.ndarray:
    """Make detail-critical regions slightly more attractive to the raw solver."""
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return rgba.copy()
    rgb = np.clip(rgba[..., :3], 0, 255).astype(np.float32)
    alpha = np.clip(rgba[..., 3], 0, 255).astype(np.float32)
    heat = np.clip(mask.astype(np.float32), 0.0, 1.0)[..., None]

    blur = cv2.GaussianBlur(rgb, (0, 0), 1.15)
    sharp = np.clip(rgb + (rgb - blur) * (0.85 * strength), 0, 255)
    gray = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114)[..., None]
    color_boost = np.clip(gray + (rgb - gray) * (1.0 + 0.18 * strength), 0, 255)
    guided = rgb * (1.0 - heat * strength) + ((sharp * 0.72) + (color_boost * 0.28)) * (heat * strength)
    return np.dstack([np.clip(guided, 0, 255), alpha]).astype(np.float32)


def detail_heatmap_preview_bytes(path: Path | str) -> bytes:
    rgba = load_rgba(path)
    heat = build_detail_heatmap(rgba)
    preview = heatmap_to_rgba(heat, rgba)
    out = BytesIO()
    Image.fromarray(preview, mode="RGBA").save(out, format="PNG")
    return out.getvalue()
