"""ss_tree.py - drive the Sysmac Studio project tree (Multiview Explorer). ELEVATED.

  ss_tree.py struct <pid> [maxDepth]        handles + child counts only (never reads text)
  ss_tree.py rows <pid>                     UIA rows (measured: ROOT nodes only)
  ss_tree.py count <pid> <path>             number of children of a node
  ss_tree.py select <pid> <path>            TVM_SELECTITEM, no print
  ss_tree.py goto <pid> <path>              TVM_SELECTITEM + caret read-back
  ss_tree.py expand <pid> <path>            TVM_EXPAND (works on ROOT nodes only)
  ss_tree.py copy <pid> <path>              select then 编辑(E) > 复制(C)
  ss_tree.py paste <pid> <path> [--yes]     select then 编辑(E) > 粘贴(P)
  ss_tree.py del <pid> <path> [--yes]       select then 编辑(E) > 删除(D)

Nothing here needs the foreground window except copy/paste/del (they open the
real menu).  Caret positioning works on a locked desktop.

path = dot separated child indices from the root, e.g.
    0     配置和设置      1     编程
    1.0   POUs            1.0.2 功能块
Indexes depend on the project - confirm them with 'struct', or read every caption
with 'ss_uimap.py treelabels'.

Never send TVM_GETITEM (0x110C, the ANSI variant) or TVM_GETITEMW with a TVITEM whose
pszText points into THIS process: both crash Sysmac Studio.  Item text is readable,
but only via TVM_GETITEMW (0x113E) with the TVITEMW *and* the character buffer
allocated inside Sysmac - that is what ss_uimap.py's node_text()/treelabels do.
"""
import sys
import time
import ctypes
import ctypes.wintypes as wt

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import ss  # noqa: E402  (also imports uiautomation)

# uiautomation re-declares Win32 prototypes; restore the 64-bit safe ones.
_u = ctypes.windll.user32
_u.SendMessageW.restype = ctypes.c_ssize_t
_u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]

TV_FIRST = 0x1100
TVM_EXPAND = TV_FIRST + 2
TVE_COLLAPSE = 1
TVE_EXPAND = 2
TVM_GETCOUNT = TV_FIRST + 5
TVM_GETNEXTITEM = TV_FIRST + 10
TVM_SELECTITEM = TV_FIRST + 11
TVGN_ROOT = 0
TVGN_NEXT = 1
TVGN_PARENT = 3
TVGN_CHILD = 4
TVGN_CARET = 9


def sm(hw, msg, wp=0, lp=0):
    return _u.SendMessageW(wt.HWND(hw), msg, wp, lp)


def find_tree(pid):
    """Return the HWND of the WinForms SysTreeView32 children of this pid."""
    out = []

    def check(hw):
        c = ctypes.create_unicode_buffer(256)
        _u.GetClassNameW(hw, c, 256)
        if 'SysTreeView32' in c.value:
            r = wt.RECT()
            _u.GetWindowRect(hw, ctypes.byref(r))
            out.append((ctypes.cast(hw, ctypes.c_void_p).value, c.value,
                        (r.left, r.top, r.right - r.left, r.bottom - r.top)))

    top = []

    def cb(hw, lp):
        p = wt.DWORD()
        _u.GetWindowThreadProcessId(hw, ctypes.byref(p))
        if p.value == pid:
            top.append(hw)
        return True

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    _u.EnumWindows(CB(cb), 0)
    for hw in top:
        check(hw)
        _u.EnumChildWindows(hw, CB(lambda h, l: (check(h), True)[1]), 0)
    return out


def tree_hwnd(pid):
    ts = find_tree(pid)
    if not ts:
        raise SystemExit('no SysTreeView32 under this pid (project not open?)')
    return ts[0][0]


def node(hw, path):
    if not path:
        return 0
    h = 0
    for depth, i in enumerate(path):
        c = sm(hw, TVM_GETNEXTITEM, TVGN_ROOT, 0) if depth == 0 \
            else sm(hw, TVM_GETNEXTITEM, TVGN_CHILD, h)
        for _ in range(i):
            if not c:
                return 0
            c = sm(hw, TVM_GETNEXTITEM, TVGN_NEXT, c)
        h = c
        if not h:
            return 0
    return h


def children(hw, h):
    out = []
    c = sm(hw, TVM_GETNEXTITEM, TVGN_CHILD, h)
    while c:
        out.append(c)
        c = sm(hw, TVM_GETNEXTITEM, TVGN_NEXT, c)
    return out


def visible_rows(pid):
    """UIA children of SolutionTreeView.  Measured: these are the TOP-LEVEL items
    only (one 'Tree' element per root node, each with an exact rectangle) - the
    expanded children are NOT exposed."""
    c, _ = ss.find(pid, 'SolutionTreeView')
    if c is None:
        return []
    rows = []
    try:
        for i, k in enumerate(c.GetChildren()):
            r = k.BoundingRectangle
            rows.append({'i': i, 'x': r.left, 'y': r.top,
                         'rect': (r.left, r.top, r.right - r.left, r.bottom - r.top)})
    except Exception:
        pass
    return rows


def caret(hw):
    return sm(hw, TVM_GETNEXTITEM, TVGN_CARET, 0)


def parent_of(hw, h):
    return sm(hw, TVM_GETNEXTITEM, TVGN_PARENT, h)


def set_caret(hw, h):
    """TVM_SELECTITEM with TVGN_CARET moves the tree caret.  Measured: this needs
    neither the foreground window nor synthetic input, so it also works on a
    locked / disconnected desktop.  Returns the caret really is 'h'."""
    sm(hw, TVM_SELECTITEM, TVGN_CARET, h)
    time.sleep(0.05)
    return caret(hw) == h


def goto(pid, path):
    """Move the tree caret to a node addressed by path (message based, verified).
    Ancestors are expanded so the node is actually visible in the pane."""
    hw = tree_hwnd(pid)
    for k in range(1, len(path)):
        sm(hw, TVM_EXPAND, TVE_EXPAND, node(hw, path[:k]))
    h = node(hw, path)
    if not h:
        raise SystemExit(f'path {path} does not exist in this project')
    if not set_caret(hw, h):
        raise SystemExit(f'caret not moved to {path} (caret={caret(hw)} want={h})')
    n = len(children(hw, h))
    print(f'caret={caret(hw)} path={path} children={n}')
    return hw


def expand_to(pid, path):
    """Expand the node at path (idempotent) and report its child count."""
    hw = tree_hwnd(pid)
    h = node(hw, path)
    if not h:
        raise SystemExit(f'path {path} does not exist in this project')
    ret = sm(hw, TVM_EXPAND, TVE_EXPAND, h)
    time.sleep(0.05)
    set_caret(hw, h)
    kids = children(hw, h)
    print(f'path={path} node={h} expand_ret={ret} (1 = was collapsed) children={len(kids)}')
    if not kids:
        print('NOTE: leaf node - nothing to expand')
    return hw


def answer_yes(pid, wait=1.2):
    time.sleep(wait)
    for name in ('是(Y)', '是', 'Yes'):
        ctl, _ = ss.find(pid, name)
        if ctl is None:
            continue
        try:
            r = ctl.BoundingRectangle
            print(f'confirm dialog: {name} at ({r.left},{r.top})')
            try:
                ctl.GetInvokePattern().Invoke()
            except Exception:
                ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        except Exception as e:
            print(f'confirm click failed: {e}')
            return 1
        time.sleep(1.0)
        return 0
    print('no confirm dialog')
    return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd = sys.argv[1].lower()
    pid = ss.resolve_pid(sys.argv[2])
    path = [int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else '').split('.') if v != '']
    yes = '--yes' in sys.argv
    if not ss.is_admin():
        print('WARN: not admin - UIA lookups may return nothing (UIPI)')

    if cmd == 'struct':
        maxd = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        hw = tree_hwnd(pid)
        print(f'tree={hw} total_nodes={sm(hw, TVM_GETCOUNT)}')

        def walk(h, d):
            kids = children(hw, h)
            print('  ' * d + f'[{d}] h={h} kids={len(kids)}')
            if kids and d < maxd:
                for k in kids:
                    walk(k, d + 1)

        root = sm(hw, TVM_GETNEXTITEM, TVGN_ROOT, 0)
        while root:
            walk(root, 0)
            root = sm(hw, TVM_GETNEXTITEM, TVGN_NEXT, root)
        return 0

    if cmd == 'rows':
        rows = visible_rows(pid)
        print(f'visible rows = {len(rows)}')
        for r in rows:
            print(f"idx={r['i']:3d} x={r['x']:4d} y={r['y']:4d} "
                  f"w={r['rect'][2]:4d} h={r['rect'][3]:3d}")
        return 0

    hw = tree_hwnd(pid)
    h = node(hw, path)
    print(f'tree={hw} path={path} node={h}')
    if cmd == 'count':
        print('children =', len(children(hw, h)) if h else 0)
        return 0

    if cmd == 'goto':
        goto(pid, path)
        return 0

    if cmd == 'expand':
        expand_to(pid, path)
        return 0

    if cmd == 'collapse':
        ret = sm(hw, TVM_EXPAND, TVE_COLLAPSE, h)
        time.sleep(0.05)
        print(f'path={path} node={h} collapse_ret={ret} (1 = was expanded)')
        return 0

    if not h:
        print('node not found')
        return 1

    main_hw = ss.main_hwnd(pid)
    ss.force_foreground(main_hw)
    print('select ret', sm(hw, TVM_SELECTITEM, TVGN_CARET, h),
          'caret =', sm(hw, TVM_GETNEXTITEM, TVGN_CARET, 0))
    time.sleep(0.4)

    MENU = {'copy': ('编辑(E)', '复制(C)'),
            'paste': ('编辑(E)', '粘贴(P)'),
            'del': ('编辑(E)', '删除(D)')}
    if cmd in MENU:
        m, i = MENU[cmd]
        ss.menu_item(pid, m, i, main_hw)
        time.sleep(1.2)
        if cmd == 'copy':
            print('verify with: python ss_clip.py list  (format '
                  'Omron.SolutionEntityClipboardFormatter / Omron.SolutionMultipleRootEntites)')
        elif yes:
            answer_yes(pid)
        else:
            print('confirm dialog may be waiting - re-run with --yes to answer it')
        return 0

    if cmd == 'select':
        print('ok (selected)')
        return 0

    print('unknown command', cmd)
    return 2


if __name__ == '__main__':
    sys.exit(main())
