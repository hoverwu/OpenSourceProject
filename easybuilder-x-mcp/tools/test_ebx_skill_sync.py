# -*- coding: utf-8 -*-
"""Skill 部署同步回归测试（hoverwu / 0.1.0）。"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sync_skill


class SkillSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix=".sync-skill-test-", dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.destination = self.root / "deployed"
        self.source.mkdir()

    def write_sources(self, packaged=False):
        (self.source / "SKILL.md").write_text("skill source", encoding="utf-8")
        reference_dir = self.source / "references" if packaged else self.source
        reference_dir.mkdir(exist_ok=True)
        for name in sync_skill.REFERENCE_FILES:
            (reference_dir / name).write_text(name, encoding="utf-8")

    def run_sync(self, check=False):
        argv = ["sync_skill.py"] + (["--check"] if check else [])
        output = io.StringIO()
        with patch.object(sync_skill, "BASE", str(self.source)), \
                patch.object(sync_skill, "DST_ROOT", str(self.destination)), \
                patch.object(sync_skill.sys, "argv", argv), \
                contextlib.redirect_stdout(output):
            code = sync_skill.main()
        return code, json.loads(output.getvalue())

    def assert_deployed_bundle(self):
        self.assertEqual(
            sorted(path.relative_to(self.destination).as_posix()
                   for path in self.destination.rglob("*") if path.is_file()),
            sorted(["SKILL.md"] + [
                "references/" + name for name in sync_skill.REFERENCE_FILES
            ]))
        for record in sync_skill.snapshot(self.source, self.destination):
            self.assertEqual(record["src_sha256"], record["dst_sha256"])

    def test_root_layout_deploys_skill_and_references(self):
        self.write_sources()
        code, result = self.run_sync()
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["files"]), 4)
        self.assert_deployed_bundle()

    def test_packaged_references_layout_is_supported(self):
        self.write_sources(packaged=True)
        code, result = self.run_sync()
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assert_deployed_bundle()

    def test_check_detects_deployed_drift(self):
        self.write_sources()
        self.assertEqual(self.run_sync()[0], 0)
        (self.destination / "SKILL.md").write_text("stale", encoding="utf-8")
        code, result = self.run_sync(check=True)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "none")


if __name__ == "__main__":
    unittest.main()
