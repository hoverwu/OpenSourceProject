# -*- coding: utf-8 -*-
"""ss_ecat.py - EtherCAT 拓扑：右击插入从站（**全程无拖拽**）。

作者：hoverwu ｜ 版本：0.1.0 ｜ 建立：2026-11-08 ｜ 非官方，必须**提权**运行
（Sysmac Studio 是 High IL；Medium IL 的 UIA 读不到它的树）。

为什么另写一个：早期一体化脚本在右击插入失败时会**自动退回拖拽**，
而用户明确要求验证"选中位置 → 选中硬件 → 右击插入"这条路，拖拽兜底会把失败掩盖成成功。
本脚本**没有任何 drag 代码路径**：插不进去就如实返回 False 并落盘证据。

  ss_ecat.py <pid> rows   <out> [--expand]
        拓扑行清单：主设备 / 从站 / 端口 / 耦合器 / NX 单元，含 rect、节点号、选中态。
        --expand 先对每个从站行按 → 展开（只改视图，不改组态）。
  ss_ecat.py <pid> search <out> <关键字>
        往工具箱 SearchTextBox 里**剪贴板粘贴**关键字，落盘结果行。判据是结果列表，
        不是读回框里的字（这个框读不回值，见 recipes §O）。
  ss_ecat.py <pid> insert <out> <关键字> [--pick 子串] [--at 位置] [--allrev]
        位置语法： master | last | slave:<行序号> | port:<行序号>:<端口标签>
        顺序严格按用户要求：先选中插入位置 → 再选中硬件结果行 → 右击 →「插入(I)」。
        --allrev 先勾上「显示所有版本」。
  ss_ecat.py <pid> name   <out> <设备名>
        改右侧参数表「设备名称」行（当前选中节点）。
  ss_ecat.py <pid> count  <out>
        只读「从设备数量」参数 + 拓扑行数，用于插入前后对比。

每一步都落盘；失败不重试拖拽、不猜坐标。
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
u = ctypes.windll.user32
k32 = ctypes.windll.kernel32
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = (ctypes.c_void_p,)
k32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
u.SetClipboardData.restype = ctypes.c_void_p
u.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)

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


def texts(c, maxd=4):
    """行内所有 TextControl 的 Name，按 UIA 顺序（= 视觉顺序）。"""
    out = []
    for k in M.find_by_type(c, ('TextControl',), maxd=maxd):
        nm = M.prop(k, 'Name') or ''
        if nm.strip():
            out.append(nm.strip())
    return out


def label(c):
    return ' | '.join(texts(c))


def set_clip(text):
    data = text.encode('utf-16-le') + b'\x00\x00'
    u.OpenClipboard(0)
    try:
        u.EmptyClipboard()
        h = k32.GlobalAlloc(0x0002, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u.SetClipboardData(13, h)            # CF_UNICODETEXT
    finally:
        u.CloseClipboard()


def ctrl_key(vk):
    u.keybd_event(0x11, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.15)


def tap(vk, delay=0.08):
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(delay)
    u.keybd_event(vk, 0, 2, 0)
    time.sleep(delay)


def paste(text):
    set_clip(text)
    time.sleep(0.15)
    ctrl_key(0x56)                            # Ctrl+V


def root_of(pid):
    return auto.ControlFromHandle(wt.HWND(M.main_window(pid)['hwnd']))


def find_aid(pid, aid, types, maxd=26):
    r = root_of(pid)
    if r is None:
        return None
    for c in M.find_by_type(r, types, maxd=maxd):
        if (M.prop(c, 'AutomationId') or '') == aid:
            x, y, w, h = rect(c)
            if w > 0 and h > 0:
                return c
    return None


def topo_tree(pid):
    return find_aid(pid, 'TopologyView', ('TreeControl',))


def focus(pid):
    M.force_foreground(M.main_window(pid)['hwnd'])
    time.sleep(0.35)


# ------------------------------------------------------------------ 拓扑行

def kind_of(c):
    nm = M.prop(c, 'Name') or ''
    lb = label(c)
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


def all_rows(pid, expand=False):
    t = topo_tree(pid)
    if t is None:
        return []
    if expand:
        focus(pid)
        for _ in range(2):
            rows = [c for c in M.find_by_type(t, ('TreeItemControl',), maxd=12)]
            slaves = [c for c in rows if kind_of(c) == 'slave']
            if not slaves:
                break
            for c in slaves:
                x, y = center(c)
                # 点行内文字，避开行尾节点号输入框（点进去就成编辑态）
                tx = texts(c)
                pt = None
                for k in M.find_by_type(c, ('TextControl',), maxd=3):
                    if (M.prop(k, 'Name') or '').strip():
                        pt = center(k)
                        break
                M.left_click(*(pt or (x, y)))
                time.sleep(0.25)
                tap(0x27)                     # VK_RIGHT
                time.sleep(0.5)
    out = []
    for i, c in enumerate(M.find_by_type(t, ('TreeItemControl',), maxd=14)):
        out.append(dict(i=i, c=c, kind=kind_of(c), vm=M.prop(c, 'Name') or '',
                        label=label(c), rect=rect(c), no=node_no(c),
                        sel='SELECTED' in M.line_of(c)))
    return out


def slave_count_param(pid):
    """右侧参数表里「从设备数量」的值（只读 LabelParameterItem）。"""
    r = root_of(pid)
    if r is None:
        return None
    for c in M.find_by_type(r, ('ListItemControl',), maxd=26):
        ts = texts(c, 3)
        if ts and ts[0] == '从设备数量':
            return ts[-1]
    return None


def cmd_rows(pid, out, expand):
    rows = all_rows(pid, expand)
    lines = ['# topology rows=%d  从设备数量=%r' % (len(rows), slave_count_param(pid))]
    for r in rows:
        lines.append('%3d %-8s no=%-4s sel=%-5s rect=%-22s %s' %
                     (r['i'], r['kind'], r['no'], r['sel'], str(r['rect']), r['label'][:110]))
        lines.append('      vm=%s' % r['vm'][:120])
    n = M.dump(out, '# ss_ecat rows pid=%d expand=%s' % (pid, expand), lines)
    print('rows=%d 从设备数量=%r -> %s (%d lines)' %
          (len(rows), slave_count_param(pid), out, n))
    return 0


# ------------------------------------------------------------------ 工具箱

def search_box(pid):
    return find_aid(pid, 'SearchTextBox', ('EditControl',))


def result_list(pid):
    return find_aid(pid, 'ItemListBox', ('ListControl',))


def results(pid):
    lst = result_list(pid)
    if lst is None:
        return []
    out = []
    for c in M.find_by_type(lst, ('ListItemControl',), maxd=4):
        out.append(dict(c=c, label=label(c), rect=rect(c),
                        sel='SELECTED' in M.line_of(c)))
    out.sort(key=lambda d: d['rect'][1])
    return out


def type_query(pid, kw):
    box = search_box(pid)
    if box is None:
        return False
    focus(pid)
    x, y = center(box)
    M.left_click(x, y)
    time.sleep(0.3)
    ctrl_key(0x41)                            # Ctrl+A
    paste(kw)
    time.sleep(1.2)
    return True


def cmd_search(pid, out, kw, allrev=False):
    if allrev:
        r = root_of(pid)
        for c in M.find_by_type(r, ('CheckBoxControl',), maxd=26):
            if (M.prop(c, 'Name') or '') == '显示所有版本':
                try:
                    if c.GetTogglePattern().ToggleState == 0:
                        c.GetTogglePattern().Toggle()
                        time.sleep(0.8)
                except Exception:
                    x, y = center(c)
                    M.left_click(x, y)
                    time.sleep(0.8)
                break
    if not type_query(pid, kw):
        print('SearchTextBox not found')
        return 1
    rs = results(pid)
    lines = ['# keyword=%r results=%d' % (kw, len(rs))]
    for i, d in enumerate(rs):
        lines.append('%3d sel=%-5s rect=%-22s %s' % (i, d['sel'], str(d['rect']), d['label']))
    n = M.dump(out, '# ss_ecat search pid=%d' % pid, lines)
    print('results=%d -> %s' % (len(rs), out))
    for i, d in enumerate(rs):
        print('  %2d %s' % (i, d['label']))
    return 0 if rs else 1


def pick_result(pid, kw, pick=''):
    rs = results(pid)
    cand = [d for d in rs if kw.lower() in d['label'].lower()]
    if pick:
        narrowed = [d for d in cand if pick.lower() in d['label'].lower()]
        if narrowed:
            cand = narrowed
    if not cand:
        return None, rs
    return cand[0], rs


# ------------------------------------------------------------------ 插入位置

def select_position(pid, spec, rows):
    """spec: master | last | slave:<i> | port:<i>:<label>  → (row dict, how)"""
    slaves = [r for r in rows if r['kind'] == 'slave']
    if spec == 'master':
        hit = [r for r in rows if r['kind'] == 'master']
        return (hit[0], 'master') if hit else (None, 'no master row')
    if spec == 'last':
        if not slaves:
            hit = [r for r in rows if r['kind'] == 'master']
            return (hit[0], 'master(empty chain)') if hit else (None, 'empty, no master')
        return slaves[-1], 'last slave #%d' % slaves[-1]['i']
    m = re.match(r'^slave:(\d+)$', spec)
    if m:
        i = int(m.group(1))
        hit = [r for r in rows if r['i'] == i]
        return (hit[0], 'row %d' % i) if hit else (None, 'no row %d' % i)
    m = re.match(r'^port:(\d+):(.+)$', spec)
    if m:
        i, want = int(m.group(1)), m.group(2)
        parent = [r for r in rows if r['i'] == i]
        if not parent:
            return None, 'no row %d' % i
        # 端口行是父行的后代：展开后按标签找
        focus(pid)
        pc = parent[0]['c']
        x, y = center(pc)
        M.left_click(x, y)
        time.sleep(0.3)
        tap(0x27)
        time.sleep(0.8)
        for k in M.find_by_type(pc, ('TreeItemControl',), maxd=6):
            lb = label(k)
            if want.lower() in lb.lower() and kind_of(k) == 'port':
                return dict(i=-1, c=k, kind='port', vm=M.prop(k, 'Name') or '',
                            label=lb, rect=rect(k), no='', sel=False), 'port %r of row %d' % (lb, i)
        return None, 'port %r not exposed under row %d (labels=%r)' % (
            want, i, [label(k) for k in M.find_by_type(pc, ('TreeItemControl',), maxd=6)])
    return None, 'bad --at spec: %r' % spec


def menu_insert(pid, pick_ctl):
    """右键工具箱结果行 →「插入(I)」。没有拖拽兜底。"""
    x, y = center(pick_ctl)
    M.right_click(x, y)
    time.sleep(0.9)
    items = []
    for w, ctl, cnt in M.menu_popups(pid):
        for k in M.find_by_type(ctl, ('MenuItemControl',), maxd=8):
            items.append(k)
    names = [M.prop(k, 'Name') or '' for k in items]
    hit = [k for k in items if '插入' in (M.prop(k, 'Name') or '')]
    if not hit:
        M.esc(2)
        return False, 'no 插入 in popup: %r' % names
    k = hit[0]
    en = M.prop(k, 'IsEnabled')
    try:
        k.GetInvokePattern().Invoke()
        how = 'invoke'
    except Exception:
        cx, cy = center(k)
        M.left_click(cx, cy)
        how = 'click'
    time.sleep(1.8)
    return True, '%s enabled=%s popup=%r' % (how, en, names)


def cmd_insert(pid, out, kw, pick='', at='master', allrev=False):
    focus(pid)
    before = all_rows(pid)
    n0 = len([r for r in before if r['kind'] == 'slave'])
    cnt0 = slave_count_param(pid)
    lines = ['# before: rows=%d slaves=%d 从设备数量=%r' % (len(before), n0, cnt0)]
    for r in before:
        lines.append('  %3d %-8s %s' % (r['i'], r['kind'], r['label'][:100]))

    if not type_query(pid, kw):
        lines.append('FAIL: SearchTextBox not found')
        M.dump(out, '# ss_ecat insert pid=%d kw=%r' % (pid, kw), lines)
        print('SearchTextBox not found')
        return 1
    if allrev:
        r = root_of(pid)
        for c in M.find_by_type(r, ('CheckBoxControl',), maxd=26):
            if (M.prop(c, 'Name') or '') == '显示所有版本':
                try:
                    if c.GetTogglePattern().ToggleState == 0:
                        c.GetTogglePattern().Toggle()
                        time.sleep(0.8)
                        type_query(pid, kw)
                except Exception:
                    pass
                break
    d, rs = pick_result(pid, kw, pick)
    lines.append('# toolbox results=%d' % len(rs))
    for i, x in enumerate(rs):
        lines.append('  %2d %s' % (i, x['label']))
    if d is None:
        lines.append('FAIL: no result matching %r / %r' % (kw, pick))
        M.dump(out, '# ss_ecat insert pid=%d kw=%r' % (pid, kw), lines)
        print('no matching result for %r pick=%r' % (kw, pick))
        return 1
    lines.append('# picked: %s' % d['label'])

    # 1) 先选中插入位置（用户要求的顺序）
    row, how = select_position(pid, at, before)
    lines.append('# position spec=%r -> %s' % (at, how))
    if row is None:
        M.dump(out, '# ss_ecat insert pid=%d kw=%r' % (pid, kw), lines)
        print('position failed:', how)
        return 1
    x, y = center(row['c'])
    M.left_click(x, y)
    time.sleep(0.6)
    lines.append('# clicked position rect=%s label=%s' % (str(row['rect']), row['label'][:80]))

    # 2) 再选中硬件结果行（左击选中，不双击）
    d, _ = pick_result(pid, kw, pick)              # 重新取，位置点击可能刷新工具箱
    if d is None:
        lines.append('FAIL: result row went stale')
        M.dump(out, '# ss_ecat insert pid=%d kw=%r' % (pid, kw), lines)
        print('result row stale')
        return 1
    hx, hy = center(d['c'])
    M.left_click(hx, hy)
    time.sleep(0.5)
    lines.append('# selected hardware rect=%s' % str(d['rect']))

    # 3) 右击 → 插入(I)
    ok, info = menu_insert(pid, d['c'])
    lines.append('# menu_insert ok=%s %s' % (ok, info))

    # 4) 校验：展开一轮再数（新从站常挂在未展开的端口下）
    after = all_rows(pid, expand=True)
    n1 = len([r for r in after if r['kind'] == 'slave'])
    cnt1 = slave_count_param(pid)
    lines.append('# after: rows=%d slaves=%d 从设备数量=%r' % (len(after), n1, cnt1))
    for r in after:
        lines.append('  %3d %-8s no=%-4s %s' % (r['i'], r['kind'], r['no'], r['label'][:100]))
    grew = n1 > n0
    lines.append('# VERDICT grew=%s (slaves %d -> %d, 从设备数量 %r -> %r)' % (grew, n0, n1, cnt0, cnt1))
    M.dump(out, '# ss_ecat insert pid=%d kw=%r at=%r' % (pid, kw, at), lines)
    print('grew=%s slaves %d->%d 从设备数量 %r->%r  menu=%s' % (grew, n0, n1, cnt0, cnt1, info))
    print('-> %s' % out)
    return 0 if grew else 1


# ------------------------------------------------------------------ 设备名

def cmd_name(pid, out, name):
    r = root_of(pid)
    focus(pid)
    hit = None
    for c in M.find_by_type(r, ('ListItemControl',), maxd=28):
        ts = texts(c, 3)
        if ts and ts[0] == '设备名称':
            hit = c
            break
    lines = ['# 设备名称 row found=%s' % (hit is not None)]
    if hit is None:
        M.dump(out, '# ss_ecat name pid=%d' % pid, lines)
        print('设备名称 row not found')
        return 1
    lines.append('# before: %s' % label(hit))
    ed = None
    for k in M.find_by_type(hit, ('EditControl',), maxd=3):
        ed = k
        break
    if ed is None:
        # 参数表是"点一下才出编辑框"的惰性控件：双击值那一格
        ts = [k for k in M.find_by_type(hit, ('TextControl',), maxd=3) if M.prop(k, 'Name')]
        tgt = ts[-1] if ts else hit
        x, y = center(tgt)
        M.double_click(x, y)
        time.sleep(0.8)
        for k in M.find_by_type(hit, ('EditControl',), maxd=3):
            ed = k
            break
    if ed is None:
        lines.append('FAIL: no EditControl in 设备名称 row')
        M.dump(out, '# ss_ecat name pid=%d' % pid, lines)
        print('no edit control')
        return 1
    x, y = center(ed)
    M.left_click(x, y)
    time.sleep(0.3)
    ctrl_key(0x41)
    paste(name)
    time.sleep(0.4)
    tap(0x0D)                                  # Enter 提交
    time.sleep(1.0)
    lines.append('# after: %s' % label(hit))
    ok = name in label(hit)
    lines.append('# VERDICT ok=%s' % ok)
    M.dump(out, '# ss_ecat name pid=%d name=%r' % (pid, name), lines)
    print('设备名称 -> %r ok=%s' % (name, ok))
    return 0 if ok else 1


def cmd_count(pid, out):
    rows = all_rows(pid)
    lines = ['rows=%d slaves=%d 从设备数量=%r' %
             (len(rows), len([r for r in rows if r['kind'] == 'slave']), slave_count_param(pid))]
    for r in rows:
        lines.append('  %3d %-8s no=%-4s %s' % (r['i'], r['kind'], r['no'], r['label'][:100]))
    M.dump(out, '# ss_ecat count pid=%d' % pid, lines)
    print(lines[0])
    return 0


def cmd_delete(pid, out, name):
    """右键从站行 →「删除(D)」。实测：删除 Main 会连带删掉它的 Sub 配对与整条下游链。"""
    rows = all_rows(pid, expand=True)
    hit = [r for r in rows if r['kind'] == 'slave' and name in r['label']]
    lines = ['# target=%r candidates=%d' % (name, len(hit))]
    if not hit:
        for r in rows:
            lines.append('  %3d %-8s %s' % (r['i'], r['kind'], r['label'][:100]))
        M.dump(out, '# ss_ecat delete pid=%d' % pid, lines)
        print('no slave row contains %r' % name)
        return 1
    r = hit[0]
    # 行 rect 会把整个子树都罩进去（父行高度=子行总和），右击必须落在**行标题那一行**：
    #   x 往右避开行首的节点号 editBox，y 用行顶 +18（子行都在更下面）。
    # 选中用 UIA SelectionItem，不用鼠标点文字（点文字会进行内编辑态，右击变成剪切/复制菜单）。
    try:
        r['c'].GetSelectionItemPattern().Select()
        time.sleep(0.3)
    except Exception:
        pass
    rx, ry, rw, rh = r['rect']
    pt = (rx + min(300, max(60, rw // 3)), ry + 18)
    lines.append('# right-click row header at %s sel=%s' % (str(pt), 'SELECTED' in M.line_of(r['c'])))
    M.right_click(*pt)
    time.sleep(0.9)
    items = []
    for w, ctl, cnt in M.menu_popups(pid):
        for k in M.find_by_type(ctl, ('MenuItemControl',), maxd=8):
            items.append(k)
    names = [(M.prop(k, 'Name') or '') for k in items]
    lines.append('# popup=%r' % names)
    d = [k for k in items if (M.prop(k, 'Name') or '').startswith('删除')]
    if not d:
        M.esc(2)
        M.dump(out, '# ss_ecat delete pid=%d' % pid, lines)
        print('no 删除 in popup: %r' % names)
        return 1
    try:
        d[0].GetInvokePattern().Invoke()
    except Exception:
        cx, cy = center(d[0])
        M.left_click(cx, cy)
    time.sleep(1.6)
    after = all_rows(pid, expand=True)
    n1 = len([x for x in after if x['kind'] == 'slave'])
    lines.append('# slaves after delete=%d 从设备数量=%r' % (n1, slave_count_param(pid)))
    for x in after:
        lines.append('  %3d %-8s no=%-4s %s' % (x['i'], x['kind'], x['no'], x['label'][:100]))
    M.dump(out, '# ss_ecat delete pid=%d' % pid, lines)
    print('deleted via %r; slaves now=%d' % (names, n1))
    return 0


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    if not M.is_admin():
        print('WARN: not admin - UIA empty (UIPI). Run elevated (as administrator).')
    pid = M.resolve_pid(sys.argv[1])
    a = sys.argv[2].lower()
    out = sys.argv[3]
    rest = sys.argv[4:]
    if a == 'rows':
        return cmd_rows(pid, out, '--expand' in rest)
    if a == 'search':
        return cmd_search(pid, out, rest[0] if rest else '', '--allrev' in rest)
    if a == 'insert':
        kw = rest[0] if rest else ''
        pick = at = ''
        allrev = '--allrev' in rest
        if '--pick' in rest:
            pick = rest[rest.index('--pick') + 1]
        if '--at' in rest:
            at = rest[rest.index('--at') + 1] or 'master'
        return cmd_insert(pid, out, kw, pick, at or 'master', allrev)
    if a == 'name':
        return cmd_name(pid, out, rest[0] if rest else '')
    if a == 'count':
        return cmd_count(pid, out)
    if a in ('delete', 'del'):
        return cmd_delete(pid, out, rest[0] if rest else '')
    print('unknown action', a)
    return 2


if __name__ == '__main__':
    sys.exit(main())