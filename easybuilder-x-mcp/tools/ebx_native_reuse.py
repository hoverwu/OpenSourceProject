# -*- coding: utf-8 -*-
"""EBX native screen cloning, lightweight queries, and snapshots (hoverwu / 0.1.0)."""
import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

if __package__:
    from .ebx_ai_socket import EBXSocket, EBXSocketError, require_ok
    from .ebx_native_codegen import import_succeeded
    from .ebx_native_patch import PatchError, canonical_hash
else:
    from ebx_ai_socket import EBXSocket, EBXSocketError, require_ok
    from ebx_native_codegen import import_succeeded
    from ebx_native_patch import PatchError, canonical_hash


def normalize_names(names):
    if not isinstance(names, list) or not names:
        raise PatchError("INVALID_NAMES", "new_names 必须是非空数组")
    normalized = []
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise PatchError("INVALID_NAMES", "画面名必须是非空字符串")
        name = name.strip()
        if "/" in name or "\\" in name:
            raise PatchError("INVALID_NAMES", "画面名不能包含路径分隔符")
        if name in normalized:
            raise PatchError("INVALID_NAMES", "new_names 不能重复")
        normalized.append(name)
    return normalized


def clone_archive(source_archive, new_names):
    if not isinstance(source_archive, dict):
        raise PatchError("INVALID_ARCHIVE", "源画面归档必须是对象")
    names = normalize_names(new_names)
    source = copy.deepcopy(source_archive)
    screens = source.get("body", {}).get("screens")
    if not isinstance(screens, list) or len(screens) != 1:
        raise PatchError("INVALID_ARCHIVE", "源归档必须且只能包含一个画面")
    template = screens[0]
    if not isinstance(template, dict):
        raise PatchError("INVALID_ARCHIVE", "源画面必须是对象")
    screens[:] = []
    for name in names:
        screen = copy.deepcopy(template)
        screen["name"] = name
        screens.append(screen)
    return source


def screen_fingerprint(screen):
    value = copy.deepcopy(screen)
    value.pop("name", None)
    return canonical_hash(value)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clone_screens(client, source_screen, new_names, dry_run=False, snapshot=False, evidence_dir="out/ai_socket"):
    if not isinstance(source_screen, str) or not source_screen.strip():
        raise PatchError("INVALID_SCREEN", "source_screen 不能为空")
    names = normalize_names(new_names)
    if source_screen.strip() in names:
        raise PatchError("NAME_CONFLICT", "新画面名不能与源画面相同")
    started = time.perf_counter()
    exported = require_ok(client.call("exportScreenView", {"screen_name": source_screen.strip()}))
    archive = clone_archive(exported["archive"], names)
    conflicts = require_ok(client.call("detectImportConflicts", {"archive": archive}))
    if conflicts.get("has_conflicts") or conflicts.get("conflict_count"):
        return {
            "ok": False,
            "code": "IMPORT_CONFLICT",
            "message": "目标画面名已存在或归档含冲突；未执行导入",
            "source_screen": source_screen.strip(),
            "new_names": names,
            "conflicts": conflicts,
        }
    source_hash = screen_fingerprint(archive["body"]["screens"][0])
    plan = {
        "ok": True,
        "dry_run": bool(dry_run),
        "source_screen": source_screen.strip(),
        "new_names": names,
        "source_hash": source_hash,
        "objects_per_screen": len(archive["body"]["screens"][0].get("objects", [])),
        "conflicts": conflicts,
    }
    if dry_run:
        plan["elapsed_seconds"] = round(time.perf_counter() - started, 4)
        return plan
    imported = require_ok(client.call("importScreenView", {"archive": archive}))
    changeset = imported.get("changeset_result", imported)
    plan["import_succeeded"] = import_succeeded({"success": True, **imported})
    plan["missing_references"] = changeset.get("missing_references", [])
    checks = []
    for name in names:
        try:
            view = require_ok(client.call("getViewByScreenName", {"screen_name": name}))
            screen = view["screen"]
            actual_hash = screen_fingerprint(screen)
            checks.append({
                "name": name,
                "ok": actual_hash == source_hash,
                "hash": actual_hash,
                "objects": len(screen.get("objects", [])),
            })
        except EBXSocketError as exc:
            checks.append({"name": name, "ok": False, "error": str(exc)})
    plan["verification"] = checks
    plan["ok"] = plan["import_succeeded"] and all(item["ok"] for item in checks)
    if not plan["ok"]:
        plan["code"] = "CLONE_VERIFY_FAILED"
        plan["message"] = "导入可能已部分生效；请检查 new_names，失败时需在 EBX 手工删除对应画面"
    if snapshot:
        plan["snapshots"] = []
        for name in names:
            try:
                plan["snapshots"].append(capture_snapshot(client, name, evidence_dir))
            except (PatchError, EBXSocketError, OSError) as exc:
                plan["snapshots"].append({
                    "ok": False,
                    "screen": name,
                    "code": getattr(exc, "code", "ERROR"),
                    "error": str(exc),
                })
    plan["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    run_id = "%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), os.getpid())
    os.makedirs(evidence_dir, exist_ok=True)
    write_json(os.path.join(evidence_dir, "native_clone_%s_archive.json" % run_id), archive)
    write_json(os.path.join(evidence_dir, "native_clone_%s_evidence.json" % run_id), plan)
    return plan


def query_objects(client, screen=None, screens=None, all_screens=False):
    selectors = sum(value is not None and value is not False for value in (screen, screens, all_screens))
    if selectors != 1:
        raise PatchError("INVALID_QUERY", "screen、screens、all_screens 必须且只能指定一个")
    if screen is not None:
        if not isinstance(screen, str) or not screen.strip():
            raise PatchError("INVALID_QUERY", "screen 不能为空")
        params = {"screen_name": screen.strip()}
    elif screens is not None:
        if not isinstance(screens, list) or not screens:
            raise PatchError("INVALID_QUERY", "screens 必须是非空数组")
        params = {"screen_names": normalize_names(screens)}
    else:
        if all_screens is not True:
            raise PatchError("INVALID_QUERY", "all_screens 必须为 true")
        params = {"all_screens": True}
    result = require_ok(client.call("queryObjects", params))
    return {"ok": True, **result}


def capture_snapshot(client, screen, evidence_dir="out/ai_socket"):
    if not isinstance(screen, str) or not screen.strip():
        raise PatchError("INVALID_SCREEN", "screen 不能为空")
    result = require_ok(client.call("getSnapshot", {"screen_name": screen.strip()}))
    source = result.get("absolute_path")
    if not source or not os.path.isfile(source):
        raise PatchError("SNAPSHOT_MISSING", "EBX 未返回可读取的快照文件")
    target_dir = os.path.join(evidence_dir, "snapshots")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, os.path.basename(source))
    shutil.copy2(source, target)
    return {
        "ok": True,
        "screen": screen.strip(),
        "path": target,
        "file_name": os.path.basename(target),
        "sha256": hashlib.sha256(Path(target).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description="EBX 原生画面克隆、轻量查询与快照")
    sub = parser.add_subparsers(dest="command", required=True)
    clone = sub.add_parser("clone")
    clone.add_argument("--source", required=True)
    clone.add_argument("--names", required=True, help="逗号分隔的新画面名")
    clone.add_argument("--dry-run", action="store_true")
    clone.add_argument("--snapshot", action="store_true")
    query = sub.add_parser("query")
    query.add_argument("--screen")
    query.add_argument("--screens", help="逗号分隔的画面名")
    query.add_argument("--all-screens", action="store_true")
    shot = sub.add_parser("snapshot")
    shot.add_argument("--screen", required=True)
    for command in (clone, query, shot):
        command.add_argument("--port", type=int)
        command.add_argument("--evidence-dir", default="out/ai_socket")
    args = parser.parse_args()
    client = EBXSocket(args.port)
    try:
        if args.command == "clone":
            names = [item.strip() for item in args.names.split(",") if item.strip()]
            result = clone_screens(client, args.source, names, args.dry_run, args.snapshot, args.evidence_dir)
        elif args.command == "query":
            screens = None if args.screens is None else [item.strip() for item in args.screens.split(",") if item.strip()]
            result = query_objects(client, args.screen, screens, args.all_screens)
        else:
            result = capture_snapshot(client, args.screen, args.evidence_dir)
    except (PatchError, EBXSocketError, OSError, ValueError) as exc:
        result = {"ok": False, "code": getattr(exc, "code", "ERROR"), "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
