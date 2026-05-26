from __future__ import annotations

import argparse
import base64
import contextlib
import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import psutil
except Exception as exc:  # pragma: no cover - handled by GUI startup
    psutil = None
    _PSUTIL_ERROR = exc
else:
    _PSUTIL_ERROR = None

from game_profiles import PROFILES
from generator_backend import (
    GENERATOR_EXE,
    GENERATED_ROOT,
    best_geometry_jsons,
    build_generator_command,
    delete_user_preset,
    generation_report_path,
    generator_stop_request_path,
    geometry_shape_count,
    import_drawable_budget,
    is_import_safe_geometry_json,
    is_internal_generator_json,
    load_settings,
    next_generator_output_dir,
    save_user_preset,
    write_custom_settings,
)
from geometry_json import ELLIPSE, RECTANGLE, ROTATED_ELLIPSE, ROTATED_RECTANGLE, load_normalized_geometry
from version_info import get_version


ROOT = Path(__file__).resolve().parent
REPO_OWNER = "heyitshestia"
REPO_NAME = "kloudys-fh6-painter"
BRANCH = "main"
GITHUB_VERSION_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/VERSION?ref={BRANCH}"
GITHUB_COMMIT_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}"
EMBEDDED_PYTHON = ROOT / "python" / "python.exe"
PROBE_DIR = ROOT / "webui-data" / "probes"
APP_SETTINGS_PATH = ROOT / "runtime" / "app_settings.json"
SESSION_PATH = PROBE_DIR / "current-fh6-session.json"
PREVIEW_MAX = 1200
MEMORY_SNAPSHOT_LIMIT_MB = 2048
UNIVERSAL_IMPORT_ROOT = ROOT / "runtime" / "universal-import"
PROJECT_PRESENCE_ASSET = ROOT / "assets" / "app" / "project-integrity.marker"
LUMA_BANDS_ROOT = ROOT / "imgs" / "luma-bands"
STANDALONE_APP_FOLDER_NAME = "KloudysFH6Painter"
USER_IMAGES_ROOT = ROOT.parent / "Images" if ROOT.name.lower() == STANDALONE_APP_FOLDER_NAME.lower() else ROOT / "Images"
THEMES = {
    "Pastel Bloom": "pastel",
    "Sakura Glass": "sakura",
    "Blackout": "blackout",
}
DEFAULT_THEME = "Blackout"


def configure_combo_box(combo: QComboBox, *, max_visible: int = 16, min_height: int = 34, editable: bool = False) -> QComboBox:
    combo.setEditable(editable)
    combo.setMinimumHeight(min_height)
    combo.setMaxVisibleItems(max_visible)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(18)
    return combo


def helper_python() -> Path | str:
    return EMBEDDED_PYTHON if EMBEDDED_PYTHON.exists() else sys.executable


def handmade_shape_count(path: Path) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    shapes = payload.get("shapes")
    if not isinstance(shapes, list):
        raise ValueError("Handmade JSON must contain a shapes list.")
    return len(shapes)


TEXT = {
    "tutorial": """Kloudy's FH6 Painter tutorial

1. First-time setup

Use the launcher if possible. On first use, press the setup buttons from left to right:

Setup Python
- Makes sure 64-bit Python 3.12 is available.
- Standalone releases include bundled Python, but this button is still the safe first check.

Install Dependencies
- Installs/checks PySide6, Pillow, NumPy, OpenCV, psutil, and import helper packages.
- Run this before opening the app for real work.

Update
- If the launcher says an update is available, click Update before first use.
- Close the app before updating.

Launch App
- Opens the painter app after setup is green.

Manual fallback files:
00_launcher.bat
01_add_python312_to_path.bat
02_install_dependencies.bat
05_check_environment.bat


2. Pick a style preset

Current stock presets are style-based:

Flat Colors / Logos
- Best for logos, decals, mascot art, hard borders, and clean color regions.
- Uses edge-biased shapes and Luma Prep by default.

Shaded Character Art
- Best default for anime, faces, eyes, hair, skin, and mixed linework.
- Uses character-art weighting and leaves Luma Prep off to protect tiny detail.

Smooth Gradients
- Best for glossy shading and dark-to-light gradients.
- Keeps Luma Prep off and uses softer detail weighting.

The vroom vroom scrrrrt zoooom! switch doubles random samples and mutated samples.
It does not double output layers or resolution.


3. Generate Final Vinyl

Open Generate Final Vinyl, choose one image, pick a preset, then click Generate Final Vinyl.

Luma Prep is optional:
- It makes a luma-banded prep image before building.
- It can help logos, stickers, and flat color art.
- Leave it off for soft gradients, hair, faces, eyes, and maximum tiny detail.

Edge Repair is normally on:
- It runs during finalization.
- It tries to clean borders, transparent holes, finger gaps, hair gaps, and cutout edges.


4. Important: generation is not done when the raw builder finishes

The app has two phases:

Phase 1: internal build
- The patched GPU builder creates raw checkpoints.
- The preview may update while layers are being built.
- These raw checkpoints are not the normal import target.

Phase 2: Finalize Checkpoints
- The app scores checkpoints.
- It caps outputs to safe layer counts.
- It applies Edge Repair if enabled.
- It writes final import-ready JSONs and previews.

Do not close the app until the log says:

FINALIZE CHECKPOINTS COMPLETE

Final files appear under:

imgs/generated/<job>/finals


5. Understand the output folders

finals
- Import-ready JSON files.
- Use these in normal import.

checkpoints
- Internal raw builder checkpoints.
- Useful for diagnostics, not normal import.

previews
- Preview PNGs for raw and finalized outputs.

reports
- Settings, toggles, scores, candidates, and run metadata.


6. Prepare FH6 before importing

In Forza Horizon 6:

1. Open Vinyl Group Editor.
2. Load or create a simple-layer template.
3. Ungroup the template.
4. Stay in the Vinyl Group Editor.
5. Do not switch menus after preparing the template.
6. Remember the exact template layer count shown by FH6.

Default import uses the full template for art layers.
Finalize Checkpoints keeps transparent-source shapes inside the PNG canvas, so normal imports do not need FH border masks.
Legacy 4-mask import is available in Settings only if you need to test old behavior.
That means normal usable art layers are:

template layers

Examples:

500 template layers = 500 usable art layers
1000 template layers = 1000 usable art layers
2000 template layers = 2000 usable art layers
3000 template layers = 3000 usable art layers


7. Import Final JSON

Open Import Final JSON.

1. Pick the generated vinyl run.
2. Pick the finalized checkpoint you want.
3. Check the preview.
4. Enter the exact FH6 template layer count.
5. Click Auto-locate FH6 template if needed.
6. Click Import Final JSON into FH6.

The highlighted finalized checkpoint is the one that imports.
The best safe final is listed first, but you can pick a different finalized checkpoint yourself.


8. If import does nothing or errors

Check these first:

- FH6 is running.
- You are inside Vinyl Group Editor, not applying a vinyl to the car.
- The template is ungrouped.
- The layer count is exact.
- The selected JSON fits inside the template layer count.
- The app may need to run as administrator.

If generation looks bad, try the preset that matches the source style, increase random samples, increase layers, or use a cleaner source image.
""",
}


def ensure_dirs() -> None:
    for path in (ROOT / "runtime", ROOT / "runtime" / "previews", ROOT / "runtime" / "custom-settings", ROOT / "runtime" / "user-presets", PROBE_DIR, LUMA_BANDS_ROOT, USER_IMAGES_ROOT, UNIVERSAL_IMPORT_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def load_app_settings() -> dict:
    try:
        data = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_app_settings(settings: dict) -> None:
    try:
        APP_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        APP_SETTINGS_PATH.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def local_app_version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def local_app_revision() -> str | None:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            creationflags=flags,
            check=False,
        )
        revision = result.stdout.strip()
        if result.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{7,40}", revision):
            return revision.lower()
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        revision = (ROOT / "BUILD_COMMIT").read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", revision):
            return revision.lower()
    except OSError:
        pass
    return None


def remote_app_version() -> str:
    request = urllib.request.Request(
        GITHUB_VERSION_API,
        headers={
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "User-Agent": "KloudysFH6Painter",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    content = str(payload.get("content", ""))
    return base64.b64decode(content).decode("utf-8", errors="replace").strip()


def remote_main_revision() -> str | None:
    request = urllib.request.Request(
        GITHUB_COMMIT_API,
        headers={
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "User-Agent": "KloudysFH6Painter",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    revision = str(payload.get("sha", "")).strip()
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", revision):
        return revision.lower()
    return None


def version_tuple(value: str) -> tuple[int, ...] | None:
    parts = re.findall(r"\d+", str(value or ""))
    if not parts:
        return None
    return tuple(int(part) for part in parts)


def compare_versions(local_value: str, remote_value: str) -> int:
    local_parts = version_tuple(local_value)
    remote_parts = version_tuple(remote_value)
    if local_parts is None or remote_parts is None:
        return 0 if str(local_value).strip() == str(remote_value).strip() else -1
    width = max(len(local_parts), len(remote_parts))
    local_parts = local_parts + (0,) * (width - len(local_parts))
    remote_parts = remote_parts + (0,) * (width - len(remote_parts))
    if remote_parts > local_parts:
        return -1
    if remote_parts < local_parts:
        return 1
    return 0


def main_revision_has_bugfix(local_revision: str | None, remote_revision: str | None) -> bool:
    if not local_revision or not remote_revision:
        return False
    return not remote_revision.startswith(local_revision) and not local_revision.startswith(remote_revision)


def require_project_presence() -> None:
    # Remove this function call and constant to disable the launch presence check.
    if not PROJECT_PRESENCE_ASSET.is_file():
        raise RuntimeError("Required project files are missing. Launch from the full Kloudy's FH6 Painter folder.")


def show_startup_dependency_error(exc: BaseException) -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    QMessageBox.critical(
        None,
        "Dependencies missing",
        "Kloudy's FH6 Painter cannot start because a required dependency is missing.\n\n"
        f"{type(exc).__name__}: {exc}\n\n"
        "Close this message, then run:\n"
        "01_add_python312_to_path.bat\n"
        "02_install_dependencies.bat",
    )


@contextlib.contextmanager
def suppress_native_stderr():
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = os.dup(2)
        os.dup2(devnull, 2)
    except OSError:
        yield
        return
    try:
        yield
    finally:
        try:
            os.dup2(stderr_fd, 2)
        finally:
            os.close(stderr_fd)
            os.close(devnull)


_CV2_CACHE = None
_CV2_ERROR = None


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


def read_stable_file_bytes(path: Path, checks: int = 2, delay: float = 0.035) -> bytes | None:
    previous_size = None
    for attempt in range(max(1, checks)):
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if size <= 0:
            return None
        if previous_size == size or attempt == checks - 1:
            try:
                data = path.read_bytes()
            except OSError:
                return None
            return data if len(data) == size else None
        previous_size = size
        time.sleep(delay)
    return None


def decode_image_bytes(data: bytes, flags=None):
    loaded = load_cv2()
    if not loaded or not data:
        return None
    cv2, np = loaded
    arr = np.frombuffer(data, dtype=np.uint8)
    if flags is None:
        flags = cv2.IMREAD_COLOR
    with suppress_native_stderr():
        return cv2.imdecode(arr, flags)


def decode_image_file(path: Path):
    data = read_stable_file_bytes(Path(path))
    return decode_image_bytes(data) if data else None


def resize_keep_aspect(image, max_size: int = PREVIEW_MAX):
    loaded = load_cv2()
    if not loaded:
        return image
    cv2, _np = loaded
    height, width = image.shape[:2]
    scale = min(max_size / max(width, height), 1.0)
    if scale < 1.0:
        image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return image


def image_to_png_bytes(image) -> bytes | None:
    loaded = load_cv2()
    if not loaded:
        return None
    cv2, _np = loaded
    image = resize_keep_aspect(image)
    ok, encoded = cv2.imencode(".png", image)
    return encoded.tobytes() if ok else None


def render_source_image(path: Path) -> bytes | None:
    image = decode_image_file(Path(path))
    return image_to_png_bytes(image) if image is not None else None


def apply_luma_bands_image(image):
    loaded = load_cv2()
    if not loaded or image is None:
        return None
    cv2, np = loaded
    if image.ndim == 2:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        alpha = np.full(image.shape[:2], 255, dtype=np.uint8)
    elif image.ndim != 3:
        return None
    elif image.shape[2] == 4:
        bgr = image[..., :3]
        alpha = image[..., 3]
    elif image.shape[2] == 3:
        bgr = image
        alpha = np.full(image.shape[:2], 255, dtype=np.uint8)
    else:
        return None

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l = lab[..., 0].astype(np.float32)
    levels = 64.0
    step = 256.0 / levels
    lq = np.floor(l / step) * step + step * 0.5

    # Adaptive banding keeps flat anime regions easy for the generator while
    # preserving soft gradients and avoiding chunky halos around detailed edges.
    blur = cv2.GaussianBlur(l, (0, 0), 1.1)
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    edge = np.sqrt(gx * gx + gy * gy)
    edge = np.clip((edge - 3.0) / 18.0, 0.0, 1.0)
    band_weight = 0.16 + edge * 0.34
    l_out = lq * band_weight + l * (1.0 - band_weight)
    l_out = (l_out - 128.0) * 1.005 + 128.0
    lab[..., 0] = np.clip(l_out, 0, 255).astype(np.uint8)
    rgb_out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    bgr_out = cv2.cvtColor(rgb_out, cv2.COLOR_RGB2BGR)
    return np.dstack([bgr_out, alpha]).astype(np.uint8)


def build_luma_bands_file(source: Path, output_dir: Path = LUMA_BANDS_ROOT) -> Path:
    loaded = load_cv2()
    if not loaded:
        raise RuntimeError("Preview dependencies are missing. Run 02_install_dependencies.bat.")
    cv2, _np = loaded
    data = read_stable_file_bytes(source)
    if not data:
        raise RuntimeError(f"Could not read image: {source}")
    image = decode_image_bytes(data, flags=cv2.IMREAD_UNCHANGED)
    processed = apply_luma_bands_image(image)
    if processed is None:
        raise RuntimeError(f"Could not process image: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem).strip("._") or "image"
    candidate = output_dir / f"{safe_stem}.luma-bands.png"
    index = 2
    while candidate.exists():
        candidate = output_dir / f"{safe_stem}.luma-bands-v{index}.png"
        index += 1
    ok = cv2.imwrite(str(candidate), processed)
    if not ok:
        raise RuntimeError(f"Could not save luma-band image: {candidate}")
    return candidate


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
        return max(1.0, w * uniform_scale * major_axis_scale), max(1.0, h * uniform_scale)
    return max(1.0, w * uniform_scale), max(1.0, h * uniform_scale * major_axis_scale)


def load_preview_geometry(path: Path) -> dict:
    try:
        return load_normalized_geometry(path)
    except Exception:
        pass

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    source = payload.get("source") if isinstance(payload, dict) else {}
    shapes_in = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes_in, list) or not shapes_in:
        raise ValueError("JSON does not contain previewable shapes.")

    drawables = []
    max_x = 1.0
    max_y = 1.0
    for item in shapes_in:
        if not isinstance(item, dict):
            continue
        data = list(item.get("data") or [])
        color = list(item.get("color") or [])
        if len(data) < 4 or len(color) < 4:
            continue
        try:
            x, y, w, h = [float(v) for v in data[:4]]
            rot = float(data[4]) if len(data) >= 5 else 0.0
            rgba = [max(0, min(255, int(round(float(v))))) for v in color[:4]]
        except (TypeError, ValueError):
            continue
        if rgba[3] <= 0:
            continue
        type_code = int(item.get("type", ROTATED_ELLIPSE))
        word = int(item.get("type_word", type_code & 0xFFFF))
        shape_type = ROTATED_ELLIPSE
        out_data = [round(x), round(y), max(1, round(w)), max(1, round(h)), round(rot) % 360]
        if word == 0x65:  # FH primitive square
            shape_type = ROTATED_RECTANGLE
            out_data = [round(x), round(y), max(1, round(w)), max(1, round(h)), round(rot) % 360]
        elif word in (0x66, 0x88):  # circle / ellipse
            shape_type = ROTATED_ELLIPSE
        drawables.append({"type": shape_type, "data": out_data, "color": rgba, "score": item.get("score", 0)})
        max_x = max(max_x, x + abs(w) + 64)
        max_y = max(max_y, y + abs(h) + 64)

    if not drawables:
        raise ValueError("JSON does not contain visible previewable layers.")
    src_size = source.get("canvas_size") or source.get("size") if isinstance(source, dict) else None
    if isinstance(src_size, list) and len(src_size) >= 2:
        width, height = int(src_size[0]), int(src_size[1])
    else:
        width, height = max(1, int(math.ceil(max_x))), max(1, int(math.ceil(max_y)))
    background = {"type": RECTANGLE, "data": [0, 0, width, height], "color": [0, 0, 0, 0], "score": 0}
    return {"shapes": [background] + drawables}


def render_geometry_json(path: Path, max_size: int = PREVIEW_MAX) -> bytes | None:
    loaded = load_cv2()
    if not loaded:
        return None
    cv2, np = loaded
    try:
        data = load_preview_geometry(path)
        shapes = data["shapes"]
        image_w, image_h = [int(v) for v in shapes[0]["data"][2:]]
        scale = min(1.0, float(max_size) / float(max(1, image_w, image_h)))
        render_w = max(1, int(round(image_w * scale)))
        render_h = max(1, int(round(image_h * scale)))
        bg_r, bg_g, bg_b, bg_a = [int(v) for v in shapes[0]["color"]]
        checker = np.zeros((render_h, render_w, 3), np.float32)
        premul = np.zeros((render_h, render_w, 3), np.float32)
        alpha_canvas = np.zeros((render_h, render_w), np.float32)
        if bg_a > 0:
            base_alpha = max(0.0, min(1.0, float(bg_a) / 255.0))
            premul[:, :] = np.array((bg_b, bg_g, bg_r), dtype=np.float32) * base_alpha
            alpha_canvas[:, :] = base_alpha
            checker[:, :] = (38, 38, 38)
        else:
            checker[:, :] = (38, 38, 38)
            tile = 32
            for y in range(0, image_h, tile):
                for x in range(0, image_w, tile):
                    if ((x // tile) + (y // tile)) % 2 == 0:
                        checker[y:y + tile, x:x + tile] = (58, 58, 58)
        for shape in shapes[1:]:
            color = [int(v) for v in shape.get("color", [])]
            if len(color) == 4 and color[3] <= 0:
                continue
            if len(color) != 4:
                continue
            r, g, b, a = color
            alpha = max(0.0, min(1.0, float(a) / 255.0))
            if alpha <= 0:
                continue
            shape_type = int(shape.get("type", 0))
            mask = np.zeros((render_h, render_w), np.uint8)
            if shape_type in (ELLIPSE, ROTATED_ELLIPSE):
                x, y, w, h, rot_deg = shape["data"]
                if shape_type == ELLIPSE:
                    rot_deg = 0
                adj_w, adj_h = compensated_ellipse_size(w, h)
                axes = (max(1, int(round(adj_h * scale))), max(1, int(round(adj_w * scale))))
                cv2.ellipse(mask, (int(round(x * scale)), int(round(y * scale))), axes, -90 + float(rot_deg), 0.0, 360.0, 255, thickness=-1)
            elif shape_type in (RECTANGLE, ROTATED_RECTANGLE):
                if shape_type == ROTATED_RECTANGLE:
                    x, y, w, h, rot_deg = shape["data"]
                    rect = ((float(x) * scale, float(y) * scale), (max(1.0, float(w) * scale), max(1.0, float(h) * scale)), float(rot_deg))
                    cv2.fillConvexPoly(mask, cv2.boxPoints(rect).astype(np.int32), 255)
                else:
                    x, y, w, h = shape["data"]
                    cv2.rectangle(
                        mask,
                        (int(round((x - w / 2) * scale)), int(round((y - h / 2) * scale))),
                        (int(round((x + w / 2) * scale)), int(round((y + h / 2) * scale))),
                        255,
                        thickness=-1,
                    )
            else:
                continue
            shape_mask = mask > 0
            src = np.array((b, g, r), dtype=np.float32)
            old_alpha = alpha_canvas[shape_mask]
            premul[shape_mask] = src * alpha + premul[shape_mask] * (1.0 - alpha)
            alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)
        preview = premul + checker * (1.0 - alpha_canvas[..., None])
        loaded = load_cv2()
        if not loaded:
            return None
        cv2, _np = loaded
        ok, encoded = cv2.imencode(".png", np.clip(preview, 0, 255).astype(np.uint8))
        return encoded.tobytes() if ok else None
    except Exception:
        return None


def game_processes():
    if psutil is None:
        return []
    names = {name.lower(): key for key, profile in PROFILES.items() for name in profile.process_names}
    found = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info.get("name") or ""
            key = names.get(name.lower())
            if key:
                found.append({"pid": proc.info["pid"], "name": name, "profile": key, "label": f"{name} pid {proc.info['pid']}"})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def parse_hex_or_empty(value: str | None) -> str | None:
    value = str(value or "").strip()
    return value or None


def load_session_location():
    if not SESSION_PATH.exists():
        return None
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def session_pid_is_live(session, game):
    if psutil is None:
        return False
    try:
        pid = int(session.get("pid", -1))
        proc = psutil.Process(pid)
        profile = PROFILES.get(game)
        return bool(profile and proc.name().lower() in [name.lower() for name in profile.process_names])
    except (psutil.Error, TypeError, ValueError):
        return False


class UiBus(QObject):
    log = Signal(str)
    status = Signal(str)
    progress = Signal(str)
    phase = Signal(str, str)
    update_alert = Signal(str, str)
    preview_bytes = Signal(bytes)
    preview_file = Signal(str)
    json_preview = Signal(int, object)
    export_json_preview = Signal(int, object)
    refresh_lists = Signal()
    generated_changed = Signal()
    auto_located = Signal(str, str, str, str, str)
    ui_call = Signal(object)


class PreviewView(QGraphicsView):
    def __init__(self, empty_text: str):
        super().__init__()
        self.empty_text = empty_text
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHints(self.renderHints())
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.clear()

    def clear(self, text: str | None = None):
        self.scene.clear()
        label = self.scene.addText(text or self.empty_text)
        label.setDefaultTextColor(Qt.GlobalColor.white)
        self.pixmap_item = None

    def set_bytes(self, data: bytes | None):
        if not data:
            self.clear("Preview unavailable. Run 02_install_dependencies.bat if this persists.")
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.clear("Preview unavailable.")
            return
        self._set_pixmap(pixmap)

    def set_file(self, path: Path | str):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            data = render_source_image(Path(path))
            self.set_bytes(data)
            return
        self._set_pixmap(pixmap)

    def _set_pixmap(self, pixmap: QPixmap):
        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.resetTransform()
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        if self.pixmap_item is None:
            return super().wheelEvent(event)
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        if self.pixmap_item is not None:
            self.resetTransform()
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        super().mouseDoubleClickEvent(event)


class AnimatedThemeBackground(QWidget):
    def __init__(self):
        super().__init__()
        self.theme_key = THEMES[DEFAULT_THEME]
        self.petals = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_petals)
        rng = random.Random(1337)
        for _index in range(34):
            self.petals.append(
                {
                    "x": rng.uniform(-0.25, 1.05),
                    "y": rng.uniform(0.02, 0.96),
                    "size": rng.uniform(8.0, 18.0),
                    "speed": rng.uniform(0.0017, 0.0042),
                    "drift": rng.uniform(0.7, 2.4),
                    "phase": rng.uniform(0.0, math.tau),
                    "spin": rng.uniform(-2.8, 2.8),
                    "angle": rng.uniform(0.0, 360.0),
                    "alpha": rng.uniform(0.34, 0.68),
                }
            )

    def set_theme(self, theme_key: str):
        self.theme_key = theme_key
        if theme_key == "sakura":
            if not self.timer.isActive():
                self.timer.start(33)
        else:
            self.timer.stop()
        self.update()

    def advance_petals(self):
        for petal in self.petals:
            petal["phase"] += 0.045 * petal["drift"]
            petal["angle"] += petal["spin"]
            petal["x"] += petal["speed"]
            petal["y"] += math.sin(petal["phase"]) * 0.0009
            if petal["x"] > 1.12:
                petal["x"] = random.uniform(-0.22, -0.04)
                petal["y"] = random.uniform(0.04, 0.95)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if self.theme_key == "sakura":
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.00, QColor("#fff6f9"))
            gradient.setColorAt(0.42, QColor("#f8e0eb"))
            gradient.setColorAt(1.00, QColor("#e9f4ff"))
            painter.fillRect(rect, gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 82))
            painter.drawEllipse(QRectF(rect.width() * 0.64, -rect.height() * 0.18, rect.width() * 0.52, rect.height() * 0.52))
            painter.setBrush(QColor(255, 205, 222, 62))
            painter.drawEllipse(QRectF(-rect.width() * 0.20, rect.height() * 0.46, rect.width() * 0.58, rect.height() * 0.58))
            self.paint_petals(painter)
        elif self.theme_key == "blackout":
            painter.fillRect(rect, QColor("#000000"))
        else:
            painter.fillRect(rect, QColor("#f5edff"))

    def paint_petals(self, painter: QPainter):
        width = max(1, self.width())
        height = max(1, self.height())
        for petal in self.petals:
            x = petal["x"] * width
            y = petal["y"] * height
            size = petal["size"]
            painter.save()
            painter.translate(x, y)
            painter.rotate(petal["angle"])
            color = QColor("#ff9fbd")
            color.setAlphaF(petal["alpha"])
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor(255, 255, 255, 100), 0.8))
            path = QPainterPath()
            path.moveTo(0, -size * 0.55)
            path.cubicTo(size * 0.58, -size * 0.30, size * 0.52, size * 0.36, 0, size * 0.62)
            path.cubicTo(-size * 0.52, size * 0.36, -size * 0.58, -size * 0.30, 0, -size * 0.55)
            painter.drawPath(path)
            painter.restore()


class MainWindow(QMainWindow):
    def __init__(self, initial_images: list[str]):
        super().__init__()
        ensure_dirs()
        if _PSUTIL_ERROR is not None:
            raise _PSUTIL_ERROR
        self.setWindowTitle(f"Kloudy's FH6 Painter - {get_version()}")
        self.resize(1280, 980)
        self.setMinimumSize(1180, 900)
        self.app_settings = load_app_settings()
        self.settings = load_settings()
        self.images = [Path(p) for p in initial_images if Path(p).exists()][:1]
        self.selected_import_json_path: Path | None = None
        self.selected_handmade_json_path: Path | None = None
        self.outputs: list[Path] = []
        self.processes = []
        self.active_processes = set()
        self.process_lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.stop_generation_event = threading.Event()
        self.active_generation_images: list[Path] = []
        self.active_generation_run_dirs: dict[Path, Path] = {}
        self.latest_generated_run_dir: Path | None = None
        self.auto_located_context: dict | None = None
        self.generated_folder_entries: dict[str, list[dict]] = {}
        self.generated_checkpoint_entries: list[dict] = []
        self.exported_game_json_entries: list[dict] = []
        self.preview_request_id = 0
        self.export_preview_request_id = 0
        self._all_combos: list[QComboBox] = []
        self._theme_apply_pending = False
        self.update_alarm_state = "checking"
        self.update_alarm_text = "checking main build..."
        self.update_blink_on = False
        self.update_check_running = False
        self.update_blink_timer = QTimer(self)
        self.update_blink_timer.setInterval(650)
        self.update_blink_timer.timeout.connect(self.toggle_update_alarm_blink)
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(5 * 60 * 1000)
        self.update_check_timer.timeout.connect(self.start_update_check)
        self.bus = UiBus()
        self.bus.log.connect(self.log_line)
        self.bus.status.connect(self.set_status)
        self.bus.progress.connect(self.set_progress)
        self.bus.phase.connect(self.set_phase)
        self.bus.update_alert.connect(self.show_update_alert)
        self.bus.preview_bytes.connect(self.show_preview_bytes)
        self.bus.preview_file.connect(self.show_preview_file)
        self.bus.json_preview.connect(self.show_json_preview_result)
        self.bus.export_json_preview.connect(self.show_export_json_preview_result)
        self.bus.refresh_lists.connect(self.render_lists)
        self.bus.generated_changed.connect(self.refresh_generated_browser)
        self.bus.auto_located.connect(self.apply_auto_locate_result)
        self.bus.ui_call.connect(lambda fn: fn())
        self._build()
        self.apply_theme()
        self.set_phase("ready", "Choose a source image or select a finalized JSON to import.")
        self.refresh_processes()
        self.refresh_generated_browser()
        self.refresh_game_export_browser()
        self.render_lists()
        if self.images:
            self.show_preview_bytes(render_source_image(self.images[0]) or b"")
        self.start_update_check()
        self.update_check_timer.start()

    def _build(self):
        central = AnimatedThemeBackground()
        central.setObjectName("appRoot")
        self.background_widget = central
        root = QVBoxLayout(central)
        self.phase_label = QLabel("Ready to generate or import.")
        self.phase_label.setObjectName("phaseBanner")
        self.phase_label.setWordWrap(True)
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.phase_label)
        self.update_alarm = QLabel("Main build: checking...")
        self.update_alarm.setObjectName("updateAlarm")
        self.update_alarm.setWordWrap(True)
        self.update_alarm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_alarm.setMaximumHeight(30)
        root.addWidget(self.update_alarm)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_generate_tab()
        self._build_import_tab()
        self._build_handmade_import_tab()
        self._build_game_export_tab()
        self._build_luma_tab()
        self._build_tutorial_tab()
        self._build_settings_tab()
        footer = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.progress_label = QLabel("")
        footer.addWidget(QLabel("Status:"))
        footer.addWidget(self.status_label)
        footer.addSpacing(24)
        footer.addWidget(QLabel("Progress:"))
        footer.addWidget(self.progress_label, 1)
        root.addLayout(footer)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(150)
        root.addWidget(self.log)
        self.setCentralWidget(central)

    def make_combo(self, items=None, *, max_visible: int = 16, min_height: int = 34, editable: bool = False) -> QComboBox:
        combo = configure_combo_box(QComboBox(), max_visible=max_visible, min_height=min_height, editable=editable)
        if items:
            combo.addItems([str(item) for item in items])
        self._all_combos.append(combo)
        return combo

    def close_combo_popups(self):
        for combo in getattr(self, "_all_combos", []):
            with contextlib.suppress(RuntimeError):
                combo.hidePopup()

    def _build_generate_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([520, 760])

        image_group = QGroupBox("Step 1 - Source Art")
        image_layout = QVBoxLayout(image_group)
        image_row = QHBoxLayout()
        choose = QPushButton("Choose source image")
        choose.clicked.connect(self.add_image)
        image_row.addWidget(choose)
        open_out = QPushButton("Open latest vinyl folder")
        open_out.clicked.connect(self.open_output_folder)
        image_row.addWidget(open_out)
        image_layout.addLayout(image_row)
        self.image_list = QListWidget()
        self.image_list.setMaximumHeight(72)
        self.image_list.currentRowChanged.connect(self.preview_selected_image)
        image_layout.addWidget(self.image_list)
        image_group.setMaximumHeight(145)
        left_layout.addWidget(image_group)

        quality_group = QGroupBox("Step 2 - Vinyl Build Preset")
        quality_layout = QVBoxLayout(quality_group)
        self.vroom = QCheckBox("vroom vroom scrrrrt zoooom!")
        self.vroom.stateChanged.connect(self.update_setting_description)
        quality_layout.addWidget(self.vroom)
        self.profile_combo = self.make_combo(max_visible=18, min_height=38)
        self.profile_combo.currentIndexChanged.connect(self.update_setting_description)
        quality_layout.addWidget(self.profile_combo)
        self.setting_description = QLabel("")
        self.setting_description.setWordWrap(True)
        quality_layout.addWidget(self.setting_description)
        self.custom_enabled = QCheckBox("Tune this run")
        self.custom_enabled.stateChanged.connect(self.sync_custom_state)
        quality_layout.addWidget(self.custom_enabled)
        form = QGridLayout()
        self.custom_layers = QLineEdit()
        self.custom_resolution = QLineEdit()
        self.custom_random = QLineEdit()
        self.custom_mutated = QLineEdit()
        self.custom_save_at = QLineEdit()
        fields = [
            ("Template layers", self.custom_layers),
            ("Max resolution", self.custom_resolution),
            ("Random samples", self.custom_random),
            ("Mutated samples", self.custom_mutated),
            ("Finalize at layers", self.custom_save_at),
        ]
        for row, (label, widget) in enumerate(fields):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)
        quality_layout.addLayout(form)
        preset_actions = QHBoxLayout()
        save_preset = QPushButton("Save custom preset")
        save_preset.clicked.connect(self.save_current_custom_preset)
        delete_preset = QPushButton("Delete selected custom")
        delete_preset.clicked.connect(self.delete_selected_custom_preset)
        preset_actions.addWidget(save_preset)
        preset_actions.addWidget(delete_preset)
        quality_layout.addLayout(preset_actions)
        self.luma_enabled = QCheckBox("Luma Prep - cleaner broad regions, but can soften tiny detail")
        self.luma_enabled.setToolTip("Best for flat logos/liveries and hard color bands. Leave off for most anime, hair, skin, and smooth gradients.")
        self.luma_enabled.setChecked(False)
        quality_layout.addWidget(self.luma_enabled)
        self.repair_enabled = QCheckBox("Edge Repair - clean borders and transparent holes")
        self.repair_enabled.setToolTip("Final pass that tightens borders and transparent holes on the finalized checkpoints.")
        self.repair_enabled.setChecked(True)
        quality_layout.addWidget(self.repair_enabled)
        left_layout.addWidget(quality_group)

        run_group = QGroupBox("Step 3 - Generate Final Vinyl")
        run_layout = QHBoxLayout(run_group)
        generate = QPushButton("Generate Final Vinyl")
        generate.setObjectName("primaryButton")
        generate.clicked.connect(self.start_generate)
        stop = QPushButton("Stop after next saved point")
        stop.clicked.connect(self.stop_generate)
        run_layout.addWidget(generate, 2)
        run_layout.addWidget(stop, 1)
        left_layout.addWidget(run_group)
        left_layout.addStretch()

        right_layout.addWidget(QLabel("Live Preview"))
        self.preview = PreviewView("Choose source art or a finalized vinyl to preview it here.")
        right_layout.addWidget(self.preview, 1)
        self.tabs.addTab(tab, "Generate Final Vinyl")
        self.populate_profile_list()
        self.update_setting_description()
        self.sync_custom_state()

    def _build_import_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([620, 660])

        game = QGroupBox("Step 1 - FH6 Session")
        game_layout = QGridLayout(game)
        self.game_combo = self.make_combo(list(PROFILES.keys()), max_visible=12)
        self.pid_combo = self.make_combo(max_visible=12, editable=True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_processes)
        game_layout.addWidget(QLabel("Game"), 0, 0)
        game_layout.addWidget(self.game_combo, 0, 1)
        game_layout.addWidget(QLabel("Process"), 1, 0)
        game_layout.addWidget(self.pid_combo, 1, 1)
        game_layout.addWidget(refresh, 1, 2)
        left_layout.addWidget(game)

        template = QGroupBox("Step 2 - Vinyl Template")
        template_layout = QGridLayout(template)
        self.layer_count = QLineEdit("3000")
        template_layout.addWidget(QLabel("Exact template layer count"), 0, 0)
        template_layout.addWidget(self.layer_count, 0, 1)
        template_help = QLabel("Default workflow: use one 3000-layer template. Imports are culled to the JSON's drawable layer count after writing.")
        template_help.setWordWrap(True)
        template_layout.addWidget(template_help, 1, 0, 1, 2)
        left_layout.addWidget(template)

        json_group = QGroupBox("Step 3 - Pick Final Vinyl")
        json_layout = QVBoxLayout(json_group)
        controls = QGridLayout()
        add_json = QPushButton("Choose final JSON...")
        add_json.clicked.connect(self.manual_add_json)
        refresh_jsons = QPushButton("Refresh")
        refresh_jsons.clicked.connect(self.refresh_generated_browser)
        add_recommended = QPushButton("Use best safe final")
        add_recommended.clicked.connect(self.select_recommended_generated_json)
        compare_btn = QPushButton("Compare selected with best")
        compare_btn.clicked.connect(self.compare_selected_checkpoint)
        resume_btn = QPushButton("Resume unfinished finalize")
        resume_btn.clicked.connect(self.start_resume_finalization)
        for button in (add_json, add_recommended, compare_btn, resume_btn):
            button.setMinimumWidth(170)
        refresh_jsons.setMinimumWidth(96)
        controls.addWidget(add_json, 0, 0)
        controls.addWidget(refresh_jsons, 0, 1)
        controls.addWidget(add_recommended, 0, 2)
        controls.addWidget(compare_btn, 1, 0, 1, 2)
        controls.addWidget(resume_btn, 1, 2)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        controls.setColumnStretch(2, 1)
        json_layout.addLayout(controls)
        self.generated_folder_combo = self.make_combo(max_visible=24, min_height=34)
        self.generated_folder_combo.currentTextChanged.connect(self.populate_generated_checkpoint_list)
        json_layout.addWidget(QLabel("Generated vinyl run"))
        json_layout.addWidget(QLabel("Pick a finalized checkpoint below. The highlighted final JSON is the one that will be imported."))
        json_layout.addWidget(self.generated_folder_combo)
        self.generated_checkpoint_list = QListWidget()
        self.generated_checkpoint_list.setObjectName("finalizedCheckpointList")
        self.generated_checkpoint_list.setMinimumHeight(420)
        self.generated_checkpoint_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.generated_checkpoint_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.generated_checkpoint_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.generated_checkpoint_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.generated_checkpoint_list.setWordWrap(True)
        self.generated_checkpoint_list.currentRowChanged.connect(self.select_generated_checkpoint)
        json_layout.addWidget(QLabel("Finalized checkpoints"))
        json_layout.addWidget(self.generated_checkpoint_list, 2)
        left_layout.addWidget(json_group, 1)

        import_group = QGroupBox("Step 4 - Import Final JSON")
        import_layout = QVBoxLayout(import_group)
        import_layout.addWidget(QLabel("Keep FH6 in Vinyl Group Editor and do not switch menus during import."))
        self.selected_json_label = QLabel("Selected final JSON: none")
        self.selected_json_label.setWordWrap(False)
        self.selected_json_label.setMaximumHeight(28)
        self.selected_json_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        import_layout.addWidget(self.selected_json_label)
        import_btn = QPushButton("Import Final JSON into FH6")
        import_btn.setObjectName("primaryButton")
        import_btn.clicked.connect(self.start_import)
        auto_btn = QPushButton("Auto-locate FH6 template")
        auto_btn.clicked.connect(self.start_auto_locate)
        import_layout.addWidget(import_btn)
        import_layout.addWidget(auto_btn)
        right_layout.addWidget(import_group)
        right_layout.addWidget(QLabel("Final Vinyl Preview"))
        self.import_preview = PreviewView("Select a finalized JSON to preview it here.")
        right_layout.addWidget(self.import_preview, 1)
        self.tabs.addTab(tab, "Import Final JSON")

    def _build_handmade_import_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([640, 640])

        intro = QLabel(
            "Universal handmade importer/exporter. Import a handmade JSON into a fresh template, "
            "or export the currently open FH6 group into a compatible handmade JSON."
        )
        intro.setWordWrap(True)
        left_layout.addWidget(intro)
        warning = QLabel(
            "WIP: after importing, save and reload the vinyl group to view the shapes properly. "
            "A weird vinyl thumbnail in the menu is normal right now. Both issues are being worked on."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("font-weight: 900; font-size: 15px;")
        left_layout.addWidget(warning)

        game = QGroupBox("Step 1 - FH6 Session")
        game_layout = QGridLayout(game)
        self.handmade_pid_combo = self.make_combo(max_visible=12, editable=True)
        handmade_refresh = QPushButton("Refresh FH6")
        handmade_refresh.clicked.connect(self.refresh_processes)
        game_layout.addWidget(QLabel("Process"), 0, 0)
        game_layout.addWidget(self.handmade_pid_combo, 0, 1)
        game_layout.addWidget(handmade_refresh, 0, 2)
        left_layout.addWidget(game)

        template = QGroupBox("Step 2 - Base Template")
        template_layout = QGridLayout(template)
        self.handmade_template_count = QLineEdit("3000")
        self.handmade_template_count.setToolTip("Use a fresh 3000-layer circle template for universal imports, then the app trims to the used layer count.")
        template_layout.addWidget(QLabel("Loaded template layer count"), 0, 0)
        template_layout.addWidget(self.handmade_template_count, 0, 1)
        template_help = QLabel("Recommended: open a fresh 3000-layer template in FH6 Vinyl Group Editor and ungroup it before importing.")
        template_help.setWordWrap(True)
        template_layout.addWidget(template_help, 1, 0, 1, 2)
        left_layout.addWidget(template)

        json_group = QGroupBox("Step 3 - Handmade JSON")
        json_layout = QVBoxLayout(json_group)
        pick_row = QHBoxLayout()
        pick = QPushButton("Choose handmade JSON")
        pick.clicked.connect(self.choose_handmade_json)
        pick_row.addWidget(pick)
        json_layout.addLayout(pick_row)
        self.handmade_json_label = QLabel("Selected handmade JSON: none")
        self.handmade_json_label.setWordWrap(True)
        self.handmade_json_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        json_layout.addWidget(self.handmade_json_label)
        left_layout.addWidget(json_group)

        run_group = QGroupBox("Step 4 - Import And Trim")
        run_layout = QVBoxLayout(run_group)
        self.handmade_clear_unused = QCheckBox("Clear unused template layers before trimming")
        self.handmade_clear_unused.setChecked(True)
        self.handmade_clear_unused.setToolTip("Keeps the save file clean if FH6 briefly sees the old template capacity during import.")
        run_layout.addWidget(self.handmade_clear_unused)
        import_btn = QPushButton("Import Handmade JSON into 3000 Template")
        import_btn.setObjectName("primaryButton")
        import_btn.clicked.connect(self.start_handmade_import)
        run_layout.addWidget(import_btn)
        run_help = QLabel("After import completes, save and reload the vinyl group to confirm the final trimmed layer count.")
        run_help.setWordWrap(True)
        run_layout.addWidget(run_help)
        left_layout.addWidget(run_group)
        left_layout.addStretch()

        right_layout.addWidget(QLabel("Universal Import Notes"))
        notes = QTextEdit()
        notes.setReadOnly(True)
        notes.setText(
            "Confirmed model:\n"
            "- Uses full 16-bit shape word at layer offset 0x7A.\n"
            "- Writes position, scale, rotation, skew, color, mask flag, and shape word only.\n"
            "- Exports the same fields read-only from the current FH6 group.\n"
            "- Does not copy volatile render/cache fields or resource pointers.\n"
            "- Auto-locates the loaded template by layer count.\n"
            "- Trims FH6 group count and table end after import.\n\n"
            "Current best workflow:\n"
            "1. Open FH6 Vinyl Group Editor.\n"
            "2. Load/prepare a fresh 3000-layer circle template.\n"
            "3. Ungroup it.\n"
            "4. To import: choose a handmade JSON, import, then save/reload.\n"
            "5. To export: enter the current group layer count and click export."
        )
        right_layout.addWidget(notes, 1)
        self.tabs.addTab(tab, "Import Handmade JSON")

    def _build_game_export_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([620, 660])

        intro = QLabel(
            "Export the currently open FH6 vinyl group into a handmade-compatible JSON. "
            "This is read-only: it only reads the live layer table and writes a JSON file."
        )
        intro.setWordWrap(True)
        left_layout.addWidget(intro)

        game = QGroupBox("Step 1 - FH6 Session")
        game_layout = QGridLayout(game)
        self.export_pid_combo = self.make_combo(max_visible=12, editable=True)
        export_refresh = QPushButton("Refresh FH6")
        export_refresh.clicked.connect(self.refresh_processes)
        game_layout.addWidget(QLabel("Process"), 0, 0)
        game_layout.addWidget(self.export_pid_combo, 0, 1)
        game_layout.addWidget(export_refresh, 0, 2)
        left_layout.addWidget(game)

        template = QGroupBox("Step 2 - Current Open Group")
        template_layout = QGridLayout(template)
        self.export_template_count = QLineEdit("3000")
        self.export_template_count.setToolTip("Enter the exact layer count of the currently open and ungrouped FH6 group.")
        template_layout.addWidget(QLabel("Current group layer count"), 0, 0)
        template_layout.addWidget(self.export_template_count, 0, 1)
        template_help = QLabel("Keep the group open, ungrouped, and do not switch FH6 menus while exporting.")
        template_help.setWordWrap(True)
        template_layout.addWidget(template_help, 1, 0, 1, 2)
        left_layout.addWidget(template)

        run_group = QGroupBox("Step 3 - Export")
        run_layout = QVBoxLayout(run_group)
        export_btn = QPushButton("Export Current FH6 Group")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self.start_game_export)
        run_layout.addWidget(export_btn)
        run_layout.addWidget(QLabel("Output is saved under runtime/universal-import and appears in the browser below."))
        left_layout.addWidget(run_group)

        browser = QGroupBox("Exported Game JSON Browser")
        browser_layout = QVBoxLayout(browser)
        browser_controls = QHBoxLayout()
        refresh_exports = QPushButton("Refresh exports")
        refresh_exports.clicked.connect(self.refresh_game_export_browser)
        use_for_import = QPushButton("Use selected in Handmade Import")
        use_for_import.clicked.connect(self.use_selected_export_for_handmade_import)
        browser_controls.addWidget(refresh_exports)
        browser_controls.addWidget(use_for_import)
        browser_layout.addLayout(browser_controls)
        self.exported_game_json_list = QListWidget()
        self.exported_game_json_list.setMinimumHeight(310)
        self.exported_game_json_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.exported_game_json_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.exported_game_json_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.exported_game_json_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.exported_game_json_list.setWordWrap(True)
        self.exported_game_json_list.currentRowChanged.connect(self.select_exported_game_json)
        browser_layout.addWidget(self.exported_game_json_list, 1)
        left_layout.addWidget(browser, 1)

        right_layout.addWidget(QLabel("Export Preview"))
        self.export_preview = PreviewView("Export a game group or select an exported JSON to preview it here.")
        right_layout.addWidget(self.export_preview, 1)
        note = QLabel(
            "Preview is an approximation for non-basic FH shapes until full shape rendering is added. "
            "The JSON still preserves the real FH type word for re-import."
        )
        note.setWordWrap(True)
        right_layout.addWidget(note)
        self.tabs.addTab(tab, "Export Game JSON")

    def _build_luma_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QGroupBox("Standalone Luma Band Pass")
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(QLabel("Choose one image. The app saves a luma-banded PNG into imgs/luma-bands and previews the before/after here."))
        actions = QHBoxLayout()
        choose = QPushButton("Choose image and run Luma Band Pass")
        choose.setObjectName("primaryButton")
        choose.clicked.connect(self.choose_luma_image)
        open_folder = QPushButton("Open luma-band folder")
        open_folder.clicked.connect(self.open_luma_folder)
        actions.addWidget(choose, 2)
        actions.addWidget(open_folder, 1)
        controls_layout.addLayout(actions)
        self.luma_status_label = QLabel(f"Output folder: {LUMA_BANDS_ROOT}")
        self.luma_status_label.setWordWrap(True)
        controls_layout.addWidget(self.luma_status_label)
        layout.addWidget(controls)

        preview_row = QHBoxLayout()
        before_col = QVBoxLayout()
        after_col = QVBoxLayout()
        before_col.addWidget(QLabel("Before"))
        after_col.addWidget(QLabel("After Luma Band Pass"))
        self.luma_before_preview = PreviewView("Choose an image to preview the source here.")
        self.luma_after_preview = PreviewView("The luma-banded result will appear here.")
        before_col.addWidget(self.luma_before_preview, 1)
        after_col.addWidget(self.luma_after_preview, 1)
        preview_row.addLayout(before_col, 1)
        preview_row.addLayout(after_col, 1)
        layout.addLayout(preview_row, 1)
        self.tabs.addTab(tab, "Luma Band Pass")

    def _build_tutorial_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(TEXT["tutorial"])
        layout.addWidget(text)
        self.tabs.addTab(tab, "Tutorial")

    def _build_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        theme = QGroupBox("Appearance")
        theme_layout = QVBoxLayout(theme)
        self.theme_combo = self.make_combo(list(THEMES.keys()), max_visible=len(THEMES), min_height=38)
        selected_theme = self.app_settings.get("theme", DEFAULT_THEME)
        if selected_theme in THEMES:
            self.theme_combo.setCurrentText(selected_theme)
        self.theme_combo.activated.connect(self.schedule_theme_apply)
        theme_layout.addWidget(QLabel("Theme"))
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addWidget(QLabel("Theme changes apply immediately and are saved for the next launch."))
        theme_layout.addWidget(QLabel("Sakura Glass uses an opaque control frame with animated cherry blossoms in the background."))
        theme_layout.addWidget(QLabel("Blackout is a full dark opaque preset for low-glare use."))
        layout.addWidget(theme)
        importer = QGroupBox("Importer")
        importer_layout = QVBoxLayout(importer)
        self.legacy_masks_enabled = QCheckBox("Use legacy 4 big FH border masks")
        self.legacy_masks_enabled.setChecked(bool(self.app_settings.get("legacy_border_masks", False)))
        self.legacy_masks_enabled.stateChanged.connect(self.save_importer_settings)
        importer_layout.addWidget(self.legacy_masks_enabled)
        mask_note = QLabel(
            "Default uses no FH border masks. Finalize Checkpoints now keeps transparent-source shapes inside the PNG canvas. Legacy uses the old 4 big border masks and may make underlying vinyls transparent when stacking designs."
        )
        mask_note.setWordWrap(True)
        importer_layout.addWidget(mask_note)
        layout.addWidget(importer)
        layout.addStretch()
        self.tabs.addTab(tab, "Settings")

    def save_importer_settings(self, *_args):
        if hasattr(self, "legacy_masks_enabled"):
            self.app_settings["legacy_border_masks"] = bool(self.legacy_masks_enabled.isChecked())
            save_app_settings(self.app_settings)

    def schedule_theme_apply(self, *_args):
        if self._theme_apply_pending:
            return
        self._theme_apply_pending = True
        self.close_combo_popups()
        QTimer.singleShot(80, self.apply_theme)

    def apply_theme(self, *_args):
        self._theme_apply_pending = False
        self.close_combo_popups()
        theme_name = self.theme_combo.currentText() if hasattr(self, "theme_combo") else DEFAULT_THEME
        theme_key = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
        if hasattr(self, "background_widget"):
            self.background_widget.set_theme(theme_key)
        if hasattr(self, "app_settings"):
            self.app_settings["theme"] = theme_name
            save_app_settings(self.app_settings)
        if theme_key == "sakura":
            self.setStyleSheet(
                """
                QMainWindow { background: #f8dfec; color: #332534; font-family: "Segoe UI Variable", "Segoe UI"; font-size: 10pt; }
                QWidget#appRoot { background: transparent; }
                QTabWidget::pane { border: 2px solid #9b5870; border-radius: 14px; background: #fff9fb; }
                QTabBar::tab { background: #e9c2d0; color: #5d2d41; padding: 10px 18px; border: 1px solid #a7647a; border-bottom: none; border-top-left-radius: 11px; border-top-right-radius: 11px; margin-right: 4px; font-weight: 700; }
                QTabBar::tab:selected { background: #fff9fb; color: #3b1f2f; }
                QGroupBox { border: 2px solid #9f6479; border-radius: 16px; margin-top: 14px; padding: 12px; background: #fffafa; font-weight: 700; color: #7f3d58; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; background: #fffafa; }
                QPushButton { background: #f3c7d6; color: #3d2430; border: 1px solid #9f6479; border-radius: 10px; padding: 8px 14px; font-weight: 700; min-height: 26px; }
                QPushButton:hover { background: #f8d9e4; }
                QPushButton#primaryButton { background: #a83f67; color: white; border: 1px solid #793047; font-weight: 800; padding: 12px 14px; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #fffdfd; color: #332534; border: 2px solid #b77b8f; border-radius: 9px; padding: 6px; selection-background-color: #d65f89; selection-color: white; }
                QComboBox { padding-right: 30px; }
                QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #b77b8f; border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: #f3c7d6; }
                QComboBox QAbstractItemView { background: #fffdfd; color: #332534; border: 2px solid #b77b8f; selection-background-color: #d65f89; selection-color: white; outline: 0; }
                QScrollArea, QAbstractScrollArea { background: transparent; border: none; }
                QCheckBox { spacing: 8px; color: #332534; }
                QLabel { color: #332534; background: transparent; }
                """
            )
        elif theme_key == "blackout":
            self.setStyleSheet(
                """
                QMainWindow, QWidget { background: #000000; color: #f4f4f4; font-family: "Segoe UI Variable", "Segoe UI"; font-size: 10pt; }
                QWidget#appRoot { background: #000000; }
                QTabWidget::pane { border: 1px solid #151515; border-radius: 12px; background: #000000; }
                QTabBar::tab { background: #030303; color: #bdbdbd; padding: 10px 18px; border: 1px solid #1b1b1b; border-bottom: none; border-top-left-radius: 10px; border-top-right-radius: 10px; margin-right: 4px; font-weight: 700; }
                QTabBar::tab:hover { background: #080808; color: #ffffff; }
                QTabBar::tab:selected { background: #000000; color: #ffffff; border-color: #343434; }
                QGroupBox { border: 1px solid #181818; border-radius: 14px; margin-top: 14px; padding: 12px; background: #000000; font-weight: 700; color: #f4f4f4; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; background: #000000; color: #ffffff; }
                QPushButton { background: #050505; color: #f4f4f4; border: 1px solid #333333; border-radius: 10px; padding: 8px 14px; font-weight: 700; min-height: 26px; }
                QPushButton:hover { background: #101010; border-color: #666666; }
                QPushButton:pressed { background: #000000; }
                QPushButton#primaryButton { background: #ffffff; color: #000000; border: 1px solid #ffffff; font-weight: 900; padding: 12px 14px; }
                QPushButton#primaryButton:hover { background: #dedede; color: #000000; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #000000; color: #f4f4f4; border: 1px solid #2b2b2b; border-radius: 8px; padding: 6px; selection-background-color: #ffffff; selection-color: #000000; }
                QComboBox { padding-right: 30px; }
                QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #2b2b2b; border-top-right-radius: 7px; border-bottom-right-radius: 7px; background: #050505; }
                QComboBox QAbstractItemView { background: #000000; color: #f4f4f4; border: 1px solid #343434; selection-background-color: #ffffff; selection-color: #000000; outline: 0; }
                QGraphicsView { background: #000000; border: 1px solid #181818; }
                QScrollArea, QAbstractScrollArea { background: #000000; border: none; }
                QCheckBox { spacing: 8px; color: #f4f4f4; background: #000000; }
                QLabel { color: #f4f4f4; background: transparent; }
                QLabel#updateAlarm { background: transparent; color: #7cff7c; border: none; padding: 0; font-weight: 800; }
                QHeaderView::section { background: #000000; color: #f4f4f4; border: 1px solid #1d1d1d; padding: 5px; }
                QScrollBar:vertical, QScrollBar:horizontal { background: #000000; border: none; width: 13px; height: 13px; }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #303030; border-radius: 6px; min-height: 24px; min-width: 24px; }
                QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #555555; }
                QScrollBar::add-line, QScrollBar::sub-line { background: transparent; border: none; width: 0; height: 0; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QMainWindow, QWidget { background: #f5edff; color: #3b244d; font-family: "Segoe UI"; font-size: 10pt; }
                QTabWidget::pane { border: 1px solid #d8c2f0; border-radius: 12px; background: #fff8fb; }
                QTabBar::tab { background: #eadcff; color: #5a2f83; padding: 10px 18px; border-top-left-radius: 10px; border-top-right-radius: 10px; margin-right: 4px; }
                QTabBar::tab:selected { background: #fff8fb; color: #3b244d; }
                QGroupBox { border: 1px solid #d8c2f0; border-radius: 14px; margin-top: 14px; padding: 12px; background: #fff8fb; font-weight: 600; color: #6c3fa0; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; }
                QPushButton { background: #eadcff; color: #3b244d; border: 1px solid #c7a8ea; border-radius: 10px; padding: 8px 14px; min-height: 26px; }
                QPushButton:hover { background: #dfc9ff; }
                QPushButton#primaryButton { background: #9f6ad8; color: white; font-weight: 700; padding: 12px 14px; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #fffdf8; color: #3b244d; border: 1px solid #d8c2f0; border-radius: 8px; padding: 6px; selection-background-color: #cfa8ff; }
                QComboBox { padding-right: 30px; }
                QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #d8c2f0; border-top-right-radius: 7px; border-bottom-right-radius: 7px; background: #eadcff; }
                QComboBox QAbstractItemView { background: #fffdf8; color: #3b244d; border: 1px solid #d8c2f0; selection-background-color: #cfa8ff; selection-color: #3b244d; outline: 0; }
                QCheckBox { spacing: 8px; }
                QLabel { color: #3b244d; }
                """
            )
        self.apply_update_alarm_style()

    def start_update_check(self):
        if self.update_check_running:
            return
        self.update_check_running = True
        self.show_update_alert("checking", "checking main build...")
        threading.Thread(target=self.update_check_worker, daemon=True).start()

    def update_check_worker(self):
        try:
            local_version = local_app_version()
            try:
                remote_version = remote_app_version()
            except Exception as exc:
                self.bus.log.emit(f"Main build check failed: {exc}")
                self.bus.update_alert.emit("unknown", "main build check unavailable")
                return
            if not local_version or local_version == "unknown" or not remote_version:
                self.bus.update_alert.emit("unknown", "main build check unavailable")
                return
            version_state = compare_versions(local_version, remote_version)
            if version_state < 0:
                self.bus.update_alert.emit("available", f"update available: main {remote_version}")
            elif version_state > 0:
                self.bus.update_alert.emit("ok", f"local test build: {local_version}")
            else:
                try:
                    local_revision = local_app_revision()
                    remote_revision = remote_main_revision()
                except Exception as exc:
                    self.bus.log.emit(f"Main revision check failed: {exc}")
                    self.bus.update_alert.emit("ok", f"up to date: main {local_version}")
                    return
                if main_revision_has_bugfix(local_revision, remote_revision):
                    remote_short = remote_revision[:8] if remote_revision else ""
                    suffix = f" {remote_short}" if remote_short else ""
                    self.bus.update_alert.emit("bugfix", f"bugfix available: main {local_version}{suffix}")
                else:
                    self.bus.update_alert.emit("ok", f"up to date: main {local_version}")
        finally:
            self.update_check_running = False

    def show_update_alert(self, state: str, text: str):
        self.update_alarm_state = state
        self.update_alarm_text = text
        self.update_blink_on = state in ("available", "bugfix")
        if state in ("available", "bugfix"):
            if not self.update_blink_timer.isActive():
                self.update_blink_timer.start()
        else:
            self.update_blink_timer.stop()
        self.apply_update_alarm_style()

    def toggle_update_alarm_blink(self):
        self.update_blink_on = not self.update_blink_on
        self.apply_update_alarm_style()

    def apply_update_alarm_style(self):
        if not hasattr(self, "update_alarm"):
            return
        state = self.update_alarm_state
        text = self.update_alarm_text
        self.update_alarm.setText(text)
        base_style = "QLabel#updateAlarm { background: transparent; border: none; padding: 0; font-weight: 900; font-size: 9pt; }"
        if state == "available":
            if self.update_blink_on:
                style = "color: #ff2020;"
            else:
                style = "color: #ff7a7a;"
        elif state == "bugfix":
            if self.update_blink_on:
                style = "color: #ff4fb8;"
            else:
                style = "color: #ffb3dc;"
        elif state == "ok":
            style = "color: #19b84a;"
        elif state == "checking":
            style = "color: #808080;"
        else:
            style = "color: #808080;"
        self.update_alarm.setStyleSheet(base_style.replace("}", f" {style} }}"))

    def populate_profile_list(self, select_path: Path | None = None):
        if not hasattr(self, "profile_combo"):
            return
        current_path = select_path
        if current_path is None:
            current = self.selected_setting()
            if current:
                current_path = Path(current.get("path", ""))
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        selected_index = 0
        for row, item in enumerate(self.settings):
            label = item["label"]
            if item.get("is_user_preset"):
                label = f"{label}  [saved]"
            self.profile_combo.addItem(label, item)
            if current_path and Path(item.get("path", "")) == current_path:
                selected_index = row
        if self.profile_combo.count() > 0:
            self.profile_combo.setCurrentIndex(selected_index)
        self.profile_combo.blockSignals(False)

    def current_custom_values(self):
        return {
            "stopAt": self.custom_layers.text(),
            "maxResolution": self.custom_resolution.text(),
            "randomSamples": self.custom_random.text(),
            "mutatedSamples": self.custom_mutated.text(),
            "saveAt": self.custom_save_at.text(),
            "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
            "v2EnableRepair": "true" if self.repair_enabled.isChecked() else "false",
        }

    def save_current_custom_preset(self):
        setting = self.selected_setting()
        if not setting:
            self.log_line("No preset selected to save from.")
            return
        default_name = re.sub(r"^Custom:\s*", "", str(setting.get("name") or ""), flags=re.I).strip()
        if not default_name or not setting.get("is_user_preset"):
            default_name = "My Custom Preset"
        name, ok = QInputDialog.getText(self, "Save custom preset", "Preset name:", text=default_name)
        if not ok:
            return
        name = name.strip()
        if not name:
            self.log_line("Custom preset was not saved: no name entered.")
            return
        try:
            saved = save_user_preset(name, setting, self.current_custom_values())
        except Exception as exc:
            self.log_line(f"Custom preset save failed: {exc}")
            QMessageBox.warning(self, "Save custom preset", f"Could not save preset:\n{exc}")
            return
        self.settings = load_settings()
        self.populate_profile_list(Path(saved["path"]))
        self.custom_enabled.setChecked(False)
        self.update_setting_description()
        self.log_line(f"Saved custom preset: {name}")

    def delete_selected_custom_preset(self):
        setting = self.selected_setting()
        if not setting or not setting.get("is_user_preset"):
            QMessageBox.information(self, "Delete custom preset", "Select a saved custom preset first.")
            return
        name = setting.get("name") or setting.get("label") or Path(setting.get("path", "")).stem
        answer = QMessageBox.question(
            self,
            "Delete custom preset",
            f"Delete saved preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not delete_user_preset(setting):
            self.log_line(f"Could not delete custom preset: {name}")
            return
        self.settings = load_settings()
        self.populate_profile_list()
        self.update_setting_description()
        self.log_line(f"Deleted custom preset: {name}")

    def update_setting_description(self):
        if not hasattr(self, "setting_description"):
            return
        item = self.selected_setting()
        if not item:
            self.setting_description.setText("No Kloudy presets found.")
            return
        description = item.get("description") or ""
        values = item.get("values", {})
        description += (
            "\n\nPreset details:"
            f"\n- Target layers: {values.get('stopAt', 'n/a')}"
            f"\n- Random samples: {values.get('randomSamples', 'n/a')}"
            f"\n- Mutated samples: {values.get('mutatedSamples', 'n/a')}"
            f"\n- Max resolution: {values.get('maxResolution', 'n/a')}"
            f"\n- Finalize at: {values.get('saveAt', values.get('stopAt', 'n/a'))}"
        )
        if self.vroom.isChecked():
            description += "\nVroom doubles random samples and mutated samples; output layers and resolution stay unchanged."
        if item.get("is_user_preset"):
            description += "\nThis is a saved custom preset stored in runtime/user-presets."
        self.setting_description.setText(description)
        if not self.custom_enabled.isChecked():
            self.custom_layers.setText(values.get("stopAt", "3000"))
            self.custom_resolution.setText(values.get("maxResolution", "1200"))
            self.custom_random.setText(values.get("randomSamples", "3000"))
            self.custom_mutated.setText(values.get("mutatedSamples", "1000"))
            self.custom_save_at.setText(values.get("saveAt", values.get("stopAt", "3000")))
            self.luma_enabled.setChecked(str(values.get("v2PreprocessMode", "none")).strip().lower() == "luma_bands")
            self.repair_enabled.setChecked(str(values.get("v2EnableRepair", "true")).strip().lower() in ("1", "true", "yes", "on"))

    def sync_custom_state(self):
        enabled = self.custom_enabled.isChecked()
        for widget in (self.custom_layers, self.custom_resolution, self.custom_random, self.custom_mutated, self.custom_save_at):
            widget.setEnabled(enabled)

    def selected_setting(self):
        if hasattr(self, "profile_combo"):
            item = self.profile_combo.currentData()
            if item:
                return item
        return self.settings[0] if self.settings else None

    def vroom_boost_overrides(self, values):
        if not self.vroom.isChecked():
            return {}
        excluded = {"description", "forceOpaqueShapes", "maxPreviewSize", "maxResolution", "saveAt", "shapeMode", "stopAt", "useWorkGroupEval", "v2EnableRepair", "v2PreprocessMode"}
        overrides = {}
        for key, value in values.items():
            text = str(value).strip()
            if key not in excluded and re.fullmatch(r"-?\d+", text) and int(text) > 0:
                overrides[key] = str(int(text) * 2)
        return overrides

    def effective_setting(self):
        setting = self.selected_setting()
        if not setting:
            return None
        overrides = {
            "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
            "forceOpaqueShapes": "true",
        }
        if self.custom_enabled.isChecked():
            overrides.update(self.current_custom_values())
        base_values = dict(setting.get("values", {}))
        base_values.update({key: value for key, value in overrides.items() if str(value).strip()})
        overrides.update(self.vroom_boost_overrides(base_values))
        force_opaque_changed = str(setting.get("values", {}).get("forceOpaqueShapes", "true")).strip().lower() not in ("1", "true", "yes", "on")
        if (
            self.custom_enabled.isChecked()
            or self.vroom.isChecked()
            or force_opaque_changed
            or overrides["v2PreprocessMode"] != str(setting.get("values", {}).get("v2PreprocessMode", "none")).strip().lower()
        ):
            boosted = write_custom_settings(setting, overrides)
            boosted["label"] = setting.get("label", boosted.get("label"))
            return boosted
        return setting

    def add_image(self):
        USER_IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose source image", str(USER_IMAGES_ROOT), "Images (*.png *.jpg *.jpeg *.bmp);;All files (*.*)")
        if not file_name:
            return
        path = Path(file_name)
        self.images = [path]
        self.render_lists()
        self.show_preview_bytes(render_source_image(path) or b"")

    def choose_luma_image(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose image for Luma Band Pass", "", "Images (*.png *.jpg *.jpeg *.bmp);;All files (*.*)")
        if not file_name:
            return
        source = Path(file_name)
        self.luma_status_label.setText(f"Processing: {source}")
        self.luma_before_preview.set_bytes(render_source_image(source) or b"")
        QApplication.processEvents()
        try:
            output = build_luma_bands_file(source)
        except Exception as exc:
            self.luma_status_label.setText(f"Luma Band Pass failed: {exc}")
            self.luma_after_preview.clear("Luma Band Pass failed.")
            self.log_line(f"Luma Band Pass failed: {exc}")
            return
        self.luma_after_preview.set_file(output)
        self.luma_status_label.setText(f"Saved luma-band image: {output}")
        self.log_line(f"Luma Band Pass saved: {output}")

    def open_luma_folder(self):
        LUMA_BANDS_ROOT.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(LUMA_BANDS_ROOT)
        else:
            subprocess.Popen(["xdg-open", str(LUMA_BANDS_ROOT)])

    def manual_add_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose finalized vinyl JSON", "", "Final vinyl JSON (*.json);;All files (*.*)")
        if not file_name:
            return
        path = Path(file_name)
        if path.exists():
            self.select_import_json(path, "manual final JSON")
        self.render_lists()

    def choose_handmade_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose handmade JSON", "", "Handmade JSON (*.json);;All files (*.*)")
        if not file_name:
            return
        path = Path(file_name)
        if not path.exists():
            return
        try:
            count = handmade_shape_count(path)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid handmade JSON", str(exc))
            return
        self.selected_handmade_json_path = path
        self.handmade_json_label.setText(f"Selected handmade JSON: {path.name}\nShapes: {count}\n{path}")
        self.handmade_json_label.setToolTip(str(path))
        self.log_line(f"Selected handmade JSON: {path} ({count} shapes)")

    def render_lists(self):
        self.image_list.clear()
        for path in self.images:
            self.image_list.addItem(str(path))
        self.update_selected_json_label()

    def log_line(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.append(f"[{timestamp}] {message}")
        hint = self.actionable_hint(message)
        if hint:
            self.log.append(f"    -> {hint}")

    def actionable_hint(self, message: str) -> str | None:
        lower = (message or "").lower()
        if "no usable python" in lower or "python 3.12 was not found" in lower:
            return "Open the launcher and click Setup Python, then Install Dependencies."
        if "dependency" in lower and ("missing" in lower or "not found" in lower):
            return "Run 02_install_dependencies.bat or use Install Dependencies in the launcher."
        if "openprocess" in lower or "permission" in lower or "access is denied" in lower:
            return "Close the app and start it as administrator, then keep FH6 open."
        if "ungroup" in lower:
            return "Stay inside Vinyl Group Editor, ungroup the template, and verify the exact layer count."
        if "does not point to a valid first slot" in lower or "failed validation" in lower:
            return "Refresh/auto-locate after opening the correct ungrouped FH6 template in Vinyl Group Editor."
        if "over-budget" in lower or "over layer budget" in lower:
            return "Pick a lower finalized checkpoint or use a larger FH6 template."
        if "png input buffer is incomplete" in lower:
            return "The preview image is incomplete or still being written. Wait for Finalize Checkpoints to finish, then refresh."
        if "generator exited with code 1" in lower:
            return "Check the lines above this error. The real cause is usually printed before the exit code."
        if "game process not found" in lower or "no supported game process" in lower:
            return "Start FH6 first, enter Vinyl Group Editor, then click Refresh."
        return None

    def set_status(self, text: str):
        self.status_label.setText(text)
        if text == "Done":
            self.set_phase("done", "Ready to import a finalized JSON.")
        elif text == "Failed":
            self.set_phase("failed", "Something failed. Check the log below for the exact error.")
        elif text == "Stopping":
            self.set_phase("finalizing", "Stop requested. Waiting for the latest checkpoint to finalize.")
        elif text == "Importing":
            self.set_phase("importing", "Writing the selected final JSON into FH6. Do not switch menus.")

    def set_progress(self, text: str):
        self.progress_label.setText(text)
        phase = self.phase_from_progress(text)
        if phase:
            self.set_phase(*phase)

    def phase_from_progress(self, text: str) -> tuple[str, str] | None:
        if text.startswith(("Building layer ", "Step ", "Retry ", "Saved internal checkpoint", "Updated preview")):
            return ("building", "Internal build is running. Final import JSONs are not ready yet.")
        if text.startswith(("Internal build finished", "INTERNAL BUILD COMPLETE", "Finalize ", "Finalizing ", "Edge Repair:", "Candidate ", "Best accuracy:", "Final JSON:", "Final preview:", "Report:")):
            return ("finalizing", "Finalize Checkpoints is running. Do not close yet.")
        if text.startswith("FINALIZE CHECKPOINTS COMPLETE"):
            return ("done", "Finalized JSONs are ready. Go to Import Final JSON.")
        return None

    def set_phase(self, phase: str, detail: str):
        labels = {
            "ready": "READY",
            "building": "BUILDING RAW GEOMETRY",
            "finalizing": "FINALIZING CHECKPOINTS - DO NOT CLOSE",
            "done": "READY TO IMPORT",
            "failed": "FAILED",
            "importing": "IMPORTING INTO FH6",
        }
        colors = {
            "ready": ("#202020", "#e8e8e8", "#a0a0a0"),
            "building": ("#102a43", "#d8ecff", "#67a9e8"),
            "finalizing": ("#3a2400", "#fff1c4", "#f4b000"),
            "done": ("#063514", "#d9f8df", "#38a853"),
            "failed": ("#4a0000", "#ffd7d7", "#e02020"),
            "importing": ("#2d155f", "#eadfff", "#8b5cf6"),
        }
        fg, bg, border = colors.get(phase, colors["ready"])
        self.phase_label.setText(f"{labels.get(phase, phase.upper())}\n{detail}")
        self.phase_label.setStyleSheet(
            f"QLabel#phaseBanner {{ color: {fg}; background: {bg}; border: 2px solid {border}; "
            "border-radius: 12px; padding: 10px; font-weight: 900; font-size: 12pt; }"
        )

    def show_preview_bytes(self, data: bytes):
        self.preview.set_bytes(data)
        self.import_preview.set_bytes(data)

    def show_preview_file(self, path: str):
        self.preview.set_file(path)
        self.import_preview.set_file(path)

    def preview_selected_image(self, row: int):
        if 0 <= row < len(self.images):
            self.preview_request_id += 1
            self.show_preview_bytes(render_source_image(self.images[row]) or b"")

    def preview_json(self, path: Path):
        self.preview_request_id += 1
        request_id = self.preview_request_id
        preview = self.preview_path_for_json(path)
        if preview and preview.exists():
            self.show_preview_file(str(preview))
        else:
            self.preview.clear("Rendering final vinyl preview...")
            self.import_preview.clear("Rendering final vinyl preview...")
            threading.Thread(target=self.render_json_preview_worker, args=(Path(path), request_id), daemon=True).start()

    def render_json_preview_worker(self, path: Path, request_id: int):
        cache_path = self.rendered_preview_cache_path(path)
        try:
            if cache_path.exists() and cache_path.stat().st_mtime >= path.stat().st_mtime:
                self.bus.json_preview.emit(request_id, cache_path.read_bytes())
                return
        except OSError:
            pass
        data = render_geometry_json(path)
        if data:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
            except OSError:
                pass
        self.bus.json_preview.emit(request_id, data)

    def show_json_preview_result(self, request_id: int, data):
        if request_id == self.preview_request_id:
            self.show_preview_bytes(data or b"")

    def preview_export_json(self, path: Path):
        self.export_preview_request_id += 1
        request_id = self.export_preview_request_id
        self.export_preview.clear("Rendering exported game JSON preview...")
        threading.Thread(target=self.render_export_json_preview_worker, args=(Path(path), request_id), daemon=True).start()

    def render_export_json_preview_worker(self, path: Path, request_id: int):
        cache_path = self.rendered_preview_cache_path(path)
        try:
            if cache_path.exists() and cache_path.stat().st_mtime >= path.stat().st_mtime:
                self.bus.export_json_preview.emit(request_id, cache_path.read_bytes())
                return
        except OSError:
            pass
        data = render_geometry_json(path)
        if data:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
            except OSError:
                pass
        self.bus.export_json_preview.emit(request_id, data)

    def show_export_json_preview_result(self, request_id: int, data):
        if request_id == self.export_preview_request_id:
            self.export_preview.set_bytes(data or b"")

    def preview_path_for_json(self, path: Path) -> Path | None:
        path = Path(path)
        name = path.name
        preview_dir = path.parent.parent / "previews"
        match = re.match(r"^(.*)\.(\d+)v2\.json$", name)
        if match:
            base, step = match.groups()
            candidates = [
                preview_dir / f"{base}.preview.{step}v2.png",
                path.with_name(f"{base}.preview.{step}v2.png"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
        if name.endswith(".v2.json"):
            candidates = [
                preview_dir / f"{path.stem}.preview.png",
                path.with_name(f"{path.stem}.preview.png"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
        if ".v2.final." in name:
            match = re.match(r"^(.*)\.v2\.final\.(\d+)\.json$", name)
            if match:
                base, count = match.groups()
                candidates = [
                    preview_dir / f"{base}.v2.final.{count}.preview.png",
                    preview_dir / f"{base}.preview.{count}v2.png",
                    path.with_name(f"{base}.v2.final.{count}.preview.png"),
                    path.with_name(f"{base}.preview.{count}v2.png"),
                ]
                for candidate in candidates:
                    if candidate.exists():
                        return candidate
            candidate = path.with_name(f"{path.stem}.preview.png")
            return candidate if candidate.exists() else None
        match = re.match(r"^(.*)\.(\d+)\.json$", name)
        if match:
            base, step = match.groups()
            candidate = path.with_name(f"{base}.preview.{step}.png")
            return candidate if candidate.exists() else None
        candidate = path.with_name(f"{path.stem}.preview.png")
        return candidate if candidate.exists() else None

    def rendered_preview_cache_path(self, path: Path) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(Path(path).resolve()))
        return ROOT / "runtime" / "previews" / f"{safe_name}.png"

    def refresh_processes(self):
        self.processes = game_processes()
        combos = [self.pid_combo]
        if hasattr(self, "handmade_pid_combo"):
            combos.append(self.handmade_pid_combo)
        if hasattr(self, "export_pid_combo"):
            combos.append(self.export_pid_combo)
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
        if self.processes:
            for item in self.processes:
                for combo in combos:
                    combo.addItem(item["label"], item)
            self.game_combo.setCurrentText(self.processes[0]["profile"])
        else:
            for combo in combos:
                combo.addItem("No supported game process detected", None)
        for combo in combos:
            combo.blockSignals(False)

    def selected_pid_value(self, combo: QComboBox | None = None) -> int | None:
        combo = combo or self.pid_combo
        data = combo.currentData()
        if data and data.get("pid"):
            return int(data["pid"])
        raw = combo.currentText()
        match = re.search(r"pid\s+(\d+)", raw, re.I)
        if match:
            return int(match.group(1))
        try:
            return int(raw.strip())
        except ValueError:
            return None

    def start_generate(self):
        if not self.images:
            self.log_line("No image selected.")
            return
        setting = self.effective_setting()
        if not setting:
            self.log_line("No Kloudy preset selected.")
            return
        if not GENERATOR_EXE.exists():
            self.log_line(f"Missing generator: {GENERATOR_EXE}")
            return
        images = list(reversed(self.images))
        repair_enabled = self.repair_enabled.isChecked()
        self.shutdown_event.clear()
        self.stop_generation_event.clear()
        self.preview_request_id += 1
        self.active_generation_images = images
        self.set_status("Running")
        self.set_phase("building", "Starting internal build. Final import JSONs are not ready yet.")
        threading.Thread(target=self.generate_worker, args=(setting, images, repair_enabled), daemon=True).start()

    def stop_generate(self):
        if not self.active_generation_images:
            self.log_line("No active generation job to stop.")
            return
        self.stop_generation_event.set()
        for image_path in list(self.active_generation_images):
            try:
                stop_path = generator_stop_request_path(image_path, self.active_generation_run_dirs.get(image_path))
                stop_path.parent.mkdir(parents=True, exist_ok=True)
                stop_path.write_text("stop\n", encoding="utf-8")
            except Exception as exc:
                self.log_line(f"Failed to request stop for {image_path.name}: {exc}")
        self.set_status("Stopping")
        self.log_line("Stop requested. Finalize Checkpoints will finish the latest saved point.")

    def generate_worker(self, setting, images, repair_enabled):
        try:
            self.bus.log.emit(f"Selected Kloudy preset: {setting.get('label') or setting['path'].name}")
            self.bus.log.emit(f"Luma Prep: {setting.get('values', {}).get('v2PreprocessMode', 'none')}")
            self.bus.log.emit(f"Edge Repair: {'on' if repair_enabled else 'off'}")
            for image_path in images:
                run_dir = next_generator_output_dir(image_path)
                before = {path.resolve() for path in self.run_json_files(run_dir)}
                self.latest_generated_run_dir = run_dir
                self.active_generation_run_dirs[image_path] = run_dir
                self.bus.log.emit(f"Generating final vinyl from: {image_path}")
                self.bus.log.emit(f"Vinyl run folder: {run_dir}")
                src = render_source_image(image_path)
                if src:
                    self.bus.preview_bytes.emit(src)
                cmd = build_generator_command(image_path, setting, enable_repair=repair_enabled, enable_overshoot=False, output_dir=run_dir)
                self.bus.log.emit(f"Running patched vinyl builder with {setting['path'].name}")
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True, encoding="utf-8", errors="replace", creationflags=flags)
                self.register_process(proc)
                output_queue = queue.Queue()

                def reader():
                    try:
                        for raw_line in proc.stdout:
                            output_queue.put(raw_line)
                    finally:
                        output_queue.put(None)

                threading.Thread(target=reader, daemon=True).start()
                last_preview_mtime = None
                last_message = None
                while proc.poll() is None:
                    last_message = self.drain_generator_output(output_queue, last_message)
                    preview_files = self.run_preview_files(image_path, run_dir)
                    if preview_files:
                        newest = preview_files[0]
                        mtime = newest.stat().st_mtime
                        if mtime != last_preview_mtime:
                            last_preview_mtime = mtime
                            self.bus.preview_file.emit(str(newest))
                    time.sleep(0.1)
                self.unregister_process(proc)
                last_message = self.drain_generator_output(output_queue, last_message)
                if proc.returncode != 0:
                    self.bus.log.emit(f"Generator exited with code {proc.returncode}.")
                    self.bus.status.emit("Failed")
                    return
                after = self.run_json_files(run_dir)
                diff_outputs = [path for path in after if path.resolve() not in before]
                new_outputs = [path for path in diff_outputs if self.is_v2_output_json(path)] or diff_outputs
                if not new_outputs and after:
                    new_outputs = [path for path in after if self.is_v2_output_json(path)] or after[:1]
                for output in sorted(new_outputs, key=lambda path: path.stat().st_mtime, reverse=True):
                    if output not in self.outputs:
                        self.outputs.append(output)
                    self.bus.log.emit(f"Final vinyl ready: {output}")
                preview_files = self.run_preview_files(image_path, run_dir)
                if preview_files:
                    newest = preview_files[0]
                    mtime = newest.stat().st_mtime
                    if mtime != last_preview_mtime:
                        self.bus.preview_file.emit(str(newest))
                if self.stop_generation_event.is_set():
                    self.bus.log.emit(f"Stopped after finalizing {image_path.name}.")
                    break
            self.bus.refresh_lists.emit()
            self.bus.generated_changed.emit()
            self.bus.status.emit("Done")
        except Exception as exc:
            self.bus.log.emit(f"Generator failed: {exc}")
            self.bus.status.emit("Failed")
        finally:
            self.active_generation_images = []
            self.active_generation_run_dirs = {}

    def drain_generator_output(self, output_queue, last_message):
        while True:
            try:
                raw = output_queue.get_nowait()
            except queue.Empty:
                break
            if raw is None:
                continue
            friendly = self.friendly_generator_line(raw)
            if friendly and friendly != last_message:
                if friendly.startswith((
                    "Building layer ",
                    "Step ",
                    "Retry ",
                    "Internal build finished",
                    "INTERNAL BUILD COMPLETE",
                    "Finalize ",
                    "Finalizing ",
                    "FINALIZE CHECKPOINTS COMPLETE",
                )):
                    self.bus.progress.emit(friendly)
                self.bus.log.emit(friendly)
                last_message = friendly
        return last_message

    def friendly_generator_line(self, line):
        text = (line or "").strip()
        if not text:
            return None
        progress = re.match(r"\[(\d+)/(\d+)\]\s+(.*)", text)
        if progress:
            current, total, detail = progress.groups()
            if re.search(r"\bAdded\b.+#\d+", detail):
                return f"Building layer {current}/{total}"
            if "Saved geometry checkpoint" in detail:
                return f"Saved internal checkpoint {current}/{total}"
            if "Saved preview snapshot" in detail:
                return f"Updated preview {current}/{total}"
            step_done = re.match(r"Step completed in (\d+)ms", detail)
            if step_done:
                return f"Step {current}/{total} completed in {step_done.group(1)}ms"
            retrying = re.match(r"No improvement .* Retry (\d+)/(\d+)", detail)
            if retrying:
                return f"Retry {retrying.group(1)}/{retrying.group(2)} at layer {current}/{total}"
            return None
        if text == "FINISHED":
            return "Internal build finished. Finalize Checkpoints is still running; final import JSONs are not ready yet."
        important = (
            "Building internal base geometry",
            "Target template",
            "Target drawable",
            "Internal build stop:",
            "Using settings:",
            "Luma Prep mode:",
            "Preprocessed image:",
            "INTERNAL BUILD COMPLETE",
            "Finalized JSONs are",
            "Finalize Checkpoints:",
            "Finalize scoring ",
            "Finalizing import JSON ",
            "FINALIZE CHECKPOINTS COMPLETE",
            "Continuing Finalize Checkpoints",
            "Edge Repair:",
            "Final previews:",
            "Candidate ",
            "Best accuracy:",
            "Latest finalized checkpoint:",
            "Final JSON:",
            "Final preview:",
            "Selected final:",
            "Report:",
            "Loaded image:",
            "Settings:",
        )
        if text.startswith(important) or any(word in text.lower() for word in ("error", "failed", "traceback", "panic")):
            return text
        return None

    def run_preview_files(self, image_path, run_dir):
        image_path = Path(image_path)
        run_dir = Path(run_dir)
        candidates = []
        if run_dir.exists():
            candidates.extend(run_dir.glob(f"{image_path.stem}.preview*.png"))
            candidates.extend(run_dir.glob(f"{image_path.stem}.v2.final.*.preview.png"))
            candidates.extend(run_dir.glob("*.preview*.png"))
            preview_dir = run_dir / "previews"
            if preview_dir.exists():
                candidates.extend(preview_dir.glob(f"{image_path.stem}*.preview*.png"))
                candidates.extend(preview_dir.glob("*.preview*.png"))
                candidates.extend(preview_dir.glob("*.raw.preview.png"))
        filtered = [path for path in candidates if ".v2.preprocess." not in path.name]
        return sorted(set(filtered), key=lambda path: path.stat().st_mtime, reverse=True)

    def run_json_files(self, run_dir):
        run_dir = Path(run_dir)
        if not run_dir.exists():
            return []
        return sorted(
            {
                path
                for path in run_dir.rglob("*.json")
                if not is_internal_generator_json(path)
            },
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def register_process(self, proc):
        with self.process_lock:
            self.active_processes.add(proc)

    def unregister_process(self, proc):
        with self.process_lock:
            self.active_processes.discard(proc)

    def terminate_process(self, proc):
        try:
            proc.terminate()
        except Exception:
            pass

    def open_output_folder(self):
        folder = None
        if self.outputs:
            output = self.outputs[-1]
            folder = output.parent.parent if output.parent.name == "finals" else output.parent
        elif self.latest_generated_run_dir:
            folder = self.latest_generated_run_dir
        elif self.images:
            folder = self.images[-1].parent
        if folder and folder.exists():
            if os.name == "nt":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", str(folder)])

    def json_group_key(self, path):
        stem = Path(path).stem
        stem = re.sub(r"\.v2\.final\.\d+$", "", stem)
        stem = re.sub(r"\.\d+v2$", "", stem)
        stem = re.sub(r"\.v2$", "", stem)
        stem = re.sub(r"\.\d+$", "", stem)
        return stem

    def checkpoint_step_info(self, path):
        name = Path(path).name
        match = re.search(r"\.(\d+)v2\.json$", name)
        if match:
            return (int(match.group(1)), 1, f"{match.group(1)} layers")
        if name.endswith(".v2.json") or ".v2.final." in name:
            return (10**9, 1, "Finalized")
        match = re.search(r"\.(\d+)\.json$", name)
        if match:
            return (int(match.group(1)), 0, match.group(1))
        return (10**9, 0, "Final")

    def checkpoint_folder_label(self, path):
        try:
            return str(Path(path).parent.relative_to(ROOT))
        except Exception:
            return str(Path(path).parent)

    def checkpoint_run_folder(self, path):
        folder = Path(path).parent
        generated_root = ROOT / "imgs" / "generated"
        try:
            rel = folder.relative_to(generated_root)
            if rel.parts:
                return generated_root / rel.parts[0]
        except Exception:
            pass
        return folder

    def checkpoint_run_label(self, folder, prefix="Run"):
        folder = Path(folder)
        try:
            name = str(folder.relative_to(ROOT))
        except Exception:
            name = str(folder)
        try:
            stamp = datetime.fromtimestamp(folder.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            stamp = "unknown time"
        return f"{prefix}: {name} ({stamp})"

    def all_generated_final_jsons(self):
        candidates = set()
        if GENERATED_ROOT.exists():
            for path in GENERATED_ROOT.rglob("*.json"):
                if is_internal_generator_json(path):
                    continue
                if self.is_v2_output_json(path):
                    candidates.add(path.resolve())
        return candidates

    def is_v2_output_json(self, path):
        name = Path(path).name.lower()
        return bool(".v2.final." in name or re.search(r"\.\d+v2\.json$", name) or name.endswith(".v2.json"))

    def checkpoint_candidates(self):
        candidates = set(self.all_generated_final_jsons())
        candidates = sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)
        recommended = {path.resolve() for path in best_geometry_jsons(candidates)} if candidates else set()
        entries = []
        for path in candidates:
            try:
                count = geometry_shape_count(path)
            except Exception:
                count = 0
            step_number, step_variant, checkpoint_label = self.checkpoint_step_info(path)
            safe = is_import_safe_geometry_json(path)
            run_folder = self.checkpoint_run_folder(path)
            try:
                run_mtime = run_folder.stat().st_mtime
            except Exception:
                run_mtime = path.stat().st_mtime
            report = self.final_json_report_info(path)
            tags = []
            if safe and path.resolve() in recommended:
                tags.append("Best safe")
            if report.get("best_score"):
                tags.append("Best score")
            if report.get("latest_checkpoint"):
                tags.append("Latest")
            if report.get("repair_applied"):
                tags.append("Edge Repair")
            tags.append("Fits budget" if safe else "Over budget")
            entries.append({
                "path": path,
                "source": self.json_group_key(path),
                "folder": self.checkpoint_folder_label(path),
                "run_folder": run_folder,
                "run_key": str(run_folder.resolve()),
                "run_mtime": run_mtime,
                "checkpoint": checkpoint_label,
                "step_number": step_number,
                "step_variant": step_variant,
                "type": self.json_display_type(path),
                "layers": count,
                "import_safe": safe,
                "import_budget": import_drawable_budget(path),
                "recommended": safe and path.resolve() in recommended,
                "tags": tags,
                "error": report.get("error"),
                "preset": report.get("preset"),
                "source_image": report.get("source_image"),
            })
        safe_layers = [entry["layers"] for entry in entries if entry.get("import_safe") and entry.get("layers")]
        if safe_layers:
            lowest = min(safe_layers)
            for entry in entries:
                if entry.get("import_safe") and entry.get("layers") == lowest:
                    entry["tags"].append("Lowest layers")
        entries.sort(key=lambda item: (-item["run_mtime"], item["source"].lower(), item["step_number"], item["step_variant"], item["path"].name.lower()))
        return entries

    def final_json_report_info(self, path: Path) -> dict:
        info = {}
        report_path = generation_report_path(path)
        if not report_path.exists():
            return info
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return info
        resolved = str(Path(path).resolve())
        info["source_image"] = Path(str(report.get("source_image") or "")).name or None
        preset = (((report.get("settings") or {}).get("preset") or {}).get("label")
                  or ((report.get("settings") or {}).get("preset") or {}).get("name"))
        info["preset"] = preset

        def matches(item):
            try:
                return str(Path(str(item.get("v2_json"))).resolve()) == resolved
            except Exception:
                return False

        for candidate in report.get("candidates", []):
            if matches(candidate):
                info.update({
                    "error": candidate.get("error"),
                    "repair_applied": candidate.get("repair_applied"),
                })
                break
        for key, tag in (("best_accuracy", "best_score"), ("latest_checkpoint_v2", "latest_checkpoint")):
            item = report.get(key) or {}
            if matches(item):
                info[tag] = True
                info.setdefault("error", item.get("error"))
                info.setdefault("repair_applied", item.get("repair_applied"))
        return info

    def json_display_type(self, path):
        name = Path(path).name
        match = re.search(r"\.(\d+)v2\.json$", name)
        if match:
            return f"Finalized checkpoint {match.group(1)}"
        if name.endswith(".v2.json") or ".v2.final." in name:
            return "Final vinyl"
        match = re.search(r"\.(\d+)\.json$", name)
        if match:
            return f"Internal checkpoint {match.group(1)}"
        return "Final vinyl"

    def generated_folder_label(self, entry):
        return self.checkpoint_run_label(entry["run_folder"])

    def generated_display_label(self, entry):
        tags = " ".join(f"[{tag}]" for tag in entry.get("tags", []))
        unsafe = ""
        if not entry.get("import_safe", True):
            budget = entry.get("import_budget")
            unsafe = f" [over layer budget"
            if budget:
                unsafe += f" > {budget}"
            unsafe += "]"
        error = entry.get("error")
        error_text = f"{float(error):.3f}" if isinstance(error, (int, float)) else "n/a"
        preset = entry.get("preset") or "unknown preset"
        source = entry.get("source_image") or entry.get("source") or "unknown source"
        return (
            f"{tags}\n"
            f"{entry['type']} | {entry['layers']} layers | error {error_text}{unsafe}\n"
            f"Preset: {preset} | Source: {source}\n"
            f"{entry['path'].name}"
        )

    def sort_generated_entries_for_picker(self, entries):
        def rank(entry):
            if entry.get("recommended"):
                return (0, 0, entry["path"].name.lower())
            if entry["step_number"] == 10**9:
                return (1, 0, entry["path"].name.lower())
            return (2, -entry["step_number"], entry["step_variant"], entry["path"].name.lower())

        return sorted(entries, key=rank)

    def refresh_generated_browser(self):
        entries = self.checkpoint_candidates()
        run_groups = {}
        run_mtimes = {}
        run_folders = {}
        for entry in entries:
            run_key = entry["run_key"]
            run_groups.setdefault(run_key, []).append(entry)
            run_mtimes[run_key] = max(run_mtimes.get(run_key, 0), entry["run_mtime"])
            run_folders[run_key] = entry["run_folder"]
        run_order = sorted(run_groups, key=lambda key: run_mtimes.get(key, 0), reverse=True)
        groups = {}
        order = []
        for index, run_key in enumerate(run_order):
            prefix = "Latest run" if index == 0 else "Previous run"
            label = self.checkpoint_run_label(run_folders[run_key], prefix=prefix)
            groups[label] = self.sort_generated_entries_for_picker(run_groups[run_key])
            order.append(label)
        self.generated_folder_entries = groups
        self.generated_folder_combo.blockSignals(True)
        self.generated_folder_combo.clear()
        self.generated_folder_combo.addItems(order)
        if self.generated_folder_combo.count() > 0:
            self.generated_folder_combo.setCurrentIndex(0)
        self.generated_folder_combo.blockSignals(False)
        self.populate_generated_checkpoint_list(self.generated_folder_combo.currentText())

    def populate_generated_checkpoint_list(self, folder_label: str):
        self.generated_checkpoint_entries = list(self.generated_folder_entries.get(folder_label, []))
        self.generated_checkpoint_list.clear()
        if not self.generated_checkpoint_entries:
            self.generated_checkpoint_list.addItem("No finalized vinyl JSONs found yet.")
            return
        for entry in self.generated_checkpoint_entries:
            item = QListWidgetItem(self.generated_display_label(entry))
            item.setSizeHint(QSize(0, 92))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.generated_checkpoint_list.addItem(item)
        self.generated_checkpoint_list.setCurrentRow(0)

    def selected_generated_entry(self):
        item = self.generated_checkpoint_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def recommended_generated_entry(self):
        entries = [entry for group in self.generated_folder_entries.values() for entry in group if entry.get("recommended")]
        if not entries:
            return None
        return sorted(entries, key=lambda entry: (entry["run_mtime"], entry["path"].stat().st_mtime), reverse=True)[0]

    def select_generated_checkpoint(self, _row: int):
        entry = self.selected_generated_entry()
        if entry:
            self.select_generated_entry_for_import(entry)

    def select_generated_entry_for_import(self, entry):
        if not entry:
            return
        if not entry.get("import_safe", True):
            self.selected_import_json_path = None
            self.update_selected_json_label("Selected final JSON: none - highlighted file is over the layer budget and cannot be imported.")
            self.preview_json(entry["path"])
            self.log_line(f"Cannot import over-budget final JSON: {entry['path']} ({entry['layers']} layers > {entry.get('import_budget') or 'target budget'})")
            return
        self.select_import_json(entry["path"], "highlighted finalized checkpoint")

    def exported_game_json_candidates(self) -> list[dict]:
        entries = []
        if not UNIVERSAL_IMPORT_ROOT.exists():
            return entries
        for path in UNIVERSAL_IMPORT_ROOT.glob("export-current-group-*/*.json"):
            if path.name.endswith(".report.json"):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("format") != "fh6_typecode_json_export_v1":
                continue
            source = payload.get("source") or {}
            shape_count = len(payload.get("shapes") or [])
            report_path = path.with_suffix(".report.json")
            entries.append({
                "path": path,
                "run_folder": path.parent,
                "mtime": path.stat().st_mtime,
                "shape_count": shape_count,
                "layer_count": source.get("layer_count"),
                "table": source.get("table"),
                "group": source.get("group"),
                "report": report_path if report_path.exists() else None,
            })
        return sorted(entries, key=lambda entry: entry["mtime"], reverse=True)

    def exported_game_json_label(self, entry):
        timestamp = datetime.fromtimestamp(entry["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{entry['path'].name}\n"
            f"{entry['shape_count']} exported layers | source count {entry.get('layer_count') or 'unknown'} | {timestamp}\n"
            f"group={entry.get('group') or 'unknown'} table={entry.get('table') or 'unknown'}"
        )

    def refresh_game_export_browser(self):
        if not hasattr(self, "exported_game_json_list"):
            return
        self.exported_game_json_entries = self.exported_game_json_candidates()
        self.exported_game_json_list.clear()
        if not self.exported_game_json_entries:
            self.exported_game_json_list.addItem("No exported FH6 group JSONs found yet.")
            if hasattr(self, "export_preview"):
                self.export_preview.clear("Export a game group or select an exported JSON to preview it here.")
            return
        for entry in self.exported_game_json_entries:
            item = QListWidgetItem(self.exported_game_json_label(entry))
            item.setSizeHint(QSize(0, 86))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.exported_game_json_list.addItem(item)
        self.exported_game_json_list.setCurrentRow(0)

    def selected_exported_game_entry(self):
        if not hasattr(self, "exported_game_json_list"):
            return None
        item = self.exported_game_json_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_exported_game_json(self, _row: int):
        entry = self.selected_exported_game_entry()
        if not entry:
            return
        self.preview_export_json(entry["path"])
        self.log_line(f"Selected exported game JSON: {entry['path']}")

    def use_selected_export_for_handmade_import(self):
        entry = self.selected_exported_game_entry()
        if not entry:
            self.log_line("No exported game JSON selected.")
            return
        path = Path(entry["path"])
        self.selected_handmade_json_path = path
        text = f"Selected handmade JSON: {path.name}\nShapes: {entry.get('shape_count') or handmade_shape_count(path)}\n{path}"
        if hasattr(self, "handmade_json_label"):
            self.handmade_json_label.setText(text)
            self.handmade_json_label.setToolTip(str(path))
        self.log_line(f"Export selected for handmade import: {path}")

    def select_recommended_generated_json(self):
        entry = self.recommended_generated_entry()
        if not entry:
            self.log_line("No best safe final JSON found yet.")
            return
        for row, candidate in enumerate(self.generated_checkpoint_entries):
            if candidate["path"] == entry["path"]:
                self.generated_checkpoint_list.setCurrentRow(row)
                break
        self.select_import_json(entry["path"], "best safe final")

    def compare_selected_checkpoint(self):
        selected = self.selected_generated_entry()
        recommended = self.recommended_generated_entry()
        if not selected:
            QMessageBox.information(self, "Compare checkpoints", "Select a finalized checkpoint first.")
            return
        if not recommended:
            QMessageBox.information(self, "Compare checkpoints", "No best safe final JSON is available for comparison yet.")
            return
        if selected["path"] == recommended["path"]:
            alternatives = [entry for entry in self.generated_checkpoint_entries if entry["path"] != selected["path"]]
            if not alternatives:
                QMessageBox.information(self, "Compare checkpoints", "This run only has one finalized checkpoint.")
                return
            recommended = alternatives[0]

        dialog = QDialog(self)
        dialog.setWindowTitle("Compare Finalized Checkpoints")
        dialog.resize(1180, 720)
        layout = QGridLayout(dialog)
        for column, (title, entry) in enumerate((("Selected", selected), ("Compare", recommended))):
            label = QLabel(f"{title}\n{self.generated_display_label(entry)}")
            label.setWordWrap(True)
            preview = PreviewView("Preview unavailable.")
            preview_path = self.preview_path_for_json(entry["path"])
            if preview_path:
                preview.set_file(str(preview_path))
            else:
                data = render_geometry_preview(entry["path"])
                if data:
                    preview.set_bytes(data)
            layout.addWidget(label, 0, column)
            layout.addWidget(preview, 1, column)
        dialog.exec()

    def unfinished_generation_runs(self) -> list[Path]:
        if not GENERATED_ROOT.exists():
            return []
        runs = []
        for run_dir in GENERATED_ROOT.iterdir():
            if not run_dir.is_dir():
                continue
            checkpoints = list((run_dir / "checkpoints").glob("*.json"))
            finals = list((run_dir / "finals").glob("*.json"))
            if checkpoints and len(finals) < len(checkpoints):
                runs.append(run_dir)
        return sorted(runs, key=lambda path: path.stat().st_mtime, reverse=True)

    def start_resume_finalization(self):
        runs = self.unfinished_generation_runs()
        if not runs:
            QMessageBox.information(self, "Resume Finalize Checkpoints", "No unfinished checkpoint runs were found.")
            return
        run_dir = runs[0]
        self.set_status("Running")
        self.set_phase("finalizing", f"Resuming Finalize Checkpoints for {run_dir.name}. Do not close yet.")
        threading.Thread(target=self.resume_finalization_worker, args=(run_dir,), daemon=True).start()

    def resume_finalization_worker(self, run_dir: Path):
        try:
            cmd = self.build_resume_finalization_command(run_dir)
            if not cmd:
                self.bus.status.emit("Failed")
                return
            self.bus.log.emit(f"Resuming Finalize Checkpoints for: {run_dir}")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=flags)
            self.register_process(proc)
            try:
                for raw_line in proc.stdout:
                    friendly = self.friendly_generator_line(raw_line) or raw_line.strip()
                    if friendly:
                        if friendly.startswith(("Finalize ", "Finalizing ", "Edge Repair:", "Candidate ", "Best accuracy:", "Final JSON:", "FINALIZE CHECKPOINTS COMPLETE")):
                            self.bus.progress.emit(friendly)
                        self.bus.log.emit(friendly)
                code = proc.wait()
            finally:
                self.unregister_process(proc)
            if code == 0:
                self.bus.generated_changed.emit()
                self.bus.refresh_lists.emit()
                self.bus.status.emit("Done")
            else:
                self.bus.log.emit(f"Resume Finalize Checkpoints exited with code {code}.")
                self.bus.status.emit("Failed")
        except Exception as exc:
            self.bus.log.emit(f"Resume Finalize Checkpoints failed: {exc}")
            self.bus.status.emit("Failed")

    def build_resume_finalization_command(self, run_dir: Path) -> list | None:
        source = self.resume_source_image(run_dir)
        if source is None:
            self.bus.log.emit(f"Cannot resume {run_dir.name}: no copied source image found in the run folder.")
            return None
        metadata_path = next((run_dir / "reports").glob("*.v2.run_metadata.json"), None)
        metadata = {}
        if metadata_path:
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
        options = metadata.get("generator_command_options") or {}
        selected_profile = metadata.get("selected_profile") or {}
        values = metadata.get("effective_settings") or selected_profile.get("values") or {}
        settings_path = Path(str(selected_profile.get("path") or ""))
        if not settings_path.exists():
            settings_path = next((run_dir / "reports").glob("*.v2.settings.ini"), None)
        if not settings_path or not Path(settings_path).exists():
            self.bus.log.emit(f"Cannot resume {run_dir.name}: no settings file found.")
            return None
        target_shapes = str(options.get("target_shapes") or values.get("stopAt") or "3000")
        checkpoint_step = str(options.get("checkpoint_step") or "250")
        preprocess = str(options.get("preprocess_mode") or values.get("v2PreprocessMode") or "none")
        cmd = [
            helper_python(),
            ROOT / "forza_generator_v2.py",
            source,
            "--settings",
            settings_path,
            "--out-dir",
            run_dir,
            "--target-shapes",
            target_shapes,
            "--checkpoint-step",
            checkpoint_step,
            "--overshoot-ratio",
            str(options.get("overshoot_ratio") or "1.0"),
            "--overshoot-max-extra",
            str(options.get("overshoot_max_extra") or "0"),
            "--preprocess-mode",
            preprocess,
            "--finalize-only",
        ]
        if options.get("repair_enabled") or values.get("v2EnableRepair") in ("true", "1", True):
            cmd.append("--enable-repair")
        return cmd

    def resume_source_image(self, run_dir: Path) -> Path | None:
        suffixes = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        candidates = [
            path for path in run_dir.iterdir()
            if path.is_file() and path.suffix.lower() in suffixes and ".preview" not in path.name.lower()
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda path: path.stat().st_mtime)[0]

    def select_import_json(self, path: Path, source: str):
        self.selected_import_json_path = Path(path)
        self.update_selected_json_label()
        self.preview_json(self.selected_import_json_path)
        self.log_line(f"Selected {source}: {self.selected_import_json_path}")

    def update_selected_json_label(self, text: str | None = None):
        if not hasattr(self, "selected_json_label"):
            return
        if text is not None:
            self.selected_json_label.setText(text)
            self.selected_json_label.setToolTip(text)
        elif self.selected_import_json_path:
            path = Path(self.selected_import_json_path)
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            self.selected_json_label.setText(f"Selected final JSON: {path.name}")
            self.selected_json_label.setToolTip(str(path))
        else:
            self.selected_json_label.setText("Selected final JSON: none")
            self.selected_json_label.setToolTip("")

    def run_subprocess(self, cmd, timeout=None):
        self.bus.log.emit(self.friendly_command_name(cmd))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        env = os.environ.copy()
        env.update({"FORZA_PAINTER_NO_ELEVATE": "1", "FORZA_PAINTER_NO_PAUSE": "1"})
        proc = subprocess.Popen([str(x) for x in cmd], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=flags, env=env)
        self.register_process(proc)
        started = time.time()
        try:
            while True:
                line = proc.stdout.readline()
                if line:
                    friendly = self.friendly_subprocess_line(line.rstrip())
                    if friendly:
                        self.bus.log.emit(friendly)
                if proc.poll() is not None:
                    break
                if timeout and time.time() - started > timeout:
                    self.terminate_process(proc)
                    self.bus.log.emit(f"Timed out after {timeout} seconds.")
                    return 124
                time.sleep(0.05)
            for line in proc.stdout.read().splitlines():
                friendly = self.friendly_subprocess_line(line.rstrip())
                if friendly:
                    self.bus.log.emit(friendly)
            return proc.returncode
        finally:
            self.unregister_process(proc)

    def friendly_command_name(self, cmd):
        joined = " ".join(str(x) for x in cmd)
        if "fh6_probe.py" in joined and "--auto-locate" in joined:
            return "Finding current FH6 template..."
        if "fh6_group1000_probe.py" in joined:
            return "Locating loaded FH6 handmade-import template..."
        if "fh6_import_typecode_json.py" in joined:
            return "Importing handmade JSON into FH6..."
        if "fh6_export_typecode_json.py" in joined:
            return "Exporting current FH6 group to handmade JSON..."
        if "fh6_trim_group_count.py" in joined:
            return "Trimming FH6 handmade-import layer count..."
        if "main.py" in joined:
            return "Importing JSON into FH6..."
        return "Starting helper..."

    def friendly_subprocess_line(self, line):
        raw = (line or "").strip()
        if not raw:
            return None
        lower = raw.lower()
        if any(part in lower for part in ("base:", "candidate score=", "layout candidate", "table[", "ptr=0x", "descriptor @")):
            return None
        if raw.startswith("<class 'SystemExit'>") or raw.startswith("SystemExit: 0"):
            return None
        if "fast fh6 layer group candidates:" in lower or "cliverylayer table found" in lower:
            return "FH6 template located and verified."
        if "auto-locating fh6" in lower:
            return "Finding current FH6 template..."
        if "forza horizon 6 detected" in lower:
            return raw
        if raw.startswith("Dumped layer "):
            return raw
        if "no safe fh6 layer group" in lower:
            return raw
        if raw.startswith("Writing layer") or raw == "DONE!" or raw.startswith("The ideal background color"):
            return raw
        if "openprocess" in lower or "error" in lower or "failed" in lower or "traceback" in lower:
            return raw
        return raw

    def start_auto_locate(self):
        pid = self.selected_pid_value()
        layer_count = self.layer_count.text().strip()
        game = self.game_combo.currentText() or "fh6"
        if not pid or not layer_count:
            self.log_line("PID and template layer count are required.")
            return
        self.set_status("Running")
        threading.Thread(target=self.auto_locate_worker, args=(pid, layer_count, game), daemon=True).start()

    def auto_locate_worker(self, pid, layer_count, game, update_status=True):
        cmd = [
            helper_python(),
            ROOT / "fh6_probe.py",
            "--game",
            game,
            "--pid",
            str(pid),
            "--layer-count",
            str(layer_count),
            "--auto-locate",
            "--write-session",
            SESSION_PATH,
            "--dump-slot-radius",
            "16",
            "--limit-mb",
            str(MEMORY_SNAPSHOT_LIMIT_MB),
            "--max-matches",
            "500000",
            "--inspect-radius",
            "0x800",
            "--max-seconds",
            "90",
        ]
        code = self.run_subprocess(cmd, timeout=220)
        if code == 0:
            session = load_session_location()
            if session and str(session.get("layer_count", "")) == str(layer_count):
                self.bus.auto_located.emit(
                    "0x{:x}".format(int(session["count_address"])),
                    "0x{:x}".format(int(session["table_address"])),
                    str(layer_count),
                    str(pid),
                    game,
                )
        if update_status:
            self.bus.status.emit("Done" if code == 0 else "Failed")

    def apply_auto_locate_result(self, count_address, table_address, layer_count, pid, game):
        self.auto_located_context = {
            "count_address": count_address,
            "table_address": table_address,
            "layer_count": str(layer_count),
            "pid": str(pid),
            "game": str(game),
        }
        self.log_line(f"Auto-located FH6 count/table: count={count_address}, table={table_address}")

    def auto_located_context_matches(self, count_address, table_address, layer_count, pid, game):
        context = self.auto_located_context
        return bool(
            context
            and context.get("count_address") == count_address
            and context.get("table_address") == table_address
            and context.get("layer_count") == str(layer_count)
            and context.get("pid") == str(pid)
            and context.get("game") == str(game)
        )

    def start_import(self):
        if not self.selected_import_json_path:
            self.log_line("No finalized JSON selected.")
            return
        pid = self.selected_pid_value()
        game = self.game_combo.currentText() or "fh6"
        layer_count = self.layer_count.text().strip()
        count_address = None
        table_address = None
        if game == "fh6":
            if not pid:
                self.log_line("Select or refresh the FH6 process before importing.")
                return
            if not layer_count:
                self.log_line("Template layer count is required for FH6 import.")
                return
            context = self.auto_located_context or {}
            if self.auto_located_context_matches(context.get("count_address"), context.get("table_address"), layer_count, pid, game):
                count_address = context.get("count_address")
                table_address = context.get("table_address")
        json_path = self.selected_import_json_path
        mask_mode, mask_budget = self.selected_import_mask_options()
        self.set_status("Importing")
        threading.Thread(
            target=self.import_worker,
            args=(pid, game, count_address, table_address, layer_count, json_path, mask_mode, mask_budget),
            daemon=True,
        ).start()

    def selected_import_mask_options(self):
        if bool(self.app_settings.get("legacy_border_masks", False)):
            return "full", 4
        return "off", 0

    def check_json_layer_fit(self, json_path, layer_count, mask_budget=4):
        try:
            json_layers = geometry_shape_count(json_path)
            template_layers = int(layer_count)
        except Exception:
            return
        usable_layers = max(0, template_layers - int(mask_budget))
        if json_layers and template_layers and json_layers > usable_layers:
            self.bus.log.emit(f"FH mask budget reserves {mask_budget} layers. JSON={json_layers}, template={template_layers}, usable={usable_layers}")
        if json_layers and usable_layers and json_layers < usable_layers * 0.75:
            self.bus.log.emit(f"Selected JSON has far fewer drawable layers than usable capacity. JSON={json_layers}, usable={usable_layers}")

    def import_worker(self, pid, game, count_address, table_address, layer_count, json_path, mask_mode="full", mask_budget=4):
        if not count_address and not table_address and game == "fh6":
            if pid and layer_count:
                self.bus.log.emit("Finding current FH6 template...")
                self.auto_locate_worker(pid, layer_count, game, update_status=False)
                session = load_session_location()
                if session and str(session.get("layer_count", "")) == str(layer_count) and session_pid_is_live(session, game):
                    count_address = "0x{:x}".format(int(session["count_address"]))
                    table_address = "0x{:x}".format(int(session["table_address"]))
                    self.bus.log.emit("FH6 template located and verified.")
                else:
                    self.bus.status.emit("Failed")
                    return
            else:
                self.bus.log.emit("FH6 import requires a selected process and template layer count.")
                self.bus.status.emit("Failed")
                return
        path = Path(json_path)
        if game == "fh6" and layer_count:
            self.check_json_layer_fit(path, layer_count, mask_budget)
        cmd = [helper_python(), ROOT / "main.py", "--game", game, "--no-preview"]
        if pid:
            cmd.extend(["--pid", str(pid)])
        if count_address:
            cmd.extend(["--layer-count-address", count_address])
        if table_address:
            cmd.extend(["--layer-table-address", table_address])
        if game == "fh6" and layer_count:
            cmd.extend(["--layer-count-value", str(layer_count)])
            cmd.extend(["--fh-boundary-mask-mode", str(mask_mode), "--fh-boundary-mask-budget", str(mask_budget)])
        cmd.append(path)
        code = self.run_subprocess(cmd)
        if code != 0:
            self.bus.status.emit("Failed")
            return
        self.bus.status.emit("Done")

    def start_handmade_import(self):
        if not self.selected_handmade_json_path:
            self.log_line("No handmade JSON selected.")
            return
        pid = self.selected_pid_value(self.handmade_pid_combo)
        if not pid:
            self.log_line("Select or refresh the FH6 process before handmade import.")
            return
        try:
            template_count = int(self.handmade_template_count.text().strip())
        except ValueError:
            self.log_line("Loaded template layer count must be a number.")
            return
        if template_count <= 0:
            self.log_line("Loaded template layer count must be greater than zero.")
            return
        try:
            shape_count = handmade_shape_count(self.selected_handmade_json_path)
        except Exception as exc:
            self.log_line(f"Handmade JSON is invalid: {exc}")
            return
        if shape_count <= 0:
            self.log_line("Handmade JSON has no shapes.")
            return
        if shape_count > template_count:
            self.log_line(f"Handmade JSON has too many shapes for the loaded template. JSON={shape_count}, template={template_count}")
            return
        self.set_status("Importing")
        self.set_phase("importing", "Importing handmade JSON into FH6, then trimming unused template layers.")
        threading.Thread(
            target=self.handmade_import_worker,
            args=(
                pid,
                template_count,
                shape_count,
                Path(self.selected_handmade_json_path),
                self.handmade_clear_unused.isChecked(),
            ),
            daemon=True,
        ).start()

    def locate_universal_template(self, pid, template_count, run_dir, purpose="template"):
        session_report = run_dir / f"fast-{purpose}-session.json"
        probe_report = run_dir / f"fallback-{purpose}-probe.json"
        self.bus.log.emit(f"Fast-locating loaded FH6 group with {template_count} layers...")
        fast_cmd = [
            helper_python(),
            ROOT / "fh6_probe.py",
            "--game",
            "fh6",
            "--pid",
            str(pid),
            "--layer-count",
            str(template_count),
            "--auto-locate",
            "--write-session",
            session_report,
            "--dump-slot-radius",
            "16",
            "--limit-mb",
            str(MEMORY_SNAPSHOT_LIMIT_MB),
            "--max-matches",
            "500000",
            "--inspect-radius",
            "0x800",
            "--max-seconds",
            "45",
        ]
        group = None
        table = None
        code = self.run_subprocess(fast_cmd, timeout=90)
        if code == 0 and session_report.exists():
            session = json.loads(session_report.read_text(encoding="utf-8"))
            if str(session.get("layer_count", "")) == str(template_count):
                table_value = session.get("table_address")
                count_value = session.get("count_address")
                group_value = session.get("group_address")
                if table_value and (group_value or count_value):
                    table = f"0x{int(table_value):x}" if isinstance(table_value, int) else str(table_value)
                    if group_value:
                        group = f"0x{int(group_value):x}" if isinstance(group_value, int) else str(group_value)
                    else:
                        group = f"0x{int(count_value) - 0x5A:x}" if isinstance(count_value, int) else f"0x{int(str(count_value), 0) - 0x5A:x}"
                    self.bus.log.emit(f"FH6 group fast-located: group={group}, table={table}, layers={template_count}")
        if group and table:
            return group, table

        self.bus.log.emit("Fast locate did not produce a usable group/table. Falling back to research scanner.")
        probe_cmd = [
            helper_python(),
            ROOT / "fh6_group1000_probe.py",
            "--pid",
            str(pid),
            "--count",
            str(template_count),
            "--max-seconds",
            "90",
            "--report-layers",
            "40",
            "--out-dir",
            run_dir,
        ]
        code = self.run_subprocess(probe_cmd, timeout=140)
        if code != 0:
            raise RuntimeError("template probe did not complete")
        probe_files = sorted(run_dir.glob(f"fh6-group{template_count}-probe-*.json"), key=lambda path: path.stat().st_mtime)
        if not probe_files:
            raise RuntimeError("template probe report was not created")
        probe_files[-1].replace(probe_report)
        probe = json.loads(probe_report.read_text(encoding="utf-8"))
        candidates = probe.get("candidates") or []
        if not candidates:
            raise RuntimeError("no matching loaded FH6 group was found")
        best = candidates[0]
        group = best.get("group")
        table = best.get("table")
        valid_ptrs = int(best.get("valid_ptrs") or 0)
        sample_ok = int(best.get("sample_ok_count") or 0)
        if not group or not table or valid_ptrs < template_count or sample_ok < min(8, template_count):
            raise RuntimeError(f"located group did not validate strongly enough (valid_ptrs={valid_ptrs}, sample_ok={sample_ok})")
        self.bus.log.emit(f"FH6 group fallback-located: group={group}, table={table}, layers={template_count}")
        return group, table

    def handmade_import_worker(self, pid, template_count, shape_count, json_path, clear_unused=True):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = UNIVERSAL_IMPORT_ROOT / f"{json_path.stem}-{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        import_backup = run_dir / "import-backup.json"
        import_report = run_dir / "import-report.json"
        trim_backup = run_dir / "trim-backup.json"
        try:
            self.bus.log.emit(f"Universal import run folder: {run_dir}")
            self.bus.log.emit(f"Handmade JSON shapes: {shape_count}")
            group, table = self.locate_universal_template(pid, template_count, run_dir, purpose="import-template")
            import_cmd = [
                helper_python(),
                ROOT / "fh6_import_typecode_json.py",
                "--pid",
                str(pid),
                "--table",
                str(table),
                "--json",
                json_path,
                "--template-count",
                str(template_count),
                "--compact-supported-layers",
                "--allow-unknown-low-byte",
                "--backup",
                import_backup,
                "--report",
                import_report,
                "--write",
            ]
            if clear_unused:
                import_cmd.append("--clear-unused")
            self.bus.log.emit("Writing handmade shapes into FH6...")
            code = self.run_subprocess(import_cmd, timeout=240)
            if code != 0:
                self.bus.log.emit("Universal import failed while writing layers.")
                self.bus.status.emit("Failed")
                return
            report = json.loads(import_report.read_text(encoding="utf-8"))
            imported = int(report.get("imported_layer_count") or 0)
            failures = int(report.get("failure_count") or 0)
            unsupported = int(report.get("unsupported_shape_count") or 0)
            if failures:
                self.bus.log.emit(f"Universal import wrote with failures: imported={imported}, failures={failures}, unsupported={unsupported}")
                self.bus.status.emit("Failed")
                return
            if imported <= 0:
                self.bus.log.emit("Universal import failed: no layers were imported.")
                self.bus.status.emit("Failed")
                return
            self.bus.log.emit(f"Imported {imported} handmade shape layers. Trimming FH6 group count...")
            trim_cmd = [
                helper_python(),
                ROOT / "fh6_trim_group_count.py",
                "--pid",
                str(pid),
                "--group",
                str(group),
                "--table",
                str(table),
                "--new-count",
                str(imported),
                "--trim-vector-end",
                "--backup",
                trim_backup,
                "--write",
            ]
            code = self.run_subprocess(trim_cmd, timeout=60)
            if code != 0:
                self.bus.log.emit("Universal import wrote layers but failed while trimming layer count.")
                self.bus.status.emit("Failed")
                return
            self.bus.log.emit(f"Universal import complete: {imported} layers. Save and reload the vinyl group to verify.")
            self.bus.status.emit("Done")
            self.bus.phase.emit("done", "Handmade JSON imported and layer count trimmed. Save/reload in FH6 to verify.")
        except Exception as exc:
            self.bus.log.emit(f"Universal import failed: {exc}")
            self.bus.status.emit("Failed")

    def start_game_export(self):
        pid = self.selected_pid_value(self.export_pid_combo)
        if not pid:
            self.log_line("Select or refresh the FH6 process before export.")
            return
        try:
            template_count = int(self.export_template_count.text().strip())
        except ValueError:
            self.log_line("Loaded template layer count must be a number.")
            return
        if template_count <= 0:
            self.log_line("Loaded template layer count must be greater than zero.")
            return
        self.set_status("Exporting")
        self.set_phase("importing", "Exporting current FH6 group into handmade-compatible JSON.")
        threading.Thread(
            target=self.handmade_export_worker,
            args=(pid, template_count),
            daemon=True,
        ).start()

    def handmade_export_worker(self, pid, template_count):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = UNIVERSAL_IMPORT_ROOT / f"export-current-group-{template_count}-{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        export_json = run_dir / f"fh6-current-group-{template_count}-{timestamp}.json"
        export_report = run_dir / f"fh6-current-group-{template_count}-{timestamp}.report.json"
        try:
            self.bus.log.emit(f"Universal export run folder: {run_dir}")
            group, table = self.locate_universal_template(pid, template_count, run_dir, purpose="export-template")
            export_cmd = [
                helper_python(),
                ROOT / "fh6_export_typecode_json.py",
                "--pid",
                str(pid),
                "--group",
                str(group),
                "--table",
                str(table),
                "--count",
                str(template_count),
                "--out",
                export_json,
                "--report",
                export_report,
            ]
            self.bus.log.emit("Reading current FH6 group into handmade JSON...")
            code = self.run_subprocess(export_cmd, timeout=240)
            if code != 0:
                self.bus.log.emit("Universal export failed while reading layers.")
                self.bus.status.emit("Failed")
                return
            report = json.loads(export_report.read_text(encoding="utf-8"))
            exported = int(report.get("exported_shape_count") or 0)
            failures = int(report.get("failure_count") or 0)
            self.selected_handmade_json_path = export_json
            self.bus.log.emit(f"Universal export complete: {exported} layers -> {export_json}")
            if failures:
                self.bus.log.emit(f"Export warning: {failures} unreadable layer(s), see report.")
            self.bus.status.emit("Done")
            self.bus.phase.emit("done", "Current FH6 group exported to handmade-compatible JSON.")
            self.bus.ui_call.emit(self.refresh_game_export_browser)
            self.bus.ui_call.emit(lambda: self.select_exported_path_after_refresh(export_json))
        except Exception as exc:
            self.bus.log.emit(f"Universal export failed: {exc}")
            self.bus.status.emit("Failed")

    def select_exported_path_after_refresh(self, path: Path):
        if not hasattr(self, "exported_game_json_list"):
            return
        for row, entry in enumerate(self.exported_game_json_entries):
            if Path(entry["path"]) == Path(path):
                self.exported_game_json_list.setCurrentRow(row)
                break

    def start_diagnose(self):
        cmd = [helper_python(), ROOT / "main.py", "--game", self.game_combo.currentText() or "fh6", "--diagnose"]
        pid = self.selected_pid_value()
        if pid:
            cmd.extend(["--pid", str(pid)])
        self.set_status("Running")
        threading.Thread(target=lambda: self.command_worker(cmd, 120), daemon=True).start()

    def start_save_snapshot(self):
        pid = self.selected_pid_value()
        count = self.snapshot_count.text().strip() or self.layer_count.text().strip()
        if not pid or not count:
            self.log_line("PID and snapshot layer count are required.")
            return
        output_path = PROBE_DIR / f"memory-count-{count}.jsonl"
        cmd = [helper_python(), ROOT / "fh6_probe.py", "--game", self.game_combo.currentText() or "fh6", "--pid", str(pid), "--layer-count", str(count), "--save-memory-snapshot", output_path, "--limit-mb", str(MEMORY_SNAPSHOT_LIMIT_MB)]
        self.set_status("Running")
        threading.Thread(target=lambda: self.command_worker(cmd, 360), daemon=True).start()

    def start_compare_snapshot(self):
        pid = self.selected_pid_value()
        previous = self.snapshot_count.text().strip()
        current = self.current_count.text().strip() or self.layer_count.text().strip()
        if not pid or not previous or not current:
            self.log_line("PID, snapshot layer count, and current layer count are required.")
            return
        snapshot_path = PROBE_DIR / f"memory-count-{previous}.jsonl"
        candidates_path = PROBE_DIR / f"memory-count-{previous}-to-{current}-candidates.json"
        cmd = [helper_python(), ROOT / "fh6_probe.py", "--game", self.game_combo.currentText() or "fh6", "--pid", str(pid), "--layer-count", str(current), "--compare-memory-snapshot", snapshot_path, "--write-candidates", candidates_path, "--max-matches", "50000"]
        self.set_status("Running")
        threading.Thread(target=lambda: self.command_worker(cmd, 360), daemon=True).start()

    def start_inspect_table(self):
        pid = self.selected_pid_value()
        table = self.inspect_table.text().strip()
        count = self.layer_count.text().strip()
        if not pid or not table or not count:
            self.log_line("PID, layer count, and table address are required.")
            return
        cmd = [helper_python(), ROOT / "fh6_probe.py", "--game", self.game_combo.currentText() or "fh6", "--pid", str(pid), "--layer-count", str(count), "--inspect-table", table, "--inspect-layers", "12"]
        self.set_status("Running")
        threading.Thread(target=lambda: self.command_worker(cmd, 60), daemon=True).start()

    def command_worker(self, cmd, timeout):
        code = self.run_subprocess(cmd, timeout=timeout)
        self.bus.status.emit("Done" if code == 0 else "Failed")

    def closeEvent(self, event):
        self.shutdown_event.set()
        with self.process_lock:
            processes = list(self.active_processes)
        for proc in processes:
            self.terminate_process(proc)
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    try:
        require_project_presence()
        parser = argparse.ArgumentParser(description="Kloudy's FH6 Painter PySide6 app.")
        parser.add_argument("images", nargs="*", help="Optional image files to preload.")
        args = parser.parse_args(argv)
        window = MainWindow(args.images)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Kloudy's FH6 Painter",
            f"{exc}\n\nIf this mentions a missing module, run 02_install_dependencies.bat and start the app again.",
        )
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
