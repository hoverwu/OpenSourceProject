#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ebx_act.py - EasyBuilder X UIA driver (activate / screenshot / click / keys / find)
author: hoverwu  version: 0.1.0  date: 2026-11-06
EBX runs asInvoker (Medium IL) => no elevated shell needed (unlike Sysmac).

Subcommands:
  shot <out.png>                 activate main window, grab its rect
  click_name <regex>             Invoke/Click first visible control whose Name matches
  click_xy <x> <y>               raw mouse click at physical coords (window must be front)
  keys <keys...>                 SendKeys to EBX main window (activate first)
  find <regex> [out.txt]         dump matches (type/name/class/rect) across ALL EBX HWNDs
  tree [maxDepth] [out.txt]      full UIA dump incl. popup HWNDs
"""
import sys, os, re, time, ctypes, ctypes.wintypes as wt
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

def dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def note(m):
    sys.stdout.write(str(m).encode("ascii", "backslashreplace").decode("ascii").rstrip() + "\n")
    sys.stdout.flush()

import uiautomation as auto
auto.SetGlobalSearchTimeout(6)
u = ctypes.windll.user32

def ebx_main():
    root = auto.GetRootControl()
    for c in root.GetChildren():
        try:
            if c.ClassName == "Qt5QWindowIcon" and "EasyBuilder" in (c.Name or "") and not c.IsOffscreen:
                return c
        except Exception:
            pass
    return None

def activate(w):
    h = wt.HWND(w.NativeWindowHandle)
    u.ShowWindow(h, 5)
    if not u.SetForegroundWindow(h):
        # break foreground lock: press Alt once (Sysmac-tested trick)
        VK_MENU, KEYEVENTF_EXTENDEDKEY, KEYUP = 0x12, 0x0001, 0x0002
        u.keybd_event(VK_MENU, 0x45, KEYEVENTF_EXTENDEDKEY, 0)
        u.keybd_event(VK_MENU, 0x45, KEYEVENTF_EXTENDEDKEY | KEYUP, 0)
        time.sleep(0.05)
        u.SetForegroundWindow(h)
    time.sleep(0.6)
    return pv(h) == pv(u.GetForegroundWindow())

def pv(x):
    return ctypes.cast(x, ctypes.c_void_p).value or 0

def all_hwnds():
    """every visible top-level window of EBX pid via Win32 EnumWindows (UIA root children
    miss native #32770 dialogs; ControlFromHandle is the reliable bridge)."""
    m = ebx_main()
    pid = m.ProcessId if m else None
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        p = wt.DWORD(0)
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if pid is None or p.value == pid:
            if u.IsWindowVisible(h):
                found.append(h)
        return True
    u.EnumWindows(EnumProc(cb), 0)
    res = []
    for h in found:
        try:
            el = auto.ControlFromHandle(h)
            if el is not None:
                res.append(el)
        except Exception:
            pass
    return res

def walk(el, rx, hits, d=0):
    try:
        nm = el.Name or ""
        cls = el.ClassName or ""
        aid = el.AutomationId or ""
        if rx.search(nm) or rx.search(cls) or rx.search(aid):
            r = el.BoundingRectangle
            hits.append("%s | N=%.40s | A=%.20s | C=%.25s | R=%d,%d %dx%d | off=%s" % (
                el.ControlTypeName, nm, aid, cls, r.left, r.top, r.width(), r.height(), el.IsOffscreen))
    except Exception:
        pass
    if d < 16:
        try:
            for k in el.GetChildren():
                walk(k, rx, hits, d + 1)
        except Exception:
            pass

def cmd_shot(out):
    m = ebx_main()
    if m is None:
        note("EBX main window not found"); return
    fg = activate(m)
    r = m.BoundingRectangle
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
    img.save(out)
    note("saved %s rect=%d,%d %dx%d fg=%s" % (out, r.left, r.top, r.width(), r.height(), fg))

def cmd_click_name(pattern):
    rx = re.compile(pattern)
    hits = []
    for w in all_hwnds():
        walk(w, rx, hits)
    # find control object again and click
    target = None
    def find(el, d=0):
        nonlocal target
        if target:
            return
        try:
            if rx.search(el.Name or "") and not el.IsOffscreen:
                target = el
                return
        except Exception:
            pass
        if d < 16:
            for k in el.GetChildren():
                find(k, d + 1)
    for w in all_hwnds():
        find(w)
    if target is None:
        note("no match for /%s/; name-hits:\n%s" % (pattern, "\n".join(hits[:40]))); return
    m = ebx_main()
    if m:
        activate(m)
    try:
        target.Click(simulateMove=False)
        note("clicked %s N=%s" % (target.ControlTypeName,
             (target.Name or "").encode("ascii", "backslashreplace").decode("ascii")))
    except Exception as e:
        # fallback: physical coords
        r = target.BoundingRectangle
        x, y = r.left + r.width() // 2, r.top + r.height() // 2
        u.SetCursorPos(x, y)
        u.mouse_event(0x02, 0, 0, 0, 0); u.mouse_event(0x04, 0, 0, 0, 0)
        note("fallback coord-click at %d,%d err=%s" % (x, y, repr(e)[:60]))

def cmd_click_xy(x, y):
    m = ebx_main()
    if m:
        activate(m)
    u.SetCursorPos(int(x), int(y))
    u.mouse_event(0x02, 0, 0, 0, 0); time.sleep(0.05); u.mouse_event(0x04, 0, 0, 0, 0)
    note("clicked %s,%s" % (x, y))

def cmd_keys(args):
    m = ebx_main()
    if m is None:
        note("no EBX"); return
    activate(m)
    auto.SendKeys("{%s}" % "}{".join(args) if len(args) > 1 else args[0], waitTime=0.2)
    note("sent: %s" % args)

def cmd_tree(maxd, out):
    lines = []
    for w in all_hwnds():
        def dump(el, d=0):
            try:
                r = el.BoundingRectangle
                rect = "%d,%d %dx%d" % (r.left, r.top, r.width(), r.height())
            except Exception:
                rect = "?"
            lines.append("%s%s | N=%.50s | A=%.20s | C=%.25s | R=%s | off=%s" % (
                "  " * d, el.ControlTypeName, el.Name or "", el.AutomationId or "",
                el.ClassName or "", rect, el.IsOffscreen))
            if d < maxd:
                try:
                    for k in el.GetChildren():
                        dump(k, d + 1)
                except Exception:
                    pass
        dump(w)
    out = out or os.path.join(OUT, "tree.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    note("wrote %s lines=%d" % (out, len(lines)))

def main():
    dpi()
    a = sys.argv[1:]
    if not a:
        note(__doc__); return
    c = a[0]
    if c == "shot":
        cmd_shot(a[1] if len(a) > 1 else os.path.join(OUT, "act.png"))
    elif c == "click_name":
        cmd_click_name(a[1])
    elif c == "click_xy":
        cmd_click_xy(a[1], a[2])
    elif c == "keys":
        cmd_keys(a[1:])
    elif c == "tree":
        cmd_tree(int(a[1]) if len(a) > 1 else 12, a[2] if len(a) > 2 else None)
    elif c == "find":
        rx = re.compile(a[1])
        hits = []
        for w in all_hwnds():
            walk(w, rx, hits)
        out = a[2] if len(a) > 2 else os.path.join(OUT, "find.txt")
        open(out, "w", encoding="utf-8").write("\n".join(hits))
        note("wrote %s hits=%d" % (out, len(hits)))
    else:
        note("unknown cmd " + c)

if __name__ == "__main__":
    main()
