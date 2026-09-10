import http.client
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from test_fabric_editor_server import EDITOR_ROOT, RunningEditorServer, fabric_server


class FabricEditorStorageLimitTests(unittest.TestCase):
    def test_client_and_server_share_project_budget(self):
        source = (EDITOR_ROOT / "editor.js").read_text(encoding="utf-8")
        self.assertEqual(100 * 1024 * 1024, fabric_server.EDITOR_PROJECT_MAX_BYTES)
        self.assertIn("const EDITOR_PROJECT_MAX_BYTES = 100 * 1024 * 1024;", source)
        self.assertIn("const EDITOR_REFERENCE_MAX_BYTES = 50 * 1024 * 1024;", source)

    def request(self, server, endpoint, body=None, length=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.httpd.server_address[1], timeout=5)
        try:
            connection.putrequest("POST", endpoint)
            connection.putheader(fabric_server.EDITOR_MUTATION_HEADER, server.httpd.editor_session_token)
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(body) if length is None else length))
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def check_boundary(self, endpoint):
        # Scale only the limit for deterministic exact-byte integration checks.
        limit = 4096
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            for name, value in {
                "EDITOR_PROJECT_MAX_BYTES": limit,
                "EDITOR_PROJECT_ROOT": root / "projects",
                "EDITOR_PROJECT_CHANGE_MARKER": root / "project-change.json",
                "EDITOR_AUTOSAVE_MARKER": root / "autosave.json",
            }.items():
                stack.enter_context(patch.object(fabric_server, name, value))
            server = stack.enter_context(RunningEditorServer())
            for size in (limit - 1, limit):
                payload = {"shapes": [{"type": 1048677, "shape_name": ""}], "recovery_revision": size}
                data = {"name": "Boundary", "payload": payload, "overwrite": True} if endpoint == fabric_server.PROJECT_SAVE_API else payload
                payload["shapes"][0]["shape_name"] = "x" * (size - len(json.dumps(data).encode("utf-8")))
                body = json.dumps(data).encode("utf-8")
                self.assertEqual(size, len(body))
                status, response = self.request(server, endpoint, body)
                self.assertEqual(200, status, response)
                target = root / "projects" / "Boundary.fabric-project.json" if endpoint == fabric_server.PROJECT_SAVE_API else root / "autosave.json"
                self.assertEqual(payload["shapes"], json.loads(target.read_text())["shapes"])
            previous = target.read_bytes()
            for length in (limit + 1, 100 * 1024 * 1024 + 1, 0, -1, "invalid"):
                status, response = self.request(server, endpoint, length=length)
                self.assertEqual(400, status, response)
                self.assertEqual(previous, target.read_bytes(), "Rejected write altered the last good file")
            self.assertEqual([], list(root.rglob("*.tmp")))

    def test_project_exact_boundary_and_rejection_preserve_previous_file(self):
        self.check_boundary(fabric_server.PROJECT_SAVE_API)

    def test_recovery_exact_boundary_and_rejection_preserve_previous_file(self):
        self.check_boundary(fabric_server.EDITOR_AUTOSAVE_API)

    def test_failed_atomic_replace_keeps_last_complete_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "project.json"
            fabric_server._write_json_atomic(target, {"shapes": [1]})
            previous = target.read_bytes()
            with patch.object(fabric_server.os, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    fabric_server._write_json_atomic(target, {"shapes": [2]})
            self.assertEqual(previous, target.read_bytes())
            self.assertEqual([], list(target.parent.glob("*.tmp")))
