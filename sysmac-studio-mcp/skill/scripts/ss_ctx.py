"""ss_ctx.py - drive the tree CONTEXT MENU of Sysmac Studio (ELEVATED + foreground).

Why: the ribbon `编辑(E)` dropdown is a custom-drawn WPF popup that exposes only a
PaneControl to UIA, and 粘贴(P) there can be silently greyed out.  Right-clicking a
tree row opens a REAL menu whose MenuItems ARE exposed (复制(C) / 粘贴(P) /
删除多个项目 / 重命名(N) ...), so they can be found by name and clicked.

  ss_ctx.py <pid|auto> <x> <y> list                right-click at (x,y), list menu items
  ss_ctx.py <pid|auto> <x> <y> click "<item>"      right-click, then click that item
  ss_ctx.py <pid|auto> <x> <y> shift10 list        focus row with a left click, then Shift+F10

(x,y) are physical screen pixels of a visible row (grab + crop to locate; rows are
26 px apart).  Everything happens in ONE process - popup HWNDs die with it.
"""
import sys
import time
import os
import ctypes
import ctypes.wintypes as wt

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import uiautomation as auto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss                                                               # noqa: E402
import ss_uimap as U                                                    # noqa: E402

auto.SetGlobalSearchTimeout(6)
u = ctypes.windll.user32
u.SendMessageW.restype = ctypes.c_ssize_t
u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]


def items(pid, main):
    """[(control, name, rect, enabled)] of every MenuItem in visible popups."""
    out = []
    for w in ss.wins_of(pid):
        if not w['vis'] or w['hwnd'] == main or w['rect'][2] <= 80:
            continue
        root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        if root is None:
            continue

        def rec(c, d):
            if d > 6:
                return
            try:
                if c.ControlTypeName == 'MenuItemControl':
                    r = c.BoundingRectangle
                    out.append((c, c.Name, (r.left, r.top, r.right - r.left, r.bottom - r.top), c.IsEnabled))
            except Exception:
                pass
            try:
                for k in c.GetChildren():
                    rec(k, d + 1)
            except Exception:
                pass

        rec(root, 0)
    return out


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    if not ss.is_admin():
        print('WARN: not admin - UIA lookups may return nothing (UIPI)')
    pid = U.resolve_pid(sys.argv[1])
    x, y = int(sys.argv[2]), int(sys.argv[3])
    mode = sys.argv[4]
    main_hw = ss.main_hwnd(pid)
    if not ss.force_foreground(main_hw):
        print('WARN: no foreground desktop')
    time.sleep(0.4)

    # A menu left open by an earlier call is toggled CLOSED by the next right-click,
    # which silently breaks this command.  Dismiss leftovers with a click on blank
    # space first (default: empty area of the tree pane, override with --blank x,y).
    bx, by = 300, 760
    if '--blank' in sys.argv:
        i = sys.argv.index('--blank')
        bx, by = int(sys.argv[i + 1]), int(sys.argv[i + 2])
    ss.click_at(bx, by)
    time.sleep(0.4)

    if mode == 'shift10':
        ss.click_at(x, y)
        time.sleep(0.4)
        u.keybd_event(0x10, 0, 0, 0)      # Shift down
        u.keybd_event(0x79, 0, 0, 0)      # F10
        u.keybd_event(0x79, 0, 2, 0)
        u.keybd_event(0x10, 0, 2, 0)
        time.sleep(0.8)
    else:
        ss.click_at(x, y, kind='rclick')
        time.sleep(0.8)

    found = items(pid, main_hw)
    if not found:
        print('no popup menu items found')
        ss.grab(pid, 'ctx-dbg.png')
        print('debug screenshot ctx-dbg.png (popups: %r)' %
              [(w['hwnd'], w['cls'][:40], w['title'], w['rect']) for w in ss.wins_of(pid) if w['hwnd'] != main_hw])
        return 1
    for c, name, rect, en in found:
        print(f'  {name!r:30s} enabled={en} rect={rect}')
    if mode == 'list':
        u.keybd_event(0x1B, 0, 0, 0)
        u.keybd_event(0x1B, 0, 2, 0)
        return 0

    want = sys.argv[5] if len(sys.argv) > 5 else None
    if mode == 'sub':
        # nested submenu: <pid> <x> <y> sub "<parent item>" "<child item>"
        if len(sys.argv) < 7:
            print('sub needs parent and child names')
            return 2
        parent, child = sys.argv[5], sys.argv[6]
        hit = [t for t in found if t[1] == parent] or [t for t in found if parent in (t[1] or '')]
        if not hit:
            print('parent item not in popup:', parent)
            return 1
        _, pname, prect, pen = hit[0]
        print(f'hovering {pname!r} at {prect[:2]}')
        u.SetCursorPos(prect[0] + prect[2] // 2, prect[1] + prect[3] // 2)
        time.sleep(1.0)
        found = items(pid, main_hw)
        # the submenu may be a brand-new popup: re-list and pick the child there
        hit = [t for t in found if t[1] == child] or [t for t in found if child in (t[1] or '')]
        if not hit:
            print('hover gave no submenu - clicking the parent item')
            ss.click_at(prect[0] + prect[2] // 2, prect[1] + prect[3] // 2)
            time.sleep(1.0)
            found = items(pid, main_hw)
            hit = [t for t in found if t[1] == child] or [t for t in found if child in (t[1] or '')]
        if not hit:
            print('child item not found after hovering; visible items:')
            for c, name, rect, en in found:
                print(f'  {name!r} enabled={en} rect={rect}')
            u.keybd_event(0x1B, 0, 0, 0)
            u.keybd_event(0x1B, 0, 2, 0)
            return 1
        ctl, name, rect, en = hit[0]
        print(f'clicking {name!r} enabled={en} at {rect[:2]}')
        try:
            ctl.Click(simulateMove=False)
        except Exception as e:
            ss.click_at(rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)
        time.sleep(1.5)
        return 0

    if not want:
        print('no item name given')
        return 2
    hit = [t for t in found if t[1] == want] or [t for t in found if want in (t[1] or '')]
    if not hit:
        print('item not in popup:', want)
        u.keybd_event(0x1B, 0, 0, 0)
        u.keybd_event(0x1B, 0, 2, 0)
        return 1
    ctl, name, rect, en = hit[0]
    print(f'clicking {name!r} enabled={en} at {rect[:2]}')
    try:
        ctl.Click(simulateMove=False)
    except Exception as e:
        print('click err', e)
        ss.click_at(rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)
    time.sleep(1.5)
    print('done')
    return 0


if __name__ == '__main__':
    sys.exit(main())
