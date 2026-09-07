from __future__ import annotations

import concurrent.futures
from datetime import datetime
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

from PIL import Image
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtWidgets import QFileDialog

from .lifecycle import discard_queued_events
from .upscale_engine import EngineStore, PRESETS, execute_job, read_image, settings_for, output_size


def preview_file(path, destination):
    with Image.open(path) as image:
        image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
        image.save(destination, format="PNG")
    return QUrl.fromLocalFile(str(destination)).toString()


class UpscaleService(QObject):
    changed = Signal()
    _ready = Signal(object)
    _progress = Signal(str, float)

    def __init__(self, paths, desktop, source, log, parent=None):
        super().__init__(parent)
        self.paths, self.desktop, self.source, self.log = paths, desktop, source, log
        catalog = paths.app_root / "tools/upscaler/engines.json"
        if not catalog.is_file():
            catalog = paths.ui_root.parent / "tools/upscaler/engines.json"
        self.store = EngineStore(paths.app_root, paths.runtime_root, catalog)
        self._closed = False
        self._cancel = threading.Event()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="upscaler")
        self._future = None
        self._last_progress = 0.0
        self._options = settings_for("anime", 2)
        self._view = dict(source="", sourceUrl="", sourceName="No image selected", sourceSize="",
                          output="", outputUrl="", outputName="No result", report="", status="Ready",
                          busy=False, progress=0, error="", width=0, height=0, operation="")
        self._ready.connect(self._apply)
        self._progress.connect(self._apply_progress)

    @Property("QVariantMap", notify=changed)
    def view(self):
        result = dict(self._view, **self._options)
        try:
            result["engineReady"] = self.store.present(self._options["engine"])
            result["downloadMB"] = round(self.store.catalog[self._options["engine"]]["size"] / 1048576)
            result["available"] = True
        except (OSError, ValueError, KeyError):
            result.update(engineReady=False, downloadMB=0, available=False)
        noise = "Off" if self._options["noise"] < 0 else ("Light", "Medium", "Strong", "Maximum")[self._options["noise"]]
        result["recommendation"] = {
            "photo": "Real-ESRGAN x4plus | GPU Auto | 128px tiles | Enhanced quality Off",
            "anime": "waifu2x CUNet | Denoise Light | GPU Auto | 128px tiles",
            "text": "waifu2x CUNet | Denoise Off | GPU Auto | 128px tiles",
        }[self._options["preset"]]
        result["settingsLabel"] = f"{self._options['scale']}x | Denoise {noise} | {self._options['tile']}px tiles"
        if self._options["engine"] == "realesrgan":
            result["settingsLabel"] = "Native 4x" + (" reduced to 2x" if self._options["scale"] == 2 else "") + f" | {self._options['tile']}px tiles"
        if self._view["width"]:
            result["targetSize"] = f"{self._view['width'] * self._options['scale']} x {self._view['height'] * self._options['scale']}"
        else:
            result["targetSize"] = ""
        return result

    @Property(bool, notify=changed)
    def running(self):
        return self._view["busy"]

    @Property(str, notify=changed)
    def status(self):
        return self._view["status"]

    @Property(str, notify=changed)
    def lastError(self):
        return self._view["error"]

    def _submit(self, operation, function):
        self._cancel.clear()
        self._view.update(busy=True, error="", operation=operation, progress=-1)
        self.changed.emit()
        self._future = self._executor.submit(function)
        self._future.add_done_callback(self._emit)

    def _emit(self, future):
        try:
            result = future.result()
        except Exception as exc:
            result = {"state": "failed", "error": str(exc)}
        if not self._closed:
            self._ready.emit(result)

    def _notify_progress(self, status, progress):
        now = time.monotonic()
        if not self._closed and now - self._last_progress >= 0.1:
            self._last_progress = now
            self._progress.emit(status, float(progress))

    @Slot(str, float)
    def _apply_progress(self, status, progress):
        if not self._closed and self.running:
            self._view.update(status=status, progress=progress)
            self.changed.emit()

    @Slot()
    def choose(self):
        if self.running or self._closed:
            return
        value = self.desktop.chooseImage()
        if value:
            self.setSource(value)

    @Slot(str)
    def setSource(self, value):
        if self.running or self._closed:
            return
        url = QUrl(value)
        if url.isLocalFile():
            value = url.toLocalFile()
        path = Path(value).resolve()
        self._view["status"] = "Loading source..."
        def load():
            image = read_image(path)
            width, height = image.size
            folder = self.paths.runtime_root / "upscaler" / "previews"
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / (uuid.uuid4().hex + ".png")
            image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
            image.save(destination)
            return dict(state="source", source=str(path), sourceUrl=QUrl.fromLocalFile(str(destination)).toString(),
                        sourceName=path.name, sourceSize=f"{width} x {height}", width=width, height=height)
        self._submit("source", load)

    @Slot()
    def useCurrentSource(self):
        if self.source.path:
            self.setSource(self.source.path)

    @Slot(str, "QVariant")
    def configure(self, field, value):
        if self.running or self._closed:
            return
        try:
            if field == "preset":
                self._options = settings_for(str(value), self._options["scale"])
            elif field == "reset":
                self._options = settings_for(self._options["preset"], self._options["scale"])
            elif field in ("scale", "noise", "tile", "gpu", "tta"):
                current = {key: self._options[key] for key in ("preset", "scale", "noise", "tile", "gpu", "tta")}
                current[field] = value
                self._options = settings_for(**current)
            else:
                return
            self._view["error"] = ""
        except (TypeError, ValueError) as exc:
            self._view["error"] = str(exc)
        self.changed.emit()

    @Slot()
    def start(self):
        if self.running or self._closed or not self._view["source"]:
            return
        options = dict(self._options)
        try:
            output_size((self._view["width"], self._view["height"]), options)
        except ValueError as exc:
            self._view.update(error=str(exc), status="Image exceeds safety limit")
            self.changed.emit()
            return
        source = self._view["source"]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        run = self.paths.runtime_root / "upscaler" / "runs" / stamp
        self._view["status"] = "Starting local upscale..."
        def work():
            result = execute_job(self.store, source, options, run, self.paths.app_root / "Images/Upscaled", self._cancel, self._notify_progress)
            if result["state"] == "complete":
                try:
                    result["outputUrl"] = preview_file(result["output"], run / "preview.png")
                except Exception as exc:
                    result["outputUrl"] = ""
                    result["preview_error"] = "Preview unavailable: " + str(exc)
            return result
        self._submit("upscale", work)

    @Slot()
    def cancel(self):
        if self.running:
            self._cancel.set()
            self._view["status"] = "Cancelling..."
            self.changed.emit()

    @Slot(object)
    def _apply(self, result):
        if self._closed:
            return
        self._view.update(busy=False, progress=0)
        if result["state"] == "source":
            self._delete_source_preview()
            self._view.update({key: value for key, value in result.items() if key != "state"})
            self._view.update(output="", outputUrl="", outputName="No result", report="", status="Ready")
        elif result["state"] == "complete":
            self._view.update(output=result["output"], outputUrl=result["outputUrl"], report=result["report"],
                              outputName=f"{result['settings']['preset'].title()} {result['settings']['scale']}x | {result['output_size'][0]} x {result['output_size'][1]}",
                              status=f"Saved in {result['elapsed_seconds']:.1f}s", progress=100)
            self.log.append("Upscale complete: " + result["output"], update_status=False)
            warnings = [result[key] for key in ("preview_error", "diagnostic_error") if result.get(key)]
            if warnings:
                self._view["status"] += ". " + "; ".join(warnings)
                self.log.append(self._view["status"], update_status=False)
        elif result["state"] == "saved":
            self._view.update(status="Saved copy: " + result["path"])
        else:
            self._view.update(error=result.get("error", "Upscale failed"), status="Cancelled" if result["state"] == "cancelled" else "Upscale failed")
            if result.get("report"):
                self._view["report"] = result["report"]
            self.log.append(self._view["error"], update_status=False)
        self.changed.emit()

    @Slot()
    def useResult(self):
        if not self.running and self._view["output"]:
            self.source.setPath(self._view["output"])

    @Slot()
    def saveAs(self):
        if self.running or not self._view["output"]:
            return
        target, _ = QFileDialog.getSaveFileName(None, "Save upscaled PNG", self._view["output"], "PNG image (*.png)")
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
        if path.resolve() == Path(self._view["source"]).resolve():
            self._view["error"] = "Choose a new filename. The original image is never overwritten."
            self.changed.emit()
            return
        output = self._view["output"]
        def save():
            if path.resolve() != Path(output).resolve():
                temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    shutil.copyfile(output, temporary)
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            return {"state": "saved", "path": str(path)}
        self._submit("save", save)

    @Slot()
    def openOutputFolder(self):
        if self._view["output"]:
            self.desktop.openFolder(str(Path(self._view["output"]).parent))

    @Slot()
    def openReport(self):
        if self._view["report"]:
            self.desktop.openFolder(str(Path(self._view["report"]).parent))

    def _delete_source_preview(self):
        url = QUrl(self._view["sourceUrl"])
        if url.isLocalFile():
            path = Path(url.toLocalFile())
            if path.is_relative_to(self.paths.runtime_root / "upscaler" / "previews"):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass  # A preview cleanup failure must not block app shutdown.

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._delete_source_preview()
        discard_queued_events(self)
