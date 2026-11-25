# -*- coding: utf-8 -*-
"""分层 MCP 目录与代理调用测试（hoverwu / 0.1.0）。"""
import unittest

from fastmcp import Client, FastMCP

try:
    from .ebx_mcp_catalog import BOOTSTRAP_TOOLS, EBXCatalogTransform
except ImportError:
    from ebx_mcp_catalog import BOOTSTRAP_TOOLS, EBXCatalogTransform


class CatalogTransformTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mcp = FastMCP("catalog-test")

        @self.mcp.tool(tags={"domain:native"})
        def ebx_native_patch_apply(patch: dict, dry_run: bool = False) -> dict:
            """应用原生增量补丁；dry_run 只检查不写入。"""
            return {"ok": True, "dry_run": dry_run}

        @self.mcp.tool(tags={"domain:screen"})
        def ebx_screen_open(name: str) -> dict:
            """切换并打开指定画面。"""
            return {"ok": True, "screen": name}

        @self.mcp.tool(tags={"domain:project"})
        def ebx_status() -> dict:
            """返回 EasyBuilder X 运行状态。"""
            return {"ok": True, "running": True}

        self.mcp.add_transform(EBXCatalogTransform())
        self.client = Client(self.mcp)
        await self.client.__aenter__()

    async def asyncTearDown(self):
        await self.client.__aexit__(None, None, None)

    async def test_only_four_bootstrap_tools_are_listed(self):
        tools = await self.client.list_tools()
        self.assertEqual([tool.name for tool in tools], BOOTSTRAP_TOOLS)

    async def test_catalog_has_three_levels(self):
        root = (await self.client.call_tool("ebx_catalog", {})).data
        self.assertEqual(root["registered_tools"], 3)
        self.assertEqual({item["id"] for item in root["domains"]}, {"project", "screen", "native"})

        domain = (await self.client.call_tool("ebx_catalog", {"domain": "native"})).data
        self.assertEqual([item["name"] for item in domain["tools"]], ["ebx_native_patch_apply"])

        tool = (await self.client.call_tool(
            "ebx_catalog", {"domain": "native", "tool": "ebx_native_patch_apply"})).data
        self.assertTrue(tool["tool"]["input_schema"]["properties"]["dry_run"])

    async def test_chinese_english_and_exact_name_search(self):
        chinese = await self.client.call_tool("ebx_find_tools", {"query": "增量补丁"})
        self.assertTrue(chinese.data.startswith("### ebx_native_patch_apply"), chinese.data)
        english = await self.client.call_tool("ebx_find_tools", {"query": "screen", "domain": "screen"})
        self.assertIn("ebx_screen_open", english.data)
        exact = await self.client.call_tool("ebx_find_tools", {"query": "ebx_screen_open"})
        self.assertIn("ebx_screen_open", exact.data)

    async def test_proxy_and_legacy_direct_calls_work(self):
        proxied = (await self.client.call_tool("ebx_call_tool", {
            "name": "ebx_native_patch_apply", "arguments": {"patch": {}, "dry_run": True}})).data
        self.assertEqual(proxied, {"ok": True, "dry_run": True})
        direct = (await self.client.call_tool("ebx_screen_open", {"name": "主监控"})).data
        self.assertEqual(direct, {"ok": True, "screen": "主监控"})

    async def test_unknown_domain_and_tool_are_structured(self):
        domain = (await self.client.call_tool("ebx_catalog", {"domain": "missing"})).data
        self.assertEqual(domain["code"], "UNKNOWN_DOMAIN")
        tool = (await self.client.call_tool("ebx_catalog", {"tool": "ebx_missing"})).data
        self.assertEqual(tool["code"], "UNKNOWN_TOOL")


if __name__ == "__main__":
    unittest.main()
