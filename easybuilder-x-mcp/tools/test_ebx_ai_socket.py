# -*- coding: utf-8 -*-
"""EBX Socket protocol tests (hoverwu / 0.1.0)."""
import json
import io
import os
import socket
import threading
import unittest
from unittest.mock import patch

import ebx_ai_socket as socket_client


class EBXSocketTests(unittest.TestCase):
    def serve_once(self, response):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        captured = []

        def worker():
            conn, _ = listener.accept()
            with conn:
                data = b""
                while b"\n" not in data:
                    data += conn.recv(4096)
                captured.append(json.loads(data.decode("utf-8")))
                conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
            listener.close()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return listener.getsockname()[1], captured, thread

    def test_call_uses_string_version_and_ndjson(self):
        port, captured, thread = self.serve_once(
            {"ok": True, "result": "pong", "schema_version": "1.4"})
        result = socket_client.EBXSocket(port=port, timeout=2).call("ping", {"probe": "中文"})
        thread.join(2)
        self.assertEqual(result["result"], "pong")
        self.assertEqual(captured, [{
            "schema_version": "1.4",
            "method": "ping",
            "params": {"probe": "中文"},
        }])

    def test_discovery_rejects_remote_or_malformed_entries(self):
        items = [
            {"host": "127.0.0.1", "port": 19001, "started_at": "2026-11-24T10:00:00"},
            {"host": "0.0.0.0", "port": 18778, "started_at": "2026-11-24T11:00:00"},
            {"host": "127.0.0.1", "port": "18779", "started_at": "2026-11-24T12:00:00"},
        ]

        def load(path, **kwargs):
            value = items[int(os.path.basename(path).split(".")[0])]
            if value["port"] == "18779":
                raise ValueError("bad port")
            return io.StringIO(json.dumps(value))

        with patch.object(socket_client, "registry_files", return_value=["0.json", "1.json", "2.json"]), \
                patch.object(socket_client, "open", side_effect=load, create=True):
            found = socket_client.discover_instances()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["port"], 19001)
        self.assertEqual(found[0]["registry_file"], "0.json")

    def test_require_ok_returns_result_and_reports_error(self):
        self.assertEqual(socket_client.require_ok({"ok": True, "result": {"x": 1}}), {"x": 1})
        with self.assertRaisesRegex(socket_client.EBXSocketError, "PROJECT_NOT_READY"):
            socket_client.require_ok({
                "ok": False,
                "error": {"code": "PROJECT_NOT_READY", "message": "打开工程后重试"},
            })


if __name__ == "__main__":
    unittest.main()
