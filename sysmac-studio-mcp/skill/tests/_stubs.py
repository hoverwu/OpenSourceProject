"""Shared fixtures: fake UIA / ss modules so tests never touch Sysmac or the UI.

Importing this installs lightweight stand-ins for uiautomation / ss / ss_uimap /
ss_axis / PIL into sys.modules and puts skill/scripts on sys.path. Each test
then monkeypatches only the functions it exercises. No real window, no windll
UI call, no Sysmac Studio installation is required.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, '..', 'scripts'))
for _p in (SCRIPTS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _install(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _boom(*a, **k):
    raise AssertionError('unexpected UI call in unit test')


_install('uiautomation',
         ControlFromHandle=_boom, WalkControl=_boom, SendKeys=_boom,
         SetGlobalSearchTimeout=lambda *a, **k: None)
_install('ss',
         main_hwnd=_boom, resolve_pid=_boom, force_foreground=_boom,
         click_at=_boom, find=_boom, wins_of=_boom)
_install('ss_uimap',
         resolve_pid=_boom, main_window=_boom, force_foreground=_boom,
         esc=_boom, close_menu=_boom, dump=_boom, popup_roots=_boom,
         prop=_boom, find_by_type=_boom, menu_bar_items=_boom,
         open_menu=_boom, menu_popups=_boom)
_install('ss_axis', combo=_boom, doc_names=_boom)
_pil = _install('PIL')
_install('PIL.ImageGrab', grab=_boom)
_pil.ImageGrab = sys.modules['PIL.ImageGrab']


class Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class Ctrl:
    """Minimal UIA control stand-in (only the attributes the scripts read)."""

    def __init__(self, type, name='', aid='', help='', rect=(0, 0, 0, 0), children=(),
                 offscreen=True):
        self.ControlTypeName = type
        self.Name = name
        self.AutomationId = aid
        self.HelpText = help
        self.BoundingRectangle = Rect(*rect)
        self.IsOffscreen = offscreen
        self._children = list(children)

    def GetChildren(self):
        return list(self._children)


class FakeAuto:
    """WalkControl yields (control, depth) tuples like uiautomation does."""

    def __init__(self, root=None):
        self.root = root
        self.sent = []

    def ControlFromHandle(self, hw):
        return self.root

    def WalkControl(self, root, maxDepth=24):
        queue = [(root, 0)]
        while queue:
            c, d = queue.pop(0)
            yield c, d
            if d < maxDepth:
                queue.extend((k, d + 1) for k in c.GetChildren())

    def SendKeys(self, text, waitTime=0, **k):
        self.sent.append(text)


class FakeTime:
    """Fake clock: sleep advances a monotonic wall clock so deadline logic that
    uses time.monotonic() can be tested without real waiting (read cost included
    by calling sleep inside a fake read)."""

    def __init__(self):
        self.slept = []
        self._now = 0.0

    def sleep(self, s):
        self.slept.append(s)
        self._now += s

    def time(self):
        return self._now

    def monotonic(self):
        return self._now