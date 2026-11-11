# -*- coding: utf-8 -*-
"""ss_save.py - 真的按 Ctrl+S 保存目标工程，并把"文件到底变了没有"作为唯一判据。

作者：hoverwu ｜ 版本：0.3.0 ｜ 本版更新：开源可移植整理（去掉本机默认工程路径，--file 必填）

为什么需要它：Skill 里其他脚本**全都不落盘**——界面写了一百个参数，`.smc2` 还是旧的，
`ss_axcmp.py` 自然什么都比不出来。所以"写完 → 保存 → 用归档复核"这条线里，保存这一步
必须有脚本、必须有证据（sha256 变了才算保存成功）。

它做的事很克制：
1. 记下目标 `.smc2` 当前 sha256；
2. `force_foreground` + **真** Ctrl+S（`combo(0x11, 0x53)`，不是 UIA Invoke）；
3. 在 +1/+3/+5/+8 s 各拍一张全图、枚举一次弹层、算一次 sha256；**文件一变就停**；
4. 任何弹层都**只记录文字不动手**——包括保存轴改动时可能冒出来的确认框；
   提到 许可/License/序列号/激活 的窗口一律不碰，只写进日志。

  python ss_save.py <pid|auto> [out_prefix] --file <目标.smc2> [--out <目录>] [--esc N] [--menu]

`--file` **必填**：要验证 sha256 的目标 `.smc2` 路径（没有默认值，缺了直接退出码 2）。
`--out` 可选：截图与日志的输出目录，默认 `<脚本目录>/logs`（运行时产物，不要提交）。
`--esc N`（默认 2）保存前先按 N 次 Esc 关掉残留弹层；`--menu` 完全跳过 Ctrl+S，
直接走 UIA 的 `文件(F) > 保存`——实测菜单项 Name 是 `保存(S)` 这种带访问键后缀的形式，
脚本会先剥后缀再匹配，所以它不依赖键盘焦点，弹层没关也能保存。

要看"这次保存写进去了什么"，接着跑 `ss_axcmp.py <源.smc2> <目标.smc2>`。
"""
import argparse
import ctypes
import hashlib
import os
import re
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ctypes.wintypes as wt                                              # noqa: E402
from PIL import ImageGrab                                                 # noqa: E402
import uiautomation as auto                                               # noqa: E402
import ss_uimap as U                                                      # noqa: E402
import ss_axis as A                                                       # noqa: E402

WATCH_WORDS = ('许可', 'License', '序列号', '激活', 'Registration')
DIR = os.path.join(HERE, 'logs')          # 运行时产物目录，可用 --out 覆盖；不要提交

u32 = ctypes.windll.user32
u32.GetWindowLongW.restype = ctypes.c_long
u32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
u32.IsWindowVisible.restype = ctypes.c_bool
u32.IsWindowVisible.argtypes = [wt.HWND]


def sha(p):
    try:
        return hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16]
    except Exception:
        return '-'


def pop_lines(pid, lines, tag):
    lines.append('---- %s' % tag)
    for w in U.popup_roots(pid):
        nm = ''
        try:
            nm = (U.prop(auto.ControlFromHandle(wt.HWND(w['hwnd'])), 'Name') or '')[:120]
        except Exception:
            pass
        flag = '  << 许可类，绝不操作' if any(t in (w.get('title', '') + nm)
                                            for t in WATCH_WORDS) else ''
        lines.append('  POP cls=%s title=%r name=%r rect=%s vis=%s ex=%s%s'
                     % (w['cls'][:34], w.get('title', ''), nm, w['rect'],
                        bool(u32.IsWindowVisible(wt.HWND(w['hwnd']))),
                        hex(u32.GetWindowLongW(wt.HWND(w['hwnd']), -20)),
                        flag))
        try:
            c = auto.ControlFromHandle(wt.HWND(w['hwnd']))
            kids = U.find_by_type(c, ('Text', 'Button', 'Document', 'MenuItem', 'List'),
                                  maxd=12)[:30]
            for k in kids:
                t = (U.prop(k, 'Name') or '').strip()
                if t:
                    lines.append('      %-14s %r' % (k.ControlTypeName, t[:120]))
            if not kids:
                lines.append('      (弹层里没有 Text/Button/Document/MenuItem/List 子节点)')
        except Exception:
            pass
    lines.append('  docs=%s' % sorted(A.doc_names(U.main_window(pid))))


ACCENT = re.compile(r'\s*[（(]\w[)）](\s*\.\.\.)?\s*$')


def bare(name):
    """菜单项 Name 实测带访问键后缀：'保存(S)'、'另存为(A)...'、'关闭(C)'。

    control-tree.md §5 记的是去掉后缀的中文标题，所以按标题匹配必须先剥掉它，
    否则 `menu_item(pid,'文件(F)','保存')` 会在弹层里找不到（实测 `item '保存' not found`，
    而弹层里明明有 `保存(S)`）。
    """
    return ACCENT.sub('', (name or '').strip())


def menu_save(pid, lines):
    """打开 文件(F) 并点 '保存' —— 不依赖键盘，弹层残留在也能走。"""
    mw = U.main_window(pid)
    root = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    top = None
    for it in U.menu_bar_items(root):
        if bare(U.prop(it, 'Name')).startswith('文件'):
            top = it
            break
    if top is None:
        lines.append('# 菜单兜底：没找到 文件(F) 顶层项')
        return False
    lines.append('# 打开 文件(F)：%s' % U.open_menu(top))
    time.sleep(0.8)
    target = None
    for w, c, n in U.menu_popups(pid):
        for k in U.find_by_type(c, ('MenuItemControl',), maxd=8):
            nm = bare(U.prop(k, 'Name'))
            if nm == '保存':
                target = k
                break
        if target is not None:
            break
    if target is None:
        lines.append('# 菜单兜底：弹层里没有 保存 / 保存(S)')
        U.close_menu()
        return False
    try:
        target.Click(simulateMove=False)
        how = 'click'
    except Exception:
        target.GetInvokePattern().Invoke()
        how = 'invoke'
    lines.append('# 点了 文件>保存（%s）' % how)
    time.sleep(1.0)
    return True


def changed_since(target, before, pid, lines, how):
    """poll sha256 for ~10 s, logging popups; return (did_change, secs)."""
    t0 = time.time()
    for d in (1.0, 3.0, 5.0, 8.0):
        time.sleep(d if d == 1.0 else 2.0)
        pop_lines(pid, lines, '%s +%.0fs' % (how, d))
        after = sha(target)
        if after != before:
            lines.append('# FILE CHANGED sha=%s at +%.0fs (%s)' % (after, d, how))
            return True, d
    return False, time.time() - t0


def main():
    ap = argparse.ArgumentParser(
        description='真的按 Ctrl+S 保存目标工程，并以 sha256 是否变化为唯一判据。')
    ap.add_argument('pid', help='目标 Sysmac 进程 pid，或 auto')
    ap.add_argument('prefix', nargs='?', default='save1',
                    help='输出文件名前缀（默认 save1）')
    ap.add_argument('--file', required=True,
                    help='目标 .smc2 路径（必填，用于校验 sha256）')
    ap.add_argument('--out', default=DIR,
                    help='截图与日志输出目录（默认 <脚本目录>/logs）')
    ap.add_argument('--esc', type=int, default=2,
                    help='保存前按 Esc 的次数（默认 2，0=不按）')
    ap.add_argument('--menu', action='store_true',
                    help='跳过 Ctrl+S，直接走 文件(F) > 保存')
    args = ap.parse_args()

    out_dir = args.out
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    pid = U.resolve_pid(args.pid)
    pre = args.prefix
    target = args.file
    nesc = args.esc
    mw = U.main_window(pid)
    lines = ['# ss_save pid=%s title=%r file=%r' % (pid, mw['title'], os.path.basename(target))]
    before = sha(target)
    lines.append('# before sha=%s' % before)
    ImageGrab.grab(all_screens=True).save(
        os.path.join(out_dir, '%s_before.png' % pre))
    # 实测：表格里**没关的下拉**是一个独立的 `HwndWrapper[...]` 顶层小窗（93×31），
    # 它会吃掉键盘——Ctrl+S 按下去一点反应都没有，文件纹丝不动（pitfalls §32 的保存版）。
    if nesc:
        U.force_foreground(mw['hwnd'])
        time.sleep(0.5)
        U.esc(nesc)
        lines.append('# pressed Esc x%d to kill lingering popups' % nesc)
        time.sleep(0.6)
    if not args.menu:
        U.force_foreground(mw['hwnd'])
        time.sleep(0.6)
        A.combo(0x11, 0x53)                   # real Ctrl+S
        ok, secs = changed_since(target, before, pid, lines, 'after Ctrl+S')
    else:
        ok, secs = False, 0.0
        lines.append('# --menu：跳过 Ctrl+S，直接走菜单')
    if not ok:
        lines.append('# Ctrl+S 没落盘（%s） - 兜底：文件(F) > 保存' % _why_not_saved(secs))
        try:
            if menu_save(pid, lines):
                ok, secs = changed_since(target, before, pid, lines, 'after 文件>保存')
        except Exception as e:
            lines.append('# 菜单兜底失败 %s: %s' % (e.__class__.__name__, str(e)[:120]))
        U.close_menu()
    lines.append('# after sha=%s' % sha(target))
    try:
        z = zipfile.ZipFile(target)
        lines.append('# archive members=%d' % len(z.namelist()))
    except Exception as e:
        lines.append('# archive open failed %r' % (e,))
    lines.append('#### %s' % ('SAVED (+%.0fs)' % secs if ok
                              else 'FILE UNCHANGED - 要么工程本来不脏，要么键盘没落到该实例'))
    out_txt = os.path.join(out_dir, '%s.txt' % pre)
    U.dump(out_txt, lines[0], lines[1:])
    print('#### %s -> %s' % ('SAVED' if ok else 'UNCHANGED', out_txt))
    return 0 if ok else 1


def _why_not_saved(secs):
    return '等了 %.0fs' % secs


if __name__ == '__main__':
    sys.exit(main())
