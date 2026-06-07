#!/usr/bin/env python3
"""Analyze FH6 research captures for export-safe group candidates.

This is offline-only. It reads capture.json files produced by
fh6_research_capture.py, builds a CLiveryGroup relationship graph per capture,
then compares grouped/nested captures against ungrouped flat captures.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


LOCKED_LABEL = "locked_community"
EDITABLE_LABELS = {"editable_allowed", "editable_own", "editable_external"}
GROUPING_LABELS = {"ungrouped", "grouped", "nested", "unknown"}


def normalize_access_state(value: str | None) -> str:
    value = str(value or "unknown").strip().lower()
    if value in {"editable_own", "editable_external"}:
        return "editable_allowed"
    if value in {"editable_allowed", "locked_community"}:
        return value
    return "unknown"


def normalize_grouping_state(value: str | None, access: str = "unknown") -> str:
    value = str(value or "unknown").strip().lower()
    aliases = {
        "flat": "ungrouped",
        "flat_orphan": "ungrouped",
        "none": "ungrouped",
        "one_group": "grouped",
        "groups": "grouped",
        "grouped_groups": "nested",
        "nested_groups": "nested",
    }
    value = aliases.get(value, value)
    if value in GROUPING_LABELS:
        return value
    # Legacy captures had no grouping label. Editable/locked is not equivalent
    # to grouping, so keep those as unknown instead of inventing structure.
    return "unknown"


def parse_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return None


def stable(values: list) -> bool:
    return bool(values) and len(set(values)) == 1


def safe_ratio(num, den) -> float:
    try:
        den = float(den)
        return 0.0 if den <= 0 else float(num) / den
    except Exception:
        return 0.0


def candidate_identity(candidate: dict) -> tuple[int | None, int | None]:
    return parse_int(candidate.get("group")), parse_int(candidate.get("table"))


def candidate_ptrs(candidate: dict) -> list[int]:
    out = []
    for value in candidate.get("table_pointers") or []:
        parsed = parse_int(value)
        if parsed is not None:
            out.append(parsed)
    return out


def merge_candidates(payload: dict) -> list[dict]:
    merged: dict[tuple[int | None, int | None], dict] = {}
    for source_name in ("candidates", "deep_candidates"):
        for candidate in payload.get(source_name) or []:
            key = candidate_identity(candidate)
            if key == (None, None):
                continue
            old = merged.get(key)
            if old is None:
                item = dict(candidate)
                item["_sources"] = [source_name]
                merged[key] = item
                continue
            old["_sources"].append(source_name)
            # Deep candidates usually include protection_research/raw context;
            # keep the richer copy while preserving the highest score.
            if candidate.get("protection_research") and not old.get("protection_research"):
                replacement = dict(candidate)
                replacement["_sources"] = old["_sources"]
                merged[key] = replacement
            elif int(candidate.get("score") or -10**9) > int(old.get("score") or -10**9):
                for k, v in candidate.items():
                    old[k] = v
    return list(merged.values())


def annotate_group_graph(candidates: list[dict]) -> None:
    group_addrs = {candidate_identity(c)[0] for c in candidates if candidate_identity(c)[0] is not None}
    ptr_sets: dict[int, set[int]] = {}
    for candidate in candidates:
        group, _table = candidate_identity(candidate)
        if group is None:
            continue
        ptr_sets[group] = set(candidate_ptrs(candidate))

    for candidate in candidates:
        group, _table = candidate_identity(candidate)
        ptrs = ptr_sets.get(group or 0, set())
        children = sorted(ptrs.intersection(group_addrs) - {group})
        parents = sorted(parent for parent, parent_ptrs in ptr_sets.items() if group is not None and group != parent and group in parent_ptrs)
        candidate["_graph"] = {
            "has_parent": bool(parents),
            "has_children": bool(children),
            "is_flat_orphan": not parents and not children,
            "parent_groups": [hex(v) for v in parents[:16]],
            "child_groups": [hex(v) for v in children[:16]],
            "parent_count": len(parents),
            "child_count": len(children),
        }


def candidate_quality(candidate: dict, requested_count: int) -> dict:
    vector_count = candidate.get("vector_count")
    capacity_count = candidate.get("capacity_count")
    count_u16 = candidate.get("count_u16_0x5a")
    valid_ptrs = int(candidate.get("valid_ptrs") or 0)
    ok_count = int(candidate.get("layer_ok_count") or 0)
    invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, requested_count - valid_ptrs))
    duplicate_ptr_count = int(candidate.get("duplicate_ptr_count") or 0)
    reasons = candidate.get("reasons") or []
    graph = candidate.get("_graph") or {}
    exact_vector = vector_count is not None and int(vector_count) == int(requested_count)
    enough_capacity = capacity_count is not None and int(capacity_count) >= int(requested_count)
    exact_count16 = count_u16 is not None and int(count_u16) == int(requested_count)
    valid_rate = safe_ratio(valid_ptrs, requested_count)
    ok_rate = safe_ratio(ok_count, requested_count)
    score = 0
    if graph.get("is_flat_orphan"):
        score += 6000
    if exact_vector:
        score += 3000
    if enough_capacity:
        score += 1200
    if exact_count16:
        score += 900
    if invalid_ptrs == 0:
        score += 600
    score += int(valid_rate * 1000)
    score += int(ok_rate * 1000)
    score += min(500, int(candidate.get("score") or 0) // 10)
    if duplicate_ptr_count:
        score -= min(1200, duplicate_ptr_count * 10)
    score -= len(reasons) * 250
    if not candidate.get("protection_research", {}).get("available"):
        score -= 1000
    return {
        "score": score,
        "exact_vector": exact_vector,
        "enough_capacity": enough_capacity,
        "exact_count16": exact_count16,
        "valid_rate": valid_rate,
        "ok_rate": ok_rate,
        "valid_ptrs": valid_ptrs,
        "ok_count": ok_count,
        "invalid_ptrs": invalid_ptrs,
        "duplicate_ptr_count": duplicate_ptr_count,
        "reasons": reasons,
    }


def select_best_candidate(candidates: list[dict], requested_count: int, require_research: bool = False) -> dict | None:
    if not candidates:
        return None
    for candidate in candidates:
        candidate["_quality"] = candidate_quality(candidate, requested_count)
    pool = candidates
    if require_research:
        pool = [c for c in candidates if c.get("protection_research", {}).get("available")]
    if not pool:
        return None
    return sorted(pool, key=lambda c: c["_quality"]["score"], reverse=True)[0]


def load_captures(root: Path) -> list[dict]:
    captures = []
    for path in sorted(root.rglob("capture.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        access = normalize_access_state(payload.get("declared_access_state"))
        grouping = normalize_grouping_state(payload.get("declared_grouping_state"), access)
        requested_count = int(payload.get("requested_count") or 0)
        candidates = merge_candidates(payload)
        if not candidates:
            continue
        annotate_group_graph(candidates)
        best = select_best_candidate(candidates, requested_count)
        best_research_candidate = select_best_candidate(candidates, requested_count, require_research=True)
        best_research = best_research_candidate.get("protection_research") if best_research_candidate else None
        captures.append({
            "path": path,
            "access": access,
            "grouping": grouping,
            "count": requested_count,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "selected": best,
            "selected_research": best_research_candidate,
            "research": best_research if isinstance(best_research, dict) else {},
        })
    return captures


def scalar_map(research: dict) -> dict[tuple[str, str], int]:
    values = {}
    for item in research.get("group_header_scalar_candidates") or []:
        values[(str(item.get("kind")), str(item.get("offset")))] = int(item.get("value") or 0)
    return values


def pointer_crc_map(research: dict) -> dict[str, str]:
    values = {}
    for item in research.get("group_window_pointer_fields") or []:
        offset = str(item.get("offset_from_group"))
        crc = item.get("target_crc32")
        if offset and crc:
            values[offset] = str(crc)
    return values


def layer_scalar_map(research: dict) -> dict[tuple[str, str], list[int]]:
    values = defaultdict(list)
    for layer in research.get("layer_samples") or []:
        for item in layer.get("flag_like_scalars_0x80_0x140") or []:
            values[(str(item.get("kind")), str(item.get("offset")))].append(int(item.get("value") or 0))
    return values


def comparable_captures(captures: list[dict]) -> list[dict]:
    return [c for c in captures if c["access"] in {LOCKED_LABEL, "editable_allowed"} and c.get("research", {}).get("available")]


def rank_scalar_differences(captures: list[dict]) -> list[dict]:
    captures = comparable_captures(captures)
    locked = [c for c in captures if c["access"] == LOCKED_LABEL]
    editable = [c for c in captures if c["access"] in EDITABLE_LABELS]
    locked_maps = [scalar_map(c["research"]) for c in locked]
    editable_maps = [scalar_map(c["research"]) for c in editable]
    keys = sorted(set().union(*(m.keys() for m in locked_maps + editable_maps))) if locked_maps or editable_maps else []
    ranked = []
    for key in keys:
        locked_values = [m[key] for m in locked_maps if key in m]
        editable_values = [m[key] for m in editable_maps if key in m]
        if len(locked_values) < 2 or len(editable_values) < 2:
            continue
        editable_unique = sorted(set(editable_values))
        locked_unique = sorted(set(locked_values))
        if stable(locked_values) and locked_values[0] not in editable_unique:
            ranked.append({
                "field": "group_header_scalar",
                "kind": key[0],
                "offset": key[1],
                "locked_value": locked_values[0],
                "editable_values": editable_unique,
                "locked_observations": len(locked_values),
                "editable_observations": len(editable_values),
                "score": 1000 + len(locked_values) * 70 + len(editable_values) * 35 - len(editable_unique) * 10,
            })
        elif len(locked_unique) <= 2 and not set(locked_unique).intersection(editable_unique):
            ranked.append({
                "field": "group_header_scalar_set",
                "kind": key[0],
                "offset": key[1],
                "locked_values": locked_unique,
                "editable_values": editable_unique,
                "locked_observations": len(locked_values),
                "editable_observations": len(editable_values),
                "score": 700 + len(locked_values) * 50 + len(editable_values) * 25 - len(locked_unique) * 20,
            })
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def rank_pointer_differences(captures: list[dict]) -> list[dict]:
    captures = comparable_captures(captures)
    locked = [c for c in captures if c["access"] == LOCKED_LABEL]
    editable = [c for c in captures if c["access"] in EDITABLE_LABELS]
    locked_maps = [pointer_crc_map(c["research"]) for c in locked]
    editable_maps = [pointer_crc_map(c["research"]) for c in editable]
    keys = sorted(set().union(*(m.keys() for m in locked_maps + editable_maps))) if locked_maps or editable_maps else []
    ranked = []
    for key in keys:
        locked_values = [m[key] for m in locked_maps if key in m]
        editable_values = [m[key] for m in editable_maps if key in m]
        if len(locked_values) < 2 or len(editable_values) < 2:
            continue
        if stable(locked_values) and locked_values[0] not in set(editable_values):
            ranked.append({
                "field": "group_pointer_target_crc",
                "offset_from_group": key,
                "locked_crc32": locked_values[0],
                "editable_crc32_values": sorted(set(editable_values)),
                "locked_observations": len(locked_values),
                "editable_observations": len(editable_values),
                "score": 700 + len(locked_values) * 45 + len(editable_values) * 20,
            })
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def rank_layer_differences(captures: list[dict]) -> list[dict]:
    captures = comparable_captures(captures)
    locked = [c for c in captures if c["access"] == LOCKED_LABEL]
    editable = [c for c in captures if c["access"] in EDITABLE_LABELS]
    locked_maps = [layer_scalar_map(c["research"]) for c in locked]
    editable_maps = [layer_scalar_map(c["research"]) for c in editable]
    keys = sorted(set().union(*(m.keys() for m in locked_maps + editable_maps))) if locked_maps or editable_maps else []
    ranked = []
    for key in keys:
        locked_values = []
        editable_values = []
        for m in locked_maps:
            locked_values.extend(m.get(key, []))
        for m in editable_maps:
            editable_values.extend(m.get(key, []))
        if len(locked_values) < 6 or len(editable_values) < 6:
            continue
        locked_unique = sorted(set(locked_values))
        editable_unique = sorted(set(editable_values))
        if len(locked_unique) <= 2 and not set(locked_unique).intersection(editable_unique):
            ranked.append({
                "field": "layer_tail_scalar",
                "kind": key[0],
                "offset": key[1],
                "locked_values": locked_unique,
                "editable_values": editable_unique[:32],
                "locked_observations": len(locked_values),
                "editable_observations": len(editable_values),
                "score": 300 + len(locked_values) + len(editable_values) - len(locked_unique) * 20,
            })
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def selected_summary(capture: dict) -> dict:
    candidate = capture.get("selected") or {}
    research_candidate = capture.get("selected_research") or {}
    graph = candidate.get("_graph") or {}
    quality = candidate.get("_quality") or {}
    research_graph = research_candidate.get("_graph") or {}
    research_quality = research_candidate.get("_quality") or {}
    return {
        "path": str(capture["path"]),
        "access": capture["access"],
        "grouping": capture.get("grouping", "unknown"),
        "count": capture["count"],
        "candidate_count": capture["candidate_count"],
        "selected_group": candidate.get("group"),
        "selected_table": candidate.get("table"),
        "selected_source": candidate.get("source"),
        "selected_score": candidate.get("score"),
        "graph": graph,
        "quality": quality,
        "vector_count": candidate.get("vector_count"),
        "capacity_count": candidate.get("capacity_count"),
        "count_u16_0x5a": candidate.get("count_u16_0x5a"),
        "valid_ptrs": candidate.get("valid_ptrs"),
        "layer_ok_count": candidate.get("layer_ok_count"),
        "duplicate_ptr_count": candidate.get("duplicate_ptr_count"),
        "reasons": candidate.get("reasons") or [],
        "has_protection_research": bool(capture.get("research", {}).get("available")),
        "research_group": research_candidate.get("group"),
        "research_table": research_candidate.get("table"),
        "research_source": research_candidate.get("source"),
        "research_graph": research_graph,
        "research_quality": research_quality,
        "research_vector_count": research_candidate.get("vector_count"),
        "research_capacity_count": research_candidate.get("capacity_count"),
        "research_valid_ptrs": research_candidate.get("valid_ptrs"),
        "research_layer_ok_count": research_candidate.get("layer_ok_count"),
        "research_reasons": research_candidate.get("reasons") or [],
    }


def graph_stats(captures: list[dict]) -> dict:
    stats = {}
    for label in ("ungrouped", "grouped", "nested", "unknown"):
        selected = [c for c in captures if c.get("grouping", "unknown") == label]
        stats[label] = {
            "captures": len(selected),
            "selected_flat_orphans": sum(1 for c in selected if (c.get("selected") or {}).get("_graph", {}).get("is_flat_orphan")),
            "selected_with_children": sum(1 for c in selected if (c.get("selected") or {}).get("_graph", {}).get("has_children")),
            "selected_with_parent": sum(1 for c in selected if (c.get("selected") or {}).get("_graph", {}).get("has_parent")),
            "selected_exact_vector": sum(1 for c in selected if (c.get("selected") or {}).get("_quality", {}).get("exact_vector")),
        }
    return stats


def legacy_access_graph_stats(captures: list[dict]) -> dict:
    stats = {}
    for label in ("editable_allowed", "locked_community", "unknown"):
        selected = [c for c in captures if c["access"] == label]
        stats[label] = {
            "captures": len(selected),
            "selected_flat_orphans": sum(1 for c in selected if (c.get("selected") or {}).get("_graph", {}).get("is_flat_orphan")),
            "selected_with_children": sum(1 for c in selected if (c.get("selected") or {}).get("_graph", {}).get("has_children")),
            "selected_with_parent": sum(1 for c in selected if (c.get("selected") or {}).get("_graph", {}).get("has_parent")),
            "selected_exact_vector": sum(1 for c in selected if (c.get("selected") or {}).get("_quality", {}).get("exact_vector")),
        }
    return stats


def write_markdown(out: Path, captures: list[dict], findings: list[dict]) -> None:
    locked_count = sum(1 for c in captures if c["access"] == LOCKED_LABEL)
    editable_count = sum(1 for c in captures if c["access"] in EDITABLE_LABELS)
    ungrouped_count = sum(1 for c in captures if c.get("grouping") == "ungrouped")
    grouped_count = sum(1 for c in captures if c.get("grouping") == "grouped")
    nested_count = sum(1 for c in captures if c.get("grouping") == "nested")
    comparable_count = len(comparable_captures(captures))
    lines = [
        "# FH6 Grouping Research Analysis",
        "",
        f"Captures loaded: {len(captures)}",
        f"Ungrouped captures: {ungrouped_count}",
        f"Grouped captures: {grouped_count}",
        f"Nested/grouped-groups captures: {nested_count}",
        f"Comparable captures with protection research: {comparable_count}",
        f"Locked captures: {locked_count}",
        f"Unlocked/editable captures: {editable_count}",
        "",
        "This analysis builds a per-capture CLiveryGroup graph. Current test labels assume unlocked means fully ungrouped and locked means one grouped vinyl. The graph is used to verify whether memory actually matches that assumption.",
        "",
        "## Grouping Graph Summary",
        "",
    ]
    stats = graph_stats(captures)
    for label, item in stats.items():
        if not item["captures"]:
            continue
        lines.append(
            f"- `{label}`: {item['captures']} captures, "
            f"{item['selected_flat_orphans']} selected flat orphans, "
            f"{item['selected_exact_vector']} selected exact-vector candidates, "
            f"{item['selected_with_children']} with children, "
            f"{item['selected_with_parent']} with parent"
        )
    lines.extend(["", "## Locked/Unlocked Graph Summary", ""])
    for label, item in legacy_access_graph_stats(captures).items():
        if not item["captures"]:
            continue
        lines.append(
            f"- `{label}`: {item['captures']} captures, "
            f"{item['selected_flat_orphans']} selected flat orphans, "
            f"{item['selected_exact_vector']} selected exact-vector candidates, "
            f"{item['selected_with_children']} with children, "
            f"{item['selected_with_parent']} with parent"
        )
    lines.extend(["", "## Selected Candidates", ""])
    for capture in captures:
        summary = selected_summary(capture)
        graph = summary["graph"]
        quality = summary["quality"]
        lines.append(
            f"- grouping=`{summary['grouping']}` access=`{summary['access']}` `{summary['count']} layers`: "
            f"flat_orphan={graph.get('is_flat_orphan')} "
            f"parent={graph.get('has_parent')} children={graph.get('has_children')} "
            f"exact_vector={quality.get('exact_vector')} "
            f"valid={summary.get('valid_ptrs')} ok={summary.get('layer_ok_count')} "
            f"source={summary.get('selected_source')} reasons={summary.get('reasons')}"
        )
        if summary.get("has_protection_research"):
            rgraph = summary.get("research_graph") or {}
            rquality = summary.get("research_quality") or {}
            lines.append(
                f"  research: flat_orphan={rgraph.get('is_flat_orphan')} "
                f"exact_vector={rquality.get('exact_vector')} "
                f"valid={summary.get('research_valid_ptrs')} ok={summary.get('research_layer_ok_count')} "
                f"source={summary.get('research_source')} reasons={summary.get('research_reasons')}"
            )
    lines.extend(["", "## Locked-vs-Unlocked Field Leads", ""])
    if not findings:
        lines.append("No stable locked-vs-editable field candidates met the current minimum observation threshold.")
    for index, item in enumerate(findings[:40], start=1):
        lines.append(f"{index}. `{item.get('field')}` score `{item.get('score')}`")
        details = {k: v for k, v in item.items() if k not in {"score", "field"}}
        lines.append(f"   `{json.dumps(details, sort_keys=True)}`")
    lines.extend(["", "## Input Captures", ""])
    for capture in captures:
        lines.append(f"- `{capture['access']}` `{capture['count']} layers` `{capture['path']}`")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="captures", help="Folder containing research capture folders.")
    parser.add_argument("--out", default=None, help="Output JSON path. Defaults to <root>/lock-research-analysis.json.")
    args = parser.parse_args()
    root = Path(args.root)
    captures = load_captures(root)
    findings = []
    findings.extend(rank_scalar_differences(captures))
    findings.extend(rank_pointer_differences(captures))
    findings.extend(rank_layer_differences(captures))
    findings.sort(key=lambda item: item.get("score", 0), reverse=True)
    out = Path(args.out) if args.out else root / "lock-research-analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "fh6_grouping_research_analysis_v3",
        "capture_count": len(captures),
        "ungrouped_capture_count": sum(1 for c in captures if c.get("grouping") == "ungrouped"),
        "grouped_capture_count": sum(1 for c in captures if c.get("grouping") == "grouped"),
        "nested_capture_count": sum(1 for c in captures if c.get("grouping") == "nested"),
        "comparable_capture_count": len(comparable_captures(captures)),
        "locked_capture_count": sum(1 for c in captures if c["access"] == LOCKED_LABEL),
        "editable_capture_count": sum(1 for c in captures if c["access"] in EDITABLE_LABELS),
        "graph_stats": graph_stats(captures),
        "legacy_access_graph_stats": legacy_access_graph_stats(captures),
        "selected_candidates": [selected_summary(c) for c in captures],
        "findings": findings,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_markdown(out.with_suffix(".md"), captures, findings)
    print(f"Wrote {out}")
    print(f"Wrote {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
