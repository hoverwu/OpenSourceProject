# -*- coding: utf-8 -*-
"""Native patch MCP wrapper tests (hoverwu / 0.1.0)."""
import unittest
from unittest.mock import patch

import ebx_mcp_server as server


class NativePatchMCPTests(unittest.TestCase):
    def test_capture_delegates_to_native_patch_tool(self):
        document = {"schema": "ebx-native-patch/1.0", "screen": "测试画面"}
        with patch.object(server, "EBXSocket") as socket, \
                patch.object(server, "native_patch_capture", return_value=document) as capture:
            result = server.ebx_native_patch_capture("测试画面")
        self.assertEqual(result, document)
        socket.assert_called_once_with()
        self.assertEqual(capture.call_args.args[1], "测试画面")
        self.assertTrue(capture.call_args.args[2].replace("\\", "/").endswith("/out/ai_socket"))

    def test_apply_passes_dry_run_and_patch(self):
        document = {"schema": "ebx-native-patch/1.0", "screen": "测试画面", "operations": []}
        response = {"ok": True, "noop": True}
        with patch.object(server, "EBXSocket"), \
                patch.object(server, "native_patch_apply", return_value=response) as apply:
            result = server.ebx_native_patch_apply(document, dry_run=True)
        self.assertEqual(result, response)
        self.assertIs(apply.call_args.args[1], document)
        self.assertIs(apply.call_args.args[2], True)

    def test_empty_screen_is_rejected_without_socket(self):
        with patch.object(server, "EBXSocket") as socket:
            result = server.ebx_native_patch_capture("")
        self.assertEqual(result["code"], "INVALID_SCREEN")
        socket.assert_not_called()

    def test_native_errors_are_returned_as_structured_results(self):
        with patch.object(server, "EBXSocket"), \
                patch.object(server, "native_patch_apply", side_effect=server.PatchError("BAD_PATCH", "bad")):
            result = server.ebx_native_patch_apply({})
        self.assertEqual(result, {"ok": False, "code": "BAD_PATCH", "message": "bad"})

    def test_clone_delegates_names_and_options(self):
        response = {"ok": True, "dry_run": True}
        with patch.object(server, "EBXSocket"), \
                patch.object(server, "native_clone_screens", return_value=response) as clone:
            result = server.ebx_native_clone_screen("源画面", ["副本1", "副本2"], True, True)
        self.assertEqual(result, response)
        self.assertEqual(clone.call_args.args[1:5], ("源画面", ["副本1", "副本2"], True, True))
        self.assertTrue(clone.call_args.args[5].replace("\\", "/").endswith("/out/ai_socket"))

    def test_query_delegates_all_selector_forms(self):
        with patch.object(server, "EBXSocket"), \
                patch.object(server, "native_query_objects", return_value={"ok": True}) as query:
            server.ebx_native_query_objects(screen="源画面")
            self.assertEqual(query.call_args.args[1:], ("源画面", None, False))
            server.ebx_native_query_objects(screens=["画面1", "画面2"])
            self.assertEqual(query.call_args.args[1:], (None, ["画面1", "画面2"], False))
            server.ebx_native_query_objects(all_screens=True)
            self.assertEqual(query.call_args.args[1:], (None, None, True))

    def test_snapshot_delegates_screen(self):
        response = {"ok": True, "screen": "源画面"}
        with patch.object(server, "EBXSocket"), \
                patch.object(server, "native_capture_snapshot", return_value=response) as snapshot:
            result = server.ebx_native_snapshot("源画面")
        self.assertEqual(result, response)
        self.assertEqual(snapshot.call_args.args[1], "源画面")

    def test_reuse_input_errors_do_not_open_socket(self):
        with patch.object(server, "EBXSocket") as socket:
            self.assertEqual(server.ebx_native_clone_screen("", ["副本"])["code"], "INVALID_SCREEN")
            self.assertEqual(server.ebx_native_clone_screen("源画面", [])["code"], "INVALID_NAMES")
            self.assertEqual(server.ebx_native_snapshot("")["code"], "INVALID_SCREEN")
        socket.assert_not_called()

    def test_reuse_native_errors_are_structured(self):
        with patch.object(server, "EBXSocket"), \
                patch.object(server, "native_clone_screens", side_effect=server.PatchError("NAME_CONFLICT", "bad")):
            result = server.ebx_native_clone_screen("源画面", ["源画面"])
        self.assertEqual(result, {"ok": False, "code": "NAME_CONFLICT", "message": "bad"})


if __name__ == "__main__":
    unittest.main()
