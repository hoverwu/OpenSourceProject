# -*- coding: utf-8 -*-
"""Portable release checks: no absolute machine paths, no binary artifacts, syntax OK.

Author: hoverwu | Version: 0.1.0
Run: python tools/check_release.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ABS_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")
# Standard Windows locations that are identical on every machine; documenting
# them (e.g. elevated cwd = %SystemRoot%\System32, Git Bash rewriting /FI) is
# portable knowledge, not machine-specific leakage.
SYSTEM_PATH = re.compile(
    r"(?<![A-Za-z0-9_])C:[\\/](?:Windows|Program Files(?: \(x86\))?)(?:[\\/\s\"'`)]|$)",
    re.IGNORECASE,
)
BAD_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".smc2", ".slr", ".zip", ".pyc", ".pyo", ".log"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "logs"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".bat", ".ps1", ".json", ".yaml", ".yml", ".gitignore"}


def iter_files():
    for path in sorted(BASE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(BASE)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield path, rel


def main() -> int:
    issues: list[str] = []
    for path, rel in iter_files():
        if path.suffix.lower() in BAD_SUFFIXES:
            issues.append(f"artifact: {rel.as_posix()}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(f"non-utf8 text file: {rel.as_posix()}")
            continue
        for number, line in enumerate(text.splitlines(), 1):
            scrubbed = SYSTEM_PATH.sub(lambda m: " " * len(m.group(0)), line)
            if ABS_PATH.search(scrubbed):
                issues.append(f"absolute path: {rel.as_posix()}:{number}: {line.strip()[:120]}")

    py_files = list((BASE / "skill" / "scripts").glob("*.py"))
    py_files += [BASE / "serve_http.py", BASE / "mcp_smoke_test.py"]
    py_files += list((BASE / "tools").glob("*.py"))
    for path in py_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            issues.append(f"Python syntax check failed: {path.relative_to(BASE).as_posix()}:{exc.lineno}: {exc.msg}")

    if issues:
        print("RELEASE CHECK FAILED")
        for issue in issues:
            print(" -", issue)
        return 1
    print("RELEASE CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())