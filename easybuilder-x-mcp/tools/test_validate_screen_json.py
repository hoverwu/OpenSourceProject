# -*- coding: utf-8 -*-
"""validate_screen_json regression tests (hoverwu / 0.1.0)."""
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import validate_screen_json as validator

BASE = Path(__file__).resolve().parents[1]
FIXTURE = BASE / "examples/C2_Native_Sample.screen.json"
SCREENS = {"主监控", "参数设定", "报警与趋势", "手动维护"}


class ValidateScreenJsonTests(unittest.TestCase):
    def setUp(self):
        with FIXTURE.open(encoding="utf-8") as f:
            self.data = json.load(f)

    def check(self, data, screens=SCREENS):
        with patch.object(validator, "open", return_value=io.StringIO(json.dumps(data))):
            return validator.validate("__memory__", screens)

    def test_valid_fixture(self):
        result = self.check(self.data)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["elements"], 8)
        self.assertEqual(result["warnings"], [])

    def test_navigation_without_screen_list_warns(self):
        result = self.check(self.data, None)
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["warnings"])

    def test_accepts_empty_addresses(self):
        data = copy.deepcopy(self.data)
        for tag in data["tags"]:
            tag["address"] = ""
        result = self.check(data)
        self.assertTrue(result["ok"], result["errors"])

    def test_rejects_invalid_values(self):
        cases = {
            "bad_kind": lambda d: d["screen"]["elements"][0].update(ebx_kind="BAD_KIND"),
            "missing_id": lambda d: d["screen"]["elements"][0].pop("id"),
            "zero_width": lambda d: d["screen"]["elements"][0].update(w=0),
            "negative_height": lambda d: d["screen"]["elements"][0].update(h=-1),
            "task_on_text": lambda d: d["screen"]["elements"][0].update(
                task={"type": "switch_screen", "target": "参数设定"}),
            "empty_target": lambda d: d["screen"]["elements"][-1]["task"].update(target=""),
            "unknown_target": lambda d: d["screen"]["elements"][-1]["task"].update(target="MISSING"),
            "duplicate_tag": lambda d: d["tags"].append(copy.deepcopy(d["tags"][0])),
            "duplicate_address": lambda d: d["tags"][1].update(address=d["tags"][0]["address"]),
            "bad_readonly": lambda d: d["screen"]["elements"][3].update(readonly="yes"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                data = copy.deepcopy(self.data)
                mutate(data)
                result = self.check(data)
                self.assertFalse(result["ok"], name)
                self.assertTrue(result["errors"], name)


if __name__ == "__main__":
    unittest.main()
