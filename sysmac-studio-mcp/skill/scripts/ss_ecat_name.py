# -*- coding: utf-8 -*-
"""ss_ecat_name.py - 在 EtherCAT 右侧参数表里写「设备名称」。

作者：hoverwu ｜ 版本：0.1.0 ｜ 建立：2026-11-08 ｜ 非官方，必须**提权**运行

实测形状（2026-11-08，SS 1.68 64bit）：
  参数表 = Custom|NodeOutlineParameter > Custom|ParameterSettingTable > List|list
  「设备名称」行 = ListItem(Class=…ParameterSettingTable.StringParameterItem)
       ├ Text|设备名称
       ├ Custom|alert IconView
       └ Text|E001  AutomationId='text'   ← 值就在这个 TextBlock 上
  这个 TextBlock **没有 ValuePattern**（uiautomation 的 TextControl 不支持 SetValue），
  点一下也不会在 UIA 里长出 EditControl，但点击处已进入**行内编辑态**，
  直接 Ctrl+A → Ctrl+V 粘贴 → Enter 就能写入（实测：不先全选会在光标处插入，
  变成 'E0设备名示例101' 这种脏值）。

  ss_ecat_name.py <pid> <out> <设备名>
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import uiautomation as auto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss_uimap as M                                                    # noqa: E402

auto.SetGlobalSearchTimeout(6)


def rect(c):
    r = M.prop(c, 'BoundingRectangle')
    try:
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return (0, 0, 0, 0)


def texts(c, maxd=3):
    out = []
    for k in M.find_by_type(c, ('TextControl',), maxd=maxd):
        nm = (M.prop(k, 'Name') or '').strip()
        if nm:
            out.append(nm)
    return out


def set_clip(text):
    u = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = (ctypes.c_void_p,)
    k32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    u.SetClipboardData.restype = ctypes.c_void_p
    u.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    data = text.encode('utf-16-le') + b'\x00\x00'
    u.OpenClipboard(0)
    try:
        u.EmptyClipboard()
        h = k32.GlobalAlloc(0x0002, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u.SetClipboardData(13, h)
    finally:
        u.CloseClipboard()


def ctrl_key(vk):
    u = ctypes.windll.user32
    u.keybd_event(0x11, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.15)


def paste(text):
    set_clip(text)
    time.sleep(0.15)
    ctrl_key(0x56)


def name_row(pid):
    root = auto.ControlFromHandle(wt.HWND(M.main_window(pid)['hwnd']))
    for c in M.find_by_type(root, ('ListItemControl',), maxd=28):
        ts = texts(c, 2)
        if ts and ts[0] == '设备名称':
            return c
    return None


def value_text(row):
    for t in M.find_by_type(row, ('TextControl',), maxd=2):
        if (M.prop(t, 'AutomationId') or '') == 'text':
            return t
    return None


def current(row):
    ts = texts(row, 2)
    return ts[-1] if ts else ''


def set_name(pid, name, attempts=3):
    """返回 (ok, info)。会先点中单元格再 Ctrl+A 覆盖，避免脏值。"""
    row = name_row(pid)
    if row is None:
        return False, 'no 设备名称 row'
    val = value_text(row)
    if val is None:
        return False, 'no value TextBlock (AutomationId=text)'
    before = current(row)
    M.force_foreground(M.main_window(pid)['hwnd'])
    time.sleep(0.2)
    x, y = rect(val)[0] + 20, rect(val)[1] + 8
    for i in range(attempts):
        M.left_click(x, y)
        time.sleep(0.4)
        ctrl_key(0x41)                 # 先全选，否则会在光标处插入
        time.sleep(0.15)
        paste(name)
        time.sleep(0.3)
        ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
        time.sleep(1.0)
        row = name_row(pid)
        now = current(row) if row is not None else ''
        if now == name:
            return True, 'before=%r after=%r (attempt %d)' % (before, now, i + 1)
        val = value_text(row) if row is not None else None
        if val is None:
            break
        x, y = rect(val)[0] + 20, rect(val)[1] + 8
        before = now
    return False, 'before=%r after=%r' % (before, current(row) if row else '')


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    pid = M.resolve_pid(argv[0])
    out, name = argv[1], argv[2]
    ok, info = set_name(pid, name)
    M.dump(out, '# ss_ecat_name pid=%d name=%r' % (pid, name),
           ['# VERDICT ok=%s %s' % (ok, info)])
    print('ok=%s %s' % (ok, info))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
