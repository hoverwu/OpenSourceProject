# -*- coding: utf-8 -*-
"""ss_ectree.py - EtherCAT 拓扑树**深度展开 + 层级落盘**（只读视图操作）。

作者：hoverwu ｜ 版本：0.2.0 ｜ 建立：2026-11-08 ｜ 非官方，必须**提权**运行
本版更新（0.2.0）：新增 subtree 动作（按行名子串定位→滚动入视野→只展开该行子树→落盘）；
pid 支持 auto（统一走 ss_uimap.resolve_pid）。

为什么要它：ss_ecat.py 的 --expand 用「点行 + VK_RIGHT」，遇到折叠层级深的树
（GX-JC06 端口 → 从站 → 端口 → …）只会展开第一层，拿不到真实父子关系。
本脚本改用 UIA 的 ExpandCollapsePattern 逐节点 Expand()，再按控件父子递归 dump，
所以能看出「某从站挂在哪个端口下」，这是复刻组态时"选中哪个位置"的唯一依据。

  ss_ectree.py <pid|auto> dump <out> [--expand] [--passes N]
        --expand  用 ExpandCollapsePattern 把所有可展开节点展开（默认做）
        --passes  最多扫几轮（默认 6；每轮总能把新露出的节点也展开）
  ss_ectree.py <pid|auto> subtree <out> <行名子串> [<行名子串> ...]
        对每个子串：在已实例化行里找 label 含该子串的行（找不到先 expand_all 再找），
        ScrollItemPattern.ScrollIntoView() 滚入视野，只对该行子树反复 Expand
        （最多 6 轮、每轮 sleep 0.5、一轮无动作即止），再从该行递归落盘。
        找不到的子串记 `# NOT FOUND`。

只改视图展开态，不改任何组态数据；不保存工程。
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
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

MASTER_VM = 'MasterDeviceTreeNode'


def rect(c):
    r = M.prop(c, 'BoundingRectangle')
    try:
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return (0, 0, 0, 0)


def row_texts(c, maxd=3):
    """行自身的文字：排除落在**子 TreeItem 矩形**里的 Text（父行 label 里会混进子行文字）。"""
    kids = []
    for k in c.GetChildren():
        if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
            continue
        for g in M.find_by_type(k, ('TreeItemControl',), maxd=12):
            kids.append(rect(g))
    out = []
    for t in M.find_by_type(c, ('TextControl',), maxd=maxd):
        nm = (M.prop(t, 'Name') or '').strip()
        if not nm:
            continue
        x, y, w, h = rect(t)
        cx, cy = x + w // 2, y + h // 2
        if any(rx <= cx < rx + rw and ry <= cy < ry + rh
               for rx, ry, rw, rh in kids):
            continue
        out.append(nm)
    return out


def texts(c, maxd=3):
    out = []
    for k in M.find_by_type(c, ('TextControl',), maxd=maxd):
        nm = (M.prop(k, 'Name') or '').strip()
        if nm:
            out.append(nm)
    return out


def kind_of(c):
    nm = M.prop(c, 'Name') or ''
    lb = ' '.join(texts(c, 2))
    if MASTER_VM in nm:
        return 'master'
    if re.match(r'^(X\d+|Internal Port)\b', lb):
        return 'port'
    if 'SlaveDeviceTreeNode' in nm:
        return 'slave'
    if 'Coupler' in nm or 'NXBus' in nm:
        return 'coupler'
    if 'NXUnit' in nm or 'Unit' in nm:
        return 'unit'
    if 'Port' in nm:
        return 'port'
    return 'other'


def node_no(c):
    for k in M.find_by_type(c, ('EditControl',), maxd=3):
        if (M.prop(k, 'AutomationId') or '') == 'editBox':
            try:
                return k.GetValuePattern().Value
            except Exception:
                return '?'
    return ''


def sel_of(c):
    try:
        return bool(c.GetSelectionItemPattern().IsSelected)
    except Exception:
        return 'SELECTED' in (M.line_of(c) or '')


def expand_state(c):
    try:
        p = c.GetExpandCollapsePattern()
        st = p.ExpandCollapseState
        names = {0: 'collapsed', 1: 'expanded', 2: 'partial', 3: 'leaf'}
        return names.get(st, str(st))
    except Exception:
        return '-'


def do_expand(c):
    """能展就展；返回是否有动作。"""
    try:
        p = c.GetExpandCollapsePattern()
        if p.ExpandCollapseState in (0, 2):      # collapsed / partial
            p.Expand()
            return True
    except Exception:
        return False
    return False


def tree(pid):
    r = auto.ControlFromHandle(wt.HWND(M.main_window(pid)['hwnd']))
    if r is None:
        return None
    for c in M.find_by_type(r, ('TreeControl',), maxd=26):
        if (M.prop(c, 'AutomationId') or '') == 'TopologyView':
            x, y, w, h = rect(c)
            if w > 0 and h > 0:
                return c
    return None


def walk(c, depth, out):
    """按控件父子递归；TreeItem 之间是父子关系，端口行是中间层。"""
    for k in c.GetChildren():
        if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
            continue
        x, y, w, h = rect(k)
        if w <= 0 or h <= 0:
            continue
        out.append(dict(depth=depth, c=k, kind=kind_of(k),
                        label=' | '.join(row_texts(k)), rect=(x, y, w, h),
                        no=node_no(k), sel=sel_of(k), st=expand_state(k),
                        vm=(M.prop(k, 'Name') or '')))
        walk(k, depth + 1, out)


def expand_all(t, max_rounds=3):
    """把当前**已实例化**的节点全部展开，返回本轮动作次数。"""
    n = 0
    for _ in range(max_rounds):
        act = 0
        stack = [t]
        seen = 0
        while stack:
            cur = stack.pop()
            for k in cur.GetChildren():
                if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
                    continue
                seen += 1
                if do_expand(k):
                    act += 1
                stack.append(k)
                if seen > 4000:
                    break
            if seen > 4000:
                break
        n += act
        if act == 0:
            break
        time.sleep(0.35)
    return n


def scroll_pct(t, v):
    """纵向滚动到 v%；横向不动。返回是否成功（不支持 ScrollPattern 时退键盘）。"""
    try:
        sp = t.GetScrollPattern()
        sp.SetScrollPercent(-1, v)          # -1 = NoScroll
        time.sleep(0.35)
        return True
    except Exception:
        pass
    try:
        t.SetFocus()
    except Exception:
        return False
    return False


def visible_rows(t):
    """当前已实例化的行，按屏幕 y 排序，附带首段文字的 x（= 树缩进）。"""
    rows = []
    for r in M.find_by_type(t, ('TreeItemControl',), maxd=14):
        x, y, w, h = rect(r)
        if w <= 0 or h <= 0:
            continue
        tx = None
        for k in M.find_by_type(r, ('TextControl',), maxd=2):
            nm = (M.prop(k, 'Name') or '').strip()
            if nm:
                kx, ky, kw, kh = rect(k)
                # 只要本行顶部的文字（父行里的子行文字在更下方）
                if ky < y + max(30, h // 2 if 'SlaveDeviceTreeNode' not in
                                (M.prop(r, 'Name') or '') else 30):
                    tx = kx
                    break
        rows.append(dict(c=r, y=y, x=(tx if tx is not None else x), h=h,
                         kind=kind_of(r),
                         label=' | '.join(row_texts(r)),
                         no=node_no(r), sel=sel_of(r), st=expand_state(r)))
    rows.sort(key=lambda d: d['y'])
    return rows


def merge(acc, new):
    """把新视口里的一屏接到已收集序列尾部，按整行内容做重叠去重。"""
    def sig(d):
        return (d['x'], d['label'], d['no'] if d['no'] != '?' else '')
    if not acc:
        return list(new)
    best = 0
    for k in range(min(len(acc), len(new)), 0, -1):
        if [sig(d) for d in acc[-k:]] == [sig(d) for d in new[:k]]:
            best = k
            break
    return acc + new[best:]


def cmd_dump(pid, out, passes):
    t = tree(pid)
    if t is None:
        print('TopologyView not found - 先打开 EtherCAT 组态页')
        return 2
    # 1) 自上而下滚一遍，把视口外的节点实例化并展开
    sp_ok = scroll_pct(t, 0)
    for v in range(0, 101, 10):
        if v and not sp_ok:
            break
        if v:
            scroll_pct(t, v)
        for _ in range(passes):
            if expand_all(t) == 0:
                break
    # 2) 回顶再走一遍，展开后内容变长，可能又露出新的可展开节点
    scroll_pct(t, 0)
    for _ in range(passes):
        if expand_all(t) == 0:
            break
    rows = []
    walk(t, 0, rows)
    total = sum(1 for _ in M.find_by_type(t, ('TreeItemControl',), maxd=14))
    lines = ['# ss_ectree pid=%d rows=%d  TreeItem=%d  scrollPattern=%s' %
             (pid, len(rows), total, sp_ok)]
    for r in rows:
        lines.append('%s%-6s no=%-4s %-9s sel=%-5s %-16s %s' % (
            '  ' * r['depth'], r['kind'], r['no'], r['st'], r['sel'],
            str(r['rect']), r['label'][:100]))
        if r['vm']:
            lines.append('%s  vm=%s' % ('  ' * r['depth'], r['vm'][:110]))
    if len(rows) < total:
        # 退化路径：拿不到完整父子关系时，补一份「按屏幕顺序 + 缩进」的清单
        lines.append('')
        lines.append('# 视图顺序（缩进=x 坐标；rows<total 时用这份）')
        for d in visible_rows(t):
            lines.append('y=%-5d x=%-5d %-6s no=%-4s %s' % (
                d['y'], d['x'], d['kind'], d['no'], d['label'][:100]))
    n = M.dump(out, '# ss_ectree fold/expand dump', lines)
    print('rows=%d total=%d -> %s (%d lines)' % (len(rows), total, out, n))
    return 0


def find_row(t, sub):
    """在已实例化行里找 label 含子串 sub 的第一行（label 是 row_texts 的本行文字）。"""
    rows = []
    walk(t, 0, rows)
    for r in rows:
        if sub in r['label']:
            return r
    return None


def scroll_to(row):
    """ScrollItemPattern.ScrollIntoView()；不支持时如实返回 False。"""
    try:
        row['c'].GetScrollItemPattern().ScrollIntoView()
        time.sleep(0.35)
        return True
    except Exception:
        return False


def deep_expand(row, rounds=6):
    """只展开该行子树：栈遍历 TreeItemControl 子节点，state in (0,2) 就 Expand，
    一轮无动作即止，最多 rounds 轮，每轮 sleep 0.5。返回是否最终无动作可展。"""
    c = row['c']
    for _ in range(rounds):
        act = 0
        stack = [c]
        while stack:
            cur = stack.pop()
            for k in cur.GetChildren():
                if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
                    continue
                if do_expand(k):
                    act += 1
                stack.append(k)
        if act == 0:
            return True
        time.sleep(0.5)
    return False


def cmd_subtree(pid, out, subs):
    t = tree(pid)
    if t is None:
        print('TopologyView not found - 先打开 EtherCAT 组态页')
        return 2
    M.force_foreground(M.main_window(pid)['hwnd'])
    time.sleep(0.3)
    lines = ['# ss_ectree subtree pid=%d subs=%r' % (pid, subs)]
    rc = 0
    for sub in subs:
        r = find_row(t, sub)
        if r is None:
            expand_all(t)
            r = find_row(t, sub)
        if r is None:
            lines.append('# NOT FOUND %r' % sub)
            rc = 1
            continue
        scroll_to(r)
        r = find_row(t, sub) or r          # 滚动后控件可能重新实例化，重新定位
        deep_expand(r)
        r = find_row(t, sub) or r          # 展开后刷新本行 st/rect
        rows = [dict(r, depth=0)]
        walk(r['c'], 1, rows)
        lines.append('## sub=%r rows=%d' % (sub, len(rows)))
        for d in rows:
            lines.append('%s%-6s no=%-4s %-9s sel=%-5s %-16s %s' % (
                '  ' * d['depth'], d['kind'], d['no'], d['st'], d['sel'],
                str(d['rect']), d['label'][:100]))
            if d['vm']:
                lines.append('%s  vm=%s' % ('  ' * d['depth'], d['vm'][:110]))
    n = M.dump(out, '# ss_ectree subtree dump', lines)
    print('-> %s (%d lines)' % (out, n))
    return rc


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    pid = M.resolve_pid(argv[0])
    act = argv[1]
    out = argv[2]
    passes = 6
    for i, a in enumerate(argv):
        if a == '--passes' and i + 1 < len(argv):
            passes = int(argv[i + 1])
    if act == 'dump':
        return cmd_dump(pid, out, passes)
    if act == 'subtree':
        subs = argv[3:]
        if not subs:
            print('subtree needs at least one 行名子串')
            print(__doc__)
            return 1
        return cmd_subtree(pid, out, subs)
    print('unknown action', act)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
