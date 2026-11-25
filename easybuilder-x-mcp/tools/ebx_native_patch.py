# -*- coding: utf-8 -*-
"""EBX 原生 Changeset 增量补丁：捕获、预检、应用与回滚（hoverwu / 0.1.0）。"""
import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time

if __package__:
    from .ebx_ai_socket import EBXSocket, EBXSocketError, require_ok
else:
    from ebx_ai_socket import EBXSocket, EBXSocketError, require_ok

SCHEMA = "ebx-native-patch/1.0"
OBJECT_TYPES = {"Text", "Numeric", "Lamp", "Button"}
INTEGER_PROPERTIES = {"x", "y", "width", "height", "radius"}
REFERENCE_PROPERTIES = {"value", "readValue"}
STRING_REFERENCE = re.compile(r"^String://.+:ID\[[0-9]+\]$")


class PatchError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def canonical_hash(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def screen_from_export(response):
    result = require_ok(response)
    archive = result.get("archive") or {}
    screens = archive.get("body", {}).get("screens") or []
    if len(screens) != 1:
        raise PatchError("SCREEN_NOT_FOUND", "导出结果不是单一画面")
    return screens[0]


def object_map(screen):
    result = {}
    for obj in screen.get("objects", []):
        name = obj.get("name")
        if name in result:
            raise PatchError("DUPLICATE_OBJECT", "画面存在重名元件: %s" % name)
        if obj.get("layer") != "root":
            raise PatchError("UNSUPPORTED_LAYER", "MVP 只支持 root 层: %s" % name)
        result[name] = obj
    return result


def schema_objects(schema_response):
    result = require_ok(schema_response)
    return {item["objectType"]: item for item in result.get("objects", [])}


def validate_schema_property(schemas, object_type, property_name):
    definition = schemas.get(object_type)
    if not definition:
        raise PatchError("UNSUPPORTED_OBJECT", "不支持的对象类型: %s" % object_type)
    prop = next((item for item in definition.get("properties", []) if item.get("name") == property_name), None)
    if not prop:
        raise PatchError("UNSUPPORTED_PROPERTY", "%s 不支持属性 %s" % (object_type, property_name))
    if prop.get("readOnly") is True:
        raise PatchError("READ_ONLY_PROPERTY", "%s.%s 只读" % (object_type, property_name))


def normalize_property(property_name, value):
    if property_name in INTEGER_PROPERTIES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise PatchError("INVALID_VALUE", "%s 必须是整数" % property_name)
        if property_name in {"width", "height"} and value <= 0:
            raise PatchError("INVALID_VALUE", "%s 必须为正数" % property_name)
        return value, str(value)
    if property_name == "padding":
        keys = {"top", "right", "bottom", "left"}
        if not isinstance(value, dict) or set(value) != keys:
            raise PatchError("INVALID_VALUE", "padding 必须包含 top/right/bottom/left")
        if any(isinstance(value[key], bool) or not isinstance(value[key], int) or value[key] < 0 for key in keys):
            raise PatchError("INVALID_VALUE", "padding 成员必须是非负整数")
        return copy.deepcopy(value), copy.deepcopy(value)
    if property_name == "text":
        if value is not None and (not isinstance(value, str) or not STRING_REFERENCE.match(value)):
            raise PatchError("INVALID_TEXT", "text 必须是 String://Project:ID[n] 或 null")
        return value, copy.deepcopy(value)
    if property_name in REFERENCE_PROPERTIES:
        if not isinstance(value, str) or not value.startswith("Variable://"):
            raise PatchError("INVALID_REFERENCE", "%s 必须是 Variable:// 引用" % property_name)
        return value, {"path": value}
    raise PatchError("UNSUPPORTED_PROPERTY", "不支持的属性: %s" % property_name)


def normalize_statements(statements):
    if not isinstance(statements, list) or any(not isinstance(item, dict) for item in statements):
        raise PatchError("INVALID_EVENT", "statements 必须是对象数组")
    return copy.deepcopy(statements)


def bare_name(value, field):
    if not isinstance(value, str) or not value or "/" in value:
        raise PatchError("INVALID_ENTITY", "%s 必须是不含 / 的元件名" % field)
    return value


def normalize_operations(operations):
    if not isinstance(operations, list):
        raise PatchError("INVALID_PATCH", "operations 必须是数组")
    normalized = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise PatchError("INVALID_OPERATION", "operations[%d] 必须是对象" % index)
        kind = operation.get("type")
        if kind == "set_property":
            entity = bare_name(operation.get("entity"), "entity")
            property_name = operation.get("property")
            if "value" not in operation:
                raise PatchError("INVALID_OPERATION", "set_property 缺少 value")
            expected, encoded = normalize_property(property_name, operation["value"])
            item = {"type": kind, "entity": entity, "property": property_name, "value": expected, "encoded": encoded}
            if "before" in operation:
                item["before"] = normalize_property(property_name, operation["before"])[0]
        elif kind == "set_event":
            entity = bare_name(operation.get("entity"), "entity")
            event = operation.get("event")
            if not isinstance(event, str) or not event:
                raise PatchError("INVALID_OPERATION", "set_event 缺少 event")
            item = {"type": kind, "entity": entity, "event": event, "statements": normalize_statements(operation.get("statements"))}
            if "before" in operation:
                item["before"] = normalize_statements(operation["before"])
        elif kind == "add_entity":
            name = bare_name(operation.get("name"), "name")
            object_type = operation.get("object_type")
            if object_type not in OBJECT_TYPES:
                raise PatchError("UNSUPPORTED_OBJECT", "不支持的 object_type: %s" % object_type)
            properties = operation.get("properties")
            if not isinstance(properties, dict):
                raise PatchError("INVALID_OPERATION", "add_entity 缺少 properties")
            for required in ("x", "y", "width", "height"):
                if required not in properties:
                    raise PatchError("INVALID_OPERATION", "add_entity 缺少 %s" % required)
            normalized_properties = []
            for property_name, value in properties.items():
                if property_name == "tag":
                    if object_type not in {"Numeric", "Lamp"}:
                        raise PatchError("INVALID_OPERATION", "只有 Numeric/Lamp 支持 tag")
                    if operation.get("readonly") is True:
                        raise PatchError("UNSUPPORTED_READONLY", "add_entity 暂不支持创建只读 Numeric")
                    property_name = "value" if object_type == "Numeric" else "readValue"
                    if not isinstance(value, str) or not value:
                        raise PatchError("INVALID_REFERENCE", "tag 必须是非空变量名或 Variable:// 引用")
                    if not value.startswith("Variable://"):
                        value = "Variable://Project/%s" % value
                expected, encoded = normalize_property(property_name, value)
                normalized_properties.append({"property": property_name, "value": expected, "encoded": encoded})
            events = operation.get("events", [])
            if not isinstance(events, list):
                raise PatchError("INVALID_OPERATION", "events 必须是数组")
            normalized_events = []
            for event in events:
                if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"]:
                    raise PatchError("INVALID_EVENT", "event 必须包含 id")
                normalized_events.append({"id": event["id"], "statements": normalize_statements(event.get("statements"))})
            item = {"type": kind, "name": name, "object_type": object_type, "properties": normalized_properties, "events": normalized_events}
        elif kind == "remove_entity":
            item = {"type": kind, "entity": bare_name(operation.get("entity"), "entity")}
        else:
            raise PatchError("UNSUPPORTED_OPERATION", "不支持的操作: %r" % kind)
        normalized.append(item)
    if any(item["type"] == "remove_entity" for item in normalized) and len(normalized) != 1:
        raise PatchError("UNSAFE_REMOVE", "remove_entity 必须单独执行，便于失败时保护原画面")
    return normalized


def current_event(obj, event_id):
    event = next((item for item in obj.get("events", []) if item.get("id") == event_id), None)
    return None if event is None else event.get("statements", [])


def evaluate(screen, operations):
    objects = object_map(screen)
    statuses = []
    errors = []
    for operation in operations:
        kind = operation["type"]
        if kind == "add_entity":
            obj = objects.get(operation["name"])
            if obj is None:
                statuses.append({"type": kind, "name": operation["name"], "status": "pending"})
                continue
            matches = obj.get("objectType") == operation["object_type"]
            for prop in operation["properties"]:
                matches = matches and obj.get("properties", {}).get(prop["property"]) == prop["value"]
            for event in operation["events"]:
                matches = matches and current_event(obj, event["id"]) == event["statements"]
            if matches:
                statuses.append({"type": kind, "name": operation["name"], "status": "satisfied"})
            else:
                errors.append("元件已存在但内容不同: %s" % operation["name"])
                statuses.append({"type": kind, "name": operation["name"], "status": "conflict"})
            continue
        obj = objects.get(operation["entity"])
        if kind == "remove_entity":
            status = "satisfied" if obj is None else "pending"
            statuses.append({"type": kind, "entity": operation["entity"], "status": status})
            continue
        if obj is None:
            errors.append("元件不存在: %s" % operation["entity"])
            statuses.append({"type": kind, "entity": operation["entity"], "status": "conflict"})
            continue
        if kind == "set_property":
            actual = obj.get("properties", {}).get(operation["property"])
            desired = operation["value"]
        else:
            actual = current_event(obj, operation["event"])
            desired = operation["statements"]
        selector = operation.get("property") or operation.get("event")
        if actual == desired:
            statuses.append({"type": kind, "entity": operation["entity"], "selector": selector, "status": "satisfied", "before": actual})
        elif "before" in operation and actual != operation["before"]:
            errors.append("before 不匹配: %s" % operation["entity"])
            statuses.append({"type": kind, "entity": operation["entity"], "selector": selector, "status": "conflict", "before": actual})
        else:
            statuses.append({"type": kind, "entity": operation["entity"], "selector": selector, "status": "pending", "before": actual})
    return statuses, errors


def native_operations(screen_name, operation):
    kind = operation["type"]
    if kind == "set_property":
        return [{
            "type": "set_property",
            "entity": "%s/%s" % (screen_name, operation["entity"]),
            "property": operation["property"],
            "value": operation["encoded"],
        }]
    if kind == "set_event":
        return [{
            "type": "set_event",
            "entity": "%s/%s" % (screen_name, operation["entity"]),
            "event": operation["event"],
            "statements": operation["statements"],
        }]
    if kind == "add_entity":
        entity = "%s/%s" % (screen_name, operation["name"])
        result = [{
            "type": "add_entity",
            "screen_or_window": screen_name,
            "object_description": operation["object_type"],
            "name": operation["name"],
        }]
        result.extend({
            "type": "set_property",
            "entity": entity,
            "property": prop["property"],
            "value": prop["encoded"],
        } for prop in operation["properties"])
        result.extend({
            "type": "set_event",
            "entity": entity,
            "event": event["id"],
            "statements": event["statements"],
        } for event in operation["events"])
        return result
    return [{
        "type": "remove_entity",
        "screen_or_window": screen_name,
        "object_description": operation["entity"],
    }]


def changeset_succeeded(response, expected_count):
    if response.get("ok") is not True:
        return False
    result = response.get("result", response)
    if result.get("all_ok") is not True:
        return False
    if result.get("missing_references"):
        return False
    per_operation = result.get("per_operation", [])
    if len(per_operation) != expected_count:
        return False
    return all(item.get("success") is True and not item.get("unresolved_references") for item in per_operation)


def rollback_operations(screen_name, pending, statuses):
    result = []
    status_by_key = {
        (item["type"], item.get("entity") or item.get("name"), item.get("selector")): item
        for item in statuses
    }
    for operation in reversed(pending):
        kind = operation["type"]
        if kind == "add_entity":
            result.append({
                "type": "remove_entity",
                "screen_or_window": screen_name,
                "object_description": operation["name"],
            })
            continue
        if kind == "remove_entity":
            continue
        selector = operation.get("property") or operation.get("event")
        status = status_by_key[(kind, operation["entity"], selector)]
        before = status.get("before")
        if kind == "set_property":
            if before is None and operation["property"] in REFERENCE_PROPERTIES:
                continue
            if operation["property"] not in INTEGER_PROPERTIES | REFERENCE_PROPERTIES | {"text", "padding"}:
                continue
            expected, encoded = normalize_property(operation["property"], before)
            result.append({
                "type": "set_property",
                "entity": "%s/%s" % (screen_name, operation["entity"]),
                "property": operation["property"],
                "value": encoded,
            })
        else:
            result.append({
                "type": "set_event",
                "entity": "%s/%s" % (screen_name, operation["entity"]),
                "event": operation["event"],
                "statements": before or [],
            })
    return result


def capture(client, screen_name, evidence_dir):
    screen = screen_from_export(client.call("exportScreenView", {"screen_name": screen_name}))
    patch = {
        "schema": SCHEMA,
        "generator": {"tool": "ebx_native_patch", "version": "0.1.0", "author": "hoverwu"},
        "screen": screen_name,
        "base_hash": canonical_hash(screen),
        "operations": [],
    }
    os.makedirs(evidence_dir, exist_ok=True)
    write_json(os.path.join(evidence_dir, "native_patch_snapshot.json"), screen)
    return patch


def apply_patch(client, patch, dry_run=False, evidence_dir="out/ai_socket"):
    if not isinstance(patch, dict) or patch.get("schema") != SCHEMA:
        raise PatchError("INVALID_SCHEMA", "schema 必须是 %s" % SCHEMA)
    screen_name = patch.get("screen")
    if not isinstance(screen_name, str) or not screen_name:
        raise PatchError("INVALID_SCREEN", "screen 不能为空")
    operations = normalize_operations(patch.get("operations"))
    screen = screen_from_export(client.call("exportScreenView", {"screen_name": screen_name}))
    schemas = schema_objects(client.call("getEditablePropertySchema", {}))
    for operation in operations:
        if operation["type"] == "set_property":
            obj = object_map(screen).get(operation["entity"])
            if obj:
                validate_schema_property(schemas, obj.get("objectType"), operation["property"])
        elif operation["type"] == "add_entity":
            for prop in operation["properties"]:
                validate_schema_property(schemas, operation["object_type"], prop["property"])
    statuses, errors = evaluate(screen, operations)
    current_hash = canonical_hash(screen)
    if errors:
        return {"ok": False, "code": "PRECHECK_FAILED", "screen": screen_name, "base_hash": current_hash, "statuses": statuses, "errors": errors}
    pending = [operation for operation, status in zip(operations, statuses) if status["status"] == "pending"]
    if not pending:
        return {"ok": True, "noop": True, "screen": screen_name, "base_hash": current_hash, "statuses": statuses}
    expected_hash = patch.get("base_hash")
    if expected_hash and expected_hash != current_hash:
        return {"ok": False, "code": "BASE_HASH_CONFLICT", "screen": screen_name, "expected_hash": expected_hash, "actual_hash": current_hash, "statuses": statuses}
    native = []
    for operation in pending:
        native.extend(native_operations(screen_name, operation))
    plan = {"ok": True, "dry_run": True, "screen": screen_name, "base_hash": current_hash, "statuses": statuses, "native_operations": native}
    if dry_run:
        return plan
    run_id = time.strftime("%Y%m%d_%H%M%S_") + str(time.time_ns() % 1000000)
    os.makedirs(evidence_dir, exist_ok=True)
    snapshot_path = os.path.join(evidence_dir, "native_patch_%s_before.json" % run_id)
    evidence_path = os.path.join(evidence_dir, "native_patch_%s_evidence.json" % run_id)
    write_json(snapshot_path, screen)
    started = time.perf_counter()
    try:
        response = client.call("applyChangeset", {"operations": native})
        after = screen_from_export(client.call("exportScreenView", {"screen_name": screen_name}))
    except EBXSocketError as exc:
        response = {"ok": False, "error": {"code": "SOCKET_ERROR", "message": str(exc)}}
        after = screen
    elapsed = time.perf_counter() - started
    success = changeset_succeeded(response, len(native))
    after_statuses, after_errors = evaluate(after, operations)
    verified = success and not after_errors and all(item["status"] == "satisfied" for item in after_statuses)
    rollback = None
    if not verified:
        reverse = rollback_operations(screen_name, pending, statuses)
        if reverse:
            try:
                rollback_response = client.call("applyChangeset", {"operations": reverse})
                rollback = {"attempted": True, "ok": changeset_succeeded(rollback_response, len(reverse)), "response": rollback_response}
            except EBXSocketError as exc:
                rollback = {"attempted": True, "ok": False, "error": str(exc)}
        else:
            rollback = {"attempted": False, "reason": "remove_entity 无法自动恢复，保留写前快照"}
    evidence = {
        "ok": verified,
        "noop": False,
        "screen": screen_name,
        "run_id": run_id,
        "elapsed_seconds": round(elapsed, 4),
        "base_hash": current_hash,
        "after_hash": canonical_hash(after),
        "snapshot": snapshot_path,
        "statuses": statuses,
        "response": response,
        "verification": {"ok": verified, "statuses": after_statuses, "errors": after_errors},
        "rollback": rollback,
    }
    write_json(evidence_path, evidence)
    evidence["evidence"] = evidence_path
    return evidence


def main():
    parser = argparse.ArgumentParser(description="EBX 原生增量补丁")
    parser.add_argument("command", choices=("capture", "apply"))
    parser.add_argument("input", nargs="?")
    parser.add_argument("--screen")
    parser.add_argument("--output")
    parser.add_argument("--port", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-dir", default="out/ai_socket")
    args = parser.parse_args()
    try:
        client = EBXSocket(args.port)
        if args.command == "capture":
            if not args.screen:
                parser.error("capture 需要 --screen")
            result = capture(client, args.screen, args.evidence_dir)
            if args.output:
                write_json(args.output, result)
        else:
            if not args.input:
                parser.error("apply 需要补丁 JSON")
            with open(args.input, encoding="utf-8") as f:
                result = apply_patch(client, json.load(f), args.dry_run, args.evidence_dir)
    except (PatchError, EBXSocketError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "code": getattr(exc, "code", "ERROR"), "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.command == "capture" or result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
