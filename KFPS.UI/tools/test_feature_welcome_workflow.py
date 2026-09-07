"""Opt-in offscreen welcome notice, targeting, dismissal and real restart checks."""
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
    result = {"action": action, "restart": restart, "cases": [], "errors": [], "qml_errors": []}
    install_root = out / ("install-" + action)
    install_root.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "VERSION", install_root / "VERSION")
    case = out / (action + ("-restart" if restart else "-first"))
    case.mkdir(exist_ok=True)
    paths = AppPaths(install_root, UI, UI / "qml", UI / "assets", install_root / "runtime", Path(sys.executable))

    def messages(kind, context, message):
        if any(word in message for word in ("Error:", "is not defined", "Cannot assign", "failed to load", "Binding loop")):
            result["qml_errors"].append(message)

    def harness(app, window, controller, community, settings, jsons, args):
        # Software/offscreen Qt cannot render the app's optional GPU glass layers.
        settings.glassEffects = False
        context = QQmlEngine.contextForObject(window)
        context.engine().rootContext().setContextProperty("screenshotMode", False)

        def click(item):
            assert item and item.isEnabled()
            pos = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(pos.x()), round(pos.y())))

        def steps():
            try:
                notice = window.findChild(QObject, "FeatureWelcomeOverlay")
                assert notice is not None
                if restart:
                    assert settings.supportUpscalerNoticeAcknowledged
                    assert not notice.property("visible"), "Acknowledged notice appeared after app restart"
                else:
                    assert notice.property("visible"), "First-launch notice did not open naturally"
                    assert not settings.supportUpscalerNoticeAcknowledged, "Opening must not acknowledge"
                    if action == "got-it":
                        for theme in sorted(KNOWN_THEME_NAMES):
                            settings.theme = theme
                            for width, height in ((960, 600), (1760, 1040)):
                                window.resize(width, height)
                                yield 350
                                report = window.findChild(QObject, "OpenPrefilledSupportForm")
                                actual = report.mapToScene(QPointF(report.width() / 2, report.height() / 2))
                                rect = notice.property("targetRect")
                                assert rect.contains(actual), (theme, "Arrow/spotlight lost its report target")
                                panel = window.findChild(QObject, "WelcomeAnnouncementPanel")
                                origin = panel.mapToScene(QPointF(0, 0))
                                assert origin.x() >= rect.right(), (theme, "Notice covers report button")
                                assert origin.y() >= 0 and origin.x() + panel.width() <= width + 1
                                assert origin.y() + panel.height() <= height + 1
                                scroll = window.findChild(QObject, "WelcomeMessageScroll")
                                for name in ("WelcomeSupportMessage", "WelcomeUpscalerMessage"):
                                    message = window.findChild(QObject, name)
                                    assert message.property("paintedWidth") <= message.width() + 1, (theme, "Notice text overflows horizontally")
                                    end = message.mapToScene(QPointF(message.width(), message.height()))
                                    viewport_end = scroll.mapToScene(QPointF(scroll.width(), scroll.height()))
                                    assert end.y() <= viewport_end.y() + 1, (theme, "Notice text is clipped")
                                for name in ("WelcomeGotIt", "WelcomeTryUpscaler"):
                                    button = window.findChild(QObject, name)
                                    pos = button.mapToScene(QPointF(0, 0))
                                    assert pos.x() >= origin.x() and pos.x() + button.width() <= origin.x() + panel.width() + 1
                                    assert pos.y() >= origin.y() and pos.y() + button.height() <= origin.y() + panel.height() + 1
                                slug = "".join(c if c.isalnum() else "-" for c in theme)
                                assert window.grabWindow().save(str(case / f"{slug}-{width}x{height}.png"))
                                result["cases"].append({"theme": theme, "size": [width, height]})
                    reports = context.contextProperty("reportService")
                    with patch.object(reports, "openSupportForm") as submit:
                        # Outside clicks must not dismiss or send a report.
                        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(5, 100))
                        yield 100
                        assert notice.property("visible")
                        click(window.findChild(QObject, "OpenPrefilledSupportForm"))
                        yield 100
                        assert notice.property("visible"), "Spotlight click must not dismiss or send a report"
                        if action == "escape":
                            QTest.keyClick(window, Qt.Key_Escape)
                        else:
                            click(window.findChild(QObject, "WelcomeGotIt" if action == "got-it" else "WelcomeTryUpscaler"))
                        yield 400
                        submit.assert_not_called()
                    assert not notice.property("visible")
                    assert settings.supportUpscalerNoticeAcknowledged
                    saved = json.loads(paths.settings_file.read_text())
                    assert saved["supportUpscalerNoticeAcknowledged"] is True
                    if action == "upscaler":
                        assert controller.currentPage == "upscaler"
                    controller.navigate("tools")
                    yield 1000
                    assert not notice.property("visible"), "Notice reopened after navigation"
                assert window.grabWindow().save(str(case / "after.png"))
            except Exception:
                result["errors"].append(traceback.format_exc())
            finally:
                (case / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                app.exit(1 if result["errors"] or result["qml_errors"] else 0)

        iterator = steps()
        def advance():
            try:
                delay = next(iterator)
            except StopIteration:
                return
            QTimer.singleShot(delay, advance)
        QTimer.singleShot(1500, advance)

    sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", "Night Blossom", "--screenshot", str(case / "capture.png"),
                "--skip-startup-index", "--skip-startup-thumbnails", "--allow-source-download", "--width", "960", "--height", "600"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), patch.object(application, "install_development_harness", side_effect=harness):
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    print(json.dumps(result))
    return code or int(bool(result["errors"] or result["qml_errors"]))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        return child(Path(sys.argv[2]), sys.argv[3], sys.argv[4] == "restart")
    out = ROOT / "runtime/welcome-testing" / datetime.now().strftime("workflow-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    for action in ("got-it", "upscaler", "escape"):
        for phase in ("first", "restart"):
            with (out / f"{action}-{phase}.log").open("w", encoding="utf-8") as log:
                run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(out), action, phase],
                                     stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
            if run.returncode:
                print(f"FAILED: {out / (action + '-' + phase + '.log')}")
                return run.returncode
    print(f"Passed: 16 theme/size captures; three dismissal actions and three real app restarts. Evidence: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
