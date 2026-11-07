# -*- coding: utf-8 -*-
"""mcp_call_once.py - 调一次 EBX MCP 工具并打印结果（hoverwu / 0.1.0）

用法:
  python tools/mcp_call_once.py <tool> ['{"k": v}'] [port]

示例:
  python tools/mcp_call_once.py ebx_screen_list
  python tools/mcp_call_once.py ebx_import_screen_json "{\"json_path\":\"out/Alarm_Trend.screen.json\",\"screen\":\"临时_导入测试\",\"limit\":1,\"no_bind\":true,\"no_nav\":true,\"no_save\":true,\"wait\":180}"

说明: 本机 NO_PROXY 里带 [::1]，httpx 会抛 InvalidURL，所以启动前清空该变量。
"""
import asyncio
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

from fastmcp import Client


async def main(tool, args, port):
    async with Client("http://127.0.0.1:%d/mcp" % port) as c:
        r = await c.call_tool(tool, args)
        d = r.data if r.data is not None else (r.content[0].text if r.content else "")
        print(d if isinstance(d, str) else json.dumps(d, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].strip() else {}
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8788
    os.chdir(BASE)
    asyncio.run(main(tool, args, port))
