"""Independent entry point for the KFPS Vinyl Editor."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(UI_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="KFPS Vinyl Editor")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--mode", choices=("activate", "new", "json", "tutorial"), default="activate")
    parser.add_argument("--runtime-root", type=Path, help="Editor data directory; defaults to the installation runtime/fabric-editor directory.")
    args = parser.parse_args()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from kfps_ui.app_paths import AppPaths
    from kfps_ui.source_download_guard import evaluate_source_download_guard
    from kfps_ui.editor_desktop import EditorDesktop, forward_request, instance_name, validate_request

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("KFPS Vinyl Editor")
    app.setOrganizationName("KFPS")
    paths = AppPaths.discover()
    if evaluate_source_download_guard(paths.app_root).blocked:
        QMessageBox.critical(None, "KFPS Editor could not start", "GitHub source downloads are not runnable releases. Use a complete KFPS installation.")
        return 2
    runtime = (args.runtime_root or paths.runtime_root / "fabric-editor").resolve()
    request = validate_request({"project": args.project_id, "mode": args.mode})
    name = instance_name(paths.app_root, runtime)
    if forward_request(name, request):
        return 0
    host = None
    try:
        host = EditorDesktop(paths.app_root, runtime)
        if not host.start(request):
            if forward_request(name, request, timeout=8000):
                return 0
            raise RuntimeError("The editor is already starting or closing. Try again in a moment.")
        host.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "KFPS Editor could not start", str(exc))
        return 1
    finally:
        if host is not None:
            host.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
