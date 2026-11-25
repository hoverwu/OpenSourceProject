# -*- coding: utf-8 -*-
"""同步项目 Skill 源稿与 references 到 Qoder 用户目录（hoverwu / 0.2.0）。

源稿开发布局：
  <项目根>\\SKILL.md
  <项目根>\\EASYBUILDERX-UIA-AGENT-GUIDE.md
  <项目根>\\EBX-MCP-CONTROL-PLAN.md
  <项目根>\\RESEARCH-LEDGER.md

发布包布局：
  <包根>\\SKILL.md
  <包根>\\references\\<三份手册>

部署位置：
  %USERPROFILE%\\.qoder-cn\\skills\\easybuilder-x-mcp\\

用法：
  python tools/sync_skill.py           # 复制并校验 sha256
  python tools/sync_skill.py --check   # 只比较，不一致返回 1
"""
import hashlib
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST_ROOT = os.path.join(os.path.expanduser("~"), ".qoder-cn", "skills", "easybuilder-x-mcp")
REFERENCE_FILES = (
    "EASYBUILDERX-UIA-AGENT-GUIDE.md",
    "EBX-MCP-CONTROL-PLAN.md",
    "RESEARCH-LEDGER.md",
)


def skill_files(base=None):
    base = base or BASE
    references = os.path.join(base, "references")
    if not os.path.isdir(references):
        references = base
    files = [("SKILL.md", os.path.join(base, "SKILL.md"))]
    files.extend(
        ("references/" + name, os.path.join(references, name))
        for name in REFERENCE_FILES
    )
    return files


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(base=None, destination=None):
    records = []
    for relative, source in skill_files(base):
        target = os.path.join(destination or DST_ROOT, *relative.split("/"))
        records.append({
            "path": relative,
            "src": source,
            "dst": target,
            "src_sha256": sha256(source) if os.path.isfile(source) else None,
            "dst_sha256": sha256(target) if os.path.isfile(target) else None,
        })
    return records


def main():
    check_only = "--check" in sys.argv
    try:
        before = snapshot()
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    missing = [record["src"] for record in before if record["src_sha256"] is None]
    if missing:
        print(json.dumps({"ok": False, "error": "源文件不存在", "missing": missing}, ensure_ascii=False))
        return 2
    if check_only:
        ok = all(record["src_sha256"] == record["dst_sha256"] for record in before)
        print(json.dumps({
            "ok": ok,
            "src_root": BASE,
            "dst_root": DST_ROOT,
            "files": before,
            "action": "none",
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    try:
        for relative, source in skill_files():
            target = os.path.join(DST_ROOT, *relative.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        after = snapshot()
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    ok = all(record["src_sha256"] == record["dst_sha256"] for record in after)
    print(json.dumps({
        "ok": ok,
        "src_root": BASE,
        "dst_root": DST_ROOT,
        "files": after,
        "action": "copied",
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
