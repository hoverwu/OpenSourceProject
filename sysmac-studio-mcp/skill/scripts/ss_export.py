"""ss_export.py - 文件(F) > 导出(E)... with an overwrite-safe filename. Must run ELEVATED + DPI aware.

  ss_export.py <pid|auto> <文件.smc2> [--keep-dir]

What it does
  1. click the 文件 menu bar cell by COORDINATE (the menu bar is NOT a UIA MenuItemControl)
  2. press the mnemonic key 'E' -> native #32770 '导出文件' dialog
  3. SetForegroundWindow(dialog)   <-- mandatory, otherwise the keystrokes go to the main window
  4. click the filename EditControl (AutomationId=1001), Ctrl+A, Ctrl+V a clipboard string
     (SendKeys cannot type CJK reliably)
  5. click ButtonControl AutomationId='1' (保存(S))
  6. answer the '确认另存为' box with 是(Y)

Notes
  * The dialog remembers the last folder. Pass a bare filename to export into that folder.
  * ValuePattern.SetValue on the filename edit raises COMError on V1.68 - do not use it.
  * If the value printed after Ctrl+V is unchanged, this DirectUI edit ignored the paste
    (observed 2026-10-30). Fallback: click the row of an EXISTING file with that name in the
    list - the filename box is filled automatically. NEVER call SetValue on a list cell:
    it silently starts an in-place rename and pops a '重命名文件' box (pitfalls §29).
  * After the dialogs close the file may still be growing; poll os.path.getsize until it stops
    changing before validating the zip.
  * Success criterion: file size / mtime changed. Repeat exports change the byte count.
"""
import sys
import time
import ctypes
import uiautomation as auto

import ss

u = ctypes.windll.user32
k32 = ctypes.windll.kernel32
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = (ctypes.c_void_p,)
k32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
u.SetClipboardData.restype = ctypes.c_void_p
u.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)


def set_clip(text):
    data = text.encode('utf-16-le') + b'\x00\x00'
    u.OpenClipboard(0)
    try:
        u.EmptyClipboard()
        h = k32.GlobalAlloc(0x0002, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u.SetClipboardData(13, h)          # CF_UNICODETEXT
    finally:
        u.CloseClipboard()


def key(vk):
    for down in (1, 0):
        u.keybd_event(vk, 0, 0 if down else 2, 0)
        time.sleep(0.06)


def dialogs(pid, title=None):
    out = []
    for w in ss.wins_of(pid, only_visible=True):
        if w['cls'] != '#32770':
            continue
        if title and title not in w['title']:
            continue
        out.append(w)
    return out


def controls(hwnd):
    res = []
    try:
        rt = auto.ControlFromHandle(hwnd)
    except Exception:
        return res
    for d in auto.WalkControl(rt, maxDepth=8):
        c = d[0] if isinstance(d, tuple) else d
        try:
            r = c.BoundingRectangle
            if r.right > 0:
                res.append((c, r))
        except Exception:
            pass
    return res


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pid = ss.resolve_pid(sys.argv[1])
    name = sys.argv[2]
    hw = ss.main_hwnd(pid)
    if not hw:
        print('no main window')
        return 1

    # 1. menu bar by coordinate: window-relative (48, 55) at 125% DPI
    wr = None
    for w in ss.wins_of(pid):
        if w['hwnd'] == hw:
            wr = w['rect']
    if wr is None:
        print('cannot read main rect')
        return 1
    left, top = wr[0], wr[1]
    ss.force_foreground(hw)
    time.sleep(0.6)
    ss.click_at(left + 48, top + 55)
    time.sleep(0.9)
    key(0x45)                              # 'E' = 导出(E)...

    # 2. wait for the native dialog
    dlg = None
    for _ in range(20):
        time.sleep(0.5)
        ws = [w for w in dialogs(pid) if '导出' in w['title']] or dialogs(pid)
        if ws:
            dlg = ws[0]['hwnd']
            break
    if dlg is None:
        print('导出文件 dialog did not open (menu broken? see pitfalls §20)')
        return 1
    u.SetForegroundWindow(ctypes.c_void_p(dlg))
    time.sleep(0.6)

    # 3. filename edit
    ed = None
    r0 = None
    for c, r in controls(dlg):
        if c.ControlTypeName == 'EditControl' and (c.AutomationId or '') == '1001':
            ed, r0 = c, r
    if ed is None:
        for c, r in controls(dlg):
            if c.ControlTypeName == 'EditControl':
                ed, r0 = c, r
                break
    if ed is None:
        print('no filename edit')
        return 1
    set_clip(name)
    ss.click_at((r0.left + r0.right) // 2, (r0.top + r0.bottom) // 2)
    time.sleep(0.4)
    u.keybd_event(0x11, 0, 0, 0)
    key(0x41)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.2)
    u.keybd_event(0x11, 0, 0, 0)
    key(0x56)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.8)
    try:
        print('value %r' % ed.GetValuePattern().Value)
    except Exception:
        print('value unreadable')

    # 4. 保存(S)
    for c, r in controls(dlg):
        if c.ControlTypeName == 'ButtonControl' and (c.AutomationId or '') == '1':
            ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            print('save clicked')
            break
    time.sleep(3.0)

    # 5. overwrite confirmation
    for w in dialogs(pid):
        u.SetForegroundWindow(ctypes.c_void_p(w['hwnd']))
        time.sleep(0.4)
        for c, r in controls(w['hwnd']):
            if c.ControlTypeName == 'ButtonControl' and (c.Name or '').strip().startswith('是'):
                ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                print('confirmed overwrite')
                time.sleep(2.5)
                break
    left_over = [(w['hwnd'], w['title']) for w in dialogs(pid)]
    print('dialogs left: %r' % left_over)
    return 0


if __name__ == '__main__':
    sys.exit(main())
