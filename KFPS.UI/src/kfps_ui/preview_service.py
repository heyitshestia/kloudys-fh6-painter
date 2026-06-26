from __future__ import annotations

import hashlib
from pathlib import Path

from .app_paths import AppPaths
from .qt_utils import file_url


class PreviewService:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.cache = paths.runtime_root / "qml-json-previews"

    def preview_for_json(self, json_path: str | Path) -> str:
        path = Path(json_path)
        if not path.is_file(): return ""
        for candidate in self._nearby(path):
            if candidate.is_file(): return file_url(candidate)
        try:
            from json_preview_renderer import render_json_preview
            fingerprint = f"{path.resolve()}|{path.stat().st_mtime_ns}|{path.stat().st_size}"
            target = self.cache / (hashlib.sha256(fingerprint.encode()).hexdigest()[:20] + ".png")
            if not target.exists():
                data = render_json_preview(path, max_size=900)
                if data:
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            return file_url(target) if target.exists() else ""
        except Exception:
            return ""

    def _nearby(self, path: Path):
        stem = path.stem
        candidates = [path.with_suffix(".png")]
        parent = path.parent
        run = parent.parent if parent.name.lower() in {"finals", "checkpoints"} else parent
        for folder in [parent, run / "previews", run / "finals"]:
            if folder.exists():
                candidates.extend(folder.glob(f"{stem}*.png"))
                # checkpoint naming variants
                prefix = stem.rsplit(".", 1)[0]
                candidates.extend(folder.glob(f"{prefix}*preview*.png"))
        return sorted(set(candidates), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
