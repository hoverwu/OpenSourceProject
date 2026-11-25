# -*- coding: utf-8 -*-
"""Native screen reuse tests (hoverwu / 0.1.0)."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ebx_native_reuse as reuse


def archive():
    return {
        "header": {"schemaVersion": "1.1", "contentType": "view", "appVersion": "test"},
        "body": {
            "screens": [{
                "name": "源画面", "groupPath": [], "availableLayers": ["root"],
                "properties": {"width": 1024, "height": 600}, "events": [], "conditions": [],
                "objects": [{"name": "标题", "objectType": "Text", "layer": "root", "properties": {"x": 10, "y": 20}, "events": [
                    {"id": "clicked", "statements": [{"type": "call", "method": "Method://<system>.changeScreen", "parameters": {"target": "Object://Screen:目标"}}]},
                ]}],
            }],
            "windows": [{"name": "公共窗口"}],
        },
    }


class FakeClient:
    def __init__(self, conflict=False, import_ok=True, snapshot=True):
        self.source = archive()
        self.conflict = conflict
        self.import_ok = import_ok
        self.snapshot = snapshot
        self.calls = []
        self.imported = []
        self.snapshot_path = None

    def call(self, method, params=None):
        params = params or {}
        self.calls.append((method, copy.deepcopy(params)))
        if method == "exportScreenView":
            return {"ok": True, "result": {"archive": copy.deepcopy(self.source)}}
        if method == "detectImportConflicts":
            return {"ok": True, "result": {"has_conflicts": self.conflict, "conflict_count": int(self.conflict), "conflicts": []}}
        if method == "importScreenView":
            if not self.import_ok:
                return {"ok": True, "result": {"success": False, "changeset_result": {"all_ok": False, "per_operation": []}}}
            self.imported = copy.deepcopy(params["archive"]["body"]["screens"])
            return {"ok": True, "result": {"success": True, "changeset_result": {"all_ok": True, "missing_references": [], "per_operation": [
                {"success": True, "unresolved_references": []} for _ in self.imported
            ]}}}
        if method == "getViewByScreenName":
            screen = next((item for item in self.imported if item["name"] == params["screen_name"]), None)
            if screen is None:
                return {"ok": False, "error": {"code": "SCREEN_NOT_FOUND", "message": params["screen_name"]}}
            return {"ok": True, "result": {"screen": copy.deepcopy(screen)}}
        if method == "queryObjects":
            return {"ok": True, "result": {"objects": [{"name": "标题", "objectDescription": "Text", "x": 10, "y": 20}]}}
        if method == "getSnapshot":
            if not self.snapshot:
                return {"ok": True, "result": {"absolute_path": ""}}
            path = Path(self.temp.name) / "screen.png"
            path.write_bytes(b"png-data")
            self.snapshot_path = path
            return {"ok": True, "result": {"absolute_path": str(path), "file_name": path.name}}
        raise AssertionError(method)

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory()
        return self

    def __exit__(self, *args):
        self.temp.cleanup()


class NativeReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_clone_archive_preserves_windows_and_source(self):
        source = archive()
        result = reuse.clone_archive(source, ["副本1", "副本2"])
        self.assertEqual([item["name"] for item in result["body"]["screens"]], ["副本1", "副本2"])
        self.assertEqual(result["body"]["windows"], source["body"]["windows"])
        self.assertEqual(result["body"]["screens"][0]["objects"][0]["events"], source["body"]["screens"][0]["objects"][0]["events"])
        self.assertEqual(source["body"]["screens"][0]["name"], "源画面")

    def test_dry_run_does_not_import_or_snapshot(self):
        with FakeClient() as client:
            result = reuse.clone_screens(client, "源画面", ["副本"], True, True, self.temp.name)
            self.assertTrue(result["ok"])
            self.assertEqual(client.imported, [])
            self.assertFalse(any(method == "getSnapshot" for method, _ in client.calls))

    def test_bulk_clone_verifies_each_screen(self):
        with FakeClient() as client:
            result = reuse.clone_screens(client, "源画面", ["副本1", "副本2"], False, False, self.temp.name)
            self.assertTrue(result["ok"])
            self.assertEqual(result["objects_per_screen"], 1)
            self.assertTrue(all(item["ok"] for item in result["verification"]))
            self.assertEqual(len(client.imported), 2)
            self.assertTrue(list(Path(self.temp.name).glob("native_clone_*_evidence.json")))

    def test_conflict_prevents_import(self):
        with FakeClient(conflict=True) as client:
            result = reuse.clone_screens(client, "源画面", ["副本"], False, False, self.temp.name)
            self.assertEqual(result["code"], "IMPORT_CONFLICT")
            self.assertEqual(client.imported, [])

    def test_failed_import_is_not_reported_as_success(self):
        with FakeClient(import_ok=False) as client:
            result = reuse.clone_screens(client, "源画面", ["副本"], False, False, self.temp.name)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "CLONE_VERIFY_FAILED")

    def test_duplicate_and_source_names_are_rejected(self):
        with self.assertRaises(reuse.PatchError):
            reuse.normalize_names(["副本", "副本"])
        with self.assertRaises(reuse.PatchError):
            reuse.normalize_names(["a/b"])
        with FakeClient() as client:
            with self.assertRaises(reuse.PatchError):
                reuse.clone_screens(client, "源画面", ["源画面"])

    def test_snapshot_is_copied_with_hash(self):
        with FakeClient() as client:
            result = reuse.capture_snapshot(client, "源画面", self.temp.name)
            self.assertTrue(result["ok"])
            self.assertEqual(Path(result["path"]).read_bytes(), b"png-data")
            self.assertEqual(len(result["sha256"]), 64)

    def test_snapshot_failure_does_not_hide_successful_clone(self):
        with FakeClient(snapshot=False) as client:
            result = reuse.clone_screens(client, "源画面", ["副本"], False, True, self.temp.name)
        self.assertTrue(result["ok"])
        self.assertFalse(result["snapshots"][0]["ok"])
        self.assertEqual(result["snapshots"][0]["code"], "SNAPSHOT_MISSING")

    def test_missing_snapshot_is_rejected(self):
        with FakeClient(snapshot=False) as client:
            with self.assertRaises(reuse.PatchError):
                reuse.capture_snapshot(client, "源画面", self.temp.name)

    def test_query_requires_exactly_one_selector(self):
        with FakeClient() as client:
            with self.assertRaises(reuse.PatchError):
                reuse.query_objects(client)
            result = reuse.query_objects(client, screen="源画面")
            self.assertTrue(result["ok"])
            self.assertEqual(result["objects"][0]["name"], "标题")
            self.assertEqual(client.calls[-1][1], {"screen_name": "源画面"})
            reuse.query_objects(client, screens=["源画面", "副本"])
            self.assertEqual(client.calls[-1][1], {"screen_names": ["源画面", "副本"]})
            reuse.query_objects(client, all_screens=True)
            self.assertEqual(client.calls[-1][1], {"all_screens": True})

    def test_package_import_resolves_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-c", "from tools.ebx_native_reuse import normalize_names; assert normalize_names(['x']) == ['x']"],
            cwd=root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
