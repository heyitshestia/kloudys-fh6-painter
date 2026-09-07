"""Pinned native engine installation and cancellable, bounded local image jobs."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile

from PIL import Image, ImageOps

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_INPUT_PIXELS = 16_000_000
MAX_OUTPUT_PIXELS = 32_000_000
PRESETS = {
    "photo": {"engine": "realesrgan", "noise": -1, "tile": 128, "tta": False},
    "anime": {"engine": "waifu2x", "noise": 0, "tile": 128, "tta": False},
    "text": {"engine": "waifu2x", "noise": -1, "tile": 128, "tta": False},
}


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled("Upscale cancelled. The original image was not changed.")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def settings_for(preset, scale, noise=None, tile=128, gpu="auto", tta=False):
    if preset not in PRESETS or scale not in (2, 4):
        raise ValueError("Choose a supported preset and either 2x or 4x.")
    values = dict(PRESETS[preset], preset=preset, scale=scale, gpu=str(gpu), tta=bool(tta), tile=int(tile))
    if noise is not None:
        values["noise"] = int(noise)
    if values["noise"] not in (-1, 0, 1, 2, 3) or values["tile"] not in (32, 64, 128, 256):
        raise ValueError("Invalid noise removal or tile size.")
    if values["gpu"] not in ("auto", "0", "1", "2", "3"):
        raise ValueError("Choose Auto or a GPU numbered 0 to 3.")
    if preset == "photo":
        values["noise"] = -1
    return values


def read_image(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Choose an image file smaller than 64 MB.")
    with Image.open(path) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Animated images are not supported. Choose a single frame.")
        if original.width * original.height > MAX_INPUT_PIXELS:
            raise ValueError("The source exceeds the 16-megapixel safety limit.")
        original.load()
        oriented = ImageOps.exif_transpose(original)
        # Keep alpha from paletted PNGs too. Native inputs are normalized PNGs.
        return oriented.convert("RGBA")


def output_size(size, options):
    scale = options["scale"]
    result = (size[0] * scale, size[1] * scale)
    # The photo model is intrinsically 4x, even when the requested output is 2x.
    internal_scale = 4 if options["engine"] == "realesrgan" else scale
    if size[0] * size[1] * internal_scale**2 > MAX_OUTPUT_PIXELS:
        raise ValueError("This image is too large for the selected model (32-megapixel processing limit). Resize the source first.")
    return result


class EngineStore:
    def __init__(self, app_root, runtime_root, catalog_path=None):
        self.root = Path(runtime_root) / "upscaler" / "engines"
        self.catalog_path = Path(catalog_path) if catalog_path else Path(app_root) / "tools/upscaler/engines.json"
        self._catalog = None

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return self._catalog

    def directory(self, name):
        spec = self.catalog[name]
        return self.root / (name + "-" + spec["version"] + "-" + spec["sha256"][:12])

    def present(self, name):
        directory = self.directory(name)
        return all((directory / rel).is_file() for rel in self.catalog[name]["files"])

    def verified(self, name, cancel):
        directory = self.directory(name)
        for rel, digest in self.catalog[name]["files"].items():
            check_cancel(cancel)
            target = directory / rel
            if not target.is_file() or target.is_symlink() or sha256(target) != digest:
                return False
        return True

    def ensure(self, name, cancel, progress):
        if os.name != "nt":
            raise RuntimeError("This upscaler currently supports 64-bit Windows with a Vulkan-capable GPU.")
        self.root.mkdir(parents=True, exist_ok=True)
        progress("Verifying local engine...", -1)
        with engine_lock(self.root / (name + ".lock")):
            if self.verified(name, cancel):
                return self.directory(name)
            spec = self.catalog[name]
            with tempfile.TemporaryDirectory(prefix="install-", dir=self.root) as temporary:
                stage = Path(temporary)
                archive = stage / "download.zip"
                request = urllib.request.Request(spec["url"], headers={"User-Agent": "KFPS-Upscaler/1"})
                start = time.monotonic()
                size = 0
                with urllib.request.urlopen(request, timeout=5) as response, archive.open("wb") as output:
                    while True:
                        check_cancel(cancel)
                        block = response.read(64 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > spec["size"] or time.monotonic() - start > 300:
                            raise RuntimeError("Engine download exceeded its size or time limit.")
                        output.write(block)
                        progress(f"Downloading {name}: {size // 1048576} / {spec['size'] // 1048576} MB", -1)
                if size != spec["size"] or sha256(archive) != spec["sha256"]:
                    raise RuntimeError("Engine download verification failed. Nothing was installed; retry the download.")
                extracted = stage / "verified"
                with zipfile.ZipFile(archive) as bundle:
                    for rel, digest in spec["files"].items():
                        check_cancel(cancel)
                        destination = extracted / rel
                        if not destination.resolve().is_relative_to(extracted.resolve()):
                            raise RuntimeError("Invalid engine catalog path.")
                        entry = bundle.getinfo(spec["prefix"] + rel)
                        if entry.file_size > 64 * 1024 * 1024:
                            raise RuntimeError("Engine member exceeds its size limit.")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.open(entry) as src, destination.open("wb") as dst:
                            shutil.copyfileobj(src, dst, 64 * 1024)
                        if sha256(destination) != digest:
                            raise RuntimeError("An engine file failed verification.")
                # Replace only our catalog's files; never extract unlisted archive paths.
                target = self.directory(name)
                for rel in spec["files"]:
                    check_cancel(cancel)
                    destination = target / rel
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(extracted / rel, destination)
            if not self.verified(name, cancel):
                raise RuntimeError("Engine installation did not validate. Retry to repair it.")
        return self.directory(name)


@contextlib.contextmanager
def engine_lock(path):
    import msvcrt
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("Another KFPS instance is preparing this engine. Wait for it to finish and retry.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def command_for(directory, engine, source, target, options):
    exe = "realesrgan-ncnn-vulkan.exe" if engine == "realesrgan" else "waifu2x-ncnn-vulkan.exe"
    command = [str(directory / exe), "-i", str(source), "-o", str(target),
               "-t", str(options["tile"]), "-j", "1:1:1", "-f", "png"]
    if engine == "realesrgan":
        command += ["-s", "4", "-m", str(directory / "models"), "-n", "realesrgan-x4plus"]
    else:
        command += ["-s", str(options["scale"]), "-m", str(directory / "models-cunet"), "-n", str(options["noise"])]
    if options["gpu"] != "auto":
        command += ["-g", options["gpu"]]
    if options["tta"]:
        command += ["-x"]
    return command


def run_native(command, cwd, log_path, cancel, progress, timeout=900):
    from .upscale_process import KillOnCloseJob
    start = time.monotonic()
    with log_path.open("wb") as output, log_path.open("rb") as reader, KillOnCloseJob() as job:
        process = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            job.assign(process)
            tail = ""
            while process.poll() is None:
                check_cancel(cancel)
                elapsed = time.monotonic() - start
                if elapsed > timeout:
                    raise RuntimeError("The upscaler exceeded its 15-minute processing limit. Retry with a smaller image or tile size.")
                if reader.tell() > 8 * 1024 * 1024:
                    raise RuntimeError("Native engine produced excessive diagnostic output.")
                tail = (tail + reader.read(65536).decode("utf-8", "replace"))[-8192:]
                matches = re.findall(r"(\d+(?:\.\d+)?)%", tail)
                progress(f"Upscaling locally ({int(elapsed)}s)...", min(98, float(matches[-1])) if matches else -1)
                cancel.wait(0.15)
            check_cancel(cancel)
            if process.returncode:
                raise RuntimeError(f"Native upscaler exited with code {process.returncode}. Check your Vulkan GPU driver or try a smaller tile. See native.log in the report folder.")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def execute_job(store, source, options, run, output_root, cancel, progress):
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "kfps.upscale-job.v1", "state": "preparing", "source": str(source),
                "settings": options, "started": time.time(), "engine_version": store.catalog[options["engine"]]["version"]}
    report = run / "report.json"
    atomic_json(report, manifest)
    try:
        progress("Checking source image...", -1)
        image = read_image(source)
        target_size = output_size(image.size, options)
        manifest["input_size"] = list(image.size)
        manifest["source_sha256"] = sha256(source)
        alpha = image.getchannel("A")
        transparent = alpha.getextrema()[0] < 255
        manifest["alpha_preserved"] = transparent
        check_cancel(cancel)
        # Native models process RGB. Edge-bleed transparent RGB before inference,
        # then resample the original alpha separately so hidden colors cannot halo.
        if transparent:
            import numpy as np
            import cv2
            pixels = np.array(image)
            hidden = pixels[:, :, 3] == 0
            if hidden.all():
                raise ValueError("The image is fully transparent.")
            if hidden.any():
                _, labels = cv2.distanceTransformWithLabels(hidden.astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
                colors = pixels[:, :, :3][~hidden]
                pixels[hidden, :3] = colors[labels[hidden] - 1]
                del labels, colors
            native_input = Image.fromarray(pixels[:, :, :3])
            del pixels
        else:
            native_input = image.convert("RGB")
        native_input.save(run / "input.png")
        del native_input, image
        directory = store.ensure(options["engine"], cancel, progress)
        manifest["state"] = "processing"
        manifest["command"] = command_for(directory, options["engine"], run / "input.png", run / "native.png", options)
        atomic_json(report, manifest)
        run_native(manifest["command"], directory, run / "native.log", cancel, progress)
        progress("Checking output and preserving transparency...", 99)
        check_cancel(cancel)
        expected_scale = 4 if options["engine"] == "realesrgan" else options["scale"]
        with Image.open(run / "native.png") as produced:
            if produced.size != tuple(v * expected_scale for v in manifest["input_size"]):
                raise RuntimeError("Native engine returned unexpected image dimensions. No output was accepted.")
            result = produced.convert("RGB")
        if result.size != target_size:
            result = result.resize(target_size, Image.Resampling.LANCZOS)
        if transparent:
            result.putalpha(alpha.resize(target_size, Image.Resampling.BILINEAR))
        del alpha
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        safe_stem = re.sub(r'[^\w .-]', "_", Path(source).stem)[:80].strip(" .") or "image"
        destination = output_root / f"{safe_stem}-{options['preset']}-{options['scale']}x-{run.name}.png"
        temporary = run / "complete.png"
        result.save(temporary)
        del result
        with Image.open(temporary) as reopened:
            reopened.load()
            if reopened.size != target_size or (transparent and "A" not in reopened.getbands()):
                raise RuntimeError("Saved output failed validation.")
        check_cancel(cancel)
        output_hash = sha256(temporary)
        os.replace(temporary, destination)
        manifest.update(state="complete", output=str(destination), output_size=list(target_size), output_sha256=output_hash)
    except Cancelled as exc:
        manifest.update(state="cancelled", error=str(exc))
    except Exception as exc:
        manifest.update(state="failed", error=str(exc))
    finally:
        manifest["finished"] = time.time()
        manifest["elapsed_seconds"] = round(manifest["finished"] - manifest["started"], 3)
        try:
            atomic_json(report, manifest)
        except OSError as exc:
            manifest["diagnostic_error"] = "Final report could not be saved: " + str(exc)
        for name in ("input.png", "native.png", "complete.png"):
            try:
                (run / name).unlink(missing_ok=True)
            except OSError as exc:
                manifest.setdefault("cleanup_errors", []).append(str(exc))
    return dict(manifest, report=str(report))
