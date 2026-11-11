# -*- coding: utf-8 -*-
"""ss_esi.py - install an EtherCAT ESI (XML) profile through Sysmac Studio's ESI库 dialog.

作者：hoverwu ｜ 版本：0.1.0 ｜ 建立：2026-11-08 ｜ 非官方，必须在**提权**上下文里跑
（Sysmac Studio 是 High IL，Medium IL 的 UIA 读不到它的树 —— UIPI）。

路线（全部实测，见 references/pitfalls.md §68）：
  EtherCAT 编辑器 → 选中「主设备」行 → 真实右键 → 菜单项 **显示ESI库**（无空格、无访问键）
  → 独立顶层窗口 `ESI库`（Custom cls='ProfileLibraryView'，Tree id='EsiProfileTreeView'）
  → Button id='installFileButton' 安装(文件) / 'installFolderButton' 安装(文件夹)
     / 'unInstallButton' 卸载 / 'cancelButton' 关闭

  ss_esi.py <pid> master                       找到主设备行并打印 rect（不点击）
  ss_esi.py <pid> open      <out>              右键主设备 → 显示ESI库 → dump 对话框
  ss_esi.py <pid> dump      <out>              dump 当前所有可见窗口（含 ESI库 / 文件对话框）
  ss_esi.py <pid> installbtn <out>             点 安装(文件)，dump 弹出的文件选择对话框
  ss_esi.py <pid> filedlg   <out> <xml路径>    在文件对话框里填路径并点「打开」，dump 结果
  ss_esi.py <pid> find      <关键字>           在 EsiProfileTreeView 里找含关键字的条目
  ss_esi.py <pid> close     <out>              点 ESI库 的 关闭（cancelButton）
  ss_esi.py <pid> msgbox    <out> [按钮名]     读 Sysmac 消息框全文并点该按钮（默认 确定）

**硬前置（2026-11-08 实测）**：点「安装(文件)」时若本机还开着别的 Sysmac Studio 实例，
会弹 MessageBoxView：「安装未执行。因为正在运行多个Sysmac Studio，无法执行安装。
请关闭其它Sysmac Studio，然后重试。」——安装 ESI 必须先收敛到**单实例**。

只做用户点名的动作：不碰卸载、不碰任何许可/序列号窗口。每一步都落盘证据。
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

MASTER_VM = 'Omron.Cxap.Modules.NexEcatConfigurationEditor.ViewModel.MasterDeviceTreeNode'
ESI_TITLE = 'ESI库'


def rect(c):
    r = M.prop(c, 'BoundingRectangle')
    try:
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return (0, 0, 0, 0)


def center(c):
    x, y, w, h = rect(c)
    return x + w // 2, y + h // 2


def windows(pid):
    # M.wins_of already filters IsWindowVisible and has no 'vis' key (unlike ss.wins_of).
    return [w for w in M.wins_of(pid) if w['rect'][2] > 60 and w['rect'][3] > 40]


def dlg(pid, title=ESI_TITLE):
    """The visible top-level window of `pid` whose title is/contains `title`."""
    for w in windows(pid):
        if w['title'] == title:
            return w
    for w in windows(pid):
        if title in (w['title'] or ''):
            return w
    return None


def by_id(root, aid, types=('ButtonControl', 'EditControl', 'ComboBoxControl', 'TreeControl')):
    for c in M.find_by_type(root, types, maxd=24):
        if (M.prop(c, 'AutomationId') or '') == aid:
            return c
    return None


def invoke(c, label=''):
    """InvokePattern first, real click on the control's own rect as fallback."""
    if c is None:
        return 'no control'
    try:
        c.GetInvokePattern().Invoke()
        return 'invoke'
    except Exception:
        pass
    x, y = center(c)
    if x <= 0 or y <= 0:
        return 'offscreen, no invoke'
    M.force_foreground(M.main_window(M.resolve_pid(sys.argv[1]))['hwnd'])
    time.sleep(0.3)
    M.left_click(x, y)
    return 'click@%d,%d' % (x, y)


def dump_all(pid, out, note=''):
    lines = []
    for w in windows(pid):
        lines.append('=== HWND=%d rect=%s cls=%r title=%r' %
                     (w['hwnd'], w['rect'], w['cls'][:44], w['title']))
        root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        if root is None:
            lines.append('  (no UIA root)')
            continue
        M.walk(root, 1, dict(all=True, depth=16, max_lines=60000, pat=False), lines)
    n = M.dump(out, '# ss_esi pid=%d %s' % (pid, note), lines)
    print('lines=%d -> %s' % (n, out))
    return n


def master_row(pid):
    mw = M.main_window(pid)
    root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    for c in M.find_by_type(root, ('TreeItemControl',), maxd=26):
        if (M.prop(c, 'Name') or '') == MASTER_VM:
            return c
    return None


def cmd_master(pid):
    c = master_row(pid)
    if c is None:
        print('master row NOT FOUND - is the EtherCAT editor the active document?')
        return 1
    print('master rect=%s selected=%s' % (rect(c), 'SELECTED' in M.line_of(c)))
    return 0


def cmd_open(pid, out):
    mw = M.main_window(pid)
    M.force_foreground(mw['hwnd'])
    time.sleep(0.4)
    c = master_row(pid)
    if c is None:
        print('master row NOT FOUND')
        return 1
    x, y = center(c)
    print('right-click master at %d,%d' % (x, y))
    M.right_click(x, y)
    time.sleep(0.9)
    hit = None
    for w, ctl, cnt in M.menu_popups(pid):
        for k in M.find_by_type(ctl, ('MenuItemControl',), maxd=8):
            nm = M.prop(k, 'Name') or ''
            if nm.replace(' ', '') == '显示ESI库':
                hit = (k, nm)
                break
        if hit:
            break
    if hit is None:
        print('显示ESI库 not in popup')
        M.esc(2)
        return 1
    k, nm = hit
    print('found %r enabled=%s rect=%s -> %s' %
          (nm, M.prop(k, 'IsEnabled'), rect(k), invoke(k, nm)))
    time.sleep(2.5)
    d = dlg(pid)
    print('ESI库 window: %r' % (d,))
    dump_all(pid, out, 'after 显示ESI库')
    return 0 if d else 1


def cmd_installbtn(pid, out):
    d = dlg(pid)
    if not d:
        print('ESI库 dialog not open')
        return 1
    M.force_foreground(d['hwnd'])
    time.sleep(0.4)
    root = auto.ControlFromHandle(wt.HWND(d['hwnd']))
    b = by_id(root, 'installFileButton')
    if b is None:
        print('installFileButton not found')
        return 1
    print('安装(文件) rect=%s -> %s' % (rect(b), invoke(b)))
    time.sleep(2.0)
    dump_all(pid, out, 'after 安装(文件)')
    return 0


def file_dialog(pid):
    """The Win32 common file dialog: class #32770, or a WPF window titled 打开/安装."""
    for w in windows(pid):
        if w['cls'].startswith('#32770'):
            return w
    for w in windows(pid):
        t = w['title'] or ''
        if t in ('打开', '安装', '选择ESI文件', 'Open') and w['hwnd'] != (dlg(pid) or {}).get('hwnd'):
            return w
    return None


def cmd_filedlg(pid, out, path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        print('no such file:', path)
        return 2
    w = file_dialog(pid)
    if not w:
        print('no file dialog; visible windows: %r' % [(x['hwnd'], x['title'], x['cls'][:30]) for x in windows(pid)])
        return 1
    print('file dialog hwnd=%d cls=%r title=%r rect=%s' % (w['hwnd'], w['cls'][:30], w['title'], w['rect']))
    M.force_foreground(w['hwnd'])
    time.sleep(0.4)
    root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
    # File name edit: the Win32 dialog nests Edit id='1148' INSIDE ComboBox id='1148'
    # (ComboBoxEx32).  Prefer the Edit - it is the one that reliably takes ValuePattern.
    target = None
    for types in (('EditControl',), ('ComboBoxControl',)):
        for aid in ('1148', '1001', 'FileNameComboBox', 'FileNameCombo'):
            target = by_id(root, aid, types)
            if target is not None and rect(target)[2] > 0:
                break
            target = None
        if target is not None:
            break
    if target is None:
        cands = [c for c in M.find_by_type(root, ('EditControl',), maxd=20) if rect(c)[2] > 40]
        target = cands[-1] if cands else None
    if target is None:
        print('no file-name edit found')
        dump_all(pid, out, 'filedlg: no edit')
        return 1
    print('file-name control %s id=%r rect=%s' %
          (M.prop(target, 'ControlTypeName'), M.prop(target, 'AutomationId'), rect(target)))
    ok = False
    try:
        target.GetValuePattern().SetValue(path)
        ok = True
        print('SetValue ok')
    except Exception as e:
        print('SetValue failed:', e.__class__.__name__)
    if not ok:
        x, y = center(target)
        M.left_click(x, y)
        time.sleep(0.3)
        auto.SendKeys('{Ctrl}a', waitTime=0.05)
        M.send_text(path) if hasattr(M, 'send_text') else auto.SendKeys(
            path.replace('{', '{{').replace('}', '{}}'), waitTime=0.01)
        print('typed path')
    time.sleep(0.6)
    # 打开(O) button: AutomationId '1' in the Win32 dialog, else Name starts with 打开.
    btn = by_id(root, '1', ('ButtonControl',))
    if btn is None or '打开' not in (M.prop(btn, 'Name') or ''):
        for c in M.find_by_type(root, ('ButtonControl',), maxd=20):
            nm = (M.prop(c, 'Name') or '').replace(' ', '')
            if nm.startswith('打开') or nm in ('Open', '确定', 'OK'):
                btn = c
                break
    if btn is None:
        print('no 打开 button')
        dump_all(pid, out, 'filedlg: no button')
        return 1
    print('打开 button %r rect=%s -> %s' % (M.prop(btn, 'Name'), rect(btn), invoke(btn)))
    time.sleep(3.0)
    dump_all(pid, out, 'after 打开 %s' % os.path.basename(path))
    return 0


def cmd_find(pid, key):
    d = dlg(pid)
    if not d:
        print('ESI库 dialog not open')
        return 1
    root = auto.ControlFromHandle(wt.HWND(d['hwnd']))
    tree = by_id(root, 'EsiProfileTreeView', ('TreeControl',))
    if tree is None:
        print('EsiProfileTreeView not found')
        return 1
    hits = 0
    for c in M.find_by_type(tree, ('TextControl', 'TreeItemControl'), maxd=12):
        nm = M.prop(c, 'Name') or ''
        if key.lower() in nm.lower():
            print('HIT %s %r rect=%s' % (M.prop(c, 'ControlTypeName'), nm, rect(c)))
            hits += 1
    print('hits=%d for %r' % (hits, key))
    return 0 if hits else 1


def cmd_close(pid, out):
    d = dlg(pid)
    if not d:
        print('ESI库 dialog not open')
        return 0
    root = auto.ControlFromHandle(wt.HWND(d['hwnd']))
    b = by_id(root, 'cancelButton')
    print('关闭 -> %s' % invoke(b))
    time.sleep(1.5)
    print('still open: %r' % (dlg(pid) is not None))
    if out and out != '-':
        dump_all(pid, out, 'after 关闭')
    return 0


def msgbox(pid):
    """Sysmac's WPF message box: Window Name='Sysmac Studio' **AutomationId='MessageBoxView'**
    (ClassName is just 'Window' - matching on ClassName finds nothing).  Measured 2026-11-08.
    Its text is a read-only Edit inside a ScrollViewer; the buttons are ListBoxItems
    wrapping a real ButtonControl (确定 / 是(Y) / 否(N) / 取消)."""
    for w in windows(pid):
        root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        if root is None:
            continue
        if (M.prop(root, 'AutomationId') or '') == 'MessageBoxView':
            return w, root
    return None, None


def cmd_msgbox(pid, out, want='确定'):
    w, root = msgbox(pid)
    if root is None:
        print('no MessageBoxView open')
        return 0
    texts = [M.prop(c, 'Name') or '' for c in M.find_by_type(root, ('PaneControl',), maxd=6)
             if (M.prop(c, 'ClassName') or '') == 'ScrollViewer']
    print('MSGBOX hwnd=%d rect=%s' % (w['hwnd'], w['rect']))
    for t in texts:
        print('TEXT: %s' % t.replace('\\n', '\n'))
    btns = [c for c in M.find_by_type(root, ('ButtonControl',), maxd=10)
            if (M.prop(c, 'Name') or '') and rect(c)[2] > 0]
    for b in btns:
        print('  button %r rect=%s enabled=%s' % (M.prop(b, 'Name'), rect(b), M.prop(b, 'IsEnabled')))
    hit = [b for b in btns if (M.prop(b, 'Name') or '').replace(' ', '') == want] or \
          [b for b in btns if want in (M.prop(b, 'Name') or '')]
    if not hit:
        print('button %r not found - left open' % want)
        return 1
    print('clicking %r -> %s' % (M.prop(hit[0], 'Name'), invoke(hit[0])))
    time.sleep(1.2)
    if out and out != '-':
        dump_all(pid, out, 'after msgbox %s' % want)
    return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    if not M.is_admin():
        print('WARN: not admin - UIA will be empty (UIPI). Run elevated (as administrator).')
    pid = M.resolve_pid(sys.argv[1])
    a = sys.argv[2].lower()
    if a == 'master':
        return cmd_master(pid)
    if a == 'open':
        return cmd_open(pid, sys.argv[3])
    if a == 'dump':
        dump_all(pid, sys.argv[3], 'manual dump')
        return 0
    if a == 'installbtn':
        return cmd_installbtn(pid, sys.argv[3])
    if a == 'filedlg':
        return cmd_filedlg(pid, sys.argv[3], sys.argv[4])
    if a == 'find':
        return cmd_find(pid, sys.argv[3])
    if a == 'close':
        return cmd_close(pid, sys.argv[3] if len(sys.argv) > 3 else '-')
    if a == 'msgbox':
        return cmd_msgbox(pid, sys.argv[3] if len(sys.argv) > 3 else '-',
                          sys.argv[4] if len(sys.argv) > 4 else '确定')
    print('unknown action', a)
    return 2


if __name__ == '__main__':
    sys.exit(main())