from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path, PurePosixPath

from PySide6.QtNetwork import QLocalSocket


def instance_name(app_root: Path, runtime: Path) -> str:
    identity = f"{app_root.resolve()}\0{runtime.resolve()}"
    if os.name == "nt":
        identity = identity.casefold()
    return "kfps-editor-" + hashlib.sha256(identity.encode()).hexdigest()[:32]


def validate_request(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"project", "mode"}:
        raise ValueError("Invalid editor launch request.")
    project = payload.get("project", "")
    mode = payload.get("mode", "activate")
    if not isinstance(project, str) or len(project) > 2048 or "\\" in project or ":" in project:
        raise ValueError("Invalid editor project path.")
    path = PurePosixPath(project)
    if project and (path.is_absolute() or ".." in path.parts or "\x00" in project or not project.endswith(".fabric-project.json")):
        raise ValueError("The requested project must be inside the editor project folder.")
    if not isinstance(mode, str) or mode not in {"activate", "new", "json", "tutorial"}:
        raise ValueError("Invalid editor launch mode.")
    return {"project": project, "mode": mode}


def forward_request(name: str, request: dict, timeout: int = 800) -> bool:
    payload = json.dumps(validate_request(request)).encode() + b"\n"
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(min(250, timeout)):
            socket.write(payload)
            socket.flush()
            result = bytearray()
            while time.monotonic() < deadline:
                if socket.bytesAvailable() or socket.waitForReadyRead(200):
                    result.extend(bytes(socket.readAll()))
                    if len(result) > 64:
                        socket.abort()
                        return False
                    if b"\n" in result:
                        socket.disconnectFromServer()
                        return bytes(result).strip() == b"ok"
            socket.abort()
            return False
        socket.abort()
        if timeout <= 800:
            return False
        time.sleep(0.1)
    return False


def editor_is_open(paths) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(instance_name(paths.app_root, paths.runtime_root / "fabric-editor"))
    connected = socket.waitForConnected(150)
    socket.abort()
    return connected


def launch_editor(paths, project: str = "", mode: str = "activate", cancelled=None) -> str:
    request = validate_request({"project": project, "mode": mode or "activate"})
    runtime = paths.runtime_root / "fabric-editor"
    name = instance_name(paths.app_root, runtime)
    if forward_request(name, request):
        return "Connected to the open editor window."
    if cancelled is not None and cancelled.is_set():
        return "Editor launch cancelled."
    entry = paths.app_root / "KFPS.UI" / "editor.py"
    if not entry.is_file():
        raise FileNotFoundError(f"Editor launcher not found: {entry}")
    runtime.mkdir(parents=True, exist_ok=True)
    log_path = runtime / "desktop.log"
    args = [paths.python_executable, str(entry), "--runtime-root", str(runtime), "--mode", request["mode"]]
    if project:
        args.extend(["--project-id", project])
    env = os.environ.copy()
    env["KFPS_APP_ROOT"] = str(paths.app_root)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with log_path.open("a", encoding="utf-8") as stream:
        process = subprocess.Popen(args, cwd=paths.app_root, env=env, creationflags=flags, close_fds=True, stdout=stream, stderr=stream)
    # The new process receives the opening request on its command line. Only ping
    # for activation here, so startup cannot open the same document twice.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if cancelled is not None and cancelled.is_set():
            return "Editor continues independently."
        if process.poll() is not None and process.returncode != 0:
            break
        if forward_request(name, {"mode": "activate", "project": ""}, timeout=300):
            return "Editor window started independently of KFPS."
        time.sleep(0.12)
    raise RuntimeError(f"The editor did not respond. See {log_path}")
