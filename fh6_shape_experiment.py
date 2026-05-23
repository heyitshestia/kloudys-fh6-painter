import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil

from game_profiles import get_profile


ROOT = Path(__file__).resolve().parent
PROBE_PATH = ROOT / "fh6_probe.py"
IMPORTER_PATH = ROOT / "main.py"
SESSION_PATH = ROOT / "webui-data" / "probes" / "current-fh6-session.json"
EXPERIMENT_DIR = ROOT / "webui-data" / "shape-experiments"

NAMED_COLORS = {
    "white": [255, 255, 255, 255],
    "black": [0, 0, 0, 255],
    "red": [255, 0, 0, 255],
    "green": [0, 255, 0, 255],
    "blue": [0, 0, 255, 255],
    "yellow": [255, 255, 0, 255],
    "magenta": [255, 0, 255, 255],
    "cyan": [0, 255, 255, 255],
    "transparent": [0, 0, 0, 0],
}

DEFAULT_VARIANTS = (
    ("white-0deg", 0.0, [255, 255, 255, 255]),
    ("white-47deg", 47.0, [255, 255, 255, 255]),
    ("red-123deg", 123.0, [255, 0, 0, 255]),
)

SHAPE_PRESETS = {
    "circle-variants": {
        "shape_kind": "circle",
        "shape_code": "1048678",
        "shape_name": "Circle",
        "section": "Page 1 - Primitives",
        "page": "1",
        "row": "2",
        "column": "1",
        "size": (420, 420),
        "variants": DEFAULT_VARIANTS,
    },
    "ellipse-variants": {
        "shape_kind": "ellipse",
        "shape_code": "1048678",
        "shape_name": "Circle",
        "section": "Page 1 - Primitives",
        "page": "1",
        "row": "2",
        "column": "1",
        "size": (460, 320),
        "variants": DEFAULT_VARIANTS,
    },
    "rectangle-variants": {
        "shape_kind": "rectangle",
        "shape_code": "1048677",
        "shape_name": "Square",
        "section": "Page 1 - Primitives",
        "page": "1",
        "row": "1",
        "column": "1",
        "size": (420, 420),
        "variants": DEFAULT_VARIANTS,
    },
}


def detect_pid(game):
    profile = get_profile(game)
    process_lookup = {}
    for proc in psutil.process_iter():
        try:
            process_lookup[proc.name().lower()] = proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    for process_name in profile.process_names:
        pid = process_lookup.get(process_name.lower())
        if pid:
            return pid
    raise RuntimeError(f"{game.upper()} is not running ({', '.join(profile.process_names)})")


def load_session():
    if not SESSION_PATH.exists():
        return None
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def session_pid_is_live(session, pid):
    try:
        return int(session.get("pid", -1)) == int(pid) and psutil.pid_exists(int(pid))
    except Exception:
        return False


def ensure_session(game, pid, layer_count):
    session = load_session()
    if session and str(session.get("layer_count", "")) == str(layer_count) and session_pid_is_live(session, pid):
        return session

    cmd = [
        sys.executable,
        str(PROBE_PATH),
        "--game",
        game,
        "--pid",
        str(pid),
        "--layer-count",
        str(layer_count),
        "--auto-locate",
        "--write-session",
        str(SESSION_PATH),
        "--limit-mb",
        "2048",
        "--max-matches",
        "500000",
        "--inspect-radius",
        "0x800",
        "--max-seconds",
        "45",
    ]
    run_checked(cmd, timeout=90)
    session = load_session()
    if not session:
        raise RuntimeError("Failed to create FH6 session location.")
    return session


def run_checked(cmd, timeout=120, input_text=None):
    print("$", " ".join(str(part) for part in cmd), flush=True)
    result = subprocess.run(cmd, timeout=timeout, input=input_text, text=True if input_text is not None else None)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(str(part) for part in cmd)}")


def write_geometry_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "shape"


def parse_color_spec(spec):
    text = spec.strip().lower()
    if text in NAMED_COLORS:
        return list(NAMED_COLORS[text])
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"Invalid color spec '{spec}'. Use a named color or r,g,b,a.")
    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid color spec '{spec}'.") from exc
    if any(value < 0 or value > 255 for value in values):
        raise argparse.ArgumentTypeError(f"Color values out of range in '{spec}'.")
    return values


def parse_variant_spec(spec):
    parts = spec.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"Invalid variant '{spec}'. Use slug:rotation:color.")
    slug = slugify(parts[0])
    try:
        rotation = float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid rotation in variant '{spec}'.") from exc
    color = parse_color_spec(parts[2])
    return slug, rotation, color


def build_shape_payload(shape_kind, width, height, rotation_deg, color_rgba, canvas):
    cx = canvas // 2
    cy = canvas // 2
    shapes = [{"type": 1, "data": [0, 0, canvas, canvas], "color": [0, 0, 0, 0]}]
    if shape_kind == "circle":
        diameter = min(width, height)
        shapes.append({"type": 16, "data": [cx, cy, diameter, diameter, rotation_deg], "color": color_rgba})
    elif shape_kind == "ellipse":
        shapes.append({"type": 16, "data": [cx, cy, width, height, rotation_deg], "color": color_rgba})
    elif shape_kind == "rectangle":
        shapes.append({"type": 1, "data": [cx, cy, width, height], "color": color_rgba})
    else:
        raise RuntimeError(f"Unsupported shape kind '{shape_kind}'.")
    return {"width": canvas, "height": canvas, "shapes": shapes}


def import_json(game, pid, layer_count, session, geometry_path):
    cmd = [
        sys.executable,
        str(IMPORTER_PATH),
        "--game",
        game,
        "--no-preview",
        "--pid",
        str(pid),
        "--layer-count-address",
        f"0x{int(session['count_address']):x}",
        "--layer-table-address",
        f"0x{int(session['table_address']):x}",
        "--layer-count-value",
        str(layer_count),
        str(geometry_path),
    ]
    run_checked(cmd, timeout=120, input_text="\n")


def dump_layer(
    game,
    pid,
    layer_count,
    slot_index_zero_based,
    output_path,
    shape_code,
    shape_name,
    section,
    page,
    row,
    column,
    table_address=None,
):
    cmd = [
        sys.executable,
        str(PROBE_PATH),
        "--game",
        game,
        "--pid",
        str(pid),
        "--layer-count",
        str(layer_count),
        "--dump-layer-index",
        str(slot_index_zero_based),
        "--dump-layer-output",
        str(output_path),
        "--dump-layer-shape-code",
        str(shape_code),
        "--dump-layer-shape-name",
        str(shape_name),
        "--dump-layer-shape-section",
        str(section),
        "--dump-layer-shape-page",
        str(page),
        "--dump-layer-shape-row",
        str(row),
        "--dump-layer-shape-column",
        str(column),
    ]
    if table_address is not None:
        cmd.extend(["--inspect-table", f"0x{int(table_address):x}"])
    else:
        cmd.extend(["--auto-dump-layer", "--dump-slot-radius", "16", "--max-seconds", "45"])
    run_checked(cmd, timeout=120)


def shape_output_dir(shape_code, shape_name):
    return EXPERIMENT_DIR / f"{shape_code}-{slugify(shape_name)}"


def run_variants(
    game,
    pid,
    layer_count,
    slot_one_based,
    shape_kind,
    shape_code,
    shape_name,
    section,
    page,
    row,
    column,
    width,
    height,
    variants,
    canvas,
    import_wait,
):
    session = ensure_session(game, pid, layer_count)
    out_dir = shape_output_dir(shape_code, shape_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, rotation, color in variants:
        geometry_path = out_dir / f"{slug}.json"
        dump_path = out_dir / f"{slug}.dump.json"
        payload = build_shape_payload(shape_kind, width, height, rotation, color, canvas)
        write_geometry_json(geometry_path, payload)
        print(f"\n=== Importing {slug} ===", flush=True)
        import_json(game, pid, layer_count, session, geometry_path)
        time.sleep(import_wait)
        print(f"=== Dumping {slug} ===", flush=True)
        dump_layer(
            game=game,
            pid=pid,
            layer_count=layer_count,
            slot_index_zero_based=slot_one_based - 1,
            output_path=dump_path,
            shape_code=shape_code,
            shape_name=shape_name,
            section=section,
            page=page,
            row=row,
            column=column,
            table_address=session.get("table_address"),
        )
    print(f"\nSaved experiment outputs under {out_dir}", flush=True)


def dump_current_shape(
    game,
    pid,
    layer_count,
    slot_one_based,
    shape_code,
    shape_name,
    section,
    page,
    row,
    column,
):
    out_dir = shape_output_dir(shape_code, shape_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_path = out_dir / "manual-current.dump.json"
    dump_layer(
        game=game,
        pid=pid,
        layer_count=layer_count,
        slot_index_zero_based=slot_one_based - 1,
        output_path=dump_path,
        shape_code=shape_code,
        shape_name=shape_name,
        section=section,
        page=page,
        row=row,
        column=column,
        table_address=None,
    )
    print(f"\nSaved manual dump to {dump_path}", flush=True)


def write_shape_byte_for_slot(pid, game, table_address, slot_index_zero_based, shape_byte):
    from native import dereference_pointer, write_process_memory

    profile = get_profile(game)
    layer_ptr = dereference_pointer(pid, int(table_address) + (int(slot_index_zero_based) * 0x8))
    if not layer_ptr:
        raise RuntimeError(f"Layer slot {slot_index_zero_based + 1} resolved to null while writing shape byte.")
    write_process_memory(pid, layer_ptr + profile.layer_shape_id_offset, bytes([int(shape_byte) & 0xFF]))
    return layer_ptr


def poke_shape_byte(
    game,
    pid,
    layer_count,
    slot_one_based,
    shape_byte,
    shape_code,
    shape_name,
    section,
    page,
    row,
    column,
):
    session = ensure_session(game, pid, layer_count)
    out_dir = shape_output_dir(shape_code or f"byte-{shape_byte}", shape_name or f"shape-byte-{shape_byte}")
    out_dir.mkdir(parents=True, exist_ok=True)
    layer_ptr = write_shape_byte_for_slot(pid, game, session.get("table_address"), slot_one_based - 1, shape_byte)
    print(f"Wrote shape byte {shape_byte} to slot {slot_one_based} at 0x{layer_ptr:x}", flush=True)
    dump_path = out_dir / f"shape-byte-{shape_byte}.dump.json"
    dump_layer(
        game=game,
        pid=pid,
        layer_count=layer_count,
        slot_index_zero_based=slot_one_based - 1,
        output_path=dump_path,
        shape_code=shape_code or str(shape_byte),
        shape_name=shape_name or f"shape-byte-{shape_byte}",
        section=section or "",
        page=page or "",
        row=row or "",
        column=column or "",
        table_address=session.get("table_address"),
    )
    print(f"\nSaved shape-byte dump to {dump_path}", flush=True)


def preset_to_args(name, args):
    preset = SHAPE_PRESETS[name]
    width, height = preset["size"]
    return {
        "shape_kind": preset["shape_kind"],
        "shape_code": preset["shape_code"],
        "shape_name": preset["shape_name"],
        "section": preset["section"],
        "page": preset["page"],
        "row": preset["row"],
        "column": preset["column"],
        "width": width,
        "height": height,
        "variants": list(preset["variants"]),
        "canvas": args.canvas,
        "import_wait": args.import_wait,
    }


def custom_to_args(args):
    if not args.shape_code or not args.shape_name:
        raise SystemExit("custom-variants requires --shape-code and --shape-name.")
    if not args.variants:
        raise SystemExit("custom-variants requires at least one --variant.")
    width = args.width
    height = args.height or args.width
    if args.shape_kind == "circle":
        height = width
    return {
        "shape_kind": args.shape_kind,
        "shape_code": args.shape_code,
        "shape_name": args.shape_name,
        "section": args.section or "",
        "page": args.page or "",
        "row": args.row or "",
        "column": args.column or "",
        "width": width,
        "height": height,
        "variants": [parse_variant_spec(spec) for spec in args.variants],
        "canvas": args.canvas,
        "import_wait": args.import_wait,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Automate FH6 importer/dump experiments with controlled one-shape JSON variants.")
    parser.add_argument("--game", default="fh6", choices=("fh6", "fh5"))
    parser.add_argument("--pid", type=int, default=None, help="Optional running game PID. If omitted, auto-detects the supported Forza process.")
    parser.add_argument("--layer-count", type=int, required=True, help="Exact ungrouped template layer count currently loaded in-game.")
    parser.add_argument("--slot", type=int, default=1, help="1-based layer slot to target for dumping.")
    parser.add_argument("--canvas", type=int, default=1000, help="Canvas size used for the generated experiment JSON.")
    parser.add_argument("--import-wait", type=float, default=0.75, help="Seconds to wait after each import before dumping.")
    parser.add_argument("--shape-kind", choices=("circle", "ellipse", "rectangle"), default="circle", help="Shape family for custom-variants.")
    parser.add_argument("--shape-code", default=None, help="Spreadsheet shape code for custom-variants.")
    parser.add_argument("--shape-name", default=None, help="Spreadsheet shape name for custom-variants.")
    parser.add_argument("--section", default=None)
    parser.add_argument("--page", default=None)
    parser.add_argument("--row", default=None)
    parser.add_argument("--column", default=None)
    parser.add_argument("--width", type=int, default=420, help="Width in JSON pixels for custom-variants.")
    parser.add_argument("--height", type=int, default=None, help="Height in JSON pixels for custom-variants.")
    parser.add_argument("--variant", dest="variants", action="append", default=[], help="Repeatable custom variant: slug:rotation:color. Color may be named or r,g,b,a.")
    parser.add_argument("--shape-byte", type=int, default=None, help="Direct shape byte to write for poke-shape-byte.")
    parser.add_argument("mode", choices=tuple(SHAPE_PRESETS.keys()) + ("custom-variants", "dump-current", "poke-shape-byte"))
    return parser.parse_args()


def main():
    args = parse_args()
    pid = args.pid or detect_pid(args.game)
    if args.slot < 1:
        raise SystemExit("--slot must be 1 or greater.")

    if args.mode == "dump-current":
        if not args.shape_code or not args.shape_name:
            raise SystemExit("dump-current requires --shape-code and --shape-name.")
        dump_current_shape(
            game=args.game,
            pid=pid,
            layer_count=args.layer_count,
            slot_one_based=args.slot,
            shape_code=args.shape_code,
            shape_name=args.shape_name,
            section=args.section or "",
            page=args.page or "",
            row=args.row or "",
            column=args.column or "",
        )
        return

    if args.mode == "poke-shape-byte":
        if args.shape_byte is None:
            raise SystemExit("poke-shape-byte requires --shape-byte.")
        poke_shape_byte(
            game=args.game,
            pid=pid,
            layer_count=args.layer_count,
            slot_one_based=args.slot,
            shape_byte=args.shape_byte,
            shape_code=args.shape_code,
            shape_name=args.shape_name,
            section=args.section,
            page=args.page,
            row=args.row,
            column=args.column,
        )
        return

    if args.mode in SHAPE_PRESETS:
        run_args = preset_to_args(args.mode, args)
    else:
        run_args = custom_to_args(args)

    run_variants(
        game=args.game,
        pid=pid,
        layer_count=args.layer_count,
        slot_one_based=args.slot,
        **run_args,
    )


if __name__ == "__main__":
    main()
