# -*- coding: utf-8 -*-
"""Read-only smoke test for the localhost MCP bridge.

Author: hoverwu | Version: 0.2.0

Run from a normal (Medium-IL) terminal to verify the same integrity-level path
an MCP client uses. Without --require-sysmac the test only checks the HTTP
handshake, tool list and window enumeration; it can pass even when Sysmac
Studio is closed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from fastmcp import Client


def result_text(result) -> str:
    return "".join(part.text for part in result.content if getattr(part, "text", None))


async def check(port: int, require_sysmac: bool) -> int:
    # Avoid malformed NO_PROXY entries such as "[::1]" breaking loopback URLs.
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    url = f"http://127.0.0.1:{port}/mcp"

    async with Client(url) as client:
        tools = await client.list_tools()
        names = [tool.name for tool in tools]
        print(f"{url}\n  tools = {len(names)}: {', '.join(names)}")
        if not names:
            print("ERROR: server returned no tools")
            return 1

        raw = result_text(await client.call_tool("list_windows", {"filter": "", "include_hidden": False}))
        windows = json.loads(raw)
        if not isinstance(windows, list):
            print(f"ERROR: unexpected list_windows payload: {raw[:200]}")
            return 1
        hits = [w for w in windows if "sysmac" in str(w.get("title", "")).lower()]
        print(f"  list_windows -> {len(windows)} windows, Sysmac matches: {len(hits)}")
        if not hits:
            if require_sysmac:
                print("ERROR: no Sysmac Studio window visible. Open Sysmac Studio and ensure the server is elevated.")
                return 1
            print("  SKIP: Sysmac Studio window check (use --require-sysmac when the application is open)")
            return 0

        target = hits[0]
        tree_raw = result_text(
            await client.call_tool(
                "inspect_element_tree",
                {"element_id": target["elementId"], "max_depth": 4},
            )
        )
        tree = json.loads(tree_raw)
        if isinstance(tree, dict) and tree.get("error"):
            print(f"ERROR: inspect_element_tree failed: {tree['error']}")
            return 1
        print(f"  inspect_element_tree({target['elementId']}) -> {len(tree_raw)} chars")
        print("OK: Medium-IL client can read the Sysmac Studio UIA tree through the elevated bridge.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the Sysmac Studio UIA MCP bridge.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--require-sysmac", action="store_true", help="fail if no Sysmac Studio window is visible")
    args = parser.parse_args()
    try:
        return asyncio.run(check(args.port, args.require_sysmac))
    except Exception as exc:
        print(f"ERROR: {exc.__class__.__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())