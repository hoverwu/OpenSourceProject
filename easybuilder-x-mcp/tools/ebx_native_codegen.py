# -*- coding: utf-8 -*-
"""把 ebx-screen/1.0 转为 EBX 原生 Screen View 并安全导入（hoverwu / 0.2.0）。"""
import argparse
import json
import os
import sys
import time

try:
    import jsonschema
except ImportError:
    jsonschema = None

if __package__:
    from .ebx_ai_socket import EBXSocket, EBXSocketError, require_ok
    from .validate_screen_json import validate
else:
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
    if imported.get("missing_references") or changeset.get("missing_references"):
        return False
    return all(
        operation.get("success", False)
        and not operation.get("unresolved_references")
        and not operation.get("missing_references")
        for operation in changeset.get("per_operation", [])
    )


def load_spec(path, screens=None):
    validation = validate(path, screens)
    if not validation["ok"]:
        return None, {"ok": False, "code": "INVALID_SCREEN_JSON", "validation": validation}
    with open(path, encoding="utf-8") as f:
        return json.load(f), validation


def prepare_archive(path, screen=None, variable_scope="Project", screens=None, omit_text=False):
    data, validation = load_spec(path, screens)
    if data is None:
        return None, validation
    try:
        archive = convert(data, screen, variable_scope, screens, omit_text)
    except (KeyError, TypeError, ValueError) as exc:
        return None, {
            "ok": False,
            "code": "CONVERSION_FAILED",
            "message": str(exc),
            "validation": validation,
        }
    return archive, validation


def validate_native_schema(archive, schema, schema_version=None):
    if jsonschema is None:
        return {
            "ok": False,
            "code": "SCHEMA_VALIDATOR_UNAVAILABLE",
            "message": "缺少 jsonschema 依赖；安装 requirements.txt 后再导入原生画面",
        }
    if not isinstance(schema, dict):
        return {
            "ok": False,
            "code": "INVALID_NATIVE_SCHEMA",
            "message": "实时 Screen View Schema 必须是 JSON 对象",
            "schema_version": schema_version,
        }
    validator_type = jsonschema.validators.validator_for(schema)
    try:
        validator_type.check_schema(schema)
    except jsonschema.SchemaError as exc:
        return {
            "ok": False,
            "code": "INVALID_NATIVE_SCHEMA",
            "message": str(exc),
            "schema_id": schema.get("$id"),
            "schema_version": schema_version or schema.get("schema_version"),
        }
    errors = sorted(
        validator_type(schema).iter_errors(archive),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return {
            "ok": True,
            "validator": validator_type.__name__,
            "schema_id": schema.get("$id"),
            "schema_version": schema_version or schema.get("schema_version"),
        }
    return {
        "ok": False,
        "code": "NATIVE_SCHEMA_VALIDATION_FAILED",
        "schema_id": schema.get("$id"),
        "schema_version": schema_version or schema.get("schema_version"),
        "error_count": len(errors),
        "errors": [
            {
                "path": "/".join(str(part) for part in error.absolute_path) or "$",
                "message": error.message,
            }
            for error in errors[:20]
        ],
    }


def import_archive(client, archive, evidence_dir=None, dry_run=False):
    screen_name = archive["body"]["screens"][0]["name"]
    started = time.perf_counter()
    evidence = {
        "screen": screen_name,
        "dry_run": dry_run,
        "conflicts": None,
        "schema": None,
        "import": None,
        "verification": None,
        "verification_full": None,
        "diagnostics": None,
    }

    def finish(code=None, message=None):
        evidence["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        if evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            write_json(os.path.join(evidence_dir, "native_codegen_archive.json"), archive)
            write_json(os.path.join(evidence_dir, "native_codegen_evidence.json"), evidence)
            for key, filename in (
                ("readback", "native_codegen_readback.json"),
                ("exported", "native_codegen_export.json"),
            ):
                if evidence.get(key) is not None:
                    write_json(os.path.join(evidence_dir, filename), evidence[key])
        result = dict(evidence)
        if code:
            result.update({"ok": False, "code": code})
            if message:
                result["message"] = message
        elif dry_run:
            result.update({"ok": True, "code": "DRY_RUN_OK"})
        else:
            result["ok"] = bool(
                import_succeeded(evidence["import"] or {})
                and (evidence["verification"] or {}).get("ok")
                and (evidence["verification_full"] or {}).get("ok")
            )
            result["code"] = "IMPORT_OK" if result["ok"] else "READBACK_MISMATCH"
        return result

    try:
        schema_response = client.call("getScreenViewJsonSchema", {})
        schema = require_ok(schema_response)
        evidence["schema"] = validate_native_schema(
            archive, schema, schema_response.get("schema_version"))
    except EBXSocketError as exc:
        return finish("SCHEMA_FETCH_FAILED", str(exc))
    if not evidence["schema"]["ok"]:
        return finish(evidence["schema"]["code"], evidence["schema"].get("message"))

    try:
        evidence["conflicts"] = require_ok(
            client.call("detectImportConflicts", {"archive": archive})
        )
    except EBXSocketError as exc:
        return finish("CONFLICT_CHECK_FAILED", str(exc))
    conflicts = evidence["conflicts"]
    if conflicts.get("has_conflicts") or conflicts.get("conflict_count"):
        return finish(
            "IMPORT_CONFLICT",
            "目标画面名已存在或归档含冲突；未执行导入。请改用 ebx_native_patch_apply 修改既有画面。",
        )
    if dry_run:
        return finish()

    try:
        evidence["import"] = require_ok(client.call("importScreenView", {"archive": archive}))
    except EBXSocketError as exc:
        return finish("IMPORT_FAILED", str(exc))
    if not import_succeeded(evidence["import"]):
        return finish("IMPORT_FAILED", "原生导入未完整成功；已保留证据，请检查未解析/缺失引用与逐项结果。")

    try:
        evidence["readback"] = require_ok(
            client.call("getViewByScreenName", {"screen_name": screen_name})
        )
        evidence["exported"] = require_ok(
            client.call("exportScreenView", {"screen_name": screen_name})
        )
        evidence["diagnostics"] = require_ok(client.call("getDiagnostics", {}))
    except EBXSocketError as exc:
        return finish("READBACK_FAILED", str(exc))

    evidence["verification"] = verify_readback(evidence["readback"], archive)
    full_screens = evidence["exported"].get("archive", {}).get("body", {}).get("screens", [])
    matching = [screen for screen in full_screens if screen.get("name") == screen_name]
    if matching:
        evidence["verification_full"] = verify_readback({"screen": matching[0]}, archive)
    else:
        evidence["verification_full"] = {"ok": False, "errors": ["完整导出中未找到目标画面"]}
    return finish()


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
    parser.add_argument("--dry-run", action="store_true", help="获取实时 Schema 并检查冲突，但不写入 EBX")
    parser.add_argument("--evidence-dir", default="out/ai_socket")
    args = parser.parse_args()
    screens = None if args.screens is None else {x.strip() for x in args.screens.split(",") if x.strip()}
    try:
        archive, validation = prepare_archive(
            args.input, args.screen, args.variable_scope, screens, args.omit_text
        )
    except (OSError, json.JSONDecodeError) as exc:
        print("[ERR] %s" % exc, file=sys.stderr)
        return 2
    if archive is None:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 2
    try:
        output_stem = os.path.splitext(os.path.basename(args.input))[0]
        if output_stem.endswith(".screen"):
            output_stem = output_stem[:-7]
        output = args.output or os.path.join("out", "ai_socket", output_stem + ".native.json")
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        write_json(output, archive)
    except OSError as exc:
        print("[ERR] %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "archive": output, "objects": len(archive["body"]["screens"][0]["objects"])}, ensure_ascii=False))
    if not args.do_import and not args.dry_run:
        return 0
    result = import_archive(EBXSocket(args.port), archive, args.evidence_dir, args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
