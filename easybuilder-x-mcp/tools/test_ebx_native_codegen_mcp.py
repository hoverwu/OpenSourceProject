# -*- coding: utf-8 -*-
"""原生生成/导入 MCP 薄封装测试（hoverwu / 0.1.0）。"""
import asyncio
import unittest
from unittest.mock import patch

import ebx_mcp_server as server


class NativeCodegenMCPTests(unittest.TestCase):
    def test_server_exposes_four_bootstrap_tools_and_tags_all_registered_tools(self):
        visible = asyncio.run(server.mcp.list_tools())
        self.assertEqual(
            [tool.name for tool in visible],
            ["ebx_status", "ebx_catalog", "ebx_find_tools", "ebx_call_tool"])
        registered = asyncio.run(server.mcp._local_provider._list_tools())
        self.assertEqual(len(registered), 31)
        self.assertTrue(all(any(tag.startswith("domain:") for tag in tool.tags) for tool in registered))

    def setUp(self):
        self.archive = {
            "header": {"schemaVersion": "1.1", "contentType": "view"},
            "body": {"screens": [{"name": "生成页", "objects": []}], "windows": []},
        }
        self.validation = {"ok": True, "elements": 0}

    def test_generate_delegates_without_socket(self):
        with patch.object(server, "native_prepare_archive", return_value=(self.archive, self.validation)) as prepare, \
                patch.object(server, "native_write_json") as write, \
                patch.object(server, "EBXSocket") as socket:
            result = server.ebx_native_generate(
                "examples/C2_Native_Sample.screen.json", "生成页", screens=["参数设定"], omit_text=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["archive"], self.archive)
        self.assertIs(prepare.call_args.args[1], "生成页")
        self.assertEqual(prepare.call_args.args[3], {"参数设定"})
        self.assertTrue(prepare.call_args.args[4])
        socket.assert_not_called()
        write.assert_called_once()
        self.assertTrue(write.call_args.args[0].endswith("C2_Native_Sample.native.json"))
        self.assertNotIn(".screen.native.json", write.call_args.args[0])

    def test_import_passes_dry_run_and_evidence(self):
        response = {"ok": True, "code": "DRY_RUN_OK"}
        with patch.object(server, "native_prepare_archive", return_value=(self.archive, self.validation)), \
                patch.object(server, "native_import_archive", return_value=response) as import_archive, \
                patch.object(server, "EBXSocket") as socket:
            result = server.ebx_native_import("input.json", dry_run=True, port=18777, evidence_dir="evidence")
        self.assertEqual(result, response)
        socket.assert_called_once_with(18777)
        self.assertEqual(import_archive.call_args.args[1], self.archive)
        self.assertTrue(import_archive.call_args.args[3])
        self.assertTrue(import_archive.call_args.args[2].replace("\\", "/").endswith("/evidence"))

    def test_prepare_failure_does_not_open_socket(self):
        failure = {"ok": False, "code": "INVALID_SCREEN_JSON"}
        with patch.object(server, "native_prepare_archive", return_value=(None, failure)), \
                patch.object(server, "EBXSocket") as socket:
            result = server.ebx_native_import("bad.json")
        self.assertEqual(result, failure)
        socket.assert_not_called()

    def test_native_errors_are_structured(self):
        with patch.object(server, "native_prepare_archive", return_value=(self.archive, self.validation)), \
                patch.object(server, "native_import_archive", side_effect=OSError("disk full")):
            result = server.ebx_native_import("input.json")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "IMPORT_ERROR")
        self.assertIn("disk full", result["message"])


if __name__ == "__main__":
    unittest.main()
