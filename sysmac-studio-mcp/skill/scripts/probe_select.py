# -*- coding: utf-8 -*-
"""probe_select.py —— TVM_SELECTITEM(TVGN_CARET) 到底改变了什么

作者：hoverwu ｜ 版本 0.1.0 ｜ 2026-11-06

为什么要测：Skill 里两份文档对同一件事给了相反的说法。
  - references/project-tree.md §3.1：`TVM_SELECTITEM(TVGN_CARET, h)` 能把光标移到
    **任意深度**，回读 `TVGN_CARET` 一致，不需要前台、锁屏也可用；
  - references/control-tree.md §6：`TVM_SELECTITEM`「到不了这棵树」，选中只能真实鼠标。
  - `ss_uimap.row_hit` 的注释又说：caret 在树没有键盘焦点时**读回来是 0**。

三句不可能同时为真。这个探针只发消息、不点鼠标、不抢前台，逐个回答：

  Q1 发完 TVM_SELECTITEM 后 `TVGN_CARET` 是否等于目标句柄？
  Q2 目标行是否因此带上 TVIS_SELECTED？（选中态 vs 光标态是不是两件事）
  Q3 上一个 caret 行是否被 deselect？（caret 是否等价于"选区"）
  Q4 前台不是 Sysmac 时以上结论是否改变？

用法：python probe_select.py [pid|auto] [out.txt] [树路径 ...]
      树路径是点分索引（如 0.0 / 1.0.2），默认 0.0 1.0；
      out 默认 <系统临时目录>/ss_probe_select.txt（运行时产物）。
"""
import os
import sys
import time
import tempfile

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)

import ss_uimap as U  # noqa: E402

L = []


def note(s):
    L.append(s)
    print(s)


def flags(thw, h):
    if not h:
        return '-'
    st = U.sm(thw, U.TVM_GETITEMSTATE, h, 0xFFFFFFFF) & 0xFFFFFFFF
    return ('0x%08X' % st) + (' SEL' if st & U.TVIS_SELECTED else '') + \
           (' EXP' if st & U.TVIS_EXPANDED else '')


def main():
    pid = U.resolve_pid(sys.argv[1] if len(sys.argv) > 1 else 'auto')
    out = (sys.argv[2] if len(sys.argv) > 2
           else os.path.join(tempfile.gettempdir(), 'ss_probe_select.txt'))
    paths = sys.argv[3:] or ['0.0', '1.0']
    thw = U.tree_hwnd(pid)
    mw = U.main_window(pid)
    fg = U.u.GetForegroundWindow()
    note('# probe_select pid=%d tree=%d title=%r' % (pid, thw, mw['title']))
    note('# foreground hwnd=%d isSysmac=%s  tree_has_focus=%s'
         % (fg, fg == mw['hwnd'], U.tree_has_focus(thw)))
    note('# 全程只发消息：不点鼠标、不抢前台、不敲键盘')

    for ps in paths:
        h = U.node_at(thw, [int(x) for x in ps.split('.')])
        if not h:
            note('\n## %s MISSING' % ps)
            continue
        before_caret = U.caret_of(thw)
        note('\n## %s  h=%d  %r  kids=%d'
             % (ps, h, U.node_text(pid, thw, h)[0], len(U.kids_of(thw, h))))
        note('  光标在别处时：caret=%s(%s) 目标flags=%s'
             % (before_caret, flags(thw, before_caret), flags(thw, h)))
        U.sm(thw, U.TVM_SELECTITEM, U.TVGN_CARET, h)
        time.sleep(0.2)
        after = U.caret_of(thw)
        note('  Q1 发消息后 TVGN_CARET == 目标？ %s (read %d)'
             % ('是' if after == h else '否', after))
        note('  Q2 目标因此带 TVIS_SELECTED？ %s  flags=%s'
             % ('是' if U.selected(thw, h) else '否', flags(thw, h)))
        if before_caret and before_caret != h:
            note('  Q3 原 caret 行 %r 现在还被选中？ %s  flags=%s'
                 % (U.node_text(pid, thw, before_caret)[0],
                    '是' if U.selected(thw, before_caret) else '否',
                    flags(thw, before_caret)))
        note('  可见化：软件是否把该行滚进视野（TV_GETNEXTITEM FIRSTVISIBLE 对照） '
             '%s' % ('是' if h in [b for b, _y, _r in U.realised_band(pid, thw)]
                     else '否（还在视口外）'))

    note('\n## Q4 前台切走再试一次（点记事本不算，用最小化 Sysmac 主窗口）')
    U.u.ShowWindow(mw['hwnd'], 6)          # SW_MINIMIZE
    time.sleep(1.0)
    h = U.node_at(thw, [int(x) for x in paths[0].split('.')])   # 复用第一个树路径
    if h:
        note('  最小化后 tree 还在吗=%s  caret=%s' % (bool(U.tree_hwnd(pid)), U.caret_of(thw)))
        U.sm(thw, U.TVM_SELECTITEM, U.TVGN_CARET, h)
        time.sleep(0.2)
        note('  Q1 最小化下仍能移动光标？ %s' % ('是' if U.caret_of(thw) == h else '否'))
        note('  Q2 最小化下选中态？ %s' % ('是' if U.selected(thw, h) else '否'))
    U.u.ShowWindow(mw['hwnd'], 9)          # SW_RESTORE
    time.sleep(0.8)
    note('# restored, foreground=%d' % U.u.GetForegroundWindow())

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    note('# -> %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
