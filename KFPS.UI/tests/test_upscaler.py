from __future__ import annotations

import json
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
from kfps_ui.upscale_engine import (
    Cancelled, EngineStore, PRESETS, command_for, execute_job, output_size,
    read_image, run_native, settings_for,
)


class UpscalerTests(unittest.TestCase):
    def test_presets_have_safe_distinct_recommended_settings(self):
        self.assertEqual(-1, settings_for("text", 2)["noise"])
        self.assertEqual(0, settings_for("anime", 2)["noise"])
        self.assertEqual("realesrgan", settings_for("photo", 2)["engine"])
        for name in PRESETS:
            self.assertEqual(128, settings_for(name, 2)["tile"])
            self.assertFalse(settings_for(name, 2)["tta"])

    def test_rejects_invalid_controls(self):
        for kwargs in ({"preset": "unknown"}, {"scale": 3}, {"tile": 0}, {"noise": 9}, {"gpu": "-1"}):
            values = dict(preset="anime", scale=2)
            values.update(kwargs)
            with self.assertRaises(ValueError):
                settings_for(**values)

    def test_internal_photo_four_x_counts_towards_memory_limit(self):
        with self.assertRaises(ValueError):
            output_size((2000, 2000), settings_for("photo", 2))
        self.assertEqual((4000, 4000), output_size((2000, 2000), settings_for("anime", 2)))

    def test_photo_two_x_requests_native_four_x(self):
        cmd = command_for(Path("engine"), "realesrgan", Path("a.png"), Path("b.png"), settings_for("photo", 2))
        self.assertEqual("4", cmd[cmd.index("-s") + 1])
        self.assertEqual("1:1:1", cmd[cmd.index("-j") + 1])
        self.assertNotIn("-x", cmd)

    def test_waifu_controls_are_forwarded(self):
        cmd = command_for(Path("engine"), "waifu2x", Path("a.png"), Path("b.png"), settings_for("text", 4, tile=64, gpu="1", tta=True))
        for flag, value in (("-s", "4"), ("-t", "64"), ("-g", "1"), ("-n", "-1")):
            self.assertEqual(value, cmd[cmd.index(flag) + 1])
        self.assertIn("-x", cmd)

    def test_catalog_is_pinned_and_all_paths_are_relative(self):
        store = EngineStore(ROOT, ROOT / "runtime")
        for name in PRESETS.values():
            spec = store.catalog[name["engine"]]
            self.assertTrue(spec["url"].startswith("https://github.com/"))
            self.assertNotIn("latest", spec["url"])
            self.assertEqual(64, len(spec["sha256"]))
            for path, digest in spec["files"].items():
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn("..", Path(path).parts)
                self.assertEqual(64, len(digest))

    def test_missing_catalog_does_not_fail_service_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EngineStore(Path(tmp), Path(tmp))
            with self.assertRaises(FileNotFoundError):
                store.present("waifu2x")

    def test_alpha_palette_and_orientation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "palette.png"
            image = Image.new("P", (8, 6), 1)
            image.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
            image.info["transparency"] = 1
            image.save(path)
            actual = read_image(path)
            self.assertEqual("RGBA", actual.mode)
            self.assertEqual((0, 0), actual.getchannel("A").getextrema())
            image = Image.new("RGB", (8, 6), "red")
            exif = image.getexif(); exif[274] = 6
            image.save(path.with_suffix(".jpg"), exif=exif)
            self.assertEqual((6, 8), read_image(path.with_suffix(".jpg")).size)

    def test_animated_and_invalid_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "animation.png"
            Image.new("RGB", (8, 8), "red").save(path, save_all=True, append_images=[Image.new("RGB", (8, 8), "blue")], duration=100)
            with self.assertRaises(ValueError):
                read_image(path)
            path.write_bytes(b"not an image")
            with self.assertRaises(OSError):
                read_image(path)

    def _job(self, tmp, preset="anime", scale=2, native=None, cancel=None):
        root = Path(tmp)
        source = root / "source.png"
        image = Image.new("RGBA", (12, 8), (240, 40, 60, 0))
        for x in range(3, 9):
            for y in range(2, 6):
                image.putpixel((x, y), (240, 40, 60, 255))
        image.save(source)
        before = source.read_bytes()
        store = EngineStore(ROOT, root)
        def produce(command, *_):
            with Image.open(command[command.index("-i") + 1]) as image:
                factor = int(command[command.index("-s") + 1])
                image.resize((image.width * factor, image.height * factor)).save(command[command.index("-o") + 1])
        with patch.object(store, "ensure", return_value=root), patch("kfps_ui.upscale_engine.run_native", side_effect=native or produce):
            result = execute_job(store, source, settings_for(preset, scale), root / "run", root / "outputs", cancel or threading.Event(), lambda *_: None)
        self.assertEqual(before, source.read_bytes())
        self.assertTrue((root / "run/report.json").exists())
        self.assertFalse((root / "run/input.png").exists())
        self.assertFalse((root / "run/native.png").exists())
        return result

    def test_output_validates_alpha_dimensions_and_preserves_original(self):
        for preset in PRESETS:
            for scale in (2, 4):
                with self.subTest(preset=preset, scale=scale), tempfile.TemporaryDirectory() as tmp:
                    result = self._job(tmp, preset, scale)
                    self.assertEqual("complete", result["state"])
                    with Image.open(result["output"]) as image:
                        self.assertEqual((12 * scale, 8 * scale), image.size)
                        self.assertEqual(0, image.getpixel((0, 0))[3])
                        self.assertEqual(255, image.getpixel((6 * scale, 4 * scale))[3])

    def test_native_failure_is_reported_without_a_completed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._job(tmp, native=lambda *_: (_ for _ in ()).throw(RuntimeError("test failure")))
            self.assertEqual("failed", result["state"])
            self.assertIn("test failure", result["error"])
            self.assertNotIn("output", result)

    def test_wrong_native_dimensions_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            def wrong(command, *_):
                Image.new("RGB", (1, 1)).save(command[command.index("-o") + 1])
            self.assertEqual("failed", self._job(tmp, native=wrong)["state"])

    def test_precancelled_job_records_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cancel = threading.Event(); cancel.set()
            self.assertEqual("cancelled", self._job(tmp, cancel=cancel)["state"])

    def test_fully_transparent_image_rejected_before_native_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "transparent.png"
            Image.new("RGBA", (12, 12)).save(source)
            store = EngineStore(ROOT, root)
            with patch.object(store, "ensure") as ensure:
                result = execute_job(store, source, settings_for("anime", 2), root / "run", root / "outputs", threading.Event(), lambda *_: None)
                self.assertEqual("failed", result["state"])
                ensure.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows native lifecycle")
    def test_running_native_process_is_cancelled_and_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            cancel = threading.Event()
            timer = threading.Timer(0.4, cancel.set); timer.start()
            started = time.monotonic()
            try:
                with self.assertRaises(Cancelled):
                    run_native([sys.executable, "-c", "import time; time.sleep(60)"], tmp, Path(tmp) / "native.log", cancel, lambda *_: None)
            finally:
                timer.cancel()
            self.assertLess(time.monotonic() - started, 3)

    @unittest.skipUnless(os.name == "nt", "Windows native lifecycle")
    def test_native_timeout_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            for script, timeout in (("import time; time.sleep(60)", 0.1), ("raise SystemExit(7)", 10)):
                with self.assertRaises(RuntimeError):
                    run_native([sys.executable, "-c", script], tmp, Path(tmp) / "native.log", threading.Event(), lambda *_: None, timeout=timeout)

    @unittest.skipUnless(os.name == "nt", "Windows native lifecycle")
    def test_job_close_terminates_its_child(self):
        from kfps_ui.upscale_process import KillOnCloseJob
        child = None
        try:
            with KillOnCloseJob() as job:
                child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                job.assign(child)
                self.assertIsNone(child.poll())
            self.assertIsNotNone(child.wait(timeout=3))
        finally:
            if child and child.poll() is None:
                child.kill()
                child.wait(timeout=3)

    def test_splash_artwork_fits_its_label(self):
        content = (UI / "src/kfps_ui/startup_splash.py").read_text()
        self.assertIn("self.art.height()", content)
        with Image.open(UI / "assets/mini-kloudy.png") as image:
            self.assertIn("A", image.getbands())
            self.assertEqual(0, image.getchannel("A").getpixel((0, 0)))

    def test_final_report_failure_does_not_hide_completed_output(self):
        from kfps_ui.upscale_engine import atomic_json
        def write(path, value):
            if value["state"] == "complete":
                raise PermissionError("report locked")
            atomic_json(path, value)
        with tempfile.TemporaryDirectory() as tmp, patch("kfps_ui.upscale_engine.atomic_json", side_effect=write):
            result = self._job(tmp)
            self.assertEqual("complete", result["state"])
            self.assertTrue(Path(result["output"]).is_file())
            self.assertIn("report locked", result["diagnostic_error"])

    def test_preview_failure_does_not_hide_success_in_service(self):
        from kfps_ui.upscale_service import UpscaleService
        with tempfile.TemporaryDirectory() as tmp:
            paths = SimpleNamespace(app_root=ROOT, runtime_root=Path(tmp), ui_root=UI)
            log = SimpleNamespace(append=lambda *args, **kwargs: None)
            service = UpscaleService(paths, None, None, log)
            try:
                service._view.update(source="source.png", width=12, height=8)
                result = dict(state="complete", output="done.png", report="report.json",
                              settings=settings_for("anime", 2), output_size=[24, 16], elapsed_seconds=1)
                with patch("kfps_ui.upscale_service.execute_job", return_value=result), patch("kfps_ui.upscale_service.preview_file", side_effect=PermissionError("preview locked")), patch.object(service, "_submit", side_effect=lambda operation, work: service._apply(work())):
                    service.start()
                self.assertEqual("done.png", service.view["output"])
                self.assertEqual("", service.view["error"])
                self.assertIn("preview locked", service.view["status"])
            finally:
                service.close()


@unittest.skipUnless(os.name == "nt", "Windows native installation")
class EngineInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.members = {"engine.exe": b"fixture-not-executable", "models/model.bin": b"fixture-model"}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, data in self.members.items():
                bundle.writestr("release/" + name, data)
            bundle.writestr("unlisted-sample.png", b"not installed")
        self.archive = archive.getvalue()
        self.store = EngineStore(ROOT, self.root)
        self.store._catalog = {"fixture": dict(version="test", size=len(self.archive),
            sha256=hashlib.sha256(self.archive).hexdigest(), url="https://example.invalid/fixture.zip",
            prefix="release/", files={name: hashlib.sha256(data).hexdigest() for name, data in self.members.items()})}
        self.cancel = threading.Event()

    def install(self, data=None):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(self.archive if data is None else data)):
            return self.store.ensure("fixture", self.cancel, lambda *_: None)

    def test_install_reuse_missing_file_and_corruption_repair(self):
        directory = self.install()
        self.assertEqual(set(self.members), {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()})
        with patch("urllib.request.urlopen", side_effect=AssertionError("cache should not download")):
            self.assertEqual(directory, self.store.ensure("fixture", self.cancel, lambda *_: None))
        (directory / "models/model.bin").unlink()
        self.assertFalse(self.store.present("fixture"))
        self.install()
        (directory / "engine.exe").write_bytes(b"broken")
        self.assertFalse(self.store.verified("fixture", self.cancel))
        self.install()
        self.assertTrue(self.store.verified("fixture", self.cancel))

    def test_bad_downloads_never_install_and_retry_recovers(self):
        for data in (b"truncated", b"x" * len(self.archive), self.archive + b"extra"):
            with self.subTest(size=len(data)), self.assertRaises(RuntimeError):
                self.install(data)
            self.assertFalse(self.store.present("fixture"))
            self.assertFalse(list(self.store.root.glob("install-*")))
        self.install()
        self.assertTrue(self.store.verified("fixture", self.cancel))

    def test_missing_or_wrong_member_rejected_before_install(self):
        files = self.store.catalog["fixture"]["files"]
        for invalid in ({"absent.bin": "0" * 64}, {"engine.exe": "0" * 64}):
            self.store.catalog["fixture"]["files"] = invalid
            with self.assertRaises((KeyError, RuntimeError)):
                self.install()
            self.assertFalse(self.store.directory("fixture").exists())
        self.store.catalog["fixture"]["files"] = files
        self.install()

    def test_network_failure_is_retryable(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("network unavailable")), self.assertRaises(TimeoutError):
            self.store.ensure("fixture", self.cancel, lambda *_: None)
        self.assertFalse(self.store.present("fixture"))
        self.install()

    def test_download_cancel_is_retryable(self):
        cancel = self.cancel
        class CancellingStream(io.BytesIO):
            def read(self, *args):
                cancel.set()
                return super().read(*args)
        with patch("urllib.request.urlopen", return_value=CancellingStream(self.archive)), self.assertRaises(Cancelled):
            self.store.ensure("fixture", cancel, lambda *_: None)
        self.assertFalse(self.store.present("fixture"))
        self.assertFalse(list(self.store.root.glob("install-*")))
        cancel.clear()
        self.install()

    def test_interrupted_install_is_repaired_next_time(self):
        replace = os.replace
        count = 0
        def interrupted(source, target):
            nonlocal count
            count += 1
            if count == 2:
                raise PermissionError("fixture interruption")
            replace(source, target)
        with patch("kfps_ui.upscale_engine.os.replace", side_effect=interrupted), self.assertRaises(PermissionError):
            self.install()
        self.assertFalse(self.store.verified("fixture", self.cancel))
        self.install()
        self.assertTrue(self.store.verified("fixture", self.cancel))

    def test_second_instance_waits_instead_of_modifying_active_install(self):
        from kfps_ui.upscale_engine import engine_lock
        self.store.root.mkdir(parents=True)
        with engine_lock(self.store.root / "fixture.lock"), self.assertRaisesRegex(RuntimeError, "Another KFPS"):
            self.store.ensure("fixture", self.cancel, lambda *_: None)
        self.install()


if __name__ == "__main__":
    unittest.main()
