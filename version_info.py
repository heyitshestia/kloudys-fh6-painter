from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "VERSION"


def _git_output(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.5,
        ).strip()
    except Exception:
        return None


def get_version() -> str:
    sha = _git_output("rev-parse", "--short=8", "HEAD")
    if sha:
        branch = _git_output("rev-parse", "--abbrev-ref", "HEAD") or "detached"
        date = _git_output("log", "-1", "--format=%cd", "--date=short") or ""
        dirty = _git_output("status", "--porcelain")
        suffix = " dirty" if dirty else ""
        date_part = f" {date}" if date else ""
        return f"{branch}@{sha}{date_part}{suffix}"

    try:
        fallback = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        fallback = ""
    return fallback or "unknown"


def get_version_label() -> str:
    return f"Version: {get_version()}"

