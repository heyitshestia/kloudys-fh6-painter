#!/usr/bin/env python3
"""Serve the Fabric FH6 editor prototype from the local prototype folder."""

from __future__ import annotations

import http.server
import socket
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "tools" / "fabric-editor" / "index.html"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

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
        print("Kloudy's Fabric FH6 editor prototype")
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
