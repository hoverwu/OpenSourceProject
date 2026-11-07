# -*- coding: utf-8 -*-
"""sync_skill.py - 把项目内的 Skill 源稿同步到 Qoder 用户目录（hoverwu / 0.1.0）

源稿（唯一事实源，跟 MCP 放在一起，便于整体打包）:
  <项目根>\\SKILL.md
部署位置（Qoder 实际加载）:
  %USERPROFILE%\\.qoder-cn\\skills\\easybuilder-x-mcp\\SKILL.md

用法:
  python tools/sync_skill.py           # 复制并校验 sha256
  python tools/sync_skill.py --check   # 只比较，不一致返回 1（适合打包前检查）

说明:
  两边是"源稿 + 部署副本"关系，不要反向编辑部署副本；改完源稿跑一次本脚本。
"""
import hashlib
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "SKILL.md")
DST = os.path.join(os.path.expanduser("~"), ".qoder-cn", "skills", "easybuilder-x-mcp", "SKILL.md")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    check_only = "--check" in sys.argv
    if not os.path.isfile(SRC):
        print(json.dumps({"ok": False, "error": "源稿不存在: %s" % SRC}, ensure_ascii=False))
        return 2
    src_hash = sha256(SRC)
    if os.path.isfile(DST):
        dst_hash = sha256(DST)
    else:
        dst_hash = None

    if check_only:
        ok = src_hash == dst_hash
        print(json.dumps({"ok": ok, "src": SRC, "dst": DST,
                          "src_sha256": src_hash, "dst_sha256": dst_hash,
                          "action": "none"}, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    shutil.copyfile(SRC, DST)
    new_hash = sha256(DST)
    ok = new_hash == src_hash
    print(json.dumps({"ok": ok, "src": SRC, "dst": DST,
                      "sha256": new_hash, "bytes": os.path.getsize(DST),
                      "action": "copied"}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
