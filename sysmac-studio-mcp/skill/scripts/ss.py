"""ss.py - generic Sysmac Studio driver (UIA + win32). Must run ELEVATED + DPI aware.

  ss.py wins                          list SysmacStudio instances (pid/hwnd/title/rect)
  ss.py state <pid|auto>              title / project / controller / mode / editors / busy
  ss.py dump <pid> <out|-> [d] [k]    export UIA tree of every top-level window of the pid
  ss.py find <pid> <id|name>          locate one element
  ss.py click <pid> <id|name>         Invoke/Select/Toggle/Expand/Collapse, fallback Click
  ss.py at|dbl|rclick <pid> <x> <y>   physical-pixel mouse (needs a foreground desktop)
  ss.py keys <pid> <SendKeys>         e.g. {ADD} {ENTER} {ESC} ^a
  ss.py type <pid> <text>
  ss.py menu <pid> <menuName> <item>  open main menu, click item inside the popup HWND
  ss.py popups <pid> [depth]          dump non-main top-level windows (menus/dialogs)
  ss.py grab <pid> <png> [x1 y1 x2 y2]
  ss.py flow <pid> "<step;step;...>"  at/dbl/rclick/cat/sat/drag/wheel/click/menu/keys/type/wait/dump/grab

Notes
  * 'auto' picks the biggest visible Sysmac main window - do NOT use it with two instances.
  * Popup menus, dropdowns and dialogs are separate top-level HWNDs, so every lookup
    walks all visible top-level windows of the pid.
  * uiautomation re-declares SendMessageW's prototype on import; it is restored here so
    64-bit tree handles are not truncated (see references/project-tree.md).
"""
import sys
import time
import ctypes
import ctypes.wintypes as wt

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import uiautomation as auto

auto.SetGlobalSearchTimeout(10)
u = ctypes.windll.user32
k32 = ctypes.windll.kernel32

# uiautomation widens/narrows some prototypes; put the 64-bit-correct ones back.
_u = ctypes.windll.user32
_u.SendMessageW.restype = ctypes.c_ssize_t
_u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]

PROC = 'SysmacStudio.exe'
TITLE = 'Sysmac Studio'


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def wins_of(pid_target, only_visible=True):
    out = []

    def cb(hw, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(p))
        if p.value != pid_target:
            return True
        vis = bool(u.IsWindowVisible(hw))
        if only_visible and not vis:
            return True
        n = u.GetWindowTextLengthW(hw)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hw, b, n + 1)
        c = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hw, c, 256)
        r = wt.RECT()
        u.GetWindowRect(hw, ctypes.byref(r))
        out.append({'hwnd': ctypes.cast(hw, ctypes.c_void_p).value, 'vis': vis,
                    'iconic': bool(u.IsIconic(hw)), 'cls': c.value, 'title': b.value,
                    'rect': (r.left, r.top, r.right - r.left, r.bottom - r.top)})
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    return out


def all_instances():
    """pid -> list of windows, for every process that owns a Sysmac Studio window."""
    seen = {}

    def cb(hw, lp):
        p = wt.DWORD()
        u.GetWindowThreadProcessId(hw, ctypes.byref(p))
        c = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hw, c, 256)
        if not c.value.startswith('HwndWrapper[SysmacStudio'):
            return True          # skip help browsers / chrome windows that carry the title
        n = u.GetWindowTextLengthW(hw)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hw, b, n + 1)
        seen.setdefault(p.value, []).append((ctypes.cast(hw, ctypes.c_void_p).value, b.value))
        return True

    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    return seen


def resolve_pid(arg):
    if arg and arg.lower() not in ('auto', '-1', '0'):
        return int(arg)
    best, best_area = None, -1
    for pid, _ in all_instances().items():
        for w in wins_of(pid):
            if 'HwndWrapper' not in w['cls']:
                continue
            area = w['rect'][2] * w['rect'][3]
            if area > best_area:
                best, best_area = pid, area
    if best is None:
        raise SystemExit('no Sysmac Studio window found - is the app running?')
    return best


def main_hwnd(pid):
    ws = [w for w in wins_of(pid) if 'HwndWrapper' in w['cls']]
    if ws:
        return max(ws, key=lambda w: w['rect'][2] * w['rect'][3])['hwnd']
    return None


def force_foreground(hwnd):
    cur = u.GetForegroundWindow()
    if not cur:
        return False                      # locked workstation: injection will not work
    if cur == hwnd:
        return True                       # already front - do NOT press ALT here,
                                          # ALT puts the WPF menu bar into keyboard
                                          # mode and swallows the next letters
    cur_tid = u.GetWindowThreadProcessId(cur, None)
    tgt_tid = u.GetWindowThreadProcessId(wt.HWND(hwnd), None)
    mine = k32.GetCurrentThreadId()
    if cur_tid:
        u.AttachThreadInput(mine, cur_tid, True)
    if tgt_tid:
        u.AttachThreadInput(mine, tgt_tid, True)
    u.BringWindowToTop(wt.HWND(hwnd))
    u.SetForegroundWindow(wt.HWND(hwnd))
    if u.GetForegroundWindow() != hwnd:
        # ALT unlock trick, only when the first attempt really failed: the ALT
        # key press also drops the WPF menu bar into keyboard mode.
        u.keybd_event(0x12, 0, 0, 0)
        u.keybd_event(0x12, 0, 2, 0)
        u.SetForegroundWindow(wt.HWND(hwnd))
    if cur_tid:
        u.AttachThreadInput(mine, cur_tid, False)
    if tgt_tid:
        u.AttachThreadInput(mine, tgt_tid, False)
    return u.GetForegroundWindow() == hwnd


def roots(pid):
    res = []
    for w in wins_of(pid):
        try:
            res.append((w, auto.ControlFromHandle(wt.HWND(w['hwnd']))))
        except Exception:
            pass
    return res


def find(pid, key, maxd=16, prefix=False):
    """Search every visible top-level window of the pid (menus/dialogs are separate)."""
    for w, root in roots(pid):
        hit = []

        def rec(c, d):
            if hit or d > maxd:
                return
            try:
                aid, nm = c.AutomationId or '', c.Name or ''
                ok = (aid.startswith(key) or nm.startswith(key)) if prefix \
                    else (aid == key or nm == key)
                if ok:
                    hit.append(c)
                    return
            except Exception:
                return
            try:
                for k in c.GetChildren():
                    rec(k, d + 1)
                    if hit:
                        return
            except Exception:
                pass

        rec(root, 0)
        if hit:
            return hit[0], w
    return None, None


def walk(c, d, maxd, maxk, lines):
    if len(lines) > 9000:
        return
    try:
        r = c.BoundingRectangle
        lines.append('  ' * d + f"{c.ControlTypeName.replace('Control', '')} "
                     f"'{(c.Name or '')[:70]}' id='{(c.AutomationId or '')[:40]}' "
                     f"cls='{(c.ClassName or '')[:30]}' "
                     f"({r.left},{r.top},{r.right - r.left}x{r.bottom - r.top})")
    except Exception as e:
        lines.append('  ' * d + f'<ERR {e}>')
        return
    if d >= maxd:
        return
    try:
        ks = c.GetChildren()
    except Exception:
        return
    for i, k in enumerate(ks):
        if i >= maxk:
            lines.append('  ' * (d + 1) + f'... truncated {maxk}/{len(ks)}')
            break
        walk(k, d + 1, maxd, maxk, lines)


def click_at(x, y, kind='click', mod=None):
    vk = {'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12}.get(mod or '')
    if vk:
        u.keybd_event(vk, 0, 0, 0)
        time.sleep(0.10)
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    if kind == 'rclick':
        u.mouse_event(0x0008, 0, 0, 0, 0)
        time.sleep(0.05)
        u.mouse_event(0x0010, 0, 0, 0, 0)
    else:
        u.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        if kind == 'dbl':
            time.sleep(0.06)
            u.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.05)
            u.mouse_event(0x0004, 0, 0, 0, 0)
    if vk:
        time.sleep(0.10)
        u.keybd_event(vk, 0, 2, 0)


def drag(x1, y1, x2, y2):
    u.SetCursorPos(x1, y1)
    time.sleep(0.2)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.2)
    for i in range(1, 26):
        u.SetCursorPos(int(x1 + (x2 - x1) * i / 25.0), int(y1 + (y2 - y1) * i / 25.0))
        time.sleep(0.03)
    time.sleep(0.15)
    u.mouse_event(0x0004, 0, 0, 0, 0)


def do_click(pid, key):
    c, w = find(pid, key)
    if c is None:
        print(f'NOT FOUND: {key}')
        return 1
    try:
        r = c.BoundingRectangle
        print(f"found {c.ControlTypeName} '{c.Name}' id='{c.AutomationId}' "
              f'rect=({r.left},{r.top},{r.right - r.left}x{r.bottom - r.top})')
    except Exception:
        pass
    for helper in ('Invoke', 'Select', 'Toggle', 'Expand', 'Collapse'):
        fn = getattr(c, helper, None)
        if fn is None:
            continue
        try:
            fn()
            print(f'  used {helper}()')
            return 0
        except Exception:
            pass
    try:
        c.Click(simulateMove=False)
        print('  used Click()')
        return 0
    except Exception as e:
        print(f'  all failed: {e}')
        return 1


def menu_item(pid, menu_name, item_name, main_hw, wait=0.8):
    m, _ = find(pid, menu_name)
    if m is None:
        print(f'menu not found: {menu_name}')
        return 1
    try:
        m.Click(simulateMove=False)
    except Exception:
        try:
            m.GetInvokePattern().Invoke()
        except Exception as e:
            print(f'menu click failed: {e}')
            return 1
    time.sleep(wait)
    pops = [w for w in wins_of(pid) if w['vis'] and w['hwnd'] != main_hw and w['rect'][2] > 80]
    for w in pops:
        try:
            r = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        except Exception:
            continue
        hit = []

        def rec(c, d):
            if hit or d > 5:
                return
            try:
                if (c.Name or '') == item_name:
                    hit.append(c)
                    return
            except Exception:
                return
            try:
                for k in c.GetChildren():
                    rec(k, d + 1)
                    if hit:
                        return
            except Exception:
                pass

        rec(r, 0)
        if hit:
            it = hit[0]
            print(f"popup hwnd={w['hwnd']} rect={w['rect']} -> clicking '{item_name}'")
            try:
                it.Click(simulateMove=False)
            except Exception as e:
                print(f'item click failed: {e}')
                try:
                    it.GetInvokePattern().Invoke()
                except Exception as e2:
                    print(f'item invoke failed: {e2}')
                    return 1
            return 0
    seen = []
    for w in pops:
        try:
            r = auto.ControlFromHandle(wt.HWND(w['hwnd']))
            for k in r.GetChildren():
                for kk in k.GetChildren()[:60]:
                    seen.append((kk.Name or '')[:20])
        except Exception:
            pass
    print(f"item '{item_name}' not found. popup items seen: {seen[:40]}")
    u.keybd_event(0x1B, 0, 0, 0)
    u.keybd_event(0x1B, 0, 2, 0)
    return 2


def state(pid):
    hw = main_hwnd(pid)
    if not hw:
        print('no main window')
        return 1
    title = [w['title'] for w in wins_of(pid) if w['hwnd'] == hw][0]
    parts = [p.strip() for p in title.split(' - ')]
    project = parts[0] if parts else ''
    controller = parts[1] if len(parts) > 1 else ''
    dock, _ = find(pid, 'MainDockSite')
    mode = ''
    if dock is not None:
        try:
            mode = dock.Name
        except Exception:
            pass
    mdi, _ = find(pid, 'TabbedMdiContainer', maxd=4, prefix=True)
    editors = -1
    if mdi is not None:
        try:
            editors = len(mdi.GetChildren())
        except Exception:
            pass
    busy = False
    pb, _ = find(pid, 'ProgressBar')
    if pb is not None:
        try:
            r = pb.BoundingRectangle
            busy = (r.right - r.left) > 0 and (r.bottom - r.top) > 0
        except Exception:
            pass
    print(f'pid={pid} hwnd={hw}')
    print(f'title={title}')
    print(f'project={project}')
    print(f'controller={controller}')
    print(f'mode={mode}')
    print(f'editors={editors}')
    print(f'busy={busy}')
    return 0


def grab(pid, out, crop=None):
    from PIL import ImageGrab
    hw = main_hwnd(pid)
    if not hw:
        print('no window')
        return 1
    if not force_foreground(hw):
        print('WARN: could not take the foreground (locked desktop?) - the capture '
              'shows whatever is on screen at that rectangle')
    time.sleep(0.4)
    w = [x for x in wins_of(pid, False) if x['hwnd'] == hw][0]
    l, t, ww, hh = w['rect']
    box = (l, t, l + ww, t + hh) if not crop else tuple(crop)
    img = ImageGrab.grab(bbox=box, all_screens=True)
    img.save(out)
    print(f'grab {out} box={box} size={img.size}')
    return 0


def run_flow(pid, steps):
    main_hw = main_hwnd(pid)
    if not main_hw:
        print(f'no main window for pid {pid}')
        return 1
    print(f'pid={pid} main={main_hw} fg={force_foreground(main_hw)}')
    time.sleep(0.4)
    for raw in steps.split(';'):
        st = raw.strip()
        if not st:
            continue
        kind, _, arg = st.partition(':')
        kind = kind.strip().lower()
        arg = arg.strip()
        if kind in ('at', 'dbl', 'rclick', 'cat', 'sat'):
            x, y = (int(v) for v in arg.split(','))
            base = 'click' if kind in ('cat', 'sat') else kind
            click_at(x, y, base, {'cat': 'ctrl', 'sat': 'shift'}.get(kind))
            print(f'{kind} {x},{y}')
            time.sleep(0.45)
        elif kind == 'drag':
            x1, y1, x2, y2 = (int(v) for v in arg.split(','))
            drag(x1, y1, x2, y2)
            print(f'drag {arg}')
            time.sleep(0.4)
        elif kind == 'wheel':
            x, y, n = (int(v) for v in arg.split(','))
            u.SetCursorPos(x, y)
            time.sleep(0.2)
            for _ in range(abs(n)):
                u.mouse_event(0x0800, 0, 0, -120 if n > 0 else 120, 0)
                time.sleep(0.06)
            print(f'wheel {arg}')
        elif kind == 'click':
            do_click(pid, arg)
            time.sleep(0.4)
        elif kind == 'menu':
            m, _, it = arg.partition('>')
            menu_item(pid, m.strip(), it.strip(), main_hw)
            time.sleep(0.6)
        elif kind == 'wait':
            time.sleep(int(arg) / 1000.0)
        elif kind == 'keys':
            auto.SendKeys(arg, waitTime=0.05)
            print(f'keys {arg}')
            time.sleep(0.3)
        elif kind == 'type':
            auto.SendKeys(arg.replace('{', '{{').replace('}', '{}}'), waitTime=0.03)
            print(f'type {arg}')
            time.sleep(0.3)
        elif kind == 'dump':
            lines = []
            root = auto.ControlFromHandle(wt.HWND(main_hw))
            walk(root, 0, 6, 80, lines)
            open(arg, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
            print(f'dump -> {arg} ({len(lines)} lines)')
        elif kind == 'grab':
            grab(pid, arg)
        else:
            print(f'unknown step: {st}')
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if not is_admin():
        print('WARN: not admin - the UIA tree of Sysmac Studio will be empty (UIPI). '
              'Re-run elevated.')
    a = sys.argv[1].lower()
    if a == 'wins':
        for pid, ws in all_instances().items():
            for hw, title in ws:
                w = [x for x in wins_of(pid, False) if x['hwnd'] == hw][0]
                aux = title in ('', 'SystemResourceNotifyWindow', 'MediaContextNotificationWindow') \
                    or title.startswith('.NET-BroadcastEventWindow')
                if aux and not w['vis']:
                    continue          # hidden WPF helper windows
                print(f"pid={pid} hwnd={hw} vis={w['vis']} iconic={w['iconic']} "
                      f"rect={w['rect']} cls={w['cls'][:44]} title='{title}'")
        return 0
    pid = resolve_pid(sys.argv[2] if len(sys.argv) > 2 else 'auto')
    if a == 'state':
        print(f'admin={is_admin()}')
        return state(pid)
    if a == 'dump':
        out = sys.argv[3] if len(sys.argv) > 3 else '-'
        maxd = int(sys.argv[4]) if len(sys.argv) > 4 else 6
        maxk = int(sys.argv[5]) if len(sys.argv) > 5 else 80
        lines = []
        for w, root in roots(pid):
            lines.append(f"=== HWND={w['hwnd']} vis={w['vis']} rect={w['rect']} "
                         f"cls='{w['cls'][:40]}' title='{w['title'][:50]}'")
            walk(root, 1, maxd, maxk, lines)
        txt = '\n'.join(lines)
        print(f'{len(lines)} lines')
        if out == '-':
            print(txt)
        else:
            open(out, 'w', encoding='utf-8', newline='\n').write(txt)
        return 0
    if a == 'popups':
        maxd = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        mh = main_hwnd(pid)
        for w in wins_of(pid):
            if w['hwnd'] == mh or w['rect'][2] < 40 or w['rect'][3] < 18:
                continue
            print(f"=== popup hwnd={w['hwnd']} rect={w['rect']} cls='{w['cls'][:40]}'")
            try:
                lines = []
                walk(auto.ControlFromHandle(wt.HWND(w['hwnd'])), 0, maxd, 80, lines)
                print('\n'.join(lines))
            except Exception as e:
                print(f'  err {e}')
        return 0
    if a == 'flow':
        return run_flow(pid, sys.argv[3])
    if a == 'grab':
        crop = [int(v) for v in sys.argv[4:8]] if len(sys.argv) > 7 else None
        return grab(pid, sys.argv[3], crop)
    if a == 'find':
        c, w = find(pid, sys.argv[3])
        if c is None:
            print('NOT FOUND')
            return 1
        r = c.BoundingRectangle
        print(f"{c.ControlTypeName} name='{c.Name}' id='{c.AutomationId}' "
              f"cls='{c.ClassName}' enabled={c.IsEnabled} "
              f'rect=({r.left},{r.top},{r.right - r.left}x{r.bottom - r.top}) in hwnd={w["hwnd"]}')
        return 0
    if a == 'click':
        return do_click(pid, sys.argv[3])
    if a == 'menu':
        hw = main_hwnd(pid)
        force_foreground(hw)
        time.sleep(0.3)
        return menu_item(pid, sys.argv[3], sys.argv[4], hw)
    if a in ('at', 'dbl', 'rclick'):
        if not force_foreground(main_hwnd(pid)):
            print('WARN: no foreground desktop - coordinate click may hit another window')
        time.sleep(0.3)
        click_at(int(sys.argv[3]), int(sys.argv[4]), a)
        print(f'{a} {sys.argv[3]},{sys.argv[4]}')
        return 0
    if a == 'keys':
        auto.SendKeys(sys.argv[3], waitTime=0.05)
        print('keys', sys.argv[3])
        return 0
    if a == 'type':
        auto.SendKeys(sys.argv[3].replace('{', '{{').replace('}', '{}}'), waitTime=0.03)
        print('type', sys.argv[3])
        return 0
    print('unknown action', a)
    return 2


if __name__ == '__main__':
    sys.exit(main())
