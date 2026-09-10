"""Independent entry point for the KFPS Vinyl Editor."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(UI_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="KFPS Vinyl Editor")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--mode", choices=("activate", "new", "json", "tutorial"), default="activate")
    parser.add_argument("--runtime-root", type=Path, help="Editor data directory; defaults to the installation runtime/fabric-editor directory.")
    parser.add_argument("--from-kfps", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    # A shortcut's working directory or inherited root must not select another install.
    os.environ["KFPS_APP_ROOT"] = str(UI_ROOT.parent)
    runtime = (args.runtime_root or UI_ROOT.parent / "runtime" / "fabric-editor").resolve()
    host = None
    app = None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
        from kfps_ui.app_paths import AppPaths
        from kfps_ui.source_download_guard import evaluate_source_download_guard
        from kfps_ui.editor_desktop import EditorDesktop, forward_request, instance_name, validate_request
        from kfps_ui.editor_launch import wait_until_ready

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv[:1])
        app.setApplicationName("KFPS Vinyl Editor")
        app.setOrganizationName("KFPS")
        paths = AppPaths.discover()
        if evaluate_source_download_guard(paths.app_root).blocked:
            raise RuntimeError("GitHub source downloads are not runnable releases. Use a complete KFPS installation.")
        request = validate_request({"project": args.project_id, "mode": args.mode})
        name = instance_name(paths.app_root, runtime)
        if forward_request(name, request):
            wait_until_ready(runtime, name)
            return 0
        host = EditorDesktop(paths.app_root, runtime)
        if not host.start(request):
            if forward_request(name, request, timeout=8000):
                wait_until_ready(runtime, name)
                return 0
            raise RuntimeError("The editor is already starting or closing. Try again in a moment.")
        host.show()
        return app.exec()
    except Exception as exc:
        message = f"{exc}\n\nSee {runtime / 'desktop.log'}"
        try:
            runtime.mkdir(parents=True, exist_ok=True)
            with (runtime / "desktop.log").open("a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
            report = runtime / f"desktop-startup-error.{os.getpid()}.tmp"
            report.write_text(json.dumps({"pid": os.getpid(), "error": str(exc)[:2000]}), encoding="utf-8")
            report.replace(runtime / "desktop-startup-error.json")
        except OSError:
            pass
        if not args.from_kfps:
            if app is not None:
                QMessageBox.critical(None, "KFPS Editor could not start", message)
            elif os.name == "nt":
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message, "KFPS Editor could not start", 0x10)
        return 1
    finally:
        if host is not None:
            host.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
