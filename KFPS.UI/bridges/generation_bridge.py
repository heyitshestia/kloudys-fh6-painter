import argparse
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generator_backend import (
    auto_generation_values,
    build_generator_command,
    generated_preview_files,
    load_settings,
    next_generator_output_dir,
    write_custom_settings,
)


def parse_args():
    parser = argparse.ArgumentParser(description="KFPS headless generation bridge")
    parser.add_argument("--image", required=True)
    parser.add_argument("--preset-index", type=int, default=0)
    parser.add_argument("--layers", default="2000")
    parser.add_argument("--save-at", default="500,1000,1250,1500,2000,2500,3000")
    parser.add_argument("--luma-prep", action="store_true")
    parser.add_argument("--detail-heatmap", action="store_true")
    parser.add_argument("--edge-repair", action="store_true")
    parser.add_argument("--sample-boost", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-resolution", default="")
    parser.add_argument("--random-samples", default="")
    parser.add_argument("--mutated-samples", default="")
    return parser.parse_args()


def stream_process(proc):
    output_queue = queue.Queue()

    def reader():
        try:
            for raw_line in proc.stdout:
                output_queue.put(raw_line)
        finally:
            output_queue.put(None)

    threading.Thread(target=reader, daemon=True).start()
    finished = False
    while not finished:
        try:
            line = output_queue.get(timeout=0.15)
        except queue.Empty:
            continue
        if line is None:
            finished = True
            continue
        print(line.rstrip(), flush=True)


def main():
    args = parse_args()
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        print(f"Generator failed: missing source image: {image_path}", flush=True)
        return 2

    settings = load_settings()
    if not settings:
        print("Generator failed: no presets found.", flush=True)
        return 2

    preset_index = max(0, min(args.preset_index, len(settings) - 1))
    setting = settings[preset_index]
    base_values = dict(setting.get("values", {}))
    base_values.update(
        {
            "stopAt": str(args.layers).strip() or base_values.get("stopAt", "2000"),
            "saveAt": str(args.save_at).strip() or base_values.get("saveAt", ""),
            "v2PreprocessMode": "luma_bands" if args.luma_prep else "none",
            "v2EnableRepair": "true" if args.edge_repair else "false",
            "detailHeatmapMode": "auto" if args.detail_heatmap else "off",
            "detailHeatmapStrength": "0.10",
        }
    )

    pro_overrides = {}
    for cli_value, setting_key in (
        (args.max_resolution, "maxResolution"),
        (args.random_samples, "randomSamples"),
        (args.mutated_samples, "mutatedSamples"),
    ):
        value = str(cli_value).strip()
        if value:
            pro_overrides[setting_key] = value

    tuned_values, auto_summary = auto_generation_values(
        image_path,
        base_values,
        pro_overrides=pro_overrides,
        sample_boost=bool(args.sample_boost),
    )
    effective = write_custom_settings(setting, tuned_values)
    effective["label"] = setting.get("label", effective.get("label"))
    effective["auto_tune"] = auto_summary
    if args.sample_boost:
        effective["vroom_boost"] = True

    values = effective.get("values", {})
    run_dir = next_generator_output_dir(image_path)
    cmd = build_generator_command(
        image_path,
        effective,
        enable_repair=bool(args.edge_repair),
        enable_overshoot=False,
        output_dir=run_dir,
        seed=max(0, int(args.seed or 0)),
    )

    print(f"KFPS_RUN_DIR: {run_dir}", flush=True)
    print(f"Selected Kloudy preset: {effective.get('label') or setting.get('label') or setting.get('name')}", flush=True)
    print(f"Generating final vinyl from: {image_path}", flush=True)
    print(f"Vinyl run folder: {run_dir}", flush=True)
    print(f"Target template layers: {values.get('stopAt', 'n/a')}", flush=True)
    print(f"Finalize at layers: {values.get('saveAt', values.get('stopAt', 'n/a'))}", flush=True)
    print(
        "Preset effort: "
        f"maxRes={values.get('maxResolution', 'n/a')} "
        f"random={values.get('randomSamples', 'n/a')} "
        f"mutated={values.get('mutatedSamples', 'n/a')}",
        flush=True,
    )
    print(f"Seed: {args.seed if int(args.seed or 0) > 0 else 'random'}", flush=True)
    print(f"Detail Heatmap: {values.get('detailHeatmapMode', 'off')}", flush=True)
    print(f"Luma Prep: {values.get('v2PreprocessMode', 'none')}", flush=True)

    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )
    stream_process(proc)
    return_code = proc.wait()
    if return_code != 0:
        print(f"Generator exited with code {return_code} for {image_path.name}.", flush=True)
        return return_code

    previews = generated_preview_files(image_path)
    if previews:
        print(f"KFPS_PREVIEW: {previews[0]}", flush=True)
    print("Universal generation complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
