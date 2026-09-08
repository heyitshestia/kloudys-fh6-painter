from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import numpy as np
from PIL import Image

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
from kfps_ui.background_remove_engine import (
    BackgroundEngineStore, Cancelled, execute_job, fetch_verified, retry_file_operation, run_worker, settings_for, wheel_entries,
)
from kfps_ui.background_remove_processing import (alpha_from_prediction, background_color, color_result, compose_result,
                                                 model_input, quality_warning, refine_illustration, validate_result)
from kfps_ui.upscale_engine import atomic_json, read_image, sha256


def spec(data, name="test"):
    return dict(name=name, url="https://example.invalid/test", size=len(data), sha256=hashlib.sha256(data).hexdigest())


class ProcessingTests(unittest.TestCase):
    def test_conservative_defaults_and_validation(self):
        self.assertEqual("anime", settings_for()["mode"])
        self.assertFalse(settings_for()["cleanup"])
        self.assertFalse(settings_for()["refine"])
        for values in (dict(refine="false"), dict(cleanup=1), dict(threads=0), dict(threads=16), dict(threads=True),
                       dict(mode="unknown"), dict(color="red"), dict(color="#fff"), dict(tolerance=float("nan")),
                       dict(tolerance=True), dict(tolerance=101), dict(enclosed=1), dict(decontaminate="false")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                settings_for(**values)

    def test_normalization_matches_published_contract(self):
        tensor = model_input(Image.new("RGBA", (23, 19), (255, 128, 0, 255)))
        self.assertEqual((1, 3, 1024, 1024), tensor.shape)
        self.assertEqual(np.float32, tensor.dtype)
        np.testing.assert_allclose(tensor[0, :, 0, 0], [1-.485, 128/255-.456, -.406], rtol=1e-6)

    def test_black_input_is_finite(self):
        self.assertTrue(np.isfinite(model_input(Image.new("RGB", (8, 8)))).all())

    def test_invalid_predictions_fail_explicitly(self):
        for prediction in (np.zeros((1, 1, 1024, 1024)), np.ones((1, 1, 12, 12)), np.full((1, 1, 1024, 1024), np.nan)):
            with self.assertRaises(ValueError):
                alpha_from_prediction(prediction, (40, 60))

    def test_mask_is_resized_to_original(self):
        prediction = np.zeros((1, 1, 1024, 1024), np.float32)
        prediction[:, :, 200:800, 200:800] = 1
        mask = alpha_from_prediction(prediction, (40, 60))
        self.assertEqual((40, 60), mask.size)
        self.assertEqual((0, 255), mask.getextrema())

    def test_refinement_never_reveals_hidden_pixels_or_changes_rgb(self):
        image = Image.new("RGBA", (32, 32), (20, 40, 80, 80))
        image.putpixel((0, 0), (100, 80, 60, 0))
        result = compose_result(image, Image.new("L", image.size, 255))
        self.assertEqual(image.tobytes(), result.tobytes())

    def test_cleanup_opt_in_preserves_disconnected_small_details_by_default(self):
        image = Image.new("RGBA", (100, 100), "white")
        alpha = Image.new("L", image.size)
        alpha.paste(255, (20, 20, 80, 80))
        alpha.putpixel((2, 2), 255)
        self.assertEqual(255, compose_result(image, alpha).getpixel((2, 2))[3])
        self.assertEqual(0, compose_result(image, alpha, cleanup=True).getpixel((2, 2))[3])

    def test_all_empty_result_is_not_success(self):
        image = Image.new("RGBA", (5, 5), "white")
        with self.assertRaisesRegex(ValueError, "No foreground"):
            compose_result(image, Image.new("L", image.size))

    def test_flat_color_keeps_disconnected_details_and_enclosed_holes(self):
        image = Image.new("RGBA", (100,80), (220,0,0,255))
        image.paste("white", (10,10,40,60))
        image.paste((220,0,0,255), (20,20,30,30))
        image.paste("white", (80,50,83,53))
        self.assertEqual("#dc0000", background_color(image))
        result = color_result(image, "#dc0000")
        self.assertEqual(0, result.getpixel((25,25))[3])
        self.assertEqual(255, result.getpixel((81,51))[3])
        self.assertEqual(255, result.getpixel((15,30))[3])
        external = color_result(image, "#dc0000", enclosed=False)
        self.assertEqual(255, external.getpixel((25,25))[3])

    def test_flat_color_unmattes_red_edge_without_recoloring_interior(self):
        image = Image.new("RGBA", (40,40), (200,0,0,255))
        image.paste("white", (10,10,30,30))
        image.putpixel((9,20), (228,128,128,255))
        result = color_result(image, "#c80000")
        edge = result.getpixel((9,20))
        self.assertTrue(120 <= edge[3] <= 136, edge)
        self.assertTrue(min(edge[:3]) >= 250, edge)
        self.assertEqual((255,255,255,255), result.getpixel((20,20)))
        validate_result(image, result, color_edges=True)

    def test_color_result_preserves_original_transparency(self):
        image = Image.new("RGBA", (40,40), (200,0,0,0))
        image.paste((255,255,255,80), (10,10,30,30))
        result = color_result(image, "#c80000")
        self.assertLessEqual(np.asarray(result.getchannel("A")).max(), 80)

    def test_hidden_rgb_does_not_contaminate_visible_edges(self):
        results=[]
        for hidden in ((0,255,0,0),(0,0,255,0)):
            image=Image.new("RGBA",(40,40),hidden)
            image.paste("white",(10,10,30,30))
            image.putpixel((9,20),(228,128,128,255))
            results.append(np.asarray(color_result(image,"#c80000")))
        visible=results[0][:,:,3]>0
        self.assertTrue(np.array_equal(results[0][visible],results[1][visible]))

    def test_thin_lettering_has_its_own_edge_reference(self):
        image=Image.new("RGBA",(40,40),(200,0,0,255))
        image.paste((228,128,128,255),(19,10,22,30))
        image.paste("white",(20,10,21,30))
        result=color_result(image,"#c80000")
        self.assertEqual((255,255,255,255),result.getpixel((20,20)))
        edge=result.getpixel((19,20))
        self.assertTrue(min(edge[:3])>=250 and 120<=edge[3]<=136,edge)

    def test_near_empty_result_has_warning_but_legitimate_small_subject_survives(self):
        image = Image.new("RGBA", (100,100))
        image.putpixel((0,0), (255,255,255,180))
        self.assertIn("Almost no", quality_warning(image))
        image.paste("white", (20,20,30,30))
        self.assertEqual("", quality_warning(image))

    def test_refinement_is_subtractive_and_deterministic(self):
        image = Image.new("RGBA", (100,100), "white")
        image.paste("black", (20,20,80,80))
        alpha = Image.new("L", image.size)
        alpha.paste(255, (22,22,78,78))
        alpha.paste(128, (25,5,30,15))
        first = refine_illustration(image, alpha)
        self.assertTrue(np.all(np.asarray(first) <= np.asarray(alpha)))
        self.assertEqual(first.tobytes(), refine_illustration(image, alpha).tobytes())

    def test_cleanup_cannot_use_faint_bridge_to_keep_small_fragment(self):
        image = Image.new("RGBA", (100,100), "white")
        a = np.zeros((100,100), np.uint8)
        a[20:80,20:80] = 255
        a[2,2] = 255
        for i in range(3,21):
            a[i,i] = 1
        result = compose_result(image, Image.fromarray(a), cleanup=True)
        self.assertEqual(0, result.getpixel((2,2))[3])
        self.assertEqual(255, result.getpixel((50,50))[3])

    def test_color_changes_and_alpha_resurrection_rejected(self):
        image = Image.new("RGBA", (5, 5), (20, 40, 80, 100))
        for color in ((21, 40, 80, 100), (20, 40, 80, 101)):
            with self.assertRaises(ValueError):
                validate_result(image, Image.new("RGBA", image.size, color))


class InstallationTests(unittest.TestCase):
    def test_transient_file_lock_retries_but_permanent_lock_stops(self):
        operation = Mock(side_effect=[PermissionError("busy"), PermissionError("busy"), "done"])
        with patch("kfps_ui.background_remove_engine.time.sleep"):
            self.assertEqual("done", retry_file_operation(operation))
            blocked = Mock(side_effect=PermissionError("locked"))
            with self.assertRaises(PermissionError):
                retry_file_operation(blocked)
        self.assertEqual(8, blocked.call_count)

    def test_catalog_pins_every_download(self):
        store = BackgroundEngineStore(ROOT / "runtime", ROOT / "tools/background_remover/engine.json")
        for item in [store.catalog["model"], *store.catalog["wheels"]]:
            self.assertEqual(64, len(item["sha256"]))
            self.assertGreater(item["size"], 0)
            self.assertTrue(item["url"].startswith(("https://github.com/", "https://files.pythonhosted.org/")))
            self.assertNotIn("latest", item["url"])

    def test_verified_download_and_offline_reuse(self):
        data = b"verified engine"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "asset"
            with patch("urllib.request.urlopen", return_value=io.BytesIO(data)):
                fetch_verified(spec(data), target, threading.Event(), lambda *_: None)
            with patch("urllib.request.urlopen", side_effect=AssertionError("must stay offline")):
                fetch_verified(spec(data), target, threading.Event(), lambda *_: None)
            self.assertEqual(data, target.read_bytes())

    def test_bad_download_does_not_replace_prior_asset(self):
        for data in (b"wrong", b"truncated", b"good" * 100):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "asset"
                target.write_bytes(b"prior")
                with patch("urllib.request.urlopen", return_value=io.BytesIO(data)), self.assertRaises(RuntimeError):
                    fetch_verified(spec(b"good data"), target, threading.Event(), lambda *_: None)
                self.assertEqual(b"prior", target.read_bytes())
                self.assertEqual(["asset"], [p.name for p in Path(tmp).iterdir()])

    def test_cancel_download_cleans_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            cancel = threading.Event()
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"abc")), self.assertRaises(Cancelled):
                fetch_verified(spec(b"abc"), Path(tmp) / "asset", cancel, lambda *_: cancel.set())
            self.assertEqual([], list(Path(tmp).iterdir()))

    def test_archive_rejects_escape_duplicate_and_links(self):
        for names in (("../escape",), ("/escape",), ("C:/escape",), ("A", "a")):
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                for name in names:
                    archive.writestr(name, b"test")
            with zipfile.ZipFile(data) as archive, self.assertRaises(RuntimeError):
                list(wheel_entries(archive))
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            entry = zipfile.ZipInfo("link")
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, b"target")
        with zipfile.ZipFile(data) as archive, self.assertRaises(RuntimeError):
            list(wheel_entries(archive))

    @unittest.skipUnless(os.name == "nt", "Windows installer lock")
    def test_runtime_repair_uses_verified_archives_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                archive.writestr("package/__init__.py", b"VALUE = 1\n")
                archive.writestr("package-1.dist-info/LICENSE", b"test license")
            wheel = data.getvalue()
            catalog = dict(schema="kfps.background-engine.v1", id="test", model=spec(b"model"), wheels=[spec(wheel)])
            atomic_json(root / "catalog.json", catalog)
            store = BackgroundEngineStore(root, root / "catalog.json")
            store.root.mkdir(parents=True)
            store._archive(catalog["wheels"][0]).write_bytes(wheel)
            store.model.write_bytes(b"model")
            with patch("urllib.request.urlopen", side_effect=AssertionError("must not download")):
                directory, _ = store.ensure(threading.Event(), lambda *_: None)
                target = directory / "package/__init__.py"
                target.write_bytes(b"bad")
                (directory / "unexpected.py").write_bytes(b"obsolete")
                store.ensure(threading.Event(), lambda *_: None)
                self.assertEqual(b"VALUE = 1\n", target.read_bytes())
                self.assertFalse((directory / "unexpected.py").exists())
                target.unlink()
                store.ensure(threading.Event(), lambda *_: None)
                self.assertTrue(target.is_file())
                self.assertTrue((directory / "package-1.dist-info/LICENSE").is_file())
                self.assertFalse(list(store.root.glob("install-*")))
                # Cancellation after retiring the old cache must restore it, even
                # though the caller's cancellation flag is already set.
                target.write_bytes(b"previous state")
                cancel = threading.Event()
                replace = os.replace
                def interrupt(source, destination):
                    replace(source, destination)
                    if Path(destination).name.startswith("replaced-"):
                        cancel.set()
                with patch("kfps_ui.background_remove_engine.os.replace", side_effect=interrupt), self.assertRaises(Cancelled):
                    store.ensure(cancel, lambda *_: None)
                self.assertEqual(b"previous state", target.read_bytes())
                store.ensure(threading.Event(), lambda *_: None)
                self.assertEqual(b"VALUE = 1\n", target.read_bytes())


class JobTests(unittest.TestCase):
    def job(self, root, image, options=None, native=None, cancel=None):
        source = root / "original.png"
        image.save(source)
        before = source.read_bytes()
        store = BackgroundEngineStore(root, ROOT / "tools/background_remover/engine.json")
        def produce(command, run, *_):
            result = read_image(run / "input.png")
            result.putalpha(Image.new("L", result.size, 100))
            result.save(run / "processed.png")
            atomic_json(run / "worker-result.json", {"provider": "CPUExecutionProvider"})
        with patch.object(store, "ensure", return_value=(root, root / "model")) as install, patch("kfps_ui.background_remove_engine.run_worker", side_effect=native or produce):
            result = execute_job(store, sys.executable, source, options or settings_for(), root / "run", root / "output",
                                 cancel or threading.Event(), lambda *_: None)
        self.assertEqual(before, source.read_bytes())
        self.assertEqual(result["state"], json.loads((root / "run/report.json").read_text())["state"])
        self.assertFalse(any((root / "run" / name).exists() for name in ("input.png", "processed.png", "complete.png", "settings.json")))
        return result, install

    def test_opaque_real_transaction_output_reopens(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, install = self.job(Path(tmp), Image.new("RGB", (27, 16), "pink"))
            self.assertEqual("complete", result["state"])
            install.assert_called_once()
            with Image.open(result["output"]) as output:
                self.assertEqual((27, 16), output.size)
                self.assertEqual((100, 100), output.getchannel("A").getextrema())

    def test_transparent_default_does_not_download_or_run_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Image.new("RGBA", (27, 16), (50, 60, 70, 123))
            result, install = self.job(Path(tmp), image, native=lambda *_: self.fail("must not run"))
            self.assertEqual("existing-transparency-preserved", result["mode"])
            install.assert_not_called()
            with Image.open(result["output"]) as output:
                self.assertEqual(image.tobytes(), output.tobytes())

    def test_refine_runs_model_for_transparent_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, install = self.job(Path(tmp), Image.new("RGBA", (27, 16), (50, 60, 70, 123)), settings_for(refine=True))
            self.assertEqual("complete", result["state"])
            install.assert_called_once()

    def test_invalid_worker_output_is_rejected(self):
        for mode, size in (("RGB", (27, 16)), ("RGBA", (2, 2))):
            def bad(command, run, *_):
                Image.new(mode, size, "white").save(run / "processed.png")
            with tempfile.TemporaryDirectory() as tmp:
                result, _ = self.job(Path(tmp), Image.new("RGB", (27, 16)), native=bad)
                self.assertEqual("failed", result["state"])
                self.assertNotIn("output", result)

    def test_worker_failure_is_reported_not_silently_successful(self):
        def fail(*_):
            raise RuntimeError("inference failed")
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = self.job(Path(tmp), Image.new("RGB", (27, 16)), native=fail)
            self.assertEqual("failed", result["state"])
            self.assertEqual("inference", result["phase"])
            self.assertIn("inference failed", result["error"])

    def test_cancel_prevents_output(self):
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = self.job(Path(tmp), Image.new("RGB", (27, 16)), cancel=cancel)
            self.assertEqual("cancelled", result["state"])
            self.assertNotIn("output", result)

    def test_empty_source_rejected_without_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, install = self.job(Path(tmp), Image.new("RGBA", (10, 10)))
            self.assertEqual("failed", result["state"])
            install.assert_not_called()

    def test_final_report_failure_preserves_success_and_warns(self):
        def write(path, value):
            if value.get("state") == "complete":
                raise PermissionError("locked")
            atomic_json(path, value)
        with tempfile.TemporaryDirectory() as tmp, patch("kfps_ui.background_remove_engine.atomic_json", side_effect=write):
            root = Path(tmp)
            Image.new("RGBA", (5, 5), (20, 30, 40, 50)).save(root / "source.png")
            store = BackgroundEngineStore(root, ROOT / "tools/background_remover/engine.json")
            result = execute_job(store, sys.executable, root / "source.png", settings_for(), root / "run", root / "out", threading.Event(), lambda *_: None)
            self.assertEqual("complete", result["state"])
            self.assertTrue(Path(result["output"]).is_file())
            self.assertIn("diagnostic_error", result)

    def test_existing_run_is_never_overwritten_or_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            (run / "input.png").write_bytes(b"old input")
            (run / "report.json").write_bytes(b"old report")
            store = BackgroundEngineStore(root, ROOT / "tools/background_remover/engine.json")
            result = execute_job(store, sys.executable, root / "missing.png", settings_for(), run, root / "out", threading.Event(), lambda *_: None)
            self.assertEqual("failed", result["state"])
            self.assertEqual("", result["report"])
            self.assertEqual(b"old input", (run / "input.png").read_bytes())
            self.assertEqual(b"old report", (run / "report.json").read_bytes())

    def test_missing_python_cannot_launch_kfps_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (8, 8), "white").save(root / "source.png")
            store = BackgroundEngineStore(root, ROOT / "tools/background_remover/engine.json")
            with patch.object(store, "ensure") as install:
                result = execute_job(store, root / "KFPS.exe", root / "source.png", settings_for(), root / "run", root / "out", threading.Event(), lambda *_: None)
            self.assertEqual("failed", result["state"])
            self.assertIn("Python runtime is missing", result["error"])
            install.assert_not_called()

    def test_native_cancellation_and_timeout_reap_process(self):
        for timeout, do_cancel in ((5, True), (0.2, False)):
            with tempfile.TemporaryDirectory() as tmp:
                cancel, processes = threading.Event(), []
                original = subprocess.Popen
                def spawn(*args, **kwargs):
                    child = original(*args, **kwargs)
                    processes.append(child)
                    return child
                timer = threading.Timer(0.3, cancel.set) if do_cancel else None
                if timer:
                    timer.start()
                try:
                    with patch("kfps_ui.background_remove_engine.subprocess.Popen", side_effect=spawn), self.assertRaises((Cancelled, RuntimeError)):
                        run_worker([sys.executable, "-c", "import time; time.sleep(60)"], Path(tmp), cancel, lambda *_: None, timeout=timeout)
                    self.assertIsNotNone(processes[0].poll())
                finally:
                    if timer:
                        timer.join()

    def test_worker_failure_message_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(RuntimeError, "test readable reason"):
            run_worker([sys.executable, "-c", "print('ERROR test readable reason'); raise SystemExit(2)"],
                       Path(tmp), threading.Event(), lambda *_: None)

    def test_memory_limit_reaps_only_its_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            processes=[]
            original=subprocess.Popen
            def spawn(*args, **kwargs):
                child=original(*args, **kwargs)
                processes.append(child)
                return child
            with patch("kfps_ui.background_remove_engine.subprocess.Popen", side_effect=spawn):
                with self.assertRaisesRegex(RuntimeError, "memory safety limit"):
                    run_worker([sys.executable,"-c","import time; data=bytearray(64*1024**2); time.sleep(30)"],
                               Path(tmp),threading.Event(),lambda *_:None,timeout=10,memory_limit=32*1024**2)
            self.assertEqual(1,len(processes))
            self.assertIsNotNone(processes[0].poll())


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def wait_service(self, service):
        deadline=time.monotonic()+10
        while service.running and time.monotonic()<deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertFalse(service.running)

    def test_correction_save_failure_reports_and_preserves_previous_result(self):
        from kfps_ui.background_remove_service import BackgroundRemoveService
        from kfps_ui.background_remove_document import MaskDocument
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            run=root/"background-remover/runs/test"
            run.mkdir(parents=True)
            original=run/"source.png"
            output=root/"output.png"
            Image.new("RGBA",(30,30),"white").save(original)
            shutil.copyfile(original,output)
            document=MaskDocument.create(run,output,root/"original.png")
            paths=SimpleNamespace(app_root=root,runtime_root=root,ui_root=UI,python_executable=sys.executable)
            service=BackgroundRemoveService(paths,Mock(),Mock(),Mock())
            service._document=document
            service._view.update(output=str(output),editable=True)
            previous=sha256(document.current_path)
            try:
                with patch("kfps_ui.background_remove_document.atomic_json",side_effect=PermissionError("locked session")):
                    service.correct("erase",[[.5,.5]],10,20)
                    self.wait_service(service)
                self.assertIn("locked session",service.lastError)
                self.assertEqual(previous,sha256(document.current_path))
                self.assertEqual(str(output),service.view["output"])
                report=json.loads(Path(service.view["report"]).read_text())
                self.assertEqual("edit",report["operation"])
                self.assertNotIn("source.png",json.dumps(report))
                service.correct("erase",[[.5,.5]],10,20)
                self.wait_service(service)
                self.assertFalse(service.lastError)
                self.assertTrue(service.view["canUndo"])
            finally:
                service.close()

    def test_invalid_resume_preserves_current_view_and_reports(self):
        from kfps_ui.background_remove_service import BackgroundRemoveService
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=SimpleNamespace(app_root=root,runtime_root=root,ui_root=UI,python_executable=sys.executable)
            service=BackgroundRemoveService(paths,Mock(),Mock(),Mock())
            service._view.update(output="existing.png")
            service._last_session.parent.mkdir(parents=True)
            service._last_session.write_text('{"schema":"kfps.background-resume.v1","run":"../../../elsewhere"}')
            try:
                service.resume()
                self.wait_service(service)
                self.assertIn("location is invalid",service.lastError)
                self.assertEqual("existing.png",service.view["output"])
                self.assertTrue(Path(service.view["report"]).is_file())
            finally:
                service.close()

    def test_service_guards_double_submit_and_closes_source_preview(self):
        from kfps_ui.background_remove_service import BackgroundRemoveService
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "source.png"
            Image.new("RGBA", (10, 10), "white").save(path)
            paths = SimpleNamespace(app_root=ROOT, runtime_root=root, ui_root=UI, python_executable=sys.executable)
            service = BackgroundRemoveService(paths, Mock(), Mock(path=""), Mock())
            service.setSource(str(path))
            first = service._future
            service.setSource(str(path))
            service.start()
            service.configure("refine", True)
            self.assertIs(first, service._future)
            self.assertFalse(service._options["refine"])
            service.close()
            service.close()
            self.assertFalse(list((root / "background-remover/previews").glob("*.png")))

    def test_missing_catalog_disables_start_without_crashing_service(self):
        from kfps_ui.background_remove_service import BackgroundRemoveService
        with tempfile.TemporaryDirectory() as tmp:
            paths = SimpleNamespace(app_root=Path(tmp), runtime_root=Path(tmp), ui_root=Path(tmp)/"UI")
            service = BackgroundRemoveService(paths, Mock(), Mock(), Mock())
            try:
                self.assertFalse(service.view["available"])
            finally:
                service.close()

    def test_ui_and_shutdown_wired_without_external_link(self):
        tools = (UI / "qml/pages/ToolsPage.qml").read_text(encoding="utf-8")
        self.assertNotIn("photoroom", tools.lower())
        self.assertIn('appController.navigate("background-remover")', tools)
        self.assertIn("background_remover,", (UI / "app.py").read_text(encoding="utf-8"))
        page = (UI / "qml/pages/BackgroundRemoverPage.qml").read_text(encoding="utf-8")
        self.assertIn("property bool advancedOpen: false", page)
        self.assertIn("backgroundRemoveService.cancel()", page)

    def test_support_report_prefills_current_error_without_artwork(self):
        from kfps_ui.support_report import build_support_report
        with tempfile.TemporaryDirectory() as tmp:
            context = dict(page="background-remover", version="test", log="", services={
                "background_remover": dict(status="Background removal failed", running=False,
                                           lastError="CPU engine failed verification", source="private-art.png")})
            report = build_support_report(Path(tmp), context, since=time.time(), collect=lambda: {})
            self.assertEqual("CPU engine failed verification", report["description"])
            self.assertNotIn("private-art", json.dumps(report))
            self.assertEqual("Other", report["feature"])


if __name__ == "__main__":
    unittest.main()
