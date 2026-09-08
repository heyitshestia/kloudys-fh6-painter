"""Opt-in real CPU jobs through the actual KFPS shell, without taking desktop focus."""
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

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
import numpy as np
import psutil
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
from kfps_ui.upscale_engine import sha256
import app as application

OUT = ROOT / "runtime/background-remover/validation" / datetime.now().strftime("workflow-%Y%m%d-%H%M%S")
OUT.mkdir(parents=True)
results = dict(cases=[], jobs=[], errors=[], qml_errors=[])


def messages(kind, context, message):
    if any(word in message for word in ("Error:", "is not defined", "Cannot assign", "failed to load", "Binding loop", "No such file")):
        results["qml_errors"].append(message)


def fixtures():
    inputs = OUT / "inputs"
    inputs.mkdir()
    with Image.open(UI / "assets/mini-kloudy.png") as source:
        image = source.convert("RGBA")
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    image.save(inputs / "transparent.png")
    for name, color in (("white", (255, 255, 255)), ("bluegrey", (70, 100, 130))):
        composite = Image.new("RGBA", image.size, (*color, 255))
        composite.alpha_composite(image)
        composite.convert("RGB").save(inputs / (name + ".png"))
    text = Image.new("RGBA", (480, 200))
    draw = ImageDraw.Draw(text)
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 50)
    draw.text((16, 12), "KFPS & i.j!", font=font, fill=(240, 50, 140, 255))
    draw.text((16, 90), "Small details", font=font, fill=(30, 40, 50, 255))
    text.save(inputs / "text.png")
    logo = Image.new("RGBA", (768,591), (220,0,0,255))
    painter = ImageDraw.Draw(logo)
    painter.rectangle((140,220,480,320), fill="white")
    painter.rectangle((190,250,230,280), fill=(220,0,0,255))
    painter.ellipse((540,290,564,314), outline="white", width=3)
    painter.text((548,293), "R", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",12), fill="white")
    logo.save(inputs / "logo.png")
    return inputs, np.asarray(image.getchannel("A"))


def worker_children():
    found = []
    for child in psutil.Process().children(recursive=True):
        try:
            if any("background_remove_worker.py" in arg for arg in child.cmdline()):
                found.append(child)
        except psutil.Error:
            pass
    return found


def install(app, window, controller, community, settings, jsons, args):
    def click(name):
        item = window.findChild(QObject, name)
        assert item and item.isEnabled(), "Missing or disabled: " + name
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
        ancestor = item.parentItem()
        while ancestor:
            if ancestor.property("contentY") is not None:
                origin = ancestor.mapToScene(QPointF(0,0))
                if point.y() < origin.y()+10 or point.y() > origin.y()+ancestor.height()-10:
                    target = float(ancestor.property("contentY")) + point.y()-origin.y()-ancestor.height()/2
                    ancestor.setProperty("contentY", max(0, min(target,float(ancestor.property("contentHeight"))-ancestor.height())))
                    app.processEvents()
                    point = item.mapToScene(QPointF(item.width()/2,item.height()/2))
                break
            ancestor = ancestor.parentItem()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))

    def wait(service, timeout=210):
        deadline = time.monotonic() + timeout
        while service.running and time.monotonic() < deadline:
            yield 25
        assert not service.running, "Service did not finish within deadline"
        yield 50  # Let queued QML bindings/layout observe the completed service state.

    def steps():
        try:
            inputs, truth = fixtures()
            context = QQmlEngine.contextForObject(window)
            service = context.contextProperty("backgroundRemoveService")
            desktop = context.contextProperty("desktop")
            source = context.contextProperty("sourceService")
            service.store.root = Path(os.environ.get(
                "KFPS_BG_TEST_ENGINE_ROOT", str(ROOT / "runtime/background-remover/engines")
            )).resolve()
            controller.navigate("tools")
            yield 700
            assert window.grabWindow().save(str(OUT / "tools.png"))
            click("GhostButton:Open Background Remover")
            yield 700
            assert controller.currentPage == "background-remover"
            page = window.findChild(QObject, "BackgroundRemoverPage")
            assert page and not page.property("advancedOpen")
            results["cases"].append("Tools opens native background remover; advanced collapsed")
            for name in ("white", "bluegrey", "transparent", "text"):
                original = inputs / (name + ".png")
                before = sha256(original)
                with patch.object(desktop, "chooseImage", return_value=str(original)):
                    click("BackgroundRemoverChoose")
                yield from wait(service, 20)
                assert not service.lastError, service.view
                click("BackgroundRemoverStart")
                future = service._future
                service.start()
                service.configure("refine", True)
                assert future is service._future and not service.view["refine"]
                yield from wait(service)
                assert not service.lastError and service.view["output"], service.view
                report = json.loads(Path(service.view["report"]).read_text())
                with Image.open(service.view["output"]) as produced, Image.open(original) as opened:
                    result = np.asarray(produced)
                    assert produced.mode == "RGBA" and produced.size == opened.size
                    if name in ("transparent", "text"):
                        assert produced.tobytes() == opened.convert("RGBA").tobytes()
                        assert report["mode"] == "existing-transparency-preserved"
                    else:
                        predicted, expected = result[:, :, 3] >= 128, truth >= 128
                        iou = float((predicted & expected).sum() / (predicted | expected).sum())
                        alpha_error = float(np.abs(result[:, :, 3].astype(float) - truth.astype(float)).mean())
                        assert iou > 0.96, f"Mascot regression: {iou}"
                        report["test_iou"] = iou
                        report["test_alpha_mae"] = alpha_error
                assert sha256(original) == before
                assert not worker_children(), "CPU worker remained after completion"
                results["jobs"].append(dict(input=name, report=service.view["report"], elapsed=report["elapsed_seconds"],
                                            inference=report.get("worker", {}).get("inference_seconds"),
                                            iou=report.get("test_iou"), alpha_mae=report.get("test_alpha_mae")))
                yield 300
                QTest.mouseMove(window, QPoint(10, 10))
                yield 100
                assert window.grabWindow().save(str(OUT / (name + "-preview.png")))
            logo = Path(os.environ.get("KFPS_BG_TEST_LOGO", str(inputs / "logo.png")))
            service.setSource(str(logo))
            yield from wait(service,20)
            if os.environ.get("KFPS_BG_TEST_LOGO"):
                service.start()
                yield from wait(service,40)
                warning=window.findChild(QObject,"BackgroundRemoverWarning")
                assert not service.lastError and service.view["warning"] and warning.isVisible(), service.view
                results["cases"].append("Almost-empty anime-model logo output has a visible review warning")
            modes = window.findChild(QObject, "BackgroundRemoverMode")
            modes.forceActiveFocus()
            QTest.keyClick(window,Qt.Key_End)
            yield 150
            assert service.view["mode"] == "color", service.view
            with patch.object(service.store, "ensure", side_effect=AssertionError("Logo mode must not prepare AI runtime")):
                click("BackgroundRemoverStart")
                yield from wait(service,40)
            assert not service.lastError, service.view
            with Image.open(logo) as original, Image.open(service.view["output"]) as opened:
                pixels=np.asarray(original.convert("RGBA"))
                cutout=np.asarray(opened)
                white=pixels[:,:,:3].min(axis=2)>=250
                assert (cutout[:,:,3][white]>=128).mean()>.999, "White logo details lost"
                background=(pixels[:,:,0]>180)&(pixels[:,:,1]<10)&(pixels[:,:,2]<10)
                assert (cutout[:,:,3][background]>=128).mean()<.0001, "Flat background retained"
                import cv2
                distance=cv2.distanceTransform(white.astype(np.uint8),cv2.DIST_L2,5)
                cy,cx=np.unravel_index(distance.argmax(),distance.shape)
            original_hash=sha256(logo)
            base_pixels=cutout.copy()
            results["cases"].append("Native logo mode preserves disconnected white details and removes flat background without AI/runtime download")
            preview=window.findChild(QObject,"BackgroundRemoverPreview")
            click("BackgroundRemoverErase")
            preview.setProperty("brushSize",12)
            yield 150
            def canvas_point(x,y):
                p=preview.mapToScene(QPointF(float(preview.property("imageX"))+x/preview.property("imageWidth")*preview.property("imageW"),
                                            float(preview.property("imageY"))+y/preview.property("imageHeight")*preview.property("imageH")))
                return QPoint(round(p.x()),round(p.y()))
            point=canvas_point(cx,cy)
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point)
            yield from wait(service,30)
            assert not service.lastError and service.view["canUndo"], service.view
            with Image.open(service.view["output"]) as opened:
                assert opened.getpixel((int(cx),int(cy)))[3] == 0, "Brush coordinates missed the selected pixel"
            click("BackgroundRemoverUndo")
            yield from wait(service,30)
            with Image.open(service.view["output"]) as opened:
                assert np.array_equal(np.asarray(opened),base_pixels)
            click("BackgroundRemoverRedo")
            yield from wait(service,30)
            click("BackgroundRemoverRestore")
            yield 100
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,canvas_point(cx,cy))
            yield from wait(service,30)
            with Image.open(service.view["output"]) as opened:
                assert opened.getpixel((int(cx),int(cy)))[3] == 255
            assert sha256(logo)==original_hash
            results["cases"].append("Actual canvas erase/undo/redo/restore hits original-resolution pixels; original unchanged")
            # Recreate the service/context as at startup, then resume through its UI button.
            expected=Image.open(service.view["output"]).tobytes()
            old_service=service
            service=type(service)(old_service.paths,desktop,source,old_service.log,parent=app)
            app._background_validation_service = service
            service.store=old_service.store
            old_service.close()
            context.engine().rootContext().setContextProperty("backgroundRemoveService",service)
            app.aboutToQuit.connect(service.close)
            yield 200
            click("BackgroundRemoverResume")
            yield from wait(service,30)
            assert not service.lastError and service.view["mode"]=="color", service.view
            with Image.open(service.view["output"]) as opened:
                assert opened.tobytes()==expected
            assert service.view["canUndo"]
            yield 200
            assert window.grabWindow().save(str(OUT/"logo-corrected-resumed.png"))
            results["cases"].append("Fresh service reloads persisted pixels, undo history and mode through Resume last")
            for env, mode in (("KFPS_BG_TEST_CHARACTER","illustration"),):
                if os.environ.get(env):
                    original=Path(os.environ[env])
                    before=sha256(original)
                    service.setSource(str(original))
                    yield from wait(service,30)
                    service.configure("mode",mode)
                    service.start()
                    yield from wait(service,90)
                    assert service.view["output"] and not service.lastError, service.view
                    assert sha256(original)==before
                    results["jobs"].append(dict(input=env, mode=mode, report=service.view["report"], output=service.view["output"]))
                    yield 200
                    assert window.grabWindow().save(str(OUT/"character-refined.png"))
                    with Image.open(service.view["output"]) as opened, Image.open(original) as source_image:
                        before_cutout=np.array(opened)
                        rgb=np.array(source_image.convert("RGB"))
                    count,labels,stats,_=cv2.connectedComponentsWithStats((before_cutout[:,:,3]>=128).astype(np.uint8),8)
                    main=1+int(stats[1:,cv2.CC_STAT_AREA].argmax())
                    fragments=[i for i in range(1,count) if i!=main and stats[i,cv2.CC_STAT_AREA]>20
                               and np.median(rgb[labels==i])>210]
                    assert fragments, "The supplied fixture no longer contains the correction-test fragment"
                    fragment=max(fragments,key=lambda i:stats[i,cv2.CC_STAT_AREA])
                    distance=cv2.distanceTransform((labels==fragment).astype(np.uint8),cv2.DIST_L2,5)
                    cy,cx=np.unravel_index(distance.argmax(),distance.shape)
                    click("BackgroundRemoverWand")
                    preview.setProperty("zoom",4)
                    scale=float(preview.property("imageScale"))
                    assert preview.setProperty("panX",float((preview.property("imageWidth")/2-cx)*scale))
                    assert preview.setProperty("panY",float((preview.property("imageHeight")/2-cy)*scale))
                    yield 100
                    point=canvas_point(cx,cy)
                    assert window.grabWindow().save(str(OUT/"character-wand-target.png"))
                    target_details=dict(pixel=[int(cx),int(cy)],scene=[point.x(),point.y()],
                                        tool=preview.property("tool"),scale=scale,visible=preview.isVisible(),
                                        page=controller.currentPage,editable=service.view["editable"])
                    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point)
                    yield from wait(service,40)
                    assert not service.lastError, service.view
                    with Image.open(service.view["output"]) as opened:
                        corrected=np.array(opened)
                    assert corrected[cy,cx,3]==0, f"Zoomed wand missed the fragment: {target_details}, {service.status}"
                    protected=(labels==main)&(rgb.max(axis=2)<150)&(before_cutout[:,:,3]>=240)
                    assert np.array_equal(corrected[protected],before_cutout[protected]), "Wand damaged separated dark foreground"
                    assert sha256(original)==before
                    click("BackgroundRemoverFit")
                    yield 300
                    assert window.grabWindow().save(str(OUT/"character-corrected.png"))
                    results["cases"].append("4x-zoomed native wand removes a remaining background fragment without changing dark foreground or original")
            saved = OUT / "saved-copy.png"
            with patch("kfps_ui.background_remove_service.QFileDialog.getSaveFileName", return_value=(str(saved), "PNG")):
                service.saveAs()
                yield from wait(service, 20)
            assert saved.read_bytes() == Path(service.view["output"]).read_bytes()
            service.useResult()
            yield from wait(service,30)
            assert source.path == str(saved)
            with patch("kfps_ui.background_remove_service.QFileDialog.getSaveFileName", return_value=(service.view["original"], "PNG")):
                service.saveAs()
            assert "never overwritten" in service.lastError
            service.configure("reset", True)
            results["cases"].append("Save copy; use as generator source; source-overwrite protection")
            with patch.object(desktop, "openFolder") as folder:
                service.openReport()
                assert folder.call_args.args[0] == str(Path(service.view["report"]).parent)
                service.openOutputFolder()
                assert folder.call_args.args[0] == str(Path(service.view["exported"]).parent)
            controller.navigate("upscaler")
            yield 400
            assert window.findChild(QObject, "UpscalerPage"), "Existing upscaler broken"
            controller.navigate("background-remover")
            yield 300
            assert service.view["output"] and not service.running
            results["cases"].append("Report/folder actions; page switching preserves result; upscaler still loads")
            for theme in sorted(KNOWN_THEME_NAMES):
                settings.theme = theme
                for width, height in ((960, 600), (1600, 1100)):
                    window.resize(width, height)
                    yield 350
                    preview = window.findChild(QObject, "BackgroundRemoverPreview")
                    assert preview and preview.width() > 200
                    button = window.findChild(QObject, "BackgroundRemoverStart")
                    point = button.mapToScene(QPointF(button.width()/2, button.height()/2))
                    assert 0 < point.x() < window.width() and 0 < point.y() < window.height()
                    slug = "".join(c if c.isalnum() else "-" for c in theme)
                    assert window.grabWindow().save(str(OUT / f"{slug}-{width}x{height}.png"))
                    results["cases"].append(f"{theme}: {width}x{height}")
            window.resize(1600, 1100)
            yield 250
            click("BackgroundRemoverAdvanced")
            yield 100
            assert page.property("advancedOpen")
            threads = window.findChild(QObject, "BackgroundRemoverThreads")
            threads.forceActiveFocus()
            QTest.keyClick(window, Qt.Key_Up)
            yield 100
            assert service.view["threads"] == 2, "CPU combo did not update the service"
            service.configure("refine", True)
            service.configure("cleanup", True)
            service.configure("threads", 1)
            service.configure("reset", True)
            assert not service.view["refine"] and not service.view["cleanup"] and service.view["threads"] == 4
            service.setSource(str(inputs / "white.png"))
            yield from wait(service, 20)
            service.configure("threads", 1)
            service.start()
            deadline = time.monotonic() + 30
            while not worker_children() and service.running and time.monotonic() < deadline:
                yield 25
            children = worker_children()
            assert children, "No real CPU worker reached cancellation test"
            pids = [child.pid for child in children]
            click("BackgroundRemoverCancel")
            yield from wait(service, 15)
            assert "cancelled" in service.status.lower(), service.view
            assert all(not psutil.pid_exists(pid) for pid in pids)
            results["cases"].append("Actual CPU worker cancellation and process cleanup")
            service.configure("threads", 4)
            service.start()
            yield from wait(service)
            assert service.view["output"] and not service.lastError, service.view
            assert not worker_children()
            results["cases"].append("Successful retry after cancellation")
            # Keep one real active worker for application shutdown to cancel and reap.
            service.configure("threads", 1)
            service.start()
            deadline = time.monotonic() + 30
            while not worker_children() and service.running and time.monotonic() < deadline:
                yield 25
            children = worker_children()
            assert children
            results["shutdown_pids"] = [child.pid for child in children]
            results["cases"].append("Application shutdown requested with real CPU worker active")
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
                "--skip-startup-index", "--skip-startup-thumbnails", "--width", "1600", "--height", "1100"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), patch.object(application, "install_development_harness", side_effect=install):
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    if worker_children() or any(psutil.pid_exists(pid) for pid in results.get("shutdown_pids", [])):
        results["errors"].append("CPU worker survived app shutdown")
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(dict(cases=len(results["cases"]), jobs=results["jobs"], errors=results["errors"],
                         qml_errors=results["qml_errors"], results=str(OUT / "results.json")), indent=2))
    return code or int(bool(results["errors"] or results["qml_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
