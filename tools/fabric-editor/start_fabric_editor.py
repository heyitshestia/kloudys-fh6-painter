#!/usr/bin/env python3
"""Serve the local KFPS Fabric editor."""

from __future__ import annotations

import http.server
import json
import socket
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "tools" / "fabric-editor" / "index.html"
STARTUP_HELP_MARKER = ROOT / "runtime" / "fabric-editor" / "startup-help-confirmed.json"
STARTUP_HELP_API = "/api/fabric-editor/startup-help-confirmed"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == STARTUP_HELP_API:
            self._send_json({
                "confirmed": STARTUP_HELP_MARKER.exists(),
                "marker": str(STARTUP_HELP_MARKER),
            })
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] == STARTUP_HELP_API:
            STARTUP_HELP_MARKER.parent.mkdir(parents=True, exist_ok=True)
            STARTUP_HELP_MARKER.write_text(
                json.dumps({"confirmed": True}, indent=2),
                encoding="utf-8",
            )
            self._send_json({
                "confirmed": True,
                "marker": str(STARTUP_HELP_MARKER),
            })
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    if not EDITOR.exists():
        print(f"Missing editor: {EDITOR}")
        return 1
    port = find_port()
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/tools/fabric-editor/index.html"
        print("KFPS Fabric editor")
        print(f"Serving: {ROOT}")
        print(f"Open:    {url}")
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
