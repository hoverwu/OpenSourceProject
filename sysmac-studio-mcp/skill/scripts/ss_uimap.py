# -*- coding: utf-8 -*-
"""ss_uimap.py - map the whole Sysmac Studio UIA tree: panels, menus, context menus, editors.

Author: hoverwu | version: 0.1.0 | unofficial. Must run ELEVATED (Sysmac runs High) + DPI aware.

  ss_uimap.py scan  <pid|auto> <out> [--all] [--depth N] [--pat]
        Full tree of the main window. Default prunes IsOffscreen subtrees.
        Columns: indent | Type | Name | AutomationId | ClassName | HelpText | rect
                 | E=IsEnabled F=IsOffscreen K=focusable | patterns
  ss_uimap.py panels <pid|auto> <out> [--fit]
        One line per docked region: menu bar items, toolbar buttons, tab strips,
        tree headers, status bar texts, editor tabs. Cheap way to see the shell.
        Pass --fit when the frame hangs below the monitor - without it the status
        bar / 输出·编译 tabs / 筛选器 read fine but are physically unreachable.
  ss_uimap.py menus  <pid|auto> <out> [--only A,B]
        Open EVERY top-level menu (read only, Esc to close) and record all items:
        text / accelerator / enabled / has-submenu / toggle state. 2nd level opened too.
  ss_uimap.py ctx    <pid|auto> <x> <y> <out> [label]
        Real right-click at physical px, dump the popup, Esc to close.
  ss_uimap.py editor <pid|auto> <out>
        Which editors are open (TabbedMdi), their option tabs + left nav + tool strips.
  ss_uimap.py open <pid|auto> <out> 1.0.2.3 0.0 ... [--fit] [--depth N] [--all]
                                             [--pat] [--expand] [--close]
        OPEN the editors for these tree paths - click + real VK_RETURN, and if that
        does nothing, deselect + real double-click - then walk each new
        DocumentWindow into the file.  Never types in a page.  --pat appends the
        UIA patterns each element answers (that is how SyntaxEditor=Text,
        closeButton=Invoke-but-refused got measured); --expand additionally calls
        ExpandCollapse.Expand() on every folded area of the page - the ST/LD 变量
        declaration table only exists in UIA after that - and re-walks.  --close
        shuts the editors it opened through their own closeButton.
  ss_uimap.py close <pid|auto> <out> [--all] [Name ...]
        Close editors by document name (used to leave the app clean after a sweep).
  ss_uimap.py tree  <pid|auto> <out> [--expand]
        Project tree STRUCTURE via TVM_GETNEXTITEM: path index, child count, expand
        state, caret.  For labels use treelabels (structure alone is enough to
        identify a node: child count + order is a reliable fingerprint).
  ss_uimap.py treelabels <pid|auto> <out>
        Every node as `path  label  kids=N`, read NATIVELY with TVM_GETITEMW
        (0x113E) using a TVITEMW + text buffer allocated INSIDE Sysmac.  The ANSI
        variant (0x110C) and any local-buffer cross-process write CRASH Sysmac -
        never use them.  Safe: verified twice over an 84-node project.
  ss_uimap.py treectx <pid|auto> <out> 0 1 1.0 1.0.2 ...
        Select each tree path, right-click its row (TVM_GETITEMRECT through a remote
        buffer) and record the context menu.  Prints the node label too.
  ss_uimap.py treerows <pid|auto> <out> [--max N] [--depth N]
        Walk the live tree, opening every node with a real click on its +/- glyph
        (TVM_EXPAND only works on the two roots; deeper it returns 0 and the
        screen does not change) and scrolling rows into view with the wheel.
        Records path / indent / label width / child count; name the paths
        with treelabels (see above) - do not try to read the rows through UIA or
        MSAA, both return empty Name for this WinForms tree.
  ss_uimap.py diff   <a> <b>
        Line diff of two dumps (what opened/closed/appeared).

Read-only by design: it only opens menus/tabs and presses Esc. It never invokes a menu
item, never types into a field, never saves. Destructive entries are only *recorded*.
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

auto.SetGlobalSearchTimeout(6)
u = ctypes.windll.user32
_u = ctypes.windll.user32
_u.SendMessageW.restype = ctypes.c_ssize_t
_u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]
_u.PostMessageW.restype = ctypes.c_int
_u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]

PROC = 'SysmacStudio.exe'
PAT_NAMES = [
    ('Invoke', 'GetInvokePattern'),
    ('ExpandCollapse', 'GetExpandCollapsePattern'),
    ('Toggle', 'GetTogglePattern'),
    ('SelectionItem', 'GetSelectionItemPattern'),
    ('Selection', 'GetSelectionPattern'),
    ('Value', 'GetValuePattern'),
    ('RangeValue', 'GetRangeValuePattern'),
    ('Scroll', 'GetScrollPattern'),
    ('Grid', 'GetGridPattern'),
    ('Table', 'GetTablePattern'),
    ('Text', 'GetTextPattern'),
]


# --------------------------------------------------------------- helpers

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def wins_of(pid_target, only_visible=True):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hw, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(p))
        if p.value != pid_target:
            return True
        if only_visible and not u.IsWindowVisible(hw):
            return True
        n = u.GetWindowTextLengthW(hw)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hw, b, n + 1)
        c = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hw, c, 256)
        r = wt.RECT()
        u.GetWindowRect(hw, ctypes.byref(r))
        out.append(dict(hwnd=ctypes.cast(hw, ctypes.c_void_p).value, title=b.value,
                        cls=c.value,
                        rect=(r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True

    u.EnumWindows(cb, 0)
    return out


def resolve_pid(arg):
    if str(arg).isdigit():
        return int(arg)
    cands = []
    for line in os.popen('tasklist /FI "IMAGENAME eq %s" /FO CSV /NH' % PROC).read().splitlines():
        f = [x.strip('"') for x in line.split('","')]
        if len(f) > 1 and f[1].isdigit():
            cands.append(int(f[1]))
    best = None
    for pid in cands:
        for w in wins_of(pid):
            area = w['rect'][2] * w['rect'][3]
            if w['title'].endswith('Sysmac Studio (64bit)') or 'Sysmac Studio' in w['title']:
                if best is None or area > best[1]:
                    best = (pid, area)
    if not best:
        raise SystemExit('no Sysmac instance found')
    return best[0]


def main_window(pid):
    ws = [w for w in wins_of(pid) if 'Sysmac Studio' in w['title']]
    if not ws:
        ws = wins_of(pid)
    ws.sort(key=lambda w: -w['rect'][2] * w['rect'][3])
    _MW[0] = ws[0]['hwnd']
    return ws[0]


def force_foreground(hwnd, tries=3):
    # Already in front? Then do NOT tap Alt: measured 2026-11-06 (probe_sweep), a
    # click after an Alt tap gets swallowed by Sysmac's menu-mnemonic mode, so only
    # the very first click of a run landed and every later one did nothing.
    if u.GetForegroundWindow() == hwnd:
        return True
    for _ in range(tries):
        u.ShowWindow(hwnd, 9)          # SW_RESTORE
        u.keybd_event(0x12, 0, 0, 0)   # alt tap so SetForegroundWindow works
        u.keybd_event(0x12, 0, 2, 0)
        u.SetForegroundWindow(hwnd)
        time.sleep(0.35)
        fg = u.GetForegroundWindow()
        p = wt.DWORD()
        u.GetWindowThreadProcessId(fg, ctypes.byref(p))
        if fg == hwnd:
            return True
    return False


def fit_on_screen(hwnd, margin=8):
    """Slide the frame up/left until it fits the monitor; return the old rect.

    Measured 2026-11-06 (probe_zorder): Sysmac's main window is (0,253)-(1938,1351)
    on a 1920x1080 display.  The tree's client bottom is then 1253 - 173 px below
    the screen - and because the control only stops scrolling when its LAST row
    reaches that client bottom, the final ~7 rows of the document can never be
    raised into a clickable position (hitcheck: 1.1.0 / 1.2.1 unreachable, every
    node above them hit).  Moving the window is the only fix that does not need a
    resize; the caller puts the rect back with restore_rect().
    """
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r))
    old = (r.left, r.top, r.right - r.left, r.bottom - r.top)
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)      # SM_CXSCREEN/CYSCREEN
    dx = max(0, r.right - (sw - margin))
    dy = max(0, r.bottom - (sh - margin))
    if dx or dy:
        u.SetWindowPos(wt.HWND(hwnd), 0, r.left - dx, r.top - dy, 0, 0,
                       0x0001 | 0x0004 | 0x0040)   # NOSIZE | NOZORDER | NOACTIVATE
        time.sleep(0.5)
        u.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r))
    return old, (r.left, r.top, r.right - r.left, r.bottom - r.top)


def restore_rect(hwnd, rect):
    x, y, w, h = rect
    u.SetWindowPos(wt.HWND(hwnd), 0, x, y, w, h, 0x0004 | 0x0040)   # NOZORDER|NOACTIVATE
    time.sleep(0.4)


def key(vk, up=False):
    u.keybd_event(vk, 0, 2 if up else 0, 0)


def esc(times=2):
    for _ in range(times):
        key(0x1B)
        time.sleep(0.25)
        key(0x1B, up=True)
        time.sleep(0.15)


def right_click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    u.mouse_event(0x0008, 0, 0, 0, 0)   # RIGHTDOWN
    time.sleep(0.06)
    u.mouse_event(0x0010, 0, 0, 0, 0)   # RIGHTUP
    time.sleep(0.55)


def left_click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.2)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.35)


def double_click(x, y):
    """Two left presses inside the double-click time, same dot.

    Only ever used on a row that has been DE-selected first (TVM_SELECTITEM
    TVGN_CARET 0): double-clicking an already-selected Sysmac tree row starts
    inline rename instead of opening the page (project-tree.md §3.1).
    """
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    for _ in range(2):
        u.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.03)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.08)
    time.sleep(0.5)


def prop(c, name, default=''):
    try:
        return getattr(c, name)
    except Exception:
        return default


def pats(c):
    got = []
    for nm, meth in PAT_NAMES:
        try:
            if getattr(c, meth)() is not None:
                got.append(nm)
        except Exception:
            pass
    return got


def line_of(c, with_pat=False):
    r = prop(c, 'BoundingRectangle')
    try:
        geo = '(%d,%d %dx%d)' % (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        geo = '(?)'
    flags = []
    if not prop(c, 'IsEnabled', True):
        flags.append('disabled')
    if prop(c, 'IsOffscreen', False):
        flags.append('off')
    if prop(c, 'IsKeyboardFocusable', False):
        flags.append('kbd')
    st = ''
    try:
        sp = c.GetSelectionItemPattern()
        if sp is not None and sp.IsSelected:
            st = ' SELECTED'
    except Exception:
        pass
    txt = prop(c, 'Name') or ''
    hp = prop(c, 'HelpText') or ''
    return '%s|%s|%s|%s|%s%s|%s|%s' % (
        prop(c, 'ControlTypeName', '?').replace('Control', ''),
        txt.replace('\n', '\\n')[:90],
        prop(c, 'AutomationId') or '',
        prop(c, 'ClassName') or '',
        hp.replace('\n', '\\n')[:60],
        st, ' '.join(flags) or '-', geo) + ((' PAT=' + ','.join(pats(c))) if with_pat else '')


def walk(c, d, opt, lines):
    if len(lines) > opt['max_lines']:
        return
    off = prop(c, 'IsOffscreen', False)
    if off and not opt['all']:
        return
    lines.append('  ' * d + line_of(c, opt['pat']))
    if d >= opt['depth']:
        return
    try:
        ks = c.GetChildren()
    except Exception:
        return
    for k in ks:
        walk(k, d + 1, opt, lines)


def dump(path, header, lines):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join([header] + lines) + '\n')
    return len(lines)


def popup_roots(pid):
    """Top-level windows that are not the main frame: menus, dropdowns, dialogs."""
    mw = main_window(pid)
    return [w for w in wins_of(pid) if w['hwnd'] != mw['hwnd']]


def menu_popups(pid):
    """Popup windows of the pid that actually contain MenuItem descendants."""
    res = []
    for w in popup_roots(pid):
        try:
            c = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        except Exception:
            continue
        items = find_by_type(c, ('MenuItemControl',), maxd=8)
        if items:
            res.append((w, c, len(items)))
    return res


def find_by_type(root, types, maxd=30, out=None, d=0):
    """Collect controls whose ControlTypeName is in `types` (bounded depth)."""
    if out is None:
        out = []
    if d > maxd or len(out) > 400:
        return out
    try:
        t = prop(root, 'ControlTypeName', '')
    except Exception:
        return out
    if t in types:
        out.append(root)
    try:
        for c in root.GetChildren():
            find_by_type(c, types, maxd, out, d + 1)
    except Exception:
        pass
    return out


# --------------------------------------------------------------- commands

def cmd_scan(argv):
    pid = resolve_pid(argv[0])
    out = argv[1]
    opt = dict(all='--all' in argv, depth=99, max_lines=200000, pat='--pat' in argv)
    for a in argv:
        if a.startswith('--depth='):
            opt['depth'] = int(a.split('=', 1)[1])
    mw = main_window(pid)
    root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    lines = []
    t0 = time.time()
    walk(root, 0, opt, lines)
    n = dump(out, '# scan pid=%d hwnd=%d %r  offscreen=%s depth=%s pat=%s  %.1fs  nodes=%d'
             % (pid, mw['hwnd'], mw['title'], opt['all'], opt['depth'], opt['pat'],
                time.time() - t0, len(lines)), lines)
    print('nodes=%d -> %s' % (n, out))
    return 0


def cmd_panels(argv):
    """Dump the main-window skeleton: menu bar, toolbar bands, dock containers,
    tree host, status bar, grids - one `==` block per area, plus every child line
    with its rect, states and the columns `line_of` prints (type|Name|id|class|
    HelpText|states|rect).

    --fit slides the window onto the screen first.  This matters more here than
    anywhere else in the tool: the default frame often hangs 200+ px below the
    monitor (measured (0,253 1938x1098) on 1920x1080), which puts the status bar,
    the 输出/编译 tabs and the 筛选器 expander off screen.  Their text still reads
    through UIA, but no real click can reach them, so a dump without --fit tends to
    record "there" as "reachable".  The original rect is restored at the end.
    """
    pid = resolve_pid(argv[0])
    out = argv[1]
    mw = main_window(pid)
    old_rect = None
    note_fit = 'window left where it was (pass --fit to slide it on screen)'
    if '--fit' in argv:
        old_rect, new = fit_on_screen(mw['hwnd'])
        note_fit = 'window %s -> %s' % (old_rect, new)
    root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    lines = []
    want = ('MenuBarControl', 'MenuControl', 'ToolBarControl', 'TabControl', 'TreeControl',
            'StatusBarControl', 'DataGridControl', 'ListControl', 'WindowControl',
            'CustomControl', 'PaneControl')
    try:
        for t in want:
            for c in find_by_type(root, (t,)):
                lines.append('== %s %s' % (t, line_of(c)))
                try:
                    for ch in c.GetChildren():
                        lines.append('   ' + line_of(ch))
                        for g in ch.GetChildren()[:12]:
                            lines.append('      ' + line_of(g))
                except Exception:
                    pass
        for w in popup_roots(pid):
            lines.append('POPUP hwnd=%d cls=%r rect=%s title=%r' %
                         (w['hwnd'], w['cls'], w['rect'], w['title']))
    finally:
        if old_rect:
            restore_rect(mw['hwnd'], old_rect)
    n = dump(out, '# panels pid=%d %r\n# %s' % (pid, mw['title'], note_fit), lines)
    print('lines=%d -> %s  (%s)' % (n, out, note_fit))
    return 0


def menu_bar_items(root):
    """Pick the application menu bar, NOT the title-bar system menu.

    The window's Win32 system menu also shows up as MenuBarControl/MenuControl with
    MenuItem children (Name '系统', rect ~28x28) - it must lose to `MainMenu`.
    """
    cands = []
    for c in find_by_type(root, ('MenuBarControl', 'MenuControl'), maxd=14):
        try:
            items = [k for k in c.GetChildren()
                     if 'MenuItem' in prop(k, 'ControlTypeName', '')]
        except Exception:
            continue
        if not items:
            continue
        aid = prop(c, 'AutomationId') or ''
        r = prop(c, 'BoundingRectangle')
        width = (r.right - r.left) if r else 0
        cands.append(((2 if aid == 'MainMenu' else 0, width, len(items)), items))
    if not cands:
        return []
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def open_menu(item):
    """Expand a top-level menu: ExpandCollapse pattern first, real click as fallback."""
    try:
        sp = item.GetExpandCollapsePattern()
        if sp is not None:
            sp.Expand()
            time.sleep(0.6)
            return 'pattern'
    except Exception:
        pass
    r = prop(item, 'BoundingRectangle')
    try:
        left_click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        return 'click'
    except Exception:
        return 'fail'


def close_menu():
    esc(2)
    time.sleep(0.2)


CONTAINERS = ('Pane', 'Window', 'List', 'Custom', 'Group', 'ScrollViewer', 'Menu',
              'MenuBar', 'Document', 'Tree', 'Header')


def item_desc(k):
    """One-line description of a menu item: name / enabled / accel / state / submenu."""
    t = prop(k, 'ControlTypeName', '').replace('Control', '')
    name = (prop(k, 'Name') or '').replace('\n', '\\n').strip()
    accel, extra = '', []
    try:
        for ch in k.GetChildren():
            cn = (prop(ch, 'Name') or '').strip()
            if not cn or cn.replace('_', '') == name.replace('_', ''):
                continue
            if 'Ctrl' in cn or 'Alt' in cn or 'Shift' in cn or cn == name:
                accel = cn
            else:
                extra.append(cn[:40])
    except Exception:
        pass
    sub = ''
    try:
        ep = k.GetExpandCollapsePattern()
        if ep is not None:
            sub = 'Expandable'
    except Exception:
        pass
    tg = ''
    try:
        tp = k.GetTogglePattern()
        if tp is not None:
            tg = ' toggle=%s' % tp.ToggleState
    except Exception:
        pass
    r = prop(k, 'BoundingRectangle')
    geo = '%d,%d' % (r.left, r.top) if r else '?'
    return '%s|%s|en=%s%s|acc=%s|sub=%s|%s' % (
        t, name, prop(k, 'IsEnabled', True), tg, accel or '-', sub or '-', geo)


def collect_items(c, out, budget, d=0):
    """Flatten MenuItem / Separator under a popup root; containers do not add depth."""
    if budget[0] <= 0 or d > 10:
        return
    try:
        kids = c.GetChildren()
    except Exception:
        return
    for k in kids:
        if budget[0] <= 0:
            return
        t = prop(k, 'ControlTypeName', '').replace('Control', '')
        if t in ('MenuItem', 'Separator', 'ListItem', 'Button', 'CheckBox', 'RadioButton'):
            out.append(k)
            budget[0] -= 1
        elif t in CONTAINERS:
            collect_items(k, out, budget, d + 1)
        else:
            collect_items(k, out, budget, d + 1)


def scrollers(c, found=None, d=0):
    if found is None:
        found = []
    if d > 8 or len(found) > 6:
        return found
    try:
        sp = c.GetScrollPattern()
        if sp is not None and sp.VerticallyScrollable:
            found.append(sp)
    except Exception:
        pass
    try:
        for ch in c.GetChildren():
            scrollers(ch, found, d + 1)
    except Exception:
        pass
    return found


def popup_ids(pid):
    return set(w['hwnd'] for w in popup_roots(pid))


def new_popups(pid, before):
    res = []
    for w in popup_roots(pid):
        if w['hwnd'] in before:
            continue
        try:
            c = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        except Exception:
            continue
        res.append((w, c))
    return res


def map_popup(c, lines, depth, budget, pid, seen_hwnds, expand_sub=True):
    """Record every item of an open popup, scrolling if it is virtualised, then recurse
    into submenus (Expand only - never Invoke)."""
    keys = []
    items = []

    def harvest():
        got = []
        collect_items(c, got, budget)
        for k in got:
            desc = item_desc(k)
            key = desc.rsplit('|', 1)[0]
            if key not in keys:
                keys.append(key)
                items.append((desc, k))

    harvest()
    for sp in scrollers(c):
        for pct in (0, 20, 40, 60, 80, 100):
            try:
                sp.SetScrollPercent(-1, pct)
                time.sleep(0.12)
                harvest()
            except Exception:
                pass
        try:
            sp.SetScrollPercent(-1, 0)
        except Exception:
            pass
    for desc, k in items:
        lines.append('  ' * depth + desc)
    if not expand_sub:
        return
    for desc, k in items:
        try:
            ep = k.GetExpandCollapsePattern()
        except Exception:
            continue
        if ep is None:
            continue
        try:
            ep.Expand()
        except Exception:
            continue
        time.sleep(0.45)
        for w, c2 in new_popups(pid, seen_hwnds):
            seen_hwnds.add(w['hwnd'])
            lines.append('  ' * (depth + 1) + '## submenu %r hwnd=%d rect=%s'
                         % ((prop(k, 'Name') or '').strip(), w['hwnd'], w['rect']))
            map_popup(c2, lines, depth + 2, budget, pid, seen_hwnds, expand_sub=False)
        try:
            ep.Collapse()
        except Exception:
            pass
        time.sleep(0.2)


def collect_menu(c, d, lines, budget):
    """Legacy flat walker kept for cmd_ctx."""
    out = []
    collect_items(c, out, budget)
    for k in out:
        lines.append('  ' * d + item_desc(k))


def cmd_menus(argv):
    pid = resolve_pid(argv[0])
    out = argv[1]
    only = []
    expand = True
    for a in argv[2:]:
        if a.startswith('--only='):
            only = a.split('=', 1)[1].split(',')
        if a == '--no-sub':
            expand = False
    mw = main_window(pid)
    force_foreground(mw['hwnd'])
    root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    items = menu_bar_items(root)
    lines = ['## menu bar: %d top items: %s'
             % (len(items), ' '.join((prop(i, 'Name') or '').strip() for i in items))]
    for idx, it in enumerate(items):
        name = (prop(it, 'Name') or '').strip()
        if only and not any(n in (str(idx), name) for n in only):
            continue
        lines.append('')
        lines.append('# TOP[%d] %r %s' % (idx, name, line_of(it)))
        how = open_menu(it)
        lines.append('#   opened via %s' % how)
        if how == 'fail':
            continue
        seen = popup_ids(pid)
        roots = menu_popups(pid)
        if not roots:
            lines.append('#   !! no popup window with menu items found')
            close_menu()
            continue
        for w, c, cnt in roots:
            lines.append('  POPUP hwnd=%s cls=%r rect=%s menuitems=%d'
                         % (w['hwnd'], w['cls'], w['rect'], cnt))
            seen.add(w['hwnd'])
            map_popup(c, lines, 1, [6000], pid, seen, expand_sub=expand)
        close_menu()
        time.sleep(0.2)
    n = dump(out, '# menus pid=%d %r  (read-only: Expand/Esc only, never Invoke)'
             % (pid, mw['title']), lines)
    print('lines=%d -> %s' % (n, out))
    return 0


# --------------------------------------------------------------- project tree (Win32)
#
# The explorer pane is a real WinForms SysTreeView32.  Handles, child counts,
# expand state and row rectangles are all safe with plain SendMessage.  Its
# captions ARE readable too - but only with TVM_GETITEMW (0x113E) and a
# TVITEM *and* text buffer that both live inside Sysmac (see node_text).  The
# ANSI variant TVM_GETITEM (0x110C), and any local TVITEM whose pszText points
# into our own process, crash Sysmac (pitfalls.md #33).
#
# Measured 2026-11-06: node_text returned all 84 labels of
# 欧姆龙库程序V2.0.0.2_20250922 and Sysmac stayed up; treeview.py did the same on a
# 219-node project on 2026-10-30.  Before that, this file assumed "GDI tree, no
# text" and every sweep had to be labelled from screenshots.

TVM_GETITEMW = 0x113E           # TV_FIRST + 62 (the W variant; 0x110C is the A variant)
TVIF_TEXT = 0x0001
TVIF_HANDLE = 0x0004
TVIF_CHILDREN = 0x0040
TVM_EXPAND = 0x1102             # TV_FIRST + 2
TVE_EXPAND = 2
TVM_ENSUREVISIBLE = 0x1114      # TV_FIRST + 20  (NOT 0x1124 - that is a colour msg)
TVM_GETNEXTITEM = 0x110A        # TV_FIRST + 10
TVGN_ROOT = 0
TVGN_NEXT = 1
TVGN_CHILD = 4
TVGN_CARET = 9
TVM_SELECTITEM = 0x110B         # TV_FIRST + 11
TVM_GETCOUNT = 0x1105           # TV_FIRST + 5
TVM_GETITEMSTATE = 0x1127       # TV_FIRST + 39
TVIS_EXPANDED = 0x0020
TVIS_SELECTED = 0x0002          # set by a click even when the tree has no focus,
                                # and by TVM_SELECTITEM too (probe_select 2026-11-06)
TVM_GETITEMRECT = 0x1104        # TV_FIRST + 4
TVGN_FIRSTVISIBLE = 5           # CommCtrl.h: TV_FIRST-relative flags for TVM_GETNEXTITEM
TVGN_NEXTVISIBLE = 6
TVGN_LASTVISIBLE = 10
# !! 0x110D is TVM_SETITEMTEXT, NOT a rect message.  An earlier draft of this file
# !! used it as TVM_GETITEMRECT and sent it with a raw buffer address as TVITEM*;
# !! that is a write-path message against the target's own tree.  Never invent TVM_*
# !! ids - check them against CommCtrl.h (TV_FIRST = WM_USER + 100 = 0x1100).
PROCESS_VM = 0x0008 | 0x0010 | 0x0020 | 0x0400   # OPERATION | READ | WRITE | QUERY_INFORMATION
MEM_COMMIT_RESERVE = 0x1000 | 0x2000
PAGE_READWRITE = 0x04
MEM_RELEASE = 0x8000

k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = ctypes.c_void_p
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                               wt.DWORD, wt.DWORD]
k32.VirtualFreeEx.restype = wt.BOOL
k32.VirtualFreeEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
k32.WriteProcessMemory.restype = wt.BOOL
k32.WriteProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL
k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def tree_hwnd(pid):
    found = []
    top = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb1(hw, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(p))
        if p.value == pid:
            top.append(hw)
        return True

    u.EnumWindows(CB(cb1), 0)

    def cb2(hw, lp):
        c = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hw, c, 256)
        if 'SysTreeView32' in c.value:
            found.append(ctypes.cast(hw, ctypes.c_void_p).value)
        return True

    for hw in top:
        u.EnumChildWindows(hw, CB(cb2), 0)
    if not found:
        raise SystemExit('no SysTreeView32 in pid %s (project open?)' % pid)
    _THW[0] = found[0]
    return found[0]


def sm(hw, msg, wp=0, lp=0):
    return u.SendMessageW(wt.HWND(hw), msg, wp, lp)


def kids_of(hw, h):
    c = sm(hw, TVM_GETNEXTITEM, TVGN_CHILD, h)
    out = []
    while c:
        out.append(c)
        c = sm(hw, TVM_GETNEXTITEM, TVGN_NEXT, c)
        if len(out) > 500:
            break
    return out


def roots_of(hw):
    out = []
    r = sm(hw, TVM_GETNEXTITEM, TVGN_ROOT, 0)
    while r:
        out.append(r)
        r = sm(hw, TVM_GETNEXTITEM, TVGN_NEXT, r)
        if len(out) > 64:
            break
    return out


def node_at(hw, path):
    """HTREEITEM of a tree path (indices are 0-based, first level = root rows)."""
    h = 0
    for depth, i in enumerate(path):
        ks = roots_of(hw) if depth == 0 else kids_of(hw, h)
        if i >= len(ks):
            return 0
        h = ks[i]
    return h


def row_rect(pid, thw, hitem, f=1, ensure=True):
    """Ask Sysmac's own tree for one item's rect.  Returns (client RECT, screen
    point of its centre, TVM_ENSUREVISIBLE ret) or None.

    Contract (CommCtrl.h): wParam = fItemRect (0 label, 1 full row, 2 glyph),
    lParam = RECT* whose first HTREEITEM-sized field already holds the handle -
    comctl32 aliases them.  The buffer therefore has to live in the target.
    FAILS for items that are not realised rows (collapsed parent), which is how
    Sysmac's tree behaves until the parent is really expanded - see pitfall #33.
    """
    import struct
    hp = k32.OpenProcess(PROCESS_VM, False, pid)
    if not hp:
        return None
    try:
        addr = k32.VirtualAllocEx(hp, None, ctypes.c_size_t(32),
                                  MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not addr:
            return None
        buf = struct.pack('<Q', hitem) + b'\x00' * 8
        written = ctypes.c_size_t(0)
        if not k32.WriteProcessMemory(hp, ctypes.c_void_p(addr), buf, 16,
                                      ctypes.byref(written)):
            k32.VirtualFreeEx(hp, ctypes.c_void_p(addr), 0, MEM_RELEASE)
            return None
        eret = sm(thw, TVM_ENSUREVISIBLE, 0, hitem) if ensure else 1
        time.sleep(0.05)
        ok = sm(thw, TVM_GETITEMRECT, f, addr)
        raw = (ctypes.c_char * 16)()
        got = ctypes.c_size_t(0)
        ok2 = k32.ReadProcessMemory(hp, ctypes.c_void_p(addr), raw, 16, ctypes.byref(got))
        k32.VirtualFreeEx(hp, ctypes.c_void_p(addr), 0, MEM_RELEASE)
        if not (ok and ok2):
            return None
        left, top, right, bottom = struct.unpack('<iiii', bytes(raw))
        pt = wt.POINT((left + right) // 2, top + (bottom - top) // 2)
        u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
        u.ClientToScreen(wt.HWND(thw), ctypes.byref(pt))
        return ((left, top, right - left, bottom - top), (pt.x, pt.y), eret)
    finally:
        k32.CloseHandle(hp)


def remote_row_rect(pid, thw, hitem):
    """Screen centre + size of a realised tree row, or None (see row_rect)."""
    r = row_rect(pid, thw, hitem, f=1)
    if not r:
        return None
    (left, top, w, h), (cx, cy), _eret = r
    return (cx, cy, w, h)


class _TVITEMW(ctypes.Structure):
    """CommCtrl.h TVITEMW on x64: ctypes inserts the same padding the C compiler
    does (hItem/pszText are 8-aligned), so sizeof == 56."""
    _fields_ = [('mask', wt.UINT), ('hItem', ctypes.c_void_p),
                ('state', wt.UINT), ('stateMask', wt.UINT),
                ('pszText', ctypes.c_void_p), ('cchTextMax', ctypes.c_int),
                ('iImage', ctypes.c_int), ('iSelectedImage', ctypes.c_int),
                ('cChildren', ctypes.c_int), ('lParam', ctypes.c_ssize_t)]


_TEXT_BUF = [None]          # (pid, hp, item_addr, text_addr) - reused per run


def node_text(pid, thw, hitem):
    """Label of a tree item: (text, cChildren), or (None, None) if it failed.

    The only safe way to read a Sysmac tree caption - TVM_GETITEMW with BOTH the
    TVITEMW and the character buffer living inside Sysmac.  A local TVITEM whose
    pszText points at our own process, or the ANSI 0x110C variant, crashes the
    software (pitfalls.md #33); this shape was proven on 219 nodes (treeview.py,
    2026-10-30) and on all 84 nodes of the current library project (2026-11-06).

    The remote TVITEMW has to be read back as well: comctl32 writes cChildren
    into the remote struct, not into ours.
    """
    buf = _TEXT_BUF[0]
    if not buf or buf[0] != pid:
        hp = k32.OpenProcess(PROCESS_VM, False, pid)
        if not hp:
            return None, None
        item = k32.VirtualAllocEx(hp, None, ctypes.c_size_t(ctypes.sizeof(_TVITEMW)),
                                  MEM_COMMIT_RESERVE, PAGE_READWRITE)
        text = k32.VirtualAllocEx(hp, None, ctypes.c_size_t(4096),
                                  MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not item or not text:
            k32.CloseHandle(hp)
            return None, None
        buf = (pid, hp, item, text)
        _TEXT_BUF[0] = buf
    _pid, hp, item, text = buf
    t = _TVITEMW()
    t.mask = TVIF_TEXT | TVIF_HANDLE | TVIF_CHILDREN
    t.hItem = hitem
    t.pszText = text
    t.cchTextMax = 1000
    written = ctypes.c_size_t(0)
    if not k32.WriteProcessMemory(hp, ctypes.c_void_p(item), ctypes.byref(t),
                                  ctypes.sizeof(t), ctypes.byref(written)):
        return None, None
    sm(thw, TVM_GETITEMW, 0, item)
    raw = (ctypes.c_wchar * 1001)()
    if not k32.ReadProcessMemory(hp, ctypes.c_void_p(text), raw, 2000,
                                 ctypes.byref(written)):
        return None, None
    back = _TVITEMW()
    k32.ReadProcessMemory(hp, ctypes.c_void_p(item), ctypes.byref(back),
                          ctypes.sizeof(back), ctypes.byref(written))
    # Sysmac stores every caption space-padded (b'EtherCAT        '), so strip it.
    return raw.value.rstrip('\x00').rstrip(), back.cChildren


def cmd_treelabels(argv):
    """Dump the whole tree as `path  label  kids=N` - the naming step that used to
    need screenshots (the tree is GDI-drawn, so UIA gives no captions)."""
    pid = resolve_pid(argv[0])
    out = argv[1]
    thw = tree_hwnd(pid)
    lines = []

    def rec(h, pre, d):
        txt, kids = node_text(pid, thw, h)
        lines.append('%s%-12s %s%s' % ('  ' * d, '.'.join(map(str, pre)), txt,
                                       '  *' if kids else ''))
        for i, k in enumerate(kids_of(thw, h)):
            rec(k, pre + [i], d + 1)

    for i, r in enumerate(roots_of(thw)):
        rec(r, [i], 0)
    n = dump(out, '# treelabels pid=%d total=%s %r'
             % (pid, sm(thw, TVM_GETCOUNT, 0, 0), main_window(pid)['title']), lines)
    print('lines=%d -> %s' % (n, out))
    return 0


def cmd_tree(argv):
    pid = resolve_pid(argv[0])
    out = argv[1]
    expand = '--expand' in argv
    thw = tree_hwnd(pid)
    lines = ['## tree hwnd=%d total=%s' % (thw, sm(thw, TVM_GETCOUNT, 0, 0))]

    def rec(h, path, d):
        if d > 7 or len(lines) > 4000:
            return
        st = sm(thw, TVM_GETITEMSTATE, h, TVIS_EXPANDED)
        ks = kids_of(thw, h)
        sel = (h == sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0))
        lines.append('%s path=%s children=%d expanded_state=%s%s'
                     % ('  ' * d, '.'.join(str(i) for i in path) or '-', len(ks),
                        bool(st & TVIS_EXPANDED), ' CARET' if sel else ''))
        if expand and ks:
            sm(thw, TVM_EXPAND, TVE_EXPAND, h)
            time.sleep(0.03)
            ks = kids_of(thw, h)
        for i, k in enumerate(ks):
            rec(k, path + [i], d + 1)

    r = sm(thw, TVM_GETNEXTITEM, TVGN_ROOT, 0)
    i = 0
    while r:
        rec(r, [i], 0)
        r = sm(thw, TVM_GETNEXTITEM, TVGN_NEXT, r)
        i += 1
    n = dump(out, '# tree pid=%d' % pid, lines)
    print('lines=%d -> %s' % (n, out))
    return 0


SYSTEM_MENU_ITEMS = ('还原', '移动(M)', '大小(S)', '最小化', '最大化', '关闭')


def is_window_system_menu(ctrl):
    """True for the '#32768' popup VK_APPS produces when the tree does not own the
    keyboard focus: that is the frame's *system* menu, not a tree menu.

    tctxA.txt recorded it for roots 0 and 1 as if it were the node's menu
    ('APPS POPUP cls='#32768' ... MenuItem|还原 ... MenuItem|关闭'), so treectx now
    recognises and discards it instead of writing it out.
    """
    names = [prop(k, 'Name', '') for k in
             find_by_type(ctrl, ('MenuItemControl',), maxd=8)]
    return sum(1 for n in names if n in SYSTEM_MENU_ITEMS) >= 3


def post_context_menu(thw, x, y):
    """Ask the tree for its context menu through its own window procedure.

    WM_CONTEXTMENU (0x007B), wParam = the tree, lParam = screen point.  POSTED, not
    sent: Sysmac's menu is modal, so SendMessageW would block this process until the
    menu closes.

    MEASURED INEFFECTIVE (probe_ctx3, 2026-11-06): posting it opens nothing, not
    even for a node whose right-click menu works - Sysmac builds the menu in its
    mouse/keyboard handling, not in the window procedure.  Kept as a documented
    dead end so nobody spends another run on it.
    """
    lp = ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)
    try:
        return bool(u.PostMessageW(wt.HWND(thw), 0x007B, wt.HWND(thw), lp))
    except Exception:
        return False


def tree_has_focus(thw):
    """Is the SysTreeView32 the real keyboard focus of its thread?

    GetFocus() from here reads 0 (different thread), so the question has to be
    asked of GetGUIThreadInfo for the tree's own thread.  VK_APPS only yields a
    tree menu when this is True; otherwise it yields the window system menu.
    """
    class GTI(ctypes.Structure):
        _fields_ = [('cb', wt.UINT), ('threadId', wt.DWORD),
                    ('hwndActive', wt.HWND), ('hwndFocus', wt.HWND),
                    ('hwndCapture', wt.HWND), ('hwndMenuOwner', wt.HWND),
                    ('hwndMoveSize', wt.HWND), ('hwndCaret', wt.HWND),
                    ('rcCaret', wt.RECT)]

    tid = u.GetWindowThreadProcessId(wt.HWND(thw), None)
    g = GTI()
    g.cb = ctypes.sizeof(GTI)
    if not u.GetGUIThreadInfo(wt.DWORD(tid), ctypes.byref(g)):
        return None
    return int(g.hwndFocus or 0) == int(thw)


def cmd_treectx(argv):
    """Right-click a list of tree paths and record each context menu.

    Ancestors are opened with expand_node (caret + VK_RIGHT) and the target row is
    located with row_hit, which proves the coordinate: the selection is cleared,
    the modelled dot is clicked, and the row counts as hit only when the tree
    itself names that handle back (TVGN_CARET or TVIS_SELECTED - the caret alone
    reads 0 when the tree has no keyboard focus).  Every record prints the node's
    caption through node_text, which is also the safest way to confirm a path means
    what you think it means before trusting a menu sweep.

    --fit slides the Sysmac frame onto the screen first (see fit_on_screen); the
    original window rect is restored when the run ends.

    Menu retrieval is a ladder, because a single right-click silently fails on some
    rows:  right-click the modelled point  ->  right-click 80 px further along the
    same row (the first point can be the expander glyph)  ->  VK_APPS, and VK_APPS
    only when GetGUIThreadInfo says the tree owns the keyboard focus.  A '#32768'
    popup whose items are 还原/移动/大小/最小化/最大化/关闭 is the frame system menu
    and is never recorded as a node menu.  Section headers (single-number paths)
    skip the mouse entirely - clicking one collapses/expands the whole section.
    A node that answers nothing on every channel is reported as a node type with no
    context menu, which probe_ctx3 verified for 0, 0.3 and 0.4.
    """
    pid = resolve_pid(argv[0])
    out = argv[1]
    paths = [p for p in argv[2:] if not p.startswith('--')]
    thw = tree_hwnd(pid)
    mw = main_window(pid)
    force_foreground(mw['hwnd'])
    old_rect = None
    if '--fit' in argv:
        old_rect, new = fit_on_screen(mw['hwnd'])
        note_fit = 'window %s -> %s' % (old_rect, new)
    else:
        note_fit = 'window left where it was (pass --fit to slide it on screen)'
    lines = []
    for ps in paths:
        path = [int(x) for x in ps.split('.') if x != '']
        anc = []
        for k in range(1, len(path)):
            a = node_at(thw, path[:k])
            if a:
                anc.append('%s=%s' % ('.'.join(map(str, path[:k])),
                                      expand_node(pid, thw, mw, a)))
        h = node_at(thw, path)
        lines.append('')
        nm = node_text(pid, thw, h)[0] if h else None
        if not h:
            lines.append('# PATH %s !! missing (ancestors %s)' % (ps, ' '.join(anc) or '-'))
            continue
        if len(path) == 1:
            # Section-header (root) rows are not clickable for this purpose: a
            # click anywhere on the row toggles the whole section (probe_ctx3:
            # root 0's TVM_GETCOUNT changed under every click), so row_hit can
            # never prove a root and the layout keeps moving under the sweep.
            # Roots are asked for their menu with the keyboard only.
            pt = row_xy(pid, thw, h)
            if not pt:
                lines.append('# PATH %s !! row not realised (state=0x%X kids=%d)'
                             % (ps, sm(thw, TVM_GETITEMSTATE, h, 0xFFFFFFFF) & 0xFFFFFFFF,
                                len(kids_of(thw, h))))
                continue
            lines.append('# PATH %s name=%r h=%d kids=%d (section header: keyboard '
                         'only, a click would toggle the section)'
                         % (ps, nm, h, len(kids_of(thw, h))))
        else:
            pt = row_hit(pid, thw, mw, h, path)
            if not pt:
                lines.append('# PATH %s name=%r !! never hit - the tree refused to '
                             'name it (state=0x%X kids=%d ancestors %s)'
                             % (ps, nm,
                                sm(thw, TVM_GETITEMSTATE, h, 0xFFFFFFFF) & 0xFFFFFFFF,
                                len(kids_of(thw, h)), ' '.join(anc) or '-'))
                continue
            x, y = pt
            rr = row_rect(pid, thw, h, ensure=False)
            # TVM_GETITEMRECT(f=1) is in CLIENT coords and the tree is horizontally
            # scrolled, so its `left` is not the visual indent - it can even go
            # negative after --fit.  Print it as what it is.
            lines.append('# PATH %s name=%r hit (%d,%d) h=%d row=%s kids=%d ancestors: %s'
                         % (ps, nm, x, y, h, rr[0] if rr else '?',
                            len(kids_of(thw, h)), ' '.join(anc) or '-'))

        def capture(tag):
            seen = popup_ids(pid)
            got = []
            sysmenu = False
            for pw, c, cnt in menu_popups(pid):
                if pw['cls'] == '#32768' and is_window_system_menu(c):
                    sysmenu = True       # frame system menu, not a node menu
                    continue
                got.append('  %s POPUP hwnd=%d cls=%r rect=%s menuitems=%d'
                           % (tag, pw['hwnd'], pw['cls'], pw['rect'], cnt))
                map_popup(c, got, 1, [4000], pid, seen, expand_sub=True)
            return got, sysmenu

        cl, ct, cr_, cb = pane_bounds(thw)
        got, sysmenu = [], False
        if len(path) > 1:
            force_foreground(mw['hwnd'])
            right_click(x, y)
            got, sysmenu = capture('RCLICK')
            if not got:
                close_menu()
                # the modelled centre can fall on the expander glyph of an
                # indented row; a click there selects the node but never opens
                # its menu, so retry further along the same row.
                xr = min(x + 80, cr_ - 30)
                if xr > x and on_screen(thw, xr, y):
                    right_click(xr, y)
                    got, sysmenu = capture('RCLICK2')
                    if not got:
                        close_menu()
        if not got:
            # probe_ctx3 (2026-11-06) measured that PostMessage WM_CONTEXTMENU
            # NEVER opens a Sysmac tree menu - not even for a node whose
            # right-click works - so it is not part of the ladder any more; the
            # function is kept for reference only.  Last resort is the apps key.
            # It reaches the tree only when the tree owns the keyboard focus, and
            # on a menu-less node it yields the frame system menu, which
            # capture() discards (see is_window_system_menu).
            if len(path) > 1 and tree_has_focus(thw) is not True:
                left_click(x, y)
                time.sleep(0.3)
            sm(thw, TVM_SELECTITEM, TVGN_CARET, h)
            time.sleep(0.2)
            focused = tree_has_focus(thw)
            if focused is False:
                lines.append('#   !! tree does not own the keyboard focus '
                             '(apps-key would open the window system menu)')
            elif caret_of(thw) == h or selected(thw, h):
                key(0x5D)                         # VK_APPS
                time.sleep(0.15)
                key(0x5D, up=True)
                time.sleep(0.9)
                got, sysmenu = capture('APPS')
            else:
                lines.append('#   !! caret would not move to the node, apps-key skipped')
            if not got and sysmenu:
                lines.append('#   !! only the window system menu (#32768) appeared')
        if not got:
            lines.append('#   !! NO CONTEXT MENU for this node type (right-click at '
                         'two x-offsets and VK_APPS with the tree focused all opened '
                         'nothing - probe_ctx3 verified the same for 0 / 0.3 / 0.4)')
            try:
                from PIL import ImageGrab
                d = os.path.join(os.path.dirname(os.path.abspath(out)), 'shots')
                if not os.path.isdir(d):
                    os.makedirs(d)
                fp = os.path.join(d, 'miss_%s.png' % ps.replace('.', '_'))
                ImageGrab.grab(all_screens=True).save(fp)   # 全虚拟屏，不写死分辨率
                lines.append('#   shot -> %s' % fp)
            except Exception as e:
                lines.append('#   shot failed: %s' % type(e).__name__)
        lines.extend(got)
        close_menu()
    if old_rect:
        restore_rect(mw['hwnd'], old_rect)
    n = dump(out, '# treectx pid=%d paths=%s\n# %s' % (pid, paths, note_fit), lines)
    print('lines=%d -> %s' % (n, out))
    return 0


_THW = [None]           # last tree hwnd seen, so wheel() can find the pane
_MW = [None]            # last main-window hwnd seen, so wheel() can raise it


def wheel(dy=-3, x=None, y=None):
    """Mouse wheel over the tree (negative dy scrolls down).

    The wheel goes to whatever window is under the cursor, so the cursor has to be
    parked on a point that really belongs to the tree.  Measured 2026-11-06
    (probe_zorder): WindowFromPoint(131,855) - the middle of the tree's client
    rect - returns an explorer.exe hwnd cls='XamlExplorerHostIslandWindow',
    NOT the tree, and wheeling there moves nothing; (131,471) and (131,705) do
    return SysTreeView32.  So the point is chosen by hit-testing candidates, and
    if none of them belongs to the tree the wheel is not sent at all (silently
    scrolling elsewhere is what made every node under root 1 unreachable)."""
    if x is None:
        if not _THW[0]:
            return
        if _MW[0]:
            force_foreground(_MW[0])
            time.sleep(0.2)
        pt = wheel_point(_THW[0])
        if not pt:
            return
        x, y = pt
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u.mouse_event(0x0800, 0, 0, 120 * dy, 0)
    time.sleep(0.12)


def on_screen(thw, x, y):
    """True when the top-level window under (x, y) is this tree."""
    r = wt.POINT(int(x), int(y))
    hw = u.WindowFromPoint(r)
    if not hw:
        return False
    root = u.GetAncestor(hw, 2)          # GA_ROOT
    return (ctypes.cast(hw, ctypes.c_void_p).value == thw
            or (root and ctypes.cast(root, ctypes.c_void_p).value == _MW[0]
                and 'SysTreeView32' in _class_of(hw)))


def _class_of(hw):
    c = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(wt.HWND(hw), c, 256)
    return c.value


def wheel_point(thw):
    """A point inside the tree that WindowFromPoint confirms, or None."""
    cl, ct, cr_, cb = pane_bounds(thw)
    for y in (ct + ROW_H // 2 + ROW_H, ct + ROW_H, (ct + cb) // 2, cb - ROW_H,
              ct + ROW_H * 3):
        for x in ((cl + cr_) // 2, cl + 40):
            if ct <= y <= cb and on_screen(thw, x, y):
                return x, y
    return None


def vis_items(thw, cap=100):
    """The handles currently realised as on-screen rows, top to bottom.

    Sysmac virtualises the tree, so this chain is the only proof a row exists:
    TVM_GETITEMRECT for anything outside it returns a recycled slot (probe_vis
    measured client y=-101 for path 1.0.1.3).  Inside it the rects are strictly
    monotonic (+26 px) and fully inside the pane (measured 2026-11-06)."""
    out = []
    h = sm(thw, TVM_GETNEXTITEM, TVGN_FIRSTVISIBLE, 0)
    first = h
    while h and len(out) < cap:
        out.append(h)
        h = sm(thw, TVM_GETNEXTITEM, TVGN_NEXTVISIBLE, h)
        if h == first:
            break
    return out


def dfs_order(thw, cap=4000):
    """Display order of every item whose ancestors are expanded."""
    out = []

    def rec(h):
        if len(out) >= cap:
            return
        out.append(h)
        if sm(thw, TVM_GETITEMSTATE, h, TVIS_EXPANDED) & TVIS_EXPANDED:
            for k in kids_of(thw, h):
                rec(k)

    for r in roots_of(thw):
        rec(r)
    return out


_EXPANDED_STAMP = [0]           # bumped by expand_node; invalidates the order cache
_ORDER_CACHE = {}


def order_map(thw):
    """handle -> display ordinal, cached until the next expansion (dfs_order over
    a few thousand items costs ~1 s of SendMessage, and treerows needs it per row)."""
    key = (thw, _EXPANDED_STAMP[0])
    if _ORDER_CACHE.get('key') != key:
        _ORDER_CACHE['key'] = key
        _ORDER_CACHE['map'] = {it: i for i, it in enumerate(dfs_order(thw))}
    return _ORDER_CACHE['map']


def scroll_to(pid, thw, h, tries=30):
    """Wheel until `h` is inside the realised band; returns that band.

    The band, NOT the FIRSTVISIBLE chain, is what "on screen" means: the chain
    runs to the document end (probe_geom2 measured 61 entries while SB_VERT only
    pages 30 rows), so an older draft that compared against vis_items computed
    `bot` as the last item of the document, always thought the target was above
    the view, and oscillated - hitcheck 2026-11-06: every node under root 1 (which
    needs real scrolling) failed, every node in the first screenful hit.
    Distance and direction come from display ordinals; one wheel notch moves
    exactly 3 rows (probe_geom2: head ordinal 0 -> 9 after three notches)."""
    order = order_map(thw)
    if h not in order:
        return []
    for _ in range(tries):
        band = realised_band(pid, thw)
        if not band:
            return band
        if any(b[0] == h for b in band):
            return band
        top_ord = order.get(band[0][0])
        if top_ord is None:
            return band
        delta = order[h] - (top_ord + len(band) // 2)   # rows: put h mid-band
        notches = int(round(delta / float(ROWS_PER_NOTCH))) or (1 if delta > 0 else -1)
        wheel(dy=-max(-10, min(10, notches)))
    return realised_band(pid, thw)


def caret_of(thw):
    return sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0)


# Tree row geometry. 26 px / 3 rows-per-notch are the 125% DPI, 1920x1080 baseline
# measured on the author's machine. Row height SCALES WITH DISPLAY DPI, so the
# authoritative value is measured live from the tree (see row_height); these are
# only the fallback / coarse-offset defaults. Override without editing code via:
#   SS_ROW_H          (px per row; default 26)
#   SS_ROWS_PER_NOTCH (rows per wheel notch; default 3, a Windows setting)
# If you change DPI / resolution / theme and hits drift, recalibrate or set these.
ROW_H = int(os.environ.get('SS_ROW_H', '26'))
ROWS_PER_NOTCH = int(os.environ.get('SS_ROWS_PER_NOTCH', '3'))

_ROW_H_CACHE = {}


def row_height(pid, thw):
    """Live tree row pitch in screen px, measured from realised rows.

    Prefers the top-to-top distance of two adjacent visible rows (the exact step
    realised_band models); falls back to the first row's own rect height, then to
    the SS_ROW_H env default. Cached per tree handle - row height does not
    change while a tree lives, and re-measuring per call would add the very
    OpenProcess/VirtualAllocEx round trips realised_band warns about."""
    if thw in _ROW_H_CACHE:
        return _ROW_H_CACHE[thw]
    val = None
    h = sm(thw, TVM_GETNEXTITEM, TVGN_FIRSTVISIBLE, 0)
    if h:
        rr = row_rect(pid, thw, h, ensure=False)
        if rr and rr[0][3] > 0:
            val = rr[0][3]
            nxt = sm(thw, TVM_GETNEXTITEM, TVGN_NEXTVISIBLE, h)
            if nxt and nxt != h:
                rr2 = row_rect(pid, thw, nxt, ensure=False)
                if rr2 and rr2[0][1] > rr[0][1]:
                    val = rr2[0][1] - rr[0][1]      # adjacent-row pitch wins
    if not val or val <= 0:
        val = ROW_H
    _ROW_H_CACHE[thw] = val
    return val


def client_screen_rect(thw):
    """The tree's client area in screen px.

    Measured 2026-11-06 (probe_geom2): window rect (18,458)-(265,1274) but client
    rect (18,458)-(244,1253) - the 21 px strip below is the horizontal scrollbar
    (SB_HORZ nMax=307 nPage=226 says it is really there).  A click at the last
    modelled row y=1251 landed in that strip: focus left the tree (hwndFocus
    2754256 -> 0) and nothing was selected.  Anything that decides "is this row
    hittable" must use the client rect, not the window rect."""
    cr = wt.RECT()
    u.GetClientRect(wt.HWND(thw), ctypes.byref(cr))
    tl, br = wt.POINT(cr.left, cr.top), wt.POINT(cr.right, cr.bottom)
    u.ClientToScreen(wt.HWND(thw), ctypes.byref(tl))
    u.ClientToScreen(wt.HWND(thw), ctypes.byref(br))
    return (tl.x, tl.y, br.x, br.y)


def pane_bounds(thw):
    """Usable pane rect in screen px: the tree's client rect, cut off at the bottom
    of the monitor.

    Measured 2026-11-06 (probe_zorder): Sysmac's main window is (0,253)-(1938,1351)
    on a 1920x1080 display, so the tree's client bottom (1253) is 173 px BELOW the
    screen.  Rows down there exist, have real rects, and are in the FIRSTVISIBLE
    chain - they simply cannot be clicked, because SetCursorPos clamps to the
    screen edge.  Any "is this row hittable" test must use this, not the client
    rect (probe_sweep: rows past ordinal ~22 never answered)."""
    cl, ct, cr_, cb = client_screen_rect(thw)
    return (cl, ct, cr_, min(cb, u.GetSystemMetrics(1) - 6))     # SM_CYSCREEN


def realised_band(pid, thw, max_rows=40):
    """[(handle, screen_y, rect_or_None)] for the rows currently inside the pane.

    The FIRSTVISIBLE/NEXTVISIBLE chain runs to the document end, so it is NOT the
    screen: only the first `ceil(pane_height / 26)` entries are hittable, and
    their rects are strictly +26 px apart (probe_vis measured 30 rows monotonic
    inside the pane; everything below came back as document coords past y=2600).
    One row_rect for the top row + TVM_GETNEXTITEM steps is therefore enough;
    the first draft here called row_rect per handle (~200 OpenProcess/VirtualAllocEx
    round trips = 3 s per call) and stalled a whole treectx run.

    A row counts as hittable only while its centre is a full ROW_H//2 inside the
    CLIENT rect (see client_screen_rect): the bottom row of the window rect is a
    clipped row whose click goes to the horizontal scrollbar instead of the tree.
    """
    h = sm(thw, TVM_GETNEXTITEM, TVGN_FIRSTVISIBLE, 0)
    if not h:
        return []
    rr = row_rect(pid, thw, h, ensure=False)
    if not rr:
        return []
    cl, ct, cr_, cb = pane_bounds(thw)
    y0 = rr[1][1]
    if not ct - 2 <= y0 <= cb + 2:
        return []
    out = [(h, y0, rr)]
    cur = h
    while len(out) < max_rows:
        nxt = sm(thw, TVM_GETNEXTITEM, TVGN_NEXTVISIBLE, cur)
        if not nxt or nxt == cur:
            break
        cur = nxt
        y = y0 + ROW_H * len(out)
        if y > cb - ROW_H // 2:
            break
        out.append((cur, y, None))
    return out


def row_visible(pid, thw, h, tries=20):
    """Scroll until the item is inside the realised band, then return its rect.
    Only guarantees the row is on screen - use row_point() when the click itself
    has to be proven."""
    for _ in range(tries):
        band = realised_band(pid, thw)
        for i, (hh, y, _rr) in enumerate(band):
            if hh == h:
                rr = row_rect(pid, thw, h, ensure=False)
                if rr:
                    return rr
                break
        if h not in vis_items(thw, cap=400):
            return None          # collapsed ancestor: no scrolling will help
        scroll_to(pid, thw, h, tries=1)
    return None


def row_xy(pid, thw, h, tries=14):
    """Modelled screen point for an item: y = band_top + 26 * (ordinal - ordinal
    of the band's top row), scrolling it into view first via scroll_to (which
    picks its direction from the ordinals; an earlier draft here scrolled *down*
    for targets above the view and so could never reach them - probe_hitdbg
    measured order[h]=16 against a band starting at 31).
    Returns (x, y) or None; x is the item's own label centre, clamped into the pane.
    A y only counts once WindowFromPoint says the dot really lands on this tree:
    probe_scroll (2026-11-06) measured rows y=991 and y=1017 inside the client rect
    yet owned by another window (explorer.exe's XamlExplorerHostIslandWindow), and a
    click there selects nothing.  When the target sits on such a row it is scrolled
    to the nearest verified slot instead."""
    order = order_map(thw)
    if h not in order:
        return None
    cl, ct, cr_, cb = pane_bounds(thw)
    rr = row_rect(pid, thw, h, ensure=False)
    x = rr[1][0] if rr else cl + 120
    x = max(cl + 60, min(x, cr_ - 30))
    for _ in range(tries):
        band = realised_band(pid, thw)
        b0 = order.get(band[0][0]) if band else None
        if b0 is not None:
            d = order[h] - b0
            if 0 <= d < len(band):
                y = band[d][1]
                if on_screen(thw, x, y):
                    return x, y
                slot = next((i for i, b in enumerate(band) if on_screen(thw, x, b[1])), None)
                if slot is None:
                    return None
                need = d - slot          # rows to move the view so h lands on slot
                notches = int(round(need / float(ROWS_PER_NOTCH))) or (1 if need > 0 else -1)
                wheel(dy=-notches)
                continue
        scroll_to(pid, thw, h, tries=1)   # direction comes from the ordinals
    return None


def selected(thw, h):
    return bool(sm(thw, TVM_GETITEMSTATE, h, TVIS_SELECTED) & TVIS_SELECTED)


def row_hit(pid, thw, mw, h, path=None, tries=8):
    """Proven screen point for an item's row, or None.

    Geometry is measured, not guessed.  probe_sweep (2026-11-06, 30 rows, one click
    per row) hit the predicted node on rows 0..19 with y = client_top+13 + 26*i
    exactly - after the Alt-tap bug in force_foreground was fixed (see there).

    Proof = "the tree itself names the row we hit": after clearing the selection
    (TVM_SELECTITEM TVGN_CARET 0) a click leaves either the caret (TVGN_CARET) or
    TVIS_SELECTED on the item under the dot.  The caret alone was not enough -
    it reads 0 when the tree has no keyboard focus - so the selected bit is
    checked too, and a miss is located by scanning the realised band for whichever
    row did get selected; that handle's display ordinal says exactly how many rows
    off we are, so one correction step converges.

    (That "caret reads 0" is about a CLICK selecting the row.  Selecting by message
    is not like this: probe_select measured TVM_SELECTITEM(TVGN_CARET, h) setting
    the caret AND TVIS_SELECTED, deselecting the previous row and scrolling the row
    in, even with the window minimised.  Message-select is reliable; do not
    "verify" it with a click and conclude from the click's behaviour.)

    Root (section header) rows are clicked like any other row now: they really do
    take the selection (probe_sweep: y=471 selected root 0), but the click also
    toggles their expander, so the item count is compared before/after and the
    ancestors are re-opened with expand_node whenever a section got collapsed.
    """
    order = order_map(thw)
    if h not in order:
        return None
    cl, ct, cr_, cb = pane_bounds(thw)
    rr = row_rect(pid, thw, h, ensure=False)
    x = rr[1][0] if rr else cl + 120
    x = max(cl + 60, min(x, cr_ - 30))
    for _ in range(tries):
        pt = row_xy(pid, thw, h)
        if not pt:
            return None
        y = pt[1]
        for _k in range(4):
            band = realised_band(pid, thw)
            n0 = sm(thw, TVM_GETCOUNT, 0, 0)
            sm(thw, TVM_SELECTITEM, TVGN_CARET, 0)
            time.sleep(0.1)
            force_foreground(mw['hwnd'])
            left_click(x, y)
            time.sleep(0.3)
            got = caret_of(thw)
            if got == h or selected(thw, h):
                return x, y
            if sm(thw, TVM_GETCOUNT, 0, 0) != n0:
                # the dot toggled a section header - put the tree back and retry
                for k in range(1, len(path or []) + 1):
                    a = node_at(thw, (path or [])[:k])
                    if a:
                        expand_node(pid, thw, mw, a)
                break
            if not got:
                got = next((bh for bh, _yy, _rr in band
                            if bh != h and selected(thw, bh)), 0)
            if not got or got not in order:
                break                  # clicked blank space: item is not on screen
            d = order[h] - order[got]
            if d == 0:
                break
            y = max(ct + ROW_H // 2, min(y + ROW_H * d, cb - ROW_H // 2))
        # no blind scroll here: the next row_xy() moves the view by ordinals,
        # which knows whether the target is above or below
    return None


def tree_focus(pid, thw, mw):
    """Give SysTreeView32 real keyboard focus: foreground, then one click on the
    caret row.  GetFocus() from here reads 0 (different thread), so focus is
    proven by the keys working, not queried."""
    force_foreground(mw['hwnd'])
    h = sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0) or (roots_of(thw) or [0])[0]
    rr = row_rect(pid, thw, h, ensure=True)
    if rr:
        left_click(rr[1][0], rr[1][1])
        time.sleep(0.35)
    return rr


def expand_node(pid, thw, mw, h, tries=3):
    """Expand one tree node: put the caret on it with TVM_SELECTITEM, then send a
    real VK_RIGHT.  Measured 2026-11-06 (probe_expand5): 9/10 collapsed nodes at
    depth 1 and 2 opened this way, coordinate-free.

    Why not the other routes:
      * TVM_EXPAND - returns 0, TVIS_EXPANDED never set (nothing happens).
      * clicking the +/- glyph - the hit point is not a stable offset: on child
        rows client x=52 opened 0.3 while x=54 did nothing to 0.4, and a sweep
        only looked decisive because hover time grew with each try
        (probe_expand3/4).  Kept below as a last-resort fallback.
      * UIA DoDefaultAction - no UIA row lines up with the TVM row rect
        ('no UIA row at that rect', probe_expand3 C).
    Never collapses: refuses when the flag is already on.
    """
    if sm(thw, TVM_GETITEMSTATE, h, TVIS_EXPANDED) & TVIS_EXPANDED:
        return 'expanded'
    # row_xy, not row_visible: a collapsed node is often scrolled out of the
    # visible chain too, and row_visible bails on that instead of scrolling
    pt = row_xy(pid, thw, h)
    if not pt:
        return 'no row'
    _x, cy = pt
    rr = row_rect(pid, thw, h, ensure=False)
    if not rr:
        return 'no rect'
    (l, t, w, hh), (cx, cy), _e = rr
    for attempt in range(tries):
        force_foreground(mw['hwnd'])
        left_click(cx, cy)                    # focus the tree, harmless select
        sm(thw, TVM_SELECTITEM, TVGN_CARET, h)
        time.sleep(0.25)
        key(0x27)                             # VK_RIGHT
        time.sleep(0.12)
        key(0x27, up=True)
        time.sleep(0.6)
        if sm(thw, TVM_GETITEMSTATE, h, TVIS_EXPANDED) & TVIS_EXPANDED:
            _EXPANDED_STAMP[0] += 1
            return 'key' if attempt == 0 else 'key(try %d)' % (attempt + 1)
        pt = row_xy(pid, thw, h)
        if pt:
            cy = pt[1]
    # fallback: sweep the indent band for the +/- glyph
    full = row_rect(pid, thw, h, f=0, ensure=False)
    if full:
        left = full[1][0] - full[0][2] // 2
        for dx in (32, 24, 40, 16, 48):
            left_click(left + dx, cy)
            time.sleep(0.5)
            if sm(thw, TVM_GETITEMSTATE, h, TVIS_EXPANDED) & TVIS_EXPANDED:
                _EXPANDED_STAMP[0] += 1
                return 'click+%d' % dx
    return 'failed'


def cmd_treerows(argv):
    """Walk the live tree, expanding with real clicks, and record every row.

    Captions are NOT obtainable: the tree is GDI-drawn (GDISolutionView), and
    UIA + LegacyIAccessible give rect/role/expand-action but empty Name for all
    rows (measured 2026-11-06).  So this records what IS observable - path,
    indent, label width, child count - which `tree_map.py` then names by
    aligning to the .oem entity tree (order + counts + label width).
    """
    pid = resolve_pid(argv[0])
    out = argv[1]
    max_nodes = int(next((a.split('=')[1] for a in argv if a.startswith('--max=')), 400))
    max_depth = int(next((a.split('=')[1] for a in argv if a.startswith('--depth=')), 6))
    thw = tree_hwnd(pid)
    mw = main_window(pid)
    force_foreground(mw['hwnd'])
    lines = []
    seen = [0]

    def rec(h, path, d):
        if seen[0] >= max_nodes or len(lines) > 4000:
            return
        seen[0] += 1
        kids = kids_of(thw, h)
        rr = row_visible(pid, thw, h)
        if not rr:
            lines.append('%s path=%-10s !! not a realised row (kids=%d)'
                         % ('  ' * d, '.'.join(map(str, path)), len(kids)))
            return
        (l, t, w, hh), (cx, cy), _e = rr
        lines.append('%s path=%-10s kids=%-3d indent=%-3d labelw=%-4d row=(%d,%d %dx%d) screen=(%d,%d)'
                     % ('  ' * d, '.'.join(map(str, path)), len(kids), l, w, l, t, w, hh, cx, cy))
        if kids and d < max_depth:
            expand_node(pid, thw, mw, h)
            kids = kids_of(thw, h)
            for i, k in enumerate(kids):
                rec(k, path + [i], d + 1)

    for i, r in enumerate(roots_of(thw)):
        rec(r, [i], 0)
    n = dump(out, '# treerows pid=%d nodes=%d (GDI tree: no captions, see tree_map.py)'
             % (pid, seen[0]), lines)
    print('lines=%d -> %s' % (n, out))
    return 0


def cmd_ctx(argv):
    pid = int(argv[0]) if argv[0].isdigit() else resolve_pid(argv[0])
    x, y, out = int(argv[1]), int(argv[2]), argv[3]
    label = argv[4] if len(argv) > 4 else ''
    mw = main_window(pid)
    force_foreground(mw['hwnd'])
    right_click(x, y)
    lines = ['## ctx at %d,%d %s' % (x, y, label)]
    for w, c, cnt in menu_popups(pid):
        lines.append('POPUP hwnd=%d cls=%r rect=%s menuitems=%d' %
                     (w['hwnd'], w['cls'], w['rect'], cnt))
        collect_menu(c, 1, lines, [2000])
    for c in find_by_type(auto.ControlFromHandle(wt.HWND(mw['hwnd'])),
                          ('MenuControl',), maxd=10):
        lines.append('INLINE MENU ' + line_of(c))
        collect_menu(c, 1, lines, [2000])
    close_menu()
    n = dump(out, '# ctx pid=%d label=%r' % (pid, label), lines)
    print('lines=%d -> %s' % (n, out))
    return 0


def doc_panes(root):
    """The open editors: PaneControl cls='DocumentWindow' (measured 2026-10-31,
    Name = the document name) plus the TabItem strips that hold their tabs.
    Keyed by (Name, rect) so a re-open of the same document is recognisable."""
    out = {}
    for c in find_by_type(root, ('PaneControl', 'TabControl', 'TabItemControl'), maxd=24):
        cn = prop(c, 'ClassName') or ''
        ct = prop(c, 'ControlTypeName') or ''
        if cn != 'DocumentWindow' and ct != 'TabItemControl':
            continue
        r = prop(c, 'BoundingRectangle')
        try:
            geo = (r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception:
            geo = (0, 0, 0, 0)
        out['%s|%s' % (prop(c, 'Name') or '', ct)] = (c, geo)
    return out


def find_doc(hwnd, name):
    """The DocumentWindow pane whose Name is `name` (exact, else contains)."""
    r = auto.ControlFromHandle(wt.HWND(hwnd))
    exact = loose = None
    for c in find_by_type(r, ('PaneControl',), maxd=24):
        if (prop(c, 'ClassName') or '') != 'DocumentWindow':
            continue
        nm = prop(c, 'Name') or ''
        if nm == name:
            exact = c
            break
        if name in nm or nm in name:
            loose = loose or c
    return exact or loose


def close_button(pane):
    for c in find_by_type(pane, ('ButtonControl',), maxd=6):
        if (prop(c, 'AutomationId') or '') == 'closeButton':
            return c
    return None


def close_document(hwnd, name, tries=2):
    """Close one editor through the `closeButton` inside its DocumentWindow pane.

    Re-rooted by Name on every attempt (the pane's Name IS the document name -
    open01.txt), because UIA references captured before another tab closed go stale.
    Only that button is touched: no keyboard, no menu - an editor this command
    opened and never typed in has nothing to save.

    Returns one of: closed / closed(click) / no pane / no button / invoke failed /
    still open.  'closed' means the pane is gone after InvokePattern; if Invoke is
    refused the fallback is a real click on the button's own rect (the window is
    already foreground here), and that is reported separately so the measurement
    stays honest.
    """
    pane = find_doc(hwnd, name)
    if not pane:
        return 'no pane'
    btn = close_button(pane)
    if not btn:
        return 'no button'
    for _ in range(tries):
        try:
            btn.Invoke()
        except Exception:
            r = prop(btn, 'BoundingRectangle')
            try:
                cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            except Exception:
                return 'invoke failed'
            force_foreground(hwnd)
            left_click(cx, cy)
            time.sleep(1.2)
            if not find_doc(hwnd, name):
                return 'closed(click)'
            return 'invoke failed'
        time.sleep(1.2)
        pane = find_doc(hwnd, name)
        if not pane:
            return 'closed'
        btn = close_button(pane) or btn
    return 'still open'


def expand_inside(ctrl, opt, lines, tag, limit=8):
    """Expand every ExpandCollapse area of one open page, then re-walk it.

    `open` without this flag only ever sees the collapsed shape: in ST/LD the
    variable declaration table hides behind an Expander whose header Text is
    literally '变量', so a page can look structurally complete while the half the
    user cares about is not realized in UIA at all.  Expand() is view state - it
    does not type, select or edit anything, so the page stays "unmodified" and
    close_document still gets no save prompt (measured, pitfalls §58).
    """
    hosts, stack = [], [(ctrl, 0)]
    seen = 0
    while stack:
        c, d = stack.pop()
        if d > 14 or len(hosts) >= limit or seen >= 2500:
            continue
        seen += 1
        try:
            ks = c.GetChildren()
        except Exception:
            ks = []
        for k in ks:
            if 'ExpandCollapse' in pats(k):
                hosts.append(k)
            stack.append((k, d + 1))
    for c in hosts:
        head = line_of(c, False)
        try:
            c.GetExpandCollapsePattern().Expand()
            lines.append('      expand %-70s ok' % head[:70])
        except Exception as e:
            lines.append('      expand %-70s FAILED %s'
                         % (head[:70], e.__class__.__name__))
        time.sleep(0.8)
    if hosts:
        lines.append('   @@ %s  [after Expand x%d]' % (tag, len(hosts)))
        walk(ctrl, 0, opt, lines)
    return len(hosts)


def cmd_open(argv):
    """Open editors by tree path and dump what they contain.

    ss_uimap.py open <pid|auto> <out> 1.0.2.3 0.0 1.1.0 ... [--fit] [--depth N]
                                      [--all] [--settle S] [--pat] [--expand]

    Opening is the one tree action that genuinely needs real input: the caret goes
    there by message (TVM_SELECTITEM), but the page only opens on a REAL Enter with
    the tree owning keyboard focus (project-tree.md §3.1/§3.4 - SendMessage of
    VK_RETURN does nothing).  So each path is: expand ancestors (expand_node) ->
    message-select -> click the row (this is what hands focus to the tree; the row
    is already selected, so one click cannot start a rename) -> VK_RETURN down+up ->
    poll the document strip for a new DocumentWindow/TabItem.

    Read-only by design: it never touches anything inside the editor and never
    types into the page.  `--close` then shuts each editor it opened through its own
    `closeButton` (InvokePattern, no keyboard), which is what makes a whole sweep
    re-runnable - measured behaviour of closing an unmodified editor is recorded in
    the log line, not assumed.  Without `--close` whatever opened stays open.

    --fit slides the window on screen first and restores it at the end; --depth caps
    the per-document walk (default 14), --all keeps offscreen subtrees, --pat lists
    each element's UIA patterns, --expand opens every folded area before re-walking.
    """
    pid = resolve_pid(argv[0])
    out = argv[1]
    paths = [p for p in argv[2:] if not p.startswith('--')]
    opt = dict(all='--all' in argv, depth=14, max_lines=40000, pat='--pat' in argv)
    for a in argv:
        if a.startswith('--depth='):
            opt['depth'] = int(a.split('=', 1)[1])
    settle = 8.0
    for a in argv:
        if a.startswith('--settle='):
            settle = float(a.split('=', 1)[1])
    mw = main_window(pid)
    thw = tree_hwnd(pid)
    old_rect = None
    note_fit = 'window left where it was (pass --fit to slide it on screen)'
    if '--fit' in argv:
        old_rect, new = fit_on_screen(mw['hwnd'])
        note_fit = 'window %s -> %s' % (old_rect, new)
    lines = []
    try:
        force_foreground(mw['hwnd'])
        root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
        before = doc_panes(root)
        lines.append('# before: %d open document parts: %s'
                     % (len(before), ' / '.join(sorted(k for k in before)[:12])))
        for ps in paths:
            path = [int(x) for x in ps.split('.') if x != '']
            anc = []
            for k in range(1, len(path)):
                a = node_at(thw, path[:k])
                if a:
                    anc.append('%s=%s' % ('.'.join(map(str, path[:k])),
                                          expand_node(pid, thw, mw, a)))
            h = node_at(thw, path)
            if not h:
                lines.append('## %s  NO SUCH NODE (ancestors: %s)' % (ps, ', '.join(anc)))
                continue
            name = node_text(pid, thw, h)[0]
            sm(thw, TVM_SELECTITEM, TVGN_CARET, h)
            pt = row_xy(pid, thw, h)
            if not pt:
                lines.append('## %s  %s  no reachable row (ancestors: %s)'
                             % (ps, name, ', '.join(anc)))
                continue

            def wait_docs(tag, secs):
                t0 = time.time()
                while time.time() - t0 < secs:
                    time.sleep(0.7)
                    now = doc_panes(auto.ControlFromHandle(wt.HWND(mw['hwnd'])))
                    g = {k: v for k, v in now.items() if k not in before}
                    if g:
                        return g
                return {}

            force_foreground(mw['hwnd'])
            pops0 = popup_ids(pid)
            n0 = sm(thw, TVM_GETCOUNT, 0, 0)
            caret0 = sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0)
            left_click(pt[0], pt[1])
            time.sleep(0.35)
            ok_focus = tree_has_focus(thw)
            # proof the dot landed: after a real click the tree must name this row
            hit1 = (sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0) == h) or selected(thw, h)
            key(0x0D)                            # VK_RETURN down
            time.sleep(0.12)
            key(0x0D, up=True)
            gained = wait_docs('enter', settle)
            how = 'enter'
            hit2 = None
            if not gained:
                # second channel: double-click a DE-selected row (a selected row
                # would go into inline rename instead - project-tree.md §3.1)
                how = 'dblclick'
                sm(thw, TVM_SELECTITEM, TVGN_CARET, 0)
                pt = row_xy(pid, thw, h) or pt
                force_foreground(mw['hwnd'])
                double_click(pt[0], pt[1])
                hit2 = (sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0) == h) or selected(thw, h)
                gained = wait_docs('dbl', settle)
                if not gained:
                    sm(thw, TVM_SELECTITEM, TVGN_CARET, h)   # leave the caret where it was
                    esc(1)                                   # in case rename got armed
                    time.sleep(0.4)
            if not gained:
                late = [w for w in popup_roots(pid)
                        if w['hwnd'] not in pops0 and (w['rect'][2] - w['rect'][0]) > 0]
                lines.append('## %s  %s  %s did not open a document '
                             '(tree focus=%s, row hit by click=%s%s, caret kept=%s, '
                             'rows %d->%d, kids=%s, new windows=%s, ancestors: %s)'
                             % (ps, name, 'enter then ' + how, ok_focus, hit1,
                                '' if hit2 is None else '/%s' % hit2,
                                caret0 == sm(thw, TVM_GETNEXTITEM, TVGN_CARET, 0),
                                n0, sm(thw, TVM_GETCOUNT, 0, 0),
                                len(kids_of(thw, h)),
                                [(w['cls'], w['title']) for w in late], ', '.join(anc)))
                if late:
                    esc(1)                    # a dialog we just summoned must not
                    time.sleep(0.6)           # swallow the whole rest of the sweep
                    lines.append('   Esc sent to clear it')
                continue
            before.update({k: v for k, v in gained.items()})
            lines.append('## %s  %s  opened via %s: %s'
                         % (ps, name, how, ' / '.join(sorted(gained))))
            for k, (ctrl, geo) in sorted(gained.items()):
                if 'TabItem' in k:
                    continue                      # the strip is walked through its pane
                lines.append('   @@ %s' % k)
                walk(ctrl, 0, opt, lines)
                if '--expand' in argv:
                    expand_inside(ctrl, opt, lines, k)
            if '--close' in argv:
                for k in sorted(gained):
                    if 'TabItem' in k:
                        continue
                    nm = k.split('|')[0]
                    res = close_document(mw['hwnd'], nm)
                    left = [prop(c, 'Name') or '' for c in
                            find_by_type(auto.ControlFromHandle(wt.HWND(mw['hwnd'])),
                                         ('PaneControl',), maxd=24)
                            if (prop(c, 'ClassName') or '') == 'DocumentWindow']
                    late = [w for w in popup_roots(pid)
                            if w['hwnd'] not in pops0 and (w['rect'][2] - w['rect'][0]) > 0]
                    lines.append('   close %r -> %s  still open=%s%s'
                                 % (nm, res, left,
                                    '' if not late else
                                    '  NEW popup=%s' % [(w['cls'], w['title']) for w in late]))
                    if res == 'closed':
                        before.pop(k, None)
        n = dump(out, '# open pid=%d %r\n# %s' % (pid, mw['title'], note_fit), lines)
        print('lines=%d docs=%d -> %s  (%s)' % (n, len(paths), out, note_fit))
    finally:
        if old_rect:
            restore_rect(mw['hwnd'], old_rect)
    return 0


def cmd_editor(argv):
    pid = resolve_pid(argv[0])
    out = argv[1]
    mw = main_window(pid)
    root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    lines = []
    for w in find_by_type(root, ('TabbedMdiContainer', 'Tab', 'Tree', 'ToolBar',
                                 'StatusBar', 'Pane', 'Custom')):
        lines.append('== ' + line_of(w))
        try:
            for ch in w.GetChildren():
                lines.append('   ' + line_of(ch))
                for g in ch.GetChildren()[:20]:
                    lines.append('      ' + line_of(g))
        except Exception:
            pass
    n = dump(out, '# editors pid=%d %r' % (pid, mw['title']), lines)
    print('lines=%d -> %s' % (n, out))
    return 0


def cmd_close(argv):
    """Close open editors by document name, or `--all` (the ones currently listed).

    ss_uimap.py close <pid|auto> <out> [--all] [Name ...]

    Goes through each DocumentWindow's own `closeButton` only - see close_document
    for why (measured: Invoke is refused there, the button's rect click closes the
    tab, and closing an editor this session never typed in raises no save prompt).
    Names are matched exactly, then loosely; `--all` closes every DocumentWindow pane
    found, biggest-name-first so the walk cannot be fooled by a tab that moved.
    """
    pid = resolve_pid(argv[0])
    out = argv[1]
    names = [a for a in argv[2:] if not a.startswith('--')]
    mw = main_window(pid)
    lines = []

    def doc_names():
        r = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
        return [prop(c, 'Name') or '' for c in find_by_type(r, ('PaneControl',), maxd=24)
                if (prop(c, 'ClassName') or '') == 'DocumentWindow']

    if '--all' in argv or not names:
        names = sorted(set(doc_names()), key=len, reverse=True)
    lines.append('# close pid=%d %r' % (pid, mw['title']))
    lines.append('# before: %s' % (doc_names() or '[]'))
    for nm in names:
        lines.append('%r -> %s' % (nm, close_document(mw['hwnd'], nm)))
    lines.append('# after: %s' % (doc_names() or '[]'))
    n = dump(out, lines[0], lines[1:])
    print('closed=%d -> %s' % (len(names), out))
    for l in lines[1:]:
        print(l)
    return 0


def cmd_diff(argv):
    a = open(argv[0], encoding='utf-8').read().splitlines()
    b = open(argv[1], encoding='utf-8').read().splitlines()
    sa, sb = set(a), set(b)
    print('only in %s: %d' % (argv[0], len(sa - sb)))
    for l in a:
        if l not in sb:
            print('  - ' + l[:150])
    print('only in %s: %d' % (argv[1], len(sb - sa)))
    for l in b:
        if l not in sa:
            print('  + ' + l[:150])
    return 0


CMDS = dict(scan=cmd_scan, panels=cmd_panels, menus=cmd_menus, ctx=cmd_ctx,
            editor=cmd_editor, diff=cmd_diff, tree=cmd_tree, treectx=cmd_treectx,
            treelabels=cmd_treelabels, treerows=cmd_treerows, open=cmd_open,
            close=cmd_close)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in CMDS:
        print(__doc__)
        return 2
    if not is_admin():
        print('WARN: not elevated - UIA input to a High-integrity Sysmac silently fails')
    return CMDS[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    sys.exit(main())
