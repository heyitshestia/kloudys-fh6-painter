from __future__ import annotations

import os
import re
import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST_ROOT = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "dev"
SAFE_VERSION = re.sub(r"[^A-Za-z0-9._-]+", "-", VERSION)
STAGE = DIST_ROOT / f"release-{SAFE_VERSION}"
APP_DIR = STAGE / "KloudysFH6Painter"
IMAGES_DIR = STAGE / "Images"
ZIP_PATH = DIST_ROOT / f"Kloudys-FH6-Painter-{SAFE_VERSION}.zip"

PROJECT_ITEMS = [
    ".gitattributes",
    ".gitignore",
    "00_launcher.bat",
    "01_add_python312_to_path.bat",
    "02_install_dependencies.bat",
    "03_update_from_github.bat",
    "04_start_app.bat",
    "05_check_environment.bat",
    "99_clean_runtime_data.bat",
    "update_from_github.bat",
    "README.md",
    "README.zh-CN.md",
    "CHANGELOG.md",
    "VERSION",
    "LICENSE",
    "LICENSE.custom-importer",
    "LICENSE.geometrize-gpu",
    "requirements.txt",
    "requirements-preview.txt",
    "app.py",
    "app_qt.py",
    "launcher_qt.py",
    "generator_backend.py",
    "forza_generator_v2.py",
    "KloudysGalateaGenesis.exe",
    "geometry_json.py",
    "game_profiles.py",
    "internal_classes.py",
    "main.py",
    "fh6_probe.py",
    "fh6_group1000_probe.py",
    "fh6_export_typecode_json.py",
    "fh6_import_typecode_json.py",
    "fh6_trim_group_count.py",
    "fh6_shape_experiment.py",
    "fh6_shape_experiment_remote.py",
    "native.py",
    "version_info.py",
    "make_release.ps1",
    "make_release.py",
    "docs",
    "assets",
    "data",
    "settings",
    "tools",
]

OPTIONAL_ITEMS = ["python"]
BLOCKED_PARTS = {".git", "runtime", "__pycache__", "dist", "build"}
BLOCKED_GENERATED = (Path("imgs") / "generated").parts
BLOCKED_WEBUI = ("webui-data",)
BLOCKED_DEVELOPMENT_DOCS = ("docs", "development")


def copy_item(relative: str) -> None:
    source = ROOT / relative
    if not source.exists():
        print(f"warning: skipping missing item: {relative}")
        return
    destination = APP_DIR / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore_blocked)
    else:
        shutil.copy2(source, destination)
        normalize_release_text(destination)


def normalize_release_text(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in {".bat", ".cmd", ".ps1", ".ini"}:
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n"), encoding="utf-8", newline="")


def ignore_blocked(directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        path = Path(directory) / name
        rel_parts = relative_parts(path)
        if (
            name in BLOCKED_PARTS
            or rel_parts[:2] == BLOCKED_GENERATED
            or rel_parts[:1] == BLOCKED_WEBUI
            or rel_parts[:2] == BLOCKED_DEVELOPMENT_DOCS
        ):
            ignored.add(name)
    return ignored


def relative_parts(path: Path) -> tuple[str, ...]:
    try:
        return path.resolve().relative_to(ROOT).parts
    except ValueError:
        return ()


def verify_stage() -> None:
    required = [
        STAGE / "Kloudys Painter Launcher.exe",
        IMAGES_DIR / "PUT_SOURCE_IMAGES_HERE.txt",
        APP_DIR / "00_launcher.bat",
        APP_DIR / "03_update_from_github.bat",
        APP_DIR / "app_qt.py",
        APP_DIR / "forza_generator_v2.py",
        APP_DIR / "KloudysGalateaGenesis.exe",
        APP_DIR / "fh6_probe.py",
        APP_DIR / "fh6_export_typecode_json.py",
        APP_DIR / "fh6_import_typecode_json.py",
        APP_DIR / "fh6_trim_group_count.py",
        APP_DIR / "assets" / "app" / "project-integrity.marker",
        APP_DIR / "settings" / "a.flat-colors.ini",
        APP_DIR / "tools" / "fabric-editor" / "index.html",
        APP_DIR / "tools" / "fabric-editor" / "editor.js",
        APP_DIR / "tools" / "fabric-editor" / "vendor" / "fabric.min.js",
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"release verification failed: missing {path}")
    verify_launcher_executable(STAGE / "Kloudys Painter Launcher.exe")
    for path in STAGE.rglob("*"):
        rel = path.relative_to(STAGE).parts
        if any(part in BLOCKED_PARTS for part in rel):
            raise RuntimeError(f"release verification failed: blocked path staged: {path}")
        if rel[:3] == ("KloudysFH6Painter", "imgs", "generated"):
            raise RuntimeError(f"release verification failed: generated output staged: {path}")
        if rel[:2] == ("KloudysFH6Painter", "webui-data"):
            raise RuntimeError(f"release verification failed: probe data staged: {path}")
        if rel[:3] == ("KloudysFH6Painter", "docs", "development"):
            raise RuntimeError(f"release verification failed: development docs staged: {path}")
    verify_updater_batch(APP_DIR / "03_update_from_github.bat")
    verify_updater_batch(APP_DIR / "update_from_github.bat")


def verify_launcher_executable(path: Path) -> None:
    data = path.read_bytes()
    forbidden = [
        b"PyInstaller",
        b"_MEIPASS",
        b"Failed to remove temporary directory",
        b"pyi-runtime-tmpdir",
    ]
    hits = [marker.decode("ascii", errors="replace") for marker in forbidden if marker in data]
    if hits:
        raise RuntimeError(
            "release verification failed: launcher is still a PyInstaller one-file executable "
            f"({', '.join(hits)}). Rebuild tools/native-launcher before packaging."
        )


def verify_updater_batch(path: Path) -> None:
    data = path.read_bytes()
    if b"\r\n" not in data or data.count(b"\n") != data.count(b"\r\n"):
        raise RuntimeError(f"release verification failed: updater is not CRLF-normalized: {path}")
    text = data.decode("utf-8", errors="replace").lower()
    for label in (":backup_existing_files", ":write_build_commit", ":ensure_git", ":cleanup_retired_files"):
        if label not in text:
            raise RuntimeError(f"release verification failed: updater label missing {label}: {path}")


def zip_stage() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(STAGE).as_posix())
    with zipfile.ZipFile(ZIP_PATH, "r") as archive:
        names = set(archive.namelist())
        required = {
            "Kloudys Painter Launcher.exe",
            "Images/PUT_SOURCE_IMAGES_HERE.txt",
            "KloudysFH6Painter/00_launcher.bat",
            "KloudysFH6Painter/03_update_from_github.bat",
            "KloudysFH6Painter/app_qt.py",
            "KloudysFH6Painter/forza_generator_v2.py",
            "KloudysFH6Painter/KloudysGalateaGenesis.exe",
            "KloudysFH6Painter/fh6_probe.py",
            "KloudysFH6Painter/fh6_export_typecode_json.py",
            "KloudysFH6Painter/fh6_import_typecode_json.py",
            "KloudysFH6Painter/fh6_trim_group_count.py",
            "KloudysFH6Painter/assets/app/project-integrity.marker",
            "KloudysFH6Painter/settings/a.flat-colors.ini",
            "KloudysFH6Painter/tools/fabric-editor/index.html",
            "KloudysFH6Painter/tools/fabric-editor/editor.js",
            "KloudysFH6Painter/tools/fabric-editor/vendor/fabric.min.js",
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"release verification failed: missing from zip: {missing}")
        for name in names:
            lowered = name.lower()
            if "/runtime/" in lowered or "/imgs/generated/" in lowered or "/webui-data/" in lowered or "/__pycache__/" in lowered:
                raise RuntimeError(f"release verification failed: blocked path in zip: {name}")
            if "/docs/development/" in lowered:
                raise RuntimeError(f"release verification failed: development docs in zip: {name}")


def main() -> int:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    (IMAGES_DIR / "PUT_SOURCE_IMAGES_HERE.txt").write_text(
        "Drop source images here. The app's Choose source image button opens this folder first.\n",
        encoding="utf-8",
    )
    launcher = ROOT / "Kloudys Painter Launcher.exe"
    if not launcher.exists():
        raise RuntimeError(f"missing launcher executable: {launcher}")
    shutil.copy2(launcher, STAGE / "Kloudys Painter Launcher.exe")
    for item in PROJECT_ITEMS:
        copy_item(item)
    for item in OPTIONAL_ITEMS:
        if (ROOT / item).exists():
            copy_item(item)
    verify_stage()
    zip_stage()
    print(f"Release package written to {ZIP_PATH}")
    print("Verified: launcher, app folder, required files, and no generated/runtime data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
