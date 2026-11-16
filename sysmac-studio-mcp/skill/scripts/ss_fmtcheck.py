# -*- coding: utf-8 -*-
"""Offline pre-flight checker for .smc2 segment serialization and archive diffs.

Why this exists: a PouBody segment written with Python json.dumps passes
json.loads / zipfile.testzip() / ss_verify.py, but Sysmac's loader silently
rejects it. The in-memory program body then degrades to an empty ladder and
compilation reports 0 errors even for deliberate undefined identifiers
("false 0 errors"). This module detects that class of damage *before* opening
the project in Sysmac.

Portable: stdlib only, no machine paths, no UI calls, no writes.

Usage:
    python ss_fmtcheck.py check <file.smc2> [--verbose]
    python ss_fmtcheck.py diff <a.smc2> <b.smc2> [--body <id>] [--axis <id>]
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile

BOM = b"\xef\xbb\xbf"
NATIVE_NEWLINE = "\\u000d\\u000a"
SHORT_NEWLINE = "\\r\\n"
PROBE_MARK = "ZZ_COMPILE_PROBE"


def find_oem(zf: zipfile.ZipFile) -> str:
    """Return the top-level .oem entry name, or '' if absent."""
    for name in zf.namelist():
        if name.lower().endswith(".oem"):
            return name
    return ""


def oem_guid(oem_name: str) -> str:
    """Return the rotating top-level GUID from an .oem entry path."""
    if not oem_name:
        return ""
    return oem_name.split("/")[0]


def classify_body(raw: bytes) -> dict:
    """Classify one PouBody XML payload as Sysmac-native or foreign JSON.

    Returns a plain dict so callers can log/serialize the result. No exception
    is raised for malformed input; the `reasons` list explains every failure.
    """
    reasons: list[str] = []
    bom = raw.startswith(BOM)
    if not bom:
        reasons.append("no_utf8_bom")

    trailing_crlf = raw.endswith(b"\r\n")
    if not trailing_crlf:
        reasons.append("no_trailing_crlf")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return {
            "native": False,
            "bom": bom,
            "trailing_crlf": trailing_crlf,
            "reasons": ["decode_failed: %s" % type(exc).__name__],
        }

    # A PouBody file may hold several concatenated JSON documents (one per
    # section), so parse them all with raw_decode instead of a single loads().
    docs = []
    decoder = json.JSONDecoder()
    pos = 0
    try:
        while pos < len(text):
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text):
                break
            obj, pos = decoder.raw_decode(text, pos)
            docs.append(obj)
    except Exception as exc:
        return {
            "native": False,
            "bom": bom,
            "trailing_crlf": trailing_crlf,
            "reasons": ["json_decode_failed: %s" % type(exc).__name__],
        }
    if not docs:
        return {
            "native": False,
            "bom": bom,
            "trailing_crlf": trailing_crlf,
            "reasons": ["no_json_document"],
        }

    native_escapes = text.count(NATIVE_NEWLINE)
    short_escapes = text.count(SHORT_NEWLINE)
    if short_escapes:
        reasons.append("short_escape_%r" % SHORT_NEWLINE)
    if not native_escapes:
        reasons.append("no_native_escape_%r" % NATIVE_NEWLINE)

    cls_count = 0
    texts = []
    for doc in docs:
        cls = doc.get("CLs") if isinstance(doc, dict) else None
        if isinstance(cls, list):
            cls_count += len(cls)
            for item in cls:
                if isinstance(item, dict) and item.get("TXT"):
                    texts.append(item["TXT"])
    st = "".join(texts)
    st_crlf = st.count("\r\n")
    bare_lf = st.count("\n") - st_crlf
    if bare_lf:
        reasons.append("bare_lf_in_st")
    probe = PROBE_MARK in st
    if probe:
        reasons.append("compile_probe_present")

    return {
        "native": not reasons,
        "bom": bom,
        "trailing_crlf": trailing_crlf,
        "native_escapes": native_escapes,
        "short_escapes": short_escapes,
        "st_chars": len(st),
        "st_crlf": st_crlf,
        "st_lines": st_crlf + 1 if st else 0,
        "bare_lf": bare_lf,
        "cls_count": cls_count,
        "probe": probe,
        "reasons": reasons,
    }


def check_archive(path: str, verbose: bool = False) -> dict:
    """Check every ladder-body-looking XML entry in one archive."""
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        oem = find_oem(zf)
        bodies: dict[str, dict] = {}
        for name in zf.namelist():
            if not name.lower().endswith(".xml"):
                continue
            raw = zf.read(name)
            if not raw.startswith(BOM):
                continue
            try:
                head = raw.decode("utf-8-sig")[:200]
            except UnicodeDecodeError:
                continue
            if '"CLs"' not in head:
                continue
            bodies[name] = classify_body(raw)

    failed = {k: v for k, v in bodies.items() if not v["native"]}
    result = {
        "zip_ok": bad is None,
        "oem": oem,
        "oem_guid": oem_guid(oem),
        "entries_checked": len(bodies),
        "failed": failed,
        "pass": bad is None and bool(bodies) and not failed,
    }
    return result


def normalized_entries(zf: zipfile.ZipFile) -> dict:
    """Map archive entries to GUID-independent keys.

    Native saves rotate the top-level .oem GUID. Both '<guid>/<path>' and
    top-level '<guid>.<suffix>' entries are stripped of that prefix so a
    before/after diff shows only real content changes.
    """
    guid = oem_guid(find_oem(zf))
    out: dict[str, bytes] = {}
    for name in zf.namelist():
        key = name
        if guid:
            if key.startswith(guid + "/"):
                key = key[len(guid) + 1:]
            # The .oem entry itself is '<guid>/<guid>.oem': strip the folder
            # prefix above, then strip the same GUID from the basename too.
            if key.startswith(guid + "."):
                key = key[len(guid) + 1:]
        if key:
            out[key] = zf.read(name)
    return out


def compare_archives(a_path: str, b_path: str) -> dict:
    """Diff two archives after stripping the rotating top-level GUID."""
    with zipfile.ZipFile(a_path) as a, zipfile.ZipFile(b_path) as b:
        ea, eb = normalized_entries(a), normalized_entries(b)
    ka, kb = set(ea), set(eb)
    changed = sorted(k for k in ka & kb if ea[k] != eb[k])
    return {
        "guid_a": oem_guid(find_oem(zipfile.ZipFile(a_path))),
        "guid_b": oem_guid(find_oem(zipfile.ZipFile(b_path))),
        "entries_a": len(ea),
        "entries_b": len(eb),
        "added": sorted(ka - kb),
        "removed": sorted(kb - ka),
        "changed": changed,
    }


def entry_identical(a_path: str, b_path: str, basename: str) -> bool:
    """True when a named entry is byte-identical across two archives."""
    with zipfile.ZipFile(a_path) as a, zipfile.ZipFile(b_path) as b:
        ea, eb = normalized_entries(a), normalized_entries(b)
    return basename in ea and basename in eb and ea[basename] == eb[basename]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("path")
    p_check.add_argument("--verbose", action="store_true")
    p_diff = sub.add_parser("diff")
    p_diff.add_argument("a")
    p_diff.add_argument("b")
    p_diff.add_argument("--body", default="", help="PouBody basename to compare")
    p_diff.add_argument("--axis", default="", help="axis entity basename to compare")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        r = check_archive(args.path, args.verbose)
        print("zip_ok=%s" % r["zip_ok"])
        print("oem_guid=%s" % r["oem_guid"])
        print("entries_checked=%d" % r["entries_checked"])
        for name, v in sorted(r["failed"].items()):
            print("BAD %s reasons=%s" % (name, ",".join(v["reasons"])))
        print("RESULT=%s" % ("PASS" if r["pass"] else "FAIL"))
        return 0 if r["pass"] else 1

    r = compare_archives(args.a, args.b)
    print("guid_a=%s" % r["guid_a"])
    print("guid_b=%s" % r["guid_b"])
    print("entries=%d -> %d" % (r["entries_a"], r["entries_b"]))
    print("added=%d removed=%d changed=%d" % (
        len(r["added"]), len(r["removed"]), len(r["changed"])))
    for name in r["changed"][:40]:
        print("  ~ %s" % name)
    for label, base in (("body", args.body), ("axis", args.axis)):
        if base:
            print("%s_identical=%s" % (label, entry_identical(args.a, args.b, base)))
    print("RESULT=INFO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
