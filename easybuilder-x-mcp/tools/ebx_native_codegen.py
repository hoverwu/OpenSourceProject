# -*- coding: utf-8 -*-
"""把 ebx-screen/1.0 转为 EBX 原生 Screen View 并导入（hoverwu / 0.1.0）。"""
import argparse
import json
import os
import sys
import time

from ebx_ai_socket import EBXSocket, EBXSocketError, require_ok
from validate_screen_json import validate

TYPE_MAP = {
    "static_text": "Text",
    "numeric_display": "Numeric",
    "indicator": "Lamp",
    "button": "Button",
}


def variable_reference(tag, variable_scope):
    if tag.startswith("Variable://"):
        return tag
    return "Variable://%s/%s" % (variable_scope, tag)


def change_screen_statement(target):
    return {
        "type": "call",
        "method": "Method://<system>.changeScreen",
        "parameters": {
            "target": "Object://Screen:%s" % target,
            "animation": {"effect": "none"},
        },
    }


def convert(data, screen_name=None, variable_scope="Project", screens=None, omit_text=False):
    source_screen = data["screen"]
    elements = source_screen["elements"]
    objects = []
    for element in elements:
        object_type = TYPE_MAP[element["type"]]
        properties = {
            "x": element["x"],
            "y": element["y"],
            "width": element["w"],
            "height": element["h"],
        }
        if not omit_text and "text" in element:
            properties["text"] = element["text"]
        if object_type in ("Numeric", "Lamp") and element.get("tag"):
            field = "value" if object_type == "Numeric" and element.get("readonly") is False else "readValue"
            properties[field] = variable_reference(element["tag"], variable_scope)
        if object_type == "Numeric" and "readonly" in element:
            properties["readOnly"] = element["readonly"]
        if not omit_text and object_type == "Button" and element.get("label") is not None:
            properties["text"] = element["label"]
        events = []
        task = element.get("task")
        if task:
            if task.get("type") != "switch_screen":
                raise ValueError("不支持的 task.type: %r" % task.get("type"))
            target = task.get("target")
            if screens is not None and target not in screens:
                raise ValueError("导航目标不存在: %s" % target)
            events.append({
                "id": "task",
                "statements": [change_screen_statement(target)],
            })
        objects.append({
            "name": element["name"],
            "objectType": object_type,
            "layer": "root",
            "properties": properties,
            "events": events,
        })
    screen = {
        "name": screen_name or source_screen["name"],
        "groupPath": [],
        "availableLayers": ["root"],
        "properties": {
            "border": {"style": "noPen"},
            "comment": "",
            "fill": "#FFFFFFFF",
            "height": source_screen["height"],
            "underlay": [],
            "width": source_screen["width"],
        },
        "events": [
            {"id": "opened", "statements": []},
            {"id": "closing", "statements": []},
        ],
        "conditions": [],
        "objects": objects,
    }
    return {
        "header": {"schemaVersion": "1.1", "contentType": "view"},
        "body": {"screens": [screen], "windows": []},
    }


def verify_readback(readback, archive):
    screen = readback["screen"]
    expected = {obj["name"]: obj for obj in archive["body"]["screens"][0]["objects"]}
    actual = {obj["name"]: obj for obj in screen.get("objects", [])}
    errors = []
    if screen.get("name") != archive["body"]["screens"][0]["name"]:
        errors.append("画面名不一致")
    if set(expected) != set(actual):
        errors.append("元件名不一致: 期望 %s, 实际 %s" % (sorted(expected), sorted(actual)))
    for name in sorted(set(expected) & set(actual)):
        exp, got = expected[name], actual[name]
        if exp["objectType"] != got.get("objectType"):
            errors.append("%s 类型不一致" % name)
        for key in ("x", "y", "width", "height"):
            if exp["properties"].get(key) != got.get("properties", {}).get(key):
                errors.append("%s %s 不一致" % (name, key))
        for key in ("text", "readOnly", "readValue", "value"):
            if key in exp["properties"] and exp["properties"][key] != got.get("properties", {}).get(key):
                errors.append("%s %s 不一致" % (name, key))
        actual_events = {event["id"]: event for event in got.get("events", [])}
        for event in exp["events"]:
            if actual_events.get(event["id"]) != event:
                errors.append("%s 事件 %s 不一致" % (name, event["id"]))
    return {
        "ok": not errors,
        "expected_objects": len(expected),
        "actual_objects": len(actual),
        "errors": errors,
    }


def import_succeeded(imported):
    if not imported.get("success", False):
        return False
    changeset = imported.get("changeset_result", imported)
    if not changeset.get("all_ok", False):
        return False
    if imported.get("unresolved_references") or changeset.get("unresolved_references"):
        return False
    if changeset.get("missing_references"):
        return False
    return all(
        operation.get("success", False) and not operation.get("unresolved_references")
        for operation in changeset.get("per_operation", [])
    )


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="代码生成 EBX 原生画面 JSON 并可选导入")
    parser.add_argument("input")
    parser.add_argument("--output")
    parser.add_argument("--screen")
    parser.add_argument("--screens", help="逗号分隔的现有画面名")
    parser.add_argument("--variable-scope", default="Project")
    parser.add_argument("--omit-text", action="store_true", help="原生 Schema 不接受内联文字时省略文字")
    parser.add_argument("--port", type=int)
    parser.add_argument("--import", action="store_true", dest="do_import")
    parser.add_argument("--evidence-dir", default="out/ai_socket")
    args = parser.parse_args()
    screens = None if args.screens is None else {x.strip() for x in args.screens.split(",") if x.strip()}
    validation = validate(args.input, screens)
    if not validation["ok"]:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 2
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    try:
        archive = convert(data, args.screen, args.variable_scope, screens, args.omit_text)
    except ValueError as exc:
        print("[ERR] %s" % exc)
        return 2
    output = args.output or os.path.join(os.path.dirname(args.input), "native.archive.json")
    write_json(output, archive)
    print(json.dumps({"ok": True, "archive": output, "objects": len(archive["body"]["screens"][0]["objects"])}, ensure_ascii=False))
    if not args.do_import:
        return 0
    client = EBXSocket(args.port)
    screen_name = archive["body"]["screens"][0]["name"]
    os.makedirs(args.evidence_dir, exist_ok=True)
    started = time.perf_counter()
    try:
        conflicts = require_ok(client.call("detectImportConflicts", {"archive": archive}))
        imported = require_ok(client.call("importScreenView", {"archive": archive}))
        readback = require_ok(client.call("getViewByScreenName", {"screen_name": screen_name}))
        exported = require_ok(client.call("exportScreenView", {"screen_name": screen_name}))
        diagnostics = require_ok(client.call("getDiagnostics", {}))
    except EBXSocketError as exc:
        print("[ERR] %s" % exc, file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started
    verification = verify_readback(readback, archive)
    evidence = {
        "screen": screen_name,
        "elapsed_seconds": round(elapsed, 3),
        "conflicts": conflicts,
        "import": imported,
        "verification": verification,
        "diagnostics": diagnostics,
    }
    write_json(os.path.join(args.evidence_dir, "native_codegen_evidence.json"), evidence)
    write_json(os.path.join(args.evidence_dir, "native_codegen_readback.json"), readback)
    write_json(os.path.join(args.evidence_dir, "native_codegen_export.json"), exported)
    import_ok = import_succeeded(imported)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if verification["ok"] and import_ok else 1


if __name__ == "__main__":
    sys.exit(main())
