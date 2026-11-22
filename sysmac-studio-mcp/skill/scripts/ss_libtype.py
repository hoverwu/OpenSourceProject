# -*- coding: utf-8 -*-
"""ss_libtype.py <路径.slr|.smc2> [--json] [--quiet] —— 离线判定 Sysmac 库类型（只读，不开界面）
作者：hoverwu ｜ 版本：0.1.0 ｜ 实测：Sysmac Studio V1.68 64bit / Win11

为什么要有这个脚本
------------------
判型是整个逆向链的第一道岔路口，判错会把后面全带偏。历史上有两个坑都是"数标签"数错的：

1. **HTML 转义坑**（2026-11-21 踩到）：PouBody 实体的正文是
   `StructuredTextModel` 里**再包一层 XML 字符串**，其中 `<EncryptedFile>` 是以
   `&lt;EncryptedFile&gt;` 形式存的。直接对原始 XML 数 `<EncryptedFile>` 会得到 **0**，
   于是误判"这个库没有加密源码、AES 配方不适用"。**必须先 html.unescape 再数。**
2. **有密文 ≠ 源码被隐藏**（2026-11-21 实测）：`IsDisableSourceDisplay=false` 的
   「常规库」里密文照样在（Sysmac 自己解密后显示）。只看 `EncryptedFile` 计数会把
   "可以直接看源码的库" 当成 "需要解密的库"，反过来也会把"重建后仍是密文壳"的库
   误认为没重建成功。

所以本脚本的判据是 **旗标为主、载体形态为辅**，并且**同时打印 raw 与 unescaped 两个计数**
——两个数不一致本身就是那条陷阱的指纹，看得见就不会踩。

模式
----
  <path>       判型并打印结论（人读）
  --json       同上，输出机器可读 JSON
  --quiet      只打印一行结论（脚本串联用）
  --selftest   用内置夹具自检（含"转义样本"与"BuildOption 干扰样本"），失败退出码 3

判型口径（与三份 Skill 一致）
----------------------------
  NO_SOURCE      IsSource=false 或 IsBackwardCompatibleNoSource=true
                 → 无源码库：AES 不适用，走编译体解析；有明文参照可走 rebuild 路径 c
  AES_HIDDEN     IsSource=true + IsDisableSourceDisplay=true + 有密文
                 → 常规库 + 禁用源显示：走无源库解密流程 §4 解密
  AES_VISIBLE    IsSource=true + IsDisableSourceDisplay=false + 有密文
                 → 密文仍在但显示已开：Sysmac 会自己解密显示，无需解密（密文只是残留）
  PLAIN_VISIBLE  IsSource=true + IsDisableSourceDisplay=false + 无密文 + 有明文 Text
                 → 源可见库（明文装配 / 重建产物），可直接导出
  UNKNOWN        未找到 LibraryModel 或旗标缺失 → 不猜，按 UNKNOWN 处理

关键实测教训
------------
- `.smc2` 里通常有**两个** `LibraryModel`：`ReferredLibraries>ReferredLibrary` 下的那个才是
  被引用库；`BuildOption` 下的那个是**工程自身**的构建选项（Name=工程名，`IsDisableSourceDisplay=true`
  是正常的）。拿错一个就判反 —— 本脚本按祖先链剔除 `BuildOption`。
- 实体 `.xml` 里凡是 PouBody 正文，整份文件**不是合法 XML**（内层又有一个 `<?xml?>` 声明），
  ET 解析必然失败；所以旗标用 ET 读，正文用字符串/正则数，两条路分开走。
- 有的库一个 POU 体实体里**同时**有 `<EncryptedFile>` 与 `<Text>`（重建中途态）→ 两者都报，
  判型按旗标，不按体。
- 只读：本脚本不写任何文件、不改 zip、不解密。传进来的路径可以是原件（仍建议先 copy 一份）。

用法示例
--------
  python ss_libtype.py "库.slr"
  python ss_libtype.py "工程.smc2" --json
  python ss_libtype.py --selftest
"""
import argparse
import hashlib
import html
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

VERSION = "0.1.0"

TAG_ENC = "<EncryptedFile>"
TAG_BUILT = "<BuiltLibraryFile"
TAG_STM = "<StructuredTextModel"
TEXT_RE = re.compile(r"<Text[^>]*>(.*?)</Text>", re.S)
UNICODE_RE = re.compile(r"<Unicode>([^<]*)</Unicode>")

FLAG_NAMES = ("IsSource", "IsDisableSourceDisplay",
              "IsBackwardCompatibleNoSource", "Password")

NEXT = {
    "NO_SOURCE": "无源码库：AES 不适用 → sysmac-build-artifact-capture（编译体解析）；"
                 "若已有同版本明文参照 → 无源库重建流程 路径 c",
    "AES_HIDDEN": "常规库+禁显：走无源库解密流程 §4 解密（key/IV 由 EncryptionLock 自包含推导）",
    "AES_VISIBLE": "密文仍在但显示已开：无需解密，Sysmac 会自己解密显示；要交付明文再走 decrypt 取文本",
    "PLAIN_VISIBLE": "源可见库（明文装配/重建产物）：可直接导出/对照，无需解密",
    "UNKNOWN": "未找到可判的 LibraryModel 或旗标缺失 → 不要猜，按未知处理并记录样本",
}


def _ln(e):
    return e.tag.rsplit("}", 1)[-1]


def _txt(e, name):
    for x in e.iter():
        if _ln(x) == name:
            return (x.text or "").strip()
    return None


def _sha256(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _models(zf, names):
    """返回所有 LibraryModel 记录（含祖先链 role）。"""
    out = []
    for n in names:
        if not n.endswith(".xml"):
            continue
        raw = zf.read(n)
        try:
            root = ET.fromstring(raw.decode("utf-8-sig", errors="replace"))
        except Exception:
            continue  # PouBody 正文等非良构 XML，正常
        parents = {c: p for p in root.iter() for c in p}
        for e in root.iter():
            if _ln(e) != "LibraryModel":
                continue
            chain = []
            cur = e
            while cur in parents:
                cur = parents[cur]
                chain.append(_ln(cur))
            chain.reverse()
            role = "buildoption" if "BuildOption" in chain else (
                "referred" if "ReferredLibraries" in chain else "entity")
            rec = {"entry": n.split("/")[-1], "role": role,
                   "chain": chain[:6], "flags": {}}
            for f in FLAG_NAMES:
                rec["flags"][f] = _txt(e, f)
            for f in ("Name", "LibraryId", "Version", "Revision"):
                rec[f] = _txt(e, f)
            out.append(rec)
    return out


def analyze(path):
    """只读分析一个 .slr / .smc2，返回 dict。"""
    r = {"path": os.path.abspath(path), "version": VERSION, "warnings": [], "errors": []}
    if not os.path.isfile(path):
        r["errors"].append("文件不存在")
        return r
    r["size"] = os.path.getsize(path)
    r["sha256"] = _sha256(path)
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        r["errors"].append("不是 ZIP 容器（.slr/.smc2 应为 ZIP）")
        return r
    names = zf.namelist()
    r["entries"] = len(names)
    r["kind_container"] = "zip"

    # ---- 正文/载体计数（raw vs unescaped 双计）----
    raw_enc = un_enc = raw_built = un_built = 0
    n_stm = plain_bodies = cipher_bodies = built_bodies = empty_bodies = 0
    unicode_hist = {}
    body_rows = []
    for n in names:
        if not n.endswith(".xml"):
            continue
        raw = zf.read(n)
        raw_txt = raw.decode("utf-8-sig", errors="replace")
        un = html.unescape(raw_txt)
        raw_enc += raw_txt.count(TAG_ENC)
        un_enc += un.count(TAG_ENC)
        raw_built += raw_txt.count(TAG_BUILT)
        un_built += un.count(TAG_BUILT)
        for u in UNICODE_RE.findall(un):
            unicode_hist[u] = unicode_hist.get(u, 0) + 1
        if TAG_STM not in un:
            continue
        n_stm += 1
        has_cipher = TAG_ENC in un
        has_built = TAG_BUILT in un
        m = TEXT_RE.search(un)
        tlen = len(m.group(1)) if m else 0
        if has_cipher:
            kind = "cipher"
            cipher_bodies += 1
        elif has_built:
            kind = "built"
            built_bodies += 1
        elif tlen:
            kind = "plain"
            plain_bodies += 1
        else:
            kind = "empty"
            empty_bodies += 1
        body_rows.append({"entry": n.split("/")[-1], "kind": kind,
                          "cipher": has_cipher, "built": has_built,
                          "text_len": tlen})

    r["counts"] = {
        "encrypted_file_raw": raw_enc,
        "encrypted_file_unescaped": un_enc,
        "built_library_file_raw": raw_built,
        "built_library_file_unescaped": un_built,
        "structured_text_models": n_stm,
        "bodies_cipher": cipher_bodies,
        "bodies_plain": plain_bodies,
        "bodies_built": built_bodies,
        "bodies_empty": empty_bodies,
        "unicode": unicode_hist,
    }
    r["bodies"] = body_rows

    # ---- 旗标（ET）----
    models = _models(zf, names)
    r["library_models"] = models
    cand = [m for m in models if m["role"] != "buildoption"]
    bo = [m for m in models if m["role"] == "buildoption"]
    if not cand:
        cand = models
    primary = None
    for m in cand:
        if m.get("LibraryId"):
            primary = m
            break
    if primary is None and cand:
        primary = cand[0]
    r["primary_model"] = primary

    # ---- 判型 ----
    verdict, reason = "UNKNOWN", "未找到 LibraryModel"
    if primary:
        f = primary["flags"]
        is_src = (f.get("IsSource") or "").lower()
        dis = (f.get("IsDisableSourceDisplay") or "").lower()
        nos = (f.get("IsBackwardCompatibleNoSource") or "").lower()
        has_cipher = un_enc > 0 or cipher_bodies > 0
        has_plain = plain_bodies > 0
        if is_src == "false" or nos == "true":
            verdict = "NO_SOURCE"
            reason = "IsSource=false" if is_src == "false" else "IsBackwardCompatibleNoSource=true"
        elif is_src == "true" and dis == "true" and has_cipher:
            verdict, reason = "AES_HIDDEN", "IsSource=true + IsDisableSourceDisplay=true + 有密文"
        elif is_src == "true" and dis == "false" and has_cipher:
            verdict, reason = "AES_VISIBLE", "IsSource=true + IsDisableSourceDisplay=false + 有密文（显示已开）"
        elif is_src == "true" and dis == "false" and has_plain:
            verdict, reason = "PLAIN_VISIBLE", "IsSource=true + 无密文 + 有明文 Text"
        elif is_src == "true" and dis == "true" and not has_cipher:
            verdict, reason = "NO_SOURCE", "IsSource=true 但无密文且无明文（体缺失）"
        else:
            reason = "旗标组合未覆盖：IsSource=%r Disable=%r" % (is_src, dis)
    r["verdict"] = verdict
    r["reason"] = reason
    r["next"] = NEXT[verdict]

    # ---- 警告 ----
    if raw_enc != un_enc:
        r["warnings"].append(
            "ESCAPING: 原始 XML 里 %s 计数=%d，html.unescape 后=%d —— 直接数原始 XML 会误判"
            "「无加密源码」，判型必须先反转义（这是已知陷阱的指纹）"
            % (TAG_ENC, raw_enc, un_enc))
    if verdict == "AES_VISIBLE":
        r["warnings"].append(
            "有密文但 IsDisableSourceDisplay=false：**不要**因为看到 EncryptedFile 就断言源码被隐藏，"
            "这类库 Sysmac 会直接解密显示")
    if bo and primary and bo[0]["flags"].get("IsDisableSourceDisplay") != primary["flags"].get("IsDisableSourceDisplay"):
        r["warnings"].append(
            "BuildOption 下的 LibraryModel（Name=%r）旗标与库实体不同（Disable=%r vs %r）——"
            "它是工程自身的构建选项，不能用来判库类型"
            % (bo[0].get("Name"), bo[0]["flags"].get("IsDisableSourceDisplay"),
               primary["flags"].get("IsDisableSourceDisplay")))
    if unicode_hist.get("Utf16"):
        r["warnings"].append(
            "Utf16 信封 %d 个：本工具链**没有 Utf16 样本**，解密侧遇到应拒绝并记录，不要猜编码"
            % unicode_hist["Utf16"])
    if verdict == "NO_SOURCE" and un_built == 0:
        r["warnings"].append("判为 NO_SOURCE 但没数到 BuiltLibraryFile：可能不是编译体内嵌形态，复核后再下结论")
    return r


def render(r):
    out = []
    out.append("FILE    %s" % r.get("path"))
    if r.get("errors"):
        for e in r["errors"]:
            out.append("ERROR   %s" % e)
        return "\n".join(out)
    out.append("        size=%s B  entries=%s  sha256=%s…"
               % (format(r["size"], ","), r["entries"], r["sha256"][:16]))
    p = r.get("primary_model")
    if p:
        f = p["flags"]
        out.append("TYPE    %-13s %s" % (r["verdict"], r["reason"]))
        out.append("FLAGS   IsSource=%s  IsDisableSourceDisplay=%s  IsBackwardCompatibleNoSource=%s  Password=%s"
                   % (f.get("IsSource"), f.get("IsDisableSourceDisplay"),
                      f.get("IsBackwardCompatibleNoSource") or "(absent)",
                      "(empty)" if not f.get("Password") else "(set)"))
        out.append("        model: Name=%r LibraryId=%s Version=%s role=%s"
                   % (p.get("Name"), (p.get("LibraryId") or "")[:8], p.get("Version"), p["role"]))
    else:
        out.append("TYPE    %-13s %s" % (r["verdict"], r["reason"]))
    c = r["counts"]
    out.append("BODY    EncryptedFile=%d (raw=%d)  BuiltLibraryFile=%d  StructuredTextModel=%d  "
               "cipher=%d plain=%d built=%d empty=%d"
               % (c["encrypted_file_unescaped"], c["encrypted_file_raw"],
                  c["built_library_file_unescaped"], c["structured_text_models"],
                  c["bodies_cipher"], c["bodies_plain"], c["bodies_built"], c["bodies_empty"]))
    if c["unicode"]:
        out.append("UNICODE " + "  ".join("%s=%d" % kv for kv in sorted(c["unicode"].items())))
    out.append("NEXT    %s" % r["next"])
    for w in r["warnings"]:
        out.append("WARN    %s" % w)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 自检：内置夹具，专门钉住两个陷阱
# --------------------------------------------------------------------------- #
LIBMODEL = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<data><data><LibraryModel>'
    '<Name>Demo</Name><LibraryId>11111111-2222-3333-4444-555555555555</LibraryId>'
    '<Version>1.0.0</Version><Password></Password>'
    '<IsSource>%s</IsSource><IsDisableSourceDisplay>%s</IsDisableSourceDisplay>%s'
    '</LibraryModel></data></data>'
)

BODY_ESCAPED = (
    '<?xml version="1.0" encoding="utf-16"?>'
    '<StructuredTextModel>&lt;EncryptedFile&gt;'
    '&lt;EncryptionLock&gt;AAAA1111/BBBB2222----------------&lt;/EncryptionLock&gt;'
    '&lt;Unicode&gt;Utf8&lt;/Unicode&gt;&lt;Body&gt;QUJDRA==&lt;/Body&gt;'
    '&lt;/EncryptedFile&gt;</StructuredTextModel>'
)

BODY_PLAIN = (
    '<?xml version="1.0" encoding="utf-16"?>'
    '<StructuredTextModel><Text>(* demo *) x := 1;</Text></StructuredTextModel>'
)

BUILDOPT = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<data><data><ReferredLibrariesModel><BuildOption><data><LibraryModel>'
    '<Name>MyProject</Name><IsSource>true</IsSource>'
    '<IsDisableSourceDisplay>true</IsDisableSourceDisplay>'
    '</LibraryModel></data></BuildOption></ReferredLibrariesModel></data></data>'
)


def _mkzip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files:
            z.writestr(name, text.encode("utf-8"))
    return buf.getvalue()


def _run_on_bytes(blob, tmpdir, tag):
    p = os.path.join(tmpdir, tag + ".slr")
    with open(p, "wb") as f:
        f.write(blob)
    return analyze(p)


def selftest():
    import tempfile
    ok = True
    results = []

    def check(name, cond, detail=""):
        nonlocal ok
        results.append("%s %-46s %s" % ("PASS" if cond else "FAIL", name, detail))
        if not cond:
            ok = False

    with tempfile.TemporaryDirectory() as td:
        # 夹具 1：转义密文 + 禁显 → 必须数到 1，且报 ESCAPING 警告
        r = _run_on_bytes(_mkzip([
            ("e1.xml", LIBMODEL % ("true", "true", "")),
            ("e2.xml", BODY_ESCAPED),
        ]), td, "esc")
        check("转义样本 unescaped 计数=1", r["counts"]["encrypted_file_unescaped"] == 1,
              str(r["counts"]["encrypted_file_unescaped"]))
        check("转义样本 raw 计数=0（陷阱可复现）", r["counts"]["encrypted_file_raw"] == 0,
              str(r["counts"]["encrypted_file_raw"]))
        check("转义样本触发 ESCAPING 警告",
              any(w.startswith("ESCAPING") for w in r["warnings"]))
        check("转义样本判型=AES_HIDDEN", r["verdict"] == "AES_HIDDEN", r["verdict"])

        # 夹具 2：明文体 + 显示开 → PLAIN_VISIBLE
        r = _run_on_bytes(_mkzip([
            ("e1.xml", LIBMODEL % ("true", "false", "")),
            ("e2.xml", BODY_PLAIN),
        ]), td, "plain")
        check("明文样本判型=PLAIN_VISIBLE", r["verdict"] == "PLAIN_VISIBLE", r["verdict"])
        check("明文样本密文计数=0", r["counts"]["encrypted_file_unescaped"] == 0)

        # 夹具 3：无源码库
        r = _run_on_bytes(_mkzip([
            ("e1.xml", LIBMODEL % ("false", "true",
                                   "<IsBackwardCompatibleNoSource>true</IsBackwardCompatibleNoSource>")),
            ("e2.xml", '<StructuredTextModel><BuiltLibraryFile TrackingId="x"/></StructuredTextModel>'),
        ]), td, "nosrc")
        check("无源码样本判型=NO_SOURCE", r["verdict"] == "NO_SOURCE", r["verdict"])

        # 夹具 4：BuildOption 干扰（工程自身 Disable=true + 被引用库 Disable=false）
        referred = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<data><ReferredLibrariesModel><ReferredLibraries><ReferredLibrary><data>'
            '<LibraryModel><Name>Demo</Name>'
            '<LibraryId>11111111-2222-3333-4444-555555555555</LibraryId>'
            '<IsSource>true</IsSource><IsDisableSourceDisplay>false</IsDisableSourceDisplay>'
            '</LibraryModel></data></ReferredLibrary></ReferredLibraries>'
            '</ReferredLibrariesModel></data>'
        )
        r = _run_on_bytes(_mkzip([
            ("e1.xml", BUILDOPT),
            ("e2.xml", referred),
            ("e3.xml", BODY_ESCAPED),
        ]), td, "buildopt")
        check("BuildOption 干扰下判型=AES_VISIBLE（取被引用库）",
              r["verdict"] == "AES_VISIBLE", r["verdict"])
        check("BuildOption 干扰下触发旗标不一致警告",
              any("BuildOption" in w for w in r["warnings"]))
        check("BuildOption 干扰下 primary 不是 buildoption",
              (r["primary_model"] or {}).get("role") != "buildoption")

        # 夹具 5：坏文件 → 明确报错而不是静默
        p = os.path.join(td, "bad.slr")
        with open(p, "wb") as f:
            f.write(b"not a zip")
        r = analyze(p)
        check("非 ZIP 输入报错", bool(r["errors"]))

    print("ss_libtype.py %s selftest" % VERSION)
    for line in results:
        print("  " + line)
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 3


def main():
    ap = argparse.ArgumentParser(description="离线判定 Sysmac 库类型（.slr/.smc2，只读）")
    ap.add_argument("path", nargs="?", help=".slr 或 .smc2 路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="只打印一行结论")
    ap.add_argument("--selftest", action="store_true", help="内置夹具自检")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.path:
        ap.print_help()
        return 2

    r = analyze(a.path)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif a.quiet:
        print("%s\t%s\t%s" % (r.get("verdict"), r.get("counts", {}).get("encrypted_file_unescaped"),
                              r.get("path")))
    else:
        print(render(r))
    if r.get("errors"):
        return 2
    return 0 if r.get("verdict") != "UNKNOWN" else 3


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
