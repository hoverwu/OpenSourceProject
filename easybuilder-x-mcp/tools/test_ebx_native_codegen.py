# -*- coding: utf-8 -*-
"""Native Screen View conversion tests (hoverwu / 0.1.0)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_cli_default_output_stays_under_out(self):
        argv = ["ebx_native_codegen.py", str(FIXTURE), "--screens", "参数设定", "--omit-text"]
        with patch.object(codegen.sys, "argv", argv), \
                patch.object(codegen, "write_json") as write, \
                patch.object(codegen.os, "makedirs"):
            self.assertEqual(codegen.main(), 0)
        self.assertEqual(
            Path(write.call_args.args[0]).as_posix(),
            "out/ai_socket/C2_Native_Sample.native.json")

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


class NativeImportTests(unittest.TestCase):
    def setUp(self):
        with FIXTURE.open(encoding="utf-8") as f:
            self.data = json.load(f)
        self.archive = codegen.convert(self.data, "安全导入", screens={"参数设定"}, omit_text=True)
        self.schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "test.screen.schema.json",
            "schema_version": "1.4",
            "type": "object",
            "required": ["header", "body"],
            "properties": {
                "header": {"type": "object", "required": ["schemaVersion", "contentType"]},
                "body": {"type": "object", "required": ["screens", "windows"]},
            },
        }

    def fake_client(self, conflicts=None, imported=None, full_screen=None, export_screen=None):
        calls = []

        case = self

        class FakeClient:
            def call(self, method, params):
                calls.append((method, copy.deepcopy(params)))
                if method == "getScreenViewJsonSchema":
                    result = copy.deepcopy(case.schema)
                elif method == "detectImportConflicts":
                    result = conflicts or {"has_conflicts": False, "conflict_count": 0, "conflicts": []}
                elif method == "importScreenView":
                    result = imported or {
                        "success": True,
                        "changeset_result": {"all_ok": True, "per_operation": [{"success": True}]},
                    }
                elif method == "getViewByScreenName":
                    result = {"screen": copy.deepcopy(full_screen or case.archive["body"]["screens"][0])}
                elif method == "exportScreenView":
                    exported = copy.deepcopy(case.archive)
                    if export_screen is not None:
                        exported["body"]["screens"][0] = copy.deepcopy(export_screen)
                    result = {"archive": exported}
                elif method == "getDiagnostics":
                    result = {"running": True}
                else:
                    raise AssertionError(method)
                return {"ok": True, "result": result, "schema_version": "1.4"}

        return FakeClient(), calls

    def test_conflict_aborts_before_import(self):
        client, calls = self.fake_client(conflicts={
            "has_conflicts": True, "conflict_count": 1, "conflicts": ["安全导入"]})
        result = codegen.import_archive(client, self.archive)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "IMPORT_CONFLICT")
        self.assertNotIn("importScreenView", [method for method, _ in calls])

    def test_dry_run_validates_schema_and_conflicts_without_import(self):
        client, calls = self.fake_client()
        result = codegen.import_archive(client, self.archive, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "DRY_RUN_OK")
        self.assertTrue(result["schema"]["ok"])
        self.assertEqual(result["schema"]["schema_version"], "1.4")
        self.assertNotIn("importScreenView", [method for method, _ in calls])

    def test_schema_failure_blocks_import(self):
        archive = copy.deepcopy(self.archive)
        archive["header"]["schemaVersion"] = "9.9"
        self.schema["properties"]["header"]["properties"] = {
            "schemaVersion": {"const": "1.1"}, "contentType": {"const": "view"}}
        client, calls = self.fake_client()
        result = codegen.import_archive(client, archive)
        self.assertEqual(result["code"], "NATIVE_SCHEMA_VALIDATION_FAILED")
        self.assertNotIn("detectImportConflicts", [method for method, _ in calls])

        self.schema = []
        client, calls = self.fake_client()
        result = codegen.import_archive(client, archive)
        self.assertEqual(result["code"], "INVALID_NATIVE_SCHEMA")
        self.assertNotIn("detectImportConflicts", [method for method, _ in calls])

    def test_readback_mismatch_is_failure_and_writes_evidence(self):
        changed = copy.deepcopy(self.archive["body"]["screens"][0])
        changed["objects"][0]["properties"]["x"] += 1
        client, _ = self.fake_client(full_screen=changed, export_screen=changed)
        with tempfile.TemporaryDirectory(dir=BASE / "out") as temp:
            result = codegen.import_archive(client, self.archive, temp)
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "READBACK_MISMATCH")
            self.assertFalse(result["verification_full"]["ok"])
            self.assertTrue((Path(temp) / "native_codegen_evidence.json").is_file())
            self.assertTrue((Path(temp) / "native_codegen_archive.json").is_file())


if __name__ == "__main__":
    unittest.main()
