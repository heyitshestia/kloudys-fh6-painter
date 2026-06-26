from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class BridgeEvent:
    kind: str
    value: str

PREFIXES = {
    "KFPS_RUN_DIR:": "run_started",
    "KFPS_PREVIEW:": "preview_updated",
    "KFPS_SELECTED_JSON:": "selected_json",
    "WPF_RUN_DIR:": "run_started",
    "WPF_PREVIEW:": "preview_updated",
    "WPF_SELECTED_JSON:": "selected_json",
}

def parse_bridge_line(line: str) -> BridgeEvent:
    text = str(line or "").strip()
    for prefix, kind in PREFIXES.items():
        if text.startswith(prefix):
            return BridgeEvent(kind, text[len(prefix):].strip())
    return BridgeEvent("log", text)
