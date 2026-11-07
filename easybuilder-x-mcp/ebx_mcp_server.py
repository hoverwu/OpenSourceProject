#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ebx_mcp_server.py - EasyBuilder X 专用 MCP 服务器（UIA + 坐标地图）
author: hoverwu  version: 0.2.0  date: 2026-11-07

定位：不是通用 uiautomation-mcp 的换皮，而是把 EBX 实测出来的
      「Ribbon 坐标地图 + 面板 UIA 语义 + 原生对话框 AutomationId」
      固化成可直接调用的领域工具。

启动：python ebx_mcp_server.py 8788
      （依赖 uiautomation / fastmcp；EBX 全系 asInvoker / Medium IL，普通权限即可，无需 UAC）
      用环境变量 EBX_EXE 指定安装在非默认位置的 EasyBuilderX.exe

边界：画布内容 UIA 不可见 -> 元件放置/选中靠坐标；Ribbon 对 UIA 完全不可见 -> 只能坐标点击。

------------------------------------------------------------------------------
UIA 树模型（V1.01.376s / Qt5 + QtitanRibbon，2026-11-07 实测）
------------------------------------------------------------------------------
Root
├─ Qt5QWindowIcon  "<工程>.ebxprj - EasyBuilder X - V1.01.376s"   主窗
│  ├─ 自绘 Ribbon 壳：UIA 里几乎取不到页签/图标 -> 只能坐标（RIBON 地图）
│  ├─ 检视 dock：TabItemControl「画面 / 窗口」+ 左区 TreeControl 列表
│  │      [0] 画面树   TreeItemControl 行 x=26 w=222 h=28，首行 y≈240；
│  │          Name=画面名；顺序=画面创建顺序（=导航下拉顺序）
│  │      [1] 元件列表 TreeItemControl 行 x=26 w=208 h=28，起点约 (0,420)；
│  │          **元件 dock 没有 TabControl**（CustomControl + TreeControl），
│  │          按页签找会永远为空，必须取左区第二棵 TreeControl
│  ├─ 画布：0 个 UIA 节点，元件完全不可见；只有状态栏 TextControl 给
│  │      "(x, y) (x2, y2) W x H"，画布 (0,0) 的屏幕坐标实测 (245, 309)
│  ├─ 属性 dock：嵌套 depth >18（标签/输入框都在 16 层以下），遍历给 30 层；
│  │      行 = TextControl 标签(x≈1298) + EditControl/ComboBoxControl(x≈1365)，
│  │      部分行必须滚动才实例化；任务行、标签组等是自绘，读不到文字。
│  │      同名 CustomControl 与 EditControl 叠在同一矩形 -> 按控件引用取值
│  ├─ 文档页签栏：**自绘，不可枚举**（TabItemControl 恒为空）；
│  │      判断当前画面只能读属性面板「名称」行（_prop_value）
│  └─ WindowControl：**部分**模态对话框（任务设置）是主窗子树里的子窗口
├─ Qt5QWindowIcon（Name 常为空）：**另一些**模态对话框（含「是否保存工程?」）
├─ Qt5QWindowPopupDropShadowSaveBits：下拉弹层 / 右键菜单（独立顶层，渲染后才出现）
└─ #32770：原生 Win32 文件对话框（保存 / 打开）

六条铁律
1. 对话框有**三种**宿主形态（主窗内子 WindowControl / 独立无标题 Qt5QWindowIcon /
   顶层 #32770），找对话框必须都搜；并跳过 1×1 的 Qt5QWindowToolSaveBits* 隐层。
2. 弹层与菜单不在主窗子树里，且是**异步绘制**：点完最多轮询 1.5 s 再判断。
3. **不要把主窗设成 HWND_TOPMOST**：之后弹出的对话框/弹层/菜单会生成在它下面——
   UIA 照样枚举得到，但屏幕上"消失"、点击打在主窗上。提权用 SetForegroundWindow，
   对弹窗单独 SetWindowPos(HWND_TOP|SWP_NOACTIVATE)。
4. 组合框弹层要先**原生激活**对话框（点标题栏 (L+W/2, T+15)），列表才真正渲染；
   否则 TreeItem 点击、方向键、SelectionItemPattern 全部无效。
5. 任务行/元件列表/按钮标签组是自绘：点「确定」≠ 落盘，必须重开对话框读
   「画面」ComboBox 的 ValuePattern 才能判定成功。
6. 删除被导航任务引用的画面会换内部 ID，旧任务失效；操作前先备份 .ebxprj。
"""
import os
import re
import sys
import json
import time
import glob
import ctypes
import ctypes.wintypes as wt
import subprocess


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import uiautomation as auto
auto.SetGlobalSearchTimeout(6)
u = ctypes.windll.user32

from fastmcp import FastMCP

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "out")
WORK = os.path.join(BASE, "work")
STATE_PATH = os.path.join(OUT, "mcp_state.json")
os.makedirs(OUT, exist_ok=True)

# EBX 安装路径：优先环境变量 EBX_EXE，其次常见默认位置（%ProgramFiles% / %ProgramFiles(x86)%）
_PF = os.environ.get("ProgramFiles", r"C:\Program Files")
_PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
EBX_EXE = (os.environ.get("EBX_EXE") or "").strip()
EBX_EXE_CANDIDATES = ([EBX_EXE] if EBX_EXE else []) + [
    os.path.join(d, "EasyBuilderX.exe")
    for d in (
        os.path.join(_PF, "EasyBuilderX"),
        os.path.join(_PF86, "EasyBuilderX"),
        os.path.join(_PF, "EasyBuilder X"),
        os.path.join(_PF86, "EasyBuilder X"),
    )
]

mcp = FastMCP("easybuilder-x")


# ----------------------------------------------------------------- 基础工具
def _ensure_uia_thread():
    try:
        auto.InitializeUIAutomationInCurrentThread()
    except Exception:
        pass


def _state_load():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _state_save(d):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _note_state(**kw):
    st = _state_load()
    st.update(kw)
    _state_save(st)


def _main_window():
    try:
        for c in auto.GetRootControl().GetChildren():
            try:
                if (c.ClassName == "Qt5QWindowIcon"
                        and "EasyBuilder" in (c.Name or "")
                        and not c.IsOffscreen):
                    return c
            except Exception:
                continue
    except Exception:
        pass
    return None


def _active_window():
    """当前前台顶层窗口（可能是 EBX 的弹窗）。"""
    try:
        h = u.GetForegroundWindow()
        return auto.ControlFromHandle(h)
    except Exception:
        return None


def _rect(el):
    try:
        r = el.BoundingRectangle
        return [int(r.left), int(r.top), int(r.width()), int(r.height())]
    except Exception:
        return None


def _title():
    w = _main_window()
    return (w.Name or "") if w else ""


def _project_name():
    t = _title()
    if ".ebxprj" in t:
        return t.split(" - ")[0]
    return ""


def _demote_topmost(h):
    """把主窗从 TOPMOST 降回普通层。实测：主窗一旦 topmost，EBX 后续弹出的对话框 /
    组合框弹层 / 右键菜单全部生成在它下面（UIA 可见、屏幕不可见、点击落空）。"""
    try:
        u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u.SetWindowPos.restype = wt.BOOL
        u.SetWindowPos(h, wt.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002)   # NOTOPMOST|NOSIZE|NOMOVE
    except Exception:
        pass


def _to_front(el, settle=0.35):
    """把某个弹窗顶到最前（不改主窗层级）。用于对话框/弹层。"""
    try:
        h = wt.HWND(el.NativeWindowHandle)
        u.SetWindowPos(h, wt.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # TOP|NOACTIVATE
        u.SetForegroundWindow(h)
        time.sleep(settle)
    except Exception:
        pass


def _force_foreground(h):
    """前台锁解法：AttachThreadInput 借用前台线程的输入队列，再 BringWindowToTop/SetForegroundWindow。
    只靠 SetForegroundWindow 在用户正操作别的窗口时会被系统拒绝（本机实测）。"""
    try:
        fg = u.GetForegroundWindow()
        tid_fg = u.GetWindowThreadProcessId(fg, None) if fg else 0
        tid_me = ctypes.windll.kernel32.GetCurrentThreadId()
        attached = False
        if fg and tid_fg and tid_fg != tid_me:
            u.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
            attached = bool(u.AttachThreadInput(tid_me, tid_fg, True))
        try:
            u.BringWindowToTop(h)
            u.SetForegroundWindow(h)
            u.SetFocus(h)
        finally:
            if attached:
                u.AttachThreadInput(tid_me, tid_fg, False)
    except Exception:
        pass


def _activate(w=None, settle=0.45):
    w = w or _main_window()
    if w is None:
        return False
    h = wt.HWND(w.NativeWindowHandle)
    _demote_topmost(h)
    u.ShowWindow(h, 9 if u.IsIconic(h) else 5)   # SW_RESTORE / SW_SHOW
    if _hwnd_value(u.GetForegroundWindow()) != _hwnd_value(h):
        _force_foreground(h)
        time.sleep(0.15)
    if _hwnd_value(u.GetForegroundWindow()) != _hwnd_value(h):
        # 最后手段：最小化再还原，触发 Z 序重排
        u.ShowWindow(h, 6)
        time.sleep(0.2)
        u.ShowWindow(h, 9)
        time.sleep(0.15)
    if _hwnd_value(u.GetForegroundWindow()) != _hwnd_value(h):
        # 前台锁仍在：先敲一次 Alt 再置前（实测有效）
        VK_MENU, EXT, UP = 0x12, 0x0001, 0x0002
        u.keybd_event(VK_MENU, 0x45, EXT, 0)
        u.keybd_event(VK_MENU, 0x45, EXT | UP, 0)
        time.sleep(0.06)
        u.SetForegroundWindow(h)
    time.sleep(settle)
    return _hwnd_value(h) == _hwnd_value(u.GetForegroundWindow())


def _hwnd_value(h):
    return ctypes.cast(h, ctypes.c_void_p).value or 0


def _ebx_pid():
    w = _main_window()
    return w.ProcessId if w else None


def _visible_toplevels(pid):
    """Win32 EnumWindows 枚举某 pid 全部可见顶层窗口（#32770 对话框不在 UIA 主窗子树里）。"""
    found = []
    if pid is None:
        return found
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _l):
        p = wt.DWORD(0)
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
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


def _all_windows():
    pid = _ebx_pid()
    return _visible_toplevels(pid)


def _desc(el, depth=0):
    return {
        "type": el.ControlTypeName,
        "name": el.Name or "",
        "automation_id": el.AutomationId or "",
        "class": el.ClassName or "",
        "rect": _rect(el),
        "offscreen": bool(el.IsOffscreen),
        "hwnd": int(el.NativeWindowHandle or 0),
        "depth": depth,
    }


def _walk(el, depth, max_depth, out, limit, rx=None):
    if len(out) >= limit:
        return
    try:
        d = _desc(el, depth)
    except Exception:
        return
    if rx is None or rx.search(d["name"]) or rx.search(d["automation_id"]) or rx.search(d["class"]):
        out.append(d)
    if depth >= max_depth:
        return
    try:
        kids = el.GetChildren()
    except Exception:
        kids = []
    for k in kids:
        if len(out) >= limit:
            return
        _walk(k, depth + 1, max_depth, out, limit, rx)


def _find_elements(rx, max_results=120):
    hits = []
    for w in _all_windows():
        _walk(w, 0, 18, hits, max_results, rx)
        if len(hits) >= max_results:
            break
    return hits


def _first_element_by_name(rx):
    def rec(el, depth):
        if depth > 18:
            return None
        try:
            if rx.search(el.Name or "") and not el.IsOffscreen:
                return el
        except Exception:
            pass
        try:
            kids = el.GetChildren()
        except Exception:
            kids = []
        for k in kids:
            got = rec(k, depth + 1)
            if got is not None:
                return got
        return None

    for w in _all_windows():
        got = rec(w, 0)
        if got is not None:
            return got
    return None


# ----------------------------------------------------------------- UIA 树辅助（画面树 / 元件列表 / 对话框 / 弹层）
def _iter(el, max_depth=30, max_nodes=20000):
    """深度优先遍历一个窗口的全部后代（含自身）。"""
    out, stack = [], [(el, 0)]
    while stack and len(out) < max_nodes:
        cur, d = stack.pop()
        out.append(cur)
        if d >= max_depth:
            continue
        try:
            kids = list(cur.GetChildren())
        except Exception:
            kids = []
        for k in reversed(kids):
            stack.append((k, d + 1))
    return out


def _popups(pid=None):
    """Qt 弹层 / 右键菜单：独立顶层，类名含 PopupDropShadow，异步渲染。"""
    pid = pid if pid is not None else _ebx_pid()
    res = []
    try:
        for c in auto.GetRootControl().GetChildren():
            try:
                if "PopupDropShadow" in (c.ClassName or "") and (pid is None or c.ProcessId == pid):
                    res.append(c)
            except Exception:
                pass
    except Exception:
        pass
    return res


def _left_trees(w):
    """左停靠区的全部 TreeControl（画面树、元件列表、变量树…），按 y 从上到下。"""
    trees = []
    wr = _rect(w)
    for el in _iter(w, 14):
        try:
            if el.ControlTypeName != "TreeControl":
                continue
            r = _rect(el)
            if not r or r[0] > wr[0] + 340 or r[2] < 100:
                continue
            trees.append((r, el))
        except Exception:
            pass
    trees.sort(key=lambda t: t[0][1])
    return trees


def _rows_of_tree(tree, max_rows=40):
    rows = []
    for el in _iter(tree, 4, 2000):
        try:
            if el is tree or el.ControlTypeName != "TreeItemControl":
                continue
            r = _rect(el)
            if r and 15 <= r[3] <= 40 and r[2] >= 40:
                rows.append({"name": (el.Name or "").strip(),
                             "x": r[0], "y": r[1], "w": r[2], "h": r[3]})
        except Exception:
            pass
    rows.sort(key=lambda r: r["y"])
    return rows[:max_rows]


def _left_panel_rows(w, tab_name="画面", max_rows=40):
    """画面树 = 左区第一个 TreeControl；元件列表 = 左区最后一个（且必须存在第二个）。
    注意：元件 dock 没有 TabControl（实测为 CustomControl + TreeControl），不能按页签找。"""
    trees = _left_trees(w or _main_window())
    if not trees:
        return []
    if tab_name == "画面":
        return _rows_of_tree(trees[0][1], max_rows)
    if len(trees) < 2:
        return []
    # 画面树下方紧接的就是元件 dock（再往下是变量/标签树），固定取第二棵
    return _rows_of_tree(trees[1][1], max_rows)


def _prop_value(w, label):
    """读属性面板某一行（如「名称」）右侧输入控件的值。画面打开后可用于确认当前画面。

    实测要点（v0.2.0）：
      - 属性面板嵌套很深（标签/输入框都在 depth >18），遍历必须给到 30 层，之前用 16 层读不到值；
      - 每行 = 左侧 TextControl 标签（x≈1298）+ 右侧 EditControl/ComboBoxControl（x≈1365）；
        同名 CustomControl 会叠在同一矩形上，按控件引用而不是按矩形比较才不会认错；
      - 值优先走 ValuePattern；ComboBoxControl 没有 Value 时退到 Selection 的第一个元素名。
    """
    w = w or _main_window()
    if w is None:
        return None
    wr = _rect(w)
    gate = (wr[0] + 600) if wr else 0
    lab = None
    for el in _iter(w, 30):
        try:
            if el.ControlTypeName == "TextControl" and (el.Name or "").strip() == label:
                r = _rect(el)
                if r and r[0] > gate:
                    lab = r
                    break
        except Exception:
            pass
    if lab is None:
        return None
    lab_cy = lab[1] + lab[3] / 2.0
    cands = []
    for el in _iter(w, 30):
        try:
            if el.ControlTypeName not in ("EditControl", "ComboBoxControl"):
                continue
            r = _rect(el)
            if not r or r[0] < lab[0]:
                continue
            if abs((r[1] + r[3] / 2.0) - lab_cy) > 18:
                continue
            cands.append((r[0] * 10000 + r[2], el))
        except Exception:
            pass
    for _, el in sorted(cands, key=lambda t: t[0]):
        try:
            v = el.GetValuePattern().Value
            if v is not None:
                return v.strip()
        except Exception:
            pass
        try:
            sel = el.GetSelectionPattern().GetCurrentSelection()
            if sel:
                return (sel[0].Name or "").strip()
        except Exception:
            pass
        try:
            n = (el.Name or "").strip()
            if n:
                return n
        except Exception:
            pass
    return None


def _find_dialog(w=None):
    """找模态对话框：① 主窗子树里的 WindowControl；② 独立无标题顶层 Qt5QWindowIcon。"""
    w = w or _main_window()
    if w is None:
        return None
    wr = _rect(w)
    for el in _iter(w, 8):
        try:
            if el is w or el.ControlTypeName != "WindowControl":
                continue
            r = _rect(el)
            if r and 280 < r[2] < 700 and 150 < r[3] < 460 and r[0] > wr[0] and r[1] > wr[1]:
                return el
        except Exception:
            pass
    for el in _visible_toplevels(w.ProcessId):
        try:
            if (el.Name or "") == (w.Name or ""):
                continue
            if el.ClassName != "Qt5QWindowIcon" or el.ControlTypeName != "WindowControl":
                continue
            r = _rect(el)
            if r and 280 < r[2] < 700 and 150 < r[3] < 460:
                return el
        except Exception:
            pass
    return None


def _uia_nodes(root, max_depth=8, limit=600):
    out = []

    def rec(el, d):
        if len(out) >= limit:
            return
        out.append(_desc(el, d))
        if d >= max_depth:
            return
        try:
            kids = el.GetChildren()
        except Exception:
            kids = []
        for k in kids:
            rec(k, d + 1)

    rec(root, 0)
    return out


def _click_element(el):
    try:
        try:
            enabled = el.IsEnabled
        except Exception:
            enabled = True
        if enabled is False:
            return "disabled"
        try:
            ip = el.GetInvokePattern()
            if ip is not None:
                ip.Invoke()
                return "invoke"
        except Exception:
            pass
        try:
            el.Click(simulateMove=False)
            return "click"
        except Exception:
            pass
        r = el.BoundingRectangle
        x = int(r.left + r.width() // 2)
        y = int(r.top + r.height() // 2)
        _raw_click(x, y)
        return "coord"
    except Exception as e:
        return "error: %r" % (e,)


def _raw_click(x, y):
    u.SetCursorPos(int(x), int(y))
    u.mouse_event(0x02, 0, 0, 0, 0)
    time.sleep(0.05)
    u.mouse_event(0x04, 0, 0, 0, 0)
    time.sleep(0.15)


def _click_rel(x, y):
    """窗口内坐标（截图坐标）-> 屏幕坐标。"""
    w = _main_window()
    if w is None:
        raise RuntimeError("EasyBuilder X 主窗口未找到")
    r = w.BoundingRectangle
    _raw_click(r.left + int(x), r.top + int(y))


# ----------------------------------------------------------------- SendInput 按键
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _fields_ = [("type", wt.DWORD), ("u", _U)]


KEYEVENTF_KEYUP = 0x0002
VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
      "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
      "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
      "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
      "delete": 0x2E, "backspace": 0x08, "up": 0x26, "down": 0x28, "left": 0x25,
      "right": 0x27, "home": 0x24, "end": 0x23}
for _ch in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[_ch] = ord(_ch.upper())


def _key(vk, up=False):
    inp = INPUT(type=1)
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = u.MapVirtualKeyW(vk, 0)
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _send_combo(combo):
    combo = combo.lower().split("+")
    mods = [k for k in combo[:-1] if k in VK]
    mainkey = combo[-1]
    if mainkey not in VK:
        raise ValueError("unknown key: %s" % mainkey)
    for m in mods:
        _key(VK[m])
        time.sleep(0.03)
    _key(VK[mainkey])
    time.sleep(0.03)
    _key(VK[mainkey], True)
    for m in reversed(mods):
        _key(VK[m], True)
        time.sleep(0.03)


# ----------------------------------------------------------------- 剪贴板（中文路径兜底）
def _set_clipboard(text):
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    if not u.OpenClipboard(0):
        return False
    try:
        u.EmptyClipboard()
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, size)
        k32.GlobalUnlock(h)
        return bool(u.SetClipboardData(CF_UNICODETEXT, ctypes.c_void_p(h)))
    finally:
        u.CloseClipboard()


def _fill_filename(dlg, path):
    """保存/打开对话框：优先 ValuePattern 写全路径，失败退到剪贴板粘贴。"""
    candidates = []
    for maker in (
        lambda: dlg.EditControl(AutomationId="1001"),
        lambda: dlg.ComboBoxControl(AutomationId="1148").EditControl(),
        lambda: dlg.ComboBoxControl(AutomationId="FileNameControlHost").EditControl(),
    ):
        try:
            el = maker()
            if el is not None and el.Exists(0.6, 0):
                candidates.append(el)
        except Exception:
            pass
    if not candidates:
        return "no-filename-edit"
    ed = candidates[0]
    try:
        ed.GetValuePattern().SetValue(path)
        return "value-pattern"
    except Exception:
        pass
    try:
        ed.SetFocus()
        time.sleep(0.15)
        ed.Click(simulateMove=False)
        time.sleep(0.15)
        _send_combo("ctrl+a")
        time.sleep(0.05)
        _send_combo("delete")
        _set_clipboard(path)
        time.sleep(0.1)
        _send_combo("ctrl+v")
        return "clipboard-paste"
    except Exception as e:
        return "failed: %r" % (e,)


def _dialog_buttons(dlg):
    names = []
    def rec(el, depth=0):
        if depth > 6:
            return
        try:
            if el.ControlTypeName == "ButtonControl":
                names.append({"name": el.Name or "", "aid": el.AutomationId or ""})
        except Exception:
            pass
        try:
            for k in el.GetChildren():
                rec(k, depth + 1)
        except Exception:
            pass
    rec(dlg)
    return names


def _find_visible_dialog(pid=None, exclude_hwnd=0, only_caption=None):
    """找 EBX 的模态框。注意：文件对话框是原生 #32770，但 EBX 自己的消息框
    （如「是否要保存该工程文件?」）是 Qt5QWindowIcon 无 AutomationId 的窗口，
    所以两类都要认；1x1 的 Qt5QWindowToolSaveBits* 是工具提示，排除。"""
    pid = pid or _ebx_pid()
    main = _main_window()
    main_hwnd = int(main.NativeWindowHandle or 0) if main is not None else 0
    for w in _visible_toplevels(pid):
        try:
            h = int(w.NativeWindowHandle or 0)
            if h == int(exclude_hwnd or 0) or h == main_hwnd:
                continue
            cls = w.ClassName or ""
            r = _rect(w)
            if not r or r[2] < 120 or r[3] < 80 or r[2] > 1200 or r[3] > 900:
                continue
            if cls == "#32770":
                pass
            elif cls.startswith("Qt5QWindow") and "Tool" not in cls:
                pass
            else:
                continue
            if only_caption and only_caption not in (w.Name or ""):
                continue
            return w
        except Exception:
            continue
    return None


def _dialog_has_edit(d):
    for e in _iter(d, 10, 800):
        try:
            if e.ControlTypeName == "EditControl":
                return True
        except Exception:
            pass
    return False


def _wait_file_dialog(timeout=5.0):
    """等"打开/保存"文件对话框（有文件名编辑框的那一个），跳过前面的消息框。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = _find_visible_dialog()
        if d is not None and _dialog_has_edit(d):
            return d
        time.sleep(0.15)
    return None


def _click_button(dlg, names, nth=0):
    """按按钮名点。EBX 的 Qt 消息框按钮名带助记符，如 '否(N) Alt+N'，所以用前缀匹配。"""
    hits = []
    for e in _iter(dlg, 10, 800):
        try:
            if e.ControlTypeName != "ButtonControl":
                continue
            nm = (e.Name or "").strip()
            if nm in names or any(nm.startswith(n) for n in names):
                hits.append(e)
        except Exception:
            pass
    if len(hits) <= nth:
        return None
    _click_element(hits[nth])
    return (hits[nth].Name or "").strip()


def _dialog_text(dlg, limit=12):
    texts = []
    def rec(el, depth=0):
        if depth > 8 or len(texts) >= limit:
            return
        try:
            if el.ControlTypeName in ("TextControl", "EditControl") and (el.Name or "").strip():
                texts.append(el.Name.strip())
        except Exception:
            pass
        try:
            for k in el.GetChildren():
                rec(k, depth + 1)
        except Exception:
            pass
    rec(dlg)
    return texts


def _wait_dialog(timeout=4.0, exclude_hwnd=0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = _find_visible_dialog(exclude_hwnd=exclude_hwnd)
        if d is not None:
            return d
        time.sleep(0.15)
    return None


def _proc_list(keywords=None):
    TH32CS_SNAPPROCESS = 0x2
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentPID", wt.DWORD),
                    ("th32Priority", wt.LONG), ("th32ClassID", wt.DWORD),
                    ("szExeFile", wt.CHAR * 260)]
    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    out = []
    k32 = ctypes.windll.kernel32
    try:
        if k32.Process32First(snap, ctypes.byref(pe)):
            while True:
                name = pe.szExeFile.decode("mbcs", "ignore")
                if keywords is None or any(k.lower() in name.lower() for k in keywords):
                    out.append({"pid": int(pe.th32ProcessID), "name": name})
                if not k32.Process32Next(snap, ctypes.byref(pe)):
                    break
    finally:
        k32.CloseHandle(snap)
    return out


def _listening_ports(pids):
    res = []
    try:
        p = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                           encoding="mbcs", errors="ignore", timeout=10)
        for line in (p.stdout or "").splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper().startswith("TCP") and "LISTEN" in line.upper():
                try:
                    pid = int(parts[-1])
                except Exception:
                    continue
                if pid in pids:
                    res.append({"addr": parts[1], "pid": pid})
    except Exception:
        pass
    return res


def _related_processes():
    return _proc_list(["EasyBuilderX", "cMTRemote", "com-x", "dserver-x", "cMTInspector", "诊断"])


# ----------------------------------------------------------------- Ribbon 坐标地图
RIBON = {
    "tabs": {
        "文件": [33, 51], "常用": [97, 51], "工程文件": [163, 51], "元件": [230, 51],
        "资料/历史": [298, 51], "IIoT": [363, 51], "检视": [417, 51], "工具": [465, 51],
        "一般属性": [565, 51], "事件": [615, 51],
    },
    "工程文件": {
        "编译": [33, 100], "在线模拟": [98, 100], "离线模拟": [167, 100],
        "下载PC>HMI": [240, 100], "工程设置": [328, 100], "系统元件": [392, 100],
        "设备列表": [455, 100], "服务器列表": [522, 100], "UAC": [590, 100],
        "语言": [658, 100], "图片": [727, 100], "字符串": [787, 100],
        "数据类型": [852, 100], "变量": [913, 100], "JS resource": [972, 100],
        "宏指令": [1036, 100], "条件": [1093, 100],
    },
    "元件": {
        "指示灯": [143, 100], "开关": [193, 100], "按钮": [240, 100],
        "项目选单": [286, 100], "滑动开关": [338, 100],
        "数值": [428, 100], "文本": [475, 100],
        "日期/时间": [545, 100], "持续时间": [605, 100],
        "棒图": [665, 100], "嵌入窗口": [720, 100], "2D条码": [775, 100],
        "PDF检视器": [825, 100], "自定义": [880, 100],
    },
    "文件后台": {
        "新建": [42, 99], "打开": [42, 153], "保存": [42, 205], "另存为": [42, 253],
        "关闭": [42, 303], "反编译": [42, 355], "语言": [42, 408],
        "偏好设置": [42, 460], "关于": [42, 511], "退出": [525, 572],
    },
}


# ================================================================= MCP 工具
@mcp.tool()
def ebx_ribbon_map() -> dict:
    """返回 EasyBuilder X 的 Ribbon / 文件后台坐标地图（窗口内坐标，y 为页签行/按钮行）。
    注意：坐标随窗口位置、DPI、Ribbon 折叠状态变化，使用前建议先 ebx_screenshot 复核。"""
    return {
        "coordinate_space": "window-relative（截图坐标；屏幕坐标 = 坐标 + 窗口原点）",
        "map": RIBON,
        "notes": [
            "Ribbon 对 UIA 完全不可见，只能坐标点击",
            "页签行 y=51；按钮行 y=100",
            "选中元件后会多出 一般属性/事件 上下文页签",
        ],
    }


@mcp.tool()
def ebx_status() -> dict:
    """EBX 运行状态：主窗口是否存在、标题/工程名/矩形/是否前台，相关进程与监听端口。"""
    _ensure_uia_thread()
    w = _main_window()
    procs = _related_processes()
    pids = {p["pid"] for p in procs}
    data = {
        "running": w is not None,
        "title": _title(),
        "project": _project_name(),
        "main_rect": _rect(w) if w else None,
        "is_foreground": (_hwnd_value(wt.HWND(w.NativeWindowHandle)) == _hwnd_value(u.GetForegroundWindow())) if w else False,
        "processes": procs,
        "listening_ports": _listening_ports(pids),
        "admin": bool(ctypes.windll.shell32.IsUserAnAdmin()),
    }
    st = _state_load()
    data["last_project_dir"] = os.path.dirname(st["last_project"]) if st.get("last_project") else None
    return data


@mcp.tool()
def ebx_launch(wait_seconds: int = 30) -> dict:
    """启动 EasyBuilder X（普通权限）。已运行则直接返回窗口信息。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is not None:
        return {"started": False, "reason": "already running", "title": w.Name, "rect": _rect(w)}
    exe = next((p for p in EBX_EXE_CANDIDATES if os.path.isfile(p)), None)
    if exe is None:
        return {"started": False,
                "error": "EasyBuilderX.exe 未找到：请设置环境变量 EBX_EXE 指向可执行文件",
                "checked": EBX_EXE_CANDIDATES}
    subprocess.Popen([exe], cwd=os.path.dirname(exe))
    t0 = time.time()
    while time.time() - t0 < wait_seconds:
        w = _main_window()
        if w is not None:
            return {"started": True, "elapsed": round(time.time() - t0, 1),
                    "title": w.Name, "rect": _rect(w), "pid": w.ProcessId}
        time.sleep(0.4)
    return {"started": False, "error": "启动超时（%ds）" % wait_seconds}


@mcp.tool()
def ebx_windows(include_related: bool = False) -> list:
    """列出 EBX 进程全部可见顶层窗口（含 #32770 对话框、独立弹窗）。
    include_related=True 时连模拟器（cMTRemote/com-x/dserver-x/诊断器）的窗口一起列出。"""
    _ensure_uia_thread()
    out = []
    for w in _all_windows():
        out.append(_desc(w))
    if include_related:
        for p in _related_processes():
            if p["name"].lower() == "easybuilderx.exe":
                continue
            for w in _visible_toplevels(p["pid"]):
                d = _desc(w)
                d["process"] = p["name"]
                out.append(d)
    return out


@mcp.tool()
def ebx_tree(max_depth: int = 8, max_lines: int = 600) -> str:
    """导出 EBX 全部顶层窗口的 UIA 树（文本）。对话框不在主窗子树里，本工具已跨窗口枚举。"""
    _ensure_uia_thread()
    lines = []
    for w in _all_windows():
        def dump(el, d=0):
            if len(lines) >= max_lines:
                return
            r = _rect(el)
            lines.append("%s%s | N=%s | A=%s | C=%s | R=%s | off=%s" % (
                "  " * d, el.ControlTypeName, (el.Name or "")[:50], el.AutomationId or "",
                el.ClassName or "", r, bool(el.IsOffscreen)))
            if d < max_depth:
                try:
                    for k in el.GetChildren():
                        dump(k, d + 1)
                except Exception:
                    pass
        dump(w)
    if len(lines) >= max_lines:
        lines.append("... [truncated at %d lines, raise max_lines if needed]" % max_lines)
    return "\n".join(lines)


@mcp.tool()
def ebx_find(pattern: str, max_results: int = 100) -> list:
    """按正则搜索 Name / AutomationId / ClassName（大小写不敏感），返回类型/名称/矩形/是否离屏。"""
    _ensure_uia_thread()
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        return [{"error": "bad regex: %s" % e}]
    return _find_elements(rx, max_results)


@mcp.tool()
def ebx_screen_list() -> dict:
    """列出画面树（左侧检视面板）里的全部画面及行坐标，并给出当前打开的画面。
    返回的 y 是该行在屏幕上的纵坐标，双击行可打开；顺序即导航下拉与创建顺序。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is None:
        return {"running": False, "screens": [], "current_screen": None}
    rows = _left_panel_rows(w, "画面")
    return {
        "running": True,
        "title": w.Name,
        "screens": rows,
        "screen_names": [r["name"] for r in rows],
        "current_screen": _prop_value(w, "名称"),
        "note": "启动页=最先创建的画面；画面树不支持拖动排序；文档页签是自绘，UIA 读不到，当前画面看 current_screen",
    }


@mcp.tool()
def ebx_screen_open(name: str) -> dict:
    """双击画面树里的某个画面，把它打开到编辑器（已打开则只切页签）。不修改内容。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is None:
        return {"ok": False, "error": "EasyBuilder X 未运行/工程未打开"}
    _activate(w)
    rows = _left_panel_rows(w, "画面")
    row = next((r for r in rows if r["name"] == name), None)
    if row is None:
        return {"ok": False, "error": "画面不存在", "screens": [r["name"] for r in rows]}
    x, y = row["x"] + 50, row["y"] + row["h"] // 2
    for attempt in range(2):
        u.SetCursorPos(x, y)
        time.sleep(0.1)
        for _ in range(2):
            u.mouse_event(0x0002, 0, 0, 0, 0)
            u.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.06)
        time.sleep(0.9)
        cur = _prop_value(w, "名称")
        if cur == name:
            return {"ok": True, "opened": name, "attempt": attempt}
    return {"ok": False, "opened": _prop_value(w, "名称"), "target": name,
            "hint": "双击后属性面板「名称」未变成目标；确认画面未被模态框挡住"}


@mcp.tool()
def ebx_screen_elements() -> list:
    """列出当前画面「元件」面板里的元件行（名称 + 行坐标）。画布本身 0 个 UIA 节点，
    这是唯一可读的元件入口；元件 dock 没有 TabControl，按左区最后一个 TreeControl 识别。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is None:
        return [{"error": "EasyBuilder X 未运行"}]
    return _left_panel_rows(w, "元件")


@mcp.tool()
def ebx_uia_dump(scope: str = "all", max_depth: int = 8, max_lines: int = 600) -> dict:
    """按窗口分组导出结构化 UIA 树，专门用于看清对话框/弹层挂在哪。
    scope: main（主窗）| dialogs（模态对话框）| popups（下拉弹层/右键菜单）| all。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is None:
        return {"running": False, "windows": []}
    groups = []
    pid = w.ProcessId
    if scope in ("all", "main"):
        groups.append({"kind": "main", "window": _desc(w),
                       "nodes": _uia_nodes(w, max_depth, max_lines)})
    if scope in ("all", "dialogs"):
        dlg = _find_dialog(w)
        if dlg is not None:
            groups.append({"kind": "dialog", "window": _desc(dlg),
                           "nodes": _uia_nodes(dlg, max_depth, max_lines)})
        for el in _visible_toplevels(pid):
            try:
                if el.ClassName == "Qt5QWindowIcon" and (el.Name or "") != (w.Name or ""):
                    if groups and groups[-1].get("window", {}).get("hwnd") == int(el.NativeWindowHandle or 0):
                        continue
                    groups.append({"kind": "dialog-top", "window": _desc(el),
                                   "nodes": _uia_nodes(el, max_depth, max_lines)})
            except Exception:
                pass
    if scope in ("all", "popups"):
        for p in _popups(pid):
            groups.append({"kind": "popup", "window": _desc(p),
                           "nodes": _uia_nodes(p, max_depth, max_lines)})
    return {"running": True, "scope": scope, "windows": groups,
            "note": "popup 只在展开期间存在；dialog 可能是主窗内 WindowControl 或无标题顶层"}


_PID_OPENPROCESS_SET = False


def _pid_alive(pid):
    global _PID_OPENPROCESS_SET
    try:
        if not _PID_OPENPROCESS_SET:
            u.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
            u.OpenProcess.restype = wt.HANDLE
            u.CloseHandle.argtypes = [wt.HANDLE]
            _PID_OPENPROCESS_SET = True
        h = u.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            u.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


@mcp.tool()
def ebx_import_screen_json(json_path: str, screen: str = "", force: bool = False,
                           no_bind: bool = False, no_nav: bool = False,
                           limit: int = 0, no_save: bool = False, wait: int = 0) -> dict:
    """用 tools/ebx_screen_importer.py 把 ebx-screen/1.0 JSON 重建进当前工程（后台进程）。
    导入期间会独占鼠标键盘：不要动电脑、不要切走 EBX，任何模态框都会让它卡住。
    wait=0 立即返回（用 ebx_import_status 查进度）；wait>0 最多等这么多秒。
    建议先 limit=8 试跑。"""
    _ensure_uia_thread()
    if not os.path.isfile(json_path):
        return {"ok": False, "error": "json 不存在: %s" % json_path}
    try:
        data = json.load(open(json_path, encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": "json 解析失败: %r" % (e,)}
    schema = data.get("schema")
    w = _main_window()
    if w is None:
        return {"ok": False, "error": "EasyBuilder X 未运行/工程未打开"}
    importer = os.path.join(BASE, "tools", "ebx_screen_importer.py")
    if not os.path.isfile(importer):
        return {"ok": False, "error": "缺少导入器 tools/ebx_screen_importer.py"}
    target = screen or (data.get("screen", {}) or {}).get("name", "")
    elements = (data.get("screen", {}) or {}).get("elements", [])
    cmd = [sys.executable, importer, json_path]
    if screen:
        cmd += ["--screen", screen]
    if force:
        cmd.append("--force")
    if no_bind:
        cmd.append("--no-bind")
    if no_nav:
        cmd.append("--no-nav")
    if limit:
        cmd += ["--limit", str(limit)]
    if no_save:
        cmd.append("--no-save")
    log_path = os.path.join(OUT, time.strftime("import_%Y%m%d_%H%M%S.log"))
    try:
        fh = open(log_path, "wb")
        p = subprocess.Popen(cmd, cwd=BASE, stdout=fh, stderr=subprocess.STDOUT)
        fh.close()
    except Exception as e:
        return {"ok": False, "error": "启动导入器失败: %r" % (e,)}
    _note_state(import_pid=p.pid, import_log=log_path, import_screen=target,
                import_total=len(elements))
    info = {"ok": True, "pid": p.pid, "screen": target, "elements": len(elements),
            "schema": schema, "log": log_path,
            "note": "导入期间不要动键鼠；每元件约 30~60 s"}
    if wait and wait > 0:
        try:
            p.wait(timeout=wait)
        except Exception:
            pass
        info.update(ebx_import_status())
    return info


@mcp.tool()
def ebx_import_status() -> dict:
    """最近一次 JSON 导入的进度：读 out/import_*.log 尾部，统计 [done]/[bind]/[task] 与结束标志。"""
    st = _state_load()
    log_path = st.get("import_log")
    if not log_path or not os.path.isfile(log_path):
        logs = sorted(glob.glob(os.path.join(OUT, "import_*.log")))
        log_path = logs[-1] if logs else None
    if not log_path:
        return {"found": False, "note": "还没有导入记录"}
    raw = open(log_path, "rb").read()[-8000:]
    text = raw.decode("utf-8", "replace")
    if text.count("\ufffd") > 20:
        text = raw.decode("gbk", "replace")
    lines = [l for l in text.splitlines() if l.strip()]
    pid = st.get("import_pid")
    return {
        "found": True,
        "log": log_path,
        "pid": pid,
        "running": bool(pid) and _pid_alive(pid),
        "target": st.get("import_screen"),
        "done": sum(1 for l in lines if l.startswith("[done]")),
        "total": st.get("import_total"),
        "binds_ok": sum(1 for l in lines if l.startswith("[bind]") and l.rstrip().endswith("ok")),
        "tasks_ok": sum(1 for l in lines if l.startswith("[task]") and l.rstrip().endswith("ok")),
        "finished": any(l.startswith("[ok] 已重建") for l in lines),
        "errors": [l for l in lines if l.startswith("[ERR]") or "[warn]" in l][-5:],
        "tail": lines[-12:],
    }


@mcp.tool()
def ebx_click_name(pattern: str) -> dict:
    """点击 Name 匹配正则的第一个可见控件（优先 Invoke，失败退坐标点击）。用于面板、对话框、欢迎页。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    rx = re.compile(pattern, re.I)
    el = _first_element_by_name(rx)
    if el is None:
        return {"ok": False, "error": "未找到匹配控件", "pattern": pattern,
                "hint": "Ribbon/画布内容不可见，请改用 ebx_click_xy 或 ebx_ribbon"}
    how = _click_element(el)
    return {"ok": how in ("invoke", "click", "coord"), "how": how,
            "element": _desc(el), "pattern": pattern}


@mcp.tool()
def ebx_click_xy(x: int, y: int, relative: bool = True) -> dict:
    """鼠标点击。relative=True 时 x,y 为窗口内坐标（截图坐标）；False 为屏幕坐标。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    if relative:
        _click_rel(x, y)
        w = _main_window()
        r = w.BoundingRectangle
        return {"ok": True, "clicked": [x, y], "screen": [r.left + x, r.top + y], "relative": True}
    _raw_click(x, y)
    return {"ok": True, "clicked": [x, y], "relative": False}


@mcp.tool()
def ebx_ribbon(tab: str, item: str = "") -> dict:
    """坐标点击 Ribbon 页签 / 页签内按钮，或文件后台项。
    例：ebx_ribbon("工程文件", "编译")、ebx_ribbon("元件", "数值")、ebx_ribbon("文件后台", "另存为")。
    纯坐标通道，Ribbon 对 UIA 不可见；失败先 ebx_screenshot 复核布局。"""
    _ensure_uia_thread()
    if tab not in RIBON["tabs"] and tab not in RIBON:
        return {"ok": False, "error": "未知页签", "valid": list(RIBON["tabs"]) + ["文件后台"]}
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    # 关掉可能残留的后台页，避免坐标落在遮罩上
    _send_combo("esc")
    time.sleep(0.25)
    if tab == "文件后台":
        if not item or item not in RIBON["文件后台"]:
            return {"ok": False, "error": "文件后台需要 item", "valid": list(RIBON["文件后台"])}
        _click_rel(33, 51)
        time.sleep(0.6)
        x, y = RIBON["文件后台"][item]
        _click_rel(x, y)
        return {"ok": True, "clicked": ["文件后台", item], "coords": [x, y]}
    t = RIBON["tabs"].get(tab)
    if t is None:
        if tab not in RIBON:
            return {"ok": False, "error": "未知页签"}
        item_map = RIBON[tab]
        if item not in item_map:
            return {"ok": False, "error": "未知按钮", "valid": list(item_map)}
        x, y = item_map[item]
        _click_rel(x, y)
        return {"ok": True, "clicked": [tab, item], "coords": [x, y]}
    _click_rel(t[0], t[1])
    time.sleep(0.45)
    if item:
        item_map = RIBON.get(tab, {})
        if item not in item_map:
            return {"ok": False, "error": "未知按钮", "tab": tab, "valid": list(item_map)}
        x, y = item_map[item]
        time.sleep(0.2)
        _click_rel(x, y)
        time.sleep(0.2)
        return {"ok": True, "clicked": [tab, item], "coords": [x, y]}
    return {"ok": True, "clicked": [tab], "coords": t}


@mcp.tool()
def ebx_screenshot(path: str = "") -> dict:
    """截取 EBX 主窗口（仅窗口区域），返回保存路径与窗口矩形供坐标换算。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is None:
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    fg = _activate(w, settle=0.35)
    r = w.BoundingRectangle
    path = path or os.path.join(OUT, "shot_%s.png" % time.strftime("%H%M%S"))
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
        img.save(path)
    except Exception as e:
        return {"ok": False, "error": repr(e)}
    return {"ok": True, "path": path, "rect": _rect(w), "foreground": fg,
            "note": "截图坐标即窗口内坐标；屏幕坐标 = 截图坐标 + rect 左上角"}


@mcp.tool()
def ebx_keys(combo: str) -> dict:
    """向 EBX 发送真实按键（SendInput），如 "ctrl+s"、"enter"、"esc"、"ctrl+shift+s"。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    try:
        _send_combo(combo)
    except Exception as e:
        return {"ok": False, "error": repr(e)}
    return {"ok": True, "sent": combo}


@mcp.tool()
def ebx_save_as(path: str) -> dict:
    """另存为 .ebxprj：走文件后台与原生 #32770 对话框，ValuePattern 写全路径后点保存，并校验产物。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    if not _project_name():
        return {"ok": False, "error": "当前没有已打开的工程（欢迎页），请先 ebx_new_project"}
    if not path.lower().endswith(".ebxprj"):
        path += ".ebxprj"
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    dlg = _find_visible_dialog()
    if dlg is not None and not _dialog_has_edit(dlg):
        return {"ok": False, "prompt": dlg.Name or "", "buttons": _dialog_buttons(dlg),
                "hint": "有消息框未处理（如未保存确认），先处理再另存为"}
    if dlg is None:
        _send_combo("esc")
        time.sleep(0.2)
        _click_rel(33, 51)     # 文件
        time.sleep(0.6)
        _click_rel(42, 253)    # 另存为
        dlg = _wait_file_dialog(4.0)
    if dlg is None:
        return {"ok": False, "error": "另存为对话框未出现", "hint": "先 ebx_screenshot 复核文件后台坐标"}
    how = _fill_filename(dlg, path)
    time.sleep(0.35)
    btn = None
    try:
        btn = dlg.ButtonControl(AutomationId="1")
    except Exception:
        pass
    clicked = "none"
    if btn is not None and btn.Exists(1.0, 0):
        btn.Click(simulateMove=False)
        clicked = "aid=1"
    else:
        b = _first_element_by_name(re.compile(r"^(保存|Save)$", re.I))
        if b is not None:
            _click_element(b)
            clicked = "name"
    time.sleep(1.5)

    # 覆盖确认（目标已存在时出现第二个 #32770）
    confirm = _find_visible_dialog(exclude_hwnd=dlg.NativeWindowHandle)
    confirmed = False
    if confirm is not None:
        b = _first_element_by_name(re.compile(r"^(是|Yes)$", re.I))
        if b is not None:
            _click_element(b)
            confirmed = True
            time.sleep(1.0)
    exists = os.path.isfile(path)
    size = os.path.getsize(path) if exists else 0
    if exists:
        _note_state(last_project=path)
    return {"ok": exists and size > 0, "path": path, "exists": exists, "size": size,
            "fill": how, "save_button": clicked, "overwrite_confirmed": confirmed,
            "dialog_buttons": _dialog_buttons(confirm) if confirm is not None else None}


@mcp.tool()
def ebx_open(path: str, discard_unsaved: bool = False) -> dict:
    """打开 .ebxprj/.ebxobj：文件后台 » 打开 » 原生对话框写路径并确认。
    当前工程有未保存修改时会弹「是否要保存该工程文件?」——默认**不替用户决定**并返回 ok:false；
    明确要丢弃时才传 discard_unsaved=true（等于点「否」）。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    if not os.path.isfile(path):
        return {"ok": False, "error": "文件不存在", "path": path}
    path = os.path.abspath(path)
    _send_combo("esc")
    time.sleep(0.2)
    # 0) 先处理已存在的模态框（典型：上一次打开留下的「是否要保存该工程文件?」）
    pre = _find_visible_dialog()
    if pre is not None:
        try:
            btns = _dialog_buttons(pre)
        except Exception:
            btns = []
        if discard_unsaved:
            try:
                _click_button(pre, ("否", "No"))
            except Exception:
                pass
            time.sleep(0.8)
            pre = _find_visible_dialog()
        if pre is not None:
            return {"ok": False, "path": path, "prompt": pre.Name or "",
                    "buttons": btns,
                    "hint": "有模态框未处理：先保存/取消，或用 discard_unsaved=true 丢弃未保存修改"}
    _click_rel(33, 51)   # 文件
    time.sleep(0.6)
    _click_rel(42, 153)  # 打开
    dlg = _wait_file_dialog(5.0)
    if dlg is None:
        return {"ok": False, "error": "打开对话框未出现",
                "dialog": _dialog_buttons(_find_visible_dialog())}
    how = _fill_filename(dlg, path)
    time.sleep(0.35)
    clicked = "none"
    for maker in (lambda: dlg.ButtonControl(AutomationId="1"),
                  lambda: _first_element_by_name(re.compile(r"^(打开|Open)$", re.I))):
        try:
            b = maker()
            if b is not None and (not hasattr(b, "Exists") or b.Exists(1.0, 0)):
                _click_element(b)
                clicked = "clicked"
                break
        except Exception:
            pass
    # 未保存确认框：是 / 否 / 取消
    time.sleep(0.8)
    prompt = _find_visible_dialog()
    if prompt is not None:
        btns = _dialog_buttons(prompt)
        if discard_unsaved:
            for e in _iter(prompt, 8):
                try:
                    nm = (e.Name or "").strip()
                    if e.ControlTypeName == "ButtonControl" and nm in ("否", "否(N)", "&No", "No"):
                        _click_element(e)
                        time.sleep(0.7)
                        prompt = _find_visible_dialog()
                        break
                except Exception:
                    pass
        if prompt is not None:
            return {"ok": False, "path": path, "fill": how, "button": clicked,
                    "prompt": prompt.Name or "", "buttons": btns,
                    "hint": "当前工程有未保存修改：先保存，或用 discard_unsaved=true 明确丢弃后再打开"}
    t0 = time.time()
    target = os.path.basename(path)
    while time.time() - t0 < 25:
        if target.split(".ebx")[0] in _title():
            break
        time.sleep(0.4)
    ok = target.split(".ebx")[0] in _title()
    if ok:
        _note_state(last_project=path)
    return {"ok": ok, "path": path, "fill": how, "button": clicked, "title": _title()}


@mcp.tool()
def ebx_new_project(wait_seconds: int = 15) -> dict:
    """新建工程。欢迎页直接点"创建"（默认机型卡）；已有工程时走 文件 » 新建（可能弹未保存确认）。"""
    _ensure_uia_thread()
    w = _main_window()
    if w is None:
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    _activate()
    dlg = _find_visible_dialog()
    if dlg is not None:
        return {"ok": False, "error": "有对话框未关闭", "dialog": dlg.Name,
                "buttons": _dialog_buttons(dlg)}
    if _project_name():
        _click_rel(33, 51)
        time.sleep(0.6)
        _click_rel(42, 99)  # 新建
    else:
        _click_rel(1645, 884)  # 欢迎页 "创建"（窗口内坐标，已实测）
    t0 = time.time()
    while time.time() - t0 < wait_seconds:
        if _project_name():
            return {"ok": True, "project": _project_name(), "title": _title(),
                    "rect": _rect(_main_window())}
        d = _find_visible_dialog()
        if d is not None:
            return {"ok": False, "prompt": d.Name, "buttons": _dialog_buttons(d),
                    "hint": "可能询问是否保存当前工程，请人工决定后用 ebx_click_name 点按钮"}
        time.sleep(0.4)
    return {"ok": False, "error": "新建超时", "title": _title()}


@mcp.tool()
def ebx_compile(project_dir: str = "", timeout: int = 120) -> dict:
    """编译工程：工程文件 » 编译，按 .ebxobj 更新时间 + 错误弹窗判定结果。
    project_dir 留空时用最近一次 ebx_save_as/ebx_open 记录的目录。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    if not _project_name():
        return {"ok": False, "error": "没有已打开工程"}
    dlg = _find_visible_dialog()
    if dlg is not None:
        return {"ok": False, "error": "有对话框未关闭", "dialog": dlg.Name,
                "buttons": _dialog_buttons(dlg)}
    st = _state_load()
    pdir = project_dir or (os.path.dirname(st["last_project"]) if st.get("last_project") else WORK)
    proj = os.path.join(pdir, _project_name())

    def snapshot():
        path = os.path.join(pdir, os.path.splitext(_project_name())[0] + ".ebxobj")
        try:
            return path, os.path.getmtime(path), os.path.getsize(path)
        except OSError:
            return path, 0.0, 0

    art, mt0, sz0 = snapshot()
    _send_combo("esc")
    time.sleep(0.2)
    _click_rel(163, 51)  # 工程文件
    time.sleep(0.5)
    _click_rel(33, 100)  # 编译
    t0 = time.time()
    last_mt, last_sz, stable = mt0, sz0, 0
    while time.time() - t0 < timeout:
        d = _find_visible_dialog()
        if d is not None:
            return {"ok": False, "error": "编译弹窗", "dialog": d.Name,
                    "text": _dialog_text(d), "buttons": _dialog_buttons(d),
                    "artifact": art, "elapsed": round(time.time() - t0, 1)}
        art, mt, sz = snapshot()
        if mt > mt0 + 0.001 and sz > 0:
            changed = True
            if sz == last_sz and mt == last_mt:
                stable += 1
            else:
                stable = 0
            last_mt, last_sz = mt, sz
            # 大文件编译会边写边变大：连续两次采样不变才算完成
            if stable >= 2:
                d = _find_visible_dialog()
                if d is not None:
                    return {"ok": False, "error": "编译弹窗", "dialog": d.Name,
                            "text": _dialog_text(d), "buttons": _dialog_buttons(d),
                            "artifact": art, "elapsed": round(time.time() - t0, 1)}
                return {"ok": True, "artifact": art, "size": sz, "size_before": sz0,
                        "elapsed": round(time.time() - t0, 1)}
        time.sleep(0.6)
    return {"ok": False, "error": "编译超时（无产物更新、无弹窗）", "artifact": art,
            "hint": "记录面板文本暂不可读；请 ebx_screenshot 人眼复核"}


@mcp.tool()
def ebx_offline_simulate(timeout: int = 45) -> dict:
    """离线模拟：工程文件 » 离线模拟，等待 cMTRemote 启动并回报进程/窗口/监听端口。
    首次可能弹 Windows 防火墙授权——不会代为放行。"""
    _ensure_uia_thread()
    if not _activate():
        return {"ok": False, "error": "EasyBuilder X 未运行"}
    if not _project_name():
        return {"ok": False, "error": "没有已打开工程（需先编译）"}
    dlg = _find_visible_dialog()
    if dlg is not None:
        return {"ok": False, "error": "有对话框未关闭", "dialog": dlg.Name}
    _send_combo("esc")
    time.sleep(0.2)
    _click_rel(163, 51)
    time.sleep(0.5)
    _click_rel(167, 100)
    t0 = time.time()
    while time.time() - t0 < timeout:
        procs = _related_processes()
        remote = [p for p in procs if p["name"].lower().startswith("cmtremote")]
        if remote:
            # 模拟器三段进程是级联启动的：等 com-x / dserver-x 也出现，再留 2s 给窗口与端口
            t1 = time.time()
            while time.time() - t1 < 12:
                names = [p["name"].lower() for p in _related_processes()]
                if any(n.startswith("com-x") for n in names) and \
                        any(n.startswith("dserver-x") for n in names):
                    break
                time.sleep(0.5)
            time.sleep(2.0)
            procs = _related_processes()
            pids = {p["pid"] for p in procs}
            windows = []
            for p in procs:
                for w in _visible_toplevels(p["pid"]):
                    windows.append({"pid": p["pid"], "process": p["name"], "name": w.Name,
                                    "class": w.ClassName, "rect": _rect(w)})
            return {"ok": True, "elapsed": round(time.time() - t0, 1),
                    "processes": procs, "windows": windows,
                    "listening_ports": _listening_ports(pids),
                    "firewall_note": "若出现 Windows 防火墙授权框，按用户策略不代点"}
        d = _find_visible_dialog()
        if d is not None:
            return {"ok": False, "error": "模拟弹窗", "dialog": d.Name,
                    "buttons": _dialog_buttons(d)}
        time.sleep(0.8)
    return {"ok": False, "error": "模拟启动超时", "processes": _related_processes()}


@mcp.tool()
def ebx_stop_simulation() -> dict:
    """结束离线模拟：优先 taskkill cMTRemote，随后检查 com-x/dserver-x 残留。"""
    subprocess.run(["taskkill", "/F", "/IM", "cMTRemote.exe"], capture_output=True)
    time.sleep(1.5)
    leftovers = [p for p in _related_processes() if p["name"].lower() in
                 ("com-x.exe", "dserver-x.exe", "cmtremote.exe")]
    return {"ok": not leftovers, "leftovers": leftovers}


@mcp.tool()
def ebx_artifacts(project_dir: str = "") -> dict:
    """列出工程目录里的 .ebxprj/.ebxobj（大小/时间），用于编译与保存结果核验。"""
    st = _state_load()
    pdir = project_dir or (os.path.dirname(st["last_project"]) if st.get("last_project") else WORK)
    items = []
    try:
        for name in sorted(os.listdir(pdir)):
            if name.lower().endswith((".ebxprj", ".ebxobj")):
                p = os.path.join(pdir, name)
                try:
                    s = os.stat(p)
                    items.append({"name": name, "size": s.st_size,
                                  "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s.st_mtime))})
                except OSError:
                    pass
    except OSError as e:
        return {"ok": False, "error": repr(e), "dir": pdir}
    return {"ok": True, "dir": pdir, "items": items}


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    sys.stdout.write("easybuilder-x MCP listening on http://127.0.0.1:%d/mcp\n" % port)
    sys.stdout.flush()
    mcp.run(transport="http", host="127.0.0.1", port=port, show_banner=False)


if __name__ == "__main__":
    main()
