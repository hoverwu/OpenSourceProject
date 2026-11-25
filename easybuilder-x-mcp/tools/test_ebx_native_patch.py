# -*- coding: utf-8 -*-
"""Native Changeset patch tests (hoverwu / 0.1.0)."""
import copy
import tempfile
import unittest
from pathlib import Path

import ebx_native_patch as patch


def prop(name, value_type="int32_t", read_only=False):
    item = {"name": name, "valueType": value_type, "referenceCapability": "full"}
    if read_only:
        item["readOnly"] = True
    return item


def schema():
    common = [prop(name) for name in ("x", "y", "width", "height", "radius")]
    common += [prop("text", "string"), prop("value", "double"), prop("readValue", "double")]
    return {
        "ok": True,
        "result": {"objects": [
            {"objectType": name, "properties": copy.deepcopy(common)}
            for name in ("Text", "Numeric", "Lamp", "Button")
        ]},
    }


def base_screen():
    return {
        "name": "测试画面",
        "groupPath": [],
        "availableLayers": ["root"],
        "properties": {"width": 1024, "height": 600},
        "events": [],
        "conditions": [],
        "objects": [{
            "name": "温度",
            "objectType": "Numeric",
            "layer": "root",
            "properties": {
                "x": 10, "y": 20, "width": 170, "height": 68,
                "radius": 0, "readValue": "Variable://Project/rTempMeas",
            },
            "events": [{"id": "valueChanged", "statements": []}],
        }],
    }


class FakeClient:
    def __init__(self, screen=None, failures=None):
        self.screen = copy.deepcopy(screen or base_screen())
        self.failures = list(failures or [])
        self.apply_calls = []

    def call(self, method, params=None):
        params = params or {}
        if method == "exportScreenView":
            return {"ok": True, "result": {"archive": {"body": {"screens": [copy.deepcopy(self.screen)]}}}}
        if method == "getEditablePropertySchema":
            return schema()
        if method != "applyChangeset":
            raise AssertionError(method)
        self.apply_calls.append(copy.deepcopy(params))
        per = []
        failed = False
        for index, operation in enumerate(params["operations"]):
            if self.failures and self.failures[0] == index:
                self.failures.pop(0)
                per.append({"success": False, "error_code": "TEST_FAILURE", "message": "forced", "unresolved_references": []})
                failed = True
                break
            self.execute(operation)
            per.append({"success": True, "error_code": "", "message": "", "unresolved_references": []})
        return {
            "ok": not failed,
            "all_ok": not failed,
            "result": {"all_ok": not failed, "missing_references": [], "per_operation": per},
        }

    def execute(self, operation):
        kind = operation["type"]
        if kind == "add_entity":
            self.screen["objects"].append({
                "name": operation["name"],
                "objectType": operation["object_description"],
                "layer": "root",
                "properties": {"x": 0, "y": 0, "width": 120, "height": 40},
                "events": [],
            })
            return
        if kind == "remove_entity":
            name = operation["object_description"]
            obj = next(item for item in self.screen["objects"] if item["name"] == name)
            self.screen["objects"].remove(obj)
            return
        obj = next(item for item in self.screen["objects"] if item["name"] == operation["entity"].split("/", 1)[1])
        if kind == "set_event":
            event = next((item for item in obj["events"] if item["id"] == operation["event"]), None)
            if event is None:
                obj["events"].append({"id": operation["event"], "statements": copy.deepcopy(operation["statements"])})
            else:
                event["statements"] = copy.deepcopy(operation["statements"])
        elif kind == "set_property":
            value = operation["value"]
            if isinstance(value, dict) and "path" in value:
                value = value["path"]
            elif operation["property"] in patch.INTEGER_PROPERTIES:
                value = int(value)
            obj["properties"][operation["property"]] = value


class NativePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = FakeClient()
        self.document = {
            "schema": patch.SCHEMA,
            "screen": "测试画面",
            "base_hash": patch.canonical_hash(self.client.screen),
            "operations": [{"type": "set_property", "entity": "温度", "property": "x", "before": 10, "value": 40}],
        }

    def tearDown(self):
        self.temp.cleanup()

    def apply(self, document=None, client=None, dry_run=False):
        return patch.apply_patch(client or self.client, document or self.document, dry_run, self.temp.name)

    def test_package_import_resolves_socket_client(self):
        from tools import ebx_native_patch as packaged_patch

        self.assertTrue(callable(packaged_patch.EBXSocket))
        self.assertEqual(packaged_patch.SCHEMA, patch.SCHEMA)

    def test_geometry_and_reference_encoding(self):
        self.assertEqual(patch.normalize_property("x", 40), (40, "40"))
        self.assertEqual(
            patch.normalize_property("readValue", "Variable://Project/rTempMeas"),
            ("Variable://Project/rTempMeas", {"path": "Variable://Project/rTempMeas"}),
        )

    def test_padding_uses_numeric_structured_value(self):
        value = {"top": 1, "right": 2, "bottom": 3, "left": 4}
        self.assertEqual(patch.normalize_property("padding", value), (value, value))
        with self.assertRaises(patch.PatchError):
            patch.normalize_property("padding", {"top": "1", "right": 2, "bottom": 3, "left": 4})

    def test_inline_text_and_unknown_property_are_rejected(self):
        with self.assertRaises(patch.PatchError):
            patch.normalize_property("text", "普通文字")
        with self.assertRaises(patch.PatchError):
            patch.normalize_property("fontBold", True)

    def test_dry_run_does_not_write(self):
        result = self.apply(dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["native_operations"][0]["value"], "40")
        self.assertEqual(self.client.apply_calls, [])
        self.assertEqual(self.client.screen["objects"][0]["properties"]["x"], 10)

    def test_apply_and_repeat_are_idempotent(self):
        first = self.apply()
        self.assertTrue(first["ok"])
        self.assertEqual(self.client.screen["objects"][0]["properties"]["x"], 40)
        second = self.apply()
        self.assertTrue(second["noop"])
        self.assertEqual(len(self.client.apply_calls), 1)

    def test_stale_base_hash_is_rejected(self):
        self.document["base_hash"] = "stale"
        result = self.apply()
        self.assertEqual(result["code"], "BASE_HASH_CONFLICT")
        self.assertEqual(self.client.apply_calls, [])

    def test_before_mismatch_is_rejected(self):
        self.client.screen["objects"][0]["properties"]["x"] = 11
        result = self.apply()
        self.assertEqual(result["code"], "PRECHECK_FAILED")
        self.assertEqual(self.client.apply_calls, [])

    def test_missing_entity_is_rejected(self):
        self.document["operations"][0]["entity"] = "不存在"
        result = self.apply()
        self.assertEqual(result["code"], "PRECHECK_FAILED")

    def test_add_entity_expands_to_native_operations(self):
        document = {
            "schema": patch.SCHEMA,
            "screen": "测试画面",
            "base_hash": patch.canonical_hash(self.client.screen),
            "operations": [{
                "type": "add_entity", "name": "状态", "object_type": "Text",
                "properties": {"x": 1, "y": 2, "width": 100, "height": 30, "text": "String://Project:ID[31]"},
            }],
        }
        result = self.apply(document)
        self.assertTrue(result["ok"])
        obj = next(item for item in self.client.screen["objects"] if item["name"] == "状态")
        self.assertEqual(obj["properties"]["x"], 1)
        self.assertEqual(obj["properties"]["text"], "String://Project:ID[31]")
        self.assertEqual(len(self.client.apply_calls[0]["operations"]), 6)

    def test_add_entity_tag_builds_project_variable_reference(self):
        document = {
            "schema": patch.SCHEMA,
            "screen": "测试画面",
            "base_hash": patch.canonical_hash(self.client.screen),
            "operations": [{
                "type": "add_entity", "name": "设定值", "object_type": "Numeric",
                "properties": {"x": 1, "y": 2, "width": 100, "height": 30, "tag": "rSetpointHmi"},
            }],
        }
        self.assertTrue(self.apply(document)["ok"])
        obj = next(item for item in self.client.screen["objects"] if item["name"] == "设定值")
        self.assertEqual(obj["properties"]["value"], "Variable://Project/rSetpointHmi")
        value_ops = [item for item in self.client.apply_calls[0]["operations"] if item.get("property") == "value"]
        self.assertEqual(value_ops[0]["value"], {"path": "Variable://Project/rSetpointHmi"})

    def test_existing_add_with_different_content_conflicts(self):
        self.client.screen["objects"].append({
            "name": "状态", "objectType": "Text", "layer": "root",
            "properties": {"x": 0, "y": 0, "width": 120, "height": 40}, "events": [],
        })
        document = {
            "schema": patch.SCHEMA, "screen": "测试画面",
            "operations": [{
                "type": "add_entity", "name": "状态", "object_type": "Text",
                "properties": {"x": 1, "y": 2, "width": 100, "height": 30},
            }],
        }
        result = self.apply(document)
        self.assertEqual(result["code"], "PRECHECK_FAILED")

    def test_remove_is_standalone_and_idempotent(self):
        document = {
            "schema": patch.SCHEMA, "screen": "测试画面",
            "base_hash": patch.canonical_hash(self.client.screen),
            "operations": [{"type": "remove_entity", "entity": "温度"}],
        }
        self.assertTrue(self.apply(document)["ok"])
        self.assertEqual(self.client.screen["objects"], [])
        self.assertTrue(self.apply(document)["noop"])
        document["operations"].append({"type": "set_property", "entity": "温度", "property": "x", "value": 1})
        with self.assertRaisesRegex(patch.PatchError, "必须单独执行"):
            self.apply(document)

    def test_set_event_is_verified(self):
        statements = [{"type": "call", "method": "Method://<system>.changeScreen", "parameters": {"target": "Object://Screen:参数设定"}}]
        document = {
            "schema": patch.SCHEMA, "screen": "测试画面",
            "base_hash": patch.canonical_hash(self.client.screen),
            "operations": [{"type": "set_event", "entity": "温度", "event": "valueChanged", "statements": statements}],
        }
        self.assertTrue(self.apply(document)["ok"])
        self.assertEqual(self.client.screen["objects"][0]["events"][0]["statements"], statements)

    def test_partial_failure_rolls_back_prior_property(self):
        self.client.failures = [1]
        document = copy.deepcopy(self.document)
        document["operations"].append({"type": "set_property", "entity": "温度", "property": "y", "value": 200})
        result = self.apply(document)
        self.assertFalse(result["ok"])
        self.assertTrue(result["rollback"]["ok"])
        self.assertEqual(self.client.screen["objects"][0]["properties"]["x"], 10)
        self.assertEqual(self.client.screen["objects"][0]["properties"]["y"], 20)

    def test_partial_failure_removes_new_entity(self):
        self.client.failures = [2]
        document = {
            "schema": patch.SCHEMA, "screen": "测试画面",
            "base_hash": patch.canonical_hash(self.client.screen),
            "operations": [{
                "type": "add_entity", "name": "状态", "object_type": "Text",
                "properties": {"x": 1, "y": 2, "width": 100, "height": 30},
            }],
        }
        result = self.apply(document)
        self.assertFalse(result["ok"])
        self.assertTrue(result["rollback"]["ok"])
        self.assertEqual([item["name"] for item in self.client.screen["objects"]], ["温度"])

    def test_rollback_failure_is_reported(self):
        self.client.failures = [1, 0]
        document = copy.deepcopy(self.document)
        document["operations"].append({"type": "set_property", "entity": "温度", "property": "y", "value": 200})
        result = self.apply(document)
        self.assertFalse(result["ok"])
        self.assertFalse(result["rollback"]["ok"])

    def test_capture_writes_snapshot_and_hash(self):
        result = patch.capture(self.client, "测试画面", self.temp.name)
        self.assertEqual(result["base_hash"], patch.canonical_hash(self.client.screen))
        self.assertTrue(Path(self.temp.name, "native_patch_snapshot.json").exists())


if __name__ == "__main__":
    unittest.main()
