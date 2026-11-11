# -*- coding: utf-8 -*-
"""Localhost HTTP bridge for uiautomation-mcp.

Author: hoverwu | Version: 0.2.0

Sysmac Studio may run at High integrity level. A stdio MCP server spawned by a
Medium-IL client inherits Medium IL and cannot read its UIA tree (UIPI). This
wrapper runs the same MCP server over a loopback HTTP socket, so a Medium-IL
client can talk to an elevated server.

Usage:
    python serve_http.py --port 8765

The server binds 127.0.0.1 only and does not accept remote hosts. This bridge
adds no telemetry of its own. By default it refuses to start without
administrator rights; use --allow-medium only when the target application
itself is not elevated.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run uiautomation-mcp on localhost HTTP.")
    parser.add_argument("--port", type=int, default=8765, help="TCP port (default: 8765)")
    parser.add_argument(
        "--allow-medium",
        action="store_true",
        help="allow startup without administrator rights (only for non-elevated target apps)",
    )
    args = parser.parse_args(argv)

    if os.name != "nt":
        parser.error("this bridge is Windows-only")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    admin = is_admin()
    if not admin and not args.allow_medium:
        print(
            "ERROR: administrator rights are required to inspect an elevated Sysmac Studio window.\n"
            "Run start-mcp.bat and approve UAC, or pass --allow-medium only for non-elevated targets.",
            file=sys.stderr,
        )
        return 2

    try:
        from uiautomation_mcp.server import mcp
    except ImportError as exc:
        print(
            f"ERROR: cannot import uiautomation_mcp ({exc}).\n"
            "Install dependencies first: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    level = "High" if admin else "Medium"
    print(
        f"uiautomation-mcp ({level} IL) listening on http://127.0.0.1:{args.port}/mcp",
        flush=True,
    )
    try:
        mcp.run(transport="http", host="127.0.0.1", port=args.port, show_banner=False)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())