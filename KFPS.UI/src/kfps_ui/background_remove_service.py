from __future__ import annotations

import concurrent.futures
from datetime import datetime
import os
import json
from pathlib import Path
import shutil
import threading
import time
import uuid

from PIL import Image
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtWidgets import QFileDialog

from .background_remove_engine import BackgroundEngineStore, execute_job, settings_for
from .background_remove_document import MaskDocument
from .background_remove_processing import background_color, quality_warning
from .lifecycle import discard_queued_events
from .upscale_engine import atomic_json, read_image, sha256
from .upscale_service import preview_file


class BackgroundRemoveService(QObject):
    changed = Signal()
    resultReady = Signal()
    _ready = Signal(object)
    _progress = Signal(str, float)

    def __init__(self, paths, desktop, source, log, parent=None):
        super().__init__(parent)
        self.paths, self.desktop, self.source, self.log = paths, desktop, source, log
        catalog = paths.app_root / "tools/background_remover/engine.json"
        if not catalog.is_file():
            catalog = paths.ui_root.parent / "tools/background_remover/engine.json"
        self.store = BackgroundEngineStore(paths.runtime_root, catalog)
        self._cancel = threading.Event()
        self._closed = False
        self._future = None
        self._last_progress = 0.0
        self._document = None
        self._last_session = paths.runtime_root / "background-remover/last-session.json"
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="background-remover")
        self._options = settings_for()
        self._view = dict(source="", sourceUrl="", sourceName="No image selected", sourceSize="",
                          output="", outputUrl="", outputName="", report="", status="Ready", busy=False,
                          progress=0, error="", warning="", width=0, height=0, transparent=False, operation="",
                          maskUrl="", original="", detectedColor="#ffffff", canUndo=False, canRedo=False,
                          editable=False, draft=False, exported="")
        self._ready.connect(self._apply)
        self._progress.connect(self._apply_progress)

    @Property("QVariantMap", notify=changed)
    def view(self):
        result = dict(self._view, **self._options)
        try:
            result.update(engineReady=self.store.present(), available=True,
                          downloadMB=round((self.store.catalog["model"]["size"] + sum(s["size"] for s in self.store.catalog["wheels"])) / 1048576))
        except (OSError, ValueError, KeyError):
            result.update(engineReady=False, available=False, downloadMB=0)
        if self._options["mode"] == "color":
            result.update(engineReady=True, available=True, downloadMB=0)
        result["preserveOnly"] = self._view["transparent"] and not self._options["refine"]
        result["resumeAvailable"] = self._last_session.is_file()
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
        self._future.add_done_callback(lambda future: self._emit(future, operation))

    def _emit(self, future, operation):
        try:
            result = future.result()
        except Exception as exc:
            result = dict(state="failed", error=str(exc))
            try:
                folder = self.paths.runtime_root / "background-remover/errors"
                folder.mkdir(parents=True, exist_ok=True)
                report = folder / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".json")
                atomic_json(report, dict(schema="kfps.background-operation-error.v1", operation=operation,
                                         error=str(exc), saved=time.time(),
                                         session=self._document.run.name if self._document else ""))
                result["report"] = str(report)
            except OSError:
                pass
        if not self._closed:
            self._ready.emit(result)

    def _notify_progress(self, status, progress):
        now = time.monotonic()
        if not self._closed and now - self._last_progress >= 0.1:
            self._last_progress = now
            self._progress.emit(status, float(progress))

    @Slot(str, float)
    def _apply_progress(self, status, progress):
        if not self._closed and self.running and not self._cancel.is_set():
            self._view.update(status=status, progress=progress)
            self.changed.emit()

    @Slot()
    def choose(self):
        if not self.running and not self._closed:
            value = self.desktop.chooseImage()
            if value:
                self.setSource(value)

    @Slot(str)
    def setSource(self, value):
        if self.running or self._closed:
            return
        url = QUrl(value)
        path = Path(url.toLocalFile() if url.isLocalFile() else value).resolve()
        self._view["status"] = "Loading source..."
        def load():
            image = read_image(path)
            width, height = image.size
            transparent = image.getchannel("A").getextrema()[0] < 255
            folder = self.paths.runtime_root / "background-remover/previews"
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / (uuid.uuid4().hex + ".png")
            try:
                detected = background_color(image)
                image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
                image.save(destination)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            return dict(state="source", source=str(path), sourceUrl=QUrl.fromLocalFile(str(destination)).toString(),
                        sourceName=path.name, sourceSize=f"{width} x {height}", width=width, height=height,
                        transparent=transparent, original=str(path), detectedColor=detected)
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
            if field == "reset":
                self._options = settings_for()
            elif field in self._options:
                options = dict(self._options)
                options[field] = value
                self._options = settings_for(**options)
            self._view["error"] = ""
            if self._view["output"]:
                self._view["status"] = "Settings changed. Run removal to apply them."
        except (TypeError, ValueError) as exc:
            self._view["error"] = str(exc)
        self.changed.emit()

    @Slot()
    def start(self):
        if self.running or self._closed or not self._view["source"]:
            return
        source, options = self._view["source"], dict(self._options)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        run = self.paths.runtime_root / "background-remover/runs" / stamp
        self._view.update(status="Starting background removal...", error="")
        def work():
            result = execute_job(self.store, self.paths.python_executable, source, options, run,
                                 self.paths.app_root / "Images/Background Removed", self._cancel, self._notify_progress)
            if result["state"] == "complete":
                try:
                    exported = result["output"]
                    document = MaskDocument.create(run, result["output"], self._view["original"] or source)
                    result.update(self._document_view(document))
                    result["document"] = document
                    result["exported"] = exported
                    result["output"] = exported
                    self._save_session(document)
                except Exception as exc:
                    result.setdefault("document", None)
                    result["preview_error"] = "Correction session unavailable: " + str(exc)
                    try:
                        result["outputUrl"] = preview_file(result["output"], run / "preview.png")
                    except Exception as preview_exc:
                        result.update(outputUrl="", preview_error="PNG saved; preview unavailable: " + str(preview_exc))
            return result
        self._submit("remove", work)

    @Slot()
    def cancel(self):
        if self.running:
            self._cancel.set()
            self._view["status"] = "Cancelling..."
            self.changed.emit()

    def _save_session(self, document):
        relative = document.run.resolve().relative_to((self.paths.runtime_root / "background-remover/runs").resolve())
        atomic_json(self._last_session, dict(schema="kfps.background-resume.v1", run=relative.as_posix()))

    def _document_view(self, document):
        path = document.current_path
        image = document.current()
        warning = quality_warning(image)
        image.thumbnail((2400,2400), Image.Resampling.LANCZOS)
        preview = document.folder / (path.stem + "-preview.png")
        mask = document.folder / (path.stem + "-mask.png")
        image.save(preview)
        image.getchannel("A").save(mask)
        return dict(output=str(path), outputUrl=QUrl.fromLocalFile(str(preview)).toString(),
                    maskUrl=QUrl.fromLocalFile(str(mask)).toString(), warning=warning,
                    canUndo=document.can_undo, canRedo=document.can_redo, editable=True,
                    draft=document.draft,
                    outputName=f"PNG | {document.state['size'][0]} x {document.state['size'][1]}" + (" | Draft" if document.draft else ""),
                    report=str(document.run / "report.json"))

    @Slot(str, "QVariantList", float, float)
    def correct(self, tool, points, diameter, tolerance):
        if self.running or self._closed or self._document is None:
            return
        self._view["status"] = "Saving correction..."
        document = self._document
        def work():
            changed = document.edit(tool, points, diameter, tolerance)
            result = self._document_view(document)
            return dict(state="edited", document=document, status="Correction saved to session." if changed else "No pixels changed.", **result)
        self._submit("edit", work)

    @Slot(int)
    def history(self, direction):
        if self.running or self._closed or self._document is None:
            return
        document = self._document
        self._view["status"] = "Restoring correction..."
        def work():
            document.step(direction)
            return dict(state="edited", document=document, status="Correction restored.", **self._document_view(document))
        self._submit("edit", work)

    @Slot()
    def resetCorrections(self):
        if self.running or self._closed or self._document is None:
            return
        document = self._document
        def work():
            document.reset()
            return dict(state="edited", document=document, status="Initial cutout restored. Undo is available.", **self._document_view(document))
        self._submit("edit", work)

    @Slot(float, float)
    def sampleColor(self, x, y):
        if self.running or self._closed or not self._view["source"] or not (0 <= x <= 1 and 0 <= y <= 1):
            return
        path = self._document.run / "source.png" if self._document else Path(self._view["source"])
        def work():
            image = read_image(path)
            rgb = image.getpixel((min(image.width-1,int(x*image.width)),min(image.height-1,int(y*image.height))))[:3]
            return dict(state="sampled", color="#" + "".join(f"{v:02x}" for v in rgb))
        self._submit("sample", work)

    @Slot()
    def resume(self):
        if self.running or self._closed or not self._last_session.is_file():
            return
        def work():
            if self._last_session.stat().st_size > 8192:
                raise ValueError("The saved session pointer is invalid.")
            value = json.loads(self._last_session.read_text(encoding="utf-8"))
            base = (self.paths.runtime_root / "background-remover/runs").resolve()
            run = (base / value["run"]).resolve()
            if value.get("schema") != "kfps.background-resume.v1" or run.parent != base:
                raise ValueError("The saved session location is invalid.")
            document = MaskDocument.open(run)
            report_path = run / "report.json"
            if report_path.stat().st_size > 128*1024:
                raise ValueError("The saved run report is invalid.")
            options = settings_for(**json.loads(report_path.read_text(encoding="utf-8")).get("settings", {}))
            image = document.original()
            width, height = image.size
            transparent = image.getchannel("A").getextrema()[0] < 255
            detected = background_color(image)
            image.thumbnail((2400,2400), Image.Resampling.LANCZOS)
            preview = run / "source-preview.png"
            image.save(preview)
            return dict(state="resumed", document=document, options=options, source=str(run/"source.png"),
                        original=document.state.get("source_original", ""),
                        sourceName=document.state["source_name"], sourceSize=f"{width} x {height}",
                        width=width, height=height, transparent=transparent, detectedColor=detected,
                        sourceUrl=QUrl.fromLocalFile(str(preview)).toString(),
                        exported=document.state.get("published_path", document.state.get("initial_output", "")),
                        status="Saved correction session restored.", **self._document_view(document))
        self._view["status"] = "Opening saved correction session..."
        self._submit("resume", work)

    @Slot(object)
    def _apply(self, result):
        if self._closed:
            return
        self._future = None
        self._view.update(busy=False, progress=0)
        state = result["state"]
        if state == "source":
            self._document = None
            self._delete_preview(self._view["sourceUrl"])
            self._view.update({key: value for key, value in result.items() if key != "state"})
            self._options["color"] = "auto"
            self._view.update(output="", outputUrl="", outputName="", report="", maskUrl="", warning="",
                              editable=False, canUndo=False, canRedo=False, draft=False, exported="",
                              status="Existing transparency detected" if result["transparent"] else "Ready")
        elif state == "complete":
            self._document = result.get("document")
            preserved = result["mode"] == "existing-transparency-preserved"
            status = "Existing transparency preserved" if preserved else "Background removed"
            self._view.update(output=result["output"], outputUrl=result["outputUrl"], report=result["report"],
                              outputName=f"PNG | {result['output_size'][0]} x {result['output_size'][1]}",
                              status=f"{status}. Saved in {result['elapsed_seconds']:.1f}s", progress=100)
            self._view.update(warning=result.get("warning", ""), maskUrl=result.get("maskUrl", ""),
                              editable=self._document is not None, canUndo=False, canRedo=False, draft=False,
                              exported=result.get("exported", result["output"]))
            warnings = [result[key] for key in ("preview_error", "diagnostic_error") if result.get(key)]
            if warnings:
                self._view["status"] += ". " + "; ".join(warnings)
            self.log.append("Background removal: " + result["output"], update_status=False)
        elif state in ("edited", "resumed"):
            self._document = result.pop("document")
            if state == "resumed":
                self._delete_preview(self._view["sourceUrl"])
                self._options = result.pop("options")
            self._view.update({key: value for key, value in result.items() if key != "state"})
        elif state == "sampled":
            self._options["color"] = result["color"]
            self._view["status"] = "Background colour selected. Run removal to apply."
        elif state == "use-result":
            self._view.update(exported=result["path"], status="Selected corrected PNG for generation.", draft=False)
            if self._document and self._document.last_export_warning:
                self._view["warning"] = self._document.last_export_warning
            self.source.setPath(result["path"])
            self.resultReady.emit()
        elif state == "saved":
            self._view.update(status="Saved copy: " + result["path"], exported=result["path"], draft=False)
            if self._document and self._document.last_export_warning:
                self._view["warning"] = self._document.last_export_warning
        if state in ("use-result", "saved"):
            self._view["outputName"] = self._view["outputName"].removesuffix(" | Draft")
        if state == "cancelled":
            self._view.update(status=result["error"], error="", report=result.get("report", ""))
        elif state not in ("source", "complete", "edited", "resumed", "sampled", "use-result", "saved"):
            self._view.update(error=result.get("error", "Background removal failed"), status="Background removal failed")
            if result.get("report"):
                self._view["report"] = result["report"]
            self.log.append(self._view["error"], update_status=False)
        self.changed.emit()

    @Slot()
    def useResult(self):
        if not self._closed and not self.running and self._view["output"]:
            if self._document:
                self._submit("save", lambda: dict(state="use-result", path=str(self._document.published_or_export(self.paths.app_root / "Images/Background Removed"))))
            else:
                self.source.setPath(self._view["output"])
                self.resultReady.emit()

    @Slot()
    def saveAs(self):
        if self._closed or self.running or not self._view["output"]:
            return
        suggested = str(Path(self._view["exported"] or self._view["output"]).parent / (Path(self._view["sourceName"]).stem + "-cutout.png"))
        target, _ = QFileDialog.getSaveFileName(None, "Save transparent PNG", suggested, "PNG image (*.png)")
        if not target:
            return
        path = Path(target)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
        if path.resolve() in {Path(self._view[key]).resolve() for key in ("source", "original") if self._view[key]}:
            self._view["error"] = "Choose a new filename. The original image is never overwritten."
            self.changed.emit()
            return
        output = self._view["output"]
        def save():
            if path.resolve() != Path(output).resolve():
                temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    shutil.copyfile(output, temporary)
                    if sha256(temporary) != sha256(output):
                        raise ValueError("The saved copy failed verification.")
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            if self._document:
                self._document.mark_exported(path)
            return dict(state="saved", path=str(path))
        self._submit("save", save)

    @Slot()
    def openOutputFolder(self):
        if self._view["exported"]:
            self.desktop.openFolder(str(Path(self._view["exported"]).parent))

    @Slot()
    def openReport(self):
        if self._view["report"]:
            self.desktop.openFolder(str(Path(self._view["report"]).parent))

    def _delete_preview(self, value):
        url = QUrl(value)
        if url.isLocalFile():
            path = Path(url.toLocalFile())
            if path.resolve().is_relative_to((self.paths.runtime_root / "background-remover/previews").resolve()):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._delete_preview(self._view["sourceUrl"])
        if self._future and not self._future.cancelled():
            try:
                result = self._future.result()
                if result.get("state") == "source":
                    self._delete_preview(result["sourceUrl"])
            except Exception:
                pass
        self._future = None
        discard_queued_events(self)
