# -*- coding: utf-8 -*-
"""validate_screen_json.py - 校验 ebx-screen/1.0 画面 JSON 是否自洽（hoverwu / 0.1.0）

用法:
  python tools/validate_screen_json.py out/Alarm_Trend.screen.json [--screens 报警与趋势,主监控,...]

退出码 0 = 全部通过；1 = 有问题；2 = 文件或参数错误。
"""
import argparse
import json
import math
import sys

KNOWN_TYPES = {"static_text", "numeric_display", "indicator", "button"}
KNOWN_KINDS = {"文本", "数值", "指示灯", "按钮"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _required_text(value):
    return isinstance(value, str) and bool(value.strip())


def validate(path, screens=None):
    errors = []
    warnings = []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"file": path, "ok": False, "screen": None, "elements": 0,
                "tags": 0, "used_tags": 0, "tasks": 0, "errors": ["根节点必须是对象"],
                "warnings": warnings}
    if data.get("schema") != "ebx-screen/1.0":
        errors.append("schema 不是 ebx-screen/1.0: %r" % (data.get("schema"),))

    scr = data.get("screen")
    if not isinstance(scr, dict):
        scr = {}
        errors.append("screen 必须是对象")
    els = scr.get("elements")
    if not isinstance(els, list):
        els = []
        errors.append("screen.elements 必须是数组")
    W, H = scr.get("width"), scr.get("height")
    if not _number(W) or W <= 0:
        errors.append("screen.width 必须是正数")
    if not _number(H) or H <= 0:
        errors.append("screen.height 必须是正数")
    if not _required_text(scr.get("name")):
        errors.append("screen.name 必须是非空字符串")
    if scr.get("element_count") != len(els):
        errors.append("element_count=%r 与实际 %d 不一致" % (scr.get("element_count"), len(els)))

    ids = []
    names = []
    for e in els:
        if not isinstance(e, dict):
            errors.append("元件必须是对象")
            continue
        eid, name = e.get("id"), e.get("name")
        if not _required_text(eid):
            errors.append("元件 id 必须是非空字符串")
        elif eid in ids:
            errors.append("id 重复: %s" % eid)
        else:
            ids.append(eid)
        if not _required_text(name):
            errors.append("元件 name 必须是非空字符串")
        elif name in names:
            errors.append("name 重复: %s" % name)
        else:
            names.append(name)

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
        errors.append("tags 必须是数组")
    tag_names = set()
    addresses = set()
    for tag in tags:
        if not isinstance(tag, dict) or not _required_text(tag.get("name")):
            errors.append("标签 name 必须是非空字符串")
            continue
        name = tag["name"]
        if name in tag_names:
            errors.append("标签 name 重复: %s" % name)
        tag_names.add(name)
        address = tag.get("address")
        if address is not None and not isinstance(address, str):
            errors.append("标签 address 必须是字符串: %s" % name)
        elif address:
            if address in addresses:
                errors.append("标签 address 重复: %s" % address)
            addresses.add(address)

    used = set()
    tasks = 0
    for e in els:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        if e.get("type") not in KNOWN_TYPES:
            errors.append("未知 type: %r (%s)" % (e.get("type"), eid))
        kind = e.get("ebx_kind")
        if kind is not None and kind not in KNOWN_KINDS:
            errors.append("未知 ebx_kind: %r (%s)" % (kind, eid))
        x, y, w, h = (e.get(k) for k in ("x", "y", "w", "h"))
        if not all(_number(v) for v in (x, y, w, h)):
            errors.append("几何值必须是有限数字: %s" % eid)
        else:
            if w <= 0 or h <= 0:
                errors.append("宽高必须为正数: %s" % eid)
            if _number(W) and _number(H) and (x < 0 or y < 0 or x + w > W or y + h > H):
                errors.append("越界: %s (%s) [%s,%s,%s,%s] 画面 %sx%s"
                              % (e.get("name"), eid, x, y, w, h, W, H))
        if e.get("readonly") is not None and not isinstance(e["readonly"], bool):
            errors.append("readonly 必须是布尔值: %s" % eid)
        if e.get("tag"):
            if not _required_text(e["tag"]):
                errors.append("tag 必须是非空字符串: %s" % eid)
            else:
                used.add(e["tag"])
        task = e.get("task")
        if task is not None:
            tasks += 1
            if e.get("type") != "button":
                errors.append("task 只允许出现在 button 上: %s" % eid)
            if not isinstance(task, dict):
                errors.append("task 必须是对象: %s" % eid)
                continue
            if task.get("type") != "switch_screen":
                errors.append("未知 task.type: %r (%s)" % (task.get("type"), eid))
            target = task.get("target")
            if not _required_text(target):
                errors.append("task.target 必须是非空字符串: %s" % eid)
            elif screens is not None and target not in screens:
                errors.append("任务目标画面不存在: %r (%s)" % (target, eid))

    missing = sorted(used - tag_names)
    if missing:
        errors.append("元素引用了未定义的标签: %s" % missing)
    declared = data.get("used_tags")
    if not isinstance(declared, list) or not all(_required_text(t) for t in declared):
        errors.append("used_tags 必须是非空字符串数组")
        declared = declared if isinstance(declared, list) else []
    declared_set = set(declared)
    if used != declared_set:
        errors.append("used_tags 不一致: 多 %s / 少 %s" % (sorted(declared_set - used), sorted(used - declared_set)))
    if tasks and screens is None:
        warnings.append("未提供 --screens，未校验导航目标是否存在")

    return {
        "file": path,
        "ok": not errors,
        "screen": scr.get("name"),
        "elements": len(els),
        "tags": len(tag_names),
        "used_tags": len(used),
        "tasks": tasks,
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="校验 ebx-screen/1.0 画面 JSON")
    parser.add_argument("path")
    parser.add_argument("--screens", help="逗号分隔的现有画面名")
    args = parser.parse_args()
    screens = None
    if args.screens is not None:
        screens = {s.strip() for s in args.screens.split(",") if s.strip()}
    try:
        res = validate(args.path, screens)
    except (OSError, json.JSONDecodeError) as exc:
        print("[ERR] %s" % exc)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
