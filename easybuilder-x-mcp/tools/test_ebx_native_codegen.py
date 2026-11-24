# -*- coding: utf-8 -*-
"""Native Screen View conversion tests (hoverwu / 0.1.0)."""
import copy
import json
from pathlib import Path
import unittest

import ebx_native_codegen as codegen

BASE = Path(__file__).resolve().parents[1]
FIXTURE = BASE / "examples/C2_Native_Sample.screen.json"


class NativeCodegenTests(unittest.TestCase):
    def setUp(self):
        with FIXTURE.open(encoding="utf-8") as f:
            self.data = json.load(f)

    def test_converts_eight_objects_and_native_types(self):
        archive = codegen.convert(self.data, screens={"参数设定"})
        self.assertEqual(archive["header"], {"schemaVersion": "1.1", "contentType": "view"})
        objects = archive["body"]["screens"][0]["objects"]
        self.assertEqual(len(objects), 8)
        self.assertEqual([obj["objectType"] for obj in objects], [
            "Text", "Text", "Text", "Numeric", "Numeric", "Text", "Lamp", "Button"])
        self.assertEqual(objects[3]["properties"]["readValue"], "Variable://Project/rTempMeas")
        self.assertEqual(objects[4]["properties"]["value"], "Variable://Project/rSetpointHmi")
        self.assertEqual(objects[6]["properties"]["readValue"], "Variable://Project/xHeaterOn")
        self.assertTrue(objects[3]["properties"]["readOnly"])
        self.assertFalse(objects[4]["properties"]["readOnly"])

    def test_button_emits_change_screen_event(self):
        archive = codegen.convert(self.data, screens={"参数设定"})
        button = archive["body"]["screens"][0]["objects"][-1]
        self.assertEqual(button["events"], [{
            "id": "task",
            "statements": [codegen.change_screen_statement("参数设定")],
        }])

    def test_unknown_navigation_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "导航目标不存在"):
            codegen.convert(self.data, screens={"主监控"})

    def test_address_changes_do_not_rewrite_native_tag_reference(self):
        changed = copy.deepcopy(self.data)
        changed["tags"][0]["address"] = "D110"
        archive = codegen.convert(changed, screens={"参数设定"})
        numeric = archive["body"]["screens"][0]["objects"][3]
        self.assertEqual(numeric["properties"]["readValue"], "Variable://Project/rTempMeas")

    def test_explicit_variable_uri_is_preserved(self):
        changed = copy.deepcopy(self.data)
        uri = "Variable://[PLC_NX502]/GlobalVariables/rTempMeas"
        changed["screen"]["elements"][3]["tag"] = uri
        archive = codegen.convert(changed, screens={"参数设定"})
        numeric = archive["body"]["screens"][0]["objects"][3]
        self.assertEqual(numeric["properties"]["readValue"], uri)

    def test_device_variable_scope_builds_device_uri(self):
        archive = codegen.convert(
            self.data, screens={"参数设定"}, variable_scope="[PLC_NX502]/GlobalVariables")
        numeric = archive["body"]["screens"][0]["objects"][3]
        self.assertEqual(
            numeric["properties"]["readValue"],
            "Variable://[PLC_NX502]/GlobalVariables/rTempMeas")

    def test_string_reference_is_preserved(self):
        changed = copy.deepcopy(self.data)
        changed["screen"]["elements"][0]["text"] = "String://Project:ID[31]"
        archive = codegen.convert(changed, screens={"参数设定"})
        text = archive["body"]["screens"][0]["objects"][0]
        self.assertEqual(text["properties"]["text"], "String://Project:ID[31]")

    def test_omit_text_and_screen_rename(self):
        archive = codegen.convert(self.data, "导入测试", screens={"参数设定"}, omit_text=True)
        screen = archive["body"]["screens"][0]
        self.assertEqual(screen["name"], "导入测试")
        for obj in screen["objects"]:
            self.assertNotIn("text", obj["properties"])

    def test_import_success_requires_all_operations_and_bindings(self):
        complete = {
            "success": True,
            "changeset_result": {
                "all_ok": True,
                "per_operation": [{"success": True, "unresolved_references": []}],
            },
        }
        self.assertTrue(codegen.import_succeeded(complete))

        top_unresolved = copy.deepcopy(complete)
        top_unresolved["unresolved_references"] = [{"path": "Variable://Project/missing"}]
        self.assertFalse(codegen.import_succeeded(top_unresolved))

        operation_unresolved = copy.deepcopy(complete)
        operation_unresolved["changeset_result"]["per_operation"][0]["unresolved_references"] = [
            {"path": "Variable://Project/missing"}
        ]
        self.assertFalse(codegen.import_succeeded(operation_unresolved))

        failed_operation = copy.deepcopy(complete)
        failed_operation["changeset_result"]["per_operation"][0]["success"] = False
        self.assertFalse(codegen.import_succeeded(failed_operation))

        failed_changeset = copy.deepcopy(complete)
        failed_changeset["changeset_result"]["all_ok"] = False
        self.assertFalse(codegen.import_succeeded(failed_changeset))

    def test_verify_readback_ignores_default_events(self):
        archive = codegen.convert(self.data, screens={"参数设定"}, omit_text=True)
        readback = copy.deepcopy(archive)
        readback = {"screen": readback["body"]["screens"][0]}
        for obj in readback["screen"]["objects"]:
            obj["events"].append({"id": "clicked", "statements": []})
        self.assertTrue(codegen.verify_readback(readback, archive)["ok"])

    def test_verify_readback_detects_geometry_and_event_changes(self):
        archive = codegen.convert(self.data, screens={"参数设定"}, omit_text=True)
        readback = {"screen": copy.deepcopy(archive["body"]["screens"][0])}
        readback["screen"]["objects"][0]["properties"]["x"] += 1
        readback["screen"]["objects"][-1]["events"] = []
        result = codegen.verify_readback(readback, archive)
        self.assertFalse(result["ok"])
        self.assertTrue(any("x 不一致" in error for error in result["errors"]))
        self.assertTrue(any("事件 task 不一致" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
