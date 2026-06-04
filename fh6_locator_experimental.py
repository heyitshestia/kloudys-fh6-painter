#!/usr/bin/env python3
"""Experimental FH6 livery table locator.

This is a read-only sidecar for testing the newer locator strategy without
changing fh6_probe.py or any importer code.

Goal:
- Prefer Dawg/forza-painter style RTTI/update-code discovery of CLiveryGroup.
- Fall back to the existing FH6 group-layout/count locator.
- Add a stricter confidence report around the winning table.
- Optionally score a deliberately made template fingerprint.

It never writes into the game process. It only reads memory and writes a JSON
report to runtime/probes by default.

Example:
    py -3.12 fh6_locator_experimental.py --pid 12345 --layers 3000

Optional template fingerprint JSON:
    {
      "slots": [
        {"index": 0, "color_rgba": [255, 0, 0, 255], "shape_byte": 102},
        {"index": 1, "color_rgba": [0, 255, 0, 255]},
        {"index": 2, "color_rgba": [0, 0, 255, 255]}
      ]
    }

The fingerprint is intentionally approximate. Any omitted field is ignored.
Supported slot keys:
- index: zero-based layer index
- color_rgba: [r, g, b, a]
- shape_byte: byte at profile.layer_shape_id_offset
- mask_byte: byte at profile.layer_mask_offset
- position: [x, y] with tolerance
- scale: [sx, sy] with tolerance
- rotation: float with tolerance
- tolerance: optional numeric tolerance for float fields, default 0.01
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from game_profiles import get_profile
from native import get_base_address, read_process_memory
from fh6_probe import (
    collect_auto_locate_tables,
    is_user_pointer,
    read_layer_state,
    read_memory_window,
    read_pointer,
    score_table,
    summarize_slot,
    validate_group_vector,
    validate_table_layer_coverage,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "runtime" / "probes" / "fh6-locator-experimental.json"


def _now() -> float:
    return time.time()


def _hex(value: Any) -> str | None:
    try:
        return f"0x{int(value):x}"
    except Exception:
        return None


def _safe_process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except Exception:
        return "unknown"


def _safe_base_address(pid: int) -> int | None:
    try:
        return int(get_base_address(pid))
    except Exception:
        return None


def load_fingerprint(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fingerprint JSON must be an object")
    slots = payload.get("slots")
    if not isinstance(slots, list):
        raise ValueError("fingerprint JSON must contain a slots list")
    normalized = []
    for row in slots:
        if not isinstance(row, dict):
            continue
        if "index" not in row:
            raise ValueError("each fingerprint slot needs an index")
        item = dict(row)
        item["index"] = int(item["index"])
        normalized.append(item)
    return {"slots": normalized, "source": str(path)}


def close_enough(actual: float | int | None, expected: float | int | None, tolerance: float) -> bool:
    if actual is None or expected is None:
        return False
    try:
        actual_f = float(actual)
        expected_f = float(expected)
    except Exception:
        return False
    if math.isnan(actual_f) or math.isnan(expected_f):
        return False
    return abs(actual_f - expected_f) <= float(tolerance)


def compare_vector(actual: list[Any] | None, expected: list[Any] | None, tolerance: float) -> bool:
    if not isinstance(actual, list) or not isinstance(expected, list):
        return False
    if len(actual) < len(expected):
        return False
    return all(close_enough(actual[i], expected[i], tolerance) for i in range(len(expected)))


def score_fingerprint_slot(known: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    tolerance = float(spec.get("tolerance", 0.01))
    checks: list[dict[str, Any]] = []
    score = 0
    possible = 0

    def add_check(name: str, passed: bool, actual: Any, expected: Any, weight: int) -> None:
        nonlocal score, possible
        possible += weight
        if passed:
            score += weight
        checks.append({
            "field": name,
            "pass": bool(passed),
            "actual": actual,
            "expected": expected,
            "weight": weight,
        })

    if "color_rgba" in spec:
        actual = known.get("color_rgba")
        expected = list(spec.get("color_rgba") or [])
        add_check("color_rgba", actual == expected, actual, expected, 40)
    if "shape_byte" in spec:
        actual = known.get("shape_byte")
        expected = int(spec["shape_byte"])
        add_check("shape_byte", actual == expected, actual, expected, 16)
    if "mask_byte" in spec:
        actual = known.get("mask_byte")
        expected = int(spec["mask_byte"])
        add_check("mask_byte", actual == expected, actual, expected, 8)
    if "position" in spec:
        actual = known.get("position")
        expected = list(spec.get("position") or [])
        add_check("position", compare_vector(actual, expected, tolerance), actual, expected, 12)
    if "scale" in spec:
        actual = known.get("scale")
        expected = list(spec.get("scale") or [])
        add_check("scale", compare_vector(actual, expected, tolerance), actual, expected, 12)
    if "rotation" in spec:
        actual = known.get("rotation")
        expected = spec.get("rotation")
        add_check("rotation", close_enough(actual, expected, tolerance), actual, expected, 8)

    ratio = (score / possible) if possible else 0.0
    return {"score": score, "possible": possible, "ratio": ratio, "checks": checks}


def score_table_fingerprint(pid: int, profile: Any, table_address: int, fingerprint: dict[str, Any] | None) -> dict[str, Any]:
    if not fingerprint:
        return {"enabled": False, "score": 0, "possible": 0, "ratio": 0.0, "slots": []}

    total = 0
    possible = 0
    slots_out = []
    for spec in fingerprint.get("slots", []):
        index = int(spec["index"])
        ptr = read_pointer(pid, table_address + index * 8)
        if not is_user_pointer(ptr):
            slot_result = {
                "index": index,
                "pointer": _hex(ptr),
                "valid_pointer": False,
                "score": 0,
                "possible": 1,
                "ratio": 0.0,
                "checks": [],
            }
            possible += 1
            slots_out.append(slot_result)
            continue
        state = read_layer_state(pid, profile, ptr)
        known = state.get("known_fields", {})
        slot_score = score_fingerprint_slot(known, spec)
        total += int(slot_score["score"])
        possible += int(slot_score["possible"])
        slots_out.append({
            "index": index,
            "pointer": _hex(ptr),
            "valid_pointer": True,
            "known_fields": known,
            **slot_score,
        })
    return {
        "enabled": True,
        "source": fingerprint.get("source"),
        "score": total,
        "possible": possible,
        "ratio": (total / possible) if possible else 0.0,
        "slots": slots_out,
    }


def confidence_label(score: int, coverage_ok: bool, vector_ok: bool, fingerprint_ratio: float | None) -> str:
    if fingerprint_ratio is not None:
        if fingerprint_ratio >= 0.90 and coverage_ok and vector_ok:
            return "very_high"
        if fingerprint_ratio >= 0.70 and coverage_ok and vector_ok:
            return "high"
        if fingerprint_ratio < 0.50:
            return "low"
    if score >= 140 and coverage_ok and vector_ok:
        return "high"
    if score >= 80 and coverage_ok:
        return "medium"
    return "low"


def enrich_candidate(pid: int, profile: Any, layer_count: int, candidate: dict[str, Any], fingerprint: dict[str, Any] | None, slot_window: int) -> dict[str, Any]:
    table_address = int(candidate["table_address"])
    group_address = int(candidate.get("group_address") or 0)
    vector_ok, vector = validate_group_vector(pid, profile, group_address, table_address, layer_count)
    coverage_ok, checked, valid_entries = validate_table_layer_coverage(pid, profile, table_address, layer_count)
    table_score, samples = score_table(pid, profile, table_address, min(int(layer_count), 64))
    fingerprint_result = score_table_fingerprint(pid, profile, table_address, fingerprint)
    fingerprint_ratio = fingerprint_result.get("ratio") if fingerprint_result.get("enabled") else None

    slots = []
    for index in range(min(int(layer_count), int(slot_window))):
        try:
            slots.append(summarize_slot(pid, profile, table_address, layer_count, 0x140, index))
        except Exception as exc:
            slots.append({"index": index, "error": f"{type(exc).__name__}: {exc}"})

    combined_score = int(candidate.get("score", 0)) + int(table_score)
    if fingerprint_result.get("enabled"):
        combined_score += int(fingerprint_result.get("score", 0))
    if vector_ok:
        combined_score += 50
    if coverage_ok:
        combined_score += 50

    return {
        "combined_score": combined_score,
        "confidence": confidence_label(combined_score, bool(coverage_ok), bool(vector_ok), fingerprint_ratio),
        "source_score": candidate.get("score"),
        "rescored_table_score": table_score,
        "locator": candidate.get("count_kind") or candidate.get("locator"),
        "group_address": _hex(group_address),
        "count_address": _hex(candidate.get("count_address")),
        "table_pointer_field": _hex(candidate.get("table_pointer_field")),
        "table_address": _hex(table_address),
        "vector_ok": bool(vector_ok),
        "vector": {k: (_hex(v) if k.endswith("end") or k.endswith("capacity") else v) for k, v in dict(vector).items()},
        "coverage_ok": bool(coverage_ok),
        "coverage_checked_slots": checked,
        "coverage_valid_entries": valid_entries,
        "validated_entries_from_locator": candidate.get("validated_entries"),
        "samples": [
            {
                "index": index,
                "pointer": _hex(ptr),
                "score": layer_score,
                "checks": checks,
            }
            for index, ptr, layer_score, checks in samples[:12]
        ],
        "fingerprint": fingerprint_result,
        "first_slots": slots,
        "table_entry_window": read_memory_window(pid, table_address, 0x40, 0x100),
    }


def locate(pid: int, game: str, layer_count: int, max_seconds: int, fingerprint_path: str | None, output_path: Path, top: int, slot_window: int) -> dict[str, Any]:
    profile = get_profile(game)
    fingerprint = load_fingerprint(fingerprint_path)
    started = _now()

    candidates = collect_auto_locate_tables(pid, profile, int(layer_count), max_seconds=int(max_seconds))
    enriched = []
    for candidate in candidates[: max(1, int(top))]:
        try:
            enriched.append(enrich_candidate(pid, profile, int(layer_count), candidate, fingerprint, int(slot_window)))
        except Exception as exc:
            enriched.append({
                "error": f"{type(exc).__name__}: {exc}",
                "raw_candidate": candidate,
            })

    enriched.sort(key=lambda item: int(item.get("combined_score", -1)), reverse=True)
    winner = enriched[0] if enriched else None

    payload = {
        "type": "fh6_locator_experimental_report_v1",
        "created": _now(),
        "elapsed_seconds": round(_now() - started, 3),
        "pid": int(pid),
        "process": _safe_process_name(pid),
        "base_address": _hex(_safe_base_address(pid)),
        "game": profile.key,
        "layer_count": int(layer_count),
        "max_seconds": int(max_seconds),
        "candidate_count": len(candidates),
        "enriched_count": len(enriched),
        "winner": winner,
        "candidates": enriched,
        "notes": [
            "Read-only locator report. No process memory was modified.",
            "Prefer confidence=high or very_high before using any table address for import.",
            "If multiple candidates score similarly, use a template fingerprint JSON to disambiguate.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Experimental read-only FH6 livery table locator")
    parser.add_argument("--pid", type=int, required=True, help="Target Forza process PID")
    parser.add_argument("--game", default="fh6", choices=("fh6", "fh5"), help="Game profile to use")
    parser.add_argument("--layers", type=int, required=True, help="Expected template layer count")
    parser.add_argument("--max-seconds", type=int, default=30, help="Stop scanning after this many seconds")
    parser.add_argument("--fingerprint", default=None, help="Optional template fingerprint JSON")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output report JSON")
    parser.add_argument("--top", type=int, default=12, help="Number of raw candidates to enrich")
    parser.add_argument("--slot-window", type=int, default=8, help="Number of first slots to summarize")
    args = parser.parse_args(argv)

    output_path = Path(args.out)
    payload = locate(
        pid=args.pid,
        game=args.game,
        layer_count=args.layers,
        max_seconds=args.max_seconds,
        fingerprint_path=args.fingerprint,
        output_path=output_path,
        top=args.top,
        slot_window=args.slot_window,
    )

    winner = payload.get("winner") or {}
    print("Experimental FH6 locator complete.")
    print(f"Report: {output_path}")
    print(f"Candidates: {payload.get('candidate_count')} raw / {payload.get('enriched_count')} enriched")
    if winner:
        print(f"Winner confidence: {winner.get('confidence')}")
        print(f"Winner table: {winner.get('table_address')}")
        print(f"Winner locator: {winner.get('locator')}")
        print(f"Vector OK: {winner.get('vector_ok')} | Coverage OK: {winner.get('coverage_ok')}")
        if winner.get("fingerprint", {}).get("enabled"):
            print(f"Fingerprint ratio: {winner['fingerprint'].get('ratio'):.3f}")
    else:
        print("No candidate was found.")
    return 0 if winner else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
