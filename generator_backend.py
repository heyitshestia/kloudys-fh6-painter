import hashlib
import re
import sys
from pathlib import Path

from geometry_json import drawable_shape_count


ROOT = Path(__file__).resolve().parent
SETTINGS_DIR = ROOT / "settings"
ACTIVE_PRESET_DIR = SETTINGS_DIR / "_archive_legacy_2026-05-22"
GENERATOR_EXE = ROOT / "forza_generator_v2.py"
RAW_GENERATOR_EXE = ROOT / "forza-painter-geometrize-go.exe"
PREVIEW_DIR = ROOT / "runtime" / "previews"
CUSTOM_SETTINGS_DIR = ROOT / "runtime" / "custom-settings"
GENERATED_ROOT = ROOT / "imgs" / "generated"


SETTING_KEYS = (
    "description",
    "detailMode",
    "maxPreviewSize",
    "maxResolution",
    "maxThreads",
    "mutatedSamples",
    "forceOpaqueShapes",
    "posterizeLevels",
    "previewEvery",
    "randomSamples",
    "saveAt",
    "saveEvery",
    "shapeMode",
    "stopAt",
    "useWorkGroupEval",
    "v2PreprocessMode",
    "v2EnableRepair",
)


def setting_description(path):
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("description"):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def parse_settings(path):
    values = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def load_settings():
    profiles = []
    preset_dir = ACTIVE_PRESET_DIR if ACTIVE_PRESET_DIR.exists() else SETTINGS_DIR
    paths = [path for path in sorted(preset_dir.glob("*.ini")) if not path.name.startswith("_")]
    for path in paths:
        name = re.sub(r"^[a-z0-9]+[.)]\s*", "", path.stem, flags=re.IGNORECASE)
        name = name.replace(" - ", " / ")
        name = name.replace("-", " ")
        name = re.sub(r"\s+", " ", name).strip()
        values = parse_settings(path)
        profiles.append({
            "path": path,
            "name": name,
            "description": setting_description(path),
            "values": values,
        })
    profiles.sort(key=lambda item: item["path"].name.lower())
    for index, item in enumerate(profiles, start=1):
        item["index"] = index
        item["label"] = f"{index}. {item['name']}"
    return profiles


def write_custom_settings(base_setting, custom_values):
    values = dict(parse_settings(base_setting["path"]))
    for key, value in custom_values.items():
        value = str(value).strip()
        if value:
            values[key] = value
    CUSTOM_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = CUSTOM_SETTINGS_DIR / "custom.ini"
    lines = ["description = Custom UI settings"]
    written = {"description"}
    for key in SETTING_KEYS:
        if key in values and key not in written:
            lines.append(f"{key} = {values[key]}")
            written.add(key)
    for key, value in values.items():
        if key not in written:
            lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    setting = dict(base_setting)
    setting["path"] = path
    setting["label"] = f"{base_setting.get('label', 'Custom')} + overrides"
    setting["description"] = "Custom UI settings"
    setting["values"] = values
    return setting


def generated_jsons(image_path):
    image_path = Path(image_path)
    candidates = []
    folder = generator_output_dir(image_path)
    if folder.exists():
        candidates.extend(folder.rglob("*.json"))
    legacy_folder = image_path.parent / image_path.stem
    if legacy_folder.exists():
        candidates.extend(legacy_folder.rglob("*.json"))
    candidates.extend(image_path.parent.glob(f"{image_path.stem}*.json"))
    filtered = []
    for path in candidates:
        name = path.name
        if ".v2.report." in name or ".v2.settings." in name or ".v2.preprocess." in name or ".fh6." in name:
            continue
        filtered.append(path)
    return sorted(set(filtered), key=lambda path: path.stat().st_mtime, reverse=True)


def geometry_shape_count(path):
    return drawable_shape_count(path)


def best_geometry_jsons(paths):
    best_by_stem = {}
    for path in paths:
        path = Path(path)
        base_name = re.sub(r"\.v2\.final\.\d+$", "", path.stem)
        base_name = re.sub(r"\.\d+v2$", "", base_name)
        base_name = re.sub(r"\.v2$", "", base_name)
        base_name = re.sub(r"\.\d+$", "", base_name)
        key = str(path.with_name(base_name).resolve()).lower()
        lower_name = path.name.lower()
        is_v2_final = 1 if ".v2.final." in lower_name or re.search(r"\.\d+v2\.json$", lower_name) or lower_name.endswith(".v2.json") else 0
        score = (is_v2_final, geometry_shape_count(path), path.stat().st_mtime)
        current = best_by_stem.get(key)
        if current is None or score > current[0]:
            best_by_stem[key] = (score, path)
    return [item[1] for item in sorted(best_by_stem.values(), key=lambda item: item[1].stat().st_mtime, reverse=True)]


def generator_preview_path(image_path):
    image_path = Path(image_path)
    return generator_output_dir(image_path) / f"{image_path.stem}.preview.png"


def generated_preview_files(image_path):
    image_path = Path(image_path)
    candidates = []
    folder = generator_output_dir(image_path)
    if folder.exists():
        candidates.extend(folder.glob(f"{image_path.stem}.preview*.png"))
        candidates.extend(folder.glob(f"{image_path.stem}.v2.final.*.preview.png"))
    legacy_folder = image_path.parent / image_path.stem
    if legacy_folder.exists():
        candidates.extend(legacy_folder.glob(f"{image_path.stem}.preview*.png"))
        candidates.extend(legacy_folder.glob(f"{image_path.stem}.v2.final.*.preview.png"))
    candidates.extend(image_path.parent.glob(f"{image_path.stem}.preview*.png"))
    filtered = [path for path in candidates if ".v2.preprocess." not in path.name]
    return sorted(set(filtered), key=lambda path: path.stat().st_mtime, reverse=True)


def generator_output_base(image_path):
    image_path = Path(image_path)
    return image_path.with_suffix("")


def generator_output_dir(image_path):
    image_path = Path(image_path)
    digest = hashlib.sha1(str(image_path.resolve()).encode("utf-8", errors="replace")).hexdigest()[:8]
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", image_path.stem).strip("._") or "image"
    return GENERATED_ROOT / f"{safe_stem}-{digest}"


def generator_stop_request_path(image_path):
    return generator_output_dir(image_path) / ".v2-stop"


def cleanup_generated_outputs(image_path):
    image_path = Path(image_path)
    folder = generator_output_dir(image_path)
    if not folder.exists():
        return
    patterns = (
        f"{image_path.stem}*.json",
        f"{image_path.stem}*.png",
        f"{image_path.stem}*.ini",
    )
    for pattern in patterns:
        for path in folder.glob(pattern):
            try:
                path.unlink()
            except OSError:
                pass
    stop_path = generator_stop_request_path(image_path)
    if stop_path.exists():
        try:
            stop_path.unlink()
        except OSError:
            pass


def build_generator_command(image_path, setting, enable_repair=False):
    image_path = Path(image_path)
    values = setting.get("values", {})
    target_shapes = str(values.get("stopAt", "3000"))
    preprocess_mode = values.get("v2PreprocessMode", "none")
    setting_repair = str(values.get("v2EnableRepair", "false")).strip().lower() in ("1", "true", "yes", "on")
    cmd = [
        sys.executable,
        "-u",
        str(GENERATOR_EXE),
        str(image_path),
        "--settings",
        str(setting["path"]),
        "--out-dir",
        str(generator_output_dir(image_path)),
        "--target-shapes",
        target_shapes,
        "--stop-file",
        str(generator_stop_request_path(image_path)),
        "--preprocess-mode",
        preprocess_mode,
    ]
    if enable_repair or setting_repair:
        cmd.append("--enable-repair")
    else:
        cmd.append("--disable-refine")
    return cmd
