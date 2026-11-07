#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ebx_screen_importer.py - 读取 ebx-screen/1.0 JSON，在 EasyBuilder X 里重建画面
（hoverwu / 0.1.0 / 2026-11-07）

前提：
  * Windows；EasyBuilder X V1.01.376s 已打开目标工程；
  * 主窗口最大化到 1920x1080 左右（画布缩放 100%），左侧/右侧面板保持默认布局；
  * 目标工程已有同名 PLC 设备与变量标签（不需要绑定时可加 --no-bind）；
  * Python 3.8+，pip install uiautomation。

用法：
  python ebx_screen_importer.py Alarm_Trend.screen.json
  python ebx_screen_importer.py Alarm_Trend.screen.json --screen 报警与趋势_导入
  python ebx_screen_importer.py Alarm_Trend.screen.json --limit 8 --no-bind --no-nav
  python ebx_screen_importer.py Alarm_Trend.screen.json --force   # 目标画面已存在时仍然新建（同名会自动加后缀）

说明：EBX 没有画面级 JSON 导入，这个脚本用 UIA 驱动界面重建，等价于人工拖放+绑变量。
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import sys
import time

import uiautomation as auto

auto.SetGlobalSearchTimeout(4)

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_uint]
u.SetWindowPos.restype = wt.BOOL

# ---- 与 EBX 实测布局相关的常量（均相对窗口左上角） ----
# 参考环境：Windows 11 / 1920x1080 / 125% 缩放未启用（系统 100%）/ EBX 最大化
# 说明：QtitanRibbon 是自绘控件，UIA 拿不到选项卡和图标，只能按像素点。
#       换机器/换 DPI/换窗口尺寸后请先运行 `--probe-ribbon` 生成带刻度截图再校准。
RIBBON_TAB = (256, 58)      # “元件”选项卡（实测：选项卡文字中心 y≈58）
ICONS = {
    "文本": (97, 146),      # 绘图组第二行的“A”＝静态文本（不是 输入组的 ABC＝文本输入）
    "文本输入": (543, 90),
    "数值": (495, 90),
    "指示灯": (184, 90),
    "按钮": (286, 90),
}
TYPE_TO_KIND = {
    "static_text": "文本",
    "numeric_display": "数值",
    "indicator": "指示灯",
    "button": "按钮",
}
SCREEN_ORDER = ["报警与趋势", "主监控", "参数设定", "手动维护"]
SCREEN_NAMES = list(SCREEN_ORDER)   # 运行时用画面树实际顺序覆盖
LOG = []


def log(msg):
    LOG.append(msg)
    print(msg, flush=True)


def find_main():
    for c in auto.GetRootControl().GetChildren():
        try:
            if c.ClassName == "Qt5QWindowIcon" and "EasyBuilder X" in (c.Name or ""):
                return c
        except Exception:
            pass
    return None


def walk(root, maxn=4000, max_left=None, min_x=None):
    out, stack = [], [root]
    while stack and len(out) < maxn:
        e = stack.pop()
        out.append(e)
        try:
            r = e.BoundingRectangle
            if max_left is not None and int(r.left) > max_left:
                continue
            if min_x is not None and int(r.left + r.width()) < min_x:
                continue
            stack.extend(list(e.GetChildren()))
        except Exception:
            pass
    return out


def rect(e):
    r = e.BoundingRectangle
    return int(r.left), int(r.top), int(r.width()), int(r.height())


def popups(pid):
    out = []
    for c in auto.GetRootControl().GetChildren():
        try:
            if "PopupDropShadow" in (c.ClassName or "") and c.ProcessId == pid:
                out.append(c)
        except Exception:
            pass
    return out


def value_of(e):
    try:
        return e.GetValuePattern().Value
    except Exception:
        return None


def activate(win):
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.IsZoomed.argtypes = [wt.HWND]
    hwnd = wt.HWND(win.NativeWindowHandle)
    u.ShowWindow(hwnd, 3)   # 先试 SW_MAXIMIZE
    time.sleep(0.5)
    if not u.IsZoomed(hwnd):
        # 某些窗口 ShowWindow 无效，用双击标题栏切换最大化
        for _ in range(2):
            l, t, w, h = rect(win)
            u.SetCursorPos(l + w // 2, t + 18)
            time.sleep(0.2)
            for _i in range(2):
                u.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.05)
                u.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.12)
            time.sleep(1.3)
            if u.IsZoomed(hwnd):
                break
    # 注意：不要把主窗口设成 HWND_TOPMOST。实测设成 topmost 后，EBX 后续弹出的
    # 对话框 / combo 弹层 / 右键菜单全部生成在它下面，截图里"凭空消失"，点击也打不中。
    # 只用 SetForegroundWindow 把它提到最前即可。
    u.SetWindowPos(hwnd, wt.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002)   # HWND_NOTOPMOST
    try:
        u.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.6)
    l, t, w, h = rect(win)
    u.SetCursorPos(l + w // 2, t + 20)
    time.sleep(0.1)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.8)


def click(x, y, pause=0.35):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.10)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(pause)


def rclick(x, y, pause=0.9):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.10)
    u.mouse_event(0x0008, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(0x0010, 0, 0, 0, 0)
    time.sleep(pause)


def wheel(x, y, delta, times=1, pause=0.18):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.08)
    for _ in range(times):
        u.mouse_event(0x0800, 0, 0, int(delta), 0)
        time.sleep(pause)


def drag(x1, y1, x2, y2, pause=0.45):
    u.SetCursorPos(int(x1), int(y1))
    time.sleep(0.12)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.12)
    for i in range(1, 9):
        u.SetCursorPos(int(x1 + (x2 - x1) * i / 8), int(y1 + (y2 - y1) * i / 8))
        time.sleep(0.04)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(pause)


def keys(combo):
    table = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "enter": 0x0D, "esc": 0x1B,
             "down": 0x28, "up": 0x26, "tab": 0x09, "home": 0x24, "end": 0x23,
             "a": 0x41, "s": 0x53, "v": 0x56, "c": 0x43}
    mods = []
    for part in combo.split("+"):
        p = part.strip().lower()
        mods.append(table.get(p))
    # 按下
    for k in mods[:-1]:
        u.keybd_event(k, 0, 0, 0)
    u.keybd_event(mods[-1], 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(mods[-1], 0, 2, 0)
    for k in reversed(mods[:-1]):
        u.keybd_event(k, 0, 2, 0)
    time.sleep(0.15)


def copy_clipboard(text):
    """Win32 剪贴板写入 Unicode 文本（不依赖 tkinter / PowerShell）。"""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wt.HGLOBAL
    k32.GlobalLock.argtypes = [wt.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    k32.GlobalFree.argtypes = [wt.HGLOBAL]
    u.OpenClipboard.argtypes = [wt.HWND]
    u.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    u.SetClipboardData.restype = wt.HANDLE
    data = text.encode("utf-16-le") + b"\x00\x00"
    if not u.OpenClipboard(None):
        return False
    try:
        u.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        p = k32.GlobalLock(h)
        if not p:
            k32.GlobalFree(h)
            return False
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        if not u.SetClipboardData(CF_UNICODETEXT, h):
            k32.GlobalFree(h)
            return False
        return True
    finally:
        u.CloseClipboard()


def paste_text(text):
    """用剪贴板粘贴中文（SendKeys/按键码不稳）。"""
    if not copy_clipboard(text):
        log("[warn] 剪贴板写入失败")
    time.sleep(0.15)
    keys("ctrl+v")
    time.sleep(0.15)


# ---------------- 画布标定 ----------------
COORD_RE = re.compile(r"^\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)$")


def status_coord(win):
    l, t, w, h = rect(win)
    for e in walk(win, 4000, min_x=l + int(w * 0.5)):
        try:
            if e.ControlTypeName == "TextControl" and int(e.BoundingRectangle.top) > t + h - 60:
                m = COORD_RE.match((e.Name or "").strip())
                if m:
                    return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    return None


def calibrate(win):
    """用状态栏“(x, y)”反推画布原点。
    实测：单纯点击/SetCursorPos 不会刷新状态栏，必须在画布上拖一小段（选择框，安全）。"""
    l, t, w, h = rect(win)
    drags = [((l + int(w * 0.42), t + int(h * 0.45)),
              (l + int(w * 0.42) + 30, t + int(h * 0.45) + 24)),
             ((l + int(w * 0.50), t + int(h * 0.50)),
              (l + int(w * 0.50) + 36, t + int(h * 0.50) + 18))]
    vals = []
    for (x1, y1), (x2, y2) in drags:
        drag(x1, y1, x2, y2, 0.45)
        time.sleep(0.5)
        c = None
        for _ in range(3):
            c = status_coord(win)
            if c:
                break
            time.sleep(0.2)
        if c:
            vals.append((x2, y2, c))
            log("[calib] end=(%d,%d) canvas=(%d,%d)" % (x2, y2, c[0], c[1]))
    keys("esc")
    time.sleep(0.3)
    if not vals:
        log("[calib] 失败：读不到状态栏坐标")
        return None
    origin = (vals[0][0] - vals[0][2][0], vals[0][1] - vals[0][2][1])
    if len(vals) > 1:
        o2 = (vals[1][0] - vals[1][2][0], vals[1][1] - vals[1][2][1])
        log("[calib] origin1=%s origin2=%s" % (origin, o2))
        if abs(o2[0] - origin[0]) > 2 or abs(o2[1] - origin[1]) > 2:
            log("[calib] 警告：两次标定不一致，改用第二次")
            origin = o2
    # 合理性检查
    if not (l + 80 <= origin[0] <= l + 700 and t + 80 <= origin[1] <= t + 700):
        log("[calib] 失败：origin=%s 不合理（窗口 %s）" % (origin, (l, t, w, h)))
        return None
    log("[calib] origin=(%d,%d)" % origin)
    return origin


# ---------------- 画面树 ----------------
def screen_rows(win, max_left):
    """画面树的行：位于“元件”面板标题之上。元件列表的行在标题之下，必须排除。"""
    l0, t0, w0, h0 = rect(win)
    header_top = None
    for e in walk(win, 6000, max_left=max_left):
        try:
            if e.ControlTypeName == "TextControl" and (e.Name or "").strip() == "元件":
                x, y, w, h = rect(e)
                if x < max_left and t0 + 250 < y < t0 + 500:
                    header_top = y
                    break
        except Exception:
            pass
    limit = (header_top - 8) if header_top else (t0 + 370)
    rows = []
    for e in walk(win, 6000, max_left=max_left):
        try:
            if e.ControlTypeName == "TreeItemControl":
                l, t, w, h = rect(e)
                nm = (e.Name or "").strip()
                if nm and w > 80 and t > t0 + 180 and t < limit:
                    rows.append((nm, l, t, w, h))
        except Exception:
            pass
    rows.sort(key=lambda r: r[2])
    return rows


def menu_click(pid, pred, pause=0.8, wait=1.5):
    """点菜单项。菜单是异步绘制的，点完立刻扫常常扫不到，所以最多等 wait 秒。"""
    t0 = time.time()
    while True:
        for p in popups(pid):
            for e in walk(p, 300):
                try:
                    nm = (e.Name or "").strip()
                    if e.ControlTypeName == "MenuItemControl" and pred(nm):
                        l, t, w, h = rect(e)
                        if w > 10:
                            click(l + 40, t + h // 2, pause)
                            return nm
                except Exception:
                    pass
        if time.time() - t0 >= wait:
            return None
        time.sleep(0.15)


def open_screen(win, name, max_left):
    """右键画面树某行 → 开启编辑器（打开或激活该画面的文档）。"""
    keys("esc")   # 若该行正处于“重命名”内联编辑状态，先退出，否则右键只有编辑菜单
    time.sleep(0.2)
    rows = screen_rows(win, max_left)
    row = next((r for r in rows if r[0] == name), None)
    if row is None:
        return False
    rclick(row[1] + 60, row[2] + 6)
    return menu_click(win.ProcessId, lambda n: n == "开启编辑器", 1.8) is not None


def create_screen(win, name, max_left):
    rows = screen_rows(win, max_left)
    if not rows:
        return None, "看不到画面树"
    if name in [r[0] for r in rows]:
        return None, "画面已存在"
    anchor = rows[-1]
    rclick(anchor[1] + 60, anchor[2] + 6)
    menu_click(win.ProcessId, lambda n: n == "插入画面", 1.4)
    after = screen_rows(win, max_left)
    new = [r for r in after if r[0] not in [x[0] for x in rows]]
    if not new:
        return None, "插入画面后没有新行"
    row = new[0]
    if not open_screen(win, row[0], max_left):
        return None, "开启编辑器失败"
    # 改画面名
    scroll_props(win, "up", 12)
    if not set_field_by_label(win, "名称", name):
        return None, "画面改名失败（新画面名仍是 %s）" % row[0]
    log("[screen] 已新建画面: %s" % name)
    return name, None


# ---------------- 属性面板 ----------------
def panel_geom(win):
    l, t, w, h = rect(win)
    for e in walk(win, 5000, min_x=l + int(w * 0.5)):
        try:
            if e.ControlTypeName == "TextControl" and (e.Name or "").strip() == "元件类型":
                px, py, pw, ph = rect(e)
                return px, t, w - (px - l)
        except Exception:
            pass
    return None


def find_label(win, name, ymin=None, ymax=None):
    pg = panel_geom(win)
    if not pg:
        return None
    px = pg[0]
    for e in walk(win, 6000, min_x=px - 40):
        try:
            if e.ControlTypeName == "TextControl" and (e.Name or "").strip() == name:
                l, t, w, h = rect(e)
                if l < px - 40:
                    continue
                if ymin is not None and t < ymin:
                    continue
                if ymax is not None and t > ymax:
                    continue
                return (l, t, w, h)
        except Exception:
            pass
    return None


def row_field(win, label_rect, min_width=80):
    l, t, w, h = label_rect
    cand = None
    for e in walk(win, 6000, min_x=l + 20):
        try:
            if e.ControlTypeName not in ("EditControl", "ComboBoxControl"):
                continue
            x, y, ww, hh = rect(e)
            if x <= l + 10:
                continue
            if abs(y - t) > 18:
                continue
            if ww < min_width:
                continue
            if cand is None or x < cand[0]:
                cand = (x, y, ww, hh, e)
        except Exception:
            pass
    return cand


def set_field_by_label(win, label, text, pause=0.5):
    ensure_props_tab(win)
    lr = find_label(win, label)
    if not lr:
        return False
    f = row_field(win, lr)
    if not f:
        return False
    click(f[0] + min(40, f[2] // 2), f[1] + f[3] // 2, 0.2)
    keys("ctrl+a")
    paste_text(text)
    keys("enter")
    time.sleep(pause)
    return True


def scroll_props(win, direction, times):
    pg = panel_geom(win)
    if not pg:
        return
    cx = pg[0] + 150
    y = rect(win)[1] + 600
    wheel(cx, y, 240 if direction == "up" else -240, times, 0.15)
    time.sleep(0.4)


def ensure_props_tab(win):
    """属性面板可能在 事件/方法 页，先切回“属性”。"""
    l, t, w, h = rect(win)
    for e in walk(win, 6000, min_x=l + int(w * 0.5)):
        try:
            if e.ControlTypeName == "TabItemControl" and (e.Name or "").strip() == "属性":
                x, y, ww, hh = rect(e)
                if 180 < y < 280:
                    click(x + ww // 2, y + hh // 2, 0.45)
                    return True
        except Exception:
            pass
    return False


def pane_kind(win):
    ensure_props_tab(win)
    lr = find_label(win, "元件类型")
    if not lr:
        return ""
    f = row_field(win, lr, 60)
    if f is not None:
        try:
            v = value_of(f[4]) or (f[4].Name or "").strip()
            if v:
                return v
        except Exception:
            pass
    # 画面/元件类型 的值经常是静态文本（TextControl），不是输入框
    l, t, w, h = lr
    best = None
    for e in walk(win, 6000, min_x=l + 20):
        try:
            if e.ControlTypeName != "TextControl":
                continue
            x, y, ww, hh = rect(e)
            if abs(y - t) > 12 or x <= l + w - 10 or ww < 20:
                continue
            nm = (e.Name or "").strip()
            if nm and (best is None or x < best[0]):
                best = (x, nm)
        except Exception:
            pass
    return best[1] if best else ""


# ---------------- 放置与绑定 ----------------
def probe_ribbon(win):
    """保存带刻度的 Ribbon 截图，便于按本机实际布局校准 RIBBON_TAB / ICONS。"""
    try:
        from PIL import ImageDraw, ImageGrab
    except ImportError:
        log("[ERR] 需要 Pillow：pip install pillow")
        return
    activate(win)
    l, t, w, h = rect(win)
    img = ImageGrab.grab(bbox=(l, t, l + w, t + h), all_screens=True)
    crop = img.crop((0, 40, min(w, 1100), 240)).convert("RGB")
    d = ImageDraw.Draw(crop)
    for x in range(0, crop.width, 50):
        d.line([(x, 0), (x, crop.height)],
               fill=(255, 0, 0) if x % 100 == 0 else (150, 150, 255))
        if x % 100 == 0:
            d.text((x + 2, 2), str(x), fill=(200, 0, 0))
    for y in range(0, crop.height, 20):
        d.line([(0, y), (crop.width, y)], fill=(222, 222, 222))
        if y % 40 == 0:
            d.text((2, y + 1), str(y + 40), fill=(0, 120, 0))
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "out", "ribbon_grid.png")
    crop.save(out)
    log("[probe] 已保存 %s；按图上刻度修改 RIBBON_TAB / ICONS" % out)


def place(win, origin, kind, x, y, w, h):
    l, t, _, _ = rect(win)
    click(l + RIBBON_TAB[0], t + RIBBON_TAB[1], 0.5)
    ix, iy = ICONS[kind]
    click(l + ix, t + iy, 0.5)
    sx, sy = origin[0] + x, origin[1] + y
    drag(sx, sy, sx + w, sy + h)
    time.sleep(0.25)
    keys("esc")                                  # 退出放置模式
    time.sleep(0.15)
    click(sx + w // 2, sy + h // 2, 0.4)         # 选中新元件，右侧属性面板才显示它


def browser_popup(win):
    """变量浏览器弹层：宽 > 300，含 Project/[PLC_...] 下拉或 GlobalVariables 树。"""
    for p in popups(win.ProcessId):
        try:
            if rect(p)[2] < 300:
                continue
        except Exception:
            continue
        for e in walk(p, 400):
            try:
                if e.ControlTypeName == "ComboBoxControl":
                    v = (value_of(e) or "").strip()
                    if v == "Project" or v.startswith("[PLC"):
                        return p
                if e.ControlTypeName == "TreeItemControl" and (e.Name or "").strip() == "GlobalVariables":
                    return p
            except Exception:
                pass
    return None


def pick_device(win, b):
    """把浏览器顶部 Project 下拉切到 [PLC_xxx]（条目不是 UIA 对象，用 Down+Enter）。"""
    for e in walk(b, 600):
        try:
            if e.ControlTypeName != "ComboBoxControl":
                continue
            v = (value_of(e) or "").strip()
            if v.startswith("[PLC"):
                return True
            if v == "Project":
                l, t, w, h = rect(e)
                click(l + w - 12, t + h // 2, 1.0)
                keys("down")
                time.sleep(0.3)
                keys("enter")
                time.sleep(1.2)
                return True
        except Exception:
            pass
    return False


def row_picker(win, lr):
    """属性行右端的选择按钮（...）。"""
    l, t, w, h = lr
    best = None
    for e in walk(win, 6000, min_x=l + 60):
        try:
            x, y, ww, hh = rect(e)
            if abs(y - t) > 20 or x < l + w:
                continue
            if 16 <= ww <= 46 and 10 <= hh <= 36:
                if best is None or x + ww > best[0] + best[2]:
                    best = (x, y, ww, hh)
        except Exception:
            pass
    return best


def bind_tag(win, tag, kind, readonly):
    ensure_props_tab(win)
    scroll_props(win, "up", 4)
    label = "读取数值" if kind == "指示灯" or readonly else "数值"
    lr = find_label(win, label) or find_label(win, "数值")
    if not lr:
        return "no_field"
    b = None
    pb = row_picker(win, lr)          # 优先点行尾“...”按钮
    if pb:
        click(pb[0] + pb[2] // 2, pb[1] + pb[3] // 2, 0.7)
        time.sleep(0.7)
        b = browser_popup(win)
    if b is None:                     # 回退：点字段本身
        f = row_field(win, lr, 60)
        if f:
            click(f[0] + 8, f[1] + f[3] // 2, 0.7)
            time.sleep(0.9)
            b = browser_popup(win)
            if b is None:                 # 再回退：点字段右缘
                click(f[0] + f[2] + 20, f[1] + f[3] // 2, 0.7)
                time.sleep(0.9)
                b = browser_popup(win)
    if b is None:
        return "no_browser"
    if not pick_device(win, b):
        return "device_fail"
    b = browser_popup(win) or b
    # 展开 GlobalVariables
    grp = None
    for e in walk(b, 500):
        try:
            if e.ControlTypeName == "TreeItemControl" and (e.Name or "").strip() == "GlobalVariables":
                grp = e
        except Exception:
            pass
    if grp is not None:
        pat = None
        try:
            pat = grp.GetExpandCollapsePattern()
        except Exception:
            pat = None
        done = False
        if pat is not None:
            try:
                if pat.ExpandCollapseState != auto.ExpandCollapseState.Expanded:
                    pat.Expand()
                    time.sleep(0.6)
                done = True
            except Exception:
                done = False
        if not done:   # Qt 自绘树通常没有 ExpandCollapsePattern，只能点箭头
            gx, gy, gw, gh = rect(grp)
            click(gx - 16, gy + gh // 2, 0.9)
    # 找标签
    tree = None
    for e in walk(b, 400):
        if e.ControlTypeName == "TreeControl":
            tree = e
            break

    def search():
        for e in walk(b, 1400):
            try:
                if e.ControlTypeName == "TreeItemControl" and (e.Name or "").strip() == tag:
                    return e
            except Exception:
                pass
        return None

    hit = search()
    if hit is None:
        # 树控件本身不暴露给 UIA 时，用 GlobalVariables 行和弹层底边推算滚动点
        if tree is not None:
            tx, ty, tw, th = rect(tree)
            cx, cy = tx + tw // 2, ty + th // 2
        elif grp is not None:
            gx, gy, gw, gh = rect(grp)
            pl, pt, pw, ph = rect(b)
            cx, cy = gx + gw // 2, min(pt + ph - 60, gy + gh + 160)
        else:
            cx = cy = None
    if hit is None and cx is not None:
        for _ in range(16):
            wheel(cx, cy, 120, 1, 0.2)
            hit = search()
            if hit is not None:
                break
        if hit is None:
            for _ in range(26):
                wheel(cx, cy, -120, 1, 0.2)
                hit = search()
                if hit is not None:
                    break
    if hit is None:
        keys("esc")
        return "tag_not_found"
    hx, hy, hw, hh = rect(hit)
    click(hx + 80, hy + hh // 2, 0.25)
    click(hx + 80, hy + hh // 2, 0.9)
    for e in walk(b, 500):            # 双击后弹层可能已关闭
        try:
            if e.ControlTypeName == "ButtonControl" and "确定" in (e.Name or ""):
                bx, by, bw, bh = rect(e)
                click(bx + bw // 2, by + bh // 2, 0.7)
                return "ok"
        except Exception:
            pass
    return "ok"


def to_front(e):
    """把弹窗顶到最前。

    关键：activate() 把 EBX 主窗口设成了 HWND_TOPMOST，之后 EBX 弹出的对话框
    （任务/切换画面等）只会出现在主窗口**下面**，截图里看不到、鼠标点击也全被主窗口
    吃掉——表现为“对话框凭空消失 / combo 点不开”。所以拿到对话框后必须把它也设为
    TOPMOST。实测：不设时 WindowFromPoint 命中的是主窗口；设了以后 combo 弹层正常。
    """
    try:
        hwnd = wt.HWND(e.NativeWindowHandle)
        u.SetWindowPos(hwnd, wt.HWND(-1), 0, 0, 0, 0,
                       0x0001 | 0x0002 | 0x0010)   # NOSIZE|NOMOVE|NOACTIVATE
        u.SetForegroundWindow(hwnd)
        time.sleep(0.5)
    except Exception:
        pass


def find_dialog(win):
    """找“任务/切换画面”对话框。

    实测 V1.01.376s：对话框有两种形态——双点已存在的任务项时是主窗口内的子
    WindowControl；点“新增...”时是独立的顶层 Qt5QWindowIcon（Name 为空）。
    两种都要覆盖，尺寸约 358x267。
    """
    for e in walk(win, 8000):
        try:
            if e.ControlTypeName == "WindowControl" and e is not win:
                l, t, w, h = rect(e)
                if 280 < w < 700 and 150 < h < 460 and l > 0 and t > 0:
                    return e
        except Exception:
            pass
    # 兜底：老版本/某些布局下 dialog 是独立顶层窗口
    for c in auto.GetRootControl().GetChildren():
        try:
            if c.ProcessId == win.ProcessId and c.ClassName == "Qt5QWindowIcon" and c.Name != win.Name:
                l, t, w, h = rect(c)
                if 280 < w < 700 and 150 < h < 460:
                    return c
        except Exception:
            pass
    return None


def add_switch_task(win, target):
    ensure_props_tab(win)
    scroll_props(win, "up", 8)
    lr = find_label(win, "任务")
    if not lr:
        return "no_task_row"
    # 任务行右侧的“＋ 新增...”链接（自绘，UIA 拿不到，按行内相对位置点）
    btn = None
    for e in walk(win, 6000, min_x=lr[0]):
        try:
            if e.ControlTypeName in ("ButtonControl", "TextControl") and "新增" in (e.Name or ""):
                x, y, w, h = rect(e)
                if abs(y - lr[1]) < 40:
                    btn = (x, y, w, h)
                    break
        except Exception:
            pass
    if btn is not None:
        click(btn[0] + btn[2] // 2, btn[1] + btn[3] // 2, 0.8)
        opened = menu_click(win.ProcessId, lambda n: n.strip() == "切换画面", 1.0) is not None
    else:
        opened = False
    if not opened:
        # “＋ 新增...”是自绘链接，按点击位置逐个试（行内右对齐，文字中心约 +190）
        for dx in (190, 232, 150):
            click(lr[0] + dx, lr[1] + 27, 0.7)
            if menu_click(win.ProcessId, lambda n: n.strip() == "切换画面", 1.0):
                opened = True
                break
    if not opened:
        return "no_menu_item"
    time.sleep(0.5)
    dlg = None
    for _ in range(4):
        dlg = find_dialog(win)
        if dlg is not None:
            break
        time.sleep(0.5)
    if dlg is None:
        return "no_dialog"
    to_front(dlg)   # 主窗口曾是 TOPMOST，不顶上去对话框会被盖住
    # 点一下标题栏让对话框真正拿到焦点：不激活时 combo 弹层只出现在 UIA 里、屏幕上看不见，
    # 点弹层项也不生效。实测“点标题栏 → 点箭头 → 点项”稳定。
    L, T, W, H = rect(dlg)
    click(L + W // 2, T + 15, 0.5)

    def get_combos():
        cs = []
        for e in walk(dlg, 600):
            try:
                if e.ControlTypeName == "ComboBoxControl":
                    cs.append(e)
            except Exception:
                pass
        cs.sort(key=lambda e: rect(e)[1])
        return cs

    combos = get_combos()
    if not combos:
        return "no_screen_combo"
    if len(combos) < 2:
        # 类型 combo 记住了上次的选择（如“返回上一个画面”），先切回“切换画面”
        tc = combos[0]
        tx, ty, tw, th = rect(tc)
        click(tx + tw - 10, ty + th // 2, 0.4)
        time.sleep(0.4)
        hit = None
        for e in walk(dlg, 900):
            try:
                nm = (e.Name or "").strip()
                if e.ControlTypeName in ("ListItemControl", "TreeItemControl") and nm == "切换画面":
                    ix, iy, iw, ih = rect(e)
                    if iy >= ty:
                        hit = (ix, iy, iw, ih)
                        break
            except Exception:
                pass
        if hit is None:
            keys("esc")
            return "no_type_switch"
        click(hit[0] + 60, hit[1] + hit[3] // 2, 0.6)
        time.sleep(0.4)
        combos = get_combos()
        if len(combos) < 2:
            return "no_screen_combo"
    sc = combos[-1]

    # 弹层用键盘选：实测直接点弹层里的 TreeItem 会把整个对话框一起关掉，
    # 任务并不落盘，所以只用 上/下 + Enter（Enter 只提交弹层，对话框仍在）。
    ok = False
    for attempt in range(4):
        sx, sy, sw, sh = rect(sc)
        click(sx + sw - 10, sy + sh // 2, 0.4)
        time.sleep(0.5 + 0.25 * attempt)
        if (value_of(sc) or "").strip() == target:
            keys("esc")
            time.sleep(0.2)
            ok = True
            break
        names = []
        for e in walk(dlg, 900):
            try:
                nm = (e.Name or "").strip()
                if e.ControlTypeName == "TreeItemControl" and nm:
                    ix, iy, iw, ih = rect(e)
                    if ix >= sx - 10 and iy >= sy + sh:
                        names.append(nm)
            except Exception:
                pass
        if not names:
            continue   # 对话框还在淡入/还没响应，再来一次
        if target not in names:
            keys("esc")
            time.sleep(0.2)
            return "target_not_found"
        # 先直接点弹层里的目标项
        hit = None
        for e in walk(dlg, 900):
            try:
                nm = (e.Name or "").strip()
                if e.ControlTypeName == "TreeItemControl" and nm == target:
                    ix, iy, iw, ih = rect(e)
                    if ix >= sx - 10 and iy >= sy + sh:
                        hit = (ix, iy, iw, ih)
                        break
            except Exception:
                pass
        if hit is not None:
            click(hit[0] + 80, hit[1] + hit[3] // 2, 0.5)
        time.sleep(0.2)
        if (value_of(sc) or "").strip() == target:
            ok = True
            break
        # 兜底：键盘（弹层没关时 Down/Enter 只提交弹层，对话框仍在）
        cur = (value_of(sc) or "").strip()
        order = names
        if cur not in order:
            cur = order[0]
        delta = order.index(target) - order.index(cur)
        for _i in range(abs(delta)):
            keys("down" if delta > 0 else "up")
            time.sleep(0.08)
        keys("enter")
        time.sleep(0.45)
        if (value_of(sc) or "").strip() == target:
            ok = True
            break
    if not ok:
        keys("esc")
        time.sleep(0.2)
        return "target_not_found"

    # 确定后必须确认对话框真的消失（点空也算"点了"，不核对就会假成功）
    closed = False
    for _ in range(3):
        dlg = find_dialog(win)
        if dlg is None:
            closed = True
            break
        to_front(dlg)
        clicked = False
        for e in walk(dlg, 600):
            try:
                if e.ControlTypeName == "ButtonControl" and "确定" in (e.Name or ""):
                    bx, by, bw, bh = rect(e)
                    click(bx + bw // 2, by + bh // 2, 0.8)
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            return "no_ok"
        time.sleep(0.5)
    if not closed:
        return "ok_unconfirmed"

    # 复核：双击任务项重新打开，读回“画面”是否等于目标（否则说明没真正落盘）
    lr2 = find_label(win, "任务")
    if not lr2:
        return "ok_unverified"
    u.SetCursorPos(lr2[0] + 130, lr2[1] + 16)
    time.sleep(0.1)
    for _i in range(2):
        u.mouse_event(0x0002, 0, 0, 0, 0)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.06)
    time.sleep(0.8)
    dlg = find_dialog(win)
    if dlg is None:
        keys("esc")   # 可能弹出了“新增...”菜单，关掉
        time.sleep(0.2)
        return "not_saved"
    to_front(dlg)
    combos = [e for e in walk(dlg, 600) if e.ControlTypeName == "ComboBoxControl"]
    combos.sort(key=lambda e: rect(e)[1])
    got = (value_of(combos[-1]) or "").strip() if len(combos) >= 2 else ""
    for e in walk(dlg, 600):
        try:
            if e.ControlTypeName == "ButtonControl" and "取消" in (e.Name or ""):
                bx, by, bw, bh = rect(e)
                click(bx + bw // 2, by + bh // 2, 0.6)
                break
        except Exception:
            pass
    return "ok" if got == target else ("mismatch:%s" % got)


def ensure_visible(win, label):
    """把属性面板滚到某一行出现在可视区域内（UIA 会暴露屏幕外的行）。"""
    ensure_props_tab(win)
    l0, t0, w0, h0 = rect(win)
    lo, hi = t0 + 90, t0 + h0 - 150
    scroll_props(win, "up", 30)
    time.sleep(0.4)
    for _ in range(40):
        lr = find_label(win, label)
        if lr is not None and lo <= lr[1] <= hi:
            return lr
        if lr is not None and lr[1] < lo:
            scroll_props(win, "up", 1)
        else:
            scroll_props(win, "down", 1)
        time.sleep(0.15)
    return None


def set_button_label(win, text):
    lr = ensure_visible(win, "文本")
    if not lr:
        return "no_label_row"
    f = row_field(win, lr, 120)
    if not f:
        return "no_label_field"
    click(f[0] + 30, f[1] + f[3] // 2, 0.2)
    keys("ctrl+a")
    paste_text(text)
    keys("enter")
    time.sleep(0.4)
    return "ok"


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file", nargs="?", default=None)
    ap.add_argument("--screen", default=None, help="目标画面名（默认用 JSON 里的名字）")
    ap.add_argument("--force", action="store_true", help="画面已存在时仍新建（加 _导入 后缀）")
    ap.add_argument("--no-bind", action="store_true")
    ap.add_argument("--no-nav", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--probe-ribbon", action="store_true",
                    help="只保存带刻度的 Ribbon 截图，用于校准图标坐标")
    args = ap.parse_args()

    if args.probe_ribbon:
        win = find_main()
        if win is None:
            log("[ERR] 找不到 EasyBuilder X 主窗口，请先打开工程")
            return 2
        probe_ribbon(win)
        return 0
    if not args.json_file:
        ap.error("需要 json_file（或用 --probe-ribbon）")

    data = json.load(open(args.json_file, encoding="utf-8"))
    if data.get("schema") != "ebx-screen/1.0":
        log("[warn] 未知 schema: %s" % data.get("schema"))
    scr = data["screen"]
    target = args.screen or scr["name"]
    elements = [e for e in scr["elements"] if not (args.no_nav and e["type"] == "button")]

    win = find_main()
    if win is None:
        log("[ERR] 找不到 EasyBuilder X 主窗口，请先打开工程")
        return 2
    activate(win)
    max_left = rect(win)[0] + 380
    rows = screen_rows(win, max_left)
    names = [r[0] for r in rows]
    global SCREEN_NAMES
    SCREEN_NAMES = list(names)
    log("[screen] 现有画面: %s" % names)
    if target in names:
        if not args.force:
            log("[ERR] 画面 %s 已存在；用 --force 新建副本，或 --screen 指定别的名字" % target)
            return 3
        target = target + "_导入"
        if target in names:
            target = target + "_2"

    created, err = create_screen(win, target, max_left)
    if err:
        log("[ERR] 新建画面失败: %s" % err)
        return 4

    SCREEN_NAMES = [r[0] for r in screen_rows(win, max_left)]
    origin = calibrate(win)
    if origin is None:
        return 5

    click(rect(win)[0] + RIBBON_TAB[0], rect(win)[1] + RIBBON_TAB[1], 1.0)  # 预热元件页

    done = 0
    for el in elements:
        if args.limit and done >= args.limit:
            break
        kind = el.get("ebx_kind") or TYPE_TO_KIND[el["type"]]
        scroll_props(win, "up", 12)
        ok = False
        for attempt in range(2):
            place(win, origin, kind, el["x"], el["y"], el["w"], el["h"])
            time.sleep(0.3)
            if pane_kind(win) == kind:
                ok = True
                break
            # 可能是别的文档/弹窗抢了焦点：重开目标画面并重新标定
            log("[retry] %s 未放置成功，重开画面编辑器" % el["name"])
            if not open_screen(win, target, max_left):
                log("[warn] 无法重开画面 %s" % target)
                break
            time.sleep(0.6)
            o = calibrate(win)
            if o:
                origin = o
            scroll_props(win, "up", 8)
        if not ok:
            log("[warn] 放置失败: %s" % el["name"])
            continue
        set_field_by_label(win, "名称", el["name"])
        if el["type"] == "static_text" and el.get("text"):
            set_field_by_label(win, "文本", el["text"])
        if el.get("tag") and not args.no_bind:
            r = bind_tag(win, el["tag"], kind, bool(el.get("readonly")))
            log("[bind] %s <- %s : %s" % (el["name"], el["tag"], r))
        if el["type"] == "button":
            if el.get("task", {}).get("type") == "switch_screen" and not args.no_nav:
                t = add_switch_task(win, el["task"]["target"])
                log("[task] %s -> %s : %s" % (el["name"], el["task"]["target"], t))
            if el.get("label"):
                l = set_button_label(win, el["label"])
                log("[label] %s : %s" % (el["name"], l))
        done += 1
        log("[done] %d/%d %s (%s)" % (done, len(elements), el["name"], kind))

    if not args.no_save:
        keys("ctrl+s")
        time.sleep(1.2)
    log("[ok] 已重建 %d 个元件到画面 %s" % (done, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
