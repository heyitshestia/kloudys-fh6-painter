"""Exercise the native livery browser with isolated settings and no game writes."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI), str(UI / "src"), str(ROOT)]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"

from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from kfps_ui.app_paths import AppPaths
from kfps_ui.full_livery_service import FullLiveryService
import app as application


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--thumbnail-root", type=Path,
                        help="Optional ContainersRoot, sampled read-only for up to 12 real thumbnails")
    options = parser.parse_args()
    out = options.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = {"cases": [], "errors": [], "qml_errors": [], "screenshots": []}
    refresh_packages = FullLiveryService.refreshPackages

    def messages(kind, context, message):
        if any(token in message for token in (
            "ReferenceError", "TypeError", "Cannot assign", "Binding loop", "is not a type",
        )):
            results["qml_errors"].append(message)

    with tempfile.TemporaryDirectory(prefix="kfps-livery-grid-") as temporary:
        isolated = Path(temporary)
        shutil.copy2(ROOT / "VERSION", isolated / "VERSION")
        paths = AppPaths(isolated, UI, UI / "qml", UI / "assets",
                         isolated / "runtime", Path(sys.executable))
        samples = []
        if options.thumbnail_root:
            for container in sorted(options.thumbnail_root.glob("Livery_*")):
                candidate = container / "bigThumb.webp"
                if candidate.is_file():
                    samples.append(candidate)
                    if len(samples) == 12:
                        break
            assert samples, "No original thumbnails at the explicitly supplied ContainersRoot"

        rows = []
        for index in range(18):
            folder = isolated / "fixtures" / f"Livery with spaces #{index:02d}"
            folder.mkdir(parents=True)
            source = folder / "C_livery"
            source.write_bytes(b"synthetic source, never parsed or exported")
            if index < 12:
                if samples:
                    shutil.copy2(samples[index % len(samples)], folder / "bigThumb.webp")
                else:
                    image = QImage(670, 376, QImage.Format_RGB32)
                    image.fill(QColor.fromHsv(index * 25, 150, 160))
                    assert image.save(str(folder / "bigThumb.webp"))
            elif index == 13:
                (folder / "bigThumb.webp").write_bytes(b"broken thumbnail fixture")
            rows.append(dict(
                path=str(source), title=f"Livery {index + 1:02d}" + (
                    " - A very long title with <markup> & literal characters" if index == 0 else ""),
                modelCode="TEST_CAR", carId=1296 + index, placementCount=50 + index,
                exportable=index != 2, privacyDetail="Preview only" if index == 2 else "",
                modified="2026-09-09", hasHeader=True,
            ))
        results["original_thumbnail_samples"] = len(samples)

        def install(app, window, controller, community, settings, jsons, args):
            context = QQmlEngine.contextForObject(window)
            service = context.contextProperty("fullLiveryService")

            def items():
                pending = [window.contentItem()]
                found = []
                while pending:
                    item = pending.pop()
                    found.append(item)
                    pending.extend(item.childItems())
                return found

            def find(name):
                item = next((item for item in items() if item.objectName() == name), None)
                assert item is not None, "Missing native item: " + name
                return item

            def click(item):
                if isinstance(item, str):
                    item = find(item)
                assert item.isEnabled() and item.isVisible(), "Disabled or hidden: " + item.objectName()
                point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
                assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), item.objectName()
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                                 QPoint(round(point.x()), round(point.y())))

            def capture(name):
                QTest.mouseMove(window, QPoint(4, 4))
                target = out / (name + ".png")
                assert window.grabWindow().save(str(target))
                results["screenshots"].append(target.name)

            def apply_rows(values):
                service._apply_result({"kind": "scan", "ok": True, "payload": {"rows": values}})

            def image_status(item):
                expression = QQmlExpression(QQmlEngine.contextForObject(item), item, "Number(status)")
                value, undefined = expression.evaluate()
                assert not undefined and not expression.hasError()
                return int(value)

            def steps():
                try:
                    with ExitStack() as stack:
                        start = stack.enter_context(patch.object(service._tasks, "start", return_value=True))
                        controller.navigate("liveries")
                        yield 500
                        page = find("LiveryPage")
                        page.setProperty("wipNoticeAcknowledged", True)
                        apply_rows(rows)
                        yield 800
                        grid = find("liveryThumbnailGrid")
                        assert grid.property("count") == len(rows)
                        image = find("liveryThumbnailImage:" + rows[0]["path"])
                        assert image_status(image) == 1, "Original WebP did not reach Image.Ready"
                        assert image.property("source").hasQuery(), "Thumbnail revision missing"
                        start.assert_not_called()
                        results["cases"].append("Real QML grid loads revisioned, escaped local WebP URLs without a worker")

                        click("liveryThumbnailTile:" + rows[0]["path"])
                        yield 100
                        assert service.selectedSource == rows[0]["path"]
                        start.assert_not_called()
                        assert not find("openSelectedLiveryPreviewButton").isEnabled()
                        service._game_folder = str(isolated / "fixture-game")
                        service.changed.emit()
                        yield 100
                        capture("grid-desktop-1440x900")
                        click("openSelectedLiveryPreviewButton")
                        yield 150
                        assert not page.property("showGallery")
                        assert start.call_count == 1 and start.call_args.args[0] == "preview-source"
                        assert start.call_args.args[1]["source"] == rows[0]["path"]
                        click("returnToLiveryGridButton")
                        yield 100
                        assert page.property("showGallery") and not service.viewerUrl
                        assert service.selectedSource == rows[0]["path"]
                        results["cases"].append("Tile selects only; linked-folder Open 3D Preview routes to existing worker; Back retains selection")

                        tile = find("liveryThumbnailTile:" + rows[0]["path"])
                        point = tile.mapToScene(QPointF(tile.width() / 2, tile.height() / 2))
                        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier,
                                          QPoint(round(point.x()), round(point.y())))
                        yield 150
                        assert not page.property("showGallery") and start.call_count == 2
                        assert service._source_preview_serial == start.call_args.kwargs["metadata"]["request_serial"]
                        click("returnToLiveryGridButton")
                        yield 100
                        find("liveryThumbnailTile:" + rows[0]["path"]).forceActiveFocus()
                        QTest.keyClick(window, Qt.Key_Return)
                        yield 150
                        assert not page.property("showGallery") and start.call_count == 3
                        click("returnToLiveryGridButton")
                        yield 100
                        results["cases"].append("Double-click and keyboard Return open the selected livery exactly once")

                        with patch.object(service._tasks, "start", return_value=True) as export_jobs, \
                                patch.object(service, "refreshPackages", side_effect=lambda: refresh_packages(service)):
                            click("PrimaryButton:Export Selected")
                            yield 100
                            assert export_jobs.call_count == 1
                            assert export_jobs.call_args.args[0] == "export-package"
                            package = Path(export_jobs.call_args.args[1]["output"])
                            package.write_bytes(b"simulated export-worker result")
                            service._apply_result({"ok": True, "kind": "export", "payload": {"path": str(package)}})
                            yield 100
                            assert export_jobs.call_count == 2
                            assert export_jobs.call_args.args[0] == "refresh-packages"
                            metadata = export_jobs.call_args.kwargs.get("metadata") or {}
                            assert not metadata.get("open_package")
                            service._apply_result({
                                "ok": True, "kind": "refresh-packages", **metadata,
                                "payload": {"rows": [dict(path=str(package), title="Exported livery", carId=1296,
                                                          modelCode="TEST_CAR", placementCount=50, portableMesh=False)]},
                            })
                            yield 250
                            assert export_jobs.call_count == 2
                            assert page.property("showGallery") and not service.viewerUrl
                            assert service.selectedSource == rows[0]["path"]
                            assert not service.selectedPackage and not service.running
                            assert service.packageModel.row(0)["path"] == str(package)
                            capture("grid-after-export")
                        results["cases"].append("Export Selected refreshes Saved packages without opening 3D or changing the selected source")

                        search = find("liveryGridSearch")
                        search.setProperty("text", "lIvErY 02")
                        yield 300
                        assert grid.property("count") == 1
                        click("liveryThumbnailTile:" + rows[1]["path"])
                        yield 80
                        assert service.selectedSource == rows[1]["path"]
                        search.setProperty("text", ".*")
                        yield 300
                        assert grid.property("count") == 0
                        capture("grid-no-matches")
                        search.setProperty("text", "")
                        yield 300
                        assert grid.property("count") == len(rows)
                        results["cases"].append("Actual search field filters literally without selection/path drift")

                        grid.setProperty("contentY", float(grid.property("contentHeight")) - grid.height())
                        yield 500
                        missing = find("liveryThumbnailImage:" + rows[12]["path"])
                        broken = find("liveryThumbnailImage:" + rows[13]["path"])
                        assert image_status(missing) == 0 and image_status(broken) == 3
                        capture("grid-missing-broken-thumbnails")
                        results["cases"].append("Missing and corrupt thumbnails remain browsable with a placeholder")

                        grid.setProperty("contentY", 0)
                        for width, height in ((1024, 720), (960, 600), (1920, 1080)):
                            window.resize(width, height)
                            yield 350
                            assert grid.width() > 200 and grid.height() > 150
                            origin = grid.mapToScene(QPointF(0, 0))
                            assert origin.x() + grid.width() <= window.width() + 1
                            assert origin.y() + grid.height() <= window.height() + 1
                            capture(f"grid-{width}x{height}")
                        results["cases"].append("Grid remains inside the native window at compact and wide sizes")

                        thumbnail_file = Path(rows[0]["path"]).parent / "bigThumb.webp"
                        original_bytes = thumbnail_file.read_bytes()
                        replacement = QImage(670, 376, QImage.Format_RGB32)
                        replacement.fill(QColor("#25a673"))
                        assert replacement.save(str(thumbnail_file))
                        apply_rows(rows)
                        yield 500
                        refreshed = find("liveryThumbnailImage:" + rows[0]["path"])
                        assert image_status(refreshed) == 1
                        center = refreshed.mapToScene(QPointF(refreshed.width() / 2, refreshed.height() / 2))
                        pixel = window.grabWindow().pixelColor(round(center.x()), round(center.y()))
                        assert abs(pixel.green() - 166) < 8 and abs(pixel.red() - 37) < 8, pixel.name()
                        thumbnail_file.write_bytes(original_bytes)
                        apply_rows(rows)
                        yield 300
                        results["cases"].append("Replacing a thumbnail refreshes actual displayed pixels while C_livery is unchanged")

                        # Repeated model URLs isolate delegate lifetime from save-parser performance.
                        large = [dict(service.sourceModel.row(i % len(rows)), path=f"fixture-{i}", title=f"Stress {i}")
                                 for i in range(1500)]
                        service._sources.replace(large)
                        yield 500
                        count_before = len([item for item in items()
                                            if item.objectName().startswith("liveryThumbnailTile:")])
                        for fraction in (0.1, 0.5, 0.9, 1, 0):
                            grid.setProperty("contentY", fraction * (float(grid.property("contentHeight")) - grid.height()))
                            yield 150
                        count_after = len([item for item in items()
                                           if item.objectName().startswith("liveryThumbnailTile:")])
                        assert 0 < count_before < 80 and 0 < count_after < 80, (count_before, count_after)
                        results["delegate_counts"] = dict(rows=1500, before=count_before, after=count_after,
                                                          measurement="tiles attached to the visual tree")
                        results["cases"].append("1500 rows stay virtualized after long-distance scrolling")

                        apply_rows(rows)
                        yield 200
                        click("openSelectedLiveryPreviewButton")
                        yield 80
                        controller.navigate("tools")
                        yield 250
                        controller.navigate("liveries")
                        yield 300
                        page = find("LiveryPage")
                        page.setProperty("wipNoticeAcknowledged", True)
                        apply_rows(rows)
                        yield 150
                        assert page.property("showGallery")
                        assert not service.viewerUrl and not service._active_source_preview
                        results["cases"].append("Leaving/reopening the page returns to the grid without restarting an old preview")
                        apply_rows([])
                        yield 150
                        assert find("liveryThumbnailGrid").property("count") == 0
                        assert not service.selectedSource
                        capture("grid-empty")
                        results["cases"].append("Empty scan clears vanished selection")
                except Exception:
                    results["errors"].append(traceback.format_exc())
                    capture("failure")
                finally:
                    app.exit(int(bool(results["errors"] or results["qml_errors"])))

            iterator = steps()

            def advance():
                try:
                    delay = next(iterator)
                except StopIteration:
                    return
                QTimer.singleShot(delay, advance)

            QTimer.singleShot(700, advance)

        sys.argv = [str(UI / "app.py"), "--demo", "--theme-preview", "Night Blossom",
                    "--screenshot", str(out / "capture-mode.png"), "--skip-startup-index",
                    "--skip-startup-thumbnails", "--width", "1440", "--height", "900"]
        previous = qInstallMessageHandler(messages)
        try:
            with patch.object(AppPaths, "discover", return_value=paths), \
                    patch.object(FullLiveryService, "scanSaves"), \
                    patch.object(FullLiveryService, "refreshPackages"), \
                    patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None), \
                    patch.object(application, "install_development_harness", side_effect=install):
                code = application.main()
        finally:
            qInstallMessageHandler(previous)
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return code or int(bool(results["errors"] or results["qml_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
