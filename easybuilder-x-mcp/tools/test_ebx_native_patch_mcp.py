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


if __name__ == "__main__":
    unittest.main()
