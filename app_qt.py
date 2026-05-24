from __future__ import annotations

import argparse
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
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
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
    generator_stop_request_path,
    geometry_shape_count,
    import_drawable_budget,
    is_import_safe_geometry_json,
    is_internal_generator_json,
    load_settings,
    next_generator_output_dir,
    write_custom_settings,
)
from geometry_json import ELLIPSE, RECTANGLE, ROTATED_ELLIPSE, ROTATED_RECTANGLE, load_normalized_geometry
from version_info import get_version


ROOT = Path(__file__).resolve().parent
EMBEDDED_PYTHON = ROOT / "python" / "python.exe"
PROBE_DIR = ROOT / "webui-data" / "probes"
APP_SETTINGS_PATH = ROOT / "runtime" / "app_settings.json"
SESSION_PATH = PROBE_DIR / "current-fh6-session.json"
PREVIEW_MAX = 1200
MEMORY_SNAPSHOT_LIMIT_MB = 2048
PUBERT_PRESENCE_ASSET = ROOT / "assets" / "a" / "b" / "c" / "d" / "e" / "f" / "pubert.jpg"
THEMES = {
    "Pastel Bloom": "pastel",
    "Sakura Glass": "sakura",
    "Blackout": "blackout",
}


def helper_python() -> Path | str:
    return EMBEDDED_PYTHON if EMBEDDED_PYTHON.exists() else sys.executable


TEXT = {
    "tutorial": """Beginner workflow

1. Run 01_add_python312_to_path.bat, then 02_install_dependencies.bat.
2. Open Generate JSON, choose one image, pick a profile, then generate.
3. Keep Luma Bands and Targeted Repair enabled unless the source looks better without them.
4. Open FH6 Vinyl Group Editor, load a simple-layer template, then ungroup it.
5. Open Import, refresh the FH6 process, enter the exact template layer count, add/select a JSON, then import.

FH6 keeps 4 boundary layers. A 2000-layer template has 1996 usable drawable layers.
""",
}


def ensure_dirs() -> None:
    for path in (ROOT / "runtime", ROOT / "runtime" / "previews", ROOT / "runtime" / "custom-settings", PROBE_DIR):
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


def require_pubert_presence() -> None:
    # Remove this function call and constant to disable the launch presence check.
    if not PUBERT_PRESENCE_ASSET.is_file():
        raise RuntimeError("pubert not present")


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


def render_geometry_json(path: Path, max_size: int = PREVIEW_MAX) -> bytes | None:
    loaded = load_cv2()
    if not loaded:
        return None
    cv2, np = loaded
    try:
        data = load_normalized_geometry(path)
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
    preview_bytes = Signal(bytes)
    preview_file = Signal(str)
    json_preview = Signal(int, object)
    refresh_lists = Signal()
    generated_changed = Signal()
    auto_located = Signal(str, str, str, str, str)


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
        self.theme_key = "pastel"
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
        self.preview_request_id = 0
        self.bus = UiBus()
        self.bus.log.connect(self.log_line)
        self.bus.status.connect(self.set_status)
        self.bus.progress.connect(self.set_progress)
        self.bus.preview_bytes.connect(self.show_preview_bytes)
        self.bus.preview_file.connect(self.show_preview_file)
        self.bus.json_preview.connect(self.show_json_preview_result)
        self.bus.refresh_lists.connect(self.render_lists)
        self.bus.generated_changed.connect(self.refresh_generated_browser)
        self.bus.auto_located.connect(self.apply_auto_locate_result)
        self._build()
        self.apply_theme()
        self.refresh_processes()
        self.refresh_generated_browser()
        self.render_lists()
        if self.images:
            self.show_preview_bytes(render_source_image(self.images[0]) or b"")

    def _build(self):
        central = AnimatedThemeBackground()
        central.setObjectName("appRoot")
        self.background_widget = central
        root = QVBoxLayout(central)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_generate_tab()
        self._build_import_tab()
        self._build_tools_tab()
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

        image_group = QGroupBox("Step 1 - Choose Image")
        image_layout = QVBoxLayout(image_group)
        image_row = QHBoxLayout()
        choose = QPushButton("Choose image")
        choose.clicked.connect(self.add_image)
        image_row.addWidget(choose)
        open_out = QPushButton("Open output folder")
        open_out.clicked.connect(self.open_output_folder)
        image_row.addWidget(open_out)
        image_layout.addLayout(image_row)
        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self.preview_selected_image)
        image_layout.addWidget(self.image_list)
        left_layout.addWidget(image_group)

        quality_group = QGroupBox("Step 2 - Choose Quality")
        quality_layout = QVBoxLayout(quality_group)
        self.vroom = QCheckBox("vroom vroom scrrrrt zoooom!")
        self.vroom.stateChanged.connect(self.update_setting_description)
        quality_layout.addWidget(self.vroom)
        self.profile_combo = QComboBox()
        self.profile_combo.setMaxVisibleItems(18)
        for item in self.settings:
            self.profile_combo.addItem(item["label"], item)
        self.profile_combo.currentIndexChanged.connect(self.update_setting_description)
        quality_layout.addWidget(self.profile_combo)
        self.setting_description = QLabel("")
        self.setting_description.setWordWrap(True)
        quality_layout.addWidget(self.setting_description)
        self.custom_enabled = QCheckBox("Use custom settings")
        self.custom_enabled.stateChanged.connect(self.sync_custom_state)
        quality_layout.addWidget(self.custom_enabled)
        form = QGridLayout()
        self.custom_layers = QLineEdit()
        self.custom_resolution = QLineEdit()
        self.custom_random = QLineEdit()
        self.custom_mutated = QLineEdit()
        self.custom_save_at = QLineEdit()
        fields = [
            ("Output layers", self.custom_layers),
            ("Max resolution", self.custom_resolution),
            ("Random samples", self.custom_random),
            ("Mutated samples", self.custom_mutated),
            ("Save checkpoints", self.custom_save_at),
        ]
        for row, (label, widget) in enumerate(fields):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)
        quality_layout.addLayout(form)
        self.luma_enabled = QCheckBox("Enable Luma Bands preprocess")
        self.luma_enabled.setChecked(True)
        quality_layout.addWidget(self.luma_enabled)
        self.repair_enabled = QCheckBox("Use targeted repair (recommended)")
        self.repair_enabled.setChecked(True)
        quality_layout.addWidget(self.repair_enabled)
        left_layout.addWidget(quality_group)

        run_group = QGroupBox("Step 3 - Generate")
        run_layout = QHBoxLayout(run_group)
        generate = QPushButton("Generate with current settings")
        generate.setObjectName("primaryButton")
        generate.clicked.connect(self.start_generate)
        stop = QPushButton("Stop after latest checkpoint")
        stop.clicked.connect(self.stop_generate)
        run_layout.addWidget(generate, 2)
        run_layout.addWidget(stop, 1)
        left_layout.addWidget(run_group)
        left_layout.addStretch()

        right_layout.addWidget(QLabel("Preview"))
        self.preview = PreviewView("Select an image or JSON to preview it here.")
        right_layout.addWidget(self.preview, 1)
        self.tabs.addTab(tab, "Generate JSON")
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

        game = QGroupBox("Step 1 - Game")
        game_layout = QGridLayout(game)
        self.game_combo = QComboBox()
        self.game_combo.addItems(list(PROFILES.keys()))
        self.pid_combo = QComboBox()
        self.pid_combo.setEditable(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_processes)
        game_layout.addWidget(QLabel("Game profile"), 0, 0)
        game_layout.addWidget(self.game_combo, 0, 1)
        game_layout.addWidget(QLabel("Process"), 1, 0)
        game_layout.addWidget(self.pid_combo, 1, 1)
        game_layout.addWidget(refresh, 1, 2)
        left_layout.addWidget(game)

        template = QGroupBox("Step 2 - Template")
        template_layout = QGridLayout(template)
        self.layer_count = QLineEdit()
        template_layout.addWidget(QLabel("Template layer count"), 0, 0)
        template_layout.addWidget(self.layer_count, 0, 1)
        left_layout.addWidget(template)

        json_group = QGroupBox("Step 3 - JSON")
        json_layout = QVBoxLayout(json_group)
        controls = QHBoxLayout()
        add_json = QPushButton("Choose JSON...")
        add_json.clicked.connect(self.manual_add_json)
        refresh_jsons = QPushButton("Refresh")
        refresh_jsons.clicked.connect(self.refresh_generated_browser)
        add_recommended = QPushButton("Use recommended")
        add_recommended.clicked.connect(self.select_recommended_generated_json)
        controls.addWidget(add_json)
        controls.addWidget(refresh_jsons)
        controls.addWidget(add_recommended)
        json_layout.addLayout(controls)
        self.generated_folder_combo = QComboBox()
        self.generated_folder_combo.setMaxVisibleItems(24)
        self.generated_folder_combo.setMinimumHeight(34)
        self.generated_folder_combo.currentTextChanged.connect(self.populate_generated_checkpoint_list)
        json_layout.addWidget(QLabel("Generated run"))
        json_layout.addWidget(QLabel("Click a checkpoint below. The highlighted JSON is the one that will be imported."))
        json_layout.addWidget(self.generated_folder_combo)
        self.generated_checkpoint_list = QListWidget()
        self.generated_checkpoint_list.setMinimumHeight(420)
        self.generated_checkpoint_list.currentRowChanged.connect(self.select_generated_checkpoint)
        json_layout.addWidget(QLabel("Checkpoints"))
        json_layout.addWidget(self.generated_checkpoint_list, 2)
        self.selected_json_label = QLabel("Selected import JSON: none")
        self.selected_json_label.setWordWrap(True)
        json_layout.addWidget(self.selected_json_label)
        left_layout.addWidget(json_group, 1)

        import_group = QGroupBox("Step 4 - Import")
        import_layout = QVBoxLayout(import_group)
        import_layout.addWidget(QLabel("Keep FH6 in Vinyl Group Editor and do not switch menus during import."))
        import_btn = QPushButton("Import JSON into FH6")
        import_btn.setObjectName("primaryButton")
        import_btn.clicked.connect(self.start_import)
        auto_btn = QPushButton("Auto-locate FH6 template")
        auto_btn.clicked.connect(self.start_auto_locate)
        import_layout.addWidget(import_btn)
        import_layout.addWidget(auto_btn)
        right_layout.addWidget(import_group)
        right_layout.addWidget(QLabel("Import Preview"))
        self.import_preview = PreviewView("Select a JSON to preview it here.")
        right_layout.addWidget(self.import_preview, 1)
        self.tabs.addTab(tab, "Import")

    def _build_tools_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QGridLayout()
        self.tools_layer_count = QLineEdit()
        self.tools_layer_count.setPlaceholderText("Same value as Import tab template layer count")
        self.tools_layer_count.textChanged.connect(lambda text: self.layer_count.setText(text) if self.layer_count.text() != text else None)
        self.layer_count.textChanged.connect(lambda text: self.tools_layer_count.setText(text) if self.tools_layer_count.text() != text else None)
        self.snapshot_count = QLineEdit()
        self.current_count = QLineEdit()
        self.inspect_table = QLineEdit()
        form.addWidget(QLabel("Layer count"), 0, 0)
        form.addWidget(self.tools_layer_count, 0, 1)
        form.addWidget(QLabel("Snapshot layer count"), 1, 0)
        form.addWidget(self.snapshot_count, 1, 1)
        form.addWidget(QLabel("Current layer count"), 2, 0)
        form.addWidget(self.current_count, 2, 1)
        form.addWidget(QLabel("Candidate table"), 3, 0)
        form.addWidget(self.inspect_table, 3, 1)
        layout.addLayout(form)
        actions = QHBoxLayout()
        for label, handler in [
            ("Diagnose", self.start_diagnose),
            ("Auto-locate", self.start_auto_locate),
            ("Save count snapshot", self.start_save_snapshot),
            ("Compare snapshot", self.start_compare_snapshot),
            ("Inspect table", self.start_inspect_table),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addStretch()
        self.tabs.addTab(tab, "FH6 Tools")

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
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        selected_theme = self.app_settings.get("theme", "Pastel Bloom")
        if selected_theme in THEMES:
            self.theme_combo.setCurrentText(selected_theme)
        self.theme_combo.currentIndexChanged.connect(self.apply_theme)
        theme_layout.addWidget(QLabel("Theme"))
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addWidget(QLabel("Theme changes apply immediately and are saved for the next launch."))
        theme_layout.addWidget(QLabel("Sakura Glass uses an opaque control frame with animated cherry blossoms in the background."))
        theme_layout.addWidget(QLabel("Blackout is a full dark opaque preset for low-glare use."))
        layout.addWidget(theme)
        layout.addStretch()
        self.tabs.addTab(tab, "Settings")

    def apply_theme(self, *_args):
        theme_name = self.theme_combo.currentText() if hasattr(self, "theme_combo") else "Pastel Bloom"
        theme_key = THEMES.get(theme_name, "pastel")
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
                QPushButton { background: #f3c7d6; color: #3d2430; border: 1px solid #9f6479; border-radius: 10px; padding: 8px 12px; font-weight: 700; }
                QPushButton:hover { background: #f8d9e4; }
                QPushButton#primaryButton { background: #a83f67; color: white; border: 1px solid #793047; font-weight: 800; padding: 12px 14px; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #fffdfd; color: #332534; border: 2px solid #b77b8f; border-radius: 9px; padding: 6px; selection-background-color: #d65f89; selection-color: white; }
                QScrollArea, QAbstractScrollArea { background: transparent; border: none; }
                QCheckBox { spacing: 8px; color: #332534; }
                QLabel { color: #332534; background: transparent; }
                """
            )
        elif theme_key == "blackout":
            self.setStyleSheet(
                """
                QMainWindow, QWidget { background: #030303; color: #eeeeee; font-family: "Segoe UI Variable", "Segoe UI"; font-size: 10pt; }
                QWidget#appRoot { background: #030303; }
                QTabWidget::pane { border: 2px solid #242424; border-radius: 12px; background: #0a0a0a; }
                QTabBar::tab { background: #111111; color: #bdbdbd; padding: 10px 18px; border: 1px solid #2a2a2a; border-bottom: none; border-top-left-radius: 10px; border-top-right-radius: 10px; margin-right: 4px; font-weight: 700; }
                QTabBar::tab:hover { background: #191919; color: #ffffff; }
                QTabBar::tab:selected { background: #0a0a0a; color: #ffffff; border-color: #4a4a4a; }
                QGroupBox { border: 2px solid #252525; border-radius: 14px; margin-top: 14px; padding: 12px; background: #080808; font-weight: 700; color: #f0f0f0; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; background: #080808; color: #ffffff; }
                QPushButton { background: #141414; color: #f2f2f2; border: 1px solid #424242; border-radius: 10px; padding: 8px 12px; font-weight: 700; }
                QPushButton:hover { background: #202020; border-color: #6a6a6a; }
                QPushButton:pressed { background: #0d0d0d; }
                QPushButton#primaryButton { background: #f5f5f5; color: #050505; border: 1px solid #ffffff; font-weight: 900; padding: 12px 14px; }
                QPushButton#primaryButton:hover { background: #ffffff; color: #000000; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #050505; color: #f2f2f2; border: 1px solid #3b3b3b; border-radius: 8px; padding: 6px; selection-background-color: #ffffff; selection-color: #000000; }
                QComboBox QAbstractItemView { background: #050505; color: #f2f2f2; border: 1px solid #4a4a4a; selection-background-color: #ffffff; selection-color: #000000; }
                QScrollArea, QAbstractScrollArea { background: #050505; border: none; }
                QCheckBox { spacing: 8px; color: #eeeeee; }
                QLabel { color: #eeeeee; background: transparent; }
                QHeaderView::section { background: #111111; color: #f2f2f2; border: 1px solid #2a2a2a; padding: 5px; }
                QScrollBar:vertical, QScrollBar:horizontal { background: #090909; border: none; width: 13px; height: 13px; }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #444444; border-radius: 6px; min-height: 24px; min-width: 24px; }
                QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #666666; }
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
                QPushButton { background: #eadcff; color: #3b244d; border: 1px solid #c7a8ea; border-radius: 10px; padding: 8px 12px; }
                QPushButton:hover { background: #dfc9ff; }
                QPushButton#primaryButton { background: #9f6ad8; color: white; font-weight: 700; padding: 12px 14px; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #fffdf8; color: #3b244d; border: 1px solid #d8c2f0; border-radius: 8px; padding: 6px; selection-background-color: #cfa8ff; }
                QCheckBox { spacing: 8px; }
                QLabel { color: #3b244d; }
                """
            )

    def update_setting_description(self):
        item = self.selected_setting()
        if not item:
            self.setting_description.setText("No settings profiles found.")
            return
        description = item.get("description") or ""
        if self.vroom.isChecked():
            description += "\nVroom doubles effort settings; output layers and resolution stay unchanged."
        self.setting_description.setText(description)
        if not self.custom_enabled.isChecked():
            values = item.get("values", {})
            self.custom_layers.setText(values.get("stopAt", "3000"))
            self.custom_resolution.setText(values.get("maxResolution", "1200"))
            self.custom_random.setText(values.get("randomSamples", "3000"))
            self.custom_mutated.setText(values.get("mutatedSamples", "1000"))
            self.custom_save_at.setText(values.get("saveAt", values.get("stopAt", "3000")))

    def sync_custom_state(self):
        enabled = self.custom_enabled.isChecked()
        for widget in (self.custom_layers, self.custom_resolution, self.custom_random, self.custom_mutated, self.custom_save_at):
            widget.setEnabled(enabled)

    def selected_setting(self):
        return self.profile_combo.currentData() if hasattr(self, "profile_combo") else (self.settings[0] if self.settings else None)

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
        overrides = {"v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none"}
        if self.custom_enabled.isChecked():
            overrides.update({
                "stopAt": self.custom_layers.text(),
                "maxResolution": self.custom_resolution.text(),
                "randomSamples": self.custom_random.text(),
                "mutatedSamples": self.custom_mutated.text(),
                "saveAt": self.custom_save_at.text(),
            })
        base_values = dict(setting.get("values", {}))
        base_values.update({key: value for key, value in overrides.items() if str(value).strip()})
        overrides.update(self.vroom_boost_overrides(base_values))
        if self.custom_enabled.isChecked() or self.vroom.isChecked() or overrides["v2PreprocessMode"] != str(setting.get("values", {}).get("v2PreprocessMode", "none")).strip().lower():
            boosted = write_custom_settings(setting, overrides)
            boosted["label"] = setting.get("label", boosted.get("label"))
            return boosted
        return setting

    def add_image(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All files (*.*)")
        if not file_name:
            return
        path = Path(file_name)
        self.images = [path]
        self.render_lists()
        self.show_preview_bytes(render_source_image(path) or b"")

    def manual_add_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose geometry JSON", "", "Geometry JSON (*.json);;All files (*.*)")
        if not file_name:
            return
        path = Path(file_name)
        if path.exists():
            self.select_import_json(path, "manual JSON")
        self.render_lists()

    def render_lists(self):
        self.image_list.clear()
        for path in self.images:
            self.image_list.addItem(str(path))
        self.update_selected_json_label()

    def log_line(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.append(f"[{timestamp}] {message}")

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_progress(self, text: str):
        self.progress_label.setText(text)

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
            self.preview.clear("Rendering JSON preview...")
            self.import_preview.clear("Rendering JSON preview...")
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

    def preview_path_for_json(self, path: Path) -> Path | None:
        path = Path(path)
        name = path.name
        match = re.match(r"^(.*)\.(\d+)v2\.json$", name)
        if match:
            base, step = match.groups()
            candidate = path.with_name(f"{base}.preview.{step}v2.png")
            return candidate if candidate.exists() else None
        if name.endswith(".v2.json"):
            candidate = path.with_name(f"{path.stem}.preview.png")
            return candidate if candidate.exists() else None
        if ".v2.final." in name:
            match = re.match(r"^(.*)\.v2\.final\.(\d+)\.json$", name)
            if match:
                base, count = match.groups()
                candidates = [
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
        self.pid_combo.clear()
        if self.processes:
            for item in self.processes:
                self.pid_combo.addItem(item["label"], item)
            self.game_combo.setCurrentText(self.processes[0]["profile"])
        else:
            self.pid_combo.addItem("No supported game process detected", None)

    def selected_pid_value(self) -> int | None:
        data = self.pid_combo.currentData()
        if data and data.get("pid"):
            return int(data["pid"])
        raw = self.pid_combo.currentText()
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
            self.log_line("No quality profile selected.")
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
        self.log_line("Graceful stop requested. V2 will finalize saved checkpoints.")

    def generate_worker(self, setting, images, repair_enabled):
        try:
            self.bus.log.emit(f"Selected profile: {setting.get('label') or setting['path'].name}")
            self.bus.log.emit(f"Preprocess: {setting.get('values', {}).get('v2PreprocessMode', 'none')}")
            self.bus.log.emit(f"Targeted repair: {'on' if repair_enabled else 'off'}")
            for image_path in images:
                run_dir = next_generator_output_dir(image_path)
                before = {path.resolve() for path in self.run_json_files(run_dir)}
                self.latest_generated_run_dir = run_dir
                self.active_generation_run_dirs[image_path] = run_dir
                self.bus.log.emit(f"Generating: {image_path}")
                self.bus.log.emit(f"Output folder: {run_dir}")
                src = render_source_image(image_path)
                if src:
                    self.bus.preview_bytes.emit(src)
                cmd = build_generator_command(image_path, setting, enable_repair=repair_enabled, enable_overshoot=False, output_dir=run_dir)
                self.bus.log.emit(f"Running GPU generator with {setting['path'].name}")
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
                    self.bus.log.emit(f"Generated: {output}")
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
                    "Generated layer ",
                    "Step ",
                    "Retry ",
                    "Raw generator finished",
                    "V2 ",
                    "RAW GENERATION COMPLETE",
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
                return f"Generated layer {current}/{total}"
            if "Saved geometry checkpoint" in detail:
                return f"Saved JSON checkpoint {current}/{total}"
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
            return "Raw generator finished. V2 finalization is still running; final import JSONs are not ready yet."
        important = (
            "Generating raw V2",
            "Target template",
            "Target drawable",
            "Raw generator stop:",
            "Using settings:",
            "Preprocess mode:",
            "Preprocessed image:",
            "RAW GENERATION COMPLETE",
            "V2 outputs are",
            "V2 finalization:",
            "V2 scoring ",
            "V2 finalizing ",
            "V2 FINALIZATION COMPLETE",
            "Continuing V2 finalization",
            "Candidate ",
            "Best accuracy:",
            "Latest checkpoint V2:",
            "V2 JSON:",
            "V2 preview:",
            "Selected final:",
            "Final JSON:",
            "Final preview:",
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
        folder = self.outputs[-1].parent if self.outputs else (self.images[-1].parent if self.images else None)
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
            return (int(match.group(1)), 1, f"{match.group(1)} V2")
        if name.endswith(".v2.json") or ".v2.final." in name:
            return (10**9, 1, "Final V2")
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

    def all_generated_checkpoint_jsons(self):
        candidates = set()
        if GENERATED_ROOT.exists():
            for path in GENERATED_ROOT.rglob("*.json"):
                if not is_internal_generator_json(path):
                    candidates.add(path.resolve())
        return candidates

    def is_v2_output_json(self, path):
        name = Path(path).name.lower()
        return bool(".v2.final." in name or re.search(r"\.\d+v2\.json$", name) or name.endswith(".v2.json"))

    def checkpoint_candidates(self):
        candidates = set(self.all_generated_checkpoint_jsons())
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
            })
        entries.sort(key=lambda item: (-item["run_mtime"], item["source"].lower(), item["step_number"], item["step_variant"], item["path"].name.lower()))
        return entries

    def json_display_type(self, path):
        name = Path(path).name
        match = re.search(r"\.(\d+)v2\.json$", name)
        if match:
            return f"Checkpoint {match.group(1)} V2"
        if name.endswith(".v2.json") or ".v2.final." in name:
            return "V2 Final"
        match = re.search(r"\.(\d+)\.json$", name)
        if match:
            return f"Checkpoint {match.group(1)}"
        return "Final"

    def generated_folder_label(self, entry):
        return self.checkpoint_run_label(entry["run_folder"])

    def generated_display_label(self, entry):
        recommended = "[recommended] " if entry.get("recommended") else ""
        unsafe = ""
        if not entry.get("import_safe", True):
            budget = entry.get("import_budget")
            unsafe = f" [raw overshoot"
            if budget:
                unsafe += f" > {budget}"
            unsafe += "]"
        return f"{recommended}{entry['type']} | {entry['layers']} layers | {entry['path'].name}{unsafe}"

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
        self.generated_folder_combo.blockSignals(False)
        self.populate_generated_checkpoint_list(self.generated_folder_combo.currentText())

    def populate_generated_checkpoint_list(self, folder_label: str):
        self.generated_checkpoint_entries = list(self.generated_folder_entries.get(folder_label, []))
        self.generated_checkpoint_list.clear()
        if not self.generated_checkpoint_entries:
            self.generated_checkpoint_list.addItem("No generated checkpoints found yet.")
            return
        for entry in self.generated_checkpoint_entries:
            item = QListWidgetItem(self.generated_display_label(entry))
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
            self.update_selected_json_label("Selected import JSON: none - highlighted checkpoint is raw overshoot and cannot be imported.")
            self.preview_json(entry["path"])
            self.log_line(f"Cannot import raw overshoot JSON: {entry['path']} ({entry['layers']} layers > {entry.get('import_budget') or 'target budget'})")
            return
        self.select_import_json(entry["path"], "highlighted checkpoint")

    def select_recommended_generated_json(self):
        entry = self.recommended_generated_entry()
        if not entry:
            self.log_line("No recommended generated JSON found yet.")
            return
        for row, candidate in enumerate(self.generated_checkpoint_entries):
            if candidate["path"] == entry["path"]:
                self.generated_checkpoint_list.setCurrentRow(row)
                break
        self.select_import_json(entry["path"], "recommended checkpoint")

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
        elif self.selected_import_json_path:
            self.selected_json_label.setText(f"Selected import JSON: {self.selected_import_json_path}")
        else:
            self.selected_json_label.setText("Selected import JSON: none")

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
            "45",
        ]
        code = self.run_subprocess(cmd, timeout=70)
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
            self.log_line("No JSON files selected.")
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
        self.set_status("Running")
        threading.Thread(
            target=self.import_worker,
            args=(pid, game, count_address, table_address, layer_count, json_path),
            daemon=True,
        ).start()

    def check_json_layer_fit(self, json_path, layer_count):
        try:
            json_layers = geometry_shape_count(json_path)
            template_layers = int(layer_count)
        except Exception:
            return
        usable_layers = max(0, template_layers - 4)
        if json_layers and template_layers and json_layers > usable_layers:
            self.bus.log.emit(f"FH needs 4 boundary layers. JSON={json_layers}, template={template_layers}, usable={usable_layers}")
        if json_layers and usable_layers and json_layers < usable_layers * 0.75:
            self.bus.log.emit(f"Selected JSON has far fewer drawable layers than usable capacity. JSON={json_layers}, usable={usable_layers}")

    def import_worker(self, pid, game, count_address, table_address, layer_count, json_path):
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
            self.check_json_layer_fit(path, layer_count)
        cmd = [helper_python(), ROOT / "main.py", "--game", game, "--no-preview"]
        if pid:
            cmd.extend(["--pid", str(pid)])
        if count_address:
            cmd.extend(["--layer-count-address", count_address])
        if table_address:
            cmd.extend(["--layer-table-address", table_address])
        if game == "fh6" and layer_count:
            cmd.extend(["--layer-count-value", str(layer_count)])
        cmd.append(path)
        code = self.run_subprocess(cmd)
        if code != 0:
            self.bus.status.emit("Failed")
            return
        self.bus.status.emit("Done")

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
        require_pubert_presence()
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
