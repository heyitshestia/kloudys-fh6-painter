from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog

from .app_paths import AppPaths
from .log_service import LogService
from .qt_utils import open_path


class DesktopService(QObject):
    def __init__(self, paths: AppPaths, log: LogService, parent=None):
        super().__init__(parent); self.paths = paths; self.log = log

    @Slot(result=str)
    def chooseImage(self):
        initial = self.paths.app_root.parent / "Images"
        path, _ = QFileDialog.getOpenFileName(None, "Choose source image", str(initial if initial.exists() else self.paths.app_root), "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)")
        return path

    @Slot(result=str)
    def chooseJson(self):
        path, _ = QFileDialog.getOpenFileName(None, "Choose vinyl JSON", str(self.paths.app_root), "Vinyl JSON (*.json);;All files (*)")
        return path

    @Slot(str)
    def openFolder(self, value):
        try:
            open_path(Path(value)); self.log.append(f"Opened folder: {value}")
        except Exception as exc: self.log.append(f"Could not open folder: {exc}", "error")

    @Slot()
    def openRoot(self): self.openFolder(str(self.paths.app_root))
    @Slot()
    def openRuntime(self): self.openFolder(str(self.paths.runtime_root))
    @Slot()
    def openJsonFolders(self): self.openFolder(str(self.paths.app_root / "imgs"))
    @Slot()
    def openGenerated(self): self.openFolder(str(self.paths.generated_root))
    @Slot()
    def openProjects(self): self.openFolder(str(self.paths.project_root))
    @Slot()
    def openReports(self): self.openFolder(str(self.paths.runtime_root / "bug-reports"))

    @Slot(str)
    def openUrl(self, url):
        try: webbrowser.open(url); self.log.append(f"Opened: {url}")
        except Exception as exc: self.log.append(f"Could not open URL: {exc}", "error")
