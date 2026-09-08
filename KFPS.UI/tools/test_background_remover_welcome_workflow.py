"""Exercise the real welcome popup offscreen with isolated settings and restarts."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QTimer, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
import app as application


def child(out, action, restart):
    result = dict(action=action, restart=restart, cases=[], errors=[], qml_errors=[])
    install = out / ("install-" + action)
    install.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "VERSION", install / "VERSION")
    case = out / (action + ("-restart" if restart else "-first"))
    case.mkdir(exist_ok=True)
    paths = AppPaths(install, UI, UI / "qml", UI / "assets", install / "runtime", Path(sys.executable))
    if not restart:
        paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
        paths.settings_file.write_text(json.dumps({"supportUpscalerNoticeAcknowledged": action != "fresh",
                                                   "communityJoinNoticeAcknowledged": action != "fresh"}))

    def messages(kind, context, message):
        if any(value in message for value in ("Error:", "is not defined", "Cannot assign", "failed to load", "Binding loop")):
            result["qml_errors"].append(message)

    def harness(app, window, controller, community, settings, jsons, args):
        settings.glassEffects = False
        settings.reducedMotion = True
        context = QQmlEngine.contextForObject(window)
        context.engine().rootContext().setContextProperty("screenshotMode", action == "capture")

        def click(name):
            item = window.findChild(QObject, name)
            assert item and item.isEnabled(), name
            point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))

        def steps():
            try:
                notice = window.findChild(QObject, "BackgroundRemoverWelcomeOverlay")
                old = window.findChild(QObject, "FeatureWelcomeOverlay")
                server = window.findChild(QObject, "CommunityWelcomeOverlay")
                service = context.contextProperty("backgroundRemoveService")
                assert notice is not None and old is not None and server is not None
                if restart or action == "capture":
                    assert not notice.property("visible")
                    assert settings.backgroundRemoverNoticeAcknowledged == restart
                    result["cases"].append("Restart stays dismissed" if restart else "Capture mode suppresses popup without acknowledging")
                else:
                    if action == "fresh":
                        assert old.property("visible") and not server.property("visible") and not notice.property("visible")
                        click("WelcomeGotIt")
                        yield 1100
                        assert server.property("visible") and not old.property("visible") and not notice.property("visible")
                        click("CommunityWelcomeGotIt")
                        yield 1100
                        result["cases"].append("Three fresh-install notices appear sequentially without overlap")
                    assert notice.property("visible"), "New notice did not open naturally"
                    assert not old.property("visible") and not server.property("visible")
                    assert not settings.backgroundRemoverNoticeAcknowledged
                    if action == "got-it":
                        for theme in sorted(KNOWN_THEME_NAMES):
                            settings.theme = theme
                            for width, height in ((960, 600), (1760, 1040)):
                                window.resize(width, height)
                                yield 350
                                panel = window.findChild(QObject, "BackgroundRemoverWelcomePanel")
                                point = panel.mapToScene(QPointF(0, 0))
                                assert 0 <= point.x() and point.x()+panel.width() <= width+1
                                assert 0 <= point.y() and point.y()+panel.height() <= height+1
                                for name in ("Title", "Message", "Corrections", "Download"):
                                    label = window.findChild(QObject, "BackgroundRemoverWelcome"+name)
                                    assert label.property("paintedWidth") <= label.width()+1, (theme, name, "Overflow")
                                for name in ("GotIt", "Open"):
                                    button = window.findChild(QObject, "BackgroundRemoverWelcome"+name)
                                    position = button.mapToScene(QPointF(0, 0))
                                    assert position.x() >= point.x() and position.x()+button.width() <= point.x()+panel.width()+1
                                    assert position.y() >= point.y() and position.y()+button.height() <= point.y()+panel.height()+1
                                art = window.findChild(QObject, "BackgroundRemoverWelcomeArt")
                                assert art.property("paintedWidth") > 0 and art.property("paintedHeight") > 0
                                slug = "".join(c if c.isalnum() else "-" for c in theme)
                                assert window.grabWindow().save(str(case / f"{slug}-{width}x{height}.png"))
                                result["cases"].append(f"{theme} {width}x{height}")
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(5, 100))
                    yield 100
                    assert notice.property("visible"), "Outside click dismissed notice"
                    if action == "read-only":
                        def deny_save():
                            raise PermissionError("read-only test")
                        with patch.object(settings, "save", new=deny_save):
                            click("BackgroundRemoverWelcomeGotIt")
                    elif action == "escape":
                        QTest.keyClick(window, Qt.Key_Escape)
                    else:
                        click("BackgroundRemoverWelcomeOpen" if action == "open" else "BackgroundRemoverWelcomeGotIt")
                    yield 1100
                    assert not notice.property("visible") and settings.backgroundRemoverNoticeAcknowledged
                    if action != "read-only":
                        assert json.loads(paths.settings_file.read_text())["backgroundRemoverNoticeAcknowledged"] is True
                    if action == "open":
                        assert controller.currentPage == "background-remover"
                        assert window.findChild(QObject, "BackgroundRemoverPage") is not None
                    controller.navigate("tools")
                    yield 1000
                    assert not notice.property("visible"), "Dismissed notice repeated after navigation"
                    result["cases"].append("Explicit dismissal persists and navigation does not reopen it")
                assert service._future is None and not service.running, "Welcome notice started work"
                assert not (paths.runtime_root / "background-remover/engines").exists(), "Welcome notice downloaded an engine"
                browser.assert_not_called()
                assert window.grabWindow().save(str(case / "after.png"))
            except Exception:
                result["errors"].append(traceback.format_exc())
            finally:
                (case / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                app.exit(int(bool(result["errors"] or result["qml_errors"])))
        iterator = steps()
        def advance():
            try:
                QTimer.singleShot(next(iterator), advance)
            except StopIteration:
                pass
        QTimer.singleShot(1500, advance)

    sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", "Night Blossom", "--screenshot", str(case / "capture.png"),
                "--skip-startup-index", "--skip-startup-thumbnails", "--width", "960", "--height", "600"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), patch.object(application, "install_development_harness", side_effect=harness), patch("kfps_ui.report_service.QDesktopServices.openUrl", return_value=True) as browser:
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    print(json.dumps(result))
    return code or int(bool(result["errors"] or result["qml_errors"]))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        return child(Path(sys.argv[2]), sys.argv[3], sys.argv[4] == "restart")
    out = ROOT / "runtime/background-remover/validation" / datetime.now().strftime("welcome-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    for action in ("got-it", "open", "escape", "fresh", "read-only", "capture"):
        phases = ("first",) if action in ("read-only", "capture") else ("first", "restart")
        for phase in phases:
            with (out / f"{action}-{phase}.log").open("w", encoding="utf-8") as log:
                run = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--child", str(out), action, phase],
                                     stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
            if run.returncode:
                print(f"FAILED ({run.returncode}): {out / (action+'-'+phase+'.log')}")
                return run.returncode
    print(f"Passed: 16 theme/size captures; dismissal, navigation, Escape, queueing, read-only settings, capture mode and four restarts. Evidence: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
