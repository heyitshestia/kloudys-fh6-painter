# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).resolve().parents[1]
ui = root / "KFPS.UI"
icon = root / "assets" / "kfps-logo.ico"

datas = [
    (str(ui / "qml"), "KFPS.UI/qml"),
    (str(ui / "assets"), "KFPS.UI/assets"),
    (str(ui / "bridges"), "KFPS.UI/bridges"),
]
hiddenimports = (
    collect_submodules("PySide6.QtQml")
    + collect_submodules("PySide6.QtQuick")
    + collect_submodules("PySide6.QtQuickControls2")
    + ["PIL", "numpy", "cv2", "psutil"]
)

a = Analysis(
    [str(ui / "app.py")],
    pathex=[str(root), str(ui / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="KFPS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon.exists() else None,
)
