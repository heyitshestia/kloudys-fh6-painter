from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import struct
import sys
import threading
import time
import urllib.request
import wave
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
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
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
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
    auto_generation_values,
    build_generator_command,
    delete_user_preset,
    detail_heatmap_preview_bytes,
    generation_report_path,
    generator_stop_request_path,
    geometry_shape_count,
    import_drawable_budget,
    is_internal_generator_json,
    load_settings,
    next_generator_output_dir,
    save_user_preset,
    source_sanity_check,
    write_custom_settings,
)
from geometry_json import ELLIPSE, RECTANGLE, ROTATED_ELLIPSE, ROTATED_RECTANGLE, load_normalized_geometry
from json_preview_renderer import render_json_preview
from version_info import get_version


ROOT = Path(__file__).resolve().parent
REPO_OWNER = "heyitshestia"
REPO_NAME = "kloudys-forza-painter-suite"
BRANCH = "main"
GITHUB_VERSION_RAW = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/VERSION"
KOFI_URL = "https://ko-fi.com/O7O020EQNQ"
EMBEDDED_PYTHON = ROOT / "python" / "python.exe"
PROBE_DIR = ROOT / "webui-data" / "probes"
APP_SETTINGS_PATH = ROOT / "runtime" / "app_settings.json"
SESSION_PATH = PROBE_DIR / "current-fh6-session.json"
PREVIEW_MAX = 1200
MEMORY_SNAPSHOT_LIMIT_MB = 2048
UNIVERSAL_IMPORT_ROOT = ROOT / "runtime" / "universal-import"
PROJECT_PRESENCE_ASSET = ROOT / "assets" / "app" / "project-integrity.marker"
LUMA_BANDS_ROOT = ROOT / "imgs" / "luma-bands"
HANDMADE_JSON_ROOT = ROOT / "imgs" / "handmade"
EDITOR_JSON_ROOT = ROOT / "imgs" / "editor"
FABRIC_EDITOR_SCRIPT = ROOT / "tools" / "fabric-editor" / "start_fabric_editor.py"
VINYL_RESOURCE_ROOT = ROOT / "tools" / "fabric-editor" / "Resources" / "Vinyls"
SHAPE_WORDS_PATH = ROOT / "tools" / "fabric-editor" / "shape-words.json"
STANDALONE_APP_FOLDER_NAME = "KloudysFH6Painter"
USER_IMAGES_ROOT = ROOT.parent / "Images" if ROOT.name.lower() == STANDALONE_APP_FOLDER_NAME.lower() else ROOT / "Images"
VINYL_TYPE_BASES = {
    "Primitives": 1048677,
    "Community_Vinyls_1": 1050677,
    "Community_Vinyls_2": 1050777,
    "Community_Vinyls_3": 1050877,
    "Community_Vinyls_4": 1050977,
    "Gradient_Shapes": 1048777,
    "Stripes": 1048877,
    "Tears": 1048977,
    "Racing_Icons": 1049077,
    "Flames": 1049177,
    "Paint_Splats": 1049277,
    "Tribal": 1049377,
    "Nature": 1049477,
    "Upper_Letters_1": 1049577,
    "Upper_Letters_2": 1049677,
    "Upper_Letters_3": 1049777,
    "Upper_Letters_4": 1049877,
    "Upper_Letters_5": 1049977,
    "Lower_Letters_1": 1050077,
    "Lower_Letters_2": 1050177,
    "Lower_Letters_3": 1050277,
    "Lower_Letters_4": 1050377,
    "Lower_Letters_5": 1050477,
}
VINYL_RESOURCE_CACHE: dict[tuple[str, int], list[tuple[float, float]]] = {}
SHAPE_WORD_RESOURCE_CACHE: dict[int, tuple[str, int] | None] | None = None
THEMES = {
    "Pastel Bloom": "pastel",
    "Sakura Glass": "sakura",
    "Horizon Pulse": "horizon",
    "Blackout": "blackout",
    "Eurocorp": "eurocorp",
    "Elite": "elite",
    "CryNet": "crynet",
    "UNATCO": "unatco",
    "New Eden": "new_eden",
    "Red Phosphorous": "red_phosphorous",
    "Blackout Violet": "blackout_violet",
    "Blue Terminal 90s": "blue_terminal_90s",
    "Matrix Green": "matrix_green",
}
DEFAULT_THEME = "Blackout"

WORKFLOW_META = {
    "Dashboard": ("Command Center", "Start the common workflows without hunting through tabs."),
    "Generate Final Vinyl": ("Create", "Build new vinyl JSONs from source art."),
    "Import JSON": ("Create", "Preview a generated or hand-edited JSON and write it into FH6."),
    "Export Game JSON": ("Create", "Read an open editable FH6 group into compatible JSON."),
    "Editor": ("Tools", "Open the local shape editor for JSON cleanup and manual edits."),
    "Image Tools": ("Tools", "External helper links for cutouts, upscaling, and resizing."),
    "Image Size Helper": ("Tools", "Check source resolution and megapixel resize targets."),
    "Bug Reports": ("Support", "Create a private, reviewable report package without automatic upload."),
    "Tutorial": ("Command Center", "Step-by-step setup, generation, import, and troubleshooting guide."),
    "Settings": ("Support", "Appearance, Pro Settings, and importer behavior."),
}

WORKFLOW_SUBTITLES = {
    "Dashboard": "One screen for the most important actions, current status, recent work, and safe next steps.",
    "Generate Final Vinyl": "Choose source art, pick a preset, and build import-ready checkpoints.",
    "Import JSON": "Select a generated final, editor export, hand-edited JSON, or exported game JSON and import through one path.",
    "Export Game JSON": "Read the current editable group into compatible JSON for backup or sharing when allowed.",
    "Editor": "Launch the local browser editor for manual JSON adjustments.",
    "Image Tools": "Quick access to safe browser tools that prepare source art before generation.",
    "Image Size Helper": "Convert image dimensions into practical megapixel targets for presets.",
    "Bug Reports": "No automatic upload. Build, inspect, redact, then save or copy a report manually.",
    "Tutorial": "Detailed setup and workflow instructions.",
    "Settings": "Theme, Pro Settings, sound toggles, and compatibility settings.",
}

SHELL_QSS = """
QFrame#topBar {
    border: 1px solid rgba(255, 255, 255, 80);
    border-radius: 18px;
    padding: 10px;
}
QLabel#appTitle {
    background: transparent;
    font-size: 19pt;
    font-weight: 950;
    letter-spacing: -0.5px;
}
QLabel#appSubtitle {
    background: transparent;
    font-size: 9pt;
}
QFrame#workflowShell {
    border-radius: 18px;
}
QListWidget#workflowNav {
    border: 1px solid rgba(255, 255, 255, 72);
    border-radius: 18px;
    padding: 10px;
    font-weight: 800;
}
QListWidget#workflowNav::item {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(255, 255, 255, 60);
    min-height: 38px;
    padding: 8px 10px;
    margin: 4px 0;
    border-radius: 12px;
}
QListWidget#workflowNav::item:hover {
    background: rgba(255, 255, 255, 42);
    border: 1px solid rgba(255, 255, 255, 130);
}
QListWidget#workflowNav::item:selected {
    border: 1px solid rgba(255, 255, 255, 220);
    font-weight: 950;
}
QListWidget#workflowNav::item:disabled {
    background: transparent;
    border: none;
    min-height: 18px;
    padding: 14px 8px 4px 8px;
    font-size: 8pt;
    font-weight: 950;
}
QFrame#workflowContent {
    border: 1px solid rgba(255, 255, 255, 56);
    border-radius: 18px;
    padding: 10px;
}
QLabel#workflowTitle {
    background: transparent;
    font-size: 20pt;
    font-weight: 950;
}
QLabel#workflowSubtitle {
    background: transparent;
    font-size: 10pt;
}
QFrame#dashboardCard {
    border: 1px solid rgba(255, 255, 255, 72);
    border-radius: 18px;
    padding: 14px;
}
QFrame#tutorialSectionFrame {
    border-radius: 14px;
    padding: 0;
}
QToolButton#tutorialSectionButton {
    border-radius: 12px;
    padding: 11px 14px;
    min-height: 34px;
    font-size: 10pt;
    font-weight: 900;
    text-align: left;
}
QToolButton#tutorialSectionButton::menu-indicator {
    image: none;
}
QFrame#tutorialSectionBodyFrame {
    border-radius: 12px;
    padding: 10px 12px;
}
QLabel#tutorialSectionBody {
    font-size: 10pt;
    padding: 4px;
}
QLabel#tutorialNoResults {
    font-size: 11pt;
    font-weight: 850;
    padding: 14px;
}
QLabel#dashboardCardTitle {
    background: transparent;
    font-size: 14pt;
    font-weight: 950;
}
QLabel#dashboardCardText {
    background: transparent;
    font-size: 10pt;
}
QLabel#bugReportPrivacy {
    background: transparent;
    font-weight: 850;
}
"""


def shell_theme_qss(theme_key: str) -> str:
    if theme_key == "sakura":
        return """
        QFrame#topBar, QFrame#workflowContent { background: rgba(255, 249, 251, 238); border: 1px solid #b77b8f; }
        QListWidget#workflowNav { background: rgba(255, 249, 251, 230); border: 1px solid #b77b8f; }
        QListWidget#workflowNav::item { background: rgba(255, 236, 243, 230); color: #5d2d41; border: 1px solid rgba(167, 100, 122, 120); }
        QListWidget#workflowNav::item:hover { background: #f8d9e4; color: #3b1f2f; border: 1px solid #a7647a; }
        QListWidget#workflowNav::item:selected { background: #a83f67; color: #ffffff; border: 1px solid #793047; }
        QListWidget#workflowNav::item:disabled { color: #7f3d58; }
        QFrame#dashboardCard { background: rgba(255, 253, 253, 245); border: 1px solid #e5b9c8; }
        QFrame#tutorialSectionFrame { background: rgba(255, 253, 253, 210); border: 1px solid #e5b9c8; }
        QToolButton#tutorialSectionButton { background: #f3c7d6; color: #3d2430; border: 1px solid #9f6479; }
        QToolButton#tutorialSectionButton:hover { background: #f8d9e4; }
        QToolButton#tutorialSectionButton:checked { background: #a83f67; color: #ffffff; border: 1px solid #793047; }
        QFrame#tutorialSectionBodyFrame { background: rgba(255, 250, 250, 230); border: 1px solid #e5b9c8; }
        QLabel#tutorialSectionBody, QLabel#tutorialNoResults { color: #332534; }
        """
    if theme_key == "horizon":
        return """
        QFrame#topBar, QFrame#workflowContent { background: rgba(5, 9, 20, 205); border: 1px solid rgba(36, 233, 255, 110); }
        QListWidget#workflowNav { background: rgba(2, 7, 14, 190); border: 1px solid rgba(36, 233, 255, 95); }
        QListWidget#workflowNav::item { background: rgba(8, 22, 35, 190); color: #e8fbff; border: 1px solid rgba(36, 233, 255, 105); }
        QListWidget#workflowNav::item:hover { background: rgba(18, 50, 66, 230); color: #ffffff; border: 1px solid #24e9ff; }
        QListWidget#workflowNav::item:selected { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4a2b, stop:0.55 #ffb000, stop:1 #24e9ff); color: #050914; border: 1px solid #ffffff; }
        QListWidget#workflowNav::item:disabled { color: #ffb000; }
        QFrame#dashboardCard { background: rgba(12, 26, 38, 222); border: 1px solid rgba(36, 233, 255, 100); }
        QFrame#tutorialSectionFrame { background: rgba(12, 26, 38, 205); border: 1px solid rgba(36, 233, 255, 100); }
        QToolButton#tutorialSectionButton { background: rgba(8, 22, 35, 230); color: #e8fbff; border: 1px solid rgba(36, 233, 255, 135); }
        QToolButton#tutorialSectionButton:hover { background: rgba(18, 50, 66, 238); border: 1px solid #24e9ff; }
        QToolButton#tutorialSectionButton:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4a2b, stop:0.55 #ffb000, stop:1 #24e9ff); color: #050914; border: 1px solid #ffffff; }
        QFrame#tutorialSectionBodyFrame { background: rgba(5, 9, 20, 220); border: 1px solid rgba(36, 233, 255, 90); }
        QLabel#tutorialSectionBody, QLabel#tutorialNoResults { color: #e8fbff; }
        """
    if theme_key == "blackout":
        return """
        QFrame#topBar, QFrame#workflowContent { background: #000000; border: 1px solid rgba(255, 255, 255, 125); }
        QListWidget#workflowNav { background: #000000; border: 1px solid rgba(255, 255, 255, 125); }
        QListWidget#workflowNav::item { background: #050505; color: #f4f4f4; border: 1px solid rgba(255, 255, 255, 105); }
        QListWidget#workflowNav::item:hover { background: #121212; color: #ffffff; border: 1px solid rgba(255, 255, 255, 190); }
        QListWidget#workflowNav::item:selected { background: #ffffff; color: #000000; border: 1px solid #ffffff; }
        QListWidget#workflowNav::item:disabled { color: #bdbdbd; }
        QFrame#dashboardCard { background: #080808; border: 1px solid rgba(255, 255, 255, 145); }
        QFrame#tutorialSectionFrame { background: #050505; border: 1px solid rgba(255, 255, 255, 120); }
        QToolButton#tutorialSectionButton { background: #050505; color: #f4f4f4; border: 1px solid rgba(255, 255, 255, 105); }
        QToolButton#tutorialSectionButton:hover { background: #121212; color: #ffffff; border: 1px solid rgba(255, 255, 255, 190); }
        QToolButton#tutorialSectionButton:checked { background: #ffffff; color: #000000; border: 1px solid #ffffff; }
        QFrame#tutorialSectionBodyFrame { background: #000000; border: 1px solid #2b2b2b; }
        QLabel#tutorialSectionBody, QLabel#tutorialNoResults { color: #f4f4f4; }
        """
    if theme_key in THEME_TOKEN_STYLES:
        tokens = THEME_TOKEN_STYLES[theme_key]
        return f"""
        QFrame#topBar, QFrame#workflowContent {{ background: {tokens["panel"]}; border: 1px solid {tokens["border"]}; }}
        QListWidget#workflowNav {{ background: {tokens["panel"]}; border: 1px solid {tokens["border"]}; }}
        QListWidget#workflowNav::item {{ background: {tokens["button"]}; color: {tokens["button_fg"]}; border: 1px solid {tokens["border"]}; }}
        QListWidget#workflowNav::item:hover {{ background: {tokens["button_active"]}; color: {tokens["button_active_fg"]}; border: 1px solid {tokens["accent"]}; }}
        QListWidget#workflowNav::item:selected {{ background: {tokens["accent"]}; color: {tokens["select_fg"]}; border: 1px solid {tokens["frame_light"]}; }}
        QListWidget#workflowNav::item:disabled {{ color: {tokens["hint"]}; }}
        QFrame#dashboardCard {{ background: {tokens["panel_alt"]}; border: 1px solid {tokens["border"]}; }}
        QFrame#tutorialSectionFrame {{ background: {tokens["panel_alt"]}; border: 1px solid {tokens["border"]}; }}
        QToolButton#tutorialSectionButton {{ background: {tokens["button"]}; color: {tokens["button_fg"]}; border: 1px solid {tokens["border"]}; }}
        QToolButton#tutorialSectionButton:hover {{ background: {tokens["button_active"]}; color: {tokens["button_active_fg"]}; border: 1px solid {tokens["accent"]}; }}
        QToolButton#tutorialSectionButton:checked {{ background: {tokens["accent"]}; color: {tokens["select_fg"]}; border: 1px solid {tokens["frame_light"]}; }}
        QFrame#tutorialSectionBodyFrame {{ background: {tokens["panel"]}; border: 1px solid {tokens["border"]}; }}
        QLabel#tutorialSectionBody, QLabel#tutorialNoResults {{ color: {tokens["text"]}; }}
        """
    return """
    QFrame#topBar, QFrame#workflowContent { background: rgba(255, 248, 251, 236); border: 1px solid #d8c2f0; }
    QListWidget#workflowNav { background: rgba(234, 220, 255, 225); border: 1px solid #d8c2f0; }
    QListWidget#workflowNav::item { background: rgba(255, 253, 248, 218); color: #3b244d; border: 1px solid rgba(159, 106, 216, 95); }
    QListWidget#workflowNav::item:hover { background: #eadcff; color: #3b244d; border: 1px solid #9f6ad8; }
    QListWidget#workflowNav::item:selected { background: #9f6ad8; color: #ffffff; border: 1px solid #7b4eb0; }
    QListWidget#workflowNav::item:disabled { color: #6c3fa0; }
    QFrame#dashboardCard { background: rgba(255, 253, 248, 245); border: 1px solid #e3d1f5; }
    QFrame#tutorialSectionFrame { background: rgba(255, 253, 248, 220); border: 1px solid #e3d1f5; }
    QToolButton#tutorialSectionButton { background: #eadcff; color: #3b244d; border: 1px solid #c7a8ea; }
    QToolButton#tutorialSectionButton:hover { background: #dfc9ff; }
    QToolButton#tutorialSectionButton:checked { background: #9f6ad8; color: #ffffff; border: 1px solid #7b4eb0; }
    QFrame#tutorialSectionBodyFrame { background: #fffdf8; border: 1px solid #d8c2f0; }
    QLabel#tutorialSectionBody, QLabel#tutorialNoResults { color: #3b244d; }
    """

THEME_TOKEN_STYLES = {
    "eurocorp": {
        "bg": "#040405",
        "panel": "#0a0b0e",
        "panel_alt": "#121418",
        "input": "#08090c",
        "text": "#e8ebf0",
        "muted": "#70788a",
        "accent": "#cc6a2e",
        "accent_dark": "#8f4a1a",
        "warn": "#a8844a",
        "border": "#262a32",
        "button": "#14171c",
        "button_active": "#1e2229",
        "hint": "#94704a",
        "info": "#5c7082",
        "success": "#6d848c",
        "error": "#b8544c",
        "preview_bg": "#0c0d10",
        "preview_fg": "#e8ebf0",
        "select_fg": "#e8ebf0",
        "button_active_fg": "#e8ebf0",
        "button_fg": "#e8ebf0",
        "accent_fg": "#040405",
        "accent_hover_fg": "#ffffff",
        "frame_light": "#353a44",
        "frame_dark": "#0c0e12",
        "sash": "#181b22",
    },
    "elite": {
        "bg": "#0a0a0a",
        "panel": "#111111",
        "panel_alt": "#1a0f00",
        "input": "#1a0f00",
        "text": "#ffa040",
        "muted": "#cc7700",
        "accent": "#ff8c00",
        "accent_dark": "#ff6a00",
        "warn": "#ffb347",
        "border": "#cc5500",
        "button": "#1a1208",
        "button_active": "#ff7a00",
        "hint": "#ff9d00",
        "info": "#ff8c00",
        "success": "#ffb84d",
        "error": "#ff6a3d",
        "preview_bg": "#0a0a0a",
        "preview_fg": "#ffa040",
        "select_fg": "#0a0a0a",
        "button_active_fg": "#0a0a0a",
        "button_fg": "#ffa040",
        "frame_light": "#cc5500",
        "frame_dark": "#1a0f00",
        "sash": "#1a0f00",
    },
    "crynet": {
        "bg": "#020304",
        "panel": "#060a10",
        "panel_alt": "#0a1018",
        "input": "#040810",
        "text": "#c8dce8",
        "muted": "#5a7284",
        "accent": "#7fefff",
        "accent_dark": "#1a4858",
        "warn": "#8ec4dc",
        "border": "#1a3848",
        "button": "#081018",
        "button_active": "#122028",
        "hint": "#6a98a8",
        "info": "#7fefff",
        "success": "#5a9aa8",
        "error": "#d06070",
        "preview_bg": "#060a10",
        "preview_fg": "#c8dce8",
        "select_fg": "#020304",
        "button_active_fg": "#7fefff",
        "button_fg": "#c8dce8",
        "accent_fg": "#020304",
        "accent_hover_fg": "#c8dce8",
        "frame_light": "#3a6878",
        "frame_dark": "#040810",
        "sash": "#142028",
    },
    "unatco": {
        "bg": "#000000",
        "panel": "#252525",
        "panel_alt": "#2a3830",
        "input": "#0a0a0a",
        "text": "#ffffff",
        "muted": "#bbbbbb",
        "accent": "#283868",
        "accent_dark": "#101830",
        "warn": "#888888",
        "border": "#505050",
        "button": "#888888",
        "button_active": "#aaaaaa",
        "hint": "#707070",
        "info": "#48b0c8",
        "success": "#99ff00",
        "error": "#c06060",
        "preview_bg": "#141414",
        "preview_fg": "#ffffff",
        "select_fg": "#ffffff",
        "button_active_fg": "#101010",
        "button_fg": "#101010",
        "frame_light": "#aaaaaa",
        "frame_dark": "#1a1a1a",
        "sash": "#404040",
    },
    "new_eden": {
        "bg": "#ffffff",
        "panel": "#ffffff",
        "panel_alt": "#f4f4f4",
        "input": "#ffffff",
        "text": "#141414",
        "muted": "#5c5c5c",
        "accent": "#e4032e",
        "accent_dark": "#c90025",
        "warn": "#b80f22",
        "border": "#e0e0e0",
        "button": "#f2f2f2",
        "button_active": "#fde8ec",
        "hint": "#8a3040",
        "info": "#1a8cff",
        "success": "#1f8a4c",
        "error": "#c90025",
        "preview_bg": "#fafafa",
        "preview_fg": "#141414",
        "select_fg": "#ffffff",
        "button_active_fg": "#141414",
        "button_fg": "#141414",
        "frame_light": "#f0f0f0",
        "frame_dark": "#e5e5e5",
        "sash": "#ebebeb",
    },
    "red_phosphorous": {
        "bg": "#0d0000",
        "panel": "#110000",
        "panel_alt": "#1a0000",
        "input": "#1a0000",
        "text": "#ff4444",
        "muted": "#cc3333",
        "accent": "#ff1a1a",
        "accent_dark": "#cc0000",
        "warn": "#ff6666",
        "border": "#800000",
        "button": "#1a0000",
        "button_active": "#cc0000",
        "hint": "#ff6666",
        "info": "#ff1a1a",
        "success": "#ff5555",
        "error": "#ff3333",
        "preview_bg": "#0d0000",
        "preview_fg": "#ff4444",
        "select_fg": "#0d0000",
        "button_active_fg": "#0d0000",
        "button_fg": "#ff4444",
        "frame_light": "#800000",
        "frame_dark": "#1a0000",
        "sash": "#1a0000",
    },
    "blackout_violet": {
        "bg": "#020003",
        "panel": "#08030d",
        "panel_alt": "#11071b",
        "input": "#060208",
        "text": "#f5eaff",
        "muted": "#a58ab8",
        "accent": "#b46cff",
        "accent_dark": "#6b2fb5",
        "warn": "#e0b0ff",
        "border": "#39204f",
        "button": "#12081c",
        "button_active": "#241032",
        "hint": "#c996ff",
        "info": "#d8b0ff",
        "success": "#b6ffde",
        "error": "#ff6fae",
        "preview_bg": "#030004",
        "preview_fg": "#f5eaff",
        "select_fg": "#050007",
        "button_active_fg": "#ffffff",
        "button_fg": "#f5eaff",
        "frame_light": "#7d42c7",
        "frame_dark": "#09030e",
        "sash": "#180a25",
        "font": "\"Segoe UI Variable\", \"Segoe UI\"",
    },
    "blue_terminal_90s": {
        "bg": "#0000aa",
        "panel": "#0000aa",
        "panel_alt": "#000088",
        "input": "#000088",
        "text": "#ffffff",
        "muted": "#c0c0c0",
        "accent": "#ffff55",
        "accent_dark": "#ffffff",
        "warn": "#ffff55",
        "border": "#ffffff",
        "button": "#000088",
        "button_active": "#5555ff",
        "hint": "#ffff55",
        "info": "#55ffff",
        "success": "#55ff55",
        "error": "#ff5555",
        "preview_bg": "#0000aa",
        "preview_fg": "#ffffff",
        "select_fg": "#0000aa",
        "button_active_fg": "#ffffff",
        "button_fg": "#ffffff",
        "accent_fg": "#0000aa",
        "accent_hover_fg": "#0000aa",
        "frame_light": "#ffffff",
        "frame_dark": "#000088",
        "sash": "#000088",
        "font": "\"Lucida Console\", \"Terminal\", \"Consolas\", \"Courier New\"",
        "font_size": "9pt",
    },
    "matrix_green": {
        "bg": "#000000",
        "panel": "#020702",
        "panel_alt": "#041204",
        "input": "#000000",
        "text": "#b7ffb7",
        "muted": "#45a645",
        "accent": "#00ff41",
        "accent_dark": "#00b830",
        "warn": "#a7ff6a",
        "border": "#087a22",
        "button": "#020d05",
        "button_active": "#063b14",
        "hint": "#66ff88",
        "info": "#00ff41",
        "success": "#00ff41",
        "error": "#ff4d6d",
        "preview_bg": "#000000",
        "preview_fg": "#b7ffb7",
        "select_fg": "#000000",
        "button_active_fg": "#d9ffd9",
        "button_fg": "#b7ffb7",
        "accent_fg": "#000000",
        "accent_hover_fg": "#000000",
        "frame_light": "#00ff41",
        "frame_dark": "#001f08",
        "sash": "#063b14",
        "font": "\"Lucida Console\", \"Consolas\", \"Courier New\"",
        "font_size": "9pt",
    },
}


def token_theme_stylesheet(tokens: dict[str, str]) -> str:
    font_family = tokens.get("font", "\"Segoe UI Variable\", \"Segoe UI\"")
    font_size = tokens.get("font_size", "10pt")
    accent_fg = tokens.get("accent_fg", tokens["button_active_fg"])
    accent_hover_fg = tokens.get("accent_hover_fg", accent_fg)
    return f"""
        QMainWindow, QWidget {{
            background: {tokens["bg"]};
            color: {tokens["text"]};
            font-family: {font_family};
            font-size: {font_size};
        }}
        QWidget#appRoot {{ background: transparent; }}
        QTabWidget::pane {{
            border: 1px solid {tokens["border"]};
            border-radius: 14px;
            background: {tokens["panel"]};
        }}
        QTabBar::tab {{
            background: {tokens["panel_alt"]};
            color: {tokens["muted"]};
            padding: 10px 18px;
            border: 1px solid {tokens["border"]};
            border-bottom: none;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            margin-right: 4px;
            font-weight: 800;
        }}
        QTabBar::tab:hover {{
            background: {tokens["button_active"]};
            color: {tokens["text"]};
            border-color: {tokens["accent"]};
        }}
        QTabBar::tab:selected {{
            background: {tokens["panel"]};
            color: {tokens["text"]};
            border-color: {tokens["accent"]};
        }}
        QGroupBox {{
            border: 1px solid {tokens["border"]};
            border-radius: 15px;
            margin-top: 14px;
            padding: 12px;
            background: {tokens["panel"]};
            font-weight: 800;
            color: {tokens["accent"]};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 9px;
            background: {tokens["panel"]};
            color: {tokens["accent"]};
            border-radius: 7px;
        }}
        QPushButton {{
            background: {tokens["button"]};
            color: {tokens["button_fg"]};
            border: 1px solid {tokens["border"]};
            border-radius: 10px;
            padding: 8px 14px;
            font-weight: 800;
            min-height: 28px;
        }}
        QPushButton:hover {{
            background: {tokens["button_active"]};
            color: {tokens["button_active_fg"]};
            border-color: {tokens["accent"]};
        }}
        QPushButton:pressed {{
            background: {tokens["frame_dark"]};
            border-color: {tokens["frame_light"]};
        }}
        QPushButton#primaryButton {{
            background: {tokens["accent"]};
            color: {accent_fg};
            border: 1px solid {tokens["frame_light"]};
            font-weight: 950;
            padding: 12px 16px;
        }}
        QPushButton#primaryButton:hover {{
            background: {tokens["accent_dark"]};
            color: {accent_hover_fg};
        }}
        QPushButton#kofiButton {{
            background: {tokens["panel"]};
            color: {tokens["hint"]};
            border: 1px solid {tokens["border"]};
            border-radius: 8px;
            padding: 2px 10px;
            font-weight: 950;
            min-height: 18px;
            max-height: 24px;
        }}
        QPushButton#kofiButton:hover {{
            background: {tokens["button_active"]};
            color: {tokens["accent"]};
            border-color: {tokens["accent"]};
        }}
        QLabel#kofiOptionalLabel {{
            color: {tokens["hint"]};
            font-size: 8pt;
            font-weight: 900;
        }}
        QLabel#subtleWarningLabel {{
            background: {tokens["panel_alt"]};
            color: {tokens["hint"]};
            border: 1px solid {tokens["border"]};
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 9pt;
            font-weight: 750;
        }}
        QFrame#editorWipPanel {{
            background: {tokens["panel_alt"]};
            border: 3px dashed {tokens["error"]};
            border-radius: 18px;
        }}
        QLabel#editorWipText {{
            color: {tokens["error"]};
            font-size: 14pt;
            font-weight: 900;
            padding: 8px 28px 28px 28px;
        }}
        QToolButton#helpButton {{
            background: {tokens["accent"]};
            color: {accent_fg};
            border: 1px solid {tokens["frame_light"]};
            border-radius: 12px;
            font-weight: 950;
        }}
        QToolButton#helpButton:hover {{
            background: {tokens["accent_dark"]};
            color: {accent_hover_fg};
        }}
        QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget {{
            background: {tokens["input"]};
            color: {tokens["text"]};
            border: 1px solid {tokens["border"]};
            border-radius: 9px;
            padding: 6px;
            selection-background-color: {tokens["accent"]};
            selection-color: {tokens["select_fg"]};
        }}
        QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTextEdit:focus, QTreeWidget:focus {{
            border: 1px solid {tokens["accent"]};
        }}
        QComboBox {{ padding-right: 30px; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border-left: 1px solid {tokens["border"]};
            border-top-right-radius: 8px;
            border-bottom-right-radius: 8px;
            background: {tokens["button"]};
        }}
        QComboBox QAbstractItemView {{
            background: {tokens["input"]};
            color: {tokens["text"]};
            border: 1px solid {tokens["accent"]};
            selection-background-color: {tokens["accent"]};
            selection-color: {tokens["select_fg"]};
            outline: 0;
        }}
        QGraphicsView {{
            background: {tokens["preview_bg"]};
            color: {tokens["preview_fg"]};
            border: 1px solid {tokens["border"]};
            border-radius: 10px;
        }}
        QScrollArea, QAbstractScrollArea {{
            background: transparent;
            border: none;
        }}
        QCheckBox {{
            spacing: 8px;
            color: {tokens["text"]};
            background: transparent;
        }}
        QLabel {{
            color: {tokens["text"]};
            background: transparent;
        }}
        QLabel#updateAlarm {{
            background: transparent;
            color: {tokens["success"]};
            border: none;
            padding: 0;
            font-weight: 900;
        }}
        QHeaderView::section {{
            background: {tokens["panel_alt"]};
            color: {tokens["accent"]};
            border: 1px solid {tokens["border"]};
            padding: 5px;
            font-weight: 800;
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {tokens["frame_dark"]};
            border: none;
            width: 13px;
            height: 13px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {tokens["border"]};
            border-radius: 6px;
            min-height: 24px;
            min-width: 24px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {tokens["accent"]};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            background: transparent;
            border: none;
            width: 0;
            height: 0;
        }}
    """


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


def import_json_shape_count(path: Path) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    shapes = payload.get("shapes")
    if not isinstance(shapes, list):
        raise ValueError("Import JSON must contain a shapes list.")
    count = 0
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            continue
        color = shape.get("color") or []
        alpha = 255
        if isinstance(color, (list, tuple)) and len(color) >= 4:
            try:
                values = [float(value) for value in color[:4]]
                alpha = int(round(values[3] * 255)) if all(0.0 <= value <= 1.0 for value in values) else int(round(values[3]))
            except (TypeError, ValueError):
                alpha = 255
        if alpha <= 0:
            continue
        try:
            shape_type = int(float(shape.get("type", 0) or 0))
        except (TypeError, ValueError):
            shape_type = 0
        if index == 0 and shape_type == 1:
            data = shape.get("data") or []
            if isinstance(data, list) and len(data) == 4:
                try:
                    if float(data[0]) == 0 and float(data[1]) == 0 and float(data[2]) > 0 and float(data[3]) > 0:
                        continue
                except (TypeError, ValueError):
                    pass
        count += 1
    return count


TEXT = {
    "tutorial": """KFPS tutorial

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

Shaded Character Art
- Best default for anime, faces, eyes, hair, skin, and mixed linework.
- Uses smart-detail weighting and leaves Luma Prep off to protect tiny detail.

Flat Colors
- Best for mascot art, stickers, hard borders, and broad clean color regions.
- Uses edge-biased shapes and Luma Prep by default.

Smooth Gradients
- Best for glossy shading and dark-to-light gradients.
- Keeps Luma Prep off, uses softer detail weighting, and allows alpha for smoother blends.

The 2x Sample Goblin (slower) switch doubles random samples and mutated samples.
It does not double output layers or resolution, and it usually takes longer.

Default settings are preset-locked now:
- Template layers controls the target vinyl layer budget.
- Finalize at layers controls which checkpoints become import choices.
- Max resolution, random samples, and mutated samples come from the selected preset.
- Enable Pro settings only if you want to override the preset values yourself.
- Pro settings stay open/closed across app restarts.


3. Generate Final Vinyl

Open Generate Final Vinyl, choose one image, pick a preset, then click Generate Final Vinyl.

Visible default controls:
- Template layers: match the FH6 template size you plan to use.
- Finalize at layers: checkpoints you want as final choices.

Pro controls:
- Max resolution: how much detail the generator can see.
- Random samples: broad search effort.
- Mutated samples: local fit/refinement effort.
- 2x Sample Goblin: doubles random and mutated samples.
- Luma Prep: luma-banded preprocessing for broad clean regions.
- Edge Repair: finalization cleanup for borders, holes, hair gaps, and transparent cutouts.


4. Important: generation is not done when the raw builder finishes

The app has two phases:

Phase 1: internal build
- The patched GPU builder creates raw checkpoints.
- The preview may update while layers are being built.
- These raw checkpoints are not the recommended import target.

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
- Use these in Import JSON.

checkpoints
- Internal raw builder checkpoints.
- Useful for diagnostics, not the recommended import target.

previews
- Preview PNGs for raw and finalized outputs.

reports
- Settings, toggles, scores, candidates, and run metadata.


6. Prepare FH6 before importing

In Forza Horizon 6:

1. Open Vinyl Group Editor.
2. Create or load a 3000-layer template made from simple plain white circle layers.
3. Save that 3000-circle template once, then leave/reopen it before using it for imports.
4. Reuse this same saved template for future imports. The importer writes into the open copy and trims the saved result; it does not overwrite your reusable template unless you save over it yourself.
5. Open the template in Vinyl Group Editor and ungroup it so every circle layer is individually editable.
6. Stay in the Vinyl Group Editor. Do not switch menus after preparing the template.
7. Enter 3000 as the exact template layer count unless you intentionally opened a different template.

Default import uses the full template for art layers.
Finalize Checkpoints keeps transparent-source shapes inside the PNG canvas, so current imports do not need FH border masks.
That means normal usable art layers are:

template layers

Examples:

500 template layers = 500 usable art layers
1000 template layers = 1000 usable art layers
2000 template layers = 2000 usable art layers
3000 template layers = 3000 usable art layers


7. Import JSON

Open Import JSON.

1. Pick the generated vinyl run.
2. Pick the finalized checkpoint you want, or choose any compatible editor, hand-edited, or exported JSON manually.
3. Check the preview.
4. Enter the exact FH6 template layer count. Default/recommended is 3000.
5. Click Auto-locate FH6 template if needed.
6. Click Import JSON into FH6.

The highlighted/selected JSON is the one that imports.
The best safe final is listed first, but you can pick a different finalized checkpoint yourself.


8. Image Tools and Editor

Open Image Tools when your source needs prep before generation:
- Background Remover opens PhotoRoom's online cutout tool.
- 2x / 4x Browser Upscaler opens a browser-local upscaler.
- Browser Downscaler / Compressor opens Squoosh.

Open Image Size Helper to check the source resolution and see 1-6 MP resize targets for the same aspect ratio.

Open Editor to launch the Fabric FH6 Editor, the bundled local-browser FH6 JSON editor.
The editor is for manual JSON creation/export. It does not write to FH6 memory.


9. If import does nothing or errors

Check these first:

- FH6 is running.
- You are inside Vinyl Group Editor, not applying a vinyl to the car.
- The template is ungrouped.
- The layer count is exact.
- The selected JSON fits inside the template layer count.
- The app may need to run as administrator.

If generation looks bad, try the preset that matches the source style, increase layers, enable Pro settings for more samples if needed, or use a cleaner source image.
""",
}


TUTORIAL_SECTIONS = [
    {
        "title": "Start Here",
        "summary": "The safe first-run path from launcher to app.",
        "body": """Use the launcher when possible.

First-time setup:
1. Run Setup Python.
2. Run Install Dependencies.
3. Run Update if the launcher says GitHub main is newer.
4. Launch the app.

Manual fallback files:
- 00_launcher.bat opens the launcher.
- 01_add_python312_to_path.bat helps when Python is missing.
- 02_install_dependencies.bat checks and installs app dependencies.
- 03_update_from_github.bat updates program files while preserving generated/runtime data.
- 05_check_environment.bat prints useful setup diagnostics.

If the launcher does not open on versions below 2.0.10, update through 03_update_from_github.bat from the root folder.""",
    },
    {
        "title": "Dashboard",
        "summary": "Where to start and what the main cards mean.",
        "body": """The Dashboard is the quick-start page.

Use it for:
- Starting a new generation.
- Opening the importer.
- Opening the Fabric editor.
- Seeing the update status and current app state.

The editor card is there because generated vinyls usually become much better after a small amount of manual cleanup. Use the editor for hand-created vinyls too, not only generator cleanup.""",
    },
    {
        "title": "Generate Final Vinyl",
        "summary": "Pick source art, preset, layer count, and checkpoints.",
        "body": """Basic flow:
1. Choose one or more source images.
2. Pick the preset that matches the art style.
3. Set Template Layers to your target FH6 template size.
4. Leave Finalize at layers as the default list unless you know exactly what you want.
5. Press Generate Final Vinyl.

Current stock presets:
- Shaded Character Art: best default for anime, faces, eyes, hair, skin, and mixed linework.
- Flat Colors: best for mascot art, stickers, hard borders, and broad clean regions.
- Smooth Gradients: best for glossy shading, soft ramps, and painterly blends.

Important:
- Raw builder checkpoints are not the recommended import target.
- Wait until the log says FINALIZE CHECKPOINTS COMPLETE.
- Final import-ready JSONs are written to imgs/generated/<job>/finals.

Pro Settings:
- Pro controls are normally hidden and preset-managed.
- Enable manual override in Settings only if you want to tune max resolution, random samples, mutated samples, Luma Prep, Edge Repair, or 2x Sample Goblin yourself.""",
    },
    {
        "title": "Source Image Checks",
        "summary": "Avoid images that are too small, too huge, or badly cut out.",
        "body": """Before generating, check the source banner above the preview.

Green means the source looks usable.
Yellow means the app can use it, but quality or speed may suffer.
Red means the image is likely a bad fit until resized or cleaned.

Common problems:
- Too small: there is not enough detail for the generator to see.
- Too large: generation slows down without proportional quality gain.
- Fake transparent background: the background looks gone, but still contains visible or semi-visible pixels.
- Transparent fringe: cutout edges contain leftover pixels that can waste shapes.

Use Image Size Helper to choose a sensible megapixel target.
Use Image Tools for background removal, browser upscaling, or browser downscaling/compression.""",
    },
    {
        "title": "Import JSON",
        "summary": "Write generated, handmade, editor, or exported JSON into FH6.",
        "body": """Default FH6 import workflow:
1. In FH6, open Vinyl Group Editor.
2. Create or load a 3000-layer template made from simple plain white circle layers.
3. Save that 3000-circle template once.
4. Reopen it before using it for imports.
5. Ungroup it so every circle is individually editable.
6. Stay inside Vinyl Group Editor and do not switch menus.
7. In KFPS, select the JSON and enter the exact template layer count.
8. Press Import JSON into selected game.
9. Save and reload the vinyl in FH6 to verify.

JSON source picker:
- Generated finals shows generated/import-ready outputs.
- Handmade folder reads JSONs from imgs/handmade.
- Editor exports reads JSONs from imgs/editor.
- Choose any JSON lets you pick a file manually.

Layer count matters:
- If the game template has 3000 layers, enter 3000.
- If it has 1000 layers, enter 1000.
- The selected JSON must fit inside the open template.""",
    },
    {
        "title": "Export Game JSON",
        "summary": "Read the current editable FH group into compatible JSON.",
        "body": """Use Export Game JSON when you want to back up or move an editable vinyl group into JSON.

Basic flow:
1. Open the vinyl group in FH6 Vinyl Group Editor.
2. Enter the visible layer count exactly.
3. Keep the game in the editor and do not switch menus.
4. Press Export Current Group.
5. Check the saved report if validation warns or fails.

Important:
- Only export designs you own or have permission to export.
- Fully ungrouped, flat editable vinyls are the most reliable target.
- Heavily grouped or nested vinyls can be harder to validate correctly.
- Exported JSONs are saved under runtime/universal-import and app-visible exported folders when available.""",
    },
    {
        "title": "Fabric Editor",
        "summary": "Create vinyls by hand or clean generated JSONs.",
        "body": """The Fabric editor is a local browser editor for FH-compatible JSON.

Use it for:
- Making vinyls from scratch.
- Editing generated outputs by hand.
- Removing or moving problem layers.
- Tracing over a source overlay.
- Searching and favoriting FH shapes.
- Grouping layers internally without changing game export structure.
- Saving projects separately from exported JSONs.

Editor basics:
- Import or browse a JSON to edit it.
- Add source images as overlays for tracing.
- Use the layer list to select, reorder, group, hide, or lock layers.
- Export JSON when you want to import the result through the app.

Editor groups are internal. Game JSON export remains flat unless FH shape data itself requires otherwise.""",
    },
    {
        "title": "Image Tools",
        "summary": "Prepare source images before generation.",
        "body": """Open Image Tools before generating if the source needs cleanup.

Tools:
- Background Remover opens PhotoRoom for cutouts.
- Browser Upscaler opens a local-browser upscaler for 2x or 4x enlarging.
- Browser Downscaler / Compressor opens Squoosh for resizing and compression.

Good source prep usually improves quality more than forcing extreme generator settings.

Typical fixes:
- Remove backgrounds before generation.
- Upscale tiny sources before using character/detail presets.
- Downscale enormous sources before generating to avoid wasted time.""",
    },
    {
        "title": "Image Size Helper",
        "summary": "Check dimensions, megapixels, and resize targets.",
        "body": """Use Image Size Helper when you are not sure whether a source is too small or too large.

It shows:
- Current width and height.
- Current megapixels.
- Same-aspect resize targets from 1 MP to 6 MP.
- A preset cheat sheet for practical source sizes.

Quick guidance:
- Flat Colors: often fine around 1.5-3 MP.
- Shaded Character Art: often best around 2-4 MP.
- Smooth Gradients: often benefits from 3-6 MP.

These are practical targets, not hard rules. Clean art and good layer count still matter.""",
    },
    {
        "title": "Settings",
        "summary": "Theme, Pro settings, sound, and compatibility toggles.",
        "body": """Settings controls app behavior, not a single generation only.

Common settings:
- Theme changes the full app look.
- Manual Pro Settings controls whether advanced generator lines are editable.
- Blue Terminal dial-up sound can be toggled for that theme.
- Game compatibility options control FH6/FH5 process targeting where available.

Leave Pro Settings disabled unless you need direct generator tuning. The presets are designed to choose safe automatic values for most users.""",
    },
    {
        "title": "Output Folders",
        "summary": "Where generated, handmade, exported, and project files belong.",
        "body": """Important folders:
- imgs/generated: generated runs, previews, reports, checkpoints, and finals.
- imgs/generated/<job>/finals: import-ready generated JSONs.
- imgs/handmade: downloaded, shared, or hand-edited JSONs for browsing/import.
- imgs/editor: Fabric editor exports and copied game exports grouped into per-design folders.
- runtime/universal-import: import/export run logs, reports, backups, and raw operation output.
- Images: source image folder used by standalone workflows.

Generated checkpoints:
- finals are the recommended import target.
- checkpoints are raw internal build saves and are mostly diagnostic.
- reports explain settings, scores, and run metadata.""",
    },
    {
        "title": "Troubleshooting",
        "summary": "Fast checks for setup, generation, import, and preview issues.",
        "body": """If generation fails:
- Check the log line before the Python traceback.
- Make sure dependencies are installed.
- For OpenCL errors, verify GPU driver OpenCL support is installed.
- Avoid write-protected folders or cloud folders that deny file writes.

If import does nothing:
- FH6 must be running.
- You must be inside Vinyl Group Editor.
- The template must be ungrouped for normal imports.
- The template layer count must be exact.
- The JSON must fit inside the template.
- Try running the app as administrator.

If the preview looks different from FH6:
- Save and reload the vinyl in game before judging shape resources.
- Some FH shapes only appear correctly after the game reloads the vinyl.
- Use the editor preview for structure, but always verify in-game before sharing.

If the app UI looks wrong after an update:
- Fully close the app and launcher.
- Run the updater batch once.
- Relaunch from the launcher or root batch file.""",
    },
]


HELP_TEXT = {
    "preset": (
        "Preset",
        "Pick the preset that matches the source style, not just the speed.\n\n"
        "Flat Colors is for mascot art, stickers, hard borders, and broad color islands.\n"
        "Shaded Character Art is the best default for anime, skin, hair, eyes, and mixed linework.\n"
        "Smooth Gradients is for glossy shading, soft ramps, and painterly blends."
    ),
    "sample_goblin": (
        "2x Sample Goblin",
        "Doubles random samples and mutated samples for the selected run.\n\n"
        "It usually improves search quality, but it is slower. It does not increase output layers, max resolution, or finalized checkpoint counts."
    ),
    "template_layers": (
        "Template Layers",
        "The target layer budget for generation and the FH6 template size you should import into.\n\n"
        "More layers can describe more detail, gradients, and corrections. More layers also take longer and make the FH6 vinyl heavier."
    ),
    "max_resolution": (
        "Max Resolution",
        "Pro setting. When Pro settings are closed, the selected preset controls this.\n\n"
        "The largest internal image size the generator scores.\n\n"
        "Higher values let it see smaller details, but only help if the layer count and samples can actually draw those details.\n\n"
        "Practical ranges:\n"
        "- Logos / flat art: 1000-1400\n"
        "- Anime / clean art: 1400-1800\n"
        "- Detailed shaded art: 1600-2200\n"
        "- Soft gradients: 1800-2400"
    ),
    "random_samples": (
        "Random Samples",
        "Pro setting. When Pro settings are closed, the selected preset controls this.\n\n"
        "Fresh shape guesses tried for each new layer.\n\n"
        "Higher values improve the odds of finding a strong starting shape, especially for small details and hard edges. This is one of the main quality/speed tradeoffs."
    ),
    "mutated_samples": (
        "Mutated Samples",
        "Pro setting. When Pro settings are closed, the selected preset controls this.\n\n"
        "Local refinement tries after a promising candidate exists.\n\n"
        "This improves position, size, rotation, and fit. It is usually more useful once random samples are high enough to find good candidates."
    ),
    "finalize_at": (
        "Finalize At Layers",
        "Checkpoint layer counts to finalize into import-ready JSON files.\n\n"
        "Example: 500,1000,1500,2000 writes final choices at those layer counts, so you can pick the best one manually instead of only using the last output."
    ),
    "luma_prep": (
        "Luma Prep",
        "Preprocesses the source into cleaner brightness/color bands before generation.\n\n"
        "Best for logos, stickers, and flat art. It can soften tiny detail, hair, skin, eyes, and smooth gradients."
    ),
    "edge_repair": (
        "Edge Repair",
        "Final pass that tightens transparent holes, cutout edges, and border adherence.\n\n"
        "Normally keep this on. It only affects finalized outputs, not the raw builder checkpoints."
    ),
    "detail_heatmap": (
        "Detail Heatmap",
        "Automatically detects likely high-detail areas before generation: eyes, linework, hard color changes, alpha cuts, highlights, and tiny local contrast.\n\n"
        "Use Preview heatmap first. If the red/yellow areas match the detail you care about, enable it before generating. Press the preview button again to return to the original source image.\n\n"
        "When enabled, the app saves a heatmap preview, gives the raw generator a gently detail-guided source image, and tells Finalize Checkpoints to protect those regions during scoring/cleanup.\n\n"
        "It does not add more layers. Actual benefit is unclear, results may vary, and very low-layer runs may trade broad-shape accuracy for line detail.\n\n"
        "For important small details, you are usually better off making or cleaning those sections by hand in the KLOUDY FORZA PAINTER SUITE EXTERNAL VINYL EDITOR."
    ),
    "import_template": (
        "Import Template Layer Count",
        "Enter the exact layer count of the open ungrouped FH6 template.\n\n"
        "Recommended default: use one saved 3000-layer template made from plain white circles. Save it once, reopen it before importing, ungroup it, and enter 3000.\n\n"
        "Imports use all open template layers for art and then cull the saved result to the JSON's used layer count. The reusable 3000-circle template itself is not overwritten unless you save over that template manually."
    ),
    "final_json_browser": (
        "JSON Browser",
        "Generated runs show finalized files from imgs/generated.\n\n"
        "Handmade reads loose or foldered JSONs from imgs/handmade.\n\n"
        "Editor exports reads per-design folders from imgs/editor.\n\n"
        "Pick a source, click a JSON, or choose any compatible JSON manually. The highlighted/selected JSON is the one that imports."
    ),
    "auto_locate": (
        "Auto-Locate",
        "Finds the live FH6 vinyl layer table in memory.\n\n"
        "Keep FH6 in Vinyl Group Editor, keep the group ungrouped, and do not switch menus while locating or importing."
    ),
    "clear_unused": (
        "Clear Unused Layers",
        "Clears leftover template slots before trimming.\n\n"
        "This helps avoid stale shapes being briefly visible or saved if FH6 still sees the old template capacity during import."
    ),
    "export_template": (
        "Export Layer Count",
        "Enter the exact layer count of the currently open FH6 group.\n\n"
        "Exporter is read-only. It records validation warnings in the saved report if a grouped vinyl does not match the old flat table assumptions.\n\n"
        "Only export designs you own or have permission to export."
    ),
    "luma_tab": (
        "Fabric FH6 Editor",
        "Opens the bundled local-browser JSON editor.\n\n"
        "Use it to create or clean FH6 JSON by hand, trace over an overlay image, search/favorite shapes, and export FH6-compatible JSON."
    ),
}


def ensure_dirs() -> None:
    for path in (ROOT / "runtime", ROOT / "runtime" / "previews", ROOT / "runtime" / "custom-settings", ROOT / "runtime" / "user-presets", PROBE_DIR, LUMA_BANDS_ROOT, HANDMADE_JSON_ROOT, EDITOR_JSON_ROOT, USER_IMAGES_ROOT, UNIVERSAL_IMPORT_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def load_app_settings() -> dict:
    try:
        data = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def settings_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


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
        GITHUB_VERSION_RAW,
        headers={
            "Accept": "text/plain",
            "Cache-Control": "no-cache",
            "User-Agent": "KloudysFH6Painter",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8", errors="replace").strip()


def remote_main_revision() -> str | None:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(
            ["git", "ls-remote", f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git", f"refs/heads/{BRANCH}"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=flags,
            check=False,
        )
        if result.returncode == 0:
            revision = result.stdout.split()[0].strip()
            if re.fullmatch(r"[0-9a-fA-F]{7,40}", revision):
                return revision.lower()
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
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


def version_update_distance(local_value: str, remote_value: str) -> int:
    local_parts = version_tuple(local_value)
    remote_parts = version_tuple(remote_value)
    if local_parts is None or remote_parts is None:
        return 1 if str(local_value).strip() != str(remote_value).strip() else 0
    width = max(3, len(local_parts), len(remote_parts))
    local_parts = local_parts + (0,) * (width - len(local_parts))
    remote_parts = remote_parts + (0,) * (width - len(remote_parts))
    if remote_parts <= local_parts:
        return 0
    if remote_parts[:2] == local_parts[:2]:
        return max(1, remote_parts[2] - local_parts[2])
    if remote_parts[0] == local_parts[0]:
        return max(2, min(8, (remote_parts[1] - local_parts[1]) * 2 + max(0, remote_parts[2])))
    return 8


def main_revision_has_bugfix(local_revision: str | None, remote_revision: str | None) -> bool:
    if not local_revision or not remote_revision:
        return False
    return not remote_revision.startswith(local_revision) and not local_revision.startswith(remote_revision)


def require_project_presence() -> None:
    # Remove this function call and constant to disable the launch presence check.
    if not PROJECT_PRESENCE_ASSET.is_file():
        raise RuntimeError("Required project files are missing. Launch from the full KFPS folder.")


def show_startup_dependency_error(exc: BaseException) -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    QMessageBox.critical(
        None,
        "Dependencies missing",
        "KFPS cannot start because a required dependency is missing.\n\n"
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


def shape_word_resource_map() -> dict[int, tuple[str, int] | None]:
    global SHAPE_WORD_RESOURCE_CACHE
    if SHAPE_WORD_RESOURCE_CACHE is not None:
        return SHAPE_WORD_RESOURCE_CACHE
    mapping: dict[int, tuple[str, int] | None] = {}
    if SHAPE_WORDS_PATH.exists():
        try:
            payload = json.loads(SHAPE_WORDS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for family, values in (payload.get("families") or {}).items():
            if not isinstance(values, dict):
                continue
            for index, word in values.items():
                try:
                    mapping[int(word) & 0xFFFF] = (family, int(index))
                except (TypeError, ValueError):
                    continue
    for family, base in VINYL_TYPE_BASES.items():
        base_word = int(base) & 0xFFFF
        for index in range(1, 41):
            mapping.setdefault((base_word + index - 1) & 0xFFFF, (family, index))
            if not family.endswith("Letters"):
                mapping.setdefault((base_word + (index - 1) * 4) & 0xFFFF, (family, index))
    for index in range(1, 41):
        mapping.setdefault((100 + index) & 0xFFFF, ("Primitives", index))
    SHAPE_WORD_RESOURCE_CACHE = mapping
    return mapping


def resolve_vinyl_resource(type_code: int, shape: dict | None = None) -> tuple[str, int] | None:
    shape = shape or {}
    family = shape.get("resource_family")
    index = shape.get("resource_index")
    if family and index:
        try:
            return str(family), int(index)
        except (TypeError, ValueError):
            pass
    word = int(shape.get("type_word", int(type_code) & 0xFFFF)) & 0xFFFF
    return shape_word_resource_map().get(word)


def load_vinyl_resource_points(family: str, index: int) -> list[tuple[float, float]] | None:
    key = (family, int(index))
    if key in VINYL_RESOURCE_CACHE:
        return VINYL_RESOURCE_CACHE[key]
    path = VINYL_RESOURCE_ROOT / family / str(index)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    vertices = payload.get("Vertices") or []
    indices = payload.get("Indices") or []
    points: list[tuple[float, float]] = []
    for idx in indices:
        try:
            vertex = vertices[int(idx)]
            points.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
    if not points:
        for vertex in vertices:
            try:
                points.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
            except (TypeError, ValueError, AttributeError):
                continue
    if not points:
        return None
    VINYL_RESOURCE_CACHE[key] = points
    return points


def fallback_resource_points_for_word(word: int) -> list[tuple[float, float]]:
    if (int(word) & 0xFFFF) == 0x65:
        return [(-64.0, -64.0), (64.0, -64.0), (64.0, 64.0), (-64.0, 64.0)]
    return [(math.cos(math.tau * step / 32) * 64.0, math.sin(math.tau * step / 32) * 64.0) for step in range(32)]


def transform_fh6_resource_points(points: list[tuple[float, float]], data: list) -> list[tuple[float, float]]:
    x = float(data[0]) if len(data) > 0 else 0.0
    y = float(data[1]) if len(data) > 1 else 0.0
    sx = float(data[2]) if len(data) > 2 else 1.0
    sy = float(data[3]) if len(data) > 3 else 1.0
    rot = math.radians(float(data[4]) if len(data) > 4 else 0.0)
    skew = float(data[5]) if len(data) > 5 else 0.0
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    transformed = []
    for px, py in points:
        lx = float(px) * sx
        ly = float(py) * sy
        if skew:
            lx += float(py) * sy * skew
        wx = x + lx * cos_r - ly * sin_r
        wy = y + lx * sin_r + ly * cos_r
        transformed.append((wx, wy))
    return transformed


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

    preview_items = []
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    for item in shapes_in:
        if not isinstance(item, dict):
            continue
        data = list(item.get("data") or [])
        color = list(item.get("color") or [])
        if len(data) < 4 or len(color) < 4:
            continue
        try:
            [float(v) for v in data[:4]]
            rgba = [max(0, min(255, int(round(float(v))))) for v in color[:4]]
        except (TypeError, ValueError):
            continue
        if rgba[3] <= 0:
            continue
        type_code = int(item.get("type", ROTATED_ELLIPSE))
        word = int(item.get("type_word", type_code & 0xFFFF))
        resource = resolve_vinyl_resource(type_code, item)
        points = load_vinyl_resource_points(*resource) if resource else None
        if not points:
            points = fallback_resource_points_for_word(word)
        world_points = transform_fh6_resource_points(points, data)
        if not world_points:
            continue
        for px, py in world_points:
            min_x = min(min_x, px)
            min_y = min(min_y, py)
            max_x = max(max_x, px)
            max_y = max(max_y, py)
        preview_items.append({
            "world_points": world_points,
            "color": rgba,
            "score": item.get("score", 0),
        })

    if not preview_items or not math.isfinite(min_x) or not math.isfinite(max_x):
        raise ValueError("JSON does not contain visible previewable layers.")
    padding = max(24.0, min(160.0, max(max_x - min_x, max_y - min_y) * 0.04))
    src_size = source.get("canvas_size") or source.get("size") if isinstance(source, dict) else None
    if isinstance(src_size, list) and len(src_size) >= 2:
        width, height = max(1, int(src_size[0])), max(1, int(src_size[1]))
        offset_x = width / 2.0
        offset_y = height / 2.0
    else:
        width = max(1, int(math.ceil((max_x - min_x) + padding * 2.0)))
        height = max(1, int(math.ceil((max_y - min_y) + padding * 2.0)))
        offset_x = -min_x + padding
        offset_y = max_y + padding
    drawables = []
    for item in preview_items:
        canvas_points = [[round(px + offset_x, 3), round(offset_y - py, 3)] for px, py in item["world_points"]]
        drawables.append({"type": "polygon", "points": canvas_points, "color": item["color"], "score": item.get("score", 0)})
    background = {"type": RECTANGLE, "data": [0, 0, width, height], "color": [0, 0, 0, 0], "score": 0}
    return {"shapes": [background] + drawables}


def render_geometry_json(path: Path, max_size: int = PREVIEW_MAX) -> bytes | None:
    shared = render_json_preview(path, max_size=max_size)
    if shared:
        return shared
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
            mask = np.zeros((render_h, render_w), np.uint8)
            if shape.get("points"):
                shape_type = 0
                try:
                    points = np.array(
                        [[int(round(float(px) * scale)), int(round(float(py) * scale))] for px, py in shape.get("points", [])],
                        dtype=np.int32,
                    )
                except (TypeError, ValueError):
                    points = np.empty((0, 2), dtype=np.int32)
                if len(points) >= 3:
                    cv2.fillPoly(mask, [points], 255)
            else:
                shape_type = int(shape.get("type", 0))
            if not mask.any() and shape_type in (ELLIPSE, ROTATED_ELLIPSE):
                x, y, w, h, rot_deg = shape["data"]
                if shape_type == ELLIPSE:
                    rot_deg = 0
                adj_w, adj_h = compensated_ellipse_size(w, h)
                axes = (max(1, int(round(adj_h * scale))), max(1, int(round(adj_w * scale))))
                cv2.ellipse(mask, (int(round(x * scale)), int(round(y * scale))), axes, -90 + float(rot_deg), 0.0, 360.0, 255, thickness=-1)
            elif not mask.any() and shape_type in (RECTANGLE, ROTATED_RECTANGLE):
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


class FinalJsonBrowserDialog(QDialog):
    def __init__(self, app: "MainWindow", entries: list[dict]):
        super().__init__(app)
        self.app = app
        self.entries = entries
        self.selected_entry: dict | None = None
        self.run_groups: dict[str, list[dict]] = {}
        self.run_mtimes: dict[str, float] = {}
        self.run_folders: dict[str, Path] = {}
        self.run_buttons: dict[str, QToolButton] = {}
        self.dialog_preview_request_id = 0
        self.setWindowTitle("Browse Finalized JSONs")
        self.resize(1420, 860)
        self.setMinimumSize(1180, 760)

        layout = QVBoxLayout(self)
        intro = QLabel("Choose a JSON folder/source, preview the available JSONs, then click Select. The selected JSON will be locked into the importer.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        run_panel = QWidget()
        run_layout = QVBoxLayout(run_panel)
        run_layout.setContentsMargins(0, 0, 0, 0)
        run_layout.addWidget(QLabel("JSON folders"))
        self.run_scroll = QScrollArea()
        self.run_scroll.setWidgetResizable(True)
        self.run_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.run_grid_host = QWidget()
        self.run_grid = QGridLayout(self.run_grid_host)
        self.run_grid.setSpacing(8)
        self.run_scroll.setWidget(self.run_grid_host)
        run_layout.addWidget(self.run_scroll, 1)
        splitter.addWidget(run_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.run_title = QLabel("Select a JSON folder")
        self.run_title.setWordWrap(True)
        detail_layout.addWidget(self.run_title)
        preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.final_preview = PreviewView("Final checkpoint preview appears here.")
        self.final_preview.setMinimumHeight(300)
        self.checkpoint_list = QListWidget()
        self.checkpoint_list.setObjectName("finalJsonDialogCheckpointList")
        self.checkpoint_list.setIconSize(QSize(180, 112))
        self.checkpoint_list.setMinimumHeight(320)
        self.checkpoint_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.checkpoint_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.checkpoint_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.checkpoint_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.checkpoint_list.setWordWrap(True)
        self.checkpoint_list.currentRowChanged.connect(self.select_checkpoint_row)
        preview_splitter.addWidget(self.final_preview)
        preview_splitter.addWidget(self.checkpoint_list)
        preview_splitter.setSizes([390, 430])
        detail_layout.addWidget(preview_splitter, 1)
        splitter.addWidget(detail_panel)
        splitter.setSizes([580, 840])

        buttons = QHBoxLayout()
        self.selection_label = QLabel("Selected: none")
        self.selection_label.setWordWrap(True)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.select_button = QPushButton("Select")
        self.select_button.setObjectName("primaryButton")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.accept_selected)
        buttons.addWidget(self.selection_label, 1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.select_button)
        layout.addLayout(buttons)

        self.prepare_runs()
        self.populate_runs()

    def prepare_runs(self):
        for entry in self.entries:
            run_key = entry.get("run_key") or str(Path(entry["path"]).parent.resolve())
            self.run_groups.setdefault(run_key, []).append(entry)
            self.run_mtimes[run_key] = max(float(self.run_mtimes.get(run_key, 0)), float(entry.get("run_mtime") or 0))
            self.run_folders[run_key] = Path(entry.get("run_folder") or Path(entry["path"]).parent)
        for run_key, group in list(self.run_groups.items()):
            self.run_groups[run_key] = self.sort_checkpoints(group)

    @staticmethod
    def sort_checkpoints(entries: list[dict]) -> list[dict]:
        return sorted(
            entries,
            key=lambda entry: (
                -int(entry.get("layers") or 0),
                -int(entry.get("step_number") or 0),
                str(entry.get("path", "")).lower(),
            ),
        )

    def populate_runs(self):
        run_order = sorted(self.run_groups, key=lambda key: self.run_mtimes.get(key, 0), reverse=True)
        if not run_order:
            label = QLabel("No JSONs found yet.")
            label.setWordWrap(True)
            self.run_grid.addWidget(label, 0, 0)
            return
        for index, run_key in enumerate(run_order):
            button = QToolButton()
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIconSize(QSize(138, 88))
            button.setMinimumSize(165, 150)
            button.setMaximumWidth(190)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            entries = self.run_groups[run_key]
            best_layers = max((int(entry.get("layers") or 0) for entry in entries), default=0)
            label = self.run_button_label(run_key, entries, best_layers)
            button.setText(label)
            source_path = self.source_image_path(entries[0])
            pixmap = self.thumbnail_pixmap(source_path, QSize(150, 96))
            if not pixmap.isNull():
                button.setIcon(QIcon(pixmap))
            button.clicked.connect(lambda _checked=False, key=run_key: self.select_run(key))
            row, column = divmod(index, 3)
            self.run_grid.addWidget(button, row, column)
            self.run_buttons[run_key] = button
        for column in range(3):
            self.run_grid.setColumnStretch(column, 1)
        self.select_run(run_order[0])

    def run_button_label(self, run_key: str, entries: list[dict], best_layers: int) -> str:
        run_folder = self.run_folders.get(run_key) or Path(entries[0]["path"]).parent
        source_name = entries[0].get("source_image") or entries[0].get("source") or run_folder.name
        try:
            stamp = datetime.fromtimestamp(run_folder.stat().st_mtime).strftime("%m-%d %H:%M")
        except Exception:
            stamp = "unknown time"
        return f"{source_name}\n{len(entries)} JSONs | top {best_layers} layers\n{stamp}"

    def source_image_path(self, entry: dict) -> Path | None:
        run_folder = Path(entry.get("run_folder") or Path(entry["path"]).parent)
        source_name = entry.get("source_image")
        if source_name:
            candidate = run_folder / source_name
            if candidate.exists():
                return candidate
            matches = list(run_folder.glob(source_name))
            if matches:
                return matches[0]
        suffixes = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        for path in sorted(run_folder.iterdir() if run_folder.exists() else [], key=lambda item: item.name.lower()):
            if path.is_file() and path.suffix.lower() in suffixes and ".preview" not in path.name.lower():
                return path
        return None

    def thumbnail_pixmap(self, path: Path | None, size: QSize) -> QPixmap:
        if not path:
            return QPixmap()
        try:
            stat = path.stat()
            cache_key = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size), size.width(), size.height())
        except OSError:
            cache_key = None
        if cache_key and cache_key in self.app.thumbnail_pixmap_cache:
            return self.app.thumbnail_pixmap_cache[cache_key]
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            data = render_source_image(path)
            if data:
                pixmap.loadFromData(data)
        if pixmap.isNull():
            return pixmap
        scaled = pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if cache_key:
            self.app.thumbnail_pixmap_cache[cache_key] = scaled
        return scaled

    def select_run(self, run_key: str):
        for key, button in self.run_buttons.items():
            button.setChecked(key == run_key)
        entries = self.run_groups.get(run_key, [])
        run_folder = self.run_folders.get(run_key)
        if run_folder:
            try:
                rel = run_folder.relative_to(ROOT)
            except ValueError:
                rel = run_folder
            self.run_title.setText(f"Run: {rel}")
        self.populate_checkpoints(entries)

    def populate_checkpoints(self, entries: list[dict]):
        self.checkpoint_list.blockSignals(True)
        self.checkpoint_list.clear()
        for entry in entries:
            item = QListWidgetItem(self.checkpoint_label(entry))
            item.setSizeHint(QSize(0, 132))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            preview = self.app.preview_path_for_json(entry["path"])
            pixmap = self.thumbnail_pixmap(preview, QSize(180, 112)) if preview else QPixmap()
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
            self.checkpoint_list.addItem(item)
        self.checkpoint_list.blockSignals(False)
        if self.checkpoint_list.count() > 0:
            self.checkpoint_list.setCurrentRow(0)
            self.select_checkpoint_row(0)
        else:
            self.selected_entry = None
            self.select_button.setEnabled(False)
            self.final_preview.clear("No finalized checkpoints in this run.")

    def checkpoint_label(self, entry: dict) -> str:
        tags = ", ".join(entry.get("tags") or [])
        if tags:
            tags = f" | {tags}"
        error = entry.get("error")
        error_text = f" | error {float(error):.3f}" if isinstance(error, (int, float)) else ""
        preset = entry.get("preset") or "unknown preset"
        return f"{entry.get('layers') or 0} layers - {entry.get('type') or 'Final JSON'}{tags}{error_text}\n{preset}\n{Path(entry['path']).name}"

    def select_checkpoint_row(self, row: int):
        item = self.checkpoint_list.item(row)
        entry = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.selected_entry = entry
        self.select_button.setEnabled(bool(entry and entry.get("import_safe", True)))
        if not entry:
            self.selection_label.setText("Selected: none")
            self.final_preview.clear("Select a finalized checkpoint.")
            return
        status = "ready to import" if entry.get("import_safe", True) else "over layer budget"
        self.selection_label.setText(f"Selected: {Path(entry['path']).name} ({entry.get('layers') or 0} layers, {status})")
        self.show_entry_preview(entry)

    def show_entry_preview(self, entry: dict):
        preview = self.app.preview_path_for_json(entry["path"])
        if preview and preview.exists():
            self.final_preview.set_file(preview)
            return
        cache_path = self.app.rendered_preview_cache_path(entry["path"])
        try:
            if cache_path.exists() and cache_path.stat().st_mtime >= Path(entry["path"]).stat().st_mtime:
                self.final_preview.set_file(cache_path)
                return
        except OSError:
            pass
        self.dialog_preview_request_id += 1
        request_id = self.dialog_preview_request_id
        path = Path(entry["path"])
        self.final_preview.clear("Rendering preview in the background...")
        threading.Thread(target=self.render_entry_preview_worker, args=(request_id, path), daemon=True).start()

    def render_entry_preview_worker(self, request_id: int, path: Path):
        cache_path = self.app.rendered_preview_cache_path(path)
        data = None
        try:
            if cache_path.exists() and cache_path.stat().st_mtime >= path.stat().st_mtime:
                self.app.bus.ui_call.emit(lambda rid=request_id, p=cache_path: self.apply_entry_preview(rid, p, None))
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
        self.app.bus.ui_call.emit(lambda rid=request_id, p=cache_path, payload=data: self.apply_entry_preview(rid, p, payload))

    def apply_entry_preview(self, request_id: int, cache_path: Path, data: bytes | None):
        if request_id != self.dialog_preview_request_id:
            return
        if cache_path.exists():
            self.final_preview.set_file(cache_path)
        else:
            self.final_preview.set_bytes(data)

    def accept_selected(self):
        if self.selected_entry and self.selected_entry.get("import_safe", True):
            self.accept()

    @property
    def selected_path(self) -> Path | None:
        if not self.selected_entry:
            return None
        return Path(self.selected_entry["path"])


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
        self.horizon_phase = 0.0
        self.horizon_streaks = []
        for index in range(42):
            lane = rng.choice([-1, 1])
            self.horizon_streaks.append(
                {
                    "x": rng.uniform(0.0, 1.0),
                    "y": rng.uniform(0.0, 1.0),
                    "length": rng.uniform(0.035, 0.11),
                    "speed": rng.uniform(0.006, 0.017),
                    "lane": lane,
                    "alpha": rng.uniform(0.22, 0.78),
                    "color": "#24e9ff" if index % 3 else "#ff4a2b",
                }
            )
        self.matrix_phase = 0.0
        self.matrix_columns = []
        for index in range(72):
            self.matrix_columns.append(
                {
                    "x": rng.uniform(0.0, 1.0),
                    "y": rng.uniform(-1.0, 1.0),
                    "speed": rng.uniform(0.006, 0.022),
                    "length": rng.randint(7, 19),
                    "alpha": rng.uniform(0.18, 0.78),
                    "glyph_seed": rng.randint(0, 9999),
                }
            )

    def set_theme(self, theme_key: str):
        self.theme_key = theme_key
        if theme_key in ("sakura", "horizon", "matrix_green"):
            if not self.timer.isActive():
                self.timer.start(33)
        else:
            self.timer.stop()
        self.update()

    def advance_petals(self):
        if self.theme_key == "sakura":
            for petal in self.petals:
                petal["phase"] += 0.045 * petal["drift"]
                petal["angle"] += petal["spin"]
                petal["x"] += petal["speed"]
                petal["y"] += math.sin(petal["phase"]) * 0.0009
                if petal["x"] > 1.12:
                    petal["x"] = random.uniform(-0.22, -0.04)
                    petal["y"] = random.uniform(0.04, 0.95)
        elif self.theme_key == "horizon":
            self.horizon_phase = (self.horizon_phase + 0.018) % math.tau
            for streak in self.horizon_streaks:
                streak["x"] += streak["speed"] * streak["lane"]
                streak["y"] += streak["speed"] * 0.35
                if streak["x"] < -0.18 or streak["x"] > 1.18 or streak["y"] > 1.12:
                    streak["x"] = random.uniform(0.12, 0.88)
                    streak["y"] = random.uniform(-0.08, 0.22)
                    streak["lane"] = random.choice([-1, 1])
        elif self.theme_key == "matrix_green":
            self.matrix_phase = (self.matrix_phase + 0.08) % math.tau
            for column in self.matrix_columns:
                column["y"] += column["speed"]
                if column["y"] > 1.18:
                    column["y"] = random.uniform(-0.55, -0.05)
                    column["x"] = random.uniform(0.0, 1.0)
                    column["speed"] = random.uniform(0.006, 0.022)
                    column["glyph_seed"] = random.randint(0, 9999)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if self.theme_key in THEME_TOKEN_STYLES:
            self.paint_token_theme(painter, rect, THEME_TOKEN_STYLES[self.theme_key])
        elif self.theme_key == "sakura":
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
        elif self.theme_key == "horizon":
            self.paint_horizon(painter, rect)
        else:
            painter.fillRect(rect, QColor("#f5edff"))

    def paint_token_theme(self, painter: QPainter, rect, tokens: dict[str, str]):
        width = max(1, rect.width())
        height = max(1, rect.height())
        if self.theme_key == "blue_terminal_90s":
            painter.fillRect(rect, QColor(tokens["bg"]))
            painter.setPen(QPen(QColor(tokens["frame_light"]), 2))
            painter.drawRect(QRectF(18, 18, width - 36, height - 36))
            painter.setPen(QPen(QColor(tokens["accent"]), 1))
            painter.drawText(34, 50, "KLOUDY BIOS TERMINAL 90S")
            painter.setPen(QPen(QColor(tokens["text"]), 1))
            for index, label in enumerate(("SYSTEM READY", "FH6 VINYL BUFFER ONLINE", "PRESS GENERATE TO CONNECT")):
                painter.drawText(34, 82 + index * 22, label)
            return
        if self.theme_key == "matrix_green":
            painter.fillRect(rect, QColor("#000000"))
            painter.setPen(QPen(QColor(0, 255, 65, 58), 1))
            painter.drawRect(QRectF(18, 18, width - 36, height - 36))
            glyphs = "01ABCDEFGHIJKLMNOPQRSTUVWXYZ#$%&<>"
            font = painter.font()
            font.setFamily("Consolas")
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            line_height = 16
            for column in self.matrix_columns:
                rng = random.Random(column["glyph_seed"])
                x = int(column["x"] * width)
                y = int(column["y"] * height)
                for row in range(column["length"]):
                    alpha = int(255 * column["alpha"] * max(0.08, 1.0 - row / max(1, column["length"])))
                    if row == 0:
                        color = QColor(220, 255, 220, min(255, alpha + 80))
                    else:
                        color = QColor(0, 255, 65, alpha)
                    painter.setPen(QPen(color, 1))
                    painter.drawText(x, y - row * line_height, rng.choice(glyphs))
            painter.setPen(QPen(QColor("#00ff41"), 1))
            painter.drawText(34, 50, "MATRIX LINK ESTABLISHED")
            return
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.00, QColor(tokens["bg"]))
        gradient.setColorAt(0.58, QColor(tokens["panel"]))
        gradient.setColorAt(1.00, QColor(tokens["panel_alt"]))
        painter.fillRect(rect, gradient)

        painter.setPen(Qt.PenStyle.NoPen)
        accent = QColor(tokens["accent"])
        accent.setAlpha(34)
        accent_dark = QColor(tokens["accent_dark"])
        accent_dark.setAlpha(46)
        painter.setBrush(accent)
        painter.drawEllipse(QRectF(width * 0.66, -height * 0.16, width * 0.46, height * 0.46))
        painter.setBrush(accent_dark)
        painter.drawEllipse(QRectF(-width * 0.18, height * 0.58, width * 0.46, height * 0.44))

        if self.theme_key in ("eurocorp", "crynet", "elite"):
            grid_color = QColor(tokens["accent"])
            grid_color.setAlpha(30 if self.theme_key != "elite" else 46)
            painter.setPen(QPen(grid_color, 1))
            step = 54 if self.theme_key != "elite" else 42
            for x in range(-step, width + step, step):
                painter.drawLine(x, 0, x + int(width * 0.10), height)
            for y in range(0, height + step, step):
                painter.drawLine(0, y, width, y - int(height * 0.06))
            painter.setPen(QPen(QColor(tokens["frame_light"]), 2))
            painter.drawLine(0, int(height * 0.16), width, int(height * 0.16))
            painter.drawLine(int(width * 0.76), 0, int(width * 0.90), height)
        elif self.theme_key == "unatco":
            block = QColor(tokens["accent"])
            block.setAlpha(42)
            painter.setBrush(block)
            for index in range(7):
                painter.drawRect(QRectF(width * (0.08 + index * 0.12), height * 0.08, width * 0.035, height * 0.18))
            painter.setPen(QPen(QColor(tokens["success"]), 1))
            for y in range(38, height, 72):
                painter.drawLine(18, y, min(width - 18, 260), y)
        elif self.theme_key == "new_eden":
            painter.setPen(QPen(QColor(tokens["accent"]), 5))
            painter.drawLine(int(width * 0.78), 0, width, int(height * 0.24))
            painter.drawLine(0, int(height * 0.82), int(width * 0.22), height)
            painter.setBrush(QColor(228, 3, 46, 22))
            painter.drawPolygon(
                [
                    QPoint(int(width * 0.68), int(height * 0.08)),
                    QPoint(int(width * 0.93), int(height * 0.17)),
                    QPoint(int(width * 0.84), int(height * 0.38)),
                    QPoint(int(width * 0.59), int(height * 0.28)),
                ]
            )
        elif self.theme_key == "red_phosphorous":
            painter.setPen(QPen(QColor(tokens["accent"]), 1))
            for y in range(0, height, 18):
                painter.drawLine(0, y, width, y)
            painter.setPen(QPen(QColor(tokens["error"]), 2))
            painter.drawRect(QRectF(16, 16, width - 32, height - 32))
        elif self.theme_key == "blackout_violet":
            painter.setPen(QPen(QColor(180, 108, 255, 32), 1))
            for index in range(9):
                x = int(width * (0.08 + index * 0.11))
                painter.drawLine(x, 0, int(x + width * 0.18), height)
            painter.setPen(QPen(QColor(125, 66, 199, 95), 2))
            painter.drawArc(QRectF(width - 280, height - 230, 210, 210), 20 * 16, 270 * 16)
            painter.drawArc(QRectF(45, 42, 170, 170), 180 * 16, -230 * 16)

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

    def paint_horizon(self, painter: QPainter, rect):
        width = max(1, rect.width())
        height = max(1, rect.height())
        pulse = 0.5 + 0.5 * math.sin(self.horizon_phase)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.00, QColor("#050914"))
        gradient.setColorAt(0.34, QColor("#071929"))
        gradient.setColorAt(0.70, QColor("#120912"))
        gradient.setColorAt(1.00, QColor("#050506"))
        painter.fillRect(rect, gradient)

        painter.setPen(Qt.PenStyle.NoPen)
        cyan_glow = QColor(31, 225, 255, int(38 + 42 * pulse))
        orange_glow = QColor(255, 79, 38, int(34 + 38 * (1.0 - pulse)))
        painter.setBrush(cyan_glow)
        painter.drawEllipse(QRectF(width * 0.66, -height * 0.17, width * 0.46, height * 0.48))
        painter.setBrush(orange_glow)
        painter.drawEllipse(QRectF(-width * 0.17, height * 0.55, width * 0.45, height * 0.46))

        horizon_y = height * 0.57
        road_bottom = height * 1.10
        painter.setPen(QPen(QColor(36, 233, 255, 54), 1.1))
        for index in range(10):
            t = index / 9
            x_top = width * (0.50 + (t - 0.5) * 0.10)
            x_bottom = width * (0.50 + (t - 0.5) * 1.38)
            painter.drawLine(int(x_top), int(horizon_y), int(x_bottom), int(road_bottom))

        painter.setPen(QPen(QColor(255, 255, 255, 35), 1.0))
        offset = (self.horizon_phase / math.tau) * 0.09
        for index in range(13):
            t = ((index / 12) + offset) % 1.0
            eased = t * t
            y = horizon_y + eased * (road_bottom - horizon_y)
            half_width = width * (0.05 + eased * 0.72)
            alpha = int(28 + eased * 58)
            painter.setPen(QPen(QColor(36, 233, 255, alpha), 1.0 + eased * 2.0))
            painter.drawLine(int(width * 0.5 - half_width), int(y), int(width * 0.5 + half_width), int(y))

        for streak in self.horizon_streaks:
            color = QColor(streak["color"])
            color.setAlphaF(streak["alpha"])
            pen = QPen(color, 1.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            x = streak["x"] * width
            y = streak["y"] * height
            length = streak["length"] * width
            painter.drawLine(int(x), int(y), int(x - length * streak["lane"]), int(y - length * 0.18))

        gauge_rect = QRectF(width - 245, height - 205, 210, 210)
        painter.setPen(QPen(QColor(255, 255, 255, 35), 8))
        painter.drawArc(gauge_rect, 205 * 16, -235 * 16)
        painter.setPen(QPen(QColor(255, 74, 43, int(130 + 80 * pulse)), 8))
        painter.drawArc(gauge_rect, 205 * 16, int(-165 * 16 - 42 * 16 * pulse))
        painter.setPen(QPen(QColor(36, 233, 255, 110), 2))
        painter.drawArc(QRectF(28, 28, 210, 210), 35 * 16, 112 * 16)


class SparkleLinkPanel(QWidget):
    def __init__(self, links):
        super().__init__()
        if isinstance(links, str):
            links = [("Background Remover", links, "Remove image backgrounds online.")]
        self.links = list(links)
        self.phase = 0.0
        rng = random.Random(260526)
        self.sparkles = [
            {
                "angle": (math.tau * index / 48.0) + rng.uniform(-0.035, 0.035),
                "length": rng.uniform(9.0, 20.0),
                "speed": rng.uniform(0.035, 0.075),
                "phase": rng.uniform(0.0, math.tau),
                "color": rng.choice(["#ffffff", "#ff4fb8", "#24e9ff", "#ffd166"]),
            }
            for index in range(48)
        ]
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.advance)
        self.timer.start()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(1)

        title = QLabel("Image Tools")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22pt; font-weight: 950; color: #ffffff;")
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Useful browser tools for source cleanup before generating a vinyl.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 11pt; color: #dbeafe;")
        layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignCenter)

        self.link_buttons = []
        for label, url, description in self.links:
            button = QPushButton(label)
            button.setObjectName("toolLinkButton")
            button.setMinimumSize(560, 66)
            button.setMaximumWidth(760)
            button.setToolTip(f"{description}\n{url}")
            button.clicked.connect(lambda _checked=False, link=url: QDesktopServices.openUrl(QUrl(link)))
            self.link_buttons.append(button)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
            hint = QLabel(description)
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            hint.setMaximumWidth(760)
            hint.setStyleSheet("color: #dbeafe; font-size: 10pt;")
            layout.addWidget(hint, 0, Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet(
            """
            QPushButton#toolLinkButton {
                color: #07101a;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4fb8, stop:0.48 #ffd166, stop:1 #24e9ff);
                border: 2px solid #ffffff;
                border-radius: 18px;
                font-size: 15pt;
                font-weight: 950;
                padding: 16px 24px;
            }
            QPushButton#toolLinkButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff80cf, stop:0.50 #ffe299, stop:1 #74f8ff);
            }
            QPushButton#toolLinkButton:pressed {
                background: #ffffff;
                color: #07101a;
            }
            """
        )
        layout.addStretch(1)

    def advance(self):
        self.phase = (self.phase + 0.035) % math.tau
        for sparkle in self.sparkles:
            sparkle["phase"] = (sparkle["phase"] + sparkle["speed"]) % math.tau
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.00, QColor("#070914"))
        gradient.setColorAt(0.45, QColor("#15112a"))
        gradient.setColorAt(1.00, QColor("#061c26"))
        painter.fillRect(rect, gradient)

        glow_alpha = int(38 + 30 * (0.5 + 0.5 * math.sin(self.phase)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 79, 184, glow_alpha))
        painter.drawEllipse(QRectF(rect.width() * 0.06, rect.height() * 0.10, rect.width() * 0.28, rect.height() * 0.32))
        painter.setBrush(QColor(36, 233, 255, glow_alpha))
        painter.drawEllipse(QRectF(rect.width() * 0.66, rect.height() * 0.52, rect.width() * 0.31, rect.height() * 0.34))

        button_rect = QRectF()
        if getattr(self, "link_buttons", None):
            first = self.link_buttons[0].geometry()
            last = self.link_buttons[-1].geometry()
            button_rect = QRectF(first).united(QRectF(last))
        if button_rect.isNull():
            button_rect = QRectF(rect.width() * 0.25, rect.height() * 0.46, rect.width() * 0.50, 72)
        center = button_rect.center()
        radius_x = button_rect.width() * 0.56
        radius_y = button_rect.height() * 1.55
        for sparkle in self.sparkles:
            twinkle = 0.5 + 0.5 * math.sin(sparkle["phase"])
            color = QColor(sparkle["color"])
            color.setAlphaF(0.18 + 0.82 * twinkle)
            angle = sparkle["angle"] + math.sin(self.phase * 0.65) * 0.045
            inner_x = center.x() + math.cos(angle) * radius_x
            inner_y = center.y() + math.sin(angle) * radius_y
            length = sparkle["length"] * (0.72 + 0.62 * twinkle)
            outer_x = center.x() + math.cos(angle) * (radius_x + length)
            outer_y = center.y() + math.sin(angle) * (radius_y + length)
            pen = QPen(color, 1.2 + 1.3 * twinkle)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(inner_x), int(inner_y), int(outer_x), int(outer_y))


class WorkflowShell(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("workflowShell")
        self.page_titles: list[str] = []
        self.page_indices: dict[str, int] = {}
        self.current_group: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.nav = QListWidget()
        self.nav.setObjectName("workflowNav")
        self.nav.setFixedWidth(280)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav.itemClicked.connect(self._activate_item)
        layout.addWidget(self.nav)

        content = QFrame()
        content.setObjectName("workflowContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 16)
        content_layout.setSpacing(10)
        self.title = QLabel("Dashboard")
        self.title.setObjectName("workflowTitle")
        self.subtitle = QLabel(WORKFLOW_SUBTITLES["Dashboard"])
        self.subtitle.setObjectName("workflowSubtitle")
        self.subtitle.setWordWrap(True)
        content_layout.addWidget(self.title)
        content_layout.addWidget(self.subtitle)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)

    def addTab(self, widget: QWidget, title: str):
        group = WORKFLOW_META.get(title, ("Other", ""))[0]
        if group != self.current_group:
            heading = QListWidgetItem(group.upper())
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            self.nav.addItem(heading)
            self.current_group = group
        index = self.stack.addWidget(widget)
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setToolTip(WORKFLOW_SUBTITLES.get(title, title))
        self.nav.addItem(item)
        self.page_titles.append(title)
        self.page_indices[title] = index
        if self.stack.count() == 1:
            self.nav.setCurrentItem(item)
            self._set_page(index)
        return index

    def switch_to(self, title: str):
        index = self.page_indices.get(title)
        if index is None:
            return
        self._set_page(index)
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == index:
                self.nav.setCurrentItem(item)
                break

    def _activate_item(self, item: QListWidgetItem):
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self._set_page(int(index))

    def _set_page(self, index: int):
        self.stack.setCurrentIndex(index)
        title = self.page_titles[index] if 0 <= index < len(self.page_titles) else "Dashboard"
        self.title.setText(title)
        self.subtitle.setText(WORKFLOW_SUBTITLES.get(title, ""))


class DashboardCard(QFrame):
    def __init__(self, title: str, text: str, action_text: str, action, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setMinimumHeight(132)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("dashboardCardTitle")
        title_label.setWordWrap(True)
        body = QLabel(text)
        body.setObjectName("dashboardCardText")
        body.setWordWrap(True)
        button = QPushButton(action_text)
        button.setObjectName("primaryButton")
        button.clicked.connect(action)
        layout.addWidget(title_label)
        layout.addWidget(body, 1)
        layout.addWidget(button)


class MainWindow(QMainWindow):
    def __init__(self, initial_images: list[str]):
        super().__init__()
        ensure_dirs()
        if _PSUTIL_ERROR is not None:
            raise _PSUTIL_ERROR
        self.setWindowTitle(f"KFPS - Kloudy's Forza Painter Suite - {get_version()}")
        self.resize(1840, 1060)
        self.setMinimumSize(1600, 940)
        self.app_settings = load_app_settings()
        self.settings = load_settings()
        self.images = [Path(p) for p in initial_images if Path(p).exists()]
        self.selected_import_json_path: Path | None = None
        self.outputs: list[Path] = []
        self.processes = []
        self.active_processes = set()
        self.process_lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.stop_generation_event = threading.Event()
        self.dialup_sound_stop_event = threading.Event()
        self.dialup_sound_thread: threading.Thread | None = None
        self.active_generation_images: list[Path] = []
        self.active_generation_run_dirs: dict[Path, Path] = {}
        self.current_generation_image: Path | None = None
        self.latest_generated_run_dir: Path | None = None
        self.generation_eta_state = {"total": None, "ema_ms": None, "last_current": 0}
        self.auto_located_context: dict | None = None
        self.generated_folder_entries: dict[str, list[dict]] = {}
        self.generated_checkpoint_entries: list[dict] = []
        self.exported_game_json_entries: list[dict] = []
        self.geometry_count_cache: dict[str, tuple[int, int, int]] = {}
        self.thumbnail_pixmap_cache: dict[tuple[str, int, int, int, int], QPixmap] = {}
        self.preview_request_id = 0
        self.export_preview_request_id = 0
        self._all_combos: list[QComboBox] = []
        self._theme_apply_pending = False
        self.update_alarm_state = "checking"
        self.update_alarm_text = "checking main build..."
        self.update_alarm_scale = 1.0
        self.update_blink_on = False
        self.update_check_running = False
        self.update_blink_timer = QTimer(self)
        self.update_blink_timer.setInterval(650)
        self.update_blink_timer.timeout.connect(self.toggle_update_alarm_blink)
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(5 * 60 * 1000)
        self.update_check_timer.timeout.connect(self.start_update_check)
        self.editor_wip_blink_on = True
        self.editor_wip_timer = QTimer(self)
        self.editor_wip_timer.setInterval(520)
        self.editor_wip_timer.timeout.connect(self.toggle_editor_wip_blink)
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
        self.apply_editor_wip_style()
        self.editor_wip_timer.start()
        self.set_phase("ready", "Choose a source image or select a finalized JSON to import.")
        self.refresh_processes()
        self.refresh_generated_browser()
        self.render_lists()
        if self.images:
            self.show_preview_bytes(render_source_image(self.images[0]) or b"")
            self.update_source_check_banner(self.images[0])
            self.sync_auto_summary()
        self.start_update_check()
        self.update_check_timer.start()

    def _build(self):
        central = AnimatedThemeBackground()
        central.setObjectName("appRoot")
        self.background_widget = central
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(12)
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 12, 18, 12)
        title_stack = QVBoxLayout()
        title = QLabel(f"KFPS {get_version()}")
        title.setObjectName("appTitle")
        subtitle = QLabel("Generate, finalize, import, edit, and troubleshoot FH6 vinyl JSONs.")
        subtitle.setObjectName("appSubtitle")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        top_layout.addLayout(title_stack, 1)
        self.phase_label = QLabel("Ready to generate or import.")
        self.phase_label.setObjectName("phaseBanner")
        self.phase_label.setWordWrap(True)
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.phase_label, 2)
        self.update_alarm = QLabel("Main build: checking...", central)
        self.update_alarm.setObjectName("updateAlarm")
        self.update_alarm.setWordWrap(True)
        self.update_alarm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_alarm.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.update_alarm.raise_()
        top_layout.addWidget(self.update_alarm, 1)
        root.addWidget(top_bar)
        self.tabs = WorkflowShell()
        root.addWidget(self.tabs, 1)
        self._build_dashboard_tab()
        self._build_tutorial_tab()
        self._build_generate_tab()
        self._build_import_tab()
        self._build_game_export_tab()
        self._build_editor_tab()
        self._build_image_tools_tab()
        self._build_image_size_tab()
        self._build_bug_report_tab()
        self._build_settings_tab()
        self.populate_profile_list()
        self.update_setting_description()
        self.sync_custom_state()
        footer = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.progress_label = QLabel("")
        footer.addWidget(QLabel("Status:"))
        footer.addWidget(self.status_label)
        footer.addSpacing(24)
        footer.addWidget(QLabel("Progress:"))
        footer.addWidget(self.progress_label, 1)
        optional_label = QLabel("optional ->")
        optional_label.setObjectName("kofiOptionalLabel")
        optional_label.setToolTip("Optional support link.")
        footer.addWidget(optional_label)
        self.kofi_button = QPushButton("Support on Ko-fi")
        self.kofi_button.setObjectName("kofiButton")
        self.kofi_button.setToolTip("Support KFPS on Ko-fi")
        self.kofi_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.kofi_button.setFixedHeight(24)
        self.kofi_button.setMinimumWidth(122)
        self.kofi_button.setMaximumWidth(150)
        self.kofi_button.clicked.connect(self.open_kofi)
        footer.addWidget(self.kofi_button)
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

    def open_kofi(self):
        QDesktopServices.openUrl(QUrl(KOFI_URL))

    def go_to_workflow(self, title: str):
        if hasattr(self, "tabs") and hasattr(self.tabs, "switch_to"):
            self.tabs.switch_to(title)

    def open_fabric_editor(self):
        if os.name != "nt":
            QMessageBox.information(
                self,
                "Windows only",
                "The Fabric FH6 editor is bundled with the standalone Windows app.",
            )
            return
        if not FABRIC_EDITOR_SCRIPT.exists():
            QMessageBox.warning(
                self,
                "Editor missing",
                f"Fabric FH6 Editor was not found:\n{FABRIC_EDITOR_SCRIPT}\n\nRun the updater or reinstall the latest standalone release.",
            )
            return
        try:
            subprocess.Popen(
                [str(EMBEDDED_PYTHON if EMBEDDED_PYTHON.exists() else sys.executable), str(FABRIC_EDITOR_SCRIPT)],
                cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.log_line("Opened Fabric FH6 editor.")
        except Exception as exc:
            QMessageBox.critical(self, "Editor failed to open", str(exc))

    def toggle_editor_wip_blink(self):
        if not hasattr(self, "editor_wip_label"):
            return
        self.editor_wip_blink_on = not self.editor_wip_blink_on
        self.apply_editor_wip_style()

    def apply_editor_wip_style(self):
        if not hasattr(self, "editor_wip_label"):
            return
        color = "#ff1010" if self.editor_wip_blink_on else "rgba(255, 16, 16, 48)"
        self.editor_wip_label.setStyleSheet(
            f"""
            QLabel#editorWipLabel {{
                color: {color};
                background: transparent;
                border: none;
                font-size: 92pt;
                font-weight: 900;
                padding: 18px;
            }}
            """
        )

    def help_button(self, key: str) -> QToolButton:
        title, body = HELP_TEXT[key]
        button = QToolButton()
        button.setText("?")
        button.setObjectName("helpButton")
        button.setCursor(Qt.CursorShape.WhatsThisCursor)
        button.setToolTip(f"{title}\n\n{body}")
        button.setToolTipDuration(30000)
        button.setFixedSize(24, 24)
        return button

    def label_with_help(self, text: str, help_key: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        layout.addWidget(self.help_button(help_key))
        layout.addStretch(1)
        return widget

    def checkbox_with_help(self, checkbox: QCheckBox, help_key: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(checkbox, 1)
        layout.addWidget(self.help_button(help_key), 0, Qt.AlignmentFlag.AlignRight)
        return widget

    def show_help(self, title: str, body: str) -> None:
        QMessageBox.information(self, title, body)

    def close_combo_popups(self):
        for combo in getattr(self, "_all_combos", []):
            with contextlib.suppress(RuntimeError):
                combo.hidePopup()

    def _build_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        start = QFrame()
        start.setObjectName("dashboardCard")
        start_layout = QGridLayout(start)
        start_layout.setHorizontalSpacing(16)
        start_layout.setVerticalSpacing(8)
        start_title = QLabel("Start with a simple path")
        start_title.setObjectName("dashboardCardTitle")
        start_title.setWordWrap(True)
        start_body = QLabel(
            "Most users only need this loop: generate a good base, fix the important bits by hand, then import the finished JSON into FH6."
        )
        start_body.setObjectName("dashboardCardText")
        start_body.setWordWrap(True)
        tutorial_btn = QPushButton("Open tutorial")
        tutorial_btn.clicked.connect(lambda: self.go_to_workflow("Tutorial"))
        start_layout.addWidget(start_title, 0, 0)
        start_layout.addWidget(start_body, 1, 0)
        start_layout.addWidget(tutorial_btn, 0, 1, 2, 1)
        start_layout.setColumnStretch(0, 1)
        layout.addWidget(start)

        workflow = QGridLayout()
        workflow.setSpacing(12)
        for column, (title, body, button_text, target) in enumerate((
            (
                "1. Generate",
                "Choose source art and build finalized JSON checkpoints.",
                "Generate",
                "Generate Final Vinyl",
            ),
            (
                "2. Edit",
                "Open the editor to create by hand, trace over an overlay, or clean up generated layers.",
                "Open editor",
                "Editor",
            ),
            (
                "3. Import",
                "Pick the final JSON, write it into the open FH6 template, then save and reload in game.",
                "Import",
                "Import JSON",
            ),
        )):
            workflow.addWidget(
                DashboardCard(title, body, button_text, lambda target=target: self.go_to_workflow(target)),
                0,
                column,
            )
        layout.addLayout(workflow)

        editor_ad = QFrame()
        editor_ad.setObjectName("dashboardCard")
        editor_layout = QGridLayout(editor_ad)
        editor_layout.setHorizontalSpacing(18)
        editor_layout.setVerticalSpacing(10)
        editor_title = QLabel("The editor is for making vinyls by hand, not just fixing generator output")
        editor_title.setObjectName("dashboardCardTitle")
        editor_title.setWordWrap(True)
        editor_body = QLabel(
            "Use the Fabric editor when you want control: searchable shapes, favorites, overlay tracing, saved colors, eyedropper tools, box selection, groups, and cleaner layer handling. "
            "Generated vinyls are a strong starting point, but the best results usually come from hand-editing the details that matter."
        )
        editor_body.setObjectName("dashboardCardText")
        editor_body.setWordWrap(True)
        editor_layout.addWidget(editor_title, 0, 0, 1, 2)
        editor_layout.addWidget(editor_body, 1, 0, 1, 2)
        layout.addWidget(editor_ad)

        kofi_ad = QFrame()
        kofi_ad.setObjectName("dashboardCard")
        kofi_layout = QVBoxLayout(kofi_ad)
        kofi_layout.setSpacing(10)
        kofi_title = QLabel("tiny optional ko-fi note")
        kofi_title.setObjectName("dashboardCardTitle")
        kofi_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kofi_body = QLabel(
            "hi, tiny ko-fi note: this is completely optional, but if the app helped you and you want to throw a little support my way, "
            "it would help me commission a proper logo/mascot someday instead of making everything myself badly lol\n\n"
            "tip button is in the bottom right."
        )
        kofi_body.setObjectName("dashboardCardText")
        kofi_body.setWordWrap(True)
        kofi_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kofi_layout.addWidget(kofi_title)
        kofi_layout.addWidget(kofi_body)
        layout.addWidget(kofi_ad)
        layout.addStretch(1)
        self.tabs.addTab(tab, "Dashboard")

    def _build_generate_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(640)
        left_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        left.setMinimumWidth(600)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([700, 860])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        image_group = QFrame()
        image_group.setObjectName("dashboardCard")
        image_layout = QVBoxLayout(image_group)
        image_title = QLabel("Step 1 - Source Art")
        image_title.setObjectName("dashboardCardTitle")
        image_layout.addWidget(image_title)
        image_row = QHBoxLayout()
        choose = QPushButton("Choose source image(s)")
        choose.clicked.connect(self.add_image)
        image_row.addWidget(choose, 1)
        open_out = QPushButton("Open latest vinyl folder")
        open_out.clicked.connect(self.open_output_folder)
        image_row.addWidget(open_out, 1)
        image_layout.addLayout(image_row)
        self.image_list = QListWidget()
        self.image_list.setMaximumHeight(118)
        self.image_list.currentRowChanged.connect(self.preview_selected_image)
        image_layout.addWidget(self.image_list)
        image_group.setMaximumHeight(178)
        left_layout.addWidget(image_group)

        quality_group = QFrame()
        quality_group.setObjectName("dashboardCard")
        quality_layout = QVBoxLayout(quality_group)
        quality_title = QLabel("Step 2 - Vinyl Build Preset")
        quality_title.setObjectName("dashboardCardTitle")
        quality_layout.addWidget(quality_title)
        quality_layout.addWidget(self.label_with_help("Preset", "preset"))
        self.profile_combo = self.make_combo(max_visible=18, min_height=38)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        quality_layout.addWidget(self.profile_combo)
        self.setting_description = QLabel("")
        self.setting_description.setWordWrap(True)
        quality_layout.addWidget(self.setting_description)
        self.auto_summary_label = QLabel("Preset settings are fixed. Source image metrics are shown for context only.")
        self.auto_summary_label.setWordWrap(True)
        quality_layout.addWidget(self.auto_summary_label)
        form = QGridLayout()
        self.custom_layers = QLineEdit()
        self.custom_save_at = QLineEdit()
        fields = [
            ("Template layers", self.custom_layers, "template_layers"),
            ("Finalize at layers", self.custom_save_at, "finalize_at"),
        ]
        for row, (label, widget, help_key) in enumerate(fields):
            form.addWidget(self.label_with_help(label, help_key), row, 0)
            form.addWidget(widget, row, 1)
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)
        for widget in (self.custom_layers, self.custom_save_at):
            widget.textEdited.connect(self.sync_auto_summary)
        quality_layout.addLayout(form)
        tuning_form = QGridLayout()
        self.custom_resolution = QLineEdit()
        self.custom_random = QLineEdit()
        self.custom_mutated = QLineEdit()
        tuning_fields = [
            ("Max resolution", self.custom_resolution, "max_resolution"),
            ("Random samples", self.custom_random, "random_samples"),
            ("Mutated samples", self.custom_mutated, "mutated_samples"),
        ]
        self.pro_setting_labels = []
        for row, (label, widget, help_key) in enumerate(tuning_fields):
            label_widget = self.label_with_help(label, help_key)
            self.pro_setting_labels.append(label_widget)
            tuning_form.addWidget(label_widget, row, 0)
            tuning_form.addWidget(widget, row, 1)
            widget.textEdited.connect(self.enable_custom_tuning_from_edit)
            widget.textEdited.connect(self.save_pro_field_values)
        tuning_form.setColumnStretch(0, 0)
        tuning_form.setColumnStretch(1, 1)
        quality_layout.addLayout(tuning_form)
        saved_pro_values = self.app_settings.get("generation_pro_values") if isinstance(self.app_settings.get("generation_pro_values"), dict) else {}
        self.custom_resolution.setText(str(saved_pro_values.get("maxResolution", "")))
        self.custom_random.setText(str(saved_pro_values.get("randomSamples", "")))
        self.custom_mutated.setText(str(saved_pro_values.get("mutatedSamples", "")))
        self.pro_setting_widgets = [self.custom_resolution, self.custom_random, self.custom_mutated]
        self.vroom = QCheckBox("2x Sample Goblin (slower)")
        self.vroom.setToolTip("Doubles auto/manual random and mutated samples for more search effort. Usually slower, sometimes cleaner.")
        self.vroom.stateChanged.connect(self.update_setting_description)
        self.vroom.stateChanged.connect(self.sync_auto_summary)
        self.vroom_row = self.checkbox_with_help(self.vroom, "sample_goblin")
        quality_layout.addWidget(self.vroom_row)
        preset_actions = QHBoxLayout()
        save_preset = QPushButton("Save custom preset")
        save_preset.clicked.connect(self.save_current_custom_preset)
        delete_preset = QPushButton("Delete selected custom")
        delete_preset.clicked.connect(self.delete_selected_custom_preset)
        preset_actions.addWidget(save_preset)
        preset_actions.addWidget(delete_preset)
        quality_layout.addLayout(preset_actions)
        self.luma_enabled = QCheckBox("Luma Prep")
        self.luma_enabled.setToolTip("Best for flat logos/liveries and hard color bands. Leave off for most anime, hair, skin, and smooth gradients.")
        self.luma_enabled.setChecked(False)
        self.luma_enabled.stateChanged.connect(self.sync_auto_summary)
        self.luma_row = self.checkbox_with_help(self.luma_enabled, "luma_prep")
        quality_layout.addWidget(self.luma_row)
        heatmap_row = QHBoxLayout()
        self.detail_heatmap_preview_active = False
        self.detail_heatmap_enabled = QCheckBox("Automatic Detail Heatmap")
        self.detail_heatmap_enabled.setToolTip(
            "Preview first. Actual benefit is unclear and results may vary. "
            "For important small details, you are usually better off making those sections by hand "
            "in the KLOUDY FORZA PAINTER SUITE EXTERNAL VINYL EDITOR."
        )
        self.detail_heatmap_enabled.setChecked(False)
        self.detail_heatmap_enabled.stateChanged.connect(self.sync_auto_summary)
        heatmap_row.addWidget(self.checkbox_with_help(self.detail_heatmap_enabled, "detail_heatmap"), 1)
        self.preview_heatmap_button = QPushButton("Preview heatmap")
        self.preview_heatmap_button.setMinimumWidth(132)
        self.preview_heatmap_button.clicked.connect(self.preview_detail_heatmap)
        heatmap_row.addWidget(self.preview_heatmap_button)
        quality_layout.addLayout(heatmap_row)
        self.repair_enabled = QCheckBox("Edge Repair")
        self.repair_enabled.setToolTip("Final pass that tightens borders and transparent holes on the finalized checkpoints.")
        self.repair_enabled.setChecked(True)
        self.repair_enabled.stateChanged.connect(self.sync_auto_summary)
        self.repair_row = self.checkbox_with_help(self.repair_enabled, "edge_repair")
        quality_layout.addWidget(self.repair_row)
        left_layout.addWidget(quality_group)

        run_group = QFrame()
        run_group.setObjectName("dashboardCard")
        run_outer = QVBoxLayout(run_group)
        run_title = QLabel("Step 3 - Generate Final Vinyl")
        run_title.setObjectName("dashboardCardTitle")
        run_outer.addWidget(run_title)
        run_layout = QHBoxLayout()
        run_outer.addLayout(run_layout)
        generate = QPushButton("Generate Final Vinyl")
        generate.setObjectName("primaryButton")
        generate.clicked.connect(self.start_generate)
        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_generate)
        run_layout.addWidget(generate, 2)
        run_layout.addWidget(stop, 1)
        left_layout.addWidget(run_group)
        left_layout.addStretch()

        right_layout.addWidget(QLabel("Live Preview"))
        self.source_check_label = QLabel("Source check: choose an image.")
        self.source_check_label.setWordWrap(True)
        self.source_check_label.setMinimumHeight(58)
        self.source_check_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_layout.addWidget(self.source_check_label)
        self.preview = PreviewView("Choose source art or a finalized vinyl to preview it here.")
        right_layout.addWidget(self.preview, 1)
        self.tabs.addTab(tab, "Generate Final Vinyl")

    def _build_import_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([760, 820])

        game = QGroupBox("Step 1 - Forza Session")
        game_layout = QGridLayout(game)
        self.game_combo = self.make_combo(list(PROFILES.keys()), max_visible=12)
        self.game_combo.setCurrentText("fh6")
        self.game_combo.currentTextChanged.connect(self.update_game_compatibility_notices)
        self.pid_combo = self.make_combo(max_visible=12, editable=True)
        self.pid_combo.currentIndexChanged.connect(lambda _index: self.sync_game_from_pid_combo(self.pid_combo, self.game_combo))
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_processes)
        game_layout.addWidget(QLabel("Game"), 0, 0)
        game_layout.addWidget(self.game_combo, 0, 1)
        game_layout.addWidget(QLabel("Process"), 1, 0)
        game_layout.addWidget(self.pid_combo, 1, 1)
        game_layout.addWidget(refresh, 1, 2)
        left_layout.addWidget(game)
        self.import_game_notice = QLabel(
            "FH5 import/export is provided as-is. KFPS focuses on FH6; FH5 may be reviewed later once the app is in a steadier state."
        )
        self.import_game_notice.setObjectName("subtleWarningLabel")
        self.import_game_notice.setWordWrap(True)
        self.import_game_notice.setVisible(False)
        left_layout.addWidget(self.import_game_notice)

        template = QGroupBox("Step 2 - Vinyl Template")
        template_layout = QGridLayout(template)
        self.layer_count = QLineEdit("3000")
        template_layout.addWidget(self.label_with_help("Exact template layer count", "import_template"), 0, 0)
        template_layout.addWidget(self.layer_count, 0, 1)
        template_help = QLabel("Default workflow: create one plain white 3000-circle template, save it, reopen it, ungroup it, and enter 3000. Reuse that same saved template for future imports.")
        template_help.setWordWrap(True)
        template_layout.addWidget(template_help, 1, 0, 1, 2)
        left_layout.addWidget(template)

        json_group = QGroupBox("Step 3 - Pick Final JSON")
        json_layout = QVBoxLayout(json_group)
        json_intro = QLabel("Pick from the latest generation below, or use Browse Finals to visually choose older runs by source image and final preview.")
        json_intro.setWordWrap(True)
        json_layout.addWidget(json_intro)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("JSON source"))
        self.json_source_combo = self.make_combo(["Generated finals", "Handmade folder", "Editor exports"], max_visible=3, min_height=38)
        self.json_source_combo.currentTextChanged.connect(lambda _text: self.refresh_generated_browser())
        source_row.addWidget(self.json_source_combo, 1)
        json_layout.addLayout(source_row)
        latest_row = QHBoxLayout()
        self.latest_final_combo = self.make_combo(max_visible=18, min_height=42)
        self.latest_final_combo.currentIndexChanged.connect(self.select_latest_final_combo_entry)
        browse_jsons = QPushButton("Browse JSONs...")
        browse_jsons.setObjectName("primaryButton")
        browse_jsons.clicked.connect(self.open_final_json_browser)
        latest_row.addWidget(self.latest_final_combo, 1)
        latest_row.addWidget(browse_jsons)
        json_layout.addLayout(latest_row)
        controls = QGridLayout()
        refresh_jsons = QPushButton("Refresh")
        refresh_jsons.clicked.connect(self.refresh_generated_browser)
        add_json = QPushButton("Choose any JSON...")
        add_json.clicked.connect(self.manual_add_json)
        for button in (refresh_jsons, add_json):
            button.setMinimumWidth(150)
        controls.addWidget(refresh_jsons, 0, 0)
        controls.addWidget(add_json, 0, 1)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        json_layout.addLayout(controls)
        latest_hint = QLabel("Generated mode shows the latest run by layer count. Handmade and Editor modes read JSONs from imgs/handmade and imgs/editor so outside files and editor exports have safe drop folders.")
        latest_hint.setWordWrap(True)
        json_layout.addWidget(latest_hint)
        self.generated_folder_combo = self.make_combo(max_visible=24, min_height=34)
        self.generated_folder_combo.currentTextChanged.connect(self.populate_generated_checkpoint_list)
        self.generated_folder_combo.setVisible(False)
        self.generated_checkpoint_list = QListWidget()
        self.generated_checkpoint_list.setObjectName("finalizedCheckpointList")
        self.generated_checkpoint_list.setMinimumHeight(320)
        self.generated_checkpoint_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.generated_checkpoint_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.generated_checkpoint_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.generated_checkpoint_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.generated_checkpoint_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.generated_checkpoint_list.setWordWrap(True)
        self.generated_checkpoint_list.currentRowChanged.connect(self.select_generated_checkpoint)
        self.generated_checkpoint_list.setVisible(False)
        json_layout.addWidget(self.generated_folder_combo)
        json_layout.addWidget(self.generated_checkpoint_list)
        left_layout.addWidget(json_group)
        left_layout.addStretch(1)

        import_group = QGroupBox("Step 4 - Import JSON")
        import_layout = QVBoxLayout(import_group)
        import_layout.addWidget(QLabel("Keep the selected game in Vinyl Group Editor and do not switch menus during import."))
        self.selected_json_label = QLabel("Selected JSON: none")
        self.selected_json_label.setWordWrap(False)
        self.selected_json_label.setMaximumHeight(28)
        self.selected_json_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        import_layout.addWidget(self.selected_json_label)
        self.import_clear_unused = QCheckBox("Clear unused template layers before trimming")
        self.import_clear_unused.setChecked(True)
        self.import_clear_unused.setToolTip("Recommended. Clears old template layers that are not used by the imported JSON before trimming the game group count.")
        import_layout.addWidget(self.checkbox_with_help(self.import_clear_unused, "clear_unused"))
        import_btn = QPushButton("Import JSON into selected game")
        import_btn.setObjectName("primaryButton")
        import_btn.clicked.connect(self.start_import)
        auto_btn = QPushButton("Auto-locate template")
        auto_btn.clicked.connect(self.start_auto_locate)
        import_layout.addWidget(import_btn)
        auto_row = QHBoxLayout()
        auto_row.addWidget(auto_btn, 1)
        auto_row.addWidget(self.help_button("auto_locate"))
        import_layout.addLayout(auto_row)
        right_layout.addWidget(import_group)
        right_layout.addWidget(QLabel("JSON Preview"))
        self.import_preview = PreviewView("Select a generated, editor, exported, or hand-edited JSON to preview it here.")
        right_layout.addWidget(self.import_preview, 1)
        notes = QLabel(
            "One importer handles generated finals, Fabric editor exports, hand-edited full-shape JSONs, and game exports. "
            "Use a saved/reopened 3000 plain white circle template, ungroup it, import once, then save and reload in game."
        )
        notes.setWordWrap(True)
        right_layout.addWidget(notes)
        self.tabs.addTab(tab, "Import JSON")

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
            "Export the currently open Forza vinyl group into compatible JSON. "
            "This is read-only. Grouped vinyls may export with validation warnings in the saved report. "
            "Only export designs you own or have permission to export."
        )
        intro.setWordWrap(True)
        left_layout.addWidget(intro)

        game = QGroupBox("Step 1 - Forza Session")
        game_layout = QGridLayout(game)
        self.export_game_combo = self.make_combo(list(PROFILES.keys()), max_visible=12)
        self.export_game_combo.setCurrentText("fh6")
        self.export_game_combo.currentTextChanged.connect(self.update_game_compatibility_notices)
        self.export_pid_combo = self.make_combo(max_visible=12, editable=True)
        self.export_pid_combo.currentIndexChanged.connect(lambda _index: self.sync_game_from_pid_combo(self.export_pid_combo, self.export_game_combo))
        export_refresh = QPushButton("Refresh")
        export_refresh.clicked.connect(self.refresh_processes)
        game_layout.addWidget(QLabel("Game"), 0, 0)
        game_layout.addWidget(self.export_game_combo, 0, 1)
        game_layout.addWidget(QLabel("Process"), 1, 0)
        game_layout.addWidget(self.export_pid_combo, 1, 1)
        game_layout.addWidget(export_refresh, 1, 2)
        left_layout.addWidget(game)
        self.export_game_notice = QLabel(
            "FH5 import/export is provided as-is. KFPS focuses on FH6; FH5 may be reviewed later once the app is in a steadier state."
        )
        self.export_game_notice.setObjectName("subtleWarningLabel")
        self.export_game_notice.setWordWrap(True)
        self.export_game_notice.setVisible(False)
        left_layout.addWidget(self.export_game_notice)

        template = QGroupBox("Step 2 - Current Open Group")
        template_layout = QGridLayout(template)
        self.export_template_count = QLineEdit("3000")
        self.export_template_count.setToolTip("Enter the exact layer count of the currently open editable game group.")
        template_layout.addWidget(self.label_with_help("Current group layer count", "export_template"), 0, 0)
        template_layout.addWidget(self.export_template_count, 0, 1)
        template_help = QLabel(
            "Keep the group open and do not switch game menus while exporting. "
            "The exporter validates the live editable layer table before writing any JSON."
        )
        template_help.setWordWrap(True)
        template_layout.addWidget(template_help, 1, 0, 1, 2)
        left_layout.addWidget(template)

        run_group = QGroupBox("Step 3 - Export")
        run_layout = QVBoxLayout(run_group)
        export_btn = QPushButton("Export Current Group")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self.start_game_export)
        run_layout.addWidget(export_btn)
        run_layout.addWidget(QLabel("Output is saved under runtime/universal-import and copied to imgs/editor so it appears in Import JSON -> Editor exports."))
        left_layout.addWidget(run_group)
        left_layout.addStretch(1)

        right_layout.addWidget(QLabel("Export Preview"))
        self.export_preview = PreviewView("Export a game group to preview it here. The JSON will be available from Import JSON -> Editor exports.")
        right_layout.addWidget(self.export_preview, 1)
        note = QLabel(
            "Preview is an approximation for non-basic FH shapes until full shape rendering is added. "
            "The JSON still preserves the real FH type word for re-import."
        )
        note.setWordWrap(True)
        right_layout.addWidget(note)
        self.tabs.addTab(tab, "Export Game JSON")

    def _build_editor_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QGroupBox("Fabric FH6 Editor")
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(self.label_with_help("Open the bundled browser-based FH6 JSON editor. This does not write to FH6 memory.", "luma_tab"))
        description = QLabel(
            "Fabric FH6 Editor opens as a local browser editor window.\n"
            "Use it to place, move, stretch, rotate, save project files, and export FH6 JSON."
        )
        description.setWordWrap(True)
        controls_layout.addWidget(description)
        actions = QHBoxLayout()
        open_editor = QPushButton("Open Fabric FH6 Editor")
        open_editor.setObjectName("primaryButton")
        open_editor.clicked.connect(self.open_fabric_editor)
        actions.addWidget(open_editor, 1)
        controls_layout.addLayout(actions)
        self.luma_status_label = QLabel(f"Editor script: {FABRIC_EDITOR_SCRIPT}")
        self.luma_status_label.setWordWrap(True)
        controls_layout.addWidget(self.luma_status_label)
        layout.addWidget(controls)

        warning_panel = QFrame()
        warning_panel.setObjectName("editorWipPanel")
        warning_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        warning_layout = QVBoxLayout(warning_panel)
        warning_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.editor_wip_label = QLabel("W I P")
        self.editor_wip_label.setObjectName("editorWipLabel")
        self.editor_wip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_layout.addWidget(self.editor_wip_label)
        editor_warning = QLabel(
            "This editor integration is not fully tested yet.\n"
            "Document every bug, broken workflow, missing feature, and anything that needs fixing or changing."
        )
        editor_warning.setObjectName("editorWipText")
        editor_warning.setWordWrap(True)
        editor_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_layout.addWidget(editor_warning)
        layout.addWidget(warning_panel, 1)
        self.tabs.addTab(tab, "Editor")

    def _build_image_tools_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            SparkleLinkPanel(
                [
                    (
                        "Background Remover",
                        "https://www.photoroom.com/tools/background-remover",
                        "Photoroom background remover for cutting out source art before generation.",
                    ),
                    (
                        "2x / 4x Browser Upscaler",
                        "https://hcodx.com/tools/image-upscaler",
                        "Free local-browser upscaler for enlarging small sources without app-side rate limits.",
                    ),
                    (
                        "Browser Downscaler / Compressor",
                        "https://squoosh.app",
                        "Free local-browser image resize/compress tool for preparing sources before import.",
                    ),
                ]
            ),
            1,
        )
        self.tabs.addTab(tab, "Image Tools")

    def _build_image_size_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QGroupBox("Image Size Helper")
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(
            QLabel(
                "Choose one image to see its current pixel size, megapixels, and matching 1-6 MP resize targets. "
                "The targets keep the same aspect ratio."
            )
        )
        actions = QHBoxLayout()
        choose = QPushButton("Choose image")
        choose.setObjectName("primaryButton")
        choose.clicked.connect(self.choose_size_helper_image)
        actions.addWidget(choose)
        actions.addStretch(1)
        controls_layout.addLayout(actions)
        self.size_helper_status = QLabel("No image selected.")
        self.size_helper_status.setWordWrap(True)
        controls_layout.addWidget(self.size_helper_status)
        layout.addWidget(controls)

        body = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Source Preview"))
        self.size_helper_preview = PreviewView("Choose an image to preview it here.")
        left_layout.addWidget(self.size_helper_preview, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Same-aspect resize targets"))
        self.size_helper_table = QTreeWidget()
        self.size_helper_table.setColumnCount(4)
        self.size_helper_table.setHeaderLabels(["Target MP", "Width", "Height", "Actual MP"])
        self.size_helper_table.setRootIsDecorated(False)
        self.size_helper_table.setAlternatingRowColors(True)
        self.size_helper_table.setMinimumWidth(420)
        self.size_helper_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        for index, width in enumerate((110, 110, 110, 120)):
            self.size_helper_table.setColumnWidth(index, width)
        right_layout.addWidget(self.size_helper_table, 1)
        right_layout.addWidget(QLabel("Preset MP cheat sheet"))
        self.size_helper_preset_table = QTreeWidget()
        self.size_helper_preset_table.setColumnCount(3)
        self.size_helper_preset_table.setHeaderLabels(["Preset", "Best MP", "Use case"])
        self.size_helper_preset_table.setRootIsDecorated(False)
        self.size_helper_preset_table.setAlternatingRowColors(True)
        self.size_helper_preset_table.setMaximumHeight(150)
        for preset, mp_range, use_case in (
            ("Flat Colors", "1.5-3 MP", "stickers, mascots, hard regions"),
            ("Shaded Character Art", "2-4 MP", "anime, faces, hair, eyes"),
            ("Smooth Gradients", "3-6 MP", "gloss, soft ramps, shading"),
        ):
            item = QTreeWidgetItem([preset, mp_range, use_case])
            item.setToolTip(0, f"{preset}: {mp_range}")
            item.setToolTip(1, "Recommended source megapixel range before generation.")
            item.setToolTip(2, use_case)
            self.size_helper_preset_table.addTopLevelItem(item)
        for index, width in enumerate((160, 90, 240)):
            self.size_helper_preset_table.setColumnWidth(index, width)
        right_layout.addWidget(self.size_helper_preset_table)

        body.addWidget(left)
        body.addWidget(right)
        body.setStretchFactor(0, 2)
        body.setStretchFactor(1, 1)
        layout.addWidget(body, 1)
        self.tabs.addTab(tab, "Image Size Helper")

    def _build_tutorial_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        intro = QFrame()
        intro.setObjectName("dashboardCard")
        intro_layout = QVBoxLayout(intro)
        title = QLabel("KFPS Tutorial")
        title.setObjectName("dashboardCardTitle")
        body = QLabel(
            "Start here if you are setting up the app, generating your first vinyl, importing into FH6, "
            "or cleaning work by hand in the editor. Use search to narrow the sections below."
        )
        body.setObjectName("dashboardCardText")
        body.setWordWrap(True)
        intro_layout.addWidget(title)
        intro_layout.addWidget(body)
        layout.addWidget(intro)

        self.tutorial_search = QLineEdit()
        self.tutorial_search.setPlaceholderText("Search tutorial sections, for example: import, template, editor, OpenCL, folders")
        self.tutorial_search.textChanged.connect(self.filter_tutorial_sections)
        layout.addWidget(self.tutorial_search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.tutorial_sections_layout = QVBoxLayout(content)
        self.tutorial_sections_layout.setContentsMargins(2, 2, 8, 2)
        self.tutorial_sections_layout.setSpacing(10)
        self.tutorial_section_widgets: list[dict] = []
        for index, section in enumerate(TUTORIAL_SECTIONS):
            self.tutorial_section_widgets.append(self.make_tutorial_section(section, index, expanded=index == 0))
        self.tutorial_no_results = QLabel("No tutorial section matches that search.")
        self.tutorial_no_results.setObjectName("tutorialNoResults")
        self.tutorial_no_results.setWordWrap(True)
        self.tutorial_no_results.setVisible(False)
        self.tutorial_sections_layout.addWidget(self.tutorial_no_results)
        self.tutorial_sections_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.tabs.addTab(tab, "Tutorial")

    def make_tutorial_section(self, section: dict, index: int, *, expanded: bool = False) -> dict:
        frame = QFrame()
        frame.setObjectName("tutorialSectionFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(8)

        button = QToolButton()
        button.setObjectName("tutorialSectionButton")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setCheckable(True)
        button.setChecked(expanded)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda checked, item_index=index: self.set_tutorial_section_open(item_index, checked))

        body_frame = QFrame()
        body_frame.setObjectName("tutorialSectionBodyFrame")
        body_layout = QVBoxLayout(body_frame)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_label = QLabel(section["body"])
        body_label.setObjectName("tutorialSectionBody")
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_layout.addWidget(body_label)
        body_frame.setVisible(expanded)

        frame_layout.addWidget(button)
        frame_layout.addWidget(body_frame)
        self.tutorial_sections_layout.addWidget(frame)

        item = {
            "index": index,
            "frame": frame,
            "button": button,
            "body_frame": body_frame,
            "title": section["title"],
            "summary": section["summary"],
            "search": f'{section["title"]} {section["summary"]} {section["body"]}'.lower(),
        }
        self.update_tutorial_button_text(item)
        return item

    def update_tutorial_button_text(self, item: dict) -> None:
        prefix = "v" if item["button"].isChecked() else ">"
        item["button"].setText(f'{prefix} {item["title"]} - {item["summary"]}')

    def set_tutorial_section_open(self, index: int, open_: bool) -> None:
        if not hasattr(self, "tutorial_section_widgets"):
            return
        for item in self.tutorial_section_widgets:
            if item["index"] != index:
                continue
            item["button"].setChecked(open_)
            item["body_frame"].setVisible(open_)
            self.update_tutorial_button_text(item)
            break

    def filter_tutorial_sections(self, query: str) -> None:
        if not hasattr(self, "tutorial_section_widgets"):
            return
        terms = [term for term in query.lower().split() if term]
        matches: list[tuple[int, dict]] = []
        for item in self.tutorial_section_widgets:
            score = 1 if not terms else sum(1 for term in terms if term in item["search"])
            if score:
                matches.append((score, item))

        for item in self.tutorial_section_widgets:
            self.tutorial_sections_layout.removeWidget(item["frame"])
            item["frame"].setVisible(False)

        if terms:
            ordered = [item for _score, item in sorted(matches, key=lambda pair: (-pair[0], pair[1]["index"]))]
        else:
            ordered = self.tutorial_section_widgets

        for item in ordered:
            item["frame"].setVisible(True)
            self.tutorial_sections_layout.insertWidget(self.tutorial_sections_layout.count() - 2, item["frame"])
            if terms:
                item["button"].setChecked(True)
                item["body_frame"].setVisible(True)
                self.update_tutorial_button_text(item)

        self.tutorial_no_results.setVisible(bool(terms) and not matches)

    def _build_bug_report_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        privacy = QLabel(
            "Private by default: this page never uploads anything. It builds a local report you can inspect, edit, copy, or send manually."
        )
        privacy.setObjectName("bugReportPrivacy")
        privacy.setWordWrap(True)
        left_layout.addWidget(privacy)

        form = QGroupBox("Report Details")
        form_layout = QGridLayout(form)
        self.report_kind = self.make_combo(["Bug", "Suggestion", "Importer issue", "Generator quality issue", "Setup issue"], max_visible=8)
        self.report_title = QLineEdit()
        self.report_title.setPlaceholderText("Short title")
        self.report_body = QTextEdit()
        self.report_body.setPlaceholderText("What happened? What did you expect? What exact steps reproduce it?")
        self.report_body.setMinimumHeight(220)
        form_layout.addWidget(QLabel("Type"), 0, 0)
        form_layout.addWidget(self.report_kind, 0, 1)
        form_layout.addWidget(QLabel("Title"), 1, 0)
        form_layout.addWidget(self.report_title, 1, 1)
        form_layout.addWidget(QLabel("Details"), 2, 0, Qt.AlignmentFlag.AlignTop)
        form_layout.addWidget(self.report_body, 2, 1)
        left_layout.addWidget(form)

        options = QGroupBox("What To Include")
        options_layout = QVBoxLayout(options)
        self.report_include_version = QCheckBox("App version and selected theme")
        self.report_include_version.setChecked(True)
        self.report_include_logs = QCheckBox("Visible app log text")
        self.report_include_logs.setChecked(True)
        self.report_include_paths = QCheckBox("Local file paths")
        self.report_include_paths.setChecked(False)
        options_layout.addWidget(self.report_include_version)
        options_layout.addWidget(self.report_include_logs)
        options_layout.addWidget(self.report_include_paths)
        note = QLabel(
            "Recommended privacy: leave local paths off. Screenshots, source images, generated JSONs, and memory dumps are never attached automatically."
        )
        note.setWordWrap(True)
        options_layout.addWidget(note)
        left_layout.addWidget(options)

        actions = QHBoxLayout()
        preview = QPushButton("Preview report")
        preview.clicked.connect(self.preview_bug_report)
        save = QPushButton("Save local report")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_bug_report)
        copy = QPushButton("Copy preview")
        copy.clicked.connect(self.copy_bug_report)
        actions.addWidget(preview)
        actions.addWidget(save)
        actions.addWidget(copy)
        left_layout.addLayout(actions)
        left_layout.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Review before sharing"))
        self.report_preview = QTextEdit()
        self.report_preview.setReadOnly(False)
        self.report_preview.setPlaceholderText("Click Preview report to build a local, redaction-friendly report.")
        right_layout.addWidget(self.report_preview, 1)
        security = QTextEdit()
        security.setReadOnly(True)
        security.setMaximumHeight(190)
        security.setPlainText(
            "Secure upload design for later:\n"
            "- App creates a redaction preview locally first.\n"
            "- Upload goes only to a private endpoint controlled by Kloudy.\n"
            "- Server owns tokens/secrets; the app never ships secrets.\n"
            "- Users can still choose manual copy/save if they do not trust upload."
        )
        right_layout.addWidget(security)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([560, 720])
        self.tabs.addTab(tab, "Bug Reports")

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
        theme_layout.addWidget(QLabel("Animated themes: Sakura Glass and Horizon Pulse."))
        theme_layout.addWidget(QLabel("Game-inspired themes: Eurocorp, Elite, CryNet, UNATCO, New Eden, Red Phosphorous, Blue Terminal 90s, and Matrix Green."))
        theme_layout.addWidget(QLabel("Blackout Violet mixes the low-glare Blackout base with a purple neon edge."))
        theme_layout.addWidget(QLabel("Blackout remains the full opaque low-glare default."))
        layout.addWidget(theme)

        generator = QGroupBox("Generator Pro Settings")
        generator_layout = QVBoxLayout(generator)
        self.custom_enabled = QCheckBox("Enable manual resolution and sample overrides")
        self.custom_enabled.setToolTip("Default uses the selected preset exactly. Enable this only when you want to override resolution and sample counts yourself.")
        self.custom_enabled.setChecked(settings_bool(self.app_settings.get("pro_generation_settings"), False))
        self.custom_enabled.stateChanged.connect(self.sync_custom_state)
        self.custom_enabled.stateChanged.connect(self.save_pro_settings_state)
        generator_layout.addWidget(self.custom_enabled)
        self.blue_terminal_dialup_enabled = QCheckBox("Blue Terminal 90s: play dial-up sound while generating")
        self.blue_terminal_dialup_enabled.setToolTip("Only affects the Blue Terminal 90s theme. The generated modem-like sound loops while generation is running and stops when it finishes.")
        self.blue_terminal_dialup_enabled.setChecked(settings_bool(self.app_settings.get("blue_terminal_dialup_sound"), False))
        self.blue_terminal_dialup_enabled.stateChanged.connect(self.save_generator_settings)
        generator_layout.addWidget(self.blue_terminal_dialup_enabled)
        layout.addWidget(generator)

        layout.addStretch()
        self.tabs.addTab(tab, "Settings")

    def save_generator_settings(self, *_args):
        if hasattr(self, "blue_terminal_dialup_enabled"):
            self.app_settings["blue_terminal_dialup_sound"] = bool(self.blue_terminal_dialup_enabled.isChecked())
            save_app_settings(self.app_settings)

    def build_bug_report_text(self) -> str:
        kind = self.report_kind.currentText() if hasattr(self, "report_kind") else "Bug"
        title = self.report_title.text().strip() if hasattr(self, "report_title") else ""
        details = self.report_body.toPlainText().strip() if hasattr(self, "report_body") else ""
        lines = [
            "# KFPS Report",
            "",
            f"Type: {kind}",
            f"Title: {title or '(not provided)'}",
            f"Created UTC: {datetime.utcnow().isoformat(timespec='seconds')}Z",
            "",
            "## User Description",
            details or "(not provided)",
            "",
        ]
        if getattr(self, "report_include_version", None) and self.report_include_version.isChecked():
            theme = self.theme_combo.currentText() if hasattr(self, "theme_combo") else self.app_settings.get("theme", DEFAULT_THEME)
            lines.extend([
                "## App Context",
                f"Version: {get_version()}",
                f"Theme: {theme}",
                f"Platform: {sys.platform}",
                "",
            ])
        if getattr(self, "report_include_logs", None) and self.report_include_logs.isChecked():
            log_text = self.log.toPlainText() if hasattr(self, "log") else ""
            if not getattr(self, "report_include_paths", None) or not self.report_include_paths.isChecked():
                log_text = re.sub(r"([A-Za-z]:\\|/home/|/Users/|\\\\)[^\n\r\t\"]+", "[local path redacted]", log_text)
            lines.extend([
                "## Visible App Log",
                "```text",
                log_text[-12000:] if log_text else "(empty)",
                "```",
                "",
            ])
        lines.extend([
            "## Privacy Notes",
            "- This report was generated locally.",
            "- No automatic upload was performed.",
            "- Screenshots, source images, generated JSONs, memory dumps, and external files are not attached automatically.",
        ])
        return "\n".join(lines)

    def preview_bug_report(self):
        self.report_preview.setPlainText(self.build_bug_report_text())
        self.log_line("Built local bug/suggestion report preview.")

    def copy_bug_report(self):
        text = self.report_preview.toPlainText().strip() or self.build_bug_report_text()
        QApplication.clipboard().setText(text)
        self.log_line("Copied local report preview to clipboard.")

    def save_bug_report(self):
        text = self.report_preview.toPlainText().strip() or self.build_bug_report_text()
        out_dir = ROOT / "runtime" / "bug-reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (self.report_title.text().strip() or "report")).strip("-")[:60]
        path = out_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe_title or 'report'}.md"
        path.write_text(text, encoding="utf-8")
        self.report_preview.setPlainText(text)
        self.log_line(f"Saved local report: {path}")

    def selected_theme_key(self) -> str:
        theme_name = self.theme_combo.currentText() if hasattr(self, "theme_combo") else self.app_settings.get("theme", DEFAULT_THEME)
        return THEMES.get(theme_name, THEMES[DEFAULT_THEME])

    def dialup_sound_enabled(self) -> bool:
        if hasattr(self, "blue_terminal_dialup_enabled"):
            return bool(self.blue_terminal_dialup_enabled.isChecked())
        return settings_bool(self.app_settings.get("blue_terminal_dialup_sound"), False)

    def start_dialup_sound_if_needed(self):
        if self.selected_theme_key() != "blue_terminal_90s":
            return
        if not self.dialup_sound_enabled():
            self.log_line("Blue Terminal 90s dial-up sound is off in Settings.")
            return
        if self.dialup_sound_thread and self.dialup_sound_thread.is_alive():
            return
        self.dialup_sound_stop_event.clear()
        self.log_line("Blue Terminal 90s dial-up sound started.")
        self.dialup_sound_thread = threading.Thread(target=self.dialup_sound_worker, daemon=True)
        self.dialup_sound_thread.start()

    def stop_dialup_sound(self):
        self.dialup_sound_stop_event.set()
        if os.name == "nt":
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:
                pass

    def dialup_wav_path(self) -> Path:
        return ROOT / "runtime" / "theme-audio" / "blue-terminal-dialup.wav"

    def ensure_dialup_wav(self) -> Path:
        path = self.dialup_wav_path()
        if path.exists() and path.stat().st_size > 1024:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 11025
        pattern = [
            (1200, 0.10),
            (0, 0.03),
            (2100, 0.08),
            (1450, 0.06),
            (900, 0.08),
            (1800, 0.12),
            (700, 0.08),
            (2300, 0.05),
            (1500, 0.10),
            (1050, 0.12),
        ]
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            phase = 0.0
            frames = bytearray()
            for frequency, seconds in pattern:
                count = max(1, int(sample_rate * seconds))
                for index in range(count):
                    if frequency <= 0:
                        sample = 0
                    else:
                        sweep = frequency + 180.0 * math.sin(index / max(1, count) * math.tau)
                        phase += math.tau * sweep / sample_rate
                        value = math.sin(phase) + 0.35 * math.sin(phase * 2.7)
                        sample = int(max(-1.0, min(1.0, value * 0.42)) * 32767)
                    frames.extend(struct.pack("<h", sample))
            wav.writeframes(bytes(frames))
        return path

    def dialup_sound_worker(self):
        if os.name != "nt":
            return
        try:
            import winsound
            path = self.ensure_dialup_wav()
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            while not self.dialup_sound_stop_event.is_set():
                time.sleep(0.1)
            winsound.PlaySound(None, 0)
        except Exception as exc:
            self.bus.log.emit(f"Blue Terminal 90s dial-up sound failed: {exc}")
            return

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
                QPushButton#kofiButton { background: #ffffff; color: #7f3d58; border: 1px solid #d65f89; border-radius: 8px; padding: 2px 10px; font-weight: 900; min-height: 18px; max-height: 24px; }
                QPushButton#kofiButton:hover { background: #fff0f6; color: #a83f67; border-color: #a83f67; }
                QLabel#kofiOptionalLabel { color: #7f3d58; font-size: 8pt; font-weight: 800; }
                QFrame#editorWipPanel { background: rgba(255, 240, 246, 180); border: 3px dashed #ff1010; border-radius: 18px; }
                QLabel#editorWipText { color: #7f1720; font-size: 14pt; font-weight: 900; padding: 8px 28px 28px 28px; }
                QToolButton#helpButton { background: #7f3d58; color: #ffffff; border: 1px solid #fffafa; border-radius: 12px; font-weight: 900; }
                QToolButton#helpButton:hover { background: #a83f67; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #fffdfd; color: #332534; border: 2px solid #b77b8f; border-radius: 9px; padding: 6px; selection-background-color: #d65f89; selection-color: white; }
                QComboBox { padding-right: 30px; }
                QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #b77b8f; border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: #f3c7d6; }
                QComboBox QAbstractItemView { background: #fffdfd; color: #332534; border: 2px solid #b77b8f; selection-background-color: #d65f89; selection-color: white; outline: 0; }
                QScrollArea, QAbstractScrollArea { background: transparent; border: none; }
                QCheckBox { spacing: 8px; color: #332534; }
                QLabel { color: #332534; background: transparent; }
                """
            )
        elif theme_key == "horizon":
            self.setStyleSheet(
                """
                QMainWindow { background: #050914; color: #e8fbff; font-family: "Segoe UI Variable", "Segoe UI"; font-size: 10pt; }
                QWidget#appRoot { background: transparent; }
                QTabWidget::pane { border: 1px solid rgba(36, 233, 255, 150); border-radius: 16px; background: rgba(5, 9, 20, 218); }
                QTabBar::tab { background: rgba(8, 22, 35, 225); color: #8bdfff; padding: 10px 18px; border: 1px solid rgba(36, 233, 255, 90); border-bottom: none; border-top-left-radius: 12px; border-top-right-radius: 12px; margin-right: 4px; font-weight: 800; }
                QTabBar::tab:hover { background: rgba(15, 48, 70, 236); color: #ffffff; border-color: rgba(255, 74, 43, 160); }
                QTabBar::tab:selected { background: rgba(8, 15, 28, 245); color: #ffffff; border-color: rgba(36, 233, 255, 210); }
                QGroupBox { border: 1px solid rgba(36, 233, 255, 130); border-radius: 16px; margin-top: 14px; padding: 12px; background: rgba(7, 13, 25, 226); font-weight: 800; color: #24e9ff; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 9px; background: rgba(7, 13, 25, 245); color: #ff8b52; border-radius: 7px; }
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(11, 45, 67, 245), stop:1 rgba(17, 18, 31, 245)); color: #effcff; border: 1px solid rgba(36, 233, 255, 150); border-radius: 11px; padding: 8px 14px; font-weight: 800; min-height: 28px; }
                QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(23, 77, 99, 252), stop:1 rgba(56, 22, 27, 252)); border-color: #ff4a2b; color: #ffffff; }
                QPushButton:pressed { background: #050914; border-color: #ffffff; }
                QPushButton#primaryButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4a2b, stop:0.52 #ffb000, stop:1 #24e9ff); color: #07101a; border: 1px solid #ffffff; font-weight: 950; padding: 12px 16px; }
                QPushButton#primaryButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff6b42, stop:0.50 #ffd166, stop:1 #6df6ff); color: #020407; }
                QPushButton#kofiButton { background: rgba(36, 233, 255, 42); color: #e8fbff; border: 1px solid rgba(36, 233, 255, 150); border-radius: 8px; padding: 2px 10px; font-weight: 950; min-height: 18px; max-height: 24px; }
                QPushButton#kofiButton:hover { background: rgba(255, 74, 43, 130); color: #ffffff; border-color: #ffb000; }
                QLabel#kofiOptionalLabel { color: #ffb000; font-size: 8pt; font-weight: 900; }
                QFrame#editorWipPanel { background: rgba(40, 0, 0, 150); border: 3px dashed #ff1010; border-radius: 18px; }
                QLabel#editorWipText { color: #ffd1d1; font-size: 14pt; font-weight: 900; padding: 8px 28px 28px 28px; }
                QToolButton#helpButton { background: #24e9ff; color: #07101a; border: 1px solid #ffffff; border-radius: 12px; font-weight: 950; }
                QToolButton#helpButton:hover { background: #ffb000; color: #020407; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: rgba(2, 7, 14, 238); color: #e8fbff; border: 1px solid rgba(36, 233, 255, 135); border-radius: 9px; padding: 6px; selection-background-color: #ff4a2b; selection-color: #ffffff; }
                QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTextEdit:focus, QTreeWidget:focus { border: 1px solid #ffb000; }
                QComboBox { padding-right: 30px; }
                QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid rgba(36, 233, 255, 130); border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: rgba(255, 74, 43, 190); }
                QComboBox QAbstractItemView { background: #050914; color: #e8fbff; border: 1px solid #24e9ff; selection-background-color: #ff4a2b; selection-color: #ffffff; outline: 0; }
                QGraphicsView { background: rgba(2, 7, 14, 236); border: 1px solid rgba(36, 233, 255, 115); border-radius: 10px; }
                QScrollArea, QAbstractScrollArea { background: transparent; border: none; }
                QCheckBox { spacing: 8px; color: #e8fbff; background: transparent; }
                QLabel { color: #e8fbff; background: transparent; }
                QLabel#updateAlarm { background: transparent; color: #19ff7f; border: none; padding: 0; font-weight: 900; }
                QHeaderView::section { background: rgba(7, 13, 25, 245); color: #24e9ff; border: 1px solid rgba(36, 233, 255, 90); padding: 5px; font-weight: 800; }
                QScrollBar:vertical, QScrollBar:horizontal { background: rgba(2, 7, 14, 170); border: none; width: 13px; height: 13px; }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #18556f; border-radius: 6px; min-height: 24px; min-width: 24px; }
                QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #ff4a2b; }
                QScrollBar::add-line, QScrollBar::sub-line { background: transparent; border: none; width: 0; height: 0; }
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
                QPushButton#kofiButton { background: #000000; color: #dcdcdc; border: 1px solid #343434; border-radius: 8px; padding: 2px 10px; font-weight: 900; min-height: 18px; max-height: 24px; }
                QPushButton#kofiButton:hover { background: #101010; color: #ffffff; border-color: #777777; }
                QLabel#kofiOptionalLabel { color: #bdbdbd; font-size: 8pt; font-weight: 800; }
                QFrame#editorWipPanel { background: #050000; border: 3px dashed #ff1010; border-radius: 18px; }
                QLabel#editorWipText { color: #ffbdbd; font-size: 14pt; font-weight: 900; padding: 8px 28px 28px 28px; }
                QToolButton#helpButton { background: #ffffff; color: #000000; border: 1px solid #ffffff; border-radius: 12px; font-weight: 950; }
                QToolButton#helpButton:hover { background: #d0d0d0; }
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
        elif theme_key in THEME_TOKEN_STYLES:
            self.setStyleSheet(token_theme_stylesheet(THEME_TOKEN_STYLES[theme_key]))
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
                QPushButton#kofiButton { background: #fffdf8; color: #6c3fa0; border: 1px solid #c7a8ea; border-radius: 8px; padding: 2px 10px; font-weight: 900; min-height: 18px; max-height: 24px; }
                QPushButton#kofiButton:hover { background: #f7eefe; color: #9f6ad8; border-color: #9f6ad8; }
                QLabel#kofiOptionalLabel { color: #6c3fa0; font-size: 8pt; font-weight: 800; }
                QFrame#editorWipPanel { background: #fff8fb; border: 3px dashed #ff1010; border-radius: 18px; }
                QLabel#editorWipText { color: #7f1720; font-size: 14pt; font-weight: 900; padding: 8px 28px 28px 28px; }
                QToolButton#helpButton { background: #9f6ad8; color: white; border: 1px solid #ffffff; border-radius: 12px; font-weight: 900; }
                QToolButton#helpButton:hover { background: #7b4eb0; }
                QLineEdit, QComboBox, QListWidget, QTextEdit, QTreeWidget { background: #fffdf8; color: #3b244d; border: 1px solid #d8c2f0; border-radius: 8px; padding: 6px; selection-background-color: #cfa8ff; }
                QComboBox { padding-right: 30px; }
                QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border-left: 1px solid #d8c2f0; border-top-right-radius: 7px; border-bottom-right-radius: 7px; background: #eadcff; }
                QComboBox QAbstractItemView { background: #fffdf8; color: #3b244d; border: 1px solid #d8c2f0; selection-background-color: #cfa8ff; selection-color: #3b244d; outline: 0; }
                QCheckBox { spacing: 8px; }
                QLabel { color: #3b244d; }
                """
            )
        self.setStyleSheet(self.styleSheet() + SHELL_QSS + shell_theme_qss(theme_key))
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
        self.update_alarm_scale = 1.0
        if state == "available":
            match = re.search(r"main\s+([0-9][0-9A-Za-z_.-]*)", text)
            remote_version = match.group(1) if match else ""
            distance = version_update_distance(local_app_version(), remote_version)
            self.update_alarm_scale = min(3.0, 1.25 ** max(0, distance))
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
        font_size = 9
        if state == "available":
            font_size = max(9, int(round(9 * self.update_alarm_scale)))
        base_style = f"QLabel#updateAlarm {{ background: transparent; border: none; padding: 0; font-weight: 900; font-size: {font_size}pt; }}"
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
        self.position_update_alarm()

    def position_update_alarm(self):
        if not hasattr(self, "update_alarm") or not hasattr(self, "background_widget"):
            return
        parent = self.background_widget
        width = max(1, parent.width())
        font_height = max(18, int(24 * getattr(self, "update_alarm_scale", 1.0)))
        y = 46
        if hasattr(self, "phase_label"):
            y = max(8, self.phase_label.geometry().bottom() - 8)
        self.update_alarm.setGeometry(0, y, width, font_height)
        self.update_alarm.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_update_alarm()

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

    def on_profile_changed(self):
        self.update_setting_description()
        self.sync_auto_summary()

    def current_custom_values(self):
        values = {
            "stopAt": self.custom_layers.text(),
            "saveAt": self.custom_save_at.text(),
            "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
            "v2EnableRepair": "true" if self.repair_enabled.isChecked() else "false",
        }
        values.update(self.detail_heatmap_values())
        if self.custom_enabled.isChecked():
            values.update({
                "maxResolution": self.custom_resolution.text(),
                "randomSamples": self.custom_random.text(),
                "mutatedSamples": self.custom_mutated.text(),
            })
        return values

    def detail_heatmap_values(self):
        return {
            "detailHeatmapMode": "auto" if self.detail_heatmap_enabled.isChecked() else "off",
            "detailHeatmapStrength": "0.10",
        }

    def pro_custom_values(self):
        if not self.custom_enabled.isChecked():
            return {}
        return self.raw_pro_field_values()

    def raw_pro_field_values(self):
        return {
            "maxResolution": self.custom_resolution.text(),
            "randomSamples": self.custom_random.text(),
            "mutatedSamples": self.custom_mutated.text(),
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
        if self.vroom.isChecked():
            description += "\n2x Sample Goblin doubles random samples and mutated samples. It is usually slower; output layers and resolution stay unchanged."
        if item.get("is_user_preset"):
            description += "\nThis is a saved custom preset stored in runtime/user-presets."
        self.setting_description.setText(description)
        self.custom_layers.setText(values.get("stopAt", "3000"))
        self.custom_save_at.setText(values.get("saveAt", values.get("stopAt", "3000")))
        self.luma_enabled.setChecked(str(values.get("v2PreprocessMode", "none")).strip().lower() == "luma_bands")
        self.repair_enabled.setChecked(str(values.get("v2EnableRepair", "true")).strip().lower() in ("1", "true", "yes", "on"))
        if not self.custom_enabled.isChecked():
            self.custom_resolution.setText(values.get("maxResolution", "1200"))
            self.custom_random.setText(values.get("randomSamples", "3000"))
            self.custom_mutated.setText(values.get("mutatedSamples", "1000"))
        self.sync_auto_summary()

    def sync_custom_state(self):
        pro = self.custom_enabled.isChecked()
        for widget in getattr(self, "pro_setting_widgets", []):
            widget.setVisible(pro)
            widget.setEnabled(pro)
        for widget in getattr(self, "pro_setting_labels", []):
            widget.setVisible(pro)
        for widget in getattr(self, "pro_action_widgets", []):
            widget.setVisible(pro)
        self.custom_layers.setEnabled(True)
        self.custom_save_at.setEnabled(True)
        self.sync_auto_summary()

    def save_pro_settings_state(self):
        if not hasattr(self, "app_settings") or not hasattr(self, "custom_enabled"):
            return
        self.app_settings["pro_generation_settings"] = bool(self.custom_enabled.isChecked())
        self.app_settings["generation_pro_values"] = self.raw_pro_field_values()
        save_app_settings(self.app_settings)

    def save_pro_field_values(self):
        if not hasattr(self, "app_settings"):
            return
        self.app_settings["generation_pro_values"] = self.raw_pro_field_values()
        save_app_settings(self.app_settings)

    def enable_custom_tuning_from_edit(self, _text=None):
        if not self.custom_enabled.isChecked():
            self.custom_enabled.setChecked(True)

    def custom_fields_differ_from_setting(self, values):
        checks = (
            ("stopAt", self.custom_layers),
            ("saveAt", self.custom_save_at),
        )
        if self.custom_enabled.isChecked():
            checks += (
                ("maxResolution", self.custom_resolution),
                ("randomSamples", self.custom_random),
                ("mutatedSamples", self.custom_mutated),
            )
        for key, widget in checks:
            current = str(widget.text()).strip()
            if not current:
                continue
            preset = str(values.get(key, "")).strip()
            if key == "saveAt" and not preset:
                preset = str(values.get("stopAt", "")).strip()
            if current != preset:
                return True
        return False

    def selected_setting(self):
        if hasattr(self, "profile_combo"):
            item = self.profile_combo.currentData()
            if item:
                return item
        return self.settings[0] if self.settings else None

    def vroom_boost_overrides(self, values):
        if not self.vroom.isChecked():
            return {}
        overrides = {}
        for key in ("randomSamples", "mutatedSamples", "maxNoImproveRetries"):
            value = values.get(key)
            text = str(value).strip()
            if re.fullmatch(r"-?\d+", text) and int(text) > 0:
                overrides[key] = str(int(text) * 2)
        return overrides

    def effective_setting(self, image_path=None):
        setting = self.selected_setting()
        if not setting:
            return None
        return self.effective_setting_from_snapshot(
            setting,
            image_path,
            ui_overrides={
                "stopAt": self.custom_layers.text(),
                "saveAt": self.custom_save_at.text(),
                "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
                "v2EnableRepair": "true" if self.repair_enabled.isChecked() else "false",
                **self.detail_heatmap_values(),
            },
            pro_overrides=self.pro_custom_values(),
            sample_boost=self.vroom.isChecked(),
        )

    def effective_setting_from_snapshot(self, setting, image_path=None, ui_overrides=None, pro_overrides=None, sample_boost=False):
        setting_values = dict(setting.get("values", {}))
        overrides = ui_overrides or {
            "stopAt": self.custom_layers.text(),
            "saveAt": self.custom_save_at.text(),
            "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
            "v2EnableRepair": "true" if self.repair_enabled.isChecked() else "false",
            **self.detail_heatmap_values(),
        }
        base_values = dict(setting_values)
        base_values.update({key: value for key, value in overrides.items() if str(value).strip()})
        if image_path is not None:
            tuned_values, auto_summary = auto_generation_values(
                image_path,
                base_values,
                pro_overrides=pro_overrides or {},
                sample_boost=sample_boost,
            )
        else:
            tuned_values = base_values
            tuned_values.update(pro_overrides or {})
            if sample_boost:
                for key in ("randomSamples", "mutatedSamples", "maxNoImproveRetries"):
                    value = tuned_values.get(key)
                    text = str(value).strip()
                    if re.fullmatch(r"-?\d+", text) and int(text) > 0:
                        tuned_values[key] = str(int(text) * 2)
            auto_summary = None
        boosted = write_custom_settings(setting, tuned_values)
        boosted["label"] = setting.get("label", boosted.get("label"))
        boosted["auto_tune"] = auto_summary
        if sample_boost:
            boosted["vroom_boost"] = True
        return boosted

    def sync_auto_summary(self):
        if not hasattr(self, "auto_summary_label"):
            return
        image_path = None
        if getattr(self, "images", None):
            row = self.image_list.currentRow() if hasattr(self, "image_list") else 0
            if not (0 <= row < len(self.images)):
                row = 0
            image_path = self.images[row]
        setting = self.selected_setting()
        if not image_path or not setting:
            self.auto_summary_label.setText("Preset settings are fixed. Source image metrics are shown for context only.")
            return
        values = dict(setting.get("values", {}))
        values.update({
            "stopAt": self.custom_layers.text(),
            "saveAt": self.custom_save_at.text(),
            "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
            "v2EnableRepair": "true" if self.repair_enabled.isChecked() else "false",
            **self.detail_heatmap_values(),
        })
        try:
            tuned, summary = auto_generation_values(
                image_path,
                values,
                pro_overrides=self.pro_custom_values(),
                sample_boost=self.vroom.isChecked(),
            )
            source = summary.get("source", {})
            self.auto_summary_label.setText(
                "Preset effort: "
                f"{source.get('width', '?')}x{source.get('height', '?')}, "
                f"{source.get('megapixels', '?')} MP, visible {source.get('alpha_coverage', '?')}. "
                f"Using max res {tuned.get('maxResolution')}, random {tuned.get('randomSamples')}, "
                f"mutated {tuned.get('mutatedSamples')}."
            )
        except Exception as exc:
            self.auto_summary_label.setText(f"Preset settings preview unavailable: {type(exc).__name__}: {exc}")

    def update_source_check_banner(self, image_path: Path | None = None):
        if not hasattr(self, "source_check_label"):
            return
        if image_path is None:
            if getattr(self, "images", None):
                row = self.image_list.currentRow() if hasattr(self, "image_list") else 0
                if not (0 <= row < len(self.images)):
                    row = 0
                image_path = self.images[row]
        if image_path is None:
            self.source_check_label.setText("Source Check - Choose an image.")
            self.source_check_label.setStyleSheet(
                "QLabel { color: #666666; background: rgba(128,128,128,24); border: 1px solid rgba(128,128,128,90); "
                "border-radius: 10px; padding: 8px; font-weight: 800; }"
            )
            return
        try:
            check = source_sanity_check(image_path)
            severity = check.get("severity", "warn")
            colors = {
                "ok": ("#083d1b", "#c9f7d7", "#27b45b"),
                "warn": ("#4d3300", "#fff1bf", "#d89b00"),
                "bad": ("#5a0710", "#ffd4da", "#e53a4d"),
            }
            fg, bg, border = colors.get(severity, colors["warn"])
            messages = check.get("messages") or ["No source details available."]
            text = f"{check.get('title', 'Source Check')} - " + " ".join(messages[:3])
            if len(messages) > 3:
                text += f" +{len(messages) - 3} more."
            self.source_check_label.setText(text)
            self.source_check_label.setStyleSheet(
                f"QLabel {{ color: {fg}; background: {bg}; border: 2px solid {border}; "
                "border-radius: 10px; padding: 8px; font-weight: 900; }}"
            )
        except Exception as exc:
            self.source_check_label.setText(f"Source Check - unavailable ({type(exc).__name__}: {exc})")
            self.source_check_label.setStyleSheet(
                "QLabel { color: #4d3300; background: #fff1bf; border: 2px solid #d89b00; "
                "border-radius: 10px; padding: 8px; font-weight: 900; }"
            )

    def add_image(self):
        USER_IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
        file_names, _ = QFileDialog.getOpenFileNames(self, "Choose source image(s)", str(USER_IMAGES_ROOT), "Images (*.png *.jpg *.jpeg *.bmp);;All files (*.*)")
        if not file_names:
            return
        self.images = [Path(file_name) for file_name in file_names]
        self.render_lists()
        self.image_list.setCurrentRow(0)
        self.detail_heatmap_preview_active = False
        self.preview_heatmap_button.setText("Preview heatmap")
        self.show_preview_bytes(render_source_image(self.images[0]) or b"")
        self.update_source_check_banner(self.images[0])
        self.sync_auto_summary()

    def preview_detail_heatmap(self):
        if not self.images:
            self.log_line("Detail Heatmap preview needs a source image first.")
            return
        row = self.image_list.currentRow() if hasattr(self, "image_list") else 0
        if not (0 <= row < len(self.images)):
            row = 0
        source = self.images[row]
        try:
            if self.detail_heatmap_preview_active:
                self.preview.set_bytes(render_source_image(source) or b"")
                self.detail_heatmap_preview_active = False
                self.preview_heatmap_button.setText("Preview heatmap")
                self.log_line(f"Source preview: {source.name}")
            else:
                self.preview.set_bytes(detail_heatmap_preview_bytes(source))
                self.detail_heatmap_preview_active = True
                self.preview_heatmap_button.setText("Show source")
                self.log_line(f"Detail Heatmap preview: {source.name}")
        except Exception as exc:
            self.log_line(f"Detail Heatmap preview failed: {type(exc).__name__}: {exc}")

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

    def choose_size_helper_image(self):
        USER_IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose image for size helper", str(USER_IMAGES_ROOT), "Images (*.png *.jpg *.jpeg *.bmp);;All files (*.*)")
        if not file_name:
            return
        source = Path(file_name)
        self.size_helper_preview.set_bytes(render_source_image(source) or b"")
        image = decode_image_file(source)
        if image is None:
            self.size_helper_status.setText(f"Could not read image: {source}")
            self.size_helper_table.clear()
            return
        height, width = image.shape[:2]
        megapixels = (width * height) / 1_000_000.0
        self.size_helper_status.setText(f"{source.name}: {width} x {height} px, {megapixels:.2f} MP")
        self.size_helper_table.clear()
        aspect = width / max(1, height)
        for target_mp in range(1, 7):
            target_pixels = target_mp * 1_000_000
            target_width = max(1, int(round(math.sqrt(target_pixels * aspect))))
            target_height = max(1, int(round(target_width / aspect)))
            actual_mp = (target_width * target_height) / 1_000_000.0
            self.size_helper_table.addTopLevelItem(
                QTreeWidgetItem([
                    f"{target_mp} MP",
                    f"{target_width:,} px",
                    f"{target_height:,} px",
                    f"{actual_mp:.2f} MP",
                ])
            )
        self.log_line(f"Image Size Helper: {source.name} is {width}x{height}, {megapixels:.2f} MP")

    def manual_add_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Choose vinyl JSON", "", "Vinyl JSON (*.json);;All files (*.*)")
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
            self.set_phase("done", "Ready to import JSON.")
        elif text == "Failed":
            self.set_phase("failed", "Something failed. Check the log below for the exact error.")
        elif text == "Stopping":
            self.set_phase("finalizing", "Stop requested. Waiting for the latest checkpoint to finalize.")
        elif text == "Importing":
            self.set_phase("importing", "Writing the selected JSON into FH6. Do not switch menus.")

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
            return ("done", "Finalized JSONs are ready. Go to Import JSON.")
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
        if not Path(path).exists():
            return
        self.preview.set_file(path)
        self.import_preview.set_file(path)

    def preview_selected_image(self, row: int):
        if 0 <= row < len(self.images):
            self.preview_request_id += 1
            if hasattr(self, "detail_heatmap_preview_active"):
                self.detail_heatmap_preview_active = False
            if hasattr(self, "preview_heatmap_button"):
                self.preview_heatmap_button.setText("Preview heatmap")
            self.show_preview_bytes(render_source_image(self.images[row]) or b"")
            self.update_source_check_banner(self.images[row])
            self.sync_auto_summary()

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
        match = re.match(r"^(.*)\.([A-Za-z0-9_-]+)v2\.json$", name)
        if match:
            base, tag = match.groups()
            candidates = [
                preview_dir / f"{base}.preview.{tag}v2.png",
                path.with_name(f"{base}.preview.{tag}v2.png"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
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
        if hasattr(self, "export_pid_combo"):
            combos.append(self.export_pid_combo)
        game_combos = [self.game_combo]
        if hasattr(self, "export_game_combo"):
            game_combos.append(self.export_game_combo)
        selected_games = {combo: combo.currentText() for combo in game_combos}
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
        if self.processes:
            for item in self.processes:
                for combo in combos:
                    combo.addItem(item["label"], item)
            for game_combo in game_combos:
                preferred = selected_games.get(game_combo)
                game_combo.setCurrentText(preferred if preferred in PROFILES else "fh6")
        else:
            for combo in combos:
                combo.addItem("No supported game process detected", None)
        for combo in combos:
            combo.blockSignals(False)
        self.sync_game_from_pid_combo(self.pid_combo, self.game_combo)
        if hasattr(self, "export_pid_combo") and hasattr(self, "export_game_combo"):
            self.sync_game_from_pid_combo(self.export_pid_combo, self.export_game_combo)
        self.update_game_compatibility_notices()

    def sync_game_from_pid_combo(self, pid_combo: QComboBox, game_combo: QComboBox):
        data = pid_combo.currentData()
        if data and data.get("profile") in PROFILES:
            game_combo.setCurrentText(data["profile"])

    def update_game_compatibility_notices(self):
        if hasattr(self, "import_game_notice"):
            self.import_game_notice.setVisible((self.game_combo.currentText() or "").strip().lower() == "fh5")
        if hasattr(self, "export_game_notice") and hasattr(self, "export_game_combo"):
            self.export_game_notice.setVisible((self.export_game_combo.currentText() or "").strip().lower() == "fh5")

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

    def selected_game_value(self, combo: QComboBox | None = None) -> str:
        combo = combo or self.game_combo
        game = (combo.currentText() or "fh6").strip().lower()
        return game if game in PROFILES else "fh6"

    def start_generate(self):
        if not self.images:
            self.log_line("No image selected.")
            return
        setting = self.selected_setting()
        if not setting:
            self.log_line("No Kloudy preset selected.")
            return
        if not GENERATOR_EXE.exists():
            self.log_line(f"Missing generator: {GENERATOR_EXE}")
            return
        images = list(self.images)
        setting_snapshot = dict(setting)
        setting_snapshot["values"] = dict(setting.get("values", {}))
        ui_overrides = {
            "stopAt": self.custom_layers.text(),
            "saveAt": self.custom_save_at.text(),
            "v2PreprocessMode": "luma_bands" if self.luma_enabled.isChecked() else "none",
            "v2EnableRepair": "true" if self.repair_enabled.isChecked() else "false",
        }
        ui_overrides.update(self.detail_heatmap_values())
        pro_overrides = self.pro_custom_values()
        sample_boost = self.vroom.isChecked()
        repair_enabled = self.repair_enabled.isChecked()
        self.shutdown_event.clear()
        self.stop_generation_event.clear()
        self.preview_request_id += 1
        self.active_generation_images = images
        self.current_generation_image = None
        self.set_status("Running")
        if len(images) > 1:
            self.log_line(f"Batch generation queued: {len(images)} image(s). Same selected settings will be used one after another.")
            self.set_phase("building", f"Batch generation queued: 1/{len(images)} starting. Final import JSONs are not ready yet.")
        else:
            self.set_phase("building", "Starting internal build. Final import JSONs are not ready yet.")
        self.start_dialup_sound_if_needed()
        threading.Thread(
            target=self.generate_worker,
            args=(setting_snapshot, images, repair_enabled, ui_overrides, pro_overrides, sample_boost),
            daemon=True,
        ).start()

    def stop_generate(self):
        if not self.active_generation_images:
            self.log_line("No active generation job to stop.")
            return
        self.stop_generation_event.set()
        current = self.current_generation_image
        targets = [current] if current is not None else list(self.active_generation_images[:1])
        for image_path in targets:
            try:
                stop_path = generator_stop_request_path(image_path, self.active_generation_run_dirs.get(image_path))
                stop_path.parent.mkdir(parents=True, exist_ok=True)
                stop_path.write_text("stop\n", encoding="utf-8")
            except Exception as exc:
                self.log_line(f"Failed to request stop for {image_path.name}: {exc}")
        self.set_status("Stopping")
        self.log_line("Stop requested. Finalize Checkpoints will finish the current image, then the batch will stop.")

    def generate_worker(self, setting, images, repair_enabled, ui_overrides, pro_overrides, sample_boost):
        failures = 0
        try:
            self.bus.log.emit(f"Selected Kloudy preset: {setting.get('label') or setting['path'].name}")
            self.bus.log.emit("Preset settings: resolution and samples are fixed by the selected preset unless Pro settings are enabled.")
            self.bus.log.emit(f"Edge Repair: {'on' if repair_enabled else 'off'}")
            total_images = len(images)
            for index, image_path in enumerate(images, start=1):
                if self.stop_generation_event.is_set():
                    self.bus.log.emit("Batch stopped before starting the next image.")
                    break
                self.current_generation_image = image_path
                self.active_generation_images = list(images[index - 1 :])
                if total_images > 1:
                    self.bus.log.emit(f"Batch item {index}/{total_images}: {image_path.name}")
                    self.bus.phase.emit("building", f"Batch generation running: {index}/{total_images}. Final import JSONs are not ready yet.")
                effective = self.effective_setting_from_snapshot(
                    setting,
                    image_path,
                    ui_overrides=ui_overrides,
                    pro_overrides=pro_overrides,
                    sample_boost=sample_boost,
                )
                if not effective:
                    self.bus.log.emit("Generator failed: no effective preset could be built.")
                    failures += 1
                    if total_images <= 1:
                        return
                    continue
                values = effective.get("values", {})
                self.reset_generation_eta()
                run_dir = next_generator_output_dir(image_path)
                before = {path.resolve() for path in self.run_json_files(run_dir)}
                self.latest_generated_run_dir = run_dir
                self.active_generation_run_dirs[image_path] = run_dir
                self.bus.log.emit(f"Generating final vinyl from: {image_path}")
                self.bus.log.emit(f"Vinyl run folder: {run_dir}")
                self.bus.log.emit(f"Target template layers: {values.get('stopAt', 'n/a')}")
                self.bus.log.emit(f"Finalize at layers: {values.get('saveAt', values.get('stopAt', 'n/a'))}")
                self.bus.log.emit(f"Preset effort: maxRes={values.get('maxResolution', 'n/a')} random={values.get('randomSamples', 'n/a')} mutated={values.get('mutatedSamples', 'n/a')}")
                self.bus.log.emit(f"Detail Heatmap: {values.get('detailHeatmapMode', 'off')}")
                auto_summary = effective.get("auto_tune") or {}
                source_summary = auto_summary.get("source") or {}
                if source_summary:
                    self.bus.log.emit(
                        "Source metrics: "
                        f"{source_summary.get('width', '?')}x{source_summary.get('height', '?')}, "
                        f"{source_summary.get('megapixels', '?')} MP, "
                        f"visible={source_summary.get('alpha_coverage', '?')}, "
                        f"edge={source_summary.get('edge_density', '?')}"
                    )
                self.bus.log.emit(f"Luma Prep: {values.get('v2PreprocessMode', 'none')}")
                src = render_source_image(image_path)
                if src:
                    self.bus.preview_bytes.emit(src)
                cmd = build_generator_command(image_path, effective, enable_repair=repair_enabled, enable_overshoot=False, output_dir=run_dir)
                self.bus.log.emit(f"Running patched vinyl builder with {effective['path'].name}")
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
                        mtime = self.safe_path_mtime(newest)
                        if mtime is None:
                            continue
                        if mtime != last_preview_mtime:
                            last_preview_mtime = mtime
                            self.bus.preview_file.emit(str(newest))
                    time.sleep(0.1)
                self.unregister_process(proc)
                last_message = self.drain_generator_output(output_queue, last_message)
                if proc.returncode != 0:
                    failures += 1
                    self.bus.log.emit(f"Generator exited with code {proc.returncode} for {image_path.name}.")
                    if total_images <= 1:
                        self.bus.status.emit("Failed")
                        return
                    continue
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
                    mtime = self.safe_path_mtime(newest)
                    if mtime is not None and mtime != last_preview_mtime:
                        self.bus.preview_file.emit(str(newest))
                if self.stop_generation_event.is_set():
                    self.bus.log.emit(f"Stopped after finalizing {image_path.name}.")
                    break
            self.bus.refresh_lists.emit()
            self.bus.generated_changed.emit()
            self.bus.status.emit("Failed" if failures and failures >= total_images else "Done")
        except Exception as exc:
            self.bus.log.emit(f"Generator failed: {exc}")
            self.bus.status.emit("Failed")
        finally:
            self.stop_dialup_sound()
            self.active_generation_images = []
            self.active_generation_run_dirs = {}
            self.current_generation_image = None

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
                return self.format_step_progress_with_eta(int(current), int(total), int(step_done.group(1)))
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
            "Detail Heatmap:",
            "Detail-guided image:",
            "Source profile:",
            "Source recommendation:",
            "Preprocessed image:",
            "Canvas boundary:",
            "V5 detail weighting:",
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

    def reset_generation_eta(self):
        self.generation_eta_state = {"total": None, "ema_ms": None, "last_current": 0}

    def format_step_progress_with_eta(self, current: int, total: int, step_ms: int) -> str:
        state = self.generation_eta_state
        if state.get("total") != total or current <= 1 or current < int(state.get("last_current") or 0):
            state["total"] = total
            state["ema_ms"] = float(step_ms)
        else:
            previous = float(state.get("ema_ms") or step_ms)
            state["ema_ms"] = previous * 0.88 + float(step_ms) * 0.12
        state["last_current"] = current

        remaining = max(total - current, 0)
        if remaining <= 0:
            return f"Step {current}/{total} completed in {step_ms}ms | ETA done"
        eta_seconds = int(round((float(state["ema_ms"]) * remaining) / 1000.0))
        return f"Step {current}/{total} completed in {step_ms}ms | ETA {self.format_eta_duration(eta_seconds)}"

    @staticmethod
    def format_eta_duration(seconds: int) -> str:
        seconds = max(int(seconds), 0)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

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
        filtered = []
        seen = set()
        for path in candidates:
            if ".v2.preprocess." in path.name:
                continue
            if path in seen:
                continue
            mtime = self.safe_path_mtime(path)
            if mtime is None:
                continue
            seen.add(path)
            filtered.append((path, mtime))
        return [path for path, _mtime in sorted(filtered, key=lambda item: item[1], reverse=True)]

    @staticmethod
    def safe_path_mtime(path: Path) -> float | None:
        try:
            return Path(path).stat().st_mtime
        except OSError:
            return None

    def cached_geometry_shape_count(self, path: Path) -> int:
        path = Path(path)
        try:
            stat = path.stat()
        except OSError:
            return 0
        key = str(path.resolve())
        cached = self.geometry_count_cache.get(key)
        fingerprint = (int(stat.st_mtime_ns), int(stat.st_size))
        if cached and cached[:2] == fingerprint:
            return cached[2]
        try:
            count = geometry_shape_count(path)
        except Exception:
            count = 0
        if count <= 0:
            try:
                count = import_json_shape_count(path)
            except Exception:
                count = 0
        self.geometry_count_cache[key] = (fingerprint[0], fingerprint[1], count)
        return count

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
        match = re.search(r"\.([A-Za-z0-9_-]+)v2\.json$", name)
        if match:
            tag = match.group(1)
            label = "Final" if tag.lower() == "final" else f"{tag} checkpoint"
            return (10**9, 1, label)
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
                if path.parent.name == "finals" or self.is_v2_output_json(path):
                    candidates.add(path.resolve())
        return candidates

    def folder_json_candidates(self, root: Path, source_label: str, preset_label: str, *, group_by_folder: bool = False) -> list[dict]:
        entries = []
        if not root.exists():
            return entries
        paths = [
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() == ".json"
        ]
        for path in sorted(paths, key=lambda item: self.safe_path_mtime(item) or 0, reverse=True):
            if is_internal_generator_json(path):
                continue
            count = self.cached_geometry_shape_count(path)
            folder = path.parent
            try:
                run_mtime = path.stat().st_mtime
            except OSError:
                run_mtime = self.safe_path_mtime(path) or 0
            run_folder = folder
            if group_by_folder:
                try:
                    rel = path.relative_to(root)
                    if len(rel.parts) > 1:
                        run_folder = root / rel.parts[0]
                except ValueError:
                    run_folder = folder
            source = run_folder.name if group_by_folder else path.stem
            entries.append({
                "path": path.resolve(),
                "source": source,
                "folder": self.checkpoint_folder_label(path),
                "run_folder": run_folder,
                "run_key": str(run_folder.resolve() if group_by_folder else path.resolve()),
                "run_mtime": run_mtime,
                "checkpoint": path.stem,
                "step_number": count,
                "step_variant": 0,
                "type": source_label,
                "layers": count,
                "import_safe": True,
                "import_budget": None,
                "recommended": False,
                "tags": [source_label.replace(" JSON", "")],
                "error": None,
                "preset": preset_label,
                "source_image": None,
            })
        entries.sort(key=lambda item: (-item["run_mtime"], -int(item.get("layers") or 0), item["path"].name.lower()))
        return entries

    def handmade_json_candidates(self) -> list[dict]:
        return self.folder_json_candidates(HANDMADE_JSON_ROOT, "Handmade JSON", "handmade/downloaded")

    def editor_json_candidates(self) -> list[dict]:
        return self.folder_json_candidates(EDITOR_JSON_ROOT, "Editor JSON", "fabric editor", group_by_folder=True)

    def is_v2_output_json(self, path):
        path = Path(path)
        name = path.name.lower()
        return bool(
            path.parent.name == "finals"
            or ".v2.final." in name
            or re.search(r"\.[a-z0-9_-]+v2\.json$", name)
            or name.endswith(".v2.json")
        )

    def checkpoint_candidates(self):
        candidates = set(self.all_generated_final_jsons())
        candidates = sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)
        entries = []
        for path in candidates:
            count = self.cached_geometry_shape_count(path)
            step_number, step_variant, checkpoint_label = self.checkpoint_step_info(path)
            budget = import_drawable_budget(path)
            safe = count <= budget if budget is not None else True
            run_folder = self.checkpoint_run_folder(path)
            try:
                run_mtime = run_folder.stat().st_mtime
            except Exception:
                run_mtime = path.stat().st_mtime
            report = self.final_json_report_info(path)
            tags = []
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
                "import_budget": budget,
                "recommended": False,
                "tags": tags,
                "error": report.get("error"),
                "preset": report.get("preset"),
                "source_image": report.get("source_image"),
            })
        for entry in entries:
            if entry.get("import_safe") and ("Best score" in entry.get("tags", []) or "Latest" in entry.get("tags", [])):
                entry["recommended"] = True
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
        match = re.search(r"\.([A-Za-z0-9_-]+)v2\.json$", name)
        if match:
            tag = match.group(1)
            return "Final vinyl" if tag.lower() == "final" else f"Finalized checkpoint {tag}"
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

    def sort_generated_entries_for_latest_combo(self, entries):
        return sorted(
            entries,
            key=lambda entry: (
                -int(entry.get("layers") or 0),
                -int(entry.get("step_number") or 0),
                str(entry.get("path", "")).lower(),
            ),
        )

    def current_json_browser_mode(self) -> str:
        if hasattr(self, "json_source_combo"):
            current = self.json_source_combo.currentText().lower()
            if current.startswith("handmade"):
                return "handmade"
            if current.startswith("editor"):
                return "editor"
        return "generated"

    def latest_final_combo_label(self, entry):
        tags = []
        if entry.get("recommended"):
            tags.append("best safe")
        if entry.get("tags"):
            for tag in entry["tags"]:
                if tag in {"Best score", "Latest", "Lowest layers"} and tag.lower() not in tags:
                    tags.append(tag.lower())
        tag_text = f" - {', '.join(tags)}" if tags else ""
        source = entry.get("source_image") or entry.get("source") or "latest source"
        return f"{entry.get('layers') or 0} layers - {Path(entry['path']).name}{tag_text} | {source}"

    def populate_latest_final_combo(self, run_groups: dict[str, list[dict]], run_order: list[str], mode: str = "generated"):
        if not hasattr(self, "latest_final_combo"):
            return
        self.latest_final_combo.blockSignals(True)
        self.latest_final_combo.clear()
        self.latest_final_entries = []
        if not run_order:
            if mode == "handmade":
                message = "No handmade JSONs found in imgs/handmade."
            elif mode == "editor":
                message = "No editor exports found in imgs/editor."
            else:
                message = "No finalized JSONs found yet."
            self.latest_final_combo.addItem(message, None)
            self.latest_final_combo.blockSignals(False)
            return
        if mode in {"handmade", "editor"}:
            latest_entries = self.sort_generated_entries_for_latest_combo([entry for group in run_groups.values() for entry in group])
        else:
            latest_entries = self.sort_generated_entries_for_latest_combo(run_groups.get(run_order[0], []))
        self.latest_final_entries = latest_entries
        for entry in latest_entries:
            self.latest_final_combo.addItem(self.latest_final_combo_label(entry), entry)
        if latest_entries:
            self.latest_final_combo.setCurrentIndex(0)
        self.latest_final_combo.blockSignals(False)
        if latest_entries:
            self.select_generated_entry_for_import(latest_entries[0])

    def select_latest_final_combo_entry(self, index: int):
        if not hasattr(self, "latest_final_combo"):
            return
        entry = self.latest_final_combo.itemData(index)
        if isinstance(entry, dict):
            self.select_generated_entry_for_import(entry)
            self.set_hidden_generated_selection(entry["path"])

    def set_latest_final_combo_to_path(self, path: Path):
        if not hasattr(self, "latest_final_combo"):
            return
        target = Path(path)
        for index in range(self.latest_final_combo.count()):
            entry = self.latest_final_combo.itemData(index)
            if isinstance(entry, dict) and Path(entry["path"]) == target:
                self.latest_final_combo.blockSignals(True)
                self.latest_final_combo.setCurrentIndex(index)
                self.latest_final_combo.blockSignals(False)
                break

    def set_hidden_generated_selection(self, path: Path):
        if not hasattr(self, "generated_checkpoint_list"):
            return
        target = Path(path)
        for row in range(self.generated_checkpoint_list.count()):
            item = self.generated_checkpoint_list.item(row)
            entry = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(entry, dict) and Path(entry["path"]) == target:
                self.generated_checkpoint_list.blockSignals(True)
                self.generated_checkpoint_list.setCurrentRow(row)
                self.generated_checkpoint_list.blockSignals(False)
                return

    def json_browser_entries_for_mode(self, mode: str) -> list[dict]:
        if mode == "handmade":
            return self.handmade_json_candidates()
        if mode == "editor":
            return self.editor_json_candidates()
        return self.checkpoint_candidates()

    def json_browser_folder_for_mode(self, mode: str) -> Path:
        if mode == "handmade":
            return HANDMADE_JSON_ROOT
        if mode == "editor":
            return EDITOR_JSON_ROOT
        return GENERATED_ROOT

    def open_final_json_browser(self):
        mode = self.current_json_browser_mode()
        entries = self.json_browser_entries_for_mode(mode)
        if not entries:
            folder = self.json_browser_folder_for_mode(mode)
            QMessageBox.information(self, "Browse JSONs", f"No JSONs were found in {folder.relative_to(ROOT)} yet.")
            return
        dialog = FinalJsonBrowserDialog(self, entries)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_path:
            selected_path = dialog.selected_path
            selected_entry = next((entry for entry in entries if Path(entry["path"]) == selected_path), None)
            if selected_entry:
                self.select_generated_entry_for_import(selected_entry)
                self.set_latest_final_combo_to_path(selected_path)
                self.set_hidden_generated_selection(selected_path)
            else:
                self.select_import_json(selected_path, "visual JSON browser")

    def refresh_generated_browser(self):
        mode = self.current_json_browser_mode()
        entries = self.json_browser_entries_for_mode(mode)
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
            if mode == "handmade":
                prefix = "Handmade folder"
            elif mode == "editor":
                prefix = "Editor exports"
            else:
                prefix = "Latest run" if index == 0 else "Previous run"
            label = self.checkpoint_run_label(run_folders[run_key], prefix=prefix)
            groups[label] = (
                self.sort_generated_entries_for_latest_combo(run_groups[run_key])
                if mode in {"handmade", "editor"}
                else self.sort_generated_entries_for_picker(run_groups[run_key])
            )
            order.append(label)
        self.generated_folder_entries = groups
        self.populate_latest_final_combo(run_groups, run_order, mode=mode)
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
            self.exported_game_json_list.addItem("No exported game group JSONs found yet.")
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

    def use_selected_export_for_import(self):
        entry = self.selected_exported_game_entry()
        if not entry:
            self.log_line("No exported game JSON selected.")
            return
        path = Path(entry["path"])
        self.select_import_json(path, "exported game JSON")
        self.go_to_workflow("Import JSON")

    def copy_export_to_editor_folder(self, export_json: Path) -> Path:
        EDITOR_JSON_ROOT.mkdir(parents=True, exist_ok=True)
        base_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", export_json.stem).strip(" .") or "game-export"
        target_folder = EDITOR_JSON_ROOT / base_name
        target_folder.mkdir(parents=True, exist_ok=True)
        target = target_folder / export_json.name
        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            target = target_folder / f"{export_json.stem}-{stamp}{export_json.suffix}"
        shutil.copy2(export_json, target)
        return target

    def select_editor_export_for_import(self, path: Path) -> None:
        if hasattr(self, "json_source_combo"):
            self.json_source_combo.setCurrentText("Editor exports")
        self.refresh_generated_browser()
        self.select_import_json(path, "editor export")
        self.set_latest_final_combo_to_path(path)
        self.set_hidden_generated_selection(path)
        self.go_to_workflow("Import JSON")

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
                data = render_geometry_json(entry["path"])
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
        live_preview_every = str(options.get("live_preview_every") or "50")
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
            "--live-preview-every",
            live_preview_every,
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
            self.selected_json_label.setText(f"Selected JSON: {path.name}")
            self.selected_json_label.setToolTip(str(path))
        else:
            self.selected_json_label.setText("Selected JSON: none")
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
            return "Finding current game template..."
        if "fh6_group1000_probe.py" in joined:
            return "Locating loaded game group..."
        if "fh6_import_typecode_json.py" in joined:
            return "Importing JSON into game..."
        if "fh6_export_typecode_json.py" in joined:
            return "Exporting current game group to compatible JSON..."
        if "fh6_trim_group_count.py" in joined:
            return "Trimming game import layer count..."
        if "main.py" in joined:
            return "Importing JSON into game..."
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
        game = self.selected_game_value(self.game_combo)
        if not pid or not layer_count:
            self.log_line("PID and template layer count are required.")
            return
        self.set_status("Running")
        threading.Thread(target=self.auto_locate_worker, args=(pid, layer_count, game), daemon=True).start()

    def auto_locate_worker(self, pid, layer_count, game, update_status=True):
        scan_started = time.time()
        try:
            SESSION_PATH.unlink(missing_ok=True)
        except OSError:
            pass
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
        located_session = None
        if code == 0:
            session = load_session_location()
            try:
                session_created = float(session.get("created", 0)) if session else 0.0
            except (TypeError, ValueError):
                session_created = 0.0
            if session and session_created >= scan_started - 2.0 and str(session.get("layer_count", "")) == str(layer_count):
                located_session = session
                self.bus.auto_located.emit(
                    "0x{:x}".format(int(session["count_address"])),
                    "0x{:x}".format(int(session["table_address"])),
                    str(layer_count),
                    str(pid),
                    game,
                )
            elif session:
                self.bus.log.emit(f"Ignoring stale {game.upper()} auto-locate session from an earlier scan.")
        if update_status:
            self.bus.status.emit("Done" if code == 0 else "Failed")
        return located_session

    def apply_auto_locate_result(self, count_address, table_address, layer_count, pid, game):
        self.auto_located_context = {
            "count_address": count_address,
            "table_address": table_address,
            "layer_count": str(layer_count),
            "pid": str(pid),
            "game": str(game),
        }
        self.log_line(f"Auto-located {str(game).upper()} count/table: count={count_address}, table={table_address}")

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
            self.log_line("No JSON selected.")
            return
        pid = self.selected_pid_value()
        game = self.selected_game_value(self.game_combo)
        if not pid:
            self.log_line("Select or refresh the game process before importing.")
            return
        try:
            template_count = int(self.layer_count.text().strip())
        except ValueError:
            self.log_line("Template layer count must be a number.")
            return
        if template_count <= 0:
            self.log_line("Template layer count must be greater than zero.")
            return
        json_path = Path(self.selected_import_json_path)
        try:
            shape_count = import_json_shape_count(json_path)
        except Exception as exc:
            self.log_line(f"Import JSON is invalid: {exc}")
            return
        if shape_count <= 0:
            self.log_line("Import JSON has no visible shapes.")
            return
        if shape_count > template_count:
            self.log_line(f"Import JSON has too many shapes for the loaded template. JSON={shape_count}, template={template_count}")
            return
        self.set_status("Importing")
        self.set_phase("importing", f"Importing JSON into {game.upper()}, then trimming unused template layers.")
        threading.Thread(
            target=self.unified_import_worker,
            args=(
                game,
                pid,
                template_count,
                shape_count,
                json_path,
                self.import_clear_unused.isChecked() if hasattr(self, "import_clear_unused") else True,
            ),
            daemon=True,
        ).start()

    def locate_universal_template(self, game, pid, template_count, run_dir, purpose="template"):
        session_report = run_dir / f"fast-{purpose}-session.json"
        probe_report = run_dir / f"fallback-{purpose}-probe.json"
        group = None
        table = None
        use_research_scanner = False
        if not use_research_scanner:
            self.bus.log.emit(f"Fast-locating loaded {game.upper()} group with {template_count} layers...")
            fast_cmd = [
                helper_python(),
                ROOT / "fh6_probe.py",
                "--game",
                game,
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
                        self.bus.log.emit(f"{game.upper()} group fast-located and validated for {template_count} layer(s).")
            if group and table:
                return group, table
            self.bus.log.emit("Fast locate did not produce a usable group/table. Falling back to research scanner.")
        else:
            self.bus.log.emit("Universal import/export uses the research scanner so grouped vinyl child tables can be found safely.")
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
            raise RuntimeError(f"no matching loaded {game.upper()} group was found")
        min_sample_ok = min(8, template_count)
        requires_fresh_circle_template = purpose.startswith("import")
        min_circle_count = int(template_count * 0.90) if requires_fresh_circle_template else 0

        def candidate_sample_ok(candidate):
            return int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)

        def candidate_sort_key(candidate):
            valid_ptrs = int(candidate.get("valid_ptrs") or 0)
            invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, template_count - valid_ptrs))
            sample_ok = candidate_sample_ok(candidate)
            exact_table = int(valid_ptrs == template_count and invalid_ptrs == 0)
            exact_decoded = int(exact_table and sample_ok >= template_count)
            vector_bonus = int(candidate.get("vector_ok") is True)
            source_bonus = 1 if candidate.get("source") == "vector_header" else 0
            return (
                exact_decoded,
                exact_table,
                valid_ptrs,
                sample_ok,
                -invalid_ptrs,
                vector_bonus,
                source_bonus,
                int(candidate.get("score") or 0),
            )

        candidates = sorted(candidates, key=candidate_sort_key, reverse=True)

        def shape_count(candidate, shape_byte):
            counts = candidate.get("shape_id_counts_all") or {}
            return int(counts.get(str(shape_byte)) or counts.get(shape_byte) or 0)

        def candidate_rejection(candidate, valid_ptrs, sample_ok):
            vector_ok = candidate.get("vector_ok")
            vector_count = candidate.get("vector_count")
            capacity_count = candidate.get("capacity_count")
            if requires_fresh_circle_template and vector_ok is False:
                return "vector metadata invalid"
            if requires_fresh_circle_template and vector_count is not None and int(vector_count) != int(template_count):
                return f"vector_count={vector_count}"
            if capacity_count is not None and int(capacity_count) < int(template_count):
                return f"capacity_count={capacity_count}"
            if valid_ptrs < template_count:
                return f"valid_ptrs={valid_ptrs}"
            invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, template_count - valid_ptrs))
            if invalid_ptrs:
                return f"invalid_ptrs={invalid_ptrs}"
            if sample_ok < min_sample_ok:
                return f"sample_ok={sample_ok}"
            if requires_fresh_circle_template:
                circle_count = shape_count(candidate, 102)
                if circle_count < min_circle_count:
                    return f"circle_template_check={circle_count}/{template_count}"
            return ""

        rejected = []
        selected = None
        strong_candidates = []
        for index, candidate in enumerate(candidates, start=1):
            group = candidate.get("group")
            table = candidate.get("table")
            valid_ptrs = int(candidate.get("valid_ptrs") or 0)
            sample_ok = candidate_sample_ok(candidate)
            rejection = candidate_rejection(candidate, valid_ptrs, sample_ok)
            if group and table and not rejection:
                strong_candidates.append((index, candidate))
                selected = (index, group, table, valid_ptrs, sample_ok, shape_count(candidate, 102))
                break
            rejected.append(f"#{index}: {rejection or 'missing group/table'}")
        if purpose.startswith("export"):
            strong_candidates = []
            for index, candidate in enumerate(candidates, start=1):
                group = candidate.get("group")
                table = candidate.get("table")
                valid_ptrs = int(candidate.get("valid_ptrs") or 0)
                sample_ok = candidate_sample_ok(candidate)
                rejection = candidate_rejection(candidate, valid_ptrs, sample_ok)
                if group and table and not rejection:
                    strong_candidates.append((index, candidate))
            if strong_candidates and selected is None:
                index, candidate = strong_candidates[0]
                selected = (
                    index,
                    candidate.get("group"),
                    candidate.get("table"),
                    int(candidate.get("valid_ptrs") or 0),
                    candidate_sample_ok(candidate),
                    shape_count(candidate, 102),
                )
        if not selected:
            detail = "; ".join(rejected[:5]) if rejected else "no candidates"
            if requires_fresh_circle_template:
                raise RuntimeError(
                    f"no safe fresh {game.upper()} import template was found. Load the saved/reopened 3000-layer plain white "
                    f"circle template, stay in the Vinyl Group Editor, and import only once per fresh template ({detail})"
                )
            raise RuntimeError(f"located group did not validate strongly enough ({detail})")
        index, group, table, valid_ptrs, sample_ok, circle_count = selected
        if index > 1:
            self.bus.log.emit(f"Skipped {index - 1} weaker fallback candidate(s).")
        circle_suffix = f", circle_template={circle_count}/{template_count}" if requires_fresh_circle_template else ""
        self.bus.log.emit(f"{game.upper()} group fallback-located and validated: layers={template_count}, validated={valid_ptrs}, sample_ok={sample_ok}{circle_suffix}")
        return group, table

    def unified_import_worker(self, game, pid, template_count, shape_count, json_path, clear_unused=True):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = UNIVERSAL_IMPORT_ROOT / f"{json_path.stem}-{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        import_backup = run_dir / "import-backup.json"
        import_report = run_dir / "import-report.json"
        trim_backup = run_dir / "trim-backup.json"
        try:
            self.bus.log.emit(f"Universal import run folder: {run_dir}")
            self.bus.log.emit(f"Target game: {game.upper()}")
            self.bus.log.emit(f"Import JSON visible shapes: {shape_count}")
            group, table = self.locate_universal_template(game, pid, template_count, run_dir, purpose="import-template")
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
            self.bus.log.emit(f"Writing JSON shapes into {game.upper()}...")
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
            self.bus.log.emit(f"Imported {imported} shape layers. Trimming {game.upper()} group count...")
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
            self.bus.phase.emit("done", f"JSON imported and layer count trimmed. Save/reload in {game.upper()} to verify.")
        except Exception as exc:
            self.bus.log.emit(f"Universal import failed: {exc}")
            self.bus.status.emit("Failed")

    def start_game_export(self):
        pid = self.selected_pid_value(self.export_pid_combo)
        game = self.selected_game_value(self.export_game_combo if hasattr(self, "export_game_combo") else None)
        if not pid:
            self.log_line("Select or refresh the game process before export.")
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
        self.set_phase("importing", f"Exporting current {game.upper()} group into compatible JSON.")
        threading.Thread(
            target=self.game_export_worker,
            args=(game, pid, template_count),
            daemon=True,
        ).start()

    def game_export_worker(self, game, pid, template_count):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = UNIVERSAL_IMPORT_ROOT / f"export-current-group-{template_count}-{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        export_json = run_dir / f"{game}-current-group-{template_count}-{timestamp}.json"
        export_report = run_dir / f"{game}-current-group-{template_count}-{timestamp}.report.json"
        try:
            self.bus.log.emit(f"Universal export run folder: {run_dir}")
            self.bus.log.emit(f"Target game: {game.upper()}")
            group, table = self.locate_universal_template(game, pid, template_count, run_dir, purpose="export-template")
            fast_report = run_dir / "fast-export-template-session.json"
            fallback_report = run_dir / "fallback-export-template-probe.json"
            locator_report = fast_report if fast_report.exists() else fallback_report
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
                "--probe-report",
                locator_report,
            ]
            self.bus.log.emit(f"Reading current {game.upper()} group into compatible JSON...")
            code = self.run_subprocess(export_cmd, timeout=240)
            if code != 0:
                if export_report.exists():
                    try:
                        report = json.loads(export_report.read_text(encoding="utf-8"))
                        refusal = report.get("refusal_reason")
                        reasons = report.get("validation_reasons") or []
                        if refusal:
                            self.bus.log.emit(str(refusal))
                            if reasons:
                                self.bus.log.emit("Export validation failed. See the saved report for technical details.")
                        else:
                            self.bus.log.emit("Universal export failed while reading layers.")
                    except Exception:
                        self.bus.log.emit("Universal export failed while reading layers.")
                else:
                    self.bus.log.emit("Universal export failed while reading layers.")
                self.bus.status.emit("Failed")
                return
            report = json.loads(export_report.read_text(encoding="utf-8"))
            exported = int(report.get("exported_shape_count") or 0)
            failures = int(report.get("failure_count") or 0)
            warnings = report.get("validation_warnings") or report.get("editable_group_check", {}).get("warnings") or []
            import_copy = self.copy_export_to_editor_folder(export_json)
            self.selected_import_json_path = import_copy
            self.bus.log.emit(f"Universal export complete: {exported} layers -> {export_json}")
            self.bus.log.emit(f"Copied import-ready export to {import_copy}")
            if warnings:
                self.bus.log.emit("Export validation warning: grouped vinyl did not match every old flat-table assumption; see report.")
            if failures:
                self.bus.log.emit(f"Export warning: {failures} unreadable layer(s), see report.")
            self.bus.status.emit("Done")
            self.bus.phase.emit("done", f"Current {game.upper()} group exported to compatible JSON.")
            self.bus.ui_call.emit(lambda: self.select_editor_export_for_import(import_copy))
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
        parser = argparse.ArgumentParser(description="KFPS PySide6 app.")
        parser.add_argument("images", nargs="*", help="Optional image files to preload.")
        args = parser.parse_args(argv)
        window = MainWindow(args.images)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "KFPS",
            f"{exc}\n\nIf this mentions a missing module, run 02_install_dependencies.bat and start the app again.",
        )
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
