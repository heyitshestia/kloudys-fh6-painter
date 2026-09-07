"""Opt-in real native upscales and offscreen interaction with the actual KFPS shell."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
from unittest.mock import patch
import urllib.request

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
from kfps_ui.startup_splash import StartupSplash
from kfps_ui.upscale_engine import sha256
import app as application

OUT = ROOT / "runtime/upscaler-testing" / datetime.now().strftime("workflow-%Y%m%d-%H%M%S")
OUT.mkdir(parents=True)
results = {"cases": [], "native": [], "errors": [], "qml_errors": []}


def messages(kind, context, message):
    if any(word in message for word in ("Error:", "is not defined", "Cannot assign", "failed to load", "Binding loop", "No such file")):
        results["qml_errors"].append(message)


def fixtures():
    images = OUT / "inputs"
    images.mkdir()
    with Image.open(UI / "assets/mini-kloudy.png") as image:
        image.thumbnail((256, 256))
        image.save(images / "anime.png")
    text = Image.new("RGBA", (320, 180), (255, 255, 255, 0))
    draw = ImageDraw.Draw(text)
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 36)
    draw.text((15, 18), "KFPS 2x / 4x", font=font, fill=(245, 30, 110, 255))
    draw.text((15, 80), "TEXT & LOGO", font=font, fill=(20, 25, 30, 255))
    text.save(images / "text.png")
    # Public OpenCV sample, downloaded only for this opt-in test; never shipped.
    photo = ROOT / "runtime/upscaler-testing/downloads/opencv-fruits.jpg"
    expected = "9c031d80a1c52da5eca790db896baffec6a7e52bf786cdb7bbfca5c7f880e6a1"
    if not photo.exists() or sha256(photo) != expected:
        photo.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen("https://raw.githubusercontent.com/opencv/opencv/4.10.0/samples/data/fruits.jpg", timeout=15) as response:
            data = response.read(1_000_000)
        photo.write_bytes(data)
    assert sha256(photo) == expected, "Photo fixture checksum mismatch"
    with Image.open(photo) as image:
        image.save(images / "photo.png")
    return images


def install(app, window, controller, community, settings, jsons, args):
    def click(item):
        assert item and item.isEnabled(), "Missing or disabled control"
        position = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(position.x()), round(position.y())))

    def steps():
        try:
            images = fixtures()
            context = QQmlEngine.contextForObject(window)
            service = context.contextProperty("upscaleService")
            desktop = context.contextProperty("desktop")
            source = context.contextProperty("sourceService")
            service.store.root = ROOT / "runtime/upscaler/engines"
            controller.navigate("tools")
            yield 700
            open_button = window.findChild(QObject, "GhostButton:Open Upscaler")
            click(open_button)
            yield 700
            assert controller.currentPage == "upscaler", "Tools did not route to native upscaler"
            page = window.findChild(QObject, "UpscalerPage")
            assert page and not page.property("advancedOpen"), "Advanced must start collapsed"
            window.resize(1600, 1100)
            yield 200
            for preset in ("photo", "anime", "text"):
                with patch.object(desktop, "chooseImage", return_value=str(images / (preset + ".png"))):
                    click(window.findChild(QObject, "UpscalerChoose"))
                deadline = time.monotonic() + 30
                while service.running and time.monotonic() < deadline:
                    yield 25
                assert service.view["source"].endswith(preset + ".png"), service.lastError
                service.configure("preset", preset)
                for scale in (2, 4):
                    click(window.findChild(QObject, "UpscalerScale" + str(scale)))
                    yield 100
                    assert service.view["scale"] == scale, "Scale button did not change the setting"
                    click(window.findChild(QObject, "UpscalerStart"))
                    assert service.running, service.lastError
                    # Double-click cannot enqueue a second run or alter its settings.
                    service.start(); service.configure("scale", 2 if scale == 4 else 4)
                    assert service.view["scale"] == scale
                    deadline = time.monotonic() + 180
                    while service.running and time.monotonic() < deadline:
                        yield 50
                    assert not service.running and not service.lastError, service.view
                    output = Path(service.view["output"])
                    report = json.loads(Path(service.view["report"]).read_text())
                    assert report["state"] == "complete" and output.exists()
                    with Image.open(output) as result, Image.open(images / (preset + ".png")) as original:
                        result.load()
                        assert result.size == (original.width * scale, original.height * scale)
                        if preset != "photo":
                            assert result.getchannel("A").getpixel((0, 0)) == 0
                    results["native"].append({"preset": preset, "scale": scale, "seconds": report["elapsed_seconds"], "output": str(output), "report": str(service.view["report"])})
                    yield 250
                    QTest.mouseMove(window, QPoint(10, 10))
                    yield 100
                    assert window.grabWindow().save(str(OUT / f"{preset}-{scale}x-preview.png"))
            yield 100
            assert window.grabWindow().save(str(OUT / "upscaler-result.png"))
            saved = OUT / "saved-copy.png"
            with patch("kfps_ui.upscale_service.QFileDialog.getSaveFileName", return_value=(str(saved), "PNG")):
                service.saveAs()
                deadline = time.monotonic() + 15
                while service.running and time.monotonic() < deadline:
                    yield 25
            assert saved.read_bytes() == Path(service.view["output"]).read_bytes(), service.lastError
            service.useResult()
            assert source.path == service.view["output"]
            # Switch away and back: settings/result persist, native models do not remain resident.
            controller.navigate("create"); yield 200
            controller.navigate("upscaler"); yield 200
            assert service.view["output"] and not service.running
            click(window.findChild(QObject, "UpscalerAdvanced")); yield 150
            assert page.property("advancedOpen")
            service.configure("noise", 3); service.configure("tile", 32); service.configure("tta", True)
            service.configure("reset", True)
            assert service.view["noise"] == -1 and service.view["tile"] == 128 and not service.view["tta"]
            for theme in sorted(KNOWN_THEME_NAMES):
                settings.theme = theme
                for width, height in ((960, 600), (1600, 1100)):
                    window.resize(width, height); yield 400
                    preview = window.findChild(QObject, "UpscalerPreview")
                    assert preview and preview.width() > 200
                    start = window.findChild(QObject, "UpscalerStart")
                    assert start.isEnabled()
                    position = start.mapToScene(QPointF(start.width() / 2, start.height() / 2))
                    assert 0 < position.x() < window.width() and 0 < position.y() < window.height(), "Start button outside the window"
                    slug = "".join(c if c.isalnum() else "-" for c in theme)
                    assert window.grabWindow().save(str(OUT / f"{slug}-{width}x{height}.png"))
                    results["cases"].append({"theme": theme, "size": [width, height]})
            # Cancellation while the real GPU engine is active, then successful recovery.
            service.setSource(str(UI / "assets/mini-kloudy.png"))
            while service.running: yield 25
            service.configure("preset", "anime"); service.configure("scale", 4); service.configure("tta", True)
            service.start()
            deadline = time.monotonic() + 20
            while "Upscaling locally" not in service.status and service.running and time.monotonic() < deadline:
                yield 50
            service.cancel()
            while service.running: yield 25
            assert service.status == "Cancelled", service.view
            cancelled = json.loads(Path(service.view["report"]).read_text())
            assert cancelled["state"] == "cancelled"
            results["cancelled"] = service.view["report"]
            service.setSource(str(images / "text.png"))
            while service.running: yield 25
            service.configure("preset", "text"); service.configure("scale", 2)
            service.start()
            while service.running: yield 25
            assert not service.lastError and service.view["output"]
            splash = StartupSplash(UI / "assets")
            splash.set_status("Preparing local image tools...", "Mini Kloudy has the clipboard.")
            assert splash.art.pixmap().height() <= splash.art.height()
            assert splash.grab().save(str(OUT / "splash.png"))
            splash.close()
        except Exception:
            results["errors"].append(traceback.format_exc())
        finally:
            (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            app.exit(1 if results["errors"] or results["qml_errors"] else 0)
    iterator = steps()
    def advance():
        try:
            delay = next(iterator)
        except StopIteration:
            return
        QTimer.singleShot(delay, advance)
    QTimer.singleShot(900, advance)


def main():
    app_root = OUT / "isolated-app"
    app_root.mkdir()
    shutil.copy2(ROOT / "VERSION", app_root / "VERSION")
    paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", app_root / "runtime", Path(sys.executable))
    sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", "Night Blossom", "--screenshot", str(OUT / "capture-mode.png"),
                "--skip-startup-index", "--skip-startup-thumbnails", "--allow-source-download", "--width", "1600", "--height", "1100"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), patch.object(application, "install_development_harness", side_effect=install):
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    print(json.dumps(dict(cases=len(results["cases"]), native=results["native"], errors=results["errors"], qml_errors=results["qml_errors"], result=str(OUT / "results.json")), indent=2))
    return code or int(bool(results["errors"] or results["qml_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
