from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget


ROOT = Path(__file__).resolve().parent
REPO_OWNER = "heyitshestia"
REPO_NAME = "kloudys-fh6-painter"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
BRANCH = "main"
GITHUB_VERSION_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/VERSION?ref={BRANCH}"
PYTHON_SETUP = ROOT / "01_add_python312_to_path.bat"
DEPENDENCY_SETUP = ROOT / "02_install_dependencies.bat"
APP_ENTRY = ROOT / "app_qt.py"
UPDATE_BAT = ROOT / "03_update_from_github.bat"
EMBEDDED_PYTHON = ROOT / "python" / "python.exe"
STANDALONE_FOLDER_NAME = "KloudysFH6Painter"
LAUNCHER_EXE_NAME = "Kloudys Painter Launcher.exe"
OLD_LAUNCHER_EXE_NAME = "Kloudys Painter.exe"


class Bus(QObject):
    status = Signal(str, str)
    log = Signal(str)
    busy = Signal(bool)


def run_command(cmd, cwd=ROOT, env_extra=None):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        env=env,
    )
    lines = []
    for line in proc.stdout:
        lines.append(line.rstrip())
    return proc.wait(), lines


def sync_standalone_launcher_exe() -> list[str]:
    """Let one updater run migrate the parent launcher exe without manual copying."""
    messages: list[str] = []
    if os.name != "nt" or ROOT.name.lower() != STANDALONE_FOLDER_NAME.lower():
        return messages
    inner_new = ROOT / LAUNCHER_EXE_NAME
    parent_new = ROOT.parent / LAUNCHER_EXE_NAME
    parent_old = ROOT.parent / OLD_LAUNCHER_EXE_NAME
    if inner_new.exists():
        try:
            shutil.copy2(inner_new, parent_new)
            inner_new.unlink()
            messages.append(f"Standalone launcher synced: {parent_new.name}")
        except OSError as exc:
            messages.append(f"Standalone launcher sync skipped: {exc}")
    if parent_new.exists() and parent_old.exists():
        try:
            parent_old.unlink()
            messages.append(f"Removed old launcher name: {parent_old.name}")
        except OSError:
            messages.append(f"Old launcher still exists because it is probably running: {parent_old.name}")
    return messages


def git_output(*args: str) -> str | None:
    if not (ROOT / ".git").exists():
        return None
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True, timeout=8).strip()
    except Exception:
        return None


def local_version() -> tuple[str, str]:
    try:
        text = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        text = "unknown"
    return text, text


def versions_match(local_value: str, remote_value: str) -> bool:
    local_value = str(local_value or "").strip().lower()
    remote_value = str(remote_value or "").strip().lower()
    if not local_value or local_value == "unknown" or not remote_value:
        return False
    return local_value == remote_value


def remote_version() -> tuple[str, str, str]:
    request = urllib.request.Request(
        GITHUB_VERSION_API,
        headers={
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "User-Agent": "KloudysFH6Painter",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    version = base64.b64decode(str(payload.get("content", ""))).decode("utf-8", errors="replace").strip()
    return version, version, ""


def find_python312() -> list[str] | None:
    candidates = [
        [str(EMBEDDED_PYTHON)],
        ["py", "-3.12"],
        ["python"],
        [str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe")],
    ]
    for cmd in candidates:
        exe = cmd[0]
        if not exe or (exe.endswith(".exe") and not Path(exe).exists()):
            continue
        try:
            subprocess.check_call(
                cmd + ["-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return cmd
        except Exception:
            continue
    return None


def dependencies_ok() -> tuple[bool, str]:
    python_cmd = find_python312()
    if not python_cmd:
        return False, "Python 3.12 was not found."
    try:
        subprocess.check_call(
            python_cmd + ["-c", "import PySide6, psutil, win32api, cv2, numpy, PIL; print('ok')"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, "Python 3.12 and dependencies are installed."
    except Exception:
        return False, "Python 3.12 is present, but dependencies are missing."


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kloudy's Painter Launcher")
        self.resize(920, 620)
        self.launcher_migration_messages = sync_standalone_launcher_exe()
        self.bus = Bus()
        self.bus.status.connect(self.set_status)
        self.bus.log.connect(self.log)
        self.bus.busy.connect(self.set_busy)
        self.update_available = False
        self.remote_full = None
        self._build()
        self.apply_theme()
        for message in self.launcher_migration_messages:
            self.log(message)
        self.refresh_status()

    def _build(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("Kloudy's Painter Launcher")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.status = QLabel("Checking install and update status...")
        self.status.setObjectName("statusNeutral")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.info = QLabel(
            "Fresh install: click Setup Python, then Install Dependencies, then Launch App.\n"
            "Updates: click Check Updates. If red update text appears, click Update."
        )
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        actions = QHBoxLayout()
        self.setup_python_btn = QPushButton("1. Setup Python")
        self.setup_python_btn.clicked.connect(lambda: self.run_batch(PYTHON_SETUP, "Python setup"))
        self.install_deps_btn = QPushButton("2. Install Dependencies")
        self.install_deps_btn.clicked.connect(lambda: self.run_batch(DEPENDENCY_SETUP, "Dependency install"))
        self.check_btn = QPushButton("Check Updates")
        self.check_btn.clicked.connect(self.refresh_status)
        self.update_btn = QPushButton("Update")
        self.update_btn.setObjectName("dangerButton")
        self.update_btn.clicked.connect(self.run_update)
        self.launch_btn = QPushButton("➜ Launch App")
        self.launch_btn.setObjectName("primaryButton")
        self.launch_btn.clicked.connect(self.launch_app)
        for button in (self.setup_python_btn, self.install_deps_btn, self.check_btn, self.update_btn, self.launch_btn):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box, 1)
        self.setCentralWidget(root)

    def apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5edff; color: #3b244d; font-family: "Segoe UI"; font-size: 11pt; }
            QLabel#title { font-size: 30pt; font-weight: 800; color: #6c3fa0; padding: 18px; }
            QLabel#statusNeutral { background: #fff8fb; border: 2px solid #d8c2f0; border-radius: 18px; padding: 22px; font-size: 18pt; font-weight: 800; }
            QLabel#statusGood { background: #efffee; color: #157c32; border: 3px solid #52b86a; border-radius: 18px; padding: 22px; font-size: 20pt; font-weight: 900; }
            QLabel#statusBad { background: #ffecec; color: #c00000; border: 4px solid #e02020; border-radius: 18px; padding: 22px; font-size: 22pt; font-weight: 1000; }
            QPushButton { background: #eadcff; color: #3b244d; border: 1px solid #c7a8ea; border-radius: 12px; padding: 12px; font-weight: 700; }
            QPushButton:hover { background: #dfc9ff; }
            QPushButton#primaryButton { background: #42a85b; color: white; font-size: 13pt; }
            QPushButton#dangerButton { background: #dc2626; color: white; font-size: 13pt; }
            QTextEdit { background: #fffdf8; border: 1px solid #d8c2f0; border-radius: 12px; padding: 8px; }
            """
        )

    def set_busy(self, busy: bool):
        for button in (self.setup_python_btn, self.install_deps_btn, self.check_btn, self.update_btn, self.launch_btn):
            button.setEnabled(not busy)

    def log(self, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{stamp}] {text}")

    def set_status(self, text: str, mode: str):
        self.status.setText(text)
        self.status.setObjectName({"good": "statusGood", "bad": "statusBad"}.get(mode, "statusNeutral"))
        self.apply_theme()

    def refresh_status(self):
        threading.Thread(target=self._refresh_status_worker, daemon=True).start()

    def _refresh_status_worker(self):
        self.bus.busy.emit(True)
        try:
            local_short, local_full = local_version()
            self.bus.log.emit(f"Local version: {local_short}")
            dep_ok, dep_message = dependencies_ok()
            self.bus.log.emit(dep_message)
            try:
                remote_short, remote_full, remote_date = remote_version()
                self.remote_full = remote_full
                self.bus.log.emit(f"GitHub main version: {remote_short}")
                if not versions_match(local_full, remote_full):
                    self.update_available = True
                    self.bus.status.emit(
                        f"UPDATE AVAILABLE!\nLocal: {local_short}  ->  GitHub main: {remote_short}\nClick Update.",
                        "bad",
                    )
                    return
            except Exception as exc:
                self.bus.log.emit(f"Update check failed: {exc}")
                self.bus.status.emit(f"Could not check GitHub updates.\n{dep_message}", "bad" if not dep_ok else "neutral")
                return
            if dep_ok:
                self.update_available = False
                self.bus.status.emit("Everything is up to date :)  ➜ Click Launch App", "good")
            else:
                self.bus.status.emit(f"Fresh install setup needed.\n{dep_message}\nRun Setup Python, then Install Dependencies.", "bad")
        finally:
            self.bus.busy.emit(False)

    def run_batch(self, path: Path, label: str):
        if not path.exists():
            QMessageBox.critical(self, label, f"Missing file:\n{path}")
            return
        threading.Thread(target=self._run_batch_worker, args=(path, label), daemon=True).start()

    def _run_batch_worker(self, path: Path, label: str):
        self.bus.busy.emit(True)
        self.bus.log.emit(f"Starting {label}...")
        try:
            if os.name == "nt":
                code, lines = run_command(["cmd", "/c", str(path)], env_extra={"FORZA_PAINTER_NO_PAUSE": "1"})
            else:
                code, lines = run_command(["bash", "-lc", f"echo Windows batch file: {path.name}"])
            for line in lines:
                if line:
                    self.bus.log.emit(line)
            self.bus.log.emit(f"{label} exited with code {code}.")
        finally:
            self.bus.busy.emit(False)
            self.refresh_status()

    def run_update(self):
        if QMessageBox.question(
            self,
            "Update",
            "This will update app files from GitHub main and preserve generated/runtime data.\n\nContinue?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.log("Starting GitHub update.")
        if os.name == "nt" and UPDATE_BAT.exists():
            threading.Thread(target=self._update_bat_worker, daemon=True).start()
            return
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_bat_worker(self):
        self.bus.busy.emit(True)
        self.bus.log.emit("Starting updater batch...")
        try:
            code, lines = run_command(["cmd", "/c", str(UPDATE_BAT)], env_extra={"FORZA_PAINTER_NO_PAUSE": "1"})
            for line in lines:
                if line:
                    self.bus.log.emit(line)
            self.bus.log.emit(f"Update exited with code {code}.")
        finally:
            self.bus.busy.emit(False)
            self.refresh_status()

    def _update_worker(self):
        self.bus.busy.emit(True)
        self.bus.log.emit("Starting GitHub update...")
        try:
            code, lines = self.sync_with_git()
            for line in lines:
                if line:
                    self.bus.log.emit(line)
            self.bus.log.emit(f"Update exited with code {code}.")
        finally:
            self.bus.busy.emit(False)
            self.refresh_status()

    def sync_with_git(self):
        if not shutil.which("git"):
            return 1, ["Git was not found. Run 03_update_from_github.bat on Windows so PortableGit can be installed."]
        if (ROOT / ".git").exists():
            lines = []
            for cmd in (["git", "fetch", "origin", BRANCH], ["git", "reset", "--hard", f"origin/{BRANCH}"]):
                code, out = run_command(cmd)
                lines.extend(out)
                if code != 0:
                    return code, lines
            lines.extend(self.post_update_cleanup())
            return 0, lines
        return 1, ["This folder is not a Git checkout. Use 03_update_from_github.bat for first sync."]

    def post_update_cleanup(self) -> list[str]:
        lines = []
        for path in (
            ROOT / "settings" / "_archive_legacy_2026-05-22",
            ROOT / "settings" / "_default.ini",
        ):
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                    lines.append(f"Removed retired folder: {path.name}")
                elif path.exists():
                    path.unlink()
                    lines.append(f"Removed retired file: {path.name}")
            except OSError as exc:
                lines.append(f"Could not remove retired path {path}: {exc}")
        lines.extend(sync_standalone_launcher_exe())
        return lines

    def launch_app(self):
        dep_ok, dep_message = dependencies_ok()
        if not dep_ok:
            QMessageBox.warning(self, "Setup needed", f"{dep_message}\n\nRun Setup Python and Install Dependencies first.")
            self.refresh_status()
            return
        python_cmd = find_python312()
        if not python_cmd:
            QMessageBox.warning(self, "Setup needed", "Python 3.12 was not found.")
            return
        try:
            flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
            subprocess.Popen(python_cmd + [str(APP_ENTRY)], cwd=ROOT, creationflags=flags)
            self.log("Launched app.")
            QTimer.singleShot(500, self.close)
        except Exception as exc:
            QMessageBox.critical(self, "Launch failed", str(exc))


def main() -> int:
    app = QApplication(sys.argv)
    window = Launcher()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
