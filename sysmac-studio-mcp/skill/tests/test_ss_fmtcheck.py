# -*- coding: utf-8 -*-
"""Pure unit tests for ss_fmtcheck: no UI, no Sysmac, no real project files.

Regression guard for the 'false 0 errors' class: a PouBody written with
Python json.dumps is accepted by json.loads/zipfile but rejected by Sysmac.
"""
import json
import os
import tempfile
import unittest
import zipfile

import _stubs  # noqa: F401  (puts scripts/ on sys.path; installs UI stubs)

import ss_fmtcheck as F

BOM = b"\xef\xbb\xbf"


def make_body(st="LINE1\r\nLINE2\r\n", *, bom=True, trailing=True,
              native=True, probe=False):
    """Build a PouBody XML payload with selectable serialization defects."""
    text = st + ("\r\nZZ_COMPILE_PROBE_UNDEF := 1;\r\n" if probe else "")
    obj = {
        "CLs": [{"__type": "IST", "EID": "e1", "H": 2, "TXT": text, "W": 400}],
        "CMT": "STMultiSection(E1)", "LRI": 1, "RRI": 2, "VLs": [],
    }
    raw = json.dumps(obj, ensure_ascii=False)
    if native:
        raw = raw.replace("\\r\\n", "\\u000d\\u000a")
    out = (BOM if bom else b"") + raw.encode("utf-8")
    if trailing:
        out += b"\r\n"
    return out


def write_archive(path, bodies, guid="aaaaaaaa-1111-2222-3333-444444444444"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(guid + "/" + guid + ".oem", b"<data/>")
        for name, raw in bodies.items():
            z.writestr(name, raw)


class ClassifyBodyTests(unittest.TestCase):
    def test_native_body_passes(self):
        r = F.classify_body(make_body())
        self.assertTrue(r["native"], r)
        self.assertEqual(r["native_escapes"], 2)
        self.assertEqual(r["short_escapes"], 0)
        self.assertEqual(r["st_lines"], 3)
        self.assertEqual(r["bare_lf"], 0)
        self.assertFalse(r["probe"])

    def test_python_json_dumps_style_is_rejected(self):
        r = F.classify_body(make_body(native=False, bom=False, trailing=False))
        self.assertFalse(r["native"])
        self.assertTrue(any("short_escape" in x for x in r["reasons"]), r)
        self.assertIn("no_trailing_crlf", r["reasons"])
        self.assertIn("no_utf8_bom", r["reasons"])

    def test_short_escape_alone_is_enough_to_fail(self):
        r = F.classify_body(make_body(native=False))
        self.assertFalse(r["native"])
        self.assertTrue(any("short_escape" in x for x in r["reasons"]), r)
        self.assertTrue(r["bom"])
        self.assertTrue(r["trailing_crlf"])

    def test_missing_bom_alone_is_enough_to_fail(self):
        r = F.classify_body(make_body(bom=False))
        self.assertFalse(r["native"])
        self.assertIn("no_utf8_bom", r["reasons"])

    def test_probe_is_detected(self):
        r = F.classify_body(make_body(probe=True))
        self.assertTrue(r["probe"])
        self.assertFalse(r["native"])
        self.assertIn("compile_probe_present", r["reasons"])

    def test_bare_lf_in_st_is_detected(self):
        r = F.classify_body(make_body(st="A\r\nB\n"))
        self.assertEqual(r["bare_lf"], 1)
        self.assertFalse(r["native"])

    def test_invalid_json_returns_reason_without_raising(self):
        r = F.classify_body(BOM + b"{not json" + b"\r\n")
        self.assertFalse(r["native"])
        self.assertTrue(any("json_decode_failed" in x for x in r["reasons"]))

    def test_empty_body_is_not_treated_as_native(self):
        r = F.classify_body(BOM + b'{"CLs":[],"RRI":1,"VLs":[]}' + b"\r\n")
        self.assertFalse(r["native"])
        self.assertTrue(any("no_native_escape" in x for x in r["reasons"]), r)
        self.assertEqual(r["cls_count"], 0)

    def test_multiple_concatenated_json_documents_are_supported(self):
        first = make_body(st="A\r\n")
        second = make_body(st="B\r\n", bom=False, trailing=False)
        r = F.classify_body(first + b"\r\n" + second + b"\r\n")
        self.assertTrue(r["native"], r)
        self.assertEqual(r["cls_count"], 2)
        self.assertEqual(r["st_crlf"], 2)


class ArchiveCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_check_native_archive_passes(self):
        p = os.path.join(self.tmp.name, "native.smc2")
        write_archive(p, {"sol/b1.xml": make_body()})
        r = F.check_archive(p)
        self.assertTrue(r["zip_ok"])
        self.assertEqual(r["entries_checked"], 1)
        self.assertTrue(r["pass"], r["failed"])

    def test_check_foreign_serialization_archive_fails(self):
        p = os.path.join(self.tmp.name, "foreign.smc2")
        write_archive(p, {"sol/b1.xml": make_body(native=False)})
        r = F.check_archive(p)
        self.assertFalse(r["pass"])
        self.assertIn("sol/b1.xml", r["failed"])

    def test_probe_archive_fails(self):
        p = os.path.join(self.tmp.name, "probe.smc2")
        write_archive(p, {"sol/b1.xml": make_body(probe=True)})
        self.assertFalse(F.check_archive(p)["pass"])


class NormalizedDiffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.g1 = "aaaaaaaa-1111-2222-3333-444444444444"
        self.g2 = "bbbbbbbb-9999-8888-7777-666666666666"

    def test_guid_rotation_does_not_look_like_mass_change(self):
        a = os.path.join(self.tmp.name, "a.smc2")
        b = os.path.join(self.tmp.name, "b.smc2")
        common = {self.g1 + "/b1.xml": make_body(), self.g1 + "/axis.xml": b"<axis/>"}
        write_archive(a, common, guid=self.g1)
        write_archive(b, {k.replace(self.g1, self.g2): v for k, v in common.items()},
                      guid=self.g2)
        r = F.compare_archives(a, b)
        self.assertEqual(r["added"], [])
        self.assertEqual(r["removed"], [])
        self.assertEqual(r["changed"], [])
        self.assertTrue(F.entry_identical(a, b, "b1.xml"))
        self.assertTrue(F.entry_identical(a, b, "axis.xml"))

    def test_real_content_change_is_reported(self):
        a = os.path.join(self.tmp.name, "a.smc2")
        b = os.path.join(self.tmp.name, "b.smc2")
        write_archive(a, {self.g1 + "/b1.xml": make_body()}, guid=self.g1)
        write_archive(b, {self.g2 + "/b1.xml": make_body(st="CHANGED\r\n")}, guid=self.g2)
        r = F.compare_archives(a, b)
        self.assertEqual(r["changed"], ["b1.xml"])
        self.assertFalse(F.entry_identical(a, b, "b1.xml"))

    def test_top_level_guid_prefixed_entries_are_normalized(self):
        a = os.path.join(self.tmp.name, "a.smc2")
        b = os.path.join(self.tmp.name, "b.smc2")
        write_archive(a, {self.g1 + ".manifest": b"v1"}, guid=self.g1)
        write_archive(b, {self.g2 + ".manifest": b"v1"}, guid=self.g2)
        r = F.compare_archives(a, b)
        self.assertEqual(r["added"], [])
        self.assertEqual(r["removed"], [])
        self.assertEqual(r["changed"], [])

    def test_missing_entry_is_not_reported_as_identical(self):
        a = os.path.join(self.tmp.name, "a.smc2")
        b = os.path.join(self.tmp.name, "b.smc2")
        write_archive(a, {self.g1 + "/b1.xml": make_body()}, guid=self.g1)
        write_archive(b, {self.g2 + "/axis.xml": b"<axis/>"}, guid=self.g2)
        self.assertFalse(F.entry_identical(a, b, "b1.xml"))


if __name__ == "__main__":
    unittest.main()
