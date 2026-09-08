"""Opt-in cache repair/restart and resource checks using the real local CPU worker."""
from __future__ import annotations

from datetime import datetime
import gc
import json
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import patch

import numpy as np
from PIL import Image
import psutil

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
from kfps_ui.background_remove_engine import BackgroundEngineStore, execute_job, settings_for
from kfps_ui.upscale_engine import sha256


def main():
    out = ROOT / "runtime/background-remover/validation" / datetime.now().strftime("resilience-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    with Image.open(UI / "assets/mini-kloudy.png") as opened:
        image = opened.convert("RGBA")
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    image.save(out / "transparent.png")
    white = Image.new("RGBA", image.size, "white")
    white.alpha_composite(image)
    white.convert("RGB").save(out / "source.png")
    before = sha256(out / "source.png")
    installed = BackgroundEngineStore(ROOT / "runtime", ROOT / "tools/background_remover/engine.json")
    assert installed.present(), "Run the first-use installation before this offline-only test."
    # Fault injection never changes the working application's engine cache.
    store = BackgroundEngineStore(out / "test-runtime", installed.catalog_path)
    shutil.copytree(installed.root, store.root)
    summary = dict(jobs=[], errors=[], python=sys.version, offline=True)
    stop = threading.Event()
    peak = [0]
    def sample():
        while not stop.wait(0.05):
            for child in psutil.Process().children():
                try:
                    if any("background_remove_worker.py" in arg for arg in child.cmdline()):
                        peak[0] = max(peak[0], child.memory_info().rss)
                except psutil.Error:
                    pass
    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    def job(name, source="source.png", options=None):
        peak[0] = 0
        result = execute_job(store, sys.executable, out / source, options or settings_for(), out / name, out / "outputs",
                             threading.Event(), lambda *_: None)
        assert result["state"] == "complete", result
        assert sha256(out / "source.png") == before
        assert not any("background_remove_worker.py" in " ".join(c.cmdline()) for c in psutil.Process().children())
        gc.collect()
        summary["jobs"].append(dict(name=name, seconds=result["elapsed_seconds"], sha256=result["output_sha256"],
                                    worker_peak_mb=round(peak[0] / 1048576, 1),
                                    parent_rss_mb=round(psutil.Process().memory_info().rss / 1048576, 1),
                                    report=result["report"]))
        return result
    try:
        with patch("urllib.request.urlopen", side_effect=RuntimeError("Offline: no network permitted in this test")):
            baseline = job("baseline")
            directory = store.directory.resolve()
            assert directory.is_relative_to((out / "test-runtime").resolve())
            native = directory / "onnxruntime/capi/onnxruntime_pybind11_state.pyd"
            original = native.read_bytes()
            native.unlink()
            try:
                repaired = job("missing-native-repaired")
                assert native.read_bytes() == original
                assert baseline["output_sha256"] == repaired["output_sha256"]
            finally:
                if not native.is_file():
                    native.write_bytes(original)
            module = directory / "flatbuffers/__init__.py"
            original = module.read_bytes()
            module.write_bytes(b"# Deliberately damaged private test cache.\n")
            try:
                repaired = job("damaged-module-repaired")
                assert module.read_bytes() == original
                assert baseline["output_sha256"] == repaired["output_sha256"]
            finally:
                if module.read_bytes() != original:
                    module.write_bytes(original)
            # A new store simulates restart: no in-memory validation receipt is reused.
            store = BackgroundEngineStore(out / "test-runtime", installed.catalog_path)
            for index in range(3):
                result = job("repeat-" + str(index))
                assert result["output_sha256"] == baseline["output_sha256"]
            result = job("unicode-\u65e5\u672c\u8a9e")
            assert result["output_sha256"] == baseline["output_sha256"]
            refined = job("refined-alpha", "transparent.png", settings_for(refine=True, cleanup=True))
            with Image.open(refined["output"]) as result:
                assert np.all(np.asarray(result.getchannel("A")) <= np.asarray(image.getchannel("A")))
                assert result.convert("RGB").tobytes() == image.convert("RGB").tobytes()
            model = store.model
            backup = model.with_suffix(".test-backup")
            assert not backup.exists()
            model.rename(backup)
            try:
                failure = execute_job(store, sys.executable, out / "source.png", settings_for(), out / "offline-missing-model",
                                      out / "outputs", threading.Event(), lambda *_: None)
                assert failure["state"] == "failed" and "Offline" in failure["error"]
                assert "output" not in failure
                summary["offline_missing_model"] = failure["report"]
            finally:
                backup.rename(model)
            job("recovered-after-offline-failure")
    except Exception:
        import traceback
        summary["errors"].append(traceback.format_exc())
    finally:
        stop.set()
        monitor.join(timeout=2)
        disposable = (out / "test-runtime").resolve()
        assert disposable.parent == out.resolve()
        shutil.rmtree(disposable)
        (out / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(dict(results=str(out / "results.json"), **summary), indent=2))
    return int(bool(summary["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
