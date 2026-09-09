"""Keep an installation unchanged while its independent editor is open."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def updater_state_root(app_root: Path) -> Path:
    root = app_root.resolve()
    if root.name.lower() == "kloudysfh6painter":
        root = root.parent
    identity = root.as_posix()
    if os.name == "nt":
        identity = identity.lower()
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path(os.environ["LOCALAPPDATA"]) / "KloudysFH6Painter" / "updater" / "installations" / digest


def acquire_update_guard(state_root: Path):
    import win32con
    import win32file
    import pywintypes

    state_root.mkdir(parents=True, exist_ok=True)
    try:
        handle = win32file.CreateFile(
            str(state_root / "updater.lock"),
            win32con.GENERIC_READ | win32con.GENERIC_WRITE, 0, None,
            win32con.OPEN_ALWAYS,
            win32con.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
    except pywintypes.error as exc:
        if exc.winerror in {32, 33}:
            raise RuntimeError("KFPS is updating. Finish the update before opening the editor.") from exc
        raise
    try:
        info = win32file.GetFileInformationByHandle(handle)
        if info[0] & (win32con.FILE_ATTRIBUTE_REPARSE_POINT | win32con.FILE_ATTRIBUTE_DIRECTORY) or info[7] != 1:
            raise RuntimeError("The updater lock is not a regular, single-link file.")
        return handle
    except Exception:
        handle.Close()
        raise
