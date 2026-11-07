#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ebx_probe.py - EasyBuilder X automation-surface probe (UIA / modules / windows / screenshot)
author: hoverwu  version: 0.1.0  date: 2026-11-06

Subcommands:
  wins                      list EBX top-level windows -> out/wins.txt
  mods                      list loaded DLLs of EBX process (tech-stack verdict) -> out/mods.txt
  tree [maxDepth] [out]     dump UIA tree (ControlType/Name/AutomationId/ClassName/rect) + histogram
  find <regex> [out]        search elements by Name | AutomationId | ClassName regex
  shot <out.png>            capture the EBX main window rect from the screen
  status                    integrity level, process info, install-dir probe -> out/status.txt

Rules baked in (from prior UIA automation work):
  - declare Per-Monitor DPI awareness before touching any rect/coordinate
  - never print CJK to the console (Git Bash + cp936); write UTF-8 files and Read them
  - search across ALL top-level HWNDs of the process (popups/menus are separate HWNDs)
"""
import sys, os, re, ctypes, subprocess
from ctypes import wintypes as wt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

_PF = os.environ.get("ProgramFiles", r"C:\Program Files")
_PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

# candidate process names / install dirs discovered empirically; extend as needed
PROC_KEYS = ["easybuilderx", "easybuilder x", "ebx", "weintek", "weinview", "wece", "cmt"]
INSTALL_CANDIDATES = ([os.path.dirname(os.environ["EBX_EXE"])] if os.environ.get("EBX_EXE") else []) + [
    os.path.join(_PF, "EasyBuilderX"),
    os.path.join(_PF, "EasyBuilder X"),
    os.path.join(_PF86, "EasyBuilderX"),
    os.path.join(_PF86, "EasyBuilder X"),
    os.path.join(_PF, "Weintek"),
    os.path.join(_PF86, "Weintek"),
    os.path.join(_PF86, "WeCE"),
]

def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "PROCESS_PER_MONITOR_DPI_AWARE"
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return "SYSTEM_DPI_AWARE"
        except Exception:
            return "NONE"

def w(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path

def note(msg):
    sys.stdout.write(str(msg).encode("ascii", "backslashreplace").decode("ascii").rstrip() + "\n")
    sys.stdout.flush()

# ---------------------------------------------------------------- process discovery
def enum_processes():
    """[(pid, name)] via Toolhelp32 (no psutil dependency)."""
    TH32CS_SNAPPROCESS = 0x2
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentPID", wt.DWORD),
                    ("th32Priority", wt.LONG), ("th32ClassID", wt.DWORD),
                    ("szExeFile", wt.CHAR * 260)]
    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(PE32)
    out = []
    k32 = ctypes.windll.kernel32
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            out.append((int(pe.th32ProcessID), pe.szExeFile.decode("mbcs", "ignore")))
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    return out

def ebx_procs():
    return [(p, n) for p, n in enum_processes() if any(k in n.lower() for k in PROC_KEYS)]

def module_list(pid):
    k32 = ctypes.windll.kernel32
    ps = ctypes.WinDLL("psapi.dll")
    ps.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
    ps.GetModuleFileNameExW.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.DWORD]
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    h = k32.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION|VM_READ
    if not h:
        return None, k32.GetLastError()
    # module handles must be c_void_p, else 64-bit truncation (OverflowError)
    n_mods = wt.DWORD(0)
    ps.EnumProcessModulesEx(h, None, 0, ctypes.byref(n_mods), 0x03)
    cnt = max(1, n_mods.value // ctypes.sizeof(wt.HMODULE))
    arr = (ctypes.c_void_p * cnt)()
    got = wt.DWORD(0)
    ok = ps.EnumProcessModulesEx(h, ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(got), 0x03)
    mods = []
    if ok:
        buf = ctypes.create_unicode_buffer(32768)
        for i in range(got.value // ctypes.sizeof(wt.HMODULE)):
            if ps.GetModuleFileNameExW(h, arr[i], buf, 32768):
                mods.append(buf.value)
    k32.CloseHandle(h)
    return mods, None

# ---------------------------------------------------------------- UIA
def uia():
    import uiautomation as auto
    auto.SetGlobalSearchTimeout(8)
    return auto

def top_windows(auto, pid):
    """all visible top-level windows of pid.
    NOTE: this uiautomation build has NO IsVisible; IsOffscreen is a PROPERTY (bool), not a method."""
    res = []
    root = auto.GetRootControl()
    for c in root.GetChildren():
        try:
            if c.ProcessId == pid and not c.IsOffscreen:
                res.append(c)
        except Exception:
            pass
    return res

def desc(el, auto, depth=0, maxdepth=14, maxkids=120, lines=None):
    if lines is None:
        lines = []
    try:
        r = el.BoundingRectangle
        rect = "%d,%d %dx%d" % (r.left, r.top, r.width(), r.height())
    except Exception:
        rect = "?"
    try:
        off = not el.IsOffscreen   # property, do NOT call
    except Exception:
        off = "?"
    lines.append("%s%s | N=%s | A=%s | C=%s | R=%s | hw=%d | on=%s" % (
        "  " * depth, el.ControlTypeName, (el.Name or "")[:60], el.AutomationId or "",
        el.ClassName or "", rect, el.NativeWindowHandle, off))
    if depth >= maxdepth:
        return lines
    try:
        kids = el.GetChildren()
    except Exception:
        kids = []
    for k in kids[:maxkids]:
        desc(k, auto, depth + 1, maxdepth, maxkids, lines)
    return lines

def cmd_wins():
    procs = ebx_procs()
    lines = ["procs: " + repr([(p, n) for p, n in procs])]
    if not procs:
        note("no EBX process found")
        note(w(os.path.join(OUT, "wins.txt"), "\n".join(lines)))
        return
    auto = uia()
    for pid, name in procs:
        lines.append("== pid %d (%s) ==" % (pid, name))
        for c in top_windows(auto, pid):
            r = c.BoundingRectangle
            lines.append("hwnd=%d class=%s title=%s rect=%d,%d %dx%d" % (
                c.NativeWindowHandle, c.ClassName, c.Name, r.left, r.top, r.width(), r.height()))
    p = w(os.path.join(OUT, "wins.txt"), "\n".join(lines))
    note("wrote %s lines=%d" % (p, len(lines)))

def cmd_mods():
    procs = ebx_procs()
    lines = ["procs: " + repr([(p, n) for p, n in procs])]
    for pid, name in procs:
        mods, err = module_list(pid)
        if mods is None:
            lines.append("== pid %d: OpenProcess failed err=%s (integrity mismatch?)" % (pid, err))
            continue
        lines.append("== pid %d: %d modules ==" % (pid, len(mods)))
        sig = {"qt": ["Qt6", "Qt5", "Qt6Core", "qwindows"],
               "dotnet_wpf": ["PresentationCore", "PresentationFramework", "WindowsBase", "clr.dll", "coreclr"],
               "dotnet_winforms": ["System.Windows.Forms"],
               "electron": ["libcef", "ffmpeg", "node.dll", "electron"],
               "activex_mfc": ["mfc1", "mfc140", "mfc100", "oleacc"],
               "cef_embedded": ["libcef"],
               "dx": ["d3d11", "d2d1", "dxgi"],
               "python": ["python3"],
               "tauri_webview2": ["WebView2Loader", "EmbeddedBrowser"],
               "fltk_or_raw_win32": ["comctl32", "user32"]}
        low = [m.lower() for m in mods]
        for k, needles in sig.items():
            hit = [n for n in needles if any(n.lower() in m for m in low)]
            if hit:
                lines.append("  SIGNAL %-18s %s" % (k, hit))
        for m in mods:
            base = os.path.basename(m).lower()
            if any(t in base for t in ("qt", "wpf", "presentation", "mfc", "cef", "electron", "webview",
                                        "python", "skia", "wx", "tk", "avalonia", "uno", ".net")):
                lines.append("  " + m)
        lines.append("  --- full list ---")
        lines.extend("  " + m for m in mods)
    p = w(os.path.join(OUT, "mods.txt"), "\n".join(lines))
    note("wrote %s lines=%d" % (p, len(lines)))

def cmd_tree(maxdepth=14, out=None):
    procs = ebx_procs()
    if not procs:
        note("no EBX process found"); return
    auto = uia()
    lines = []
    hist = {}
    for pid, name in procs:
        wins = top_windows(auto, pid)
        lines.append("===== pid %d (%s) windows=%d =====" % (pid, name, len(wins)))
        for c in wins:
            sub = desc(c, auto, 0, maxdepth, 120, [])
            lines.extend(sub)
            for s in sub:
                t = s.split("  ")[-1].split(" | ")[0]
                hist[t] = hist.get(t, 0) + 1
    lines.append("===== ControlType histogram =====")
    lines.extend("%s %d" % (k, v) for k, v in sorted(hist.items(), key=lambda x: -x[1]))
    out = out or os.path.join(OUT, "tree.txt")
    p = w(out, "\n".join(lines))
    note("wrote %s nodes=%d types=%d" % (p, len(lines) - len(hist) - 1, len(hist)))

def cmd_find(pattern, out=None):
    procs = ebx_procs()
    if not procs:
        note("no EBX process found"); return
    auto = uia()
    rx = re.compile(pattern, re.I)
    hits = []
    def walk(el, d=0):
        try:
            if rx.search(el.Name or "") or rx.search(el.AutomationId or "") or rx.search(el.ClassName or ""):
                r = el.BoundingRectangle
                hits.append("%s | N=%s | A=%s | C=%s | R=%d,%d %dx%d | hw=%d" % (
                    el.ControlTypeName, el.Name, el.AutomationId, el.ClassName,
                    r.left, r.top, r.width(), r.height(), el.NativeWindowHandle))
        except Exception:
            pass
        if d < 16:
            for k in el.GetChildren():
                walk(k, d + 1)
    for pid, name in procs:
        for c in top_windows(auto, pid):
            walk(c)
    out = out or os.path.join(OUT, "find.txt")
    p = w(out, "\n".join(hits))
    note("wrote %s hits=%d" % (p, len(hits)))

def cmd_shot(out):
    procs = ebx_procs()
    if not procs:
        note("no EBX process found"); return
    auto = uia()
    from PIL import ImageGrab
    boxes = []
    for pid, name in procs:
        for c in top_windows(auto, pid):
            r = c.BoundingRectangle
            if r.width() > 50 and r.height() > 50:
                boxes.append(((r.left, r.top, r.right, r.bottom), c.Name))
    if not boxes:
        note("no window box"); return
    img = ImageGrab.grab(bbox=boxes[0][0], all_screens=True)
    img.save(out)
    note("saved %s box=%s title=%s" % (out, boxes[0][0],
         str(boxes[0][1]).encode("ascii", "backslashreplace").decode("ascii")))

def cmd_status():
    lines = []
    try:
        lines.append("IsUserAnAdmin(shell) = %s" % ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        lines.append("IsUserAnAdmin err %s" % e)
    lines.append("dpi = %s" % dpi_aware())
    lines.append("procs = %r" % (ebx_procs(),))
    for d in INSTALL_CANDIDATES:
        if os.path.isdir(d):
            lines.append("INSTALL DIR FOUND: " + d)
            for root, dirs, files in os.walk(d):
                depth = root[len(d):].count(os.sep)
                if depth > 1:
                    dirs[:] = []
                    continue
                lines.append("  %s\\  %s" % (os.path.basename(root), sorted(dirs)))
                lines.append("    files(%d): %s" % (len(files), ", ".join(sorted(files)[:40])))
    # registry uninstall entries
    try:
        import winreg
        for hive, path in ((wt.HKEY_LOCAL_MACHINE if False else winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                           (winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                           (winreg.HKEY_CURRENT_USER,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
            try:
                k = winreg.OpenKey(hive, path)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    sk = winreg.OpenKey(k, sub)
                    disp = winreg.QueryValueEx(sk, "DisplayName")[0]
                    inst = ""
                    try:
                        inst = winreg.QueryValueEx(sk, "InstallLocation")[0]
                    except OSError:
                        pass
                    ver = ""
                    try:
                        ver = winreg.QueryValueEx(sk, "DisplayVersion")[0]
                    except OSError:
                        pass
                    if any(t in str(disp).lower() for t in ("easybuilder", "weintek", "weinview", "ebx")):
                        lines.append("UNINSTALL: %s | %s | %s | key=%s" % (disp, ver, inst, sub))
                except OSError:
                    continue
    except Exception as e:
        lines.append("registry probe err: %s" % e)
    p = w(os.path.join(OUT, "status.txt"), "\n".join(lines))
    note("wrote %s lines=%d" % (p, len(lines)))

def main():
    d = dpi_aware()
    note("dpi=%s admin=%s" % (d, ctypes.windll.shell32.IsUserAnAdmin()))
    a = sys.argv[1:] if len(sys.argv) > 1 else ["status"]
    cmd = a[0]
    if cmd == "wins":
        cmd_wins()
    elif cmd == "mods":
        cmd_mods()
    elif cmd == "tree":
        cmd_tree(int(a[1]) if len(a) > 1 else 14, a[2] if len(a) > 2 else None)
    elif cmd == "find":
        cmd_find(a[1] if len(a) > 1 else ".", a[2] if len(a) > 2 else None)
    elif cmd == "shot":
        cmd_shot(a[1] if len(a) > 1 else os.path.join(OUT, "shot.png"))
    elif cmd == "status":
        cmd_status()
    else:
        note("unknown subcommand: " + cmd)
        note("use: wins | mods | tree | find | shot | status")

if __name__ == "__main__":
    main()
