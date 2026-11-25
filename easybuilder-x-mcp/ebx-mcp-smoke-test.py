# -*- coding: utf-8 -*-
"""ebx-mcp-smoke-test.py - EasyBuilder X 专用 MCP 服务器只读自检（hoverwu / 0.6.0）

用法:
  python ebx-mcp-smoke-test.py [port]

注意: 若 NO_PROXY/no_proxy 里含 [::1]，httpx 会抛 InvalidURL: Invalid port: ':1]'，
      脚本启动时已清空这两个变量；手工用 curl/其它客户端时请自行 unset。
"""
import asyncio
import json
import os
import sys

os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

from fastmcp import Client

READONLY_CALLS = (
    ("ebx_status", {}),
    ("ebx_screen_list", {}),
    ("ebx_screen_elements", {}),
    ("ebx_uia_dump", {"scope": "popups", "max_depth": 5, "max_lines": 80}),
    ("ebx_import_status", {}),
    ("ebx_ribbon_map", {}),
    ("ebx_windows", {}),
)


async def main(port):
    url = "http://127.0.0.1:%d/mcp" % port
    async with Client(url) as c:
        tools = await c.list_tools()
        names = [t.name for t in tools]
        expected = ["ebx_status", "ebx_catalog", "ebx_find_tools", "ebx_call_tool"]
        assert names == expected, (names, expected)
        print("bootstrap(%d): %s" % (len(names), ", ".join(names)))

        catalog = (await c.call_tool("ebx_catalog", {})).data
        assert catalog["registered_tools"] >= 31, catalog
        assert "native" in {item["id"] for item in catalog["domains"]}, catalog
        print("== catalog: %d tools / %d domains" % (
            catalog["registered_tools"], len(catalog["domains"])))

        native = (await c.call_tool("ebx_catalog", {"domain": "native"})).data
        native_names = {item["name"] for item in native["tools"]}
        assert {"ebx_native_generate", "ebx_native_import", "ebx_native_patch_apply"} <= native_names
        schema = (await c.call_tool("ebx_catalog", {"tool": "ebx_native_import"})).data
        assert "json_path" in schema["tool"]["input_schema"]["properties"]
        print("== native catalog: %s" % ", ".join(sorted(native_names)))

        found = (await c.call_tool("ebx_find_tools", {"query": "增量补丁"})).data
        assert "ebx_native_patch_apply" in found, found
        print("== search: %s" % found.splitlines()[0])

        proxied = await c.call_tool("ebx_call_tool", {
            "name": "ebx_ribbon_map", "arguments": {}})
        proxied_data = proxied.data if proxied.data is not None else (proxied.content[0].text if proxied.content else "")
        assert proxied_data, proxied
        print("== proxy: ebx_ribbon_map ok")

        for name, args in READONLY_CALLS:
            r = await c.call_tool(name, args)
            data = r.data if r.data is not None else (r.content[0].text if r.content else "")
            text = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
            print("== %s: %s" % (name, text[:600]))
        print("SMOKE OK")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    asyncio.run(main(port))
