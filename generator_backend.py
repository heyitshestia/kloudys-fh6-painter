import hashlib
import json
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


def sorted_settings(values):
    return {key: values[key] for key in sorted(values)}


def load_settings():
    profiles = []
    preset_dir = ACTIVE_PRESET_DIR if ACTIVE_PRESET_DIR.exists() else SETTINGS_DIR
    paths = [path for path in sorted(preset_dir.glob("*.ini")) if not path.name.startswith("_")]
    for path in paths:
        name = re.sub(r"^[a-z0-9]+[.)]\s*", "", path.stem, flags=re.IGNORECASE)
        name = name.replace(" - ", " / ")
        name = name.replace("-", " ")
        name = re.sub(r"\s+", " ", name).strip()
        values = sorted_settings(parse_settings(path))
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
    values = sorted_settings(parse_settings(base_setting["path"]))
    applied_overrides = {}
    for key, value in custom_values.items():
        value = str(value).strip()
        if value:
            values[key] = value
            applied_overrides[key] = value
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
    setting["base_setting"] = {
        "label": base_setting.get("label"),
        "name": base_setting.get("name"),
        "description": base_setting.get("description"),
        "path": str(base_setting.get("path")),
        "values": sorted_settings(parse_settings(base_setting["path"])),
    }
    setting["ui_overrides"] = sorted_settings(applied_overrides)
    return setting


def generated_jsons(image_path):
    image_path = Path(image_path)
    candidates = []
    for folder in generator_output_dirs(image_path):
        candidates.extend(folder.rglob("*.json"))
    legacy_folder = image_path.parent / image_path.stem
    if legacy_folder.exists():
        candidates.extend(legacy_folder.rglob("*.json"))
    candidates.extend(image_path.parent.glob(f"{image_path.stem}*.json"))
    filtered = []
    for path in candidates:
        if is_internal_generator_json(path):
            continue
        filtered.append(path)
    return sorted(set(filtered), key=lambda path: path.stat().st_mtime, reverse=True)


def is_internal_generator_json(path):
    name = Path(path).name.lower()
    return (
        ".v2.report." in name
        or ".v2.settings." in name
        or ".v2.preprocess." in name
        or ".v2.run_metadata." in name
        or ".fh6." in name
    )


def geometry_shape_count(path):
    return drawable_shape_count(path)


def geometry_group_stem(path):
    path = Path(path)
    base_name = re.sub(r"\.v2\.final\.\d+$", "", path.stem)
    base_name = re.sub(r"\.\d+v2$", "", base_name)
    base_name = re.sub(r"\.v2$", "", base_name)
    base_name = re.sub(r"\.\d+$", "", base_name)
    return base_name


def generation_report_path(path):
    path = Path(path)
    return path.with_name(f"{geometry_group_stem(path)}.v2.report.json")


def import_drawable_budget(path):
    report_path = generation_report_path(path)
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for key in ("drawable_target_shapes", "target_drawable_shapes"):
        try:
            value = int(report.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        target_shapes = int(report.get("target_shapes"))
    except (TypeError, ValueError):
        return None
    if target_shapes > 4:
        return target_shapes - 4
    return target_shapes if target_shapes > 0 else None


def is_v2_output_json(path):
    lower_name = Path(path).name.lower()
    return bool(".v2.final." in lower_name or re.search(r"\.\d+v2\.json$", lower_name) or lower_name.endswith(".v2.json"))


def is_import_safe_geometry_json(path):
    budget = import_drawable_budget(path)
    if budget is None:
        return True
    return geometry_shape_count(path) <= budget


def best_geometry_jsons(paths):
    best_by_stem = {}
    for path in paths:
        path = Path(path)
        if is_internal_generator_json(path):
            continue
        if not is_import_safe_geometry_json(path):
            continue
        base_name = geometry_group_stem(path)
        key = str(path.with_name(base_name).resolve()).lower()
        is_v2_final = 1 if is_v2_output_json(path) else 0
        try:
            shape_count = geometry_shape_count(path)
        except Exception:
            continue
        score = (is_v2_final, shape_count, path.stat().st_mtime)
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
    for folder in generator_output_dirs(image_path):
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


def generator_safe_stem(image_path):
    image_path = Path(image_path)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", image_path.stem).strip("._") or "image"


def legacy_generator_output_dir(image_path):
    image_path = Path(image_path)
    digest = hashlib.sha1(str(image_path.resolve()).encode("utf-8", errors="replace")).hexdigest()[:8]
    return GENERATED_ROOT / f"{generator_safe_stem(image_path)}-{digest}"


def generator_output_dir(image_path):
    return GENERATED_ROOT / generator_safe_stem(image_path)


def generator_output_dirs(image_path):
    safe_stem = generator_safe_stem(image_path)
    candidates = []
    if GENERATED_ROOT.exists():
        for path in GENERATED_ROOT.iterdir():
            if not path.is_dir():
                continue
            name = path.name
            if name == safe_stem or re.fullmatch(re.escape(safe_stem) + r"v\d+", name):
                candidates.append(path)
            elif re.fullmatch(re.escape(safe_stem) + r"-[0-9a-f]{8}", name, flags=re.IGNORECASE):
                candidates.append(path)
    legacy = legacy_generator_output_dir(image_path)
    if legacy.exists():
        candidates.append(legacy)
    return sorted(set(candidates), key=lambda path: path.stat().st_mtime, reverse=True)


def next_generator_output_dir(image_path):
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    base = generator_output_dir(image_path)
    if not base.exists():
        return base
    safe_stem = generator_safe_stem(image_path)
    index = 2
    while True:
        candidate = GENERATED_ROOT / f"{safe_stem}v{index}"
        if not candidate.exists():
            return candidate
        index += 1


def generator_stop_request_path(image_path, output_dir=None):
    folder = Path(output_dir) if output_dir is not None else generator_output_dir(image_path)
    return folder / ".v2-stop"


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


def build_generator_command(image_path, setting, enable_repair=False, enable_overshoot=False, output_dir=None):
    image_path = Path(image_path)
    output_dir = Path(output_dir) if output_dir is not None else generator_output_dir(image_path)
    values = setting.get("values", {})
    target_shapes = str(values.get("stopAt", "3000"))
    try:
        target_count = int(target_shapes)
    except (TypeError, ValueError):
        target_count = 3000
    checkpoint_step = "250" if target_count <= 1000 else "500"
    preprocess_mode = values.get("v2PreprocessMode", "none")
    setting_repair = str(values.get("v2EnableRepair", "false")).strip().lower() in ("1", "true", "yes", "on")
    run_metadata_path = output_dir / f"{image_path.stem}.v2.run_metadata.json"
    run_metadata = {
        "selected_profile": {
            "label": setting.get("label"),
            "name": setting.get("name"),
            "description": setting.get("description"),
            "path": str(setting.get("path")),
            "values": sorted_settings(values),
        },
        "base_profile": setting.get("base_setting"),
        "ui_overrides": sorted_settings(setting.get("ui_overrides", {})),
        "effective_settings": sorted_settings(values),
        "toggles": {
            "luma_bands": str(preprocess_mode).strip().lower() == "luma_bands",
            "quality_overshoot": bool(enable_overshoot),
            "targeted_repair": bool(enable_repair or setting_repair),
        },
        "generator_command_options": {
            "target_shapes": target_shapes,
            "checkpoint_step": checkpoint_step,
            "preprocess_mode": preprocess_mode,
            "overshoot_ratio": "1.12" if enable_overshoot else "1.0",
            "overshoot_max_extra": "400" if enable_overshoot else "0",
            "repair_enabled": bool(enable_repair or setting_repair),
        },
    }
    run_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    run_metadata_path.write_text(json.dumps(run_metadata, indent=2) + "\n", encoding="utf-8")
    cmd = [
        sys.executable,
        "-u",
        str(GENERATOR_EXE),
        str(image_path),
        "--settings",
        str(setting["path"]),
        "--out-dir",
        str(output_dir),
        "--target-shapes",
        target_shapes,
        "--checkpoint-step",
        checkpoint_step,
        "--stop-file",
        str(generator_stop_request_path(image_path, output_dir)),
        "--preprocess-mode",
        preprocess_mode,
        "--run-metadata",
        str(run_metadata_path),
    ]
    if enable_overshoot:
        cmd.extend(["--overshoot-ratio", "1.12", "--overshoot-max-extra", "400"])
    if enable_repair or setting_repair:
        cmd.append("--enable-repair")
    else:
        cmd.append("--disable-refine")
    return cmd
