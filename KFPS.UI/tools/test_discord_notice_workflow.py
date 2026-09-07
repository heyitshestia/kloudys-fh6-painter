"""Offscreen product checks for the one-time community notice and contest expiry."""
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
from PySide6.QtCore import QObject, QDate, QDateTime, QPoint, QPointF, Qt, QTime, QTimer, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
import app as application


def child(out, action, restart):
    result = {"action": action, "restart": restart, "cases": [], "errors": [], "qml_errors": [], "browser_opens": 0}
    install_root = out / ("install-" + action)
    install_root.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "VERSION", install_root / "VERSION")
    case = out / (action + ("-restart" if restart else "-first"))
    case.mkdir(exist_ok=True)
    paths = AppPaths(install_root, UI, UI / "qml", UI / "assets", install_root / "runtime", Path(sys.executable))
    if not restart:
        paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
        paths.settings_file.write_text(json.dumps({"supportUpscalerNoticeAcknowledged": action != "fresh"}))

    def messages(kind, context, message):
        if any(word in message for word in ("Error:", "is not defined", "Cannot assign", "failed to load", "Binding loop")):
            result["qml_errors"].append(message)

    def harness(app, window, controller, community, settings, jsons, args):
        settings.glassEffects = False
        settings.reducedMotion = True
        context = QQmlEngine.contextForObject(window)
        context.engine().rootContext().setContextProperty("screenshotMode", False)

        def click(item):
            assert item and item.isEnabled()
            pos = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(pos.x()), round(pos.y())))

        def steps():
            try:
                notice = window.findChild(QObject, "CommunityWelcomeOverlay")
                old = window.findChild(QObject, "FeatureWelcomeOverlay")
                assert notice is not None and old is not None
                if restart:
                    assert settings.communityJoinNoticeAcknowledged
                    assert not notice.property("visible"), "Dismissed notice reopened after process restart"
                    assert not old.property("visible")
                else:
                    if action == "fresh":
                        assert old.property("visible") and not notice.property("visible"), "Startup notices overlap"
                        click(window.findChild(QObject, "WelcomeGotIt"))
                        yield 1100
                    assert notice.property("visible"), "Community notice did not open naturally"
                    assert not old.property("visible"), "Startup notices overlap"
                    assert not settings.communityJoinNoticeAcknowledged
                    notice.setProperty("currentDate", QDateTime(QDate(2026, 9, 30), QTime(23, 59, 59)))
                    assert notice.property("contestActive")
                    if action == "got-it":
                        for theme in sorted(KNOWN_THEME_NAMES):
                            settings.theme = theme
                            for width, height in ((960, 600), (1760, 1040)):
                                window.resize(width, height)
                                yield 350
                                target = window.findChild(QObject, "JoinSupportServer")
                                actual = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
                                rect = notice.property("targetRect")
                                assert rect.contains(actual), (theme, "Spotlight lost Join the server")
                                panel = window.findChild(QObject, "CommunityWelcomePanel")
                                origin = panel.mapToScene(QPointF(0, 0))
                                assert origin.y() > rect.bottom(), (theme, "Notice covers join target")
                                assert origin.x() >= 0 and origin.x() + panel.width() <= width + 1
                                assert origin.y() + panel.height() <= height + 1
                                scroll = window.findChild(QObject, "CommunityWelcomeScroll")
                                for name in ("CommunityWelcomeMessage", "CommunityContestEntry", "CommunityContestDeadline", "CommunityContestPrizes"):
                                    message = window.findChild(QObject, name)
                                    assert message.property("paintedWidth") <= message.width() + 1, (theme, name, "Text overflows")
                                    end = message.mapToScene(QPointF(message.width(), message.height()))
                                    viewport_end = scroll.mapToScene(QPointF(scroll.width(), scroll.height()))
                                    assert end.y() <= viewport_end.y() + 1, (theme, name, "Text clipped")
                                for name in ("CommunityWelcomeGotIt", "CommunityWelcomeJoin"):
                                    button = window.findChild(QObject, name)
                                    pos = button.mapToScene(QPointF(0, 0))
                                    assert pos.x() >= origin.x() and pos.x() + button.width() <= origin.x() + panel.width() + 1
                                    assert pos.y() >= origin.y() and pos.y() + button.height() <= origin.y() + panel.height() + 1
                                slug = "".join(c if c.isalnum() else "-" for c in theme)
                                assert window.grabWindow().save(str(case / f"{slug}-{width}x{height}.png"))
                                result["cases"].append({"theme": theme, "size": [width, height]})
                    if action == "expired":
                        notice.setProperty("currentDate", QDateTime(QDate(2026, 10, 1), QTime(0, 0)))
                        yield 200
                        assert not notice.property("contestActive"), "Contest remained advertised after September"
                        assert not window.findChild(QObject, "CommunityContestSection").isVisible()
                        assert window.findChild(QObject, "CommunityWelcomeMessage").isVisible()
                        assert window.grabWindow().save(str(case / "expired.png"))
                    reports = context.contextProperty("reportService")
                    with patch.object(reports, "openSupportForm") as submit:
                        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(5, 100))
                        yield 80
                        assert notice.property("visible")
                        click(window.findChild(QObject, "JoinSupportServer"))
                        yield 80
                        assert notice.property("visible"), "Spotlight click should not dismiss"
                        assert browser_open.call_count == 0
                        if action == "escape":
                            QTest.keyClick(window, Qt.Key_Escape)
                        else:
                            click(window.findChild(QObject, "CommunityWelcomeJoin" if action == "join" else "CommunityWelcomeGotIt"))
                        yield 300
                        submit.assert_not_called()
                    assert not notice.property("visible")
                    assert settings.communityJoinNoticeAcknowledged
                    saved = json.loads(paths.settings_file.read_text())
                    assert saved["communityJoinNoticeAcknowledged"] is True
                    assert browser_open.call_count == int(action == "join")
                    if action == "join":
                        assert browser_open.call_args.args[0].toString() == "https://discord.gg/XT8dG8bDKy"
                    result["browser_opens"] = browser_open.call_count
                    controller.navigate("community")
                    yield 1100
                    assert not notice.property("visible"), "Notice reopened after navigation"
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
                "--skip-startup-index", "--skip-startup-thumbnails", "--allow-source-download", "--width", "960", "--height", "600"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), patch.object(application, "install_development_harness", side_effect=harness), patch("kfps_ui.report_service.QDesktopServices.openUrl", return_value=True) as browser_open:
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    print(json.dumps(result))
    return code or int(bool(result["errors"] or result["qml_errors"]))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        return child(Path(sys.argv[2]), sys.argv[3], sys.argv[4] == "restart")
    out = ROOT / "runtime/discord-integration-testing" / datetime.now().strftime("notice-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    for action in ("got-it", "join", "escape", "fresh", "expired"):
        for phase in ("first", "restart"):
            with (out / f"{action}-{phase}.log").open("w", encoding="utf-8") as log:
                run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(out), action, phase],
                                     stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
            if run.returncode:
                print(f"FAILED: {out / (action + '-' + phase + '.log')}")
                return run.returncode
    print(f"Passed: 16 theme/size captures; join, acknowledgement, Escape, fresh-install sequencing, expiry and five process restarts. Evidence: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
