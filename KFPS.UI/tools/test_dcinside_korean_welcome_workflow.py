"""Real QML notice workflow with isolated settings, language simulation and restarts."""
from datetime import datetime
from contextlib import ExitStack
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
from PySide6.QtGui import QFont, QFontDatabase, QRawFont
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
import app as application

ACK = "dcinsideKoreanNotice202609Acknowledged"


def child(out, action, restart):
    result = dict(action=action, restart=restart, checks=[], errors=[], qml_errors=[])
    install = out / ("install-" + action)
    install.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "VERSION", install / "VERSION")
    case = out / (action + ("-restart" if restart else "-first"))
    case.mkdir(exist_ok=True)
    paths = AppPaths(install, UI, UI / "qml", UI / "assets", install / "runtime", Path(sys.executable))
    if not restart:
        paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
        paths.settings_file.write_text(json.dumps({
            "supportUpscalerNoticeAcknowledged": action != "fresh",
            "communityJoinNoticeAcknowledged": action != "fresh",
            "backgroundRemoverNoticeAcknowledged": action != "fresh",
        }), encoding="utf-8")

    def create_application(args):
        app = QApplication(args)
        # The offscreen platform does not discover the Windows system fonts.
        fonts = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"
        for name in ("malgun.ttf", "malgunbd.ttf", "segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguiemj.ttf"):
            assert QFontDatabase.addApplicationFont(str(fonts / name)) >= 0, name
        korean = QRawFont.fromFont(QFont("Malgun Gothic", 12))
        text = (UI / "qml/shell/DcinsideKoreanWelcomeOverlay.qml").read_text(encoding="utf-8")
        characters = {ord(c) for c in text if 0xAC00 <= ord(c) <= 0xD7A3 or 0x3130 <= ord(c) <= 0x318F}
        assert all(korean.supportsCharacter(code) for code in characters)
        emoji = QRawFont.fromFont(QFont("Segoe UI Emoji", 12))
        assert all(emoji.supportsCharacter(code) for code in (0x1F60A, 0x1F64F))
        result["checks"].append(f"Installed fonts support all {len(characters)} Korean characters and both emoji")
        return app

    def messages(kind, context, message):
        if any(value in message for value in ("Error:", "is not defined", "Cannot assign", "failed to load", "Binding loop")):
            result["qml_errors"].append(message)

    def harness(app, window, controller, community, settings, jsons, args):
        settings.glassEffects = False
        settings.reducedMotion = True
        context = QQmlEngine.contextForObject(window)
        context.engine().rootContext().setContextProperty("screenshotMode", action == "capture")

        def item(name):
            found = window.findChild(QObject, name)
            if found is None and name.startswith("DcinsideKoreanParagraph"):
                found = next((label for label in item("DcinsideKoreanWelcomeBody").childItems()
                              if label.objectName() == name), None)
            assert found is not None, name
            return found

        def click(name):
            target = item(name)
            assert target.isEnabled()
            point = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))

        def steps():
            try:
                notice = item("DcinsideKoreanWelcomeOverlay")
                if (restart and action not in ("interrupted", "read-only", "language-change")) or action == "capture" or (action == "language-change" and not restart):
                    assert not notice.property("visible"), "Suppressed notice opened"
                    assert settings.dcinsideKoreanNoticeAcknowledged == (restart and action != "capture")
                    result["checks"].append("No popup for acknowledged, capture-mode or non-Korean launch")
                else:
                    if action == "fresh":
                        for overlay, button in (("FeatureWelcomeOverlay", "WelcomeGotIt"),
                                                ("CommunityWelcomeOverlay", "CommunityWelcomeGotIt"),
                                                ("BackgroundRemoverWelcomeOverlay", "BackgroundRemoverWelcomeGotIt")):
                            assert item(overlay).property("visible")
                            assert not notice.property("visible")
                            click(button)
                            yield 1100
                        result["checks"].append("Existing three notices queue before the Korean notice")
                    assert notice.property("visible"), "Korean notice did not open naturally"
                    assert not settings.dcinsideKoreanNoticeAcknowledged
                    for name in ("FeatureWelcomeOverlay", "CommunityWelcomeOverlay", "BackgroundRemoverWelcomeOverlay"):
                        assert not item(name).property("visible"), "Notice overlap"
                    if action == "got-it":
                        for theme in sorted(KNOWN_THEME_NAMES):
                            settings.theme = theme
                            for width, height in ((960, 600), (1440, 1080)):
                                window.resize(width, height)
                                yield 400
                                panel = item("DcinsideKoreanWelcomePanel")
                                point = panel.mapToScene(QPointF(0, 0))
                                assert point.x() >= 0 and point.y() >= 0
                                assert point.x() + panel.width() <= window.width() + 1
                                assert point.y() + panel.height() <= window.height() + 1
                                scroll = item("DcinsideKoreanWelcomeScroll")
                                bar = item("DcinsideKoreanWelcomeScrollBar")
                                bar_point = bar.mapToScene(QPointF(0, 0))
                                body = item("DcinsideKoreanWelcomeBody")
                                body_point = body.mapToScene(QPointF(0, 0))
                                assert bar_point.x() >= body_point.x() + body.width(), "Scrollbar overlaps message"
                                assert bar_point.x() + bar.width() <= point.x() + panel.width()
                                previous_bottom = 0
                                for index in range(9):
                                    label = item("DcinsideKoreanParagraph" + str(index))
                                    assert label.property("paintedWidth") <= label.width() + 1, (theme, index, "text overflow")
                                    assert label.property("paintedHeight") > 0
                                    assert label.y() >= previous_bottom - 1
                                    previous_bottom = label.y() + label.height()
                                button = item("DcinsideKoreanWelcomeGotIt")
                                position = button.mapToScene(QPointF(0, 0))
                                scroll_point = scroll.mapToScene(QPointF(0, 0))
                                assert position.y() >= scroll_point.y() + scroll.height()
                                assert position.x() >= point.x() and position.x() + button.width() <= point.x() + panel.width() + 1
                                assert position.y() + button.height() <= point.y() + panel.height() + 1
                                flickable = scroll.property("contentItem")
                                if width == 960:
                                    assert scroll.property("contentHeight") > scroll.height(), "Small-window case should scroll"
                                    assert bar.isVisible(), "Scrollable message has no scrollbar"
                                    flickable.setProperty("contentY", 0)
                                    QTest.wheelEvent(window, QPointF(scroll_point.x() + scroll.width() / 2,
                                                                  scroll_point.y() + scroll.height() / 2), QPoint(0, -120))
                                    yield 150
                                    assert flickable.property("contentY") > 0, "Mouse wheel did not scroll message"
                                    flickable.setProperty("contentY", scroll.property("contentHeight") - flickable.height())
                                    yield 150
                                    signature = item("DcinsideKoreanParagraph8")
                                    sign_point = signature.mapToScene(QPointF(0, 0))
                                    assert sign_point.y() >= scroll_point.y() - 1
                                    assert sign_point.y() + signature.height() <= scroll_point.y() + scroll.height() + 1
                                    assert notice.property("visible"), "Scrolling dismissed notice"
                                else:
                                    flickable.setProperty("contentY", 0)
                                    yield 150
                                    assert scroll.property("contentHeight") <= scroll.height() + 1, "Preview should show the entire message"
                                    assert not bar.isVisible(), "Unneeded scrollbar should be hidden"
                                slug = "".join(c if c.isalnum() else "-" for c in theme)
                                assert window.grabWindow().save(str(case / f"{slug}-{width}x{height}.png"))
                                result["checks"].append(f"{theme} {width}x{height}: text, scrolling, button and panel bounds")
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(5, 100))
                    yield 100
                    assert notice.property("visible"), "Outside click dismissed notice"
                    if action == "interrupted" and not restart:
                        result["checks"].append("Exit before acknowledgement leaves notice pending")
                    else:
                        if action == "read-only" and not restart:
                            lifetime.enter_context(patch.object(settings, "save", side_effect=PermissionError("read-only test")))
                            click("DcinsideKoreanWelcomeGotIt")
                            assert not json.loads(paths.settings_file.read_text()).get(ACK, False)
                        elif action == "escape":
                            QTest.keyClick(window, Qt.Key_Escape)
                        else:
                            click("DcinsideKoreanWelcomeGotIt")
                        yield 1000
                        assert not notice.property("visible") and settings.dcinsideKoreanNoticeAcknowledged
                        if action != "read-only" or restart:
                            assert json.loads(paths.settings_file.read_text())[ACK] is True
                            settings.reset()
                            assert settings.dcinsideKoreanNoticeAcknowledged
                        controller.navigate("tools")
                        yield 1000
                        assert not notice.property("visible"), "Navigation or reset repeated notice"
                        result["checks"].append("Dismissal works; navigation and preference reset do not repeat notice")
                browser.assert_not_called()
                collect.assert_not_called()
            except Exception:
                result["errors"].append(traceback.format_exc())
            finally:
                window.grabWindow().save(str(case / "last-state.png"))
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
        with patch.object(application, "QApplication", side_effect=create_application), patch.object(AppPaths, "discover", return_value=paths), patch.object(
            application, "install_development_harness", side_effect=harness
        ), patch("kfps_ui.settings_service.is_korean_display_language", return_value=action != "language-change" or restart), patch(
            "kfps_ui.report_service.QDesktopServices.openUrl", return_value=True
        ) as browser, patch("kfps_ui.report_service.ReportService.openSupportForm") as collect, ExitStack() as lifetime:
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    print(json.dumps(result))
    return code or int(bool(result["errors"] or result["qml_errors"]))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        return child(Path(sys.argv[2]), sys.argv[3], sys.argv[4] == "restart")
    out = ROOT / "runtime/welcome-testing" / datetime.now().strftime("dcinside-korean-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    runs = []
    for action in ("got-it", "escape", "fresh", "read-only", "interrupted", "capture", "language-change"):
        for phase in (("first",) if action == "capture" else ("first", "restart")):
            with (out / f"{action}-{phase}.log").open("w", encoding="utf-8") as log:
                run = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--child", str(out), action, phase],
                                     stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120)
            runs.append(dict(action=action, phase=phase, exit_code=run.returncode))
            (out / "runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
            if run.returncode:
                print(f"FAILED ({run.returncode}): {out / (action+'-'+phase+'.log')}")
                return run.returncode
    print(f"Passed: 16 theme/size captures and {len(runs)} isolated app launches. Evidence: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
