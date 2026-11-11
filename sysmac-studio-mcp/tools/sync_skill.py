# -*- coding: utf-8 -*-
"""Sync the bundled Skill source to the Qoder user skills directory.

Author: hoverwu | Version: 0.1.0

Source of truth: <package>/skill
Destination:     %USERPROFILE%/.qoder-cn/skills/sysmac-studio-control

Usage:
    python tools/sync_skill.py
    python tools/sync_skill.py --check

The script copies files and verifies SHA-256. It does not delete extra files in
the destination; use a dedicated destination folder for this Skill.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "skill"
DST = Path.home() / ".qoder-cn" / "skills" / "sysmac-studio-control"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "logs", "*.log", "*.png", "*.jpg", "*.smc2", "*.slr")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if "__pycache__" in parts or "logs" in parts:
            continue
        if path.suffix.lower() in {".pyc", ".pyo", ".log", ".png", ".jpg", ".smc2", ".slr"}:
            continue
        out[rel] = sha256(path)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync bundled Sysmac Studio Skill to Qoder.")
    parser.add_argument("--check", action="store_true", help="compare only; do not copy")
    args = parser.parse_args()

    if not (SRC / "SKILL.md").is_file():
        print(json.dumps({"ok": False, "error": f"missing source: {SRC / 'SKILL.md'}"}, ensure_ascii=False))
        return 2

    src_manifest = manifest(SRC)
    dst_manifest = manifest(DST)
    if args.check:
        ok = src_manifest == dst_manifest
        print(json.dumps({"ok": ok, "src": str(SRC), "dst": str(DST), "files": len(src_manifest), "action": "none"}, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    DST.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC, DST, dirs_exist_ok=True, ignore=IGNORE)
    new_manifest = manifest(DST)
    ok = all(new_manifest.get(rel) == digest for rel, digest in src_manifest.items())
    print(json.dumps({"ok": ok, "src": str(SRC), "dst": str(DST), "files": len(src_manifest), "action": "copied"}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())