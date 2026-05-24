import argparse
import csv
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, Button, Canvas, Checkbutton, Entry, Frame, Label, Listbox, PhotoImage, StringVar, Text, Tk, Toplevel, filedialog, ttk

import psutil

from game_profiles import PROFILES
from geometry_json import RECTANGLE, ROTATED_ELLIPSE, load_normalized_geometry
from generator_backend import GENERATOR_EXE, best_geometry_jsons, build_generator_command, cleanup_generated_outputs, generated_jsons, generated_preview_files, generator_preview_path, geometry_shape_count, load_settings, write_custom_settings
from generator_backend import generator_output_dir, generator_stop_request_path


ROOT = Path(__file__).resolve().parent
PROBE_DIR = ROOT / "webui-data" / "probes"
SHAPE_DUMP_DIR = ROOT / "webui-data" / "shape-dumps"
SHAPE_GUIDE_CACHE = PROBE_DIR / "shapes-guide.csv"
SHAPE_GUIDE_URL = "https://docs.google.com/spreadsheets/d/1zmdme-c1ZqxTw8dd-ooYhJV8aOSYc1LkZlmIfELRbqo/export?format=csv&gid=0"
SESSION_PATH = PROBE_DIR / "current-fh6-session.json"
MEMORY_SNAPSHOT_LIMIT_MB = 2048
PREVIEW_MAX = 520
_CV2_CACHE = None
_CV2_ERROR = None
ELLIPSE_IMPORT_BASE_DIVISOR = 63.0


TEXT = {
    "en": {
        "title": "forza-painter FH6",
        "subtitle": "Generate geometry JSON and import it into Forza Horizon vinyl editor.",
        "language": "Language",
        "process": "Game process",
        "refresh": "Refresh",
        "shape_dumps": "Shape dumps",
        "generate_tab": "Generate JSON",
        "import_tab": "Import",
        "tools_tab": "FH6 Tools",
        "tutorial_tab": "Tutorial",
        "images": "Images",
        "add_images": "Choose image",
        "quality": "Quality profile",
        "custom_settings": "Use custom settings",
        "custom_layers": "Output layers",
        "custom_resolution": "Max resolution",
        "custom_random": "Random samples",
        "custom_mutated": "Mutated samples",
        "custom_save_at": "Save checkpoints",
        "luma_bands": "Enable Luma Bands preprocess",
        "luma_bands_hint": "Create a luma-banded intermediate image before generation. Useful for flatter anime-style shading and cleaner separations.",
        "quality_overshoot": "Enable quality overshoot",
        "quality_overshoot_hint": "Generate about 12% extra raw layers, then let V2 prune/cap back to the FH6-safe target. Slower, but can improve difficult edges, holes, and small details.",
        "targeted_repair": "Use targeted repair (recommended)",
        "targeted_repair_hint": "After generation, tries to clean messy borders and transparent holes. Slower, but usually gives cleaner edges.",
        "custom_panel_title": "Custom settings",
        "custom_panel_hint": "The selected preset fills these values. Enable custom settings if you want to edit them before generating.",
        "generate_step_image": "Step 1 - Choose images",
        "generate_step_image_hint": "Add PNG/JPG/BMP images. Generated JSON is saved beside each source image.",
        "generate_step_quality": "Step 2 - Choose quality",
        "generate_step_quality_hint": "Fast profiles are quicker. Slow profiles use more GPU time and usually look cleaner.",
        "generate_step_run": "Step 3 - Generate",
        "generate_step_run_hint": "Click once and wait. Progress appears in Logs; generated JSON is added to the Import page automatically.",
        "scroll_hint": "Add image, choose a preset, then adjust custom settings if needed.",
        "start_generate": "Generate with current settings",
        "stop_generate": "Stop after latest checkpoint",
        "open_output": "Open output folder",
        "preview": "Preview",
        "preview_hint": "Select an image or JSON to preview it here.",
        "preview_unavailable": "Preview is unavailable. Install optional preview dependencies, or continue without preview.",
        "logs": "Logs",
        "progress": "Progress",
        "json_files": "Geometry JSON files",
        "add_json": "Add JSON",
        "generated_runs": "Generated runs",
        "generated_folder": "Folder",
        "generated_checkpoints": "Checkpoints",
        "generated_refresh": "Refresh generated",
        "generated_none": "No generated checkpoints found yet.",
        "checkpoint_browser": "Checkpoint browser",
        "checkpoint_browser_hint": "Browse generated checkpoints and finals grouped by folder and source image. The browser scans the imgs folder each time, so older runs appear even after restart.",
        "checkpoint_browser_empty": "No generated JSON checkpoints were found in the imgs folder or current session outputs.",
        "checkpoint_source": "Folder / Source",
        "checkpoint_type": "Type",
        "checkpoint_layers": "Layers",
        "checkpoint_file": "File",
        "checkpoint_recommended": "Recommended",
        "checkpoint_add_selected": "Add selected",
        "checkpoint_add_best": "Add recommended",
        "checkpoint_manual": "Manual file picker",
        "checkpoint_refresh": "Refresh",
        "checkpoint_close": "Close",
        "shape_dump_window": "FH6 shape dumps",
        "shape_dump_hint": "Select a shape from the community sheet, put that exact shape on a single ungrouped layer in FH6, choose the layer slot number, then dump that one layer.",
        "shape_dump_search": "Search",
        "shape_dump_selected": "Selected shape",
        "shape_dump_layer_index": "Layer slot (1-based)",
        "shape_dump_dump": "Dump selected layer",
        "shape_dump_open_folder": "Open dump folder",
        "shape_dump_refresh": "Reload shape list",
        "shape_dump_empty": "No shapes loaded.",
        "shape_dump_saved": "Saved shape dump",
        "shape_dump_loading": "Loading shapes guide...",
        "use_outputs": "Use generated JSON",
        "step_game": "Step 1 - Game",
        "step_game_hint": "Start FH6, open Vinyl Group Editor, load an ungrouped sphere template, then refresh the process list.",
        "step_template": "Step 2 - Template",
        "step_template_hint": "Enter the exact layer count shown by your current in-game template.",
        "step_json": "Step 3 - JSON",
        "step_json_hint": "Use the JSON generated by this app, or add a geometry JSON manually.",
        "step_import": "Step 4 - Import",
        "step_import_hint": "Click import once. The app will find the FH6 layer table safely, then write the design.",
        "advanced_options": "Advanced options",
        "show_advanced": "Show advanced",
        "hide_advanced": "Hide advanced",
        "import_preview": "Selected JSON preview",
        "game_profile": "Game profile",
        "pid": "PID",
        "layer_count": "Template layer count",
        "easy_import": "Easy import",
        "easy_import_hint": "For FH6, leave addresses empty. The app will reuse a live session or auto-locate before import.",
        "manual_count": "Layer count address",
        "manual_table": "Layer table address",
        "auto_locate": "Auto-locate FH6",
        "import_json": "Import JSON",
        "diagnose": "Diagnose",
        "save_snapshot": "Save count snapshot",
        "compare_snapshot": "Compare snapshot",
        "snapshot_count": "Snapshot layer count",
        "current_count": "Current layer count",
        "inspect_table": "Inspect table",
        "table_address": "Candidate table",
        "admin_note": "Import needs administrator permission. Start this app as administrator if OpenProcess fails.",
        "no_game": "No supported game process detected",
        "ready": "Ready",
        "running": "Running",
        "stopping": "Stopping",
        "done": "Done",
        "failed": "Failed",
        "locating": "Finding current FH6 template...",
        "located": "FH6 template located and verified.",
        "importing": "Importing JSON into FH6...",
        "json_too_small": "Selected JSON has far fewer drawable layers than the usable template capacity. Import will look blurry; choose a higher-layer JSON.",
        "json_needs_more_template_layers": "FH needs 4 boundary layers for correct cover/apply behavior. Use a template with at least JSON drawable layers + 4.",
        "safe_stop": "Stopped before writing because no safe FH6 template was found.",
        "tutorial": """Beginner workflow

1. Install 64-bit Python 3.12 if possible, then run install_dependencies.bat.
   NumPy/OpenCV preview is optional; generation and import do not require it.
   JSON generation uses the bundled GPU/OpenCL generator, so keep the graphics driver updated.

2. Start Forza Horizon 6 and enter Create Vinyl Group / Vinyl Group Editor.

3. Load or create a template made of many simple sphere layers. 500 or more layers is recommended. Ungroup the template before importing.

4. In this app, open Generate JSON, add a PNG/JPG/BMP image, choose a quality profile, then click Start generating. If preview dependencies are available, the preview area shows the source image first, then the generated geometry preview when JSON appears.

5. Open Import. Add the generated JSON or click Use generated JSON. Keep Game profile as Forza Horizon 6.

6. Enter the real template layer count currently loaded in-game. For FH6 you normally do not need to type memory addresses. Click Import JSON; the app will auto-locate the live FH6 layer table if needed.

7. If import fails with OpenProcess or permission errors, close the app and run it as administrator. If the game was restarted, entered another menu, or reloaded the template, run Auto-locate FH6 again or import again with the correct layer count.

Notes

- The old FH5 signature chain is kept for compatibility, but FH6/Steam builds should use runtime auto-location.
- Current FH6 addresses are valid only for the current game process and editor state.
- If the app cannot find a safe template, confirm the editor is open, the template is ungrouped, and the layer count is exact.
""",
    },
    "zh": {
        "title": "forza-painter FH6",
        "subtitle": "生成 geometry JSON，并导入到 Forza Horizon 的 Vinyl Group 编辑器。",
        "language": "语言",
        "process": "游戏进程",
        "refresh": "刷新",
        "shape_dumps": "形状转储",
        "generate_tab": "生成 JSON",
        "import_tab": "导入",
        "tools_tab": "FH6 工具",
        "tutorial_tab": "教程",
        "images": "图片",
        "add_images": "选择图片",
        "quality": "品质配置",
        "custom_settings": "使用自定义参数",
        "custom_layers": "输出层数",
        "custom_resolution": "最大分辨率",
        "custom_random": "随机样本",
        "custom_mutated": "变异样本",
        "custom_save_at": "保存节点",
        "luma_bands": "启用 Luma Bands 预处理",
        "luma_bands_hint": "先生成一张亮度分层的中间图再开始生成。更适合偏平涂的动漫风格和更清晰的明暗分离。",
        "quality_overshoot": "启用品质超量生成",
        "quality_overshoot_hint": "先多生成约 12% 原始图层，再由 V2 修剪/限制回 FH6 安全目标。会更慢，但可能改善复杂边缘、孔洞和小细节。",
        "targeted_repair": "使用定向修复（推荐）",
        "targeted_repair_hint": "生成后尝试清理杂乱边缘和透明孔洞。会更慢，但边缘通常更干净。",
        "custom_panel_title": "自定义参数",
        "custom_panel_hint": "上方预设会自动填入这些参数；勾选使用自定义参数后可直接修改。",
        "generate_step_image": "第 1 步 - 选择图片",
        "generate_step_image_hint": "添加 PNG/JPG/BMP 图片。生成的 JSON 会保存在原图片旁边。",
        "generate_step_quality": "第 2 步 - 选择品质",
        "generate_step_quality_hint": "快速配置耗时短；慢速配置会占用更多 GPU 时间，通常画面更干净。",
        "generate_step_run": "第 3 步 - 开始生成",
        "generate_step_run_hint": "点击一次后等待。进度会显示在日志里，生成的 JSON 会自动加入导入页面。",
        "scroll_hint": "添加图片、选择预设；需要时直接修改下方自定义参数。",
        "start_generate": "按当前配置生成",
        "stop_generate": "在最新检查点后停止",
        "open_output": "打开输出目录",
        "preview": "预览",
        "preview_hint": "选择图片或 JSON 后会在这里预览。",
        "preview_unavailable": "当前环境无法显示预览。可安装可选预览依赖，也可以直接继续生成或导入。",
        "logs": "日志",
        "progress": "进度",
        "json_files": "Geometry JSON 文件",
        "add_json": "添加 JSON",
        "generated_runs": "已生成结果",
        "generated_folder": "文件夹",
        "generated_checkpoints": "检查点",
        "generated_refresh": "刷新已生成结果",
        "generated_none": "还没有扫描到已生成的检查点。",
        "checkpoint_browser": "检查点浏览器",
        "checkpoint_browser_hint": "按文件夹和源图片分组浏览你已经生成过的 checkpoint 和 final。浏览器每次都会扫描 imgs 文件夹，因此重启后也能看到旧结果。",
        "checkpoint_browser_empty": "在 imgs 文件夹或当前会话输出里没有找到可用的生成 JSON。",
        "checkpoint_source": "文件夹 / 来源",
        "checkpoint_type": "类型",
        "checkpoint_layers": "层数",
        "checkpoint_file": "文件",
        "checkpoint_recommended": "推荐",
        "checkpoint_add_selected": "添加所选",
        "checkpoint_add_best": "添加推荐",
        "checkpoint_manual": "手动选文件",
        "checkpoint_refresh": "刷新",
        "checkpoint_close": "关闭",
        "shape_dump_window": "FH6 形状转储",
        "shape_dump_hint": "先在列表中选择一个形状，再在 FH6 里把这个形状放到一个单独且已取消分组的图层上，填写图层槽位编号，然后转储该单层数据。",
        "shape_dump_search": "搜索",
        "shape_dump_selected": "当前形状",
        "shape_dump_layer_index": "图层槽位（从 1 开始）",
        "shape_dump_dump": "转储所选图层",
        "shape_dump_open_folder": "打开转储目录",
        "shape_dump_refresh": "重载形状列表",
        "shape_dump_empty": "没有加载到形状。",
        "shape_dump_saved": "已保存形状转储",
        "shape_dump_loading": "正在加载 Shapes Guide...",
        "use_outputs": "使用已生成 JSON",
        "step_game": "第 1 步 - 游戏",
        "step_game_hint": "启动 FH6，进入 Vinyl Group Editor，载入未分组的球形模板，然后刷新进程列表。",
        "step_template": "第 2 步 - 模板",
        "step_template_hint": "填写游戏里当前模板显示的真实层数。",
        "step_json": "第 3 步 - JSON",
        "step_json_hint": "使用本软件生成的 JSON，或手动添加 geometry JSON。",
        "step_import": "第 4 步 - 导入",
        "step_import_hint": "只点一次导入。软件会安全定位 FH6 图层表，然后写入图案。",
        "advanced_options": "高级选项",
        "show_advanced": "显示高级",
        "hide_advanced": "隐藏高级",
        "import_preview": "已选 JSON 预览",
        "game_profile": "游戏 profile",
        "pid": "PID",
        "layer_count": "模板层数",
        "easy_import": "简化导入",
        "easy_import_hint": "FH6 通常不需要手填地址。留空即可复用当前 session，或在导入前自动定位。",
        "manual_count": "层数地址",
        "manual_table": "图层表地址",
        "auto_locate": "自动定位 FH6",
        "import_json": "导入 JSON",
        "diagnose": "诊断",
        "save_snapshot": "保存层数快照",
        "compare_snapshot": "对比快照",
        "snapshot_count": "快照层数",
        "current_count": "当前层数",
        "inspect_table": "精查 table",
        "table_address": "候选 table",
        "admin_note": "导入需要管理员权限。如果日志出现 OpenProcess 失败，请用管理员身份启动本程序。",
        "no_game": "未检测到支持的游戏进程",
        "ready": "就绪",
        "running": "运行中",
        "stopping": "停止中",
        "done": "完成",
        "failed": "失败",
        "locating": "正在查找当前 FH6 模板...",
        "located": "已安全定位并验证 FH6 模板。",
        "importing": "正在导入 JSON 到 FH6...",
        "json_too_small": "当前 JSON 可绘制层数远少于模板可用容量，导入会很糊；请换用更高层数的 JSON。",
        "json_needs_more_template_layers": "FH 需要预留 4 个边界层，才能正常保存封面和贴到车上。模板层数建议至少为 JSON 可绘制层数 + 4。",
        "safe_stop": "未找到安全 FH6 模板，已在写入前停止。",
        "tutorial": """小白流程

1. 尽量安装 64 位 Python 3.12，然后运行 install_dependencies.bat。
   NumPy/OpenCV 预览是可选功能；生成和导入不依赖它。
   JSON 生成使用自带的 GPU/OpenCL 生成器，请保持显卡驱动正常。

2. 启动 Forza Horizon 6，进入 Create Vinyl Group / Vinyl Group Editor。

3. 载入或新建一个由大量 sphere 图层组成的模板。建议 500 层以上。导入前必须先 ungroup。

4. 在本软件的“生成 JSON”页添加 PNG/JPG/BMP 图片，选择品质配置，点击“开始生成”。如果预览依赖可用，预览区会先显示原图，JSON 出现后显示生成后的几何预览。

5. 打开“导入”页，添加生成的 JSON，或点击“使用已生成 JSON”。游戏 profile 保持 Forza Horizon 6。

6. 填写游戏里当前模板的真实层数。FH6 通常不需要手动填写内存地址。点击“导入 JSON”，软件会在需要时自动定位当前 FH6 图层表。

7. 如果日志提示 OpenProcess 或权限失败，请关闭软件，用管理员身份重新运行。如果重启过游戏、切换过菜单或重新加载模板，需要用正确层数重新自动定位或重新导入。

说明

- 旧 FH5 签名链仍保留用于兼容；FH6/Steam 构建优先使用运行时自动定位。
- FH6 地址只对当前游戏进程和当前编辑器状态有效。
- 如果软件找不到安全模板，请确认编辑器仍然打开、模板已经 ungroup、层数填写完全正确。
""",
    },
}


def ensure_dirs():
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    SHAPE_DUMP_DIR.mkdir(parents=True, exist_ok=True)


def tr(lang, key):
    return TEXT[lang].get(key, TEXT["en"].get(key, key))


def safe_name_fragment(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "shape"


def fetch_shape_guide_csv():
    try:
        data = urllib.request.urlopen(SHAPE_GUIDE_URL, timeout=20).read().decode("utf-8", "replace")
        SHAPE_GUIDE_CACHE.write_text(data, encoding="utf-8")
        return data
    except Exception:
        if SHAPE_GUIDE_CACHE.exists():
            return SHAPE_GUIDE_CACHE.read_text(encoding="utf-8", errors="replace")
        raise


def parse_shape_guide_csv(text):
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        return []
    titles = rows[0]
    entries = []
    for row_values in rows[3:]:
        for start in range(0, len(row_values), 5):
            chunk = row_values[start:start + 5]
            if len(chunk) < 5:
                continue
            code, name, page, row, column = [item.strip() for item in chunk]
            if not code or not name:
                continue
            try:
                page_num = int(page)
                row_num = int(row)
                col_num = int(column)
            except ValueError:
                continue
            if page_num <= 0 or row_num <= 0 or col_num <= 0:
                continue
            section = (titles[start] if start < len(titles) else "").strip() or f"Page {page_num}"
            entries.append({
                "code": code,
                "name": name,
                "page": page_num,
                "row": row_num,
                "column": col_num,
                "section": section,
            })
    entries.sort(key=lambda item: (item["page"], item["row"], item["column"], item["name"].lower(), item["code"]))
    return entries


def load_shape_guide_entries():
    return parse_shape_guide_csv(fetch_shape_guide_csv())


def game_processes():
    names = {name.lower(): key for key, profile in PROFILES.items() for name in profile.process_names}
    found = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info.get("name") or ""
            key = names.get(name.lower())
            if key:
                found.append({
                    "pid": proc.info["pid"],
                    "name": name,
                    "profile": key,
                    "label": f"{name} pid {proc.info['pid']}",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def parse_hex_or_empty(value):
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
    try:
        pid = int(session.get("pid", -1))
        proc = psutil.Process(pid)
        profile = PROFILES.get(game)
        return bool(profile and proc.name().lower() in [name.lower() for name in profile.process_names])
    except (psutil.Error, TypeError, ValueError):
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


def resize_keep_aspect(image, max_size=PREVIEW_MAX):
    loaded = load_cv2()
    if not loaded:
        return image
    cv2, _np = loaded
    height, width = image.shape[:2]
    scale = min(max_size / max(width, height), 1.0)
    if scale < 1.0:
        image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return image


def image_to_photo(image):
    loaded = load_cv2()
    if not loaded:
        return None
    cv2, _np = loaded
    image = resize_keep_aspect(image)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        return None
    return encoded.tobytes()


class ZoomPreview:
    def __init__(self, parent, empty_text, width=60, height=24, bg="#202020"):
        self.empty_text = empty_text
        self.bg = bg
        self.canvas = Canvas(parent, bg=bg, highlightthickness=0, width=width * 8, height=height * 16)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)
        self.canvas.bind("<Double-Button-1>", self._on_reset)
        self._image_item = None
        self._text_item = None
        self._photo = None
        self._array = None
        self._scale = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_x = None
        self._drag_y = None
        self.clear()

    def pack(self, *args, **kwargs):
        self.canvas.pack(*args, **kwargs)

    def _decode_bytes(self, data):
        loaded = load_cv2()
        if not loaded or not data:
            return None
        cv2, np = loaded
        arr = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return image

    def _load_file(self, path):
        loaded = load_cv2()
        if not loaded:
            return None
        cv2, np = loaded
        try:
            arr = np.fromfile(str(path), dtype=np.uint8)
        except Exception:
            return None
        if arr.size == 0:
            return None
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def clear(self, text=None):
        self._array = None
        self._photo = None
        self._image_item = None
        self._scale = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.canvas.delete("all")
        self._text_item = self.canvas.create_text(
            max(10, self.canvas.winfo_width() // 2),
            max(10, self.canvas.winfo_height() // 2),
            text=text or self.empty_text,
            fill="#dddddd",
            width=max(120, self.canvas.winfo_width() - 20),
            justify="center",
        )

    def set_data(self, data):
        image = self._decode_bytes(data)
        if image is None:
            self.clear()
            return
        self._array = image
        self._fit_to_canvas()
        self._render()

    def set_file(self, path):
        image = self._load_file(path)
        if image is None:
            self.clear()
            return
        self._array = image
        self._fit_to_canvas()
        self._render()

    def _fit_to_canvas(self):
        if self._array is None:
            return
        h, w = self._array.shape[:2]
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        self._scale = min(cw / max(1, w), ch / max(1, h))
        self._scale = max(0.05, min(self._scale, 12.0))
        self._pan_x = 0.0
        self._pan_y = 0.0

    def _render(self):
        if self._array is None:
            self.clear()
            return
        loaded = load_cv2()
        if not loaded:
            self.clear()
            return
        cv2, _np = loaded
        h, w = self._array.shape[:2]
        scale = max(0.05, min(self._scale, 12.0))
        rw = max(1, int(round(w * scale)))
        rh = max(1, int(round(h * scale)))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(self._array, (rw, rh), interpolation=interpolation)
        ok, encoded = cv2.imencode(".png", resized)
        if not ok:
            self.clear()
            return
        self._photo = PhotoImage(data=encoded.tobytes())
        self.canvas.delete("all")
        cx = self.canvas.winfo_width() / 2.0
        cy = self.canvas.winfo_height() / 2.0
        x = cx - (rw / 2.0) + self._pan_x
        y = cy - (rh / 2.0) + self._pan_y
        self._image_item = self.canvas.create_image(int(round(x)), int(round(y)), anchor="nw", image=self._photo)

    def _on_configure(self, _event=None):
        if self._array is None:
            self.clear()
        else:
            self._render()

    def _on_press(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        if self._array is None or self._drag_x is None or self._drag_y is None:
            return
        self._pan_x += event.x - self._drag_x
        self._pan_y += event.y - self._drag_y
        self._drag_x = event.x
        self._drag_y = event.y
        self._render()

    def _on_wheel(self, event):
        if self._array is None:
            return
        if getattr(event, "num", None) == 4:
            factor = 1.12
        elif getattr(event, "num", None) == 5:
            factor = 1.0 / 1.12
        else:
            delta = getattr(event, "delta", 0)
            factor = 1.12 if delta > 0 else (1.0 / 1.12)
        old_scale = self._scale
        self._scale = max(0.05, min(self._scale * factor, 12.0))
        if abs(self._scale - old_scale) < 1e-6:
            return
        self._render()

    def _on_reset(self, _event=None):
        if self._array is None:
            return
        self._fit_to_canvas()
        self._render()


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


def render_source_image(path):
    loaded = load_cv2()
    if not loaded:
        return None
    cv2, _np = loaded
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    return image_to_photo(image)


def render_geometry_json(path):
    loaded = load_cv2()
    if not loaded:
        return None
    cv2, np = loaded
    try:
        data = load_normalized_geometry(path)
        shapes = data["shapes"]
        image_w, image_h = [int(v) for v in shapes[0]["data"][2:]]
        bg_r, bg_g, bg_b, bg_a = [int(v) for v in shapes[0]["color"]]
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
            tile = 32
            for y in range(0, image_h, tile):
                for x in range(0, image_w, tile):
                    if ((x // tile) + (y // tile)) % 2 == 0:
                        checker[y:y + tile, x:x + tile] = (58, 58, 58)
        for shape in shapes[1:]:
            color = [int(v) for v in shape.get("color", [])]
            if len(color) == 4 and color[3] <= 0:
                continue
            r, g, b, a = color
            shape_type = int(shape.get("type", 0))
            if shape_type == ROTATED_ELLIPSE:
                x, y, w, h, rot_deg = shape["data"]
                center = (int(round(x)), int(round(y)))
                adj_w, adj_h = compensated_ellipse_size(w, h)
                axes = (max(1, int(round(adj_h))), max(1, int(round(adj_w))))
                mask = np.zeros((image_h, image_w), np.uint8)
                cv2.ellipse(mask, center, axes, -90 + float(rot_deg), 0.0, 360.0, 255, thickness=-1)
                alpha = max(0.0, min(1.0, float(a) / 255.0))
                if alpha > 0.0:
                    shape_mask = mask > 0
                    src = np.array((b, g, r), dtype=np.float32)
                    old_alpha = alpha_canvas[shape_mask]
                    premul[shape_mask] = src * alpha + premul[shape_mask] * (1.0 - alpha)
                    alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)
            elif shape_type == RECTANGLE:
                x, y, w, h = shape["data"]
                x0 = int(round(x - w / 2))
                y0 = int(round(y - h / 2))
                x1 = int(round(x + w / 2))
                y1 = int(round(y + h / 2))
                alpha = max(0.0, min(1.0, float(a) / 255.0))
                if alpha > 0.0:
                    mask = np.zeros((image_h, image_w), np.uint8)
                    cv2.rectangle(mask, (x0, y0), (x1, y1), 255, thickness=-1)
                    shape_mask = mask > 0
                    src = np.array((b, g, r), dtype=np.float32)
                    old_alpha = alpha_canvas[shape_mask]
                    premul[shape_mask] = src * alpha + premul[shape_mask] * (1.0 - alpha)
                    alpha_canvas[shape_mask] = alpha + old_alpha * (1.0 - alpha)
        preview = premul + checker * (1.0 - alpha_canvas[..., None])
        return image_to_photo(np.clip(preview, 0, 255).astype(np.uint8))
    except Exception:
        return None


class App:
    def __init__(self, initial_images):
        ensure_dirs()
        self.root = Tk()
        self.root.title("forza-painter FH6")
        screen_w = max(1180, int(self.root.winfo_screenwidth() or 1180))
        screen_h = max(780, int(self.root.winfo_screenheight() or 780))
        window_w = min(1180, screen_w)
        window_h = max(780, screen_h - 72)
        offset_x = max(0, (screen_w - window_w) // 2)
        self.root.geometry(f"{window_w}x{window_h}+{offset_x}+0")
        self.lang = "en"
        self.queue = queue.Queue()
        self.shutdown_event = threading.Event()
        self.stop_generation_event = threading.Event()
        self.active_processes = set()
        self.process_lock = threading.Lock()
        self.closed = False
        self.settings = load_settings()
        self.images = []
        for path in initial_images:
            candidate = Path(path)
            if candidate.exists():
                self.images = [candidate]
                break
        self.json_files = []
        self.outputs = []
        self.processes = []
        self.photo = None
        self.preview_widget = None
        self.import_preview_widget = None
        self.use_custom_settings = StringVar(value="0")
        self.enable_luma_bands = StringVar(value="0")
        self.enable_quality_overshoot = StringVar(value="0")
        self.enable_targeted_repair = StringVar(value="1")
        self.custom_stop_at = StringVar()
        self.custom_max_resolution = StringVar()
        self.custom_random_samples = StringVar()
        self.custom_mutated_samples = StringVar()
        self.custom_save_at = StringVar()
        self.translated = []
        self.status = StringVar(value=tr(self.lang, "ready"))
        self.progress_text = StringVar(value="")
        self.selected_profile = StringVar()
        self.selected_game = StringVar(value="fh6")
        self.selected_pid = StringVar()
        self.layer_count = StringVar()
        self.generated_folder = StringVar()
        self.snapshot_count = StringVar()
        self.current_count = StringVar()
        self.count_address = StringVar()
        self.table_address = StringVar()
        self.inspect_table_value = StringVar()
        self.shape_dump_search = StringVar()
        self.shape_dump_layer_index = StringVar(value="1")
        self.shape_dump_selected_text = StringVar(value="")
        self.advanced_visible = False
        self.browser_window = None
        self.browser_tree = None
        self.browser_preview_widget = None
        self.browser_entries = {}
        self.generated_folder_entries = {}
        self.generated_checkpoint_entries = []
        self.shape_dump_window = None
        self.shape_dump_tree = None
        self.shape_dump_entries = []
        self.shape_dump_filtered = []
        self.shape_dump_entry_map = {}
        self.shape_dump_selected = None
        self.active_generation_images = []
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_processes()
        if self.settings:
            default = next(
                (item for item in self.settings if item["path"].name == "c. balanced - good quality and speed.ini"),
                self.settings[min(2, len(self.settings) - 1)],
            )
            self.selected_profile.set(default["label"])
            self._update_setting_description()
        self._render_lists()
        self._poll_queue()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.configure(
            "Primary.TNotebook.Tab",
            padding=(18, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Primary.TNotebook.Tab",
            background=[("selected", "#d8e8ff"), ("active", "#eef5ff")],
            foreground=[("selected", "#003b73"), ("active", "#003b73")],
        )

    def _register_process(self, proc):
        with self.process_lock:
            self.active_processes.add(proc)

    def _unregister_process(self, proc):
        with self.process_lock:
            self.active_processes.discard(proc)

    def _terminate_process(self, proc):
        if proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5,
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _terminate_active_processes(self):
        with self.process_lock:
            processes = list(self.active_processes)
        for proc in processes:
            self._terminate_process(proc)

    def on_close(self):
        self.closed = True
        self.shutdown_event.set()
        self._terminate_active_processes()
        if self.browser_window is not None:
            try:
                self.browser_window.destroy()
            except Exception:
                pass
        if self.shape_dump_window is not None:
            try:
                self.shape_dump_window.destroy()
            except Exception:
                pass
        self.root.destroy()

    def _label(self, parent, key, **kwargs):
        widget = Label(parent, text=tr(self.lang, key), **kwargs)
        self.translated.append((widget, key, "text"))
        return widget

    def _button(self, parent, key, command, **kwargs):
        widget = Button(parent, text=tr(self.lang, key), command=command, **kwargs)
        self.translated.append((widget, key, "text"))
        return widget

    def _build(self):
        self._configure_styles()
        header = Frame(self.root)
        header.pack(fill=X, padx=14, pady=(12, 6))
        title_box = Frame(header)
        title_box.pack(side=LEFT, fill=X, expand=True)
        self._label(title_box, "title", font=("Segoe UI", 18, "bold"), anchor="w").pack(fill=X)
        self._label(title_box, "subtitle", anchor="w", fg="#555").pack(fill=X)
        right = Frame(header)
        right.pack(side=RIGHT)
        self._label(right, "language").pack(anchor="e")
        self.lang_combo = ttk.Combobox(right, values=["English", "中文"], state="readonly", width=10)
        self.lang_combo.set("English")
        self.lang_combo.pack(anchor="e")
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language)

        process_bar = Frame(self.root)
        process_bar.pack(fill=X, padx=14, pady=(0, 8))
        self._label(process_bar, "process").pack(side=LEFT)
        self.process_combo = ttk.Combobox(process_bar, textvariable=self.selected_pid, state="readonly", width=44)
        self.process_combo.pack(side=LEFT, padx=8)
        self._button(process_bar, "refresh", self.refresh_processes).pack(side=LEFT)
        self._button(process_bar, "shape_dumps", self.open_shape_dump_window).pack(side=LEFT, padx=6)
        Label(process_bar, textvariable=self.status, anchor="e").pack(side=RIGHT)

        self.tabs = ttk.Notebook(self.root, style="Primary.TNotebook")
        self.tabs.pack(fill=BOTH, expand=True, padx=14, pady=(0, 8))
        self.generate_tab = Frame(self.tabs)
        self.import_tab = Frame(self.tabs)
        self.tools_tab = Frame(self.tabs)
        self.tutorial_tab = Frame(self.tabs)
        self.tabs.add(self.generate_tab, text=tr(self.lang, "generate_tab"))
        self.tabs.add(self.import_tab, text=tr(self.lang, "import_tab"))
        self.tabs.add(self.tutorial_tab, text=tr(self.lang, "tutorial_tab"))

        self._build_generate_tab()
        self._build_import_tab()
        self._build_tools_tab()
        self._build_tutorial_tab()
        self._build_log()

    def _build_generate_tab(self):
        left_outer = Frame(self.generate_tab)
        left_outer.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10), pady=10)
        right = Frame(self.generate_tab)
        right.pack(side=RIGHT, fill=BOTH, expand=True, pady=10)

        self._label(left_outer, "scroll_hint", anchor="w", justify=LEFT, fg="#8a5300").pack(fill=X, pady=(0, 6))
        scroll_area = Frame(left_outer)
        scroll_area.pack(fill=BOTH, expand=True, pady=(0, 8))
        left_canvas = Canvas(scroll_area, highlightthickness=0)
        left_scroll = ttk.Scrollbar(scroll_area, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        left_scroll.pack(side=RIGHT, fill="y")
        left = Frame(left_canvas)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _update_scroll_region(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _match_canvas_width(event):
            left_canvas.itemconfigure(left_window, width=event.width)

        def _mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event=None):
            left_canvas.bind_all("<MouseWheel>", _mousewheel)

        def _unbind_mousewheel(_event=None):
            left_canvas.unbind_all("<MouseWheel>")

        left.bind("<Configure>", _update_scroll_region)
        left_canvas.bind("<Configure>", _match_canvas_width)
        scroll_area.bind("<Enter>", _bind_mousewheel)
        scroll_area.bind("<Leave>", _unbind_mousewheel)

        step1 = ttk.LabelFrame(left, text=tr(self.lang, "generate_step_image"))
        self.translated.append((step1, "generate_step_image", "text"))
        step1.pack(fill=X, pady=(0, 6))
        row = Frame(step1)
        row.pack(fill=X, padx=10, pady=(6, 2))
        self._label(row, "images").pack(side=LEFT)
        self._button(row, "add_images", self.add_images).pack(side=RIGHT)
        self.image_list = Listbox(step1, height=3)
        self.image_list.pack(fill=X, padx=10, pady=(2, 8))
        self.image_list.bind("<<ListboxSelect>>", self._preview_selected_image)

        step2 = ttk.LabelFrame(left, text=tr(self.lang, "generate_step_quality"))
        self.translated.append((step2, "generate_step_quality", "text"))
        step2.pack(fill=X, pady=(0, 6))
        profile_row = Frame(step2)
        profile_row.pack(fill=X, padx=10, pady=(8, 4))
        self._label(profile_row, "quality").pack(side=LEFT)
        self.profile_combo = ttk.Combobox(
            profile_row,
            values=[item["label"] for item in self.settings],
            textvariable=self.selected_profile,
            state="readonly",
            width=32,
        )
        self.profile_combo.pack(side=LEFT, fill=X, expand=True, padx=(8, 0))
        self.profile_combo.bind("<<ComboboxSelected>>", self._update_setting_description)
        self.setting_description = Label(step2, text="", anchor="w", justify=LEFT, wraplength=500)
        self.setting_description.pack(fill=X, padx=10, pady=(0, 8))

        custom_section = ttk.LabelFrame(left, text=tr(self.lang, "custom_panel_title"))
        self.translated.append((custom_section, "custom_panel_title", "text"))
        custom_section.pack(fill=X, pady=(0, 6))
        self._label(custom_section, "custom_panel_hint", anchor="w", justify=LEFT, wraplength=540, fg="#005a9e").pack(fill=X, padx=10, pady=(6, 2))
        custom_toggle = Checkbutton(
            custom_section,
            text=tr(self.lang, "custom_settings"),
            variable=self.use_custom_settings,
            onvalue="1",
            offvalue="0",
            command=self._sync_custom_state,
        )
        custom_toggle.pack(anchor="w", padx=10, pady=(0, 2))
        self.translated.append((custom_toggle, "custom_settings", "text"))
        custom_grid = Frame(custom_section)
        custom_grid.pack(fill=X, padx=10, pady=(0, 6))
        self.custom_fields = []
        custom_specs = [
            ("custom_layers", self.custom_stop_at),
            ("custom_resolution", self.custom_max_resolution),
            ("custom_random", self.custom_random_samples),
            ("custom_mutated", self.custom_mutated_samples),
            ("custom_save_at", self.custom_save_at),
        ]
        for row_index, (key, variable) in enumerate(custom_specs):
            label = self._label(custom_grid, key, anchor="w")
            label.grid(row=row_index, column=0, sticky="w", pady=1, padx=(0, 8))
            entry = Entry(custom_grid, textvariable=variable, width=18)
            entry.grid(row=row_index, column=1, sticky="ew", pady=1)
            self.custom_fields.append(entry)
        custom_grid.columnconfigure(1, weight=1)
        self._sync_custom_state()

        luma_section = ttk.LabelFrame(left, text=tr(self.lang, "luma_bands"))
        self.translated.append((luma_section, "luma_bands", "text"))
        luma_section.pack(fill=X, pady=(0, 6))
        self._label(luma_section, "luma_bands_hint", anchor="w", justify=LEFT, wraplength=540, fg="#005a9e").pack(fill=X, padx=10, pady=(6, 2))
        luma_toggle = Checkbutton(
            luma_section,
            text=tr(self.lang, "luma_bands"),
            variable=self.enable_luma_bands,
            onvalue="1",
            offvalue="0",
        )
        luma_toggle.pack(anchor="w", padx=10, pady=(0, 8))
        self.translated.append((luma_toggle, "luma_bands", "text"))

        overshoot_section = ttk.LabelFrame(left, text=tr(self.lang, "quality_overshoot"))
        self.translated.append((overshoot_section, "quality_overshoot", "text"))
        overshoot_section.pack(fill=X, pady=(0, 6))
        self._label(overshoot_section, "quality_overshoot_hint", anchor="w", justify=LEFT, wraplength=540, fg="#8a5300").pack(fill=X, padx=10, pady=(6, 2))
        overshoot_toggle = Checkbutton(
            overshoot_section,
            text=tr(self.lang, "quality_overshoot"),
            variable=self.enable_quality_overshoot,
            onvalue="1",
            offvalue="0",
        )
        overshoot_toggle.pack(anchor="w", padx=10, pady=(0, 8))
        self.translated.append((overshoot_toggle, "quality_overshoot", "text"))

        repair_section = ttk.LabelFrame(left, text=tr(self.lang, "targeted_repair"))
        self.translated.append((repair_section, "targeted_repair", "text"))
        repair_section.pack(fill=X, pady=(0, 6))
        self._label(repair_section, "targeted_repair_hint", anchor="w", justify=LEFT, wraplength=540, fg="#8a5300").pack(fill=X, padx=10, pady=(6, 2))
        repair_toggle = Checkbutton(
            repair_section,
            text=tr(self.lang, "targeted_repair"),
            variable=self.enable_targeted_repair,
            onvalue="1",
            offvalue="0",
        )
        repair_toggle.pack(anchor="w", padx=10, pady=(0, 8))
        self.translated.append((repair_toggle, "targeted_repair", "text"))

        step3 = ttk.LabelFrame(left_outer, text=tr(self.lang, "generate_step_run"))
        self.translated.append((step3, "generate_step_run", "text"))
        step3.pack(fill=X)
        self._label(step3, "generate_step_run_hint", anchor="w", justify=LEFT, wraplength=540).pack(fill=X, padx=10, pady=(8, 4))
        actions = Frame(step3)
        actions.pack(fill=X, padx=10, pady=(4, 12))
        self._button(actions, "start_generate", self.start_generate, font=("Segoe UI", 12, "bold"), height=2).pack(side=LEFT, fill=X, expand=True)
        self._button(actions, "stop_generate", self.stop_generate, height=2).pack(side=LEFT, padx=8)
        self._button(actions, "open_output", self.open_output_folder, height=2).pack(side=LEFT, padx=8)

        self._label(right, "preview", anchor="w", font=("Segoe UI", 12, "bold")).pack(fill=X)
        self.preview_widget = ZoomPreview(right, tr(self.lang, "preview_hint"), width=60, height=24)
        self.preview_widget.pack(fill=BOTH, expand=True, pady=6)

    def _build_import_tab(self):
        left = Frame(self.import_tab)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10), pady=10)
        right = Frame(self.import_tab)
        right.pack(side=RIGHT, fill=BOTH, expand=True, pady=10)

        step1 = ttk.LabelFrame(left, text=tr(self.lang, "step_game"))
        self.translated.append((step1, "step_game", "text"))
        step1.pack(fill=X, pady=(0, 10))
        self._label(step1, "step_game_hint", anchor="w", justify=LEFT, wraplength=540).pack(fill=X, padx=10, pady=(8, 4))
        game_row = Frame(step1)
        game_row.pack(fill=X, padx=10, pady=(0, 10))
        self._label(game_row, "game_profile").pack(side=LEFT)
        self.import_game_combo = ttk.Combobox(game_row, values=list(PROFILES.keys()), textvariable=self.selected_game, state="readonly", width=8)
        self.import_game_combo.pack(side=LEFT, padx=8)
        self._label(game_row, "pid").pack(side=LEFT)
        self.import_pid_entry = Entry(game_row, textvariable=self.selected_pid, width=30)
        self.import_pid_entry.pack(side=LEFT, padx=8)
        self._button(game_row, "refresh", self.refresh_processes).pack(side=LEFT)

        step2 = ttk.LabelFrame(left, text=tr(self.lang, "step_template"))
        self.translated.append((step2, "step_template", "text"))
        step2.pack(fill=X, pady=(0, 10))
        self._label(step2, "step_template_hint", anchor="w", justify=LEFT, wraplength=540).pack(fill=X, padx=10, pady=(8, 4))
        template_row = Frame(step2)
        template_row.pack(fill=X, padx=10, pady=(0, 10))
        self._label(template_row, "layer_count").pack(side=LEFT)
        Entry(template_row, textvariable=self.layer_count, width=18, font=("Segoe UI", 13)).pack(side=LEFT, padx=8)

        step3 = ttk.LabelFrame(left, text=tr(self.lang, "step_json"))
        self.translated.append((step3, "step_json", "text"))
        step3.pack(fill=BOTH, expand=True, pady=(0, 10))
        self._label(step3, "step_json_hint", anchor="w", justify=LEFT, wraplength=540).pack(fill=X, padx=10, pady=(8, 4))
        row = Frame(step3)
        row.pack(fill=X, padx=10)
        self._label(row, "json_files").pack(side=LEFT)
        self._button(row, "add_json", self._manual_add_json).pack(side=RIGHT)
        self._button(row, "use_outputs", self.use_generated_outputs).pack(side=RIGHT, padx=8)

        generated_box = ttk.LabelFrame(step3, text=tr(self.lang, "generated_runs"))
        self.translated.append((generated_box, "generated_runs", "text"))
        generated_box.pack(fill=BOTH, expand=True, padx=10, pady=(6, 6))
        folder_row = Frame(generated_box)
        folder_row.pack(fill=X, padx=10, pady=(8, 4))
        self._label(folder_row, "generated_folder").pack(side=LEFT)
        self.generated_folder_combo = ttk.Combobox(folder_row, textvariable=self.generated_folder, state="readonly", width=44)
        self.generated_folder_combo.pack(side=LEFT, fill=X, expand=True, padx=8)
        self.generated_folder_combo.bind("<<ComboboxSelected>>", self._on_generated_folder_selected)
        self._button(folder_row, "generated_refresh", self._refresh_import_generated_browser).pack(side=RIGHT)

        self._label(generated_box, "generated_checkpoints", anchor="w").pack(fill=X, padx=10, pady=(2, 0))
        self.generated_checkpoint_list = Listbox(generated_box, height=8)
        self.generated_checkpoint_list.pack(fill=BOTH, expand=True, padx=10, pady=(2, 8))
        self.generated_checkpoint_list.bind("<<ListboxSelect>>", self._preview_selected_generated_checkpoint)
        self.generated_checkpoint_list.bind("<Double-1>", lambda _e: self._add_selected_generated_json())

        self.json_list = Listbox(step3, height=5)
        self.json_list.pack(fill=BOTH, expand=True, padx=10, pady=6)
        self.json_list.bind("<<ListboxSelect>>", self._preview_selected_json)

        step4 = ttk.LabelFrame(right, text=tr(self.lang, "step_import"))
        self.translated.append((step4, "step_import", "text"))
        step4.pack(fill=X, pady=(0, 10))
        self._label(step4, "step_import_hint", anchor="w", justify=LEFT, wraplength=500).pack(fill=X, padx=10, pady=(8, 4))
        self._label(step4, "easy_import_hint", anchor="w", justify=LEFT, wraplength=500, fg="#555").pack(fill=X, padx=10, pady=4)
        self._label(step4, "admin_note", anchor="w", justify=LEFT, wraplength=500, fg="#8a5300").pack(fill=X, padx=10, pady=4)
        actions = Frame(step4)
        actions.pack(fill=X, padx=10, pady=12)
        self._button(actions, "import_json", self.start_import, font=("Segoe UI", 13, "bold"), height=2).pack(side=LEFT, fill=X, expand=True)
        self.advanced_button = self._button(actions, "show_advanced", self.toggle_advanced)
        self.advanced_button.pack(side=LEFT, padx=(8, 0))

        self.advanced_frame = ttk.LabelFrame(right, text=tr(self.lang, "advanced_options"))
        self.translated.append((self.advanced_frame, "advanced_options", "text"))
        self._field(self.advanced_frame, "manual_count", self.count_address, row=0)
        self._field(self.advanced_frame, "manual_table", self.table_address, row=1)
        self._button(self.advanced_frame, "auto_locate", self.start_auto_locate).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        self._label(right, "import_preview", anchor="w", font=("Segoe UI", 12, "bold")).pack(fill=X, pady=(8, 0))
        self.import_preview_widget = ZoomPreview(right, tr(self.lang, "preview_hint"), width=56, height=20)
        self.import_preview_widget.pack(fill=BOTH, expand=True, pady=6)

    def _build_tools_tab(self):
        form = Frame(self.tools_tab)
        form.pack(fill=X, padx=10, pady=10)
        self._field(form, "layer_count", self.layer_count, row=0)
        self._field(form, "snapshot_count", self.snapshot_count, row=1)
        self._field(form, "current_count", self.current_count, row=2)
        self._field(form, "table_address", self.inspect_table_value, row=3)
        actions = Frame(self.tools_tab)
        actions.pack(fill=X, padx=10, pady=8)
        self._button(actions, "diagnose", self.start_diagnose).pack(side=LEFT)
        self._button(actions, "auto_locate", self.start_auto_locate).pack(side=LEFT, padx=6)
        self._button(actions, "save_snapshot", self.start_save_snapshot).pack(side=LEFT, padx=6)
        self._button(actions, "compare_snapshot", self.start_compare_snapshot).pack(side=LEFT, padx=6)
        self._button(actions, "inspect_table", self.start_inspect_table).pack(side=LEFT, padx=6)

    def _build_tutorial_tab(self):
        self.tutorial_text = Text(self.tutorial_tab, wrap="word")
        self.tutorial_text.pack(fill=BOTH, expand=True, padx=10, pady=10)
        self._update_tutorial()

    def _build_log(self):
        row = Frame(self.root)
        row.pack(fill=X, padx=14)
        self._label(row, "logs", anchor="w").pack(side=LEFT)
        self._label(row, "progress", anchor="e").pack(side=LEFT, padx=(18, 4))
        Label(row, textvariable=self.progress_text, anchor="w", fg="#005a9e").pack(side=LEFT, fill=X, expand=True)
        self.log = Text(self.root, height=9)
        self.log.pack(fill=BOTH, padx=14, pady=(0, 12))

    def _field(self, parent, key, variable, row, values=None, readonly=False):
        self._label(parent, key, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
        if values:
            widget = ttk.Combobox(parent, values=values, textvariable=variable, state="readonly" if readonly else "normal")
        else:
            widget = Entry(parent, textvariable=variable)
        widget.grid(row=row, column=1, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)
        return widget

    def _on_language(self, _event=None):
        self.lang = "zh" if self.lang_combo.get() == "中文" else "en"
        for widget, key, option in self.translated:
            try:
                widget.config(**{option: tr(self.lang, key)})
            except Exception:
                pass
        self.tabs.tab(self.generate_tab, text=tr(self.lang, "generate_tab"))
        self.tabs.tab(self.import_tab, text=tr(self.lang, "import_tab"))
        self.tabs.tab(self.tutorial_tab, text=tr(self.lang, "tutorial_tab"))
        if self.photo is None:
            if self.preview_widget is not None:
                self.preview_widget.empty_text = tr(self.lang, "preview_hint")
                self.preview_widget.clear()
            if self.import_preview_widget is not None:
                self.import_preview_widget.empty_text = tr(self.lang, "preview_hint")
                self.import_preview_widget.clear()
            if self.browser_preview_widget is not None:
                self.browser_preview_widget.empty_text = tr(self.lang, "preview_hint")
                self.browser_preview_widget.clear()
        if hasattr(self, "advanced_button"):
            self.advanced_button.config(text=tr(self.lang, "hide_advanced" if self.advanced_visible else "show_advanced"))
        self._update_tutorial()
        self.status.set(tr(self.lang, "ready"))

    def _update_tutorial(self):
        self.tutorial_text.config(state="normal")
        self.tutorial_text.delete("1.0", END)
        self.tutorial_text.insert(END, tr(self.lang, "tutorial"))
        self.tutorial_text.config(state="disabled")

    def _update_setting_description(self, _event=None):
        item = self._selected_setting()
        self.setting_description.config(text=item["description"] if item else "No settings profiles found.")
        if item and self.use_custom_settings.get() != "1":
            values = item.get("values", {})
            self.custom_stop_at.set(values.get("stopAt", "3000"))
            self.custom_max_resolution.set(values.get("maxResolution", "1200"))
            self.custom_random_samples.set(values.get("randomSamples", "3000"))
            self.custom_mutated_samples.set(values.get("mutatedSamples", "1000"))
            self.custom_save_at.set(values.get("saveAt", values.get("stopAt", "3000")))

    def _sync_custom_state(self):
        state = "normal" if self.use_custom_settings.get() == "1" else "disabled"
        for entry in getattr(self, "custom_fields", []):
            entry.config(state=state)

    def _effective_setting(self):
        setting = self._selected_setting()
        if not setting:
            return None
        overrides = {
            "v2PreprocessMode": "luma_bands" if self.enable_luma_bands.get() == "1" else "none",
        }
        if self.use_custom_settings.get() == "1":
            overrides.update({
                "stopAt": self.custom_stop_at.get(),
                "maxResolution": self.custom_max_resolution.get(),
                "randomSamples": self.custom_random_samples.get(),
                "mutatedSamples": self.custom_mutated_samples.get(),
                "saveAt": self.custom_save_at.get(),
            })
        if self.use_custom_settings.get() == "1" or overrides["v2PreprocessMode"] != str(setting.get("values", {}).get("v2PreprocessMode", "none")).strip().lower():
            return write_custom_settings(setting, overrides)
        return setting

    def _repair_enabled(self):
        return self.enable_targeted_repair.get() == "1"

    def _quality_overshoot_enabled(self):
        return self.enable_quality_overshoot.get() == "1"

    def toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_frame.pack(fill=X, pady=(0, 10))
        else:
            self.advanced_frame.pack_forget()
        self.advanced_button.config(text=tr(self.lang, "hide_advanced" if self.advanced_visible else "show_advanced"))

    def _selected_setting(self):
        label = self.selected_profile.get()
        for item in self.settings:
            if item["label"] == label:
                return item
        return self.settings[0] if self.settings else None

    def _render_lists(self):
        self.image_list.delete(0, END)
        for path in self.images:
            self.image_list.insert(END, str(path))
        self.json_list.delete(0, END)
        for path in self.json_files:
            self.json_list.insert(END, str(path))
        if hasattr(self, "generated_checkpoint_list"):
            self._refresh_import_generated_browser()

    def log_line(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log.insert(END, f"[{timestamp}] {message}\n")
        self.log.see(END)

    def friendly_generator_line(self, line):
        text = (line or "").strip()
        if not text:
            return None
        if text.startswith("Generating raw V2 candidates for "):
            return text
        if text.startswith("Target drawable shapes:"):
            return text
        if text.startswith("Raw generator stop:"):
            return text
        if text.startswith("Using settings:"):
            return text
        if text.startswith("Preprocess mode:"):
            return text
        if text.startswith("Preprocessed image:"):
            return text
        if text.startswith("Smart repair:") or text.startswith("Smart previews:"):
            return text
        if text.startswith("Candidate "):
            return text
        if text.startswith("Best accuracy:"):
            return text
        if text.startswith("Latest checkpoint V2:"):
            return text
        if text.startswith("Selected final:"):
            return text
        if text.startswith("Final JSON:") or text.startswith("Final preview:") or text.startswith("V2 JSON:") or text.startswith("V2 preview:") or text.startswith("Report:"):
            return text
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
                retry_current, retry_total = retrying.groups()
                return f"Retry {retry_current}/{retry_total} at layer {current}/{total}"
            if "Step completed" in detail:
                return None
            return None
        if text.startswith("Loaded image:"):
            return text
        if text.startswith("Settings:"):
            return text
        if text in ("FINISHED",):
            return text
        if "error" in text.lower() or "failed" in text.lower() or "panic" in text.lower():
            return text
        return None

    def queue_generator_message(self, friendly, last_message):
        if not friendly or friendly == last_message:
            return last_message
        if friendly.startswith("Generated layer "):
            self.queue.put(("progress", friendly))
            self.queue.put(("log", friendly))
            return friendly
        if friendly.startswith("Step ") or friendly.startswith("Retry "):
            self.queue.put(("progress", friendly))
            self.queue.put(("log", friendly))
            return friendly
        if friendly == "FINISHED":
            self.queue.put(("progress", friendly))
        self.queue.put(("log", friendly))
        return friendly

    def add_images(self):
        item = filedialog.askopenfilename(
            title="Choose image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")],
        )
        if not item:
            return
        path = Path(item)
        if path.exists():
            self.images = [path]
        self._render_lists()
        if self.images:
            self.image_list.selection_clear(0, END)
            self.image_list.selection_set(0)
        self.show_preview(render_source_image(path))

    def _manual_add_json(self):
        files = filedialog.askopenfilenames(
            title="Choose geometry JSON",
            filetypes=[("Geometry JSON", "*.json"), ("All files", "*.*")],
        )
        added = 0
        for item in files:
            path = Path(item)
            if path.exists() and path not in self.json_files:
                self.json_files.append(path)
                added += 1
        self._render_lists()
        if files:
            self.show_preview(render_geometry_json(Path(files[0])))
        if added:
            self.log_line(f"Added {added} JSON file(s) to import list.")

    def _preview_path_for_json(self, path):
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
            candidate = path.with_name(f"{path.stem}.preview.png")
            return candidate if candidate.exists() else None
        match = re.match(r"^(.*)\.(\d+)\.json$", name)
        if match:
            base, step = match.groups()
            candidate = path.with_name(f"{base}.preview.{step}.png")
            return candidate if candidate.exists() else None
        if name.endswith(".json"):
            candidate = path.with_name(f"{path.stem}.preview.png")
            return candidate if candidate.exists() else None
        return None

    def _json_group_key(self, path):
        stem = Path(path).stem
        stem = re.sub(r"\.v2\.final\.\d+$", "", stem)
        stem = re.sub(r"\.\d+v2$", "", stem)
        stem = re.sub(r"\.v2$", "", stem)
        stem = re.sub(r"\.\d+$", "", stem)
        return stem

    def _json_display_type(self, path):
        name = Path(path).name
        match = re.search(r"\.(\d+)v2\.json$", name)
        if match:
            return f"Checkpoint {match.group(1)} V2"
        if name.endswith(".v2.json"):
            return "V2 Final"
        if ".v2.final." in name:
            return "V2 Final"
        match = re.search(r"\.(\d+)\.json$", name)
        if match:
            return f"Checkpoint {match.group(1)}"
        return "Final"

    def _checkpoint_step_info(self, path):
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

    def _checkpoint_folder_label(self, path):
        path = Path(path)
        try:
            relative = path.parent.relative_to(ROOT)
            return str(relative)
        except Exception:
            return str(path.parent)

    def _all_generated_checkpoint_jsons(self):
        candidates = set()
        imgs_root = ROOT / "imgs"
        if not imgs_root.exists():
            return candidates
        for path in imgs_root.rglob("*.json"):
            name = path.name
            if ".v2.report." in name or ".v2.settings." in name or ".v2.preprocess." in name or ".fh6." in name:
                continue
            candidates.add(path.resolve())
        return candidates

    def _is_v2_output_json(self, path):
        name = Path(path).name.lower()
        return bool(".v2.final." in name or re.search(r"\.\d+v2\.json$", name) or name.endswith(".v2.json"))

    def _checkpoint_candidates(self):
        candidates = set(self._all_generated_checkpoint_jsons())
        seeds = list(self.images) + list(self.outputs) + list(self.json_files)
        for image_path in self.images:
            for path in generated_jsons(image_path):
                candidates.add(path.resolve())
        for path in seeds:
            path = Path(path)
            if path.suffix.lower() == ".json" and path.exists():
                candidates.add(path.resolve())
                base = self._json_group_key(path)
                for sibling in path.parent.glob(f"{base}*.json"):
                    if sibling.exists():
                        candidates.add(sibling.resolve())
            elif path.exists():
                stem = path.stem
                for sibling in path.parent.glob(f"{stem}*.json"):
                    if sibling.exists():
                        candidates.add(sibling.resolve())
                folder = path.parent / stem
                if folder.exists():
                    for sibling in folder.glob("*.json"):
                        if sibling.exists():
                            candidates.add(sibling.resolve())
        candidates = sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)
        recommended = {path.resolve() for path in best_geometry_jsons(candidates)} if candidates else set()
        entries = []
        for path in candidates:
            try:
                count = geometry_shape_count(path)
            except Exception:
                count = 0
            group = self._json_group_key(path)
            step_number, step_variant, checkpoint_label = self._checkpoint_step_info(path)
            folder_label = self._checkpoint_folder_label(path)
            entries.append({
                "path": path,
                "source": group,
                "folder": folder_label,
                "type": self._json_display_type(path),
                "checkpoint": checkpoint_label,
                "step_number": step_number,
                "step_variant": step_variant,
                "layers": count,
                "recommended": path.resolve() in recommended,
                "mtime": path.stat().st_mtime,
            })
        entries.sort(
            key=lambda item: (
                item["folder"].lower(),
                item["source"].lower(),
                item["step_number"],
                item["step_variant"],
                item["path"].name.lower(),
            )
        )
        return entries

    def _browser_selected_entry(self):
        if self.browser_tree is None:
            return None
        selection = self.browser_tree.selection()
        if not selection:
            return None
        return self.browser_entries.get(selection[0])

    def _browser_update_preview(self, _event=None):
        entry = self._browser_selected_entry()
        if not entry or self.browser_preview_widget is None:
            return
        preview_path = self._preview_path_for_json(entry["path"])
        if preview_path and preview_path.exists():
            self.browser_preview_widget.set_file(preview_path)
            return
        data = render_geometry_json(entry["path"])
        if not data:
            self.browser_preview_widget.clear(tr(self.lang, "preview_unavailable"))
            return
        self.browser_preview_widget.set_data(data)

    def _browser_add_selected(self):
        entry = self._browser_selected_entry()
        if not entry:
            return
        path = entry["path"]
        if path not in self.json_files:
            self.json_files.append(path)
            self._render_lists()
            self.log_line(f"Added JSON: {path}")
        self.show_preview(render_geometry_json(path))

    def _browser_add_recommended(self):
        entries = [entry for entry in self.browser_entries.values() if entry.get("recommended")]
        added = 0
        for entry in entries:
            path = entry["path"]
            if path not in self.json_files:
                self.json_files.append(path)
                added += 1
        self._render_lists()
        if entries:
            self.show_preview(render_geometry_json(entries[0]["path"]))
        self.log_line(f"Added {added} recommended JSON file(s) to import list.")

    def _generated_folder_label(self, entry):
        if entry["folder"] in ("", "."):
            return entry["source"]
        return f"{entry['folder']} / {entry['source']}"

    def _generated_display_label(self, entry):
        recommended = " [recommended]" if entry.get("recommended") else ""
        return f"{entry['checkpoint']} | {entry['type']} | {entry['layers']} layers{recommended}"

    def _refresh_import_generated_browser(self):
        if not hasattr(self, "generated_folder_combo") or self.generated_folder_combo is None:
            return
        entries = self._checkpoint_candidates()
        groups = {}
        order = []
        for entry in entries:
            label = self._generated_folder_label(entry)
            if label not in groups:
                groups[label] = []
                order.append(label)
            groups[label].append(entry)
        self.generated_folder_entries = groups
        self.generated_folder_combo["values"] = order
        current = self.generated_folder.get().strip()
        if order:
            if current not in groups:
                current = order[0]
                self.generated_folder.set(current)
            self._populate_generated_checkpoint_list(current)
        else:
            self.generated_folder.set("")
            self.generated_checkpoint_entries = []
            self.generated_checkpoint_list.delete(0, END)
            self.generated_checkpoint_list.insert(END, tr(self.lang, "generated_none"))

    def _populate_generated_checkpoint_list(self, folder_label):
        entries = list(self.generated_folder_entries.get(folder_label, []))
        self.generated_checkpoint_entries = entries
        self.generated_checkpoint_list.delete(0, END)
        for entry in entries:
            self.generated_checkpoint_list.insert(END, self._generated_display_label(entry))
        if entries:
            self.generated_checkpoint_list.selection_clear(0, END)
            self.generated_checkpoint_list.selection_set(0)
            self._preview_selected_generated_checkpoint()

    def _on_generated_folder_selected(self, _event=None):
        folder_label = self.generated_folder.get().strip()
        self._populate_generated_checkpoint_list(folder_label)

    def _selected_generated_entry(self):
        if not hasattr(self, "generated_checkpoint_list"):
            return None
        selection = self.generated_checkpoint_list.curselection()
        if not selection:
            return None
        idx = selection[0]
        if idx < 0 or idx >= len(self.generated_checkpoint_entries):
            return None
        return self.generated_checkpoint_entries[idx]

    def _preview_selected_generated_checkpoint(self, _event=None):
        entry = self._selected_generated_entry()
        if not entry:
            return
        preview_path = self._preview_path_for_json(entry["path"])
        if preview_path and preview_path.exists():
            self.show_preview_file(preview_path)
        else:
            self.show_preview(render_geometry_json(entry["path"]))

    def _add_selected_generated_json(self):
        entry = self._selected_generated_entry()
        if entry is None:
            self.log_line(tr(self.lang, "generated_none"))
            return
        path = entry["path"]
        if path not in self.json_files:
            self.json_files.append(path)
            self._render_lists()
            self.log_line(f"Added JSON: {path}")
        preview_path = self._preview_path_for_json(path)
        if preview_path and preview_path.exists():
            self.show_preview_file(preview_path)
        else:
            self.show_preview(render_geometry_json(path))

    def _refresh_checkpoint_browser(self):
        if self.browser_tree is None:
            return
        self.browser_tree.delete(*self.browser_tree.get_children())
        self.browser_entries = {}
        entries = self._checkpoint_candidates()
        if not entries:
            self.browser_tree.insert("", END, iid="empty", text=tr(self.lang, "checkpoint_browser_empty"), values=("", "", "", "", ""))
            return
        groups = {}
        for index, entry in enumerate(entries):
            group_key = (entry["folder"], entry["source"])
            parent_iid = groups.get(group_key)
            if parent_iid is None:
                parent_iid = f"group-{len(groups)}"
                if entry["folder"] in ("", "."):
                    parent_text = entry["source"]
                else:
                    parent_text = f"{entry['folder']} / {entry['source']}"
                self.browser_tree.insert("", END, iid=parent_iid, text=parent_text, open=True, values=("", "", "", "", ""))
                groups[group_key] = parent_iid
            iid = f"row-{index}"
            values = (
                "yes" if entry["recommended"] else "",
                entry["checkpoint"],
                entry["type"],
                entry["layers"],
                entry["path"].name,
            )
            self.browser_tree.insert(parent_iid, END, iid=iid, text="", values=values)
            self.browser_entries[iid] = entry
        first = self.browser_tree.get_children()
        if first:
            first_parent = first[0]
            children = self.browser_tree.get_children(first_parent)
            if children:
                self.browser_tree.focus(children[0])
                self.browser_tree.selection_set(children[0])
                self.browser_tree.see(children[0])
                self._browser_update_preview()

    def _close_checkpoint_browser(self):
        if self.browser_window is not None:
            try:
                self.browser_window.destroy()
            except Exception:
                pass
        self.browser_window = None
        self.browser_tree = None
        self.browser_preview_widget = None
        self.browser_entries = {}

    def open_checkpoint_browser(self):
        if self.browser_window is not None:
            try:
                self.browser_window.deiconify()
                self.browser_window.lift()
                self._refresh_checkpoint_browser()
                return
            except Exception:
                self._close_checkpoint_browser()
        window = Toplevel(self.root)
        window.title(tr(self.lang, "checkpoint_browser"))
        window.geometry("1180x760")
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_checkpoint_browser)
        self.browser_window = window

        top = Frame(window)
        top.pack(fill=X, padx=12, pady=(12, 8))
        Label(top, text=tr(self.lang, "checkpoint_browser"), font=("Segoe UI", 14, "bold")).pack(anchor="w")
        Label(top, text=tr(self.lang, "checkpoint_browser_hint"), justify=LEFT, anchor="w", wraplength=1100, fg="#555").pack(fill=X, pady=(4, 0))

        body = Frame(window)
        body.pack(fill=BOTH, expand=True, padx=12, pady=(0, 8))
        left = Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True)

        cols = ("recommended", "checkpoint", "type", "layers", "file")
        tree = ttk.Treeview(left, columns=cols, show="tree headings", selectmode="browse")
        tree.heading("#0", text=tr(self.lang, "checkpoint_source"))
        tree.column("#0", width=280, anchor="w")
        tree.heading("recommended", text=tr(self.lang, "checkpoint_recommended"))
        tree.heading("checkpoint", text="Checkpoint")
        tree.heading("type", text=tr(self.lang, "checkpoint_type"))
        tree.heading("layers", text=tr(self.lang, "checkpoint_layers"))
        tree.heading("file", text=tr(self.lang, "checkpoint_file"))
        tree.column("recommended", width=100, anchor="center")
        tree.column("checkpoint", width=110, anchor="center")
        tree.column("type", width=140, anchor="w")
        tree.column("layers", width=90, anchor="center")
        tree.column("file", width=290, anchor="w")
        scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        tree.bind("<<TreeviewSelect>>", self._browser_update_preview)
        tree.bind("<Double-1>", lambda _e: self._browser_add_selected())
        self.browser_tree = tree

        Label(right, text=tr(self.lang, "import_preview"), anchor="w", font=("Segoe UI", 12, "bold")).pack(fill=X)
        preview = ZoomPreview(right, tr(self.lang, "preview_hint"), width=56, height=28)
        preview.pack(fill=BOTH, expand=True, pady=(6, 0))
        self.browser_preview_widget = preview

        actions = Frame(window)
        actions.pack(fill=X, padx=12, pady=(0, 12))
        Button(actions, text=tr(self.lang, "checkpoint_add_selected"), command=self._browser_add_selected).pack(side=LEFT)
        Button(actions, text=tr(self.lang, "checkpoint_add_best"), command=self._browser_add_recommended).pack(side=LEFT, padx=6)
        Button(actions, text=tr(self.lang, "checkpoint_manual"), command=self._manual_add_json).pack(side=LEFT, padx=6)
        Button(actions, text=tr(self.lang, "checkpoint_refresh"), command=self._refresh_checkpoint_browser).pack(side=LEFT, padx=6)
        Button(actions, text=tr(self.lang, "checkpoint_close"), command=self._close_checkpoint_browser).pack(side=RIGHT)

        self._refresh_checkpoint_browser()

    def add_json(self):
        self._manual_add_json()

    def use_generated_outputs(self):
        entry = self._selected_generated_entry()
        if entry is not None:
            self._add_selected_generated_json()
            return
        added = 0
        for path in self.outputs:
            if path.exists() and path not in self.json_files:
                self.json_files.append(path)
                added += 1
        self._render_lists()
        self.log_line(f"Added {added} generated JSON file(s) to import list.")

    def _preview_selected_image(self, _event=None):
        selection = self.image_list.curselection()
        if selection:
            self.show_preview(render_source_image(self.images[selection[0]]))

    def _preview_selected_json(self, _event=None):
        selection = self.json_list.curselection()
        if selection:
            path = self.json_files[selection[0]]
            preview_path = self._preview_path_for_json(path)
            if preview_path and preview_path.exists():
                self.show_preview_file(preview_path)
            else:
                self.show_preview(render_geometry_json(path))

    def show_preview(self, data):
        if not data:
            message = tr(self.lang, "preview_unavailable")
            if self.preview_widget is not None:
                self.preview_widget.clear(message)
            if self.import_preview_widget is not None:
                self.import_preview_widget.clear(message)
            return
        self.photo = data
        if self.preview_widget is not None:
            self.preview_widget.set_data(data)
        if self.import_preview_widget is not None:
            self.import_preview_widget.set_data(data)

    def show_preview_file(self, path):
        if not path:
            self.show_preview(None)
            return
        self.photo = str(path)
        if self.preview_widget is not None:
            self.preview_widget.set_file(path)
        if self.import_preview_widget is not None:
            self.import_preview_widget.set_file(path)

    def refresh_processes(self):
        self.processes = game_processes()
        values = [item["label"] for item in self.processes]
        if not values:
            values = [tr(self.lang, "no_game")]
        self.process_combo["values"] = values
        if self.processes:
            self.selected_pid.set(values[0])
            self.selected_game.set(self.processes[0]["profile"])
        else:
            self.selected_pid.set("")

    def selected_pid_value(self):
        raw = self.selected_pid.get()
        match = re.search(r"pid\s+(\d+)", raw, re.I)
        if match:
            return int(match.group(1))
        try:
            return int(raw.strip())
        except ValueError:
            return None

    def start_generate(self):
        if not self.images:
            self.log_line("No images selected.")
            return
        setting = self._effective_setting()
        if not setting:
            self.log_line("No quality profile selected.")
            return
        if not GENERATOR_EXE.exists():
            self.log_line(f"Missing generator: {GENERATOR_EXE}")
            return
        self.shutdown_event.clear()
        self.stop_generation_event.clear()
        self.active_generation_images = list(self.images)
        self.progress_text.set("")
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=self._generate_worker, args=(setting,), daemon=True).start()

    def stop_generate(self):
        if not self.active_generation_images:
            self.log_line("No active generation job to stop.")
            return
        self.stop_generation_event.set()
        for image_path in list(self.active_generation_images):
            try:
                stop_path = generator_stop_request_path(image_path)
                stop_path.parent.mkdir(parents=True, exist_ok=True)
                stop_path.write_text("stop\n", encoding="utf-8")
            except Exception as exc:
                self.log_line(f"Failed to request stop for {image_path.name}: {exc}")
        self.status.set(tr(self.lang, "stopping"))
        self.log_line("Graceful stop requested. V2 will finalize every saved checkpoint, including the latest one.")

    def _generate_worker(self, setting):
        try:
            self.queue.put(("log", f"Selected profile: {setting.get('label') or setting['path'].name}"))
            self.queue.put(("log", f"Preprocess: {setting.get('values', {}).get('v2PreprocessMode', 'none')}"))
            self.queue.put(("log", f"Quality overshoot: {'on' if self._quality_overshoot_enabled() else 'off'}"))
            self.queue.put(("log", f"Targeted repair: {'on' if self._repair_enabled() else 'off'}"))
            for image_path in list(self.images):
                if self.shutdown_event.is_set():
                    self.queue.put(("status", tr(self.lang, "failed")))
                    self.active_generation_images = []
                    return
                before = {path.resolve() for path in generated_jsons(image_path)}
                preview_path = generator_preview_path(image_path)
                if preview_path.exists():
                    try:
                        preview_path.unlink()
                    except OSError:
                        pass
                cleanup_generated_outputs(image_path)
                self.queue.put(("log", f"Generating: {image_path}"))
                self.queue.put(("preview", render_source_image(image_path)))
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                cmd = build_generator_command(
                    image_path,
                    setting,
                    enable_repair=self._repair_enabled(),
                    enable_overshoot=self._quality_overshoot_enabled(),
                )
                self.queue.put(("log", f"Running GPU generator with {setting['path'].name}"))
                proc = subprocess.Popen(
                    cmd,
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=flags,
                )
                self._register_process(proc)

                last_preview = None
                last_preview_mtime = None
                last_generator_message = None
                output_queue = queue.Queue()

                def _read_generator_output():
                    try:
                        for raw_line in proc.stdout:
                            output_queue.put(raw_line)
                    finally:
                        output_queue.put(None)

                reader = threading.Thread(target=_read_generator_output, daemon=True)
                reader.start()

                def _drain_generator_output():
                    nonlocal last_generator_message
                    while True:
                        try:
                            raw_line = output_queue.get_nowait()
                        except queue.Empty:
                            break
                        if raw_line is None:
                            continue
                        friendly = self.friendly_generator_line(raw_line)
                        last_generator_message = self.queue_generator_message(friendly, last_generator_message)

                try:
                    while proc.poll() is None:
                        if self.shutdown_event.is_set():
                            self._terminate_process(proc)
                            self.queue.put(("status", tr(self.lang, "failed")))
                            return
                        _drain_generator_output()
                        preview_files = generated_preview_files(image_path)
                        if preview_files:
                            newest_preview = preview_files[0]
                            preview_mtime = newest_preview.stat().st_mtime
                            if preview_mtime != last_preview_mtime:
                                last_preview_mtime = preview_mtime
                                self.queue.put(("preview_file", newest_preview))
                        newest = generated_jsons(image_path)
                        if newest and newest[0] != last_preview:
                            last_preview = newest[0]
                        time.sleep(0.1)
                    if self.shutdown_event.is_set():
                        return
                    reader.join(timeout=1)
                    _drain_generator_output()
                finally:
                    self._unregister_process(proc)
                if proc.returncode != 0:
                    self.queue.put(("log", f"Generator exited with code {proc.returncode}."))
                    self.queue.put(("status", tr(self.lang, "failed")))
                    self.active_generation_images = []
                    return
                after = generated_jsons(image_path)
                diff_outputs = [path for path in after if path.resolve() not in before]
                v2_outputs = [path for path in diff_outputs if self._is_v2_output_json(path)]
                new_outputs = v2_outputs or diff_outputs
                if not new_outputs and after:
                    new_outputs = [path for path in after if self._is_v2_output_json(path)] or after[:1]
                if not new_outputs:
                    self.queue.put(("log", "Generator finished but no JSON output was found."))
                    self.queue.put(("status", tr(self.lang, "failed")))
                    self.active_generation_images = []
                    return
                for output in sorted(new_outputs, key=lambda path: path.stat().st_mtime, reverse=True):
                    if output not in self.outputs:
                        self.outputs.append(output)
                    if output not in self.json_files:
                        self.json_files.append(output)
                    self.queue.put(("log", f"Generated: {output}"))
                    preview_files = generated_preview_files(image_path)
                    if preview_files:
                        self.queue.put(("preview_file", preview_files[0]))
                    else:
                        self.queue.put(("preview", render_geometry_json(output)))
                if self.stop_generation_event.is_set():
                    self.queue.put(("log", f"Stopped after finalizing {image_path.name}."))
                    break
            self.queue.put(("render_lists", None))
            self.queue.put(("status", tr(self.lang, "done")))
        except Exception as exc:
            self.queue.put(("log", f"Generator failed: {exc}"))
            self.queue.put(("status", tr(self.lang, "failed")))
        finally:
            self.active_generation_images = []

    def open_output_folder(self):
        folder = None
        if self.outputs:
            folder = self.outputs[-1].parent
        elif self.images:
            folder = self.images[-1].parent
        if folder and folder.exists():
            os.startfile(folder)

    def run_subprocess(self, cmd, timeout=None):
        self.queue.put(("log", self._friendly_command_name(cmd)))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        env = os.environ.copy()
        env.update({"FORZA_PAINTER_NO_ELEVATE": "1", "FORZA_PAINTER_NO_PAUSE": "1"})
        proc = subprocess.Popen(
            [str(x) for x in cmd],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
            env=env,
        )
        self._register_process(proc)
        started = time.time()
        try:
            while True:
                if self.shutdown_event.is_set():
                    self._terminate_process(proc)
                    return 130
                line = proc.stdout.readline()
                if line:
                    friendly = self._friendly_subprocess_line(line.rstrip())
                    if friendly:
                        self.queue.put(("log", friendly))
                if proc.poll() is not None:
                    break
                if timeout and time.time() - started > timeout:
                    self._terminate_process(proc)
                    self.queue.put(("log", f"Timed out after {timeout} seconds."))
                    return 124
                time.sleep(0.05)
            if self.shutdown_event.is_set():
                return 130
            for line in proc.stdout.read().splitlines():
                friendly = self._friendly_subprocess_line(line.rstrip())
                if friendly:
                    self.queue.put(("log", friendly))
            return proc.returncode
        finally:
            self._unregister_process(proc)

    def _friendly_command_name(self, cmd):
        joined = " ".join(str(x) for x in cmd)
        if "fh6_probe.py" in joined and "--dump-layer-output" in joined:
            return "Dumping FH6 layer..."
        if "fh6_probe.py" in joined and "--auto-locate" in joined:
            return tr(self.lang, "locating")
        if "main.py" in joined:
            return tr(self.lang, "importing")
        return "Starting helper..."

    def _check_json_layer_fit(self, json_path, layer_count):
        try:
            from generator_backend import geometry_shape_count
            json_layers = geometry_shape_count(json_path)
            template_layers = int(layer_count)
        except Exception:
            return
        usable_layers = max(0, template_layers - 4)
        if json_layers and template_layers and json_layers > usable_layers:
            self.queue.put(("log", f"{tr(self.lang, 'json_needs_more_template_layers')} JSON={json_layers}, template={template_layers}, usable={usable_layers}"))
        if json_layers and usable_layers and json_layers < usable_layers * 0.75:
            self.queue.put(("log", f"{tr(self.lang, 'json_too_small')} JSON={json_layers}, usable={usable_layers}"))

    def _friendly_subprocess_line(self, line):
        if not line:
            return None
        raw = line.strip()
        lower = raw.lower()
        noisy_parts = (
            "base:",
            "candidate score=",
            "layout candidate",
            "table[",
            "ptr=0x",
            "count=0x",
            "tablefield=",
            "wrote fh6 session location",
            "fh6 layout-count scan checked",
            "process: forzahorizon",
            "current values:",
            "loaded ",
            "descriptor @",
            "info found:",
            "vtp found:",
        )
        if any(part in lower for part in noisy_parts):
            return None
        if "fast fh6 layer group candidates:" in lower:
            return tr(self.lang, "located")
        if raw.startswith("Dumped layer "):
            return raw
        if "no safe fh6 layer group" in lower:
            return tr(self.lang, "safe_stop")
        if "auto-locating fh6 layer count/table" in lower:
            return tr(self.lang, "locating")
        if "cliverylayer table found" in lower:
            return tr(self.lang, "located")
        if "forza horizon 6 detected" in lower:
            return raw
        if raw.startswith("Writing layer") or raw == "DONE!" or raw.startswith("The ideal background color"):
            return raw
        if "openprocess" in lower or "error" in lower or "failed" in lower or "traceback" in lower:
            return raw
        if raw.startswith("<class 'SystemExit'>") or raw.startswith("SystemExit: 0"):
            return None
        return raw

    def start_auto_locate(self):
        pid = self.selected_pid_value()
        layer_count = self.layer_count.get().strip()
        if not pid or not layer_count:
            self.log_line("PID and template layer count are required.")
            return
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=self._auto_locate_worker, args=(pid, layer_count), daemon=True).start()

    def _auto_locate_worker(self, pid, layer_count):
        cmd = [
            sys.executable,
            ROOT / "fh6_probe.py",
            "--game",
            self.selected_game.get() or "fh6",
            "--pid",
            str(pid),
            "--layer-count",
            str(layer_count),
            "--auto-locate",
            "--write-session",
            SESSION_PATH,
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
        if code == 0 and SESSION_PATH.exists():
            session = load_session_location()
            if session:
                self.queue.put(("log", tr(self.lang, "located")))
        self.queue.put(("status", tr(self.lang, "done") if code == 0 else tr(self.lang, "failed")))

    def start_import(self):
        if not self.json_files:
            self.log_line("No JSON files selected.")
            return
        pid = self.selected_pid_value()
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=self._import_worker, args=(pid,), daemon=True).start()

    def _import_worker(self, pid):
        game = self.selected_game.get() or "fh6"
        count_address = parse_hex_or_empty(self.count_address.get())
        table_address = parse_hex_or_empty(self.table_address.get())
        layer_count = self.layer_count.get().strip()
        if not count_address and not table_address and game == "fh6":
            if pid and layer_count:
                self.queue.put(("log", tr(self.lang, "locating")))
                self._auto_locate_worker(pid, layer_count)
                session = load_session_location()
                if session and str(session.get("layer_count", "")) == str(layer_count) and session_pid_is_live(session, game):
                    count_address = "0x{:x}".format(int(session["count_address"]))
                    table_address = "0x{:x}".format(int(session["table_address"]))
                    self.queue.put(("log", tr(self.lang, "located")))
                else:
                    self.queue.put(("status", tr(self.lang, "failed")))
                    return
        for path in list(self.json_files):
            if game == "fh6" and layer_count:
                self._check_json_layer_fit(path, layer_count)
            cmd = [sys.executable, ROOT / "main.py", "--game", game, "--no-preview"]
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
                self.queue.put(("status", tr(self.lang, "failed")))
                return
        self.queue.put(("status", tr(self.lang, "done")))

    def start_diagnose(self):
        pid = self.selected_pid_value()
        cmd = [sys.executable, ROOT / "main.py", "--game", self.selected_game.get() or "fh6", "--diagnose"]
        if pid:
            cmd.extend(["--pid", str(pid)])
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=lambda: self._run_command_worker(cmd, 120), daemon=True).start()

    def start_save_snapshot(self):
        pid = self.selected_pid_value()
        count = self.snapshot_count.get().strip() or self.layer_count.get().strip()
        if not pid or not count:
            self.log_line("PID and snapshot layer count are required.")
            return
        output_path = PROBE_DIR / f"memory-count-{count}.jsonl"
        cmd = [
            sys.executable,
            ROOT / "fh6_probe.py",
            "--game",
            self.selected_game.get() or "fh6",
            "--pid",
            str(pid),
            "--layer-count",
            str(count),
            "--save-memory-snapshot",
            output_path,
            "--limit-mb",
            str(MEMORY_SNAPSHOT_LIMIT_MB),
        ]
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=lambda: self._run_command_worker(cmd, 360), daemon=True).start()

    def start_compare_snapshot(self):
        pid = self.selected_pid_value()
        previous = self.snapshot_count.get().strip()
        current = self.current_count.get().strip() or self.layer_count.get().strip()
        if not pid or not previous or not current:
            self.log_line("PID, snapshot layer count, and current layer count are required.")
            return
        snapshot_path = PROBE_DIR / f"memory-count-{previous}.jsonl"
        candidates_path = PROBE_DIR / f"memory-count-{previous}-to-{current}-candidates.json"
        intersect_path = PROBE_DIR / f"memory-count-{int(previous) - 1}-to-{previous}-candidates.json"
        cmd = [
            sys.executable,
            ROOT / "fh6_probe.py",
            "--game",
            self.selected_game.get() or "fh6",
            "--pid",
            str(pid),
            "--layer-count",
            str(current),
            "--compare-memory-snapshot",
            snapshot_path,
            "--write-candidates",
            candidates_path,
            "--max-matches",
            "50000",
        ]
        if intersect_path.exists():
            cmd.extend(["--intersect-candidates", intersect_path])
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=lambda: self._run_command_worker(cmd, 360), daemon=True).start()

    def start_inspect_table(self):
        pid = self.selected_pid_value()
        table = self.inspect_table_value.get().strip()
        count = self.layer_count.get().strip()
        if not pid or not table or not count:
            self.log_line("PID, layer count, and table address are required.")
            return
        cmd = [
            sys.executable,
            ROOT / "fh6_probe.py",
            "--game",
            self.selected_game.get() or "fh6",
            "--pid",
            str(pid),
            "--layer-count",
            str(count),
            "--inspect-table",
            table,
            "--inspect-layers",
            "12",
        ]
        self.status.set(tr(self.lang, "running"))
        threading.Thread(target=lambda: self._run_command_worker(cmd, 60), daemon=True).start()

    def _close_shape_dump_window(self):
        if self.shape_dump_window is not None:
            try:
                self.shape_dump_window.destroy()
            except Exception:
                pass
        self.shape_dump_window = None
        self.shape_dump_tree = None
        self.shape_dump_entry_map = {}
        self.shape_dump_selected = None

    def _shape_dump_selected_entry(self):
        if self.shape_dump_tree is None:
            return None
        selection = self.shape_dump_tree.selection()
        if not selection:
            return None
        return self.shape_dump_entry_map.get(selection[0])

    def _refresh_shape_dump_tree(self, *_event):
        if self.shape_dump_tree is None:
            return
        search = self.shape_dump_search.get().strip().lower()
        self.shape_dump_tree.delete(*self.shape_dump_tree.get_children())
        self.shape_dump_entry_map = {}
        if search:
            self.shape_dump_filtered = [
                entry for entry in self.shape_dump_entries
                if search in entry["code"].lower()
                or search in entry["name"].lower()
                or search in entry["section"].lower()
            ]
        else:
            self.shape_dump_filtered = list(self.shape_dump_entries)
        if not self.shape_dump_filtered:
            self.shape_dump_selected = None
            self.shape_dump_selected_text.set(tr(self.lang, "shape_dump_empty"))
            return
        for index, entry in enumerate(self.shape_dump_filtered):
            iid = f"shape-{index}"
            self.shape_dump_tree.insert(
                "",
                END,
                iid=iid,
                values=(
                    entry["code"],
                    entry["name"],
                    entry["section"],
                    entry["page"],
                    entry["row"],
                    entry["column"],
                ),
            )
            self.shape_dump_entry_map[iid] = entry
        first = self.shape_dump_tree.get_children()
        if first:
            self.shape_dump_tree.focus(first[0])
            self.shape_dump_tree.selection_set(first[0])
            self.shape_dump_tree.see(first[0])
            self._on_shape_dump_select()

    def _on_shape_dump_select(self, _event=None):
        entry = self._shape_dump_selected_entry()
        self.shape_dump_selected = entry
        if not entry:
            self.shape_dump_selected_text.set(tr(self.lang, "shape_dump_empty"))
            return
        self.shape_dump_selected_text.set(
            f"{entry['code']}  {entry['name']}  |  {entry['section']}  |  "
            f"page {entry['page']} row {entry['row']} col {entry['column']}"
        )

    def _load_shape_dump_entries(self):
        self.shape_dump_selected_text.set(tr(self.lang, "shape_dump_loading"))
        try:
            self.shape_dump_entries = load_shape_guide_entries()
        except Exception as exc:
            self.shape_dump_entries = []
            self.shape_dump_selected_text.set(f"{tr(self.lang, 'shape_dump_empty')} ({exc})")
            self.log_line(f"Failed to load Shapes Guide: {exc}")
            return
        self._refresh_shape_dump_tree()

    def open_shape_dump_folder(self):
        if SHAPE_DUMP_DIR.exists():
            os.startfile(SHAPE_DUMP_DIR)

    def open_shape_dump_window(self):
        if self.shape_dump_window is not None:
            try:
                self.shape_dump_window.deiconify()
                self.shape_dump_window.lift()
                return
            except Exception:
                self._close_shape_dump_window()
        window = Toplevel(self.root)
        window.title(tr(self.lang, "shape_dump_window"))
        window.geometry("1120x760")
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_shape_dump_window)
        self.shape_dump_window = window

        top = Frame(window)
        top.pack(fill=X, padx=12, pady=(12, 8))
        Label(top, text=tr(self.lang, "shape_dump_window"), font=("Segoe UI", 14, "bold")).pack(anchor="w")
        Label(top, text=tr(self.lang, "shape_dump_hint"), justify=LEFT, anchor="w", wraplength=1040, fg="#555").pack(fill=X, pady=(4, 0))

        search_row = Frame(window)
        search_row.pack(fill=X, padx=12, pady=(0, 8))
        self._label(search_row, "shape_dump_search").pack(side=LEFT)
        search_entry = Entry(search_row, textvariable=self.shape_dump_search)
        search_entry.pack(side=LEFT, fill=X, expand=True, padx=(8, 10))
        search_entry.bind("<KeyRelease>", self._refresh_shape_dump_tree)
        self._button(search_row, "shape_dump_refresh", self._load_shape_dump_entries).pack(side=LEFT)

        body = Frame(window)
        body.pack(fill=BOTH, expand=True, padx=12, pady=(0, 8))
        tree_cols = ("code", "name", "section", "page", "row", "column")
        tree = ttk.Treeview(body, columns=tree_cols, show="headings", selectmode="browse")
        tree.heading("code", text="Code")
        tree.heading("name", text="Name")
        tree.heading("section", text="Section")
        tree.heading("page", text="Page")
        tree.heading("row", text="Row")
        tree.heading("column", text="Col")
        tree.column("code", width=110, anchor="center")
        tree.column("name", width=300, anchor="w")
        tree.column("section", width=240, anchor="w")
        tree.column("page", width=70, anchor="center")
        tree.column("row", width=70, anchor="center")
        tree.column("column", width=70, anchor="center")
        scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        tree.bind("<<TreeviewSelect>>", self._on_shape_dump_select)
        self.shape_dump_tree = tree

        footer = ttk.LabelFrame(window, text=tr(self.lang, "shape_dump_selected"))
        self.translated.append((footer, "shape_dump_selected", "text"))
        footer.pack(fill=X, padx=12, pady=(0, 12))
        Label(footer, textvariable=self.shape_dump_selected_text, anchor="w", justify=LEFT, wraplength=1040).pack(fill=X, padx=10, pady=(8, 6))
        layer_row = Frame(footer)
        layer_row.pack(fill=X, padx=10, pady=(0, 10))
        self._label(layer_row, "shape_dump_layer_index").pack(side=LEFT)
        Entry(layer_row, textvariable=self.shape_dump_layer_index, width=10).pack(side=LEFT, padx=(8, 16))
        self._button(layer_row, "shape_dump_dump", self.start_shape_dump).pack(side=LEFT)
        self._button(layer_row, "shape_dump_open_folder", self.open_shape_dump_folder).pack(side=LEFT, padx=6)
        self._button(layer_row, "checkpoint_close", self._close_shape_dump_window).pack(side=RIGHT)

        self._load_shape_dump_entries()

    def _resolve_live_table_address(self, pid, layer_count, game):
        manual = self.inspect_table_value.get().strip() or self.table_address.get().strip()
        if manual:
            return manual
        session = load_session_location()
        if session and str(session.get("layer_count", "")) == str(layer_count) and session_pid_is_live(session, game):
            return "0x{:x}".format(int(session["table_address"]))
        cmd = [
            sys.executable,
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
        if code != 0:
            return None
        session = load_session_location()
        if session and str(session.get("layer_count", "")) == str(layer_count) and session_pid_is_live(session, game):
            return "0x{:x}".format(int(session["table_address"]))
        return None

    def start_shape_dump(self):
        shape = self.shape_dump_selected
        pid = self.selected_pid_value()
        layer_count = self.layer_count.get().strip()
        layer_index_raw = self.shape_dump_layer_index.get().strip()
        if not shape:
            self.log_line("No shape is selected for dumping.")
            return
        if not pid or not layer_count or not layer_index_raw:
            self.log_line("PID, template layer count, and layer slot are required.")
            return
        try:
            layer_index = int(layer_index_raw)
            if layer_index < 1:
                raise ValueError
        except ValueError:
            self.log_line("Layer slot must be a positive integer.")
            return
        self.status.set(tr(self.lang, "running"))
        threading.Thread(
            target=self._shape_dump_worker,
            args=(pid, layer_count, layer_index, dict(shape)),
            daemon=True,
        ).start()

    def _shape_dump_worker(self, pid, layer_count, layer_index, shape):
        game = self.selected_game.get() or "fh6"
        folder = SHAPE_DUMP_DIR / f"{shape['code']}-{safe_name_fragment(shape['name'])}"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        output_path = folder / f"layer-{layer_index:04d}-{timestamp}.json"
        manual_table = self.inspect_table_value.get().strip() or self.table_address.get().strip()
        cmd = [
            sys.executable,
            ROOT / "fh6_probe.py",
            "--game",
            game,
            "--pid",
            str(pid),
            "--layer-count",
            str(layer_count),
            "--dump-layer-index",
            str(layer_index - 1),
            "--dump-layer-output",
            output_path,
            "--dump-layer-shape-code",
            shape["code"],
            "--dump-layer-shape-name",
            shape["name"],
            "--dump-layer-shape-section",
            shape["section"],
            "--dump-layer-shape-page",
            str(shape["page"]),
            "--dump-layer-shape-row",
            str(shape["row"]),
            "--dump-layer-shape-column",
            str(shape["column"]),
        ]
        if manual_table:
            self.queue.put(("log", f"{tr(self.lang, 'locating')} (manual table override)"))
            cmd.extend([
                "--inspect-table",
                manual_table,
            ])
        else:
            self.queue.put(("log", tr(self.lang, "locating")))
            cmd.extend([
                "--auto-dump-layer",
                "--dump-slot-radius",
                "16",
                "--max-seconds",
                "45",
            ])
        code = self.run_subprocess(cmd, timeout=60)
        if code == 0:
            self.queue.put(("log", f"{tr(self.lang, 'shape_dump_saved')}: {output_path}"))
            self.queue.put(("status", tr(self.lang, "done")))
            return
        self.queue.put(("status", tr(self.lang, "failed")))

    def _run_command_worker(self, cmd, timeout):
        code = self.run_subprocess(cmd, timeout=timeout)
        self.queue.put(("status", tr(self.lang, "done") if code == 0 else tr(self.lang, "failed")))

    def _poll_queue(self):
        if self.closed:
            return
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_line(payload)
            elif kind == "progress":
                self.progress_text.set(payload)
            elif kind == "status":
                self.status.set(payload)
            elif kind == "preview":
                self.show_preview(payload)
            elif kind == "preview_file":
                self.show_preview_file(payload)
            elif kind == "render_lists":
                self._render_lists()
        if not self.closed:
            self.root.after(100, self._poll_queue)

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Standalone forza-painter FH6 desktop app.")
    parser.add_argument("images", nargs="*", help="Optional image files to preload.")
    args = parser.parse_args()
    App(args.images).run()


if __name__ == "__main__":
    main()
