# -*- coding: utf-8 -*-
"""ss_ecat_build.py - 按计划表在 EtherCAT 拓扑里**逐个右击插入**从站并回填设备名/节点号。

作者：hoverwu ｜ 版本：0.3.0 ｜ 建立：2026-11-08 ｜ 非官方，必须**提权**运行

与 ss_ecat.py 的分工：ss_ecat.py 是单步交互（rows/search/insert/delete/name），
本脚本把"选中位置 → 选中硬件 → 右击插入(I) → 改设备名 → (最后)改节点号 → 校验"
串成一步，并按 JSON 计划表批量执行，每步各自落盘，便于对照源工程逐条复现。

**全程没有 drag 代码路径**：位置靠"选中行 + 右击工具箱结果 → 插入(I)"。

------------------------------------------------------------------ 两条实测语义

1) **插入 Main device 是"一对"**
   GX-JC06(IN,X2,X3) Main device 插入后，软件自动在该 Main 的 Internal Port 下
   再挂一个 GX-JC06(X4,X5,X6) Sub-device（默认名 E00x）。两个节点各占一个节点号。
   计划里用 sub_name / sub_node 描述这个自动生成的从站。

2) **插入落在所选端口的"头部"，且会自动重排节点号**
   → 同一端口上的菊花链必须**倒序插入**（计划里先写链尾），最终顺序才与源工程一致；
   → 每次插入都会重排全网络节点号，所以**节点号最后统一写**（renumber 子命令）。

------------------------------------------------------------------ 计划表

UTF-8 JSON 数组，按顺序执行：

  [
    {"step": 1, "parent": "master", "port": "",
     "kw": "GX-JC06", "pick": "GX-JC06(IN,X2,X3) Main device",
     "name": "耦合器1", "node": "1",
     "sub_name": "耦合器1Sub", "sub_node": "32"},
    {"step": 2, "parent": "耦合器1", "port": "X2",
     "kw": "NX-ECC203", "pick": "NX-ECC203",
     "name": "NX耦合器2", "node": "3"}
  ]

  parent：master = 主设备；否则是**父从站行 label 里的唯一子串**（常用设备名）
  port  ：留空=挂在父行本身（只对 master 有意义）；否则是该从站的端口行标签
          X2 / X3 / X4 / X5 / X6 / Internal Port
  pick  ：在该关键字的结果里挑包含这个子串的那一行（"Main device" 之类）
  node  ：留给 renumber 阶段写（插入阶段只校验设备名）
  sub_* ：仅 Main+Sub 成对插入时使用

执行方式：
  ss_ecat_build.py <pid> <plan.json> <logdir> [--from N] [--to N] [--dry] [--save-each]
  ss_ecat_build.py <pid> renumber <plan.json> <logdir> [--dry] [--only "名1||名2"]

  --save-each：每步成功后立即 文件(F) > 保存。**强烈建议开**：组态只存在进程内存里，
               应用一关全部丢失（实测 2026-11-08：建完 16 步没落盘，进程退出后
               .smc2 的 mtime 还停在建之前，整轮白做）。

判据：插入阶段要求「新行出现 + 设备名读回 == 计划值（Main 与 Sub 各一次）」；
renumber 阶段要求「逐行节点号读回 == 计划值 + 从设备数量 == 计划节点数」。
任何一步失败立即停止（不自动换路线、不重试拖拽），已成功的步骤保留。
"""
import ctypes
import ctypes.wintypes as wt
import json
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
import ss_ecat_name as N                                                # noqa: E402

auto.SetGlobalSearchTimeout(6)

MASTER_VM = 'MasterDeviceTreeNode'


# ------------------------------------------------------------------ 基础

def rect(c):
    r = M.prop(c, 'BoundingRectangle')
    try:
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return (0, 0, 0, 0)


def center(c):
    x, y, w, h = rect(c)
    return x + w // 2, y + h // 2


def header_point(r):
    """行矩形覆盖整棵子树，必须点行首那条标题带；行心会落到子行上。"""
    if not isinstance(r, tuple):
        r = rect(r)
    x, y, w, h = r
    return x + min(300, max(60, w // 3)), y + 18


def texts(c, maxd=4):
    out = []
    for k in M.find_by_type(c, ('TextControl',), maxd=maxd):
        nm = (M.prop(k, 'Name') or '').strip()
        if nm:
            out.append(nm.strip())
    return out


def label(c):
    return ' | '.join(texts(c))


def row_texts(c, maxd=3):
    """只取这一行自己的文字：剔除落在**子 TreeItem 矩形**内的 Text。

    父行的 UIA 子树包含所有后代行，直接 texts() 会让父行 label 含全部子孙文字，
    导致 find_slave 把祖先当成目标（实测 2026-11-08：Sub 被挂到错的 Main 上）。
    """
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


def row_label(c, maxd=3):
    return ' | '.join(row_texts(c, maxd))


def kind_of(c):
    nm = M.prop(c, 'Name') or ''
    lb = row_label(c, 2)
    if MASTER_VM in nm:
        return 'master'
    if re.match(r'^(X\d+|Internal Port)\b', lb):
        return 'port'
    if 'SlaveDeviceTreeNode' in nm:
        return 'slave'
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


def is_sel(c):
    try:
        return bool(c.GetSelectionItemPattern().IsSelected)
    except Exception:
        return 'SELECTED' in (M.line_of(c) or '')


def tap(vk, delay=0.08):
    u = ctypes.windll.user32
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(delay)
    u.keybd_event(vk, 0, 2, 0)
    time.sleep(delay)


def set_clip(text):
    u = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = (ctypes.c_void_p,)
    k32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    u.SetClipboardData.restype = ctypes.c_void_p
    u.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    data = text.encode('utf-16-le') + b'\x00\x00'
    u.OpenClipboard(0)
    try:
        u.EmptyClipboard()
        h = k32.GlobalAlloc(0x0002, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u.SetClipboardData(13, h)
    finally:
        u.CloseClipboard()


def ctrl_key(vk):
    u = ctypes.windll.user32
    u.keybd_event(0x11, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.15)


def paste(text):
    set_clip(text)
    time.sleep(0.15)
    ctrl_key(0x56)


def root_of(pid):
    return auto.ControlFromHandle(wt.HWND(M.main_window(pid)['hwnd']))


def find_aid(pid, aid, types=('TreeControl',), maxd=26):
    r = root_of(pid)
    if r is None:
        return None
    for c in M.find_by_type(r, types, maxd=maxd):
        if (M.prop(c, 'AutomationId') or '') == aid:
            x, y, w, h = rect(c)
            if w > 0 and h > 0:
                return c
    return None


def tree(pid):
    return find_aid(pid, 'TopologyView')


def focus(pid):
    M.force_foreground(M.main_window(pid)['hwnd'])
    time.sleep(0.35)


def expand(c):
    try:
        p = c.GetExpandCollapsePattern()
        if p.ExpandCollapseState in (0, 2):
            p.Expand()
            time.sleep(0.45)
            return True
    except Exception:
        pass
    return False


def scroll_into(c):
    try:
        c.GetScrollItemPattern().ScrollIntoView()
        time.sleep(0.3)
    except Exception:
        pass


def select_row(row, verify=True):
    """UIA 选中 + 点一下标题带（让软件自己也认这个插入点）。"""
    try:
        row['c'].GetSelectionItemPattern().Select()
        time.sleep(0.25)
    except Exception:
        pass
    x, y = header_point(row['rect'])
    M.left_click(x, y)
    time.sleep(0.5)
    return is_sel(row['c']) if verify else True


# ------------------------------------------------------------------ 树遍历

def walk(c, depth=0, out=None):
    if out is None:
        out = []
    for k in c.GetChildren():
        if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
            continue
        x, y, w, h = rect(k)
        out.append(dict(c=k, depth=depth, kind=kind_of(k), label=row_label(k),
                        rect=(x, y, w, h), no=node_no(k), sel=is_sel(k)))
        if h > 0:
            walk(k, depth + 1, out)
    return out


def find_slave(t, s):
    for r in walk(t):
        if r['kind'] == 'slave' and s in r['label']:
            return r
    return None


def find_master(t):
    for r in walk(t):
        if r['kind'] == 'master':
            return r
    return None


def child_ports(row):
    out = []
    for k in row['c'].GetChildren():
        if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
            continue
        if kind_of(k) == 'port':
            out.append(dict(c=k, kind='port', label=row_label(k), rect=rect(k),
                            no='', sel=is_sel(k)))
    return out


def direct_slaves(row):
    out = []
    for k in row['c'].GetChildren():
        if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
            continue
        if kind_of(k) == 'slave':
            out.append(dict(c=k, kind='slave', label=row_label(k), rect=rect(k),
                            no=node_no(k), sel=is_sel(k)))
    return out


def ensure_row(pid, t, pred, desc, tries=3):
    """找到行；找不到就先展开整棵已实例化的树、再滚一遍（视口变化不影响 UIA）。"""
    for i in range(tries):
        r = pred()
        if r is not None:
            scroll_into(r['c'])
            return r
        # 展开一轮：深层的行要先展开父行才会实例化
        expand_tree(t)
        time.sleep(0.5)
        if i >= 1:
            # 还找不到就滚一遍，让视口外的行实例化后再展开
            sweep_expand(t)
            r = pred()
            if r is not None:
                scroll_into(r['c'])
                return r
    return None


def sweep_expand(t):
    """上下滚动一遍并展开，逼出视口外尚未实例化的行。只改视图。"""
    try:
        sp = t.GetScrollPattern()
    except Exception:
        return False
    for v in range(0, 101, 10):
        try:
            sp.SetScrollPercent(-1, v)
        except Exception:
            return False
        time.sleep(0.3)
        expand_tree(t)
    try:
        sp.SetScrollPercent(-1, 0)
    except Exception:
        pass
    time.sleep(0.3)
    return True


def expand_tree(t):
    """按 UIA 展开当前已实例化的所有节点（只改视图）。"""
    for _ in range(4):
        act = 0
        stack = [t]
        while stack:
            cur = stack.pop()
            for k in cur.GetChildren():
                if (M.prop(k, 'ControlTypeName') or '') != 'TreeItemControl':
                    continue
                try:
                    p = k.GetExpandCollapsePattern()
                    if p.ExpandCollapseState in (0, 2):
                        p.Expand()
                        act += 1
                except Exception:
                    pass
                stack.append(k)
        if act == 0:
            break
        time.sleep(0.45)


# ------------------------------------------------------------------ 工具箱

def search_box(pid):
    return find_aid(pid, 'SearchTextBox', ('EditControl',))


def result_list(pid):
    return find_aid(pid, 'ItemListBox', ('ListControl',))


def ensure_toolbox(pid, tries=3):
    """右下角是「工具箱 / 查找和替换」两个页签，被切走时 SearchTextBox 会消失。
    找不到搜索框就点回「工具箱」页签（实测页签是 PaneControl，不是 TabItemControl）。"""
    for _ in range(tries):
        if search_box(pid) is not None:
            return True
        r = root_of(pid)
        hit = None
        for c in M.find_by_type(r, ('PaneControl', 'TabItemControl'), maxd=26):
            if (M.prop(c, 'Name') or '').strip() == '工具箱':
                x, y, w, h = rect(c)
                if w > 0 and h > 0:
                    hit = c
                    break
        if hit is None:
            time.sleep(0.6)
            continue
        x, y = center(hit)
        M.left_click(x, y)
        time.sleep(0.9)
    return search_box(pid) is not None


def results(pid):
    lst = result_list(pid)
    if lst is None:
        return []
    out = []
    for c in M.find_by_type(lst, ('ListItemControl',), maxd=4):
        out.append(dict(c=c, label=label(c), rect=rect(c)))
    out.sort(key=lambda d: d['rect'][1])
    return out


def type_query(pid, kw):
    box = search_box(pid)
    if box is None:
        return False
    x, y = center(box)
    M.left_click(x, y)
    time.sleep(0.3)
    ctrl_key(0x41)
    paste(kw)
    time.sleep(2.2)
    return True


def set_all_versions(pid, want=False):
    """把「显示所有版本」强制成指定状态（False = 只列当前推荐版本）。"""
    r = root_of(pid)
    for c in M.find_by_type(r, ('CheckBoxControl',), maxd=26):
        if (M.prop(c, 'Name') or '') == '显示所有版本':
            try:
                st = c.GetTogglePattern().ToggleState
                if bool(st) != bool(want):
                    c.GetTogglePattern().Toggle()
                    time.sleep(0.9)
                return bool(want)
            except Exception:
                return None
    return None


# ------------------------------------------------------------------ 参数表

def param_row(pid, title):
    r = root_of(pid)
    for c in M.find_by_type(r, ('ListItemControl',), maxd=28):
        ts = texts(c, 3)
        if ts and ts[0] == title:
            return c, ts
    return None, []


def slave_count(pid):
    """选中主设备后读「从设备数量」。会改变选中项（视图态）。"""
    t = tree(pid)
    m = find_master(t)
    if m is None:
        return None
    scroll_into(m['c'])
    select_row(m)
    time.sleep(0.5)
    _, ts = param_row(pid, '从设备数量')
    return ts[-1] if ts else None


def set_node_no(row, no):
    for k in M.find_by_type(row['c'], ('EditControl',), maxd=3):
        if (M.prop(k, 'AutomationId') or '') == 'editBox':
            x, y = center(k)
            M.left_click(x, y)
            time.sleep(0.25)
            ctrl_key(0x41)
            paste(no)
            time.sleep(0.3)
            tap(0x0D)
            time.sleep(0.9)
            try:
                return k.GetValuePattern().Value
            except Exception:
                return '?'
    return None


# ------------------------------------------------------------------ 插入

def menu_insert(pid, ctl):
    """右击工具箱结果 → 插入(I)。没有任何拖拽分支。"""
    x, y = center(ctl)
    M.right_click(x, y)
    time.sleep(0.9)
    items = []
    for w, c, cnt in M.menu_popups(pid):
        for k in M.find_by_type(c, ('MenuItemControl',), maxd=8):
            items.append(k)
    names = [(M.prop(k, 'Name') or '') for k in items]
    hit = [k for k in items if '插入' in (M.prop(k, 'Name') or '')]
    if not hit:
        M.esc(2)
        return False, 'no 插入 in popup: %r' % names
    k = hit[0]
    try:
        k.GetInvokePattern().Invoke()
        how = 'invoke'
    except Exception:
        cx, cy = center(k)
        M.left_click(cx, cy)
        how = 'click'
    time.sleep(2.0)
    return True, '%s popup=%r' % (how, names)


def locate_target(pid, t, p):
    """每次都重新 walk：插入后控件会重建，旧引用不可复用。"""
    if p.get('parent') == 'master':
        parent = ensure_row(pid, t, lambda: find_master(t), 'master')
        if parent is None:
            return None, None, 'master row not found'
    else:
        parent = ensure_row(pid, t, lambda: find_slave(t, p['parent']), p['parent'])
        if parent is None:
            return None, None, 'parent slave %r not found' % p['parent']
    target = parent
    if p.get('port'):
        expand(parent['c'])
        time.sleep(0.5)
        want = p['port'].lower()
        hit = None
        for k in child_ports(parent):
            if k['label'].lower().startswith(want):
                hit = k
                break
        if hit is None:
            return parent, None, 'port %r not found; ports=%r' % (
                p['port'], [k['label'] for k in child_ports(parent)])
        target = hit
    return parent, target, ''


def locate_new(t, target, pick):
    """新行 = 选中且匹配 pick 的从站；否则取端口下的第一个从站（头插）。"""
    pl = (pick or '').lower()
    for r in walk(t):
        if r['kind'] == 'slave' and r['sel'] and (not pl or pl in r['label'].lower()):
            return r
    for r in direct_slaves(target):
        if not pl or pl in r['label'].lower():
            return r
    kids = direct_slaves(target)
    return kids[0] if kids else None


def main_subs(t, main_name, tries=3):
    """Main 的 Internal Port 下的直接从站（= 自动生成的 Sub-device）。

    实测：刚插入时 Main 行是**折叠**的，孩子行还没实例化，直接 GetChildren 拿到空；
    必须先 Expand 主干行、再 Expand Internal Port，然后重新 walk 取新控件。
    """
    for _ in range(tries):
        row = find_slave(t, main_name)
        if row is None:
            return []
        expand(row['c'])
        time.sleep(0.7)
        row = find_slave(t, main_name)
        if row is None:
            return []
        for pp in child_ports(row):
            if pp['label'].lower().startswith('internal port'):
                expand(pp['c'])
                time.sleep(0.7)
                kids = direct_slaves(pp)
                if kids:
                    return kids
        time.sleep(0.5)
    return []


def dump_tree(t, path):
    lines = []
    for r in walk(t):
        lines.append('%s%-6s no=%-4s sel=%-5s %-18s %s' % (
            '  ' * r['depth'], r['kind'], r['no'], r['sel'],
            str(r['rect']), r['label'][:110]))
    M.dump(path, '# ss_ecat_build tree', lines)
    return len(lines)


def run_step(pid, t, p, logdir, dry=False):
    """插入+命名一步。返回 (ok, log lines)。"""
    L = []
    L.append('== step %s  parent=%r port=%r kw=%r pick=%r name=%r sub=%r' % (
        p.get('step'), p.get('parent'), p.get('port'), p.get('kw'),
        p.get('pick'), p.get('name'), p.get('sub_name')))

    # ---- 1) 选插入位置
    parent, target, err = locate_target(pid, t, p)
    if target is None:
        return False, L + ['FAIL: ' + err]
    scroll_into(target['c'])
    sel_ok = select_row(target)
    L.append('  target: %s %s sel=%s' % (target['kind'], target['label'][:80], sel_ok))
    if dry:
        return True, L + ['DRY: stop before toolbox']

    # ---- 2) 选硬件
    if not ensure_toolbox(pid):
        return False, L + ['FAIL: 工具箱页签/SearchTextBox not found']
    if not type_query(pid, p['kw']):
        return False, L + ['FAIL: SearchTextBox not found']
    rs = results(pid)
    L.append('  results=%d' % len(rs))
    for i, d in enumerate(rs):
        L.append('    %2d %s' % (i, d['label']))
    pick = p.get('pick') or ''
    cand = [d for d in rs if pick.lower() in d['label'].lower()] if pick else rs
    if not cand:
        return False, L + ['FAIL: no result contains pick %r' % pick]
    d = cand[0]
    L.append('  picked: %s' % d['label'])
    hx, hy = center(d['c'])
    M.left_click(hx, hy)
    time.sleep(0.5)

    # ---- 3) 右击 → 插入(I)
    ok, info = menu_insert(pid, d['c'])
    L.append('  menu_insert ok=%s %s' % (ok, info))
    if not ok:
        return False, L

    # ---- 4) 定位新行（树已重建：重新 walk，按 IsSelected / 头插判定）
    time.sleep(1.2)
    parent, target, err = locate_target(pid, t, p)
    if target is None:
        return False, L + ['FAIL after insert: ' + err]
    expand(target['c'])
    time.sleep(0.5)
    new = locate_new(t, target, pick)
    if new is None:
        expand_tree(t)
        time.sleep(0.7)
        parent, target, err = locate_target(pid, t, p)
        new = locate_new(t, target, pick) if target is not None else None
    if new is None:
        return False, L + ['FAIL: inserted slave row not found under target']
    L.append('  new row: no=%r %s' % (new['no'], new['label'][:100]))

    # ---- 5) 设备名（Main）
    scroll_into(new['c'])
    select_row(new)
    time.sleep(0.6)
    ok_name, info = N.set_name(pid, p['name'])
    L.append('  name ok=%s %s' % (ok_name, info))
    if not ok_name:
        return False, L + ['FAIL: 设备名称 not accepted']

    # ---- 6) 成对插入的 Sub-device
    if p.get('sub_name'):
        time.sleep(0.8)
        main_row = find_slave(t, p['name'])
        if main_row is None:
            return False, L + ['FAIL: cannot re-locate Main %r for sub' % p['name']]
        subs = main_subs(t, p['name'])
        L.append('  main_subs=%d %r' % (len(subs), [s['label'][:40] for s in subs]))
        if not subs:
            return False, L + ['FAIL: Sub-device under Internal Port not found']
        sub = subs[0]
        scroll_into(sub['c'])
        select_row(sub)
        time.sleep(0.6)
        ok_sub, info = N.set_name(pid, p['sub_name'])
        L.append('  sub name ok=%s %s' % (ok_sub, info))
        if not ok_sub:
            return False, L + ['FAIL: Sub 设备名称 not accepted']

    cnt = slave_count(pid)
    L.append('  SLAVES NOW = %r' % cnt)
    return True, L


# ------------------------------------------------------------------ 节点号

def plan_pairs(plan):
    out = []
    for p in plan:
        if p.get('name') and p.get('node'):
            out.append((p['name'], str(p['node'])))
        if p.get('sub_name') and p.get('sub_node'):
            out.append((p['sub_name'], str(p['sub_node'])))
    return out


def cmd_renumber(pid, plan, logdir, dry=False, only=None):
    """拓扑建完后统一写节点号（插入会自动重排，提前写没意义）。"""
    focus(pid)
    ensure_toolbox(pid)
    set_all_versions(pid, False)
    t = tree(pid)
    if t is None:
        print('TopologyView not found - 先打开 EtherCAT 组态页')
        return 2
    expand_tree(t)
    L = []
    pairs = plan_pairs(plan)
    if only:
        pairs = [p for p in pairs if p[0] in only]
    L.append('== renumber %d nodes' % len(pairs))
    bad = []
    for name, no in pairs:
        got = ''
        for attempt in range(2):
            r = ensure_row(pid, t, lambda: find_slave(t, name), name)
            if r is None:
                got = None
                break
            scroll_into(r['c'])
            select_row(r)
            time.sleep(0.5)
            if dry:
                L.append('  %-22s want=%-3s now=%r (dry)' % (name, no, r['no']))
                break
            got = set_node_no(r, no)
            if got == no:
                break
            time.sleep(0.8)
        L.append('  %-22s set -> %r want=%r %s' % (
            name, got, no, 'OK' if got == no else 'MISMATCH'))
        if got != no:
            bad.append(name)
        time.sleep(0.2)

    # 终检：滚动一遍把深层行实例化，再逐行读回 + 从设备数量
    t = tree(pid)
    expand_tree(t)
    sweep_expand(t)
    L.append('== verify')
    rows = [r for r in walk(t) if r['kind'] == 'slave']
    for name, no in pairs:
        hit = [r for r in rows if name in r['label']]
        got = hit[0]['no'] if hit else None
        ok = (got == no)
        L.append('  %-22s readback=%r want=%r %s' % (name, got, no, 'OK' if ok else 'MISMATCH'))
        if not ok:
            bad.append(name)
    cnt = slave_count(pid)
    L.append('  SLAVES NOW = %r (plan has %d)' % (cnt, len(pairs)))

    M.dump(os.path.join(logdir, 'renumber.log'),
           '# ss_ecat_build renumber pid=%d' % pid, L)
    dump_tree(tree(pid), os.path.join(logdir, 'tree_renumber.txt'))
    print('\n'.join(L))
    ok = not bad
    print('RENUMBER', 'OK' if ok else 'FAIL: %r' % bad)
    return 0 if ok else 1


# ------------------------------------------------------------------ 落盘

def save_now(pid):
    """走 文件(F) > 保存 落盘。返回 (ok, info)。

    为什么要每步都存：Sysmac 的组态只在进程内存里，进程一退出（崩溃、误关、
    被 taskkill）就全部丢掉，.smc2 的 mtime 一点都不动。实测 2026-11-08 整轮
    16 步建完没存，进程消失后只能重做。
    """
    try:
        import ss_save as SV
    except Exception as e:
        return False, 'import ss_save failed: %r' % (e,)
    lines = []
    ok = False
    try:
        M.force_foreground(M.main_window(pid)['hwnd'])
        time.sleep(0.4)
        ok = SV.menu_save(pid, lines)
    except Exception as e:
        lines.append('# menu_save raised %r' % (e,))
    finally:
        try:
            M.close_menu()
        except Exception:
            pass
    time.sleep(1.5)
    return ok, ' | '.join(lines[-2:])


# ------------------------------------------------------------------ main

def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    pid = M.resolve_pid(argv[0])
    mode = argv[1] if argv[1] in ('renumber', 'verify') else 'insert'
    rest = argv[2:] if mode != 'insert' else argv[1:]
    if len(rest) < 2:
        print(__doc__)
        return 1
    plan_path, logdir = rest[0], rest[1]
    frm, to, dry = 0, 9999, '--dry' in argv
    save_each = '--save-each' in argv
    if '--from' in argv:
        frm = int(argv[argv.index('--from') + 1])
    if '--to' in argv:
        to = int(argv[argv.index('--to') + 1])
    with open(plan_path, encoding='utf-8') as f:
        plan = json.load(f)
    os.makedirs(logdir, exist_ok=True)

    if mode in ('renumber', 'verify'):
        only = None
        if '--only' in argv:
            only = [x for x in argv[argv.index('--only') + 1].split('||') if x]
        return cmd_renumber(pid, plan, logdir, dry, only)

    focus(pid)
    ensure_toolbox(pid)
    set_all_versions(pid, False)      # 只列推荐版本，避免插到 Rev:1.3 之类旧版
    t = tree(pid)
    if t is None:
        print('TopologyView not found - 先打开 EtherCAT 组态页')
        return 2
    expand_tree(t)
    dump_tree(t, os.path.join(logdir, 'tree_before.txt'))
    print('slaves before =', slave_count(pid))

    summary = []
    for p in plan:
        n = int(p.get('step') or 0)
        if n < frm or n > to:
            continue
        ok, L = run_step(pid, t, p, logdir, dry)
        t = tree(pid)
        if ok and save_each and not dry:
            s_ok, s_info = save_now(pid)
            L.append('  SAVE ok=%s %s' % (s_ok, s_info))
            t = tree(pid)
        if t is not None:
            dump_tree(t, os.path.join(logdir, 'tree_step%02d.txt' % n))
        with open(os.path.join(logdir, 'step%02d.log' % n), 'w', encoding='utf-8') as f:
            f.write('\n'.join(L) + '\n')
        print('\n'.join(L))
        summary.append((n, ok))
        if not ok:
            print('STOP at step %d' % n)
            break
    with open(os.path.join(logdir, 'summary.txt'), 'w', encoding='utf-8') as f:
        for n, ok in summary:
            f.write('step %02d %s\n' % (n, 'OK' if ok else 'FAIL'))
    print('done:', ' '.join('%d:%s' % (n, 'OK' if ok else 'FAIL') for n, ok in summary))
    return 0 if all(ok for _, ok in summary) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
