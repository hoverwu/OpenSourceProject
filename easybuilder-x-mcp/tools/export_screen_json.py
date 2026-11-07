#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""export_screen_json.py - 把 EBX 画面导出成可移植 JSON（hoverwu / 0.1.0 / 2026-11-07）

数据源：work/hmi_spec.json（本工程构建规格，与工程内实际落点一致） + work/tags/PipeTags.txt。
输出：out/<screen>.screen.json（UTF-8，无 BOM）。

用法:
  python tools/export_screen_json.py 报警与趋势
  python tools/export_screen_json.py 报警与趋势 out/Alarm_Trend.screen.json
"""
import json
import os
import sys
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECP = os.path.join(BASE, "work", "hmi_spec.json")
TAGP = os.path.join(BASE, "work", "tags", "PipeTags.txt")
OUTDIR = os.path.join(BASE, "out")

# 导航键：与 nav_build.py 实测一致（右侧按钮条）
NAV_Y, NAV_H, NAV_W = 548, 38, 140
NAV_X = [520, 672, 824]
SCREENS = ["报警与趋势", "主监控", "参数设定", "手动维护"]

TYPE_MAP = {
    "文本": "static_text",
    "数值": "numeric_display",
    "指示灯": "indicator",
    "按钮": "button",
}


def load_tags():
    raw = open(TAGP, "rb").read()
    text = None
    for enc in ("utf-8-sig", "gbk", "cp936"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("无法解码标签文件")
    lines = [l for l in text.splitlines() if l.strip()]
    head = lines[0].split("\t")
    tags = []
    for line in lines[1:]:
        cols = line.split("\t")
        cols += [""] * (len(head) - len(cols))
        row = dict(zip(head, cols))
        name = row.get("NAME", "").strip()
        if not name:
            continue
        tags.append({
            "name": name,
            "data_type": row.get("DATATYPE", "").strip(),
            "address": row.get("ADDRESS", "").strip(),
            "comment": row.get("COMMENT", "").strip(),
            "rw": row.get("RW", "").strip(),
            "scope": "GlobalVariables",
            "addressing": "CIP variable name",
        })
    return tags


def export(screen, outpath):
    spec = json.load(open(SPECP, encoding="utf-8"))
    if screen not in spec:
        raise SystemExit("画面不存在: %s（可选: %s）" % (screen, ", ".join(spec)))
    tags = load_tags()
    tag_index = {t["name"]: t for t in tags}

    elements = []
    used = []
    for i, el in enumerate(spec[screen], 1):
        kind = el["k"]
        item = {
            "id": "e%02d" % i,
            "type": TYPE_MAP.get(kind, kind),
            "ebx_kind": kind,
            "name": el["name"],
            "x": el["x"],
            "y": el["y"],
            "w": el.get("w", 100),
            "h": el.get("h", 40),
        }
        if el.get("text"):
            item["text"] = el["text"]
        if el.get("tag"):
            item["tag"] = el["tag"]
            item["readonly"] = bool(el.get("ro", False))
            used.append(el["tag"])
            if el["tag"] not in tag_index:
                item["warning"] = "标签表中缺少该变量"
        elements.append(item)

    # 导航键（每个画面 3 个，指向其他画面）
    nav = []
    others = [s for s in SCREENS if s != screen]
    for i, target in enumerate(others):
        nav.append({
            "id": "n%02d" % (i + 1),
            "type": "button",
            "ebx_kind": "按钮",
            "name": "nav_" + target,
            "x": NAV_X[i],
            "y": NAV_Y,
            "w": NAV_W,
            "h": NAV_H,
            "label": target,
            "task": {"type": "switch_screen", "target": target},
        })
    elements.extend(nav)

    data = {
        "schema": "ebx-screen/1.0",
        "generator": {
            "tool": "EasyBuilder X UIA bridge",
            "version": "0.1.0",
            "author": "hoverwu",
            "exported_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "source_project": "PipeHeating_HMI.ebxprj",
        "target": {
            "software": "EasyBuilder X V1.01.376s",
            "model": "cMT3075XH",
            "width": 1024,
            "height": 600,
            "zoom": 100,
        },
        "device": {
            "name": "PLC_NX502",
            "driver": "Omron EtherNet/IP (NJ/NX Series)",
            "ip": "192.168.250.1",
            "addressing": "CIP 变量名（GlobalVariables）",
        },
        "screen": {
            "name": screen,
            "comment": "",
            "width": 1024,
            "height": 600,
            "background": "default",
            "element_count": len(elements),
            "elements": elements,
        },
        "tags": tags,
        "used_tags": sorted(set(used + [])),
        "import": {
            "native_json_support": False,
            "note": "EasyBuilder X V1.01.376 没有画面级 JSON 导入（画面树只有 插入/复制/粘贴）。"
                    "本文件需用 ebx_screen_importer.py 通过 UIA 重建，或在源工程里复制画面后粘贴。",
            "requirements": [
                "Windows + EasyBuilder X V1.01.376s，已打开目标工程并最大化到 1920x1080（画布缩放 100%）",
                "目标工程已添加设备 PLC_NX502（Omron EtherNet/IP NJ/NX），并导入同名变量标签",
                "Python 3.8+ 与 uiautomation 2.x（pip install uiautomation）",
            ],
            "style_policy": "字体/颜色/对齐/数值格式均为 EBX 默认值（Noto Sans 16、黑色、居中），"
                            "导入器不改这些属性，因此与源画面一致。",
        },
    }

    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    with open(outpath, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return data, outpath


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    screen = sys.argv[1]
    outpath = sys.argv[2] if len(sys.argv) > 2 else os.path.join(OUTDIR, "Alarm_Trend.screen.json")
    data, path = export(screen, outpath)
    counts = {}
    for el in data["screen"]["elements"]:
        counts[el["type"]] = counts.get(el["type"], 0) + 1
    print(json.dumps({
        "out": path,
        "screen": screen,
        "elements": data["screen"]["element_count"],
        "by_type": counts,
        "tags": len(data["tags"]),
        "used_tags": len(data["used_tags"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
