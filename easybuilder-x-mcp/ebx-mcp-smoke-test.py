# -*- coding: utf-8 -*-
"""ebx-mcp-smoke-test.py - EasyBuilder X 专用 MCP 服务器只读自检（hoverwu / 0.2.0）

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
        print("tools(%d): %s" % (len(names), ", ".join(sorted(names))))
        for name, args in READONLY_CALLS:
            r = await c.call_tool(name, args)
            data = r.data if r.data is not None else (r.content[0].text if r.content else "")
            text = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
            print("== %s: %s" % (name, text[:600]))
        print("SMOKE OK")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    asyncio.run(main(port))
