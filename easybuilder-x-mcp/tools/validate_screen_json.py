# -*- coding: utf-8 -*-
"""validate_screen_json.py - 校验 ebx-screen/1.0 画面 JSON 是否自洽（hoverwu / 0.1.0）

用法:
  python tools/validate_screen_json.py out/Alarm_Trend.screen.json [--screens 报警与趋势,主监控,...]

检查项:
  1. schema 与 screen.element_count 一致；
  2. id / name 唯一；
  3. 每个元素的 tag 都在 tags[] 里，且 used_tags 与元素实际用到的集合一致；
  4. 所有元素落在画面边界内；
  5. switch_screen 任务的目标画面存在（给了 --screens 时）；
  6. type / ebx_kind 在已知枚举内。
退出码 0 = 全部通过；1 = 有问题（打印明细）。
"""
import json
import os
import sys

KNOWN_TYPES = {"static_text", "numeric_display", "indicator", "button"}


def validate(path, screens=None):
    errors = []
    data = json.load(open(path, encoding="utf-8"))
    if data.get("schema") != "ebx-screen/1.0":
        errors.append("schema 不是 ebx-screen/1.0: %r" % (data.get("schema"),))
    scr = data.get("screen") or {}
    els = scr.get("elements") or []
    W, H = scr.get("width", 0), scr.get("height", 0)
    if scr.get("element_count") != len(els):
        errors.append("element_count=%r 与实际 %d 不一致" % (scr.get("element_count"), len(els)))

    ids = [e.get("id") for e in els]
    names = [e.get("name") for e in els]
    if len(set(ids)) != len(ids):
        errors.append("id 有重复: %s" % sorted({i for i in ids if ids.count(i) > 1}))
    if len(set(names)) != len(names):
        errors.append("name 有重复: %s" % sorted({n for n in names if names.count(n) > 1}))

    tagset = {t.get("name") for t in (data.get("tags") or [])}
    used = {e["tag"] for e in els if e.get("tag")}
    missing = sorted(used - tagset)
    if missing:
        errors.append("元素引用了未定义的标签: %s" % missing)
    declared = set(data.get("used_tags") or [])
    if used != declared:
        errors.append("used_tags 不一致: 多 %s / 少 %s" % (sorted(declared - used), sorted(used - declared)))

    for e in els:
        if e.get("type") not in KNOWN_TYPES:
            errors.append("未知 type: %r (%s)" % (e.get("type"), e.get("id")))
        x, y, w, h = e.get("x", 0), e.get("y", 0), e.get("w", 0), e.get("h", 0)
        if x < 0 or y < 0 or x + w > W or y + h > H:
            errors.append("越界: %s (%s) [%s,%s,%s,%s] 画面 %dx%d"
                          % (e.get("name"), e.get("id"), x, y, w, h, W, H))
        task = e.get("task")
        if task:
            if task.get("type") != "switch_screen":
                errors.append("未知 task.type: %r (%s)" % (task.get("type"), e.get("id")))
            if screens and task.get("target") not in screens:
                errors.append("任务目标画面不存在: %r (%s)" % (task.get("target"), e.get("id")))

    return {
        "file": path,
        "ok": not errors,
        "screen": scr.get("name"),
        "elements": len(els),
        "tags": len(tagset),
        "used_tags": len(used),
        "tasks": sum(1 for e in els if e.get("task")),
        "errors": errors,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    screens = None
    if "--screens" in sys.argv:
        screens = {s.strip() for s in sys.argv[sys.argv.index("--screens") + 1].split(",") if s.strip()}
    if not os.path.isfile(path):
        print("[ERR] 文件不存在: %s" % path)
        return 2
    res = validate(path, screens)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
