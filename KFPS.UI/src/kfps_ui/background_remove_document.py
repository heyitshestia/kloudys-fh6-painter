"""Bounded, atomic edit history for a single local cutout. No Qt or model state."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re
import time
import uuid

import cv2
import numpy as np
from PIL import Image

from .upscale_engine import atomic_json, read_image, sha256

MAX_ENTRIES = 33
MAX_HISTORY_BYTES = 128 * 1048576


def _revision_path(folder, name):
    if not isinstance(name, str) or not re.fullmatch(r"revision-[a-f0-9]{32}\.png", name):
        raise ValueError("Invalid correction history filename.")
    path = folder / name
    if path.is_symlink() or path.is_junction() or path.resolve().parent != folder.resolve():
        raise ValueError("Correction history contains a file link.")
    return path


def paint_mask(original, current, tool, points, diameter=40, tolerance=20):
    if tool not in ("erase", "restore", "wand"):
        raise ValueError("Unknown correction tool.")
    if (type(diameter) not in (int, float) or not math.isfinite(diameter) or not 1 <= diameter <= 1000
            or type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 <= tolerance <= 100):
        raise ValueError("Invalid correction size or tolerance.")
    if not isinstance(points, (list, tuple)) or not 1 <= len(points) <= 4096:
        raise ValueError("The correction stroke is empty or too large.")
    width, height = original.size
    pixels = []
    for point in points:
        if (not isinstance(point, (list, tuple)) or len(point) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in point)):
            raise ValueError("Invalid correction coordinates.")
        pixels.append((min(width-1, round(point[0]*width)), min(height-1, round(point[1]*height))))
    if current.size != original.size or original.mode != "RGBA" or current.mode != "RGBA":
        raise ValueError("Correction images do not match.")
    before, result = np.asarray(original), np.array(current)
    if tool == "wand":
        mask = np.zeros((height+2, width+2), np.uint8)
        cv2.floodFill(np.ascontiguousarray(before[:,:,:3]), mask, pixels[0], (0,0,0),
                     (tolerance,)*3, (tolerance,)*3, 4 | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY | (255 << 8))
        result[mask[1:-1,1:-1] > 0, 3] = 0
    else:
        radius = max(1, round(diameter/2))
        left = max(0, min(p[0] for p in pixels)-radius-2)
        top = max(0, min(p[1] for p in pixels)-radius-2)
        right = min(width, max(p[0] for p in pixels)+radius+3)
        bottom = min(height, max(p[1] for p in pixels)+radius+3)
        coverage = np.zeros((bottom-top, right-left), np.uint8)
        local = [(x-left,y-top) for x,y in pixels]
        for first, second in zip(local, local[1:]):
            cv2.line(coverage, first, second, 255, 2*radius, cv2.LINE_AA)
        for point in (local[0], local[-1]):
            cv2.circle(coverage, point, radius, 255, -1, cv2.LINE_AA)
        amount = coverage.astype(np.float32)/255
        target = result[top:bottom,left:right]
        source = before[top:bottom,left:right]
        if tool == "erase":
            target[:,:,3] = np.rint(target[:,:,3]*(1-amount)).astype(np.uint8)
        else:
            target[:] = np.rint(target*(1-amount[:,:,None])+source*amount[:,:,None]).astype(np.uint8)
    result[:,:,3] = np.minimum(result[:,:,3], before[:,:,3])
    return Image.fromarray(result)


class MaskDocument:
    def __init__(self, run, state):
        self.run = Path(run)
        self.folder = self.run / "edits"
        self.path = self.run / "edit-state.json"
        self.state = state
        self.last_export_warning = ""

    @classmethod
    def create(cls, run, output, source_name):
        run = Path(run)
        folder = run / "edits"
        folder.mkdir(exist_ok=False)
        original = read_image(run / "source.png")
        result = read_image(output)
        if original.size != result.size:
            raise ValueError("Cutout dimensions do not match the source snapshot.")
        state = dict(schema="kfps.background-mask.v1", cursor=0, entries=[],
                     source_sha256=sha256(run / "source.png"), size=list(original.size),
                     source_name=Path(source_name).name, source_original=str(source_name),
                     initial_output=str(output), published_path=str(output), published_sha256=sha256(output))
        document = cls(run, state)
        document._commit(result, {"tool": "base"})
        return document

    @classmethod
    def open(cls, run):
        run = Path(run)
        path = run / "edit-state.json"
        if (path.stat().st_size > 128*1024
                or any(p.is_symlink() or p.is_junction() for p in (run,run/"edits",path))):
            raise ValueError("Invalid correction session.")
        state = json.loads(path.read_text(encoding="utf-8"))
        if (state.get("schema") != "kfps.background-mask.v1" or not isinstance(state.get("entries"), list)
                or not 1 <= len(state["entries"]) <= MAX_ENTRIES or type(state.get("cursor")) is not int
                or not 0 <= state["cursor"] < len(state["entries"])):
            raise ValueError("Unsupported or incomplete correction session.")
        document = cls(run, state)
        for entry in state["entries"]:
            _revision_path(document.folder, entry["file"])
        document.original()
        document.current()
        return document

    @property
    def current_path(self):
        return _revision_path(self.folder, self.state["entries"][self.state["cursor"]]["file"])

    @property
    def can_undo(self):
        return self.state["cursor"] > 0

    @property
    def can_redo(self):
        return self.state["cursor"]+1 < len(self.state["entries"])

    @property
    def draft(self):
        return self.state["entries"][self.state["cursor"]]["sha256"] != self.state.get("published_sha256")

    def original(self):
        source = self.run / "source.png"
        if source.is_symlink() or source.is_junction() or sha256(source) != self.state["source_sha256"]:
            raise ValueError("The source snapshot changed. Reopen the original image to start a new session.")
        result = read_image(source)
        if list(result.size) != self.state["size"]:
            raise ValueError("The source snapshot dimensions changed.")
        return result

    def current(self):
        entry = self.state["entries"][self.state["cursor"]]
        path = self.current_path
        if sha256(path) != entry["sha256"]:
            raise ValueError("The saved correction changed or is incomplete. It was not loaded.")
        result = read_image(path)
        if list(result.size) != self.state["size"]:
            raise ValueError("Saved correction dimensions changed.")
        return result

    def _commit(self, image, action):
        started = time.monotonic()
        name = "revision-" + uuid.uuid4().hex + ".png"
        destination = _revision_path(self.folder, name)
        previous = self.state
        state = copy.deepcopy(previous)
        try:
            image.save(destination, format="PNG")
            with Image.open(destination) as check:
                check.load()
                if check.mode != "RGBA" or check.size != image.size or check.tobytes() != image.tobytes():
                    raise ValueError("The correction PNG failed verification.")
            state["entries"] = state["entries"][:state["cursor"]+1]
            state["entries"].append(dict(file=name, sha256=sha256(destination), bytes=destination.stat().st_size,
                                         action=action, saved=time.time()))
            while len(state["entries"]) > 2 and (len(state["entries"]) > MAX_ENTRIES
                    or sum(entry["bytes"] for entry in state["entries"]) > MAX_HISTORY_BYTES):
                state["entries"].pop(1)
            state["cursor"] = len(state["entries"])-1
            state["last_save_seconds"] = round(time.monotonic()-started,3)
            atomic_json(self.path, state)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        self.state = state
        used = {entry["file"] for entry in state["entries"]}
        for entry in previous["entries"]:
            if entry["file"] not in used:
                path = _revision_path(self.folder, entry["file"])
                for owned in (path, path.with_name(path.stem+"-preview.png"), path.with_name(path.stem+"-mask.png")):
                    try:
                        owned.unlink(missing_ok=True)
                    except OSError:
                        pass

    def edit(self, tool, points, diameter=40, tolerance=20):
        original, current = self.original(), self.current()
        result = paint_mask(original, current, tool, points, diameter, tolerance)
        if result.tobytes() == current.tobytes():
            return False
        self._commit(result, dict(tool=tool, point_count=len(points), diameter=diameter, tolerance=tolerance))
        return True

    def step(self, amount):
        if amount not in (-1,1):
            raise ValueError("Invalid history step.")
        index = self.state["cursor"] + amount
        if not 0 <= index < len(self.state["entries"]):
            return False
        state = dict(self.state, cursor=index)
        probe = MaskDocument(self.run, state)
        probe.current()
        atomic_json(self.path, state)
        self.state = state
        return True

    def reset(self):
        base = _revision_path(self.folder, self.state["entries"][0]["file"])
        if sha256(base) != self.state["entries"][0]["sha256"]:
            raise ValueError("The initial cutout changed; reset was not applied.")
        self._commit(read_image(base), {"tool": "reset"})

    def export(self, output_root):
        image = self.current()
        folder = Path(output_root)
        folder.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^\w .-]", "_", Path(self.state["source_name"]).stem)[:80].strip(" .") or "image"
        target = folder / (stem + "-cutout-edited-" + uuid.uuid4().hex[:10] + ".png")
        temporary = target.with_suffix(".tmp")
        try:
            image.save(temporary, format="PNG")
            if sha256(temporary) != self.state["entries"][self.state["cursor"]]["sha256"]:
                # Different Pillow versions can encode identical pixels differently.
                if read_image(temporary).tobytes() != image.tobytes():
                    raise ValueError("The exported correction failed verification.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        self.mark_exported(target)
        return target

    def published_or_export(self, output_root):
        published = self.state.get("published_path", "")
        if not self.draft and published:
            path = Path(published)
            if path.is_file() and sha256(path) == self.state["published_sha256"]:
                return path
        return self.export(output_root)

    def mark_exported(self, target):
        state = dict(self.state, published_path=str(target), published_sha256=self.state["entries"][self.state["cursor"]]["sha256"])
        self.last_export_warning = ""
        try:
            atomic_json(self.path, state)
        except OSError as exc:
            self.last_export_warning = "PNG saved, but its session record could not be updated: " + str(exc)
        else:
            self.state = state
