"""Optional, hash-pinned CPU engine and isolated background-removal transactions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import uuid
import zipfile
import psutil

from PIL import Image

from .upscale_engine import Cancelled, atomic_json, engine_lock, read_image, sha256
from .upscale_process import KillOnCloseJob


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled("Background removal cancelled. The original image was not changed.")


def settings_for(refine=False, cleanup=False, threads=4, mode="anime", color="auto",
                 tolerance=12, enclosed=True, decontaminate=True):
    if not isinstance(refine, bool) or not isinstance(cleanup, bool) or type(threads) not in (int, float) or threads not in (1, 2, 4, 8):
        raise ValueError("Invalid background-removal settings.")
    if (mode not in ("illustration", "anime", "color") or not isinstance(color, str)
            or (color != "auto" and not re.fullmatch(r"#[0-9a-fA-F]{6}", color))
            or type(tolerance) not in (int, float) or not 0 <= tolerance <= 100
            or not isinstance(enclosed, bool) or not isinstance(decontaminate, bool)):
        raise ValueError("Invalid background-removal mode or colour settings.")
    return dict(refine=refine, cleanup=cleanup if mode != "color" else False, threads=int(threads),
                mode=mode, color=color.lower(), tolerance=int(tolerance), enclosed=enclosed, decontaminate=decontaminate)


def _plain_file(path):
    return path.is_file() and not path.is_symlink() and not path.is_junction()


def retry_file_operation(operation, cancel=None):
    for attempt in range(8):
        if cancel is not None:
            check_cancel(cancel)
        try:
            return operation()
        except PermissionError:
            if attempt == 7:
                raise
            delay = 0.05 * (attempt + 1)
            if cancel is None:
                time.sleep(delay)
            else:
                cancel.wait(delay)


def fetch_verified(spec, target, cancel, progress):
    """Keep verified downloads for offline repair; interrupted files never become assets."""
    check_cancel(cancel)
    if _plain_file(target) and target.stat().st_size == spec["size"] and sha256(target) == spec["sha256"]:
        return
    temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".part")
    start, count = time.monotonic(), 0
    name = spec.get("name", "model")
    try:
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "KFPS-Background-Remover/1"})
        with urllib.request.urlopen(request, timeout=5) as response, temporary.open("xb") as output:
            while True:
                check_cancel(cancel)
                block = response.read(64 * 1024)
                if not block:
                    break
                count += len(block)
                if count > spec["size"] or time.monotonic() - start > 600:
                    raise RuntimeError("Engine download exceeded its size or 10-minute time limit.")
                output.write(block)
                progress(f"Downloading {name}: {count / 1048576:.1f} / {spec['size'] / 1048576:.1f} MB", -1)
        if count != spec["size"] or sha256(temporary) != spec["sha256"]:
            raise RuntimeError("Engine download failed verification. Retry to download a verified copy.")
        check_cancel(cancel)
        retry_file_operation(lambda: os.replace(temporary, target), cancel)
    finally:
        temporary.unlink(missing_ok=True)


def wheel_entries(bundle):
    total, names = 0, set()
    for entry in bundle.infolist():
        if entry.is_dir():
            continue
        name = entry.filename
        path = PurePosixPath(name)
        total += entry.file_size
        mode = entry.external_attr >> 16
        if (entry.orig_filename != name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                or name.casefold() in names or stat.S_ISLNK(mode)
                or entry.file_size > 128 * 1048576 or total > 256 * 1048576
                or len(names) >= 10000):
            raise RuntimeError("Unsafe or oversized engine archive.")
        names.add(name.casefold())
        yield entry


class BackgroundEngineStore:
    def __init__(self, runtime_root, catalog_path):
        self.root = Path(runtime_root) / "background-remover" / "engines"
        self.catalog_path = Path(catalog_path)
        self._catalog = None

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            if self._catalog.get("schema") != "kfps.background-engine.v1":
                raise ValueError("Unsupported background-removal engine catalog. Repair KFPS.")
        return self._catalog

    @property
    def directory(self):
        digest = hashlib.sha256(json.dumps(self.catalog, sort_keys=True).encode()).hexdigest()[:16]
        return self.root / ("cpu-" + digest)

    @property
    def model(self):
        return self.root / (self.catalog["model"]["sha256"] + ".onnx")

    def present(self):
        return self.model.is_file() and (self.directory / "onnxruntime/capi/onnxruntime_pybind11_state.pyd").is_file()

    def _archive(self, spec):
        return self.root / (spec["sha256"] + ".whl")

    def _verify_runtime(self, cancel, progress):
        if not self.directory.is_dir() or self.directory.is_symlink() or self.directory.is_junction():
            return False
        expected = set()
        for spec in self.catalog["wheels"]:
            progress("Verifying " + spec["name"].split("-")[0] + "...", -1)
            with zipfile.ZipFile(self._archive(spec)) as bundle:
                for entry in wheel_entries(bundle):
                    check_cancel(cancel)
                    path = self.directory / entry.filename
                    expected.add(path.relative_to(self.directory).as_posix())
                    if not _plain_file(path) or not path.resolve().is_relative_to(self.directory.resolve()):
                        return False
                    if path.stat().st_size != entry.file_size:
                        return False
                    with bundle.open(entry) as content:
                        if sha256(path) != hashlib.file_digest(content, "sha256").hexdigest():
                            return False
        # The child uses -B. No extra Python code or stale package files are accepted.
        actual = {p.relative_to(self.directory).as_posix() for p in self.directory.rglob("*") if p.is_file()}
        return actual == expected

    def ensure(self, cancel, progress):
        if os.name != "nt":
            raise RuntimeError("The local background remover currently requires Windows x64 and KFPS's Python 3.12 runtime.")
        self.root.mkdir(parents=True, exist_ok=True)
        with engine_lock(self.root / "prepare.lock"):
            progress("Checking local background-removal engine...", -1)
            for spec in self.catalog["wheels"]:
                fetch_verified(spec, self._archive(spec), cancel, progress)
            fetch_verified(self.catalog["model"], self.model, cancel, progress)
            if not self._verify_runtime(cancel, progress):
                progress("Preparing isolated CPU runtime...", -1)
                with tempfile.TemporaryDirectory(prefix="install-", dir=self.root) as temporary:
                    stage = Path(temporary) / "site"
                    stage.mkdir()
                    for spec in self.catalog["wheels"]:
                        with zipfile.ZipFile(self._archive(spec)) as bundle:
                            for entry in wheel_entries(bundle):
                                check_cancel(cancel)
                                destination = stage / entry.filename
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                with bundle.open(entry) as source, destination.open("xb") as target:
                                    shutil.copyfileobj(source, target, 64 * 1024)
                    # Only our catalog-specific runtime is swapped; user files are outside it.
                    old = self.root / ("replaced-" + uuid.uuid4().hex)
                    if self.directory.is_symlink() or self.directory.is_junction():
                        raise RuntimeError("The isolated engine folder is a link. Restore a regular engine folder before retrying.")
                    if self.directory.exists():
                        retry_file_operation(lambda: os.replace(self.directory, old), cancel)
                    try:
                        retry_file_operation(lambda: os.replace(stage, self.directory), cancel)
                    except Exception:
                        if old.exists():
                            retry_file_operation(lambda: os.replace(old, self.directory))
                        raise
                    else:
                        if old.exists():
                            retry_file_operation(lambda: shutil.rmtree(old))
                if not self._verify_runtime(cancel, progress):
                    raise RuntimeError("CPU runtime verification failed. Retry to repair it.")
        return self.directory, self.model


def run_worker(command, run, cancel, progress, timeout=180, memory_limit=2*1024**3):
    start = time.monotonic()
    log_path = run / "worker.log"
    with log_path.open("wb") as output, log_path.open("rb") as reader, KillOnCloseJob() as job:
        process = subprocess.Popen(command, cwd=run, stdout=output, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            job.assign(process)
            try:
                monitor = psutil.Process(process.pid)
            except psutil.NoSuchProcess:
                monitor = None
            peak = 0
            while process.poll() is None:
                check_cancel(cancel)
                elapsed = time.monotonic() - start
                if elapsed > timeout:
                    raise RuntimeError("Background removal exceeded its 3-minute processing limit. Try a smaller image.")
                if log_path.stat().st_size > 2 * 1048576:
                    raise RuntimeError("Background-removal worker produced excessive diagnostic output.")
                try:
                    if monitor is not None:
                        # Windows venv python.exe is a redirector: the actual
                        # worker may be its child rather than the launched PID.
                        resident = 0
                        for member in [monitor, *monitor.children(recursive=True)]:
                            try:
                                resident += member.memory_info().rss
                            except psutil.NoSuchProcess:
                                pass
                        peak = max(peak, resident)
                except psutil.NoSuchProcess:
                    pass
                if peak > memory_limit:
                    raise RuntimeError(f"Background removal reached its {memory_limit/1024**3:g} GB memory safety limit. Try a smaller image.")
                messages = reader.read(65536).decode("utf-8", "replace")
                phase = "Removing background locally"
                if "INFERENCE" not in messages and elapsed < 1:
                    phase = "Starting CPU worker"
                progress(f"{phase} ({elapsed:.0f}s)...", -1)
                cancel.wait(0.1)
            check_cancel(cancel)
            if process.returncode:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                detail = next((line[6:] for line in reversed(tail.splitlines()) if line.startswith("ERROR ")), "See worker.log in the run report.")
                raise RuntimeError(f"Background-removal worker failed ({process.returncode}). {detail}")
            return dict(pid=process.pid, peak_mb=round(peak/1048576,1), elapsed_seconds=round(time.monotonic()-start,3))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def execute_job(store, python, source, options, run, output_root, cancel, progress):
    run, source = Path(run), Path(source)
    report = run / "report.json"
    created = False
    manifest = dict(schema="kfps.background-remove-job.v1", state="preparing", source=str(source),
                    settings=options, started=time.time(), phase="prepare", timings={})
    try:
        run.mkdir(parents=True, exist_ok=False)
        created = True
        atomic_json(report, manifest)
        options = settings_for(**options)
        manifest["settings"] = options
        manifest["engine_id"] = "flat-color-v1" if options["mode"] == "color" else store.catalog["id"]
        if options["mode"] != "color":
            manifest["model_sha256"] = store.catalog["model"]["sha256"]
        manifest["phase"] = "read-source"
        phase_start = time.monotonic()
        progress("Checking source image...", -1)
        source_hash = sha256(source)
        image = read_image(source)
        if sha256(source) != source_hash:
            raise RuntimeError("The source changed while it was being read. Retry with the saved image.")
        alpha = image.getchannel("A")
        if alpha.getextrema()[1] == 0:
            raise ValueError("The image is fully transparent; there is no visible subject to keep.")
        transparent = alpha.getextrema()[0] < 255
        manifest.update(source_sha256=source_hash, input_size=list(image.size), had_transparency=transparent)
        # A private snapshot allows restoration/corrections even if the original
        # is later moved. It is never included in a diagnostic upload.
        image.save(run / "source.png")
        manifest["source_snapshot_sha256"] = sha256(run / "source.png")
        manifest["timings"]["source_seconds"] = round(time.monotonic() - phase_start, 3)
        check_cancel(cancel)
        if transparent and not options["refine"]:
            manifest["mode"] = "existing-transparency-preserved"
            result = image
        else:
            executable = Path(python)
            if not executable.is_file() or not executable.name.lower().startswith("python"):
                raise RuntimeError("KFPS's Python runtime is missing. Repair KFPS before running background removal.")
            manifest.update(phase="prepare-engine", mode="flat-color" if options["mode"] == "color" else "isnet-" + options["mode"] + "-cpu")
            atomic_json(report, manifest)
            phase_start = time.monotonic()
            directory, model = (run, run / "unused") if options["mode"] == "color" else store.ensure(cancel, progress)
            manifest["timings"]["engine_prepare_seconds"] = round(time.monotonic() - phase_start, 3)
            image.save(run / "input.png")
            atomic_json(run / "settings.json", options)
            manifest.update(phase="inference", state="processing")
            atomic_json(report, manifest)
            command = [str(python), "-I", "-B", "-X", "utf8", "-u", str(Path(__file__).with_name("background_remove_worker.py")),
                       str(directory), str(model), str(run / "input.png"), str(run / "processed.png"), str(run / "settings.json")]
            phase_start = time.monotonic()
            manifest["process"] = run_worker(command, run, cancel, progress)
            manifest["timings"]["worker_seconds"] = round(time.monotonic() - phase_start, 3)
            with Image.open(run / "processed.png") as produced:
                if produced.size != image.size or produced.mode != "RGBA":
                    raise RuntimeError("The engine returned invalid image dimensions or transparency.")
                result = produced.copy()
            from .background_remove_processing import validate_result
            validate_result(image, result, color_edges=options["mode"] == "color")
            manifest["worker"] = json.loads((run / "worker-result.json").read_text(encoding="utf-8"))
        from .background_remove_processing import quality_warning
        manifest["warning"] = quality_warning(result)
        manifest["phase"] = "save-output"
        phase_start = time.monotonic()
        progress("Verifying and saving transparent PNG...", 99)
        check_cancel(cancel)
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        safe_stem = re.sub(r'[^\w .-]', "_", source.stem)[:80].strip(" .") or "image"
        destination = output_root / f"{safe_stem}-cutout-{run.name}.png"
        temporary = run / "complete.png"
        result.save(temporary, format="PNG")
        with Image.open(temporary) as reopened:
            reopened.load()
            if reopened.mode != "RGBA" or reopened.size != image.size or reopened.tobytes() != result.tobytes():
                raise RuntimeError("Saved PNG failed validation. No result was accepted.")
        check_cancel(cancel)
        output_hash = sha256(temporary)
        retry_file_operation(lambda: os.replace(temporary, destination), cancel)
        manifest["timings"]["save_seconds"] = round(time.monotonic() - phase_start, 3)
        manifest.update(state="complete", phase="complete", output=str(destination),
                        output_size=list(image.size), output_sha256=output_hash)
    except Cancelled as exc:
        manifest.update(state="cancelled", error=str(exc))
    except Exception as exc:
        manifest.update(state="failed", error=str(exc))
    finally:
        manifest.update(finished=time.time())
        manifest["elapsed_seconds"] = round(manifest["finished"] - manifest["started"], 3)
        if created:
            try:
                atomic_json(report, manifest)
            except OSError as exc:
                manifest["diagnostic_error"] = "Report could not be saved: " + str(exc)
            for name in ("input.png", "processed.png", "complete.png", "settings.json"):
                try:
                    (run / name).unlink(missing_ok=True)
                except OSError as exc:
                    manifest.setdefault("cleanup_errors", []).append(str(exc))
    return dict(manifest, report=str(report) if created and report.is_file() else "")
