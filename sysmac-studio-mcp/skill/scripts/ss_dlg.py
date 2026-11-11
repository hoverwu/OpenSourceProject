# -*- coding: utf-8 -*-
"""ss_dlg.py - 在 Sysmac 的任意弹层/对话框里按名点按钮（提权运行）。

作者：hoverwu ｜ 版本：0.1.0 ｜ 建立：2026-11-08 ｜ 非官方，需提权（High IL 的 UIA）。

  ss_dlg.py <pid> list  [标题包含串]
        列出该 pid 所有可见顶层窗口 + 每个窗口里的 Button（Name / AutomationId / rect / enabled）。
  ss_dlg.py <pid> bind  <AutomationId|按钮名> [标题包含串]
        在匹配窗口里点该按钮：InvokePattern 优先，失败退回真实点击。
        默认**只点**，不猜第二个按钮；找不到就如实失败。
  ss_dlg.py <pid> text  [标题包含串]
        打印匹配窗口里的 Text / Pane(ScrollViewer) 文案（消息框正文就在这里）。

为什么单独一个：内联 `python -c` 经多层外壳转发时引号会被吃，
凡是多点两步的对话框操作都写成文件跑。
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


def wins(pid):
    mw = M.main_window(pid)
    out = []
    for w in M.wins_of(pid):
        if w['hwnd'] == mw['hwnd'] or w['rect'][2] < 40 or w['rect'][3] < 20:
            continue
        out.append(w)
    return out


def pick(pid, title_filter):
    cands = wins(pid)
    if title_filter:
        cands = [w for w in cands if title_filter in (w['title'] or '')]
    return cands


def cmd_list(pid, title_filter=''):
    for w in pick(pid, title_filter):
        print('=== hwnd=%d rect=%s title=%r cls=%r' % (w['hwnd'], w['rect'], w['title'], w['cls'][:38]))
        root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        if root is None:
            continue
        for c in M.find_by_type(root, ('ButtonControl',), maxd=14):
            if rect(c)[2] <= 0:
                continue
            print('   Button %-16r aid=%-18r rect=%-22s enabled=%s' %
                  (M.prop(c, 'Name'), M.prop(c, 'AutomationId'), str(rect(c)), M.prop(c, 'IsEnabled')))
    return 0


def cmd_text(pid, title_filter=''):
    for w in pick(pid, title_filter):
        print('=== hwnd=%d title=%r' % (w['hwnd'], w['title']))
        root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        if root is None:
            continue
        for c in M.find_by_type(root, ('TextControl', 'PaneControl', 'EditControl'), maxd=8):
            nm = M.prop(c, 'Name') or ''
            if nm.strip():
                print('   %-14s %s' % (M.prop(c, 'ControlTypeName'), nm.replace('\n', ' / ')))
    return 0


def cmd_bind(pid, key, title_filter=''):
    for w in pick(pid, title_filter):
        root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        if root is None:
            continue
        btns = [c for c in M.find_by_type(root, ('ButtonControl',), maxd=14) if rect(c)[2] > 0]
        hit = [c for c in btns if (M.prop(c, 'AutomationId') or '') == key]
        if not hit:
            hit = [c for c in btns if (M.prop(c, 'Name') or '').replace(' ', '') == key.replace(' ', '')]
        if not hit:
            continue
        b = hit[0]
        M.force_foreground(w['hwnd'])
        time.sleep(0.4)
        try:
            b.GetInvokePattern().Invoke()
            how = 'invoke'
        except Exception:
            x, y, bw, bh = rect(b)
            M.left_click(x + bw // 2, y + bh // 2)
            how = 'click@%d,%d' % (x + bw // 2, y + bh // 2)
        print('clicked %r aid=%r in %r -> %s' %
              (M.prop(b, 'Name'), M.prop(b, 'AutomationId'), w['title'], how))
        time.sleep(1.5)
        return 0
    print('no button %r in windows %r' % (key, [w['title'] for w in pick(pid, title_filter)]))
    return 1


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    if not M.is_admin():
        print('WARN: not admin - UIA empty (UIPI)')
    pid = M.resolve_pid(sys.argv[1])
    a = sys.argv[2].lower()
    tf = ''
    if a == 'list':
        tf = sys.argv[3] if len(sys.argv) > 3 else ''
        return cmd_list(pid, tf)
    if a == 'text':
        tf = sys.argv[3] if len(sys.argv) > 3 else ''
        return cmd_text(pid, tf)
    if a == 'bind':
        key = sys.argv[3]
        tf = sys.argv[4] if len(sys.argv) > 4 else ''
        return cmd_bind(pid, key, tf)
    print('unknown action', a)
    return 2


if __name__ == '__main__':
    sys.exit(main())