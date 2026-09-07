"""Actual offscreen shell layout and input checks; external browsing is mocked."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from kfps_ui.app_paths import AppPaths
from kfps_ui.theme_catalog import KNOWN_THEME_NAMES
import app as application

OUT = ROOT / "runtime/discord-integration-testing" / datetime.now().strftime("join-%Y%m%d-%H%M%S")
OUT.mkdir(parents=True)
result = {"cases": [], "errors": [], "qml_errors": [], "clicks": 0}


def messages(kind, context, message):
    if any(word in message for word in ("Error:", "is not defined", "Cannot assign", "Binding loop", "failed to load")):
        result["qml_errors"].append(message)


def install(app, window, controller, community, settings, jsons, args):
    settings.glassEffects = False
    settings.reducedMotion = True

    def steps():
        try:
            button = window.findChild(QObject, "JoinSupportServer")
            ticker = window.findChild(QObject, "AnnouncementTicker")
            assert button is not None and ticker is not None
            for theme in sorted(KNOWN_THEME_NAMES):
                settings.theme = theme
                yield 100
                for size in ((960, 600), (1760, 1040)):
                    window.resize(*size)
                    yield 100
                    for page in ("create", "outputs", "community", "editor", "liveries", "tools", "upscaler", "help", "update", "settings"):
                        controller.navigate(page)
                        yield 120
                        for show in (True, False):
                            settings.liveStatusVisible = show
                            yield 30
                            top = button.mapToScene(QPointF(0, 0))
                            bottom = button.mapToScene(QPointF(button.width(), button.height()))
                            tick = ticker.mapToScene(QPointF(0, 0))
                            assert button.isVisible() and button.isEnabled()
                            assert 0 <= top.x() < bottom.x() <= window.width()
                            assert 0 <= top.y() < bottom.y() <= window.height()
                            assert abs(button.height() - ticker.height()) < 1
                            assert abs(top.y() - tick.y()) < 1
                            assert bottom.x() < tick.x(), (theme, page, "join overlaps ticker")
                            assert tick.x() + ticker.width() <= window.width(), (theme, page, "ticker outside window")
                            assert ticker.isVisible() == show
                            label = [c for c in button.findChildren(QObject) if c.property("text") == "Join the server" and c is not button]
                            assert label and all(c.property("truncated") is not True for c in label)
                            result["cases"].append({"theme": theme, "size": size, "page": page, "status_visible": show})
                    settings.liveStatusVisible = True
                    controller.navigate("create")
                    yield 100
                    slug = "".join(c if c.isalnum() else "-" for c in theme)
                    assert window.grabWindow().save(str(OUT / f"{slug}-{size[0]}x{size[1]}.png"))
            with patch("kfps_ui.report_service.QDesktopServices.openUrl", return_value=True) as opened:
                position = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(position.x()), round(position.y())))
                yield 30
                assert opened.call_count == 1
                button.forceActiveFocus()
                QTest.keyClick(window, Qt.Key_Space)
                yield 30
                assert opened.call_count == 2
                assert all(call.args[0].toString() == "https://discord.gg/XT8dG8bDKy" for call in opened.call_args_list)
                result["clicks"] = opened.call_count
        except Exception:
            result["errors"].append(traceback.format_exc())
        finally:
            (OUT / "results.json").write_text(json.dumps(result, indent=2))
            app.exit(int(bool(result["errors"] or result["qml_errors"])))
    iterator = steps()

    def advance():
        try:
            QTimer.singleShot(next(iterator), advance)
        except StopIteration:
            pass
    QTimer.singleShot(800, advance)


def main():
    isolated = OUT / "isolated-app"
    isolated.mkdir()
    shutil.copy2(ROOT / "VERSION", isolated / "VERSION")
    paths = AppPaths(isolated, UI, UI / "qml", UI / "assets", isolated / "runtime", Path(sys.executable))
    sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", "Night Blossom", "--screenshot", str(OUT / "capture-mode.png"), "--skip-startup-index", "--skip-startup-thumbnails", "--allow-source-download", "--width", "960", "--height", "600"]
    previous = qInstallMessageHandler(messages)
    try:
        with patch.object(AppPaths, "discover", return_value=paths), patch.object(application, "install_development_harness", side_effect=install):
            code = application.main()
    finally:
        qInstallMessageHandler(previous)
    print(json.dumps({"cases": len(result["cases"]), "errors": result["errors"], "qml_errors": result["qml_errors"], "clicks": result["clicks"], "evidence": str(OUT)}))
    return code or int(bool(result["errors"] or result["qml_errors"]) or result["clicks"] != 2)


if __name__ == "__main__":
    raise SystemExit(main())
