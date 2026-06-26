from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a KFPS JSON preview for the desktop shell.")
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-size", type=int, default=900)
    args = parser.parse_args()

    app_root = Path(args.app_root)
    json_path = Path(args.json)
    output_path = Path(args.output)

    sys.path.insert(0, str(app_root))
    try:
        from json_preview_renderer import render_json_preview
    except Exception as exc:
        print(f"preview import failed: {exc}", file=sys.stderr)
        return 2

    data = render_json_preview(json_path, max_size=args.max_size)
    if not data:
        print("preview renderer returned no data", file=sys.stderr)
        return 3

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    print(str(output_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
