"""ss_record.py - record manual operations in Sysmac Studio into JSON.

作者：hoverwu ｜ 版本：0.2.0 ｜ 非官方工具

Must run ELEVATED: Sysmac Studio runs at High integrity, so a medium-integrity
process sees no controls and gets no cross-process UIA events. The accompanying
.bat self-elevates (one UAC prompt).

  ss_record.py [--out DIR] [--pid N] [--all] [--note TEXT] [--seconds N]

Stop: press Ctrl+Alt+F12, or close the console window. The .jsonl is written
line by line, so even a hard close keeps everything up to that point; the final
.json (with meta / actions summary) is written on a clean stop.

DESIGN INVARIANT (learned the hard way, 2026-10-31):
  The low-level mouse/keyboard hook callbacks must NEVER call UI Automation,
  read the clipboard, touch the disk or print. A cross-process UIA call inside
  a WH_*_LL hook can wait on the target's UI thread, which is itself waiting
  for the hook to return -> the whole input queue freezes (pressing Win and
  opening the Start menu was enough to hang the console). Hooks therefore only
  capture raw data into a queue; one worker thread does all UIA / I/O.

What gets recorded (only events aimed at Sysmac Studio by default):
  click / doubleclick / rightclick   element resolved in the worker while the
                                     button is still down (menu still open)
  drag                               from/to elements, dx/dy, duration
  wheel                              point + delta
  text / paste / shortcut / key      typed characters, clipboard paste, Ctrl+...
  value                              focused edit box re-read after Enter/Tab
                                     (recovers IME-composed CJK text)
  focus                              focused control changes
  window_open / window_close         top-level windows + control tree snapshot
  activate                           foreground switch into/out of Sysmac

Coordinates are physical pixels (per-monitor DPI aware). Element paths are live
UIA snapshots; RuntimeId is NOT stable across launches, so replay should match
on aid / ctl / name / rect, in that order.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)      # per-monitor, before UIA starts
except Exception:
    pass
import uiautomation as auto          # noqa: E402
import ss                            # noqa: E402

VERSION = '0.2.0'
AUTHOR = 'hoverwu'

u = ctypes.windll.user32
k32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_QUIT = 0x0012

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_F12 = 0x7B

STOP_HOTKEY_VK = VK_F12            # Ctrl+Alt+F12


class POINT(ctypes.Structure):
    _fields_ = [('x', wt.LONG), ('y', wt.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('pt', POINT), ('mouseData', wt.DWORD), ('flags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wt.DWORD), ('scanCode', wt.DWORD), ('flags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)


def _setup_ctypes():
    u.SetWindowsHookExW.restype = ctypes.c_void_p
    u.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wt.DWORD]
    u.CallNextHookEx.restype = ctypes.c_ssize_t
    u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
    u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    u.GetForegroundWindow.restype = wt.HWND
    u.GetMessageW.restype = ctypes.c_int
    u.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    u.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
    u.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u.ToUnicodeEx.restype = ctypes.c_int
    u.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_wchar_p,
                              ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]


def screen_metrics():
    return {
        'screen': [u.GetSystemMetrics(0), u.GetSystemMetrics(1)],
        'virtual': [u.GetSystemMetrics(76), u.GetSystemMetrics(77),
                    u.GetSystemMetrics(78), u.GetSystemMetrics(79)],
    }


def fg_pid():
    """Foreground pid only - no title/class lookups, no cross-process memory."""
    hw = u.GetForegroundWindow()
    if not hw:
        return 0
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(hw, ctypes.byref(pid))
    return pid.value


def fg_window():
    hw = u.GetForegroundWindow()
    if not hw:
        return {}
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(hw, ctypes.byref(pid))
    n = u.GetWindowTextLengthW(hw)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hw, b, n + 1)
    c = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hw, c, 256)
    return {'hwnd': ctypes.cast(hw, ctypes.c_void_p).value,
            'pid': pid.value, 'title': b.value, 'cls': c.value}


def _rect(ctl):
    try:
        r = ctl.BoundingRectangle
        return [int(r.left), int(r.top), int(r.right - r.left), int(r.bottom - r.top)]
    except Exception:
        return [0, 0, 0, 0]


def _brief(ctl):
    try:
        return {'ctl': ctl.ControlTypeName,
                'name': (ctl.Name or '')[:200],
                'aid': ctl.AutomationId or '',
                'cls': ctl.ClassName or '',
                'rect': _rect(ctl)}
    except Exception:
        return {'ctl': '?', 'name': '', 'aid': '', 'cls': '', 'rect': [0, 0, 0, 0]}


def _leaf_texts(ctl, limit=12):
    out = []
    try:
        for k in ctl.GetChildren():
            try:
                if k.ControlTypeName == 'TextControl' and k.Name:
                    out.append(k.Name)
            except Exception:
                continue
    except Exception:
        pass
    return out[:limit]


def _value(ctl):
    try:
        return ctl.GetValuePattern().Value
    except Exception:
        return ''


def _pid_of(ctl):
    try:
        return ctl.ProcessId
    except Exception:
        return 0


def snapshot(ctl, depth=8, texts=True):
    """Leaf-first snapshot turned into a root->leaf path. Desktop is dropped."""
    chain = []
    c = ctl
    for _ in range(depth):
        if c is None:
            break
        chain.append(_brief(c))
        try:
            c = c.GetParentControl()
        except Exception:
            break
    chain.reverse()
    while chain and chain[0]['cls'] == '#32769':
        chain.pop(0)
    return {'path': chain,
            'texts': _leaf_texts(ctl) if texts else [],
            'value': _value(ctl) if texts else ''}


def tree_snapshot(ctl, max_depth=5, max_nodes=400):
    budget = [max_nodes]

    def node(c, d):
        if budget[0] <= 0 or d > max_depth:
            return None
        budget[0] -= 1
        n = _brief(c)
        n['kids'] = []
        try:
            for k in c.GetChildren():
                kn = node(k, d + 1)
                if kn:
                    n['kids'].append(kn)
        except Exception:
            pass
        if not n['kids']:
            del n['kids']
        return n

    return node(ctl, 0)


class Recorder:
    def __init__(self, out_dir, note='', only_sysmac=True, pid_override=None):
        self.out_dir = out_dir
        self.note = note
        self.only_sysmac = only_sysmac
        self.pid_override = pid_override
        self.t0 = time.time()
        self.lock = threading.Lock()
        self.events = []
        self.windows = {}
        self.sysmac_pids = set()
        self.own_pid = os.getpid()
        self.thread_id = k32.GetCurrentThreadId()
        self.stop = False
        self.finished = False
        self.text_buf = []
        self.pending = {}            # seq -> {'pt','button','t','el'}  (worker side)
        self.seq = 0                 # bumped in the hook (single writer)
        self.last_click = None
        self.shift = self.ctrl = self.alt = False
        self.hooks = []
        self.fg_key = None
        self.focus_key = None
        self.clicks = 0
        self._last_val = None
        self.started = datetime.datetime.now()
        self.q = queue.Queue()
        self.worker = None
        self.fg_pid = 0              # cached by the worker; hooks never query Win32
        os.makedirs(out_dir, exist_ok=True)
        stem = 'rec_' + self.started.strftime('%Y%m%d_%H%M%S')
        self.jsonl_path = os.path.join(out_dir, stem + '.jsonl')
        self.json_path = os.path.join(out_dir, stem + '.json')
        self.jl = open(self.jsonl_path, 'a', encoding='utf-8', newline='\n')
        self._refresh_pids()
        self._prime_windows()

    # ------------------------------------------------------------ log/output

    def now_ms(self):
        return int((time.time() - self.t0) * 1000)

    def emit(self, ev):
        ev.setdefault('t', ev.pop('t_ms', None) if ev.get('t_ms') is not None else self.now_ms())
        ev.pop('t_ms', None)
        ev.setdefault('fg', self._fg_short())
        with self.lock:
            self.events.append(ev)
            self.jl.write(json.dumps(ev, ensure_ascii=False) + '\n')
            self.jl.flush()
        desc = ev.get('kind', '?')
        target = ''
        try:
            p = ev.get('el', {}).get('path') or []
            if p:
                leaf = p[-1]
                target = '%s %r aid=%r' % (leaf['ctl'], leaf['name'][:40], leaf['aid'])
        except Exception:
            pass
        extra = ''
        if ev.get('kind') == 'text':
            extra = repr(ev.get('text', '')[:60])
        elif ev.get('kind') == 'key':
            extra = ev.get('name', '')
        elif ev.get('kind') == 'window_open':
            extra = repr(ev.get('win', {}).get('title', '')[:50])
        elif ev.get('kind') in ('click', 'doubleclick', 'rightclick', 'drag'):
            extra = ev.get('button', '')
        print('[%8.3fs] %-12s %-30s %s' % (time.time() - self.t0, desc, extra, target),
              flush=True)

    def _fg_short(self):
        f = fg_window()
        return {'pid': f.get('pid', 0), 'title': f.get('title', '')}

    # ------------------------------------------------------------- pid/windows

    def _refresh_pids(self):
        try:
            inst = ss.all_instances()
        except Exception:
            inst = {}
        pids = set(inst.keys())
        if self.pid_override:
            pids = {self.pid_override}
        self.sysmac_pids = pids
        return pids

    def _is_target_pid(self, pid):
        if not self.only_sysmac:
            return True
        return pid in self.sysmac_pids

    def _top_windows(self):
        out = []
        for pid in self._refresh_pids():
            for w in ss.wins_of(pid):
                if not w['vis']:
                    continue
                out.append(w)
        return out

    def _prime_windows(self):
        now = self.now_ms()
        for w in self._top_windows():
            self.windows[w['hwnd']] = {'hwnd': w['hwnd'], 'title': w['title'],
                                       'cls': w['cls'], 'rect': list(w['rect']),
                                       'first': now}
        print('目标进程：%s' % (sorted(self.sysmac_pids) or '（未发现 Sysmac，稍后自动发现）'))

    # ------------------------------------------------------------------ worker

    def _worker(self):
        """Everything that touches UIA / disk / clipboard runs here, never in a hook."""
        auto.InitializeUIAutomationInCurrentThread()
        last_poll = 0.0
        while True:
            try:
                self.fg_pid = fg_pid()
            except Exception:
                pass
            try:
                item = self.q.get(timeout=0.1)
            except queue.Empty:
                item = None
            if item is not None:
                try:
                    self._handle(item)
                except Exception as e:
                    print('  ! handler: %s' % e, flush=True)
            now = time.time()
            if now - last_poll > 0.4:
                last_poll = now
                try:
                    self._poll_windows()
                    self._poll_foreground()
                    self._poll_focus()
                except Exception:
                    pass
            if self.stop and self.q.empty():
                break
        self._flush_text()

    def _handle(self, it):
        k = it.get('k')
        if k == 'down':
            el = self._element_at(it['pt'])
            self.pending[it['seq']] = {'pt': it['pt'], 'button': it['button'],
                                       't': it['t'], 'el': el}
            if len(self.pending) > 32:
                self.pending.pop(min(self.pending), None)
        elif k == 'up':
            p = self.pending.pop(it['seq'], None)
            if p is None:
                return
            dur = it['t'] - p['t']
            dist = self._dist(p['pt'], it['pt'])
            moved = max(dist, it.get('moved', 0.0))
            if p['button'] == 'left' and dur > 0.35 and moved > 8:
                self.emit({'kind': 'drag',
                           'from': p['el'],
                           'to': self._element_at(it['pt']),
                           'dx': it['pt'][0] - p['pt'][0],
                           'dy': it['pt'][1] - p['pt'][1],
                           'ms': int(dur * 1000),
                           'point': list(p['pt']),
                           't_ms': int((p['t'] - self.t0) * 1000)})
            else:
                self._record_click(p, it['pt'], dur)
        elif k == 'wheel':
            el = self._element_at(it['pt'])
            if el is not None:
                self.emit({'kind': 'wheel', 'delta': it['delta'],
                           'point': list(it['pt']), 'el': el, 't_ms': it['t_ms']})
        elif k == 'key':
            self._on_key(it)
        elif k == 'stop':
            self.request_stop()

    @staticmethod
    def _dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def _record_click(self, p, up_pt, dur):
        el = p['el']
        if el is None and self.only_sysmac:
            return
        dbl = False
        if p['button'] == 'left' and self.last_click is not None:
            lt, lx, ly = self.last_click
            dbl = (time.time() - lt) < 0.5 and abs(up_pt[0] - lx) <= 4 and abs(up_pt[1] - ly) <= 4
        if p['button'] == 'left':
            self.last_click = (time.time(), up_pt[0], up_pt[1])
        kind = 'rightclick' if p['button'] == 'right' else ('doubleclick' if dbl else 'click')
        self.emit({'kind': kind, 'button': p['button'],
                   'point': list(p['pt']), 'up': list(up_pt),
                   'ms': int(dur * 1000), 'el': el,
                   't_ms': int((p['t'] - self.t0) * 1000)})
        self.clicks += 1
        self._flush_text()
        self._read_focused_value()

    def _element_at(self, pt):
        try:
            c = auto.ControlFromPoint(pt[0], pt[1])
        except Exception:
            return None
        if c is None:
            return None
        if not self._is_target_pid(_pid_of(c)):
            return None
        return snapshot(c)

    # --------------------------------------------------------------- keyboard

    def _on_key(self, it):
        vk = it['vk']
        self.shift, self.ctrl, self.alt = it['shift'], it['ctrl'], it['alt']
        if vk in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN,
                  0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            return
        if self.ctrl and not self.alt and 0x41 <= vk <= 0x5A:
            ch = chr(vk)
            if ch == 'V':
                txt = ''
                try:
                    txt = auto.GetClipboardText() or ''
                except Exception:
                    pass
                self._flush_text()
                self.emit({'kind': 'paste', 'text': txt, 't_ms': it['t_ms']})
            else:
                self._flush_text()
                self.emit({'kind': 'shortcut', 'keys': 'Ctrl+' + ch, 't_ms': it['t_ms']})
            return
        if self.alt:
            self._flush_text()
            self.emit({'kind': 'altkey', 'vk': vk, 't_ms': it['t_ms']})
            return
        if vk == VK_RETURN:
            self._flush_text()
            self.emit({'kind': 'key', 'name': 'Enter', 't_ms': it['t_ms']})
            self._read_focused_value()
            return
        if vk == VK_TAB:
            self._flush_text()
            self.emit({'kind': 'key', 'name': 'Tab', 'shift': self.shift, 't_ms': it['t_ms']})
            self._read_focused_value()
            return
        if vk == VK_ESCAPE:
            self._flush_text()
            self.emit({'kind': 'key', 'name': 'Escape', 't_ms': it['t_ms']})
            return
        if vk == VK_BACK:
            if self.text_buf:
                self.text_buf.pop()
                self.emit({'kind': 'key', 'name': 'Backspace',
                           'buffered': ''.join(self.text_buf), 't_ms': it['t_ms']})
            else:
                self.emit({'kind': 'key', 'name': 'Backspace', 't_ms': it['t_ms']})
            return
        if vk in (VK_DELETE, 0x25, 0x26, 0x27, 0x28, 0x21, 0x22, 0x23, 0x24):
            self._flush_text()
            self.emit({'kind': 'key', 'name': {VK_DELETE: 'Delete', 0x25: 'Left', 0x26: 'Up',
                                               0x27: 'Right', 0x28: 'Down', 0x21: 'PageUp',
                                               0x22: 'PageDown', 0x23: 'End', 0x24: 'Home'}[vk],
                       'shift': self.shift, 't_ms': it['t_ms']})
            return
        ch = self._char(vk, it['scan'])
        if ch and ch.isprintable():
            self.text_buf.append(ch)
        else:
            self.emit({'kind': 'ime_key', 'vk': vk, 't_ms': it['t_ms']})

    def _char(self, vk, scan):
        try:
            state = (ctypes.c_byte * 256)()
            state[VK_SHIFT] = 0x80 if self.shift else 0
            state[VK_CONTROL] = 0x80 if self.ctrl else 0
            state[VK_MENU] = 0x80 if self.alt else 0
            hkl = u.GetKeyboardLayout(0)
            buf = ctypes.create_unicode_buffer(8)
            n = u.ToUnicodeEx(vk, scan, state, buf, 8, 0, hkl)
            if n == 1 and buf.value and buf.value.isprintable():
                return buf.value
        except Exception:
            pass
        return ''

    def _flush_text(self):
        if not self.text_buf:
            return
        txt = ''.join(self.text_buf)
        self.text_buf = []
        self.emit({'kind': 'text', 'text': txt})

    def _read_focused_value(self):
        """IME-composed text never reaches a low-level keyboard hook; the edit's
        value after Enter/Tab/click does. Record it when it changed."""
        try:
            c = auto.GetFocusedControl()
        except Exception:
            return
        if c is None or not self._is_target_pid(_pid_of(c)):
            return
        val = _value(c)
        if not val:
            return
        el = snapshot(c, texts=False)
        leaf = el['path'][-1] if el.get('path') else {}
        key = (leaf.get('aid', ''), leaf.get('name', ''))
        if self._last_val == (key, val):
            return
        self._last_val = (key, val)
        self.emit({'kind': 'value', 'value': val, 'el': el})

    # ---------------------------------------------------- polling (worker only)

    def _poll_windows(self):
        seen = set()
        for w in self._top_windows():
            seen.add(w['hwnd'])
            if w['hwnd'] not in self.windows:
                root = None
                try:
                    root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
                except Exception:
                    pass
                self.windows[w['hwnd']] = {'hwnd': w['hwnd'], 'title': w['title'],
                                           'cls': w['cls'], 'rect': list(w['rect']),
                                           'first': self.now_ms()}
                ev = {'kind': 'window_open', 'win': dict(self.windows[w['hwnd']])}
                if root is not None:
                    ev['tree'] = tree_snapshot(root)
                self.emit(ev)
        for hwnd, info in list(self.windows.items()):
            if hwnd in seen or 'closed' in info:
                continue
            info['closed'] = self.now_ms()
            self.emit({'kind': 'window_close', 'win': dict(info)})
        if len(self.windows) > 200:
            old = sorted(self.windows.items(), key=lambda kv: kv[1].get('first', 0))[:100]
            for k, _ in old:
                self.windows.pop(k, None)

    def _poll_foreground(self):
        f = fg_window()
        if not f:
            return
        key = (f.get('pid'), f.get('hwnd'))
        if key == self.fg_key:
            return
        self.fg_key = key
        if f.get('pid') == self.own_pid:
            self.emit({'kind': 'activate', 'to': 'self'})
            return
        if self._is_target_pid(f.get('pid') or 0):
            self.emit({'kind': 'activate', 'to': 'sysmac', 'win': f})

    def _poll_focus(self):
        try:
            c = auto.GetFocusedControl()
        except Exception:
            return
        if c is None:
            return
        pid = _pid_of(c)
        if not self._is_target_pid(pid):
            self.focus_key = None
            return
        b = _brief(c)
        key = (pid, b['aid'], b['name'], tuple(b['rect']))
        if key == self.focus_key:
            return
        self.focus_key = key
        self.emit({'kind': 'focus', 'el': snapshot(c, texts=False)})

    # ------------------------------------------------------------------ hooks
    # Nothing below may call UIA / do I/O / print.

    def _mouse_proc(self, ncode, wparam, lparam):
        if ncode < 0:
            return u.CallNextHookEx(None, ncode, wparam, lparam)
        try:
            ms = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            pt = (ms.pt.x, ms.pt.y)
            t = time.time()
            if wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                self.seq += 1
                self.q.put({'k': 'down', 'seq': self.seq, 'pt': pt, 't': t,
                            'button': 'left' if wparam == WM_LBUTTONDOWN else 'right'})
            elif wparam in (WM_LBUTTONUP, WM_RBUTTONUP):
                self.q.put({'k': 'up', 'seq': self.seq, 'pt': pt, 't': t,
                            'button': 'left' if wparam == WM_LBUTTONUP else 'right'})
            elif wparam == WM_MOUSEMOVE:
                pass
            elif wparam == WM_MOUSEWHEEL:
                self.q.put({'k': 'wheel', 'pt': pt, 'delta': (ms.mouseData >> 16) & 0xFFFF,
                            't_ms': int((t - self.t0) * 1000)})
        except Exception:
            pass
        return u.CallNextHookEx(None, ncode, wparam, lparam)

    def _key_proc(self, ncode, wparam, lparam):
        if ncode < 0:
            return u.CallNextHookEx(None, ncode, wparam, lparam)
        try:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = kb.vkCode
            down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            if vk in (VK_CONTROL, 0xA2, 0xA3):
                self.ctrl = down
            elif vk in (VK_SHIFT, 0xA0, 0xA1):
                self.shift = down
            elif vk in (VK_MENU, 0xA4, 0xA5):
                self.alt = down
            if down:
                if self.ctrl and self.alt and vk == STOP_HOTKEY_VK:
                    self.q.put({'k': 'stop'})
                    return 1
                if self._keyboard_targets_sysmac():
                    self.q.put({'k': 'key', 'vk': vk, 'scan': kb.scanCode,
                                'ctrl': self.ctrl, 'alt': self.alt, 'shift': self.shift,
                                't_ms': int((time.time() - self.t0) * 1000)})
        except Exception:
            pass
        return u.CallNextHookEx(None, ncode, wparam, lparam)

    def _keyboard_targets_sysmac(self):
        if not self.only_sysmac:
            return True
        return (self.fg_pid or 0) in self.sysmac_pids

    # ------------------------------------------------------------------- loop

    def request_stop(self):
        if self.stop:
            return
        self.stop = True
        u.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)

    def install_console_handler(self):
        """Closing the console fires CTRL_CLOSE_EVENT; give the worker a moment to
        write the final .json before Windows kills the process."""
        self._ctrl_cb = ctypes.WINFUNCTYPE(wt.BOOL, wt.DWORD)(self._ctrl_handler)
        k32.SetConsoleCtrlHandler(self._ctrl_cb, True)

    def _ctrl_handler(self, evt):
        if evt in (2, 5, 6):                 # CLOSE / LOGOFF / SHUTDOWN
            print('\n窗口即将关闭，写入 JSON…', flush=True)
            self.request_stop()
            t0 = time.time()
            while time.time() - t0 < 4 and not self.finished:
                time.sleep(0.05)
            return True
        return False                         # Ctrl+C: let Python raise

    def install_hooks(self):
        self._mouse_cb = HOOKPROC(self._mouse_proc)
        self._key_cb = HOOKPROC(self._key_proc)
        hm = u.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_cb, None, 0)
        hk = u.SetWindowsHookExW(WH_KEYBOARD_LL, self._key_cb, None, 0)
        if not hm or not hk:
            raise SystemExit('SetWindowsHookEx failed (err=%d) - run elevated' % k32.GetLastError())
        self.hooks = [hm, hk]

    def _unhook(self):
        for h in self.hooks:
            try:
                u.UnhookWindowsHookEx(h)
            except Exception:
                pass
        self.hooks = []

    def run(self):
        self.install_hooks()
        self.install_console_handler()
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()
        msg = wt.MSG()
        try:
            while not self.stop:
                rv = u.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if rv == 0 or rv == -1:
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
        except KeyboardInterrupt:
            pass
        finally:
            self.stop = True
            self._unhook()                   # stop new events, then drain
            if self.worker is not None:
                self.worker.join(4)
            self.finish()

    def finish(self):
        self.stop = True
        self._unhook()
        self._flush_text()
        ended = datetime.datetime.now()
        actions = self._summarise()
        data = {
            'meta': {
                'tool': 'ss_record', 'version': VERSION, 'author': AUTHOR,
                'started': self.started.isoformat(timespec='seconds'),
                'ended': ended.isoformat(timespec='seconds'),
                'duration_s': round((ended - self.started).total_seconds(), 1),
                'note': self.note, 'elevated': ss.is_admin(),
                'sysmac_pids': sorted(self.sysmac_pids),
                'clicks': self.clicks, 'events': len(self.events),
                **screen_metrics(),
            },
            'windows': list(self.windows.values()),
            'actions': actions,
            'events': self.events,
        }
        with open(self.json_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        try:
            self.jl.close()
        except Exception:
            pass
        self.finished = True
        print('\n录制结束：%d 个事件 / %d 次点击' % (len(self.events), self.clicks))
        print('JSON  : %s' % self.json_path)
        print('JSONL : %s' % self.jsonl_path)
        print('可直接把 JSON 交给 Agent，按 actions 生成固定流程脚本。')

    # ---------------------------------------------------------------- summary

    def _summarise(self):
        """Group events into user-level actions: one click/drag + its inputs."""
        actions = []
        cur = None

        def target_of(el):
            if not el:
                return ''
            p = (el.get('path') or [])
            if not p:
                return ''
            leaf = p[-1]
            return '%s %r%s' % (leaf['ctl'], leaf['name'][:60],
                                (' aid=' + leaf['aid']) if leaf['aid'] else '')

        for ev in self.events:
            k = ev.get('kind')
            if k in ('click', 'doubleclick', 'rightclick'):
                if cur:
                    actions.append(cur)
                cur = {'i': ev.get('t'), 'kind': k, 'target': target_of(ev.get('el')),
                       'point': ev.get('point'), 'inputs': [], 'windows': [],
                       'el': ev.get('el')}
            elif k == 'drag':
                if cur:
                    actions.append(cur)
                cur = {'i': ev.get('t'), 'kind': 'drag',
                       'target': target_of(ev.get('from')),
                       'drop': target_of(ev.get('to')),
                       'dx': ev.get('dx'), 'dy': ev.get('dy'),
                       'inputs': [], 'windows': [], 'el': ev.get('from')}
            elif k in ('text', 'paste', 'shortcut', 'key', 'value', 'altkey'):
                if cur is None:
                    cur = {'i': ev.get('t'), 'kind': 'input_only', 'target': '',
                           'inputs': [], 'windows': []}
                cur['inputs'].append({kk: ev.get(kk) for kk in
                                      ('kind', 'text', 'keys', 'name', 'value') if kk in ev})
            elif k == 'window_open':
                if cur is not None:
                    cur['windows'].append(ev.get('win', {}).get('title', ''))
            elif k == 'wheel' and cur is not None:
                cur['inputs'].append({'kind': 'wheel', 'delta': ev.get('delta')})
        if cur:
            actions.append(cur)
        return [a for a in actions if not (a['kind'] == 'input_only' and not a['inputs'])]


def main():
    ap = argparse.ArgumentParser(description='Record Sysmac Studio operations into JSON (run elevated)')
    ap.add_argument('--out', default=os.path.join(os.getcwd(), 'recordings'))
    ap.add_argument('--pid', type=int, default=0)
    ap.add_argument('--all', action='store_true', help='record every app, not only Sysmac')
    ap.add_argument('--note', default='')
    ap.add_argument('--seconds', type=float, default=0,
                    help='self-test: stop automatically after N seconds')
    args = ap.parse_args()

    _setup_ctypes()
    auto.SetGlobalSearchTimeout(2)
    if not ss.is_admin():
        print('警告：当前不是管理员。Sysmac 以 High 运行时，录制器看不到它的控件。', flush=True)
    print('== Sysmac 操作录制器 v%s (%s)' % (VERSION, AUTHOR))
    print('   停止：Ctrl+Alt+F12（或关闭本窗口）')
    print('   只记录发往 Sysmac Studio 的操作%s' % ('' if not args.all else '（--all：全部应用）'))
    rec = Recorder(args.out, note=args.note, only_sysmac=not args.all,
                   pid_override=args.pid or None)
    print('   输出：%s' % rec.jsonl_path)
    if args.seconds > 0:
        threading.Timer(args.seconds, rec.request_stop).start()
    rec.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
