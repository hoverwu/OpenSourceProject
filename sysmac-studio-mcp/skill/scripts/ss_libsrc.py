# -*- coding: utf-8 -*-
"""ss_libsrc.py - 读"被引用库里的 POU 源码"的唯一稳定通道（工具箱枚举 / 转到下层 / SyntaxEditor 全文导出）

作者：hoverwu ｜ 版本：0.1.0 ｜ 实测：Sysmac Studio V1.68 64bit / Win11 / 125% DPI（2026-11-21）
必须提权运行（Sysmac 是 High 完整性，UIPI 会挡住 UIA）。

为什么需要这个脚本
------------------
引用库（.slr）里的 POU **不在工程树里**，所以 `ss_uimap.py open <树路径>` 根本够不着。
库索引那个 `LibraryDataGrid` 是 WPF 自绘表格，**不向 UIA 暴露任何行/子节点**（点展开箭头、
双击行、SetFocus+方向键全部无效，2026-11-21 实测）。唯一稳定通道是：

    程序编辑器（梯形图）→ 工具箱库分组 ` <库名> ( <版本> )`(groupToggle) 展开
    → 右键该库 FB 的实例 → 菜单「转到下层」→ 打开 `<FB名> - <实例名>` 文档
    → 里面的 `Text|textEditor|SyntaxEditor` 用 TextPattern 取全文

三个模式
--------
  ss_libsrc.py <pid|auto> <out> toolbox [--no-expand]
        列出工具箱里所有库分组与其 POU（纯 UIA，不动鼠标）。判据：能看到 `group` 行与
        其下 `POU` 行。**默认先 Toggle 所有折叠态分组**——折叠分组不向 UIA 暴露子项，
        不加这一步只会拿到分组名（2026-11-21 实测）；`--no-expand` 关闭该行为。

  ss_libsrc.py <pid|auto> <out> goto <x> <y> [--item 转到下层] [--no-text] [--title P]
        在物理坐标 (x,y) 右键（库 FB 实例在梯形图上的位置），再按 **菜单项 Name** Invoke
        `转到下层`（不是坐标点，菜单位置随 DPI/布局变）。点完默认立刻导出全文。
        坐标怎么来：先 `ss_uimap.py scan` 看梯形图区域，或肉眼取一次后写进调用脚本。
        右键后会把鼠标位置还原（不把光标留在原地）。

  ss_libsrc.py <pid|auto> <out> text [--title P] [--st FILE]
        把当前打开的 ST 编辑器全文导出（`--title` 按文档名前缀过滤），
        落盘 `<out>.st`（或 `--st` 指定），并在 out 里记 chars/lines/sha256/首末行。
        比对离线明文时只做 CRLF→LF + 去首尾空行，**不要做内容级清洗**。

判据与坑
--------
- `goto` 之后没有新文档窗口 = 右键没落在实例上（坐标偏了）或菜单项名变了；脚本会列出
  实际抓到的菜单项，照着改 `--item`。
- `text` 取不到 = 该页不是 ST（LD/变量表没有 textEditor），或编辑器没获得焦点（先 goto）。
- 取到的文本含 CRLF；与磁盘明文比对前必须归一化，否则会假报"不一致"。
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import os
import sys
import time

# 控制台/管道输出统一 UTF-8：否则中文库名在 cp936 控制台或被 UTF-8 捕获时变乱码
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import uiautomation as auto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss  # noqa: E402

auto.SetGlobalSearchTimeout(4)
u = ctypes.windll.user32

TOOLBOX_AID = 'toolboxItems'
GROUP_AID = 'groupToggle'
EDITOR_AID = 'textEditor'


def norm(s):
    return s.replace('\r\n', '\n').replace('\r', '\n').strip('\n')


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def walk(root, max_depth=18, limit=20000):
    """Depth-first walk that survives dead nodes. Yields (control, depth)."""
    stack = [(root, 0)]
    n = 0
    while stack and n < limit:
        c, d = stack.pop()
        n += 1
        yield c, d
        if d >= max_depth:
            continue
        try:
            kids = c.GetChildren()
        except Exception:
            kids = []
        for k in reversed(kids):
            stack.append((k, d + 1))


def aid_of(c):
    try:
        return c.AutomationId or ''
    except Exception:
        return ''


def name_of(c):
    try:
        return (c.Name or '').strip()
    except Exception:
        return ''


def find_aid(root, aid):
    for c, _ in walk(root):
        if aid_of(c) == aid:
            return c
    return None


def popup_items(pid):
    """Every MenuItemControl of this process, across all top-level windows."""
    out = []
    for w in auto.GetRootControl().GetChildren():
        try:
            if w.ProcessId != pid:
                continue
        except Exception:
            continue
        for c, _ in walk(w, max_depth=12):
            try:
                if c.ControlTypeName == 'MenuItemControl':
                    nm = name_of(c)
                    if nm:
                        out.append((nm, c))
            except Exception:
                pass
    return out


def invoke_menu_item(pid, wanted, log):
    """Invoke a context-menu item by NAME. Returns the name actually invoked or ''."""
    cands = popup_items(pid)
    log.append('menu items: %r' % ([n for n, _ in cands][:40],))
    exact = [c for n, c in cands if n == wanted]
    loose = [c for n, c in cands if n.startswith(wanted)]
    for c in (exact or loose):
        try:
            c.GetInvokePattern().Invoke()
            return wanted
        except Exception as e:
            log.append('invoke %r failed: %r' % (wanted, e))
    return ''


def doc_windows(pid):
    """Open document panes: [(title, control)]."""
    res = []
    for w in auto.GetRootControl().GetChildren():
        try:
            if w.ProcessId != pid:
                continue
        except Exception:
            continue
        for c, _ in walk(w, max_depth=12):
            try:
                if c.ControlTypeName == 'PaneControl' and c.ClassName == 'DocumentWindow':
                    res.append((name_of(c), c))
            except Exception:
                pass
    return res


def editors(pid, title_prefix=''):
    """All SyntaxEditor controls, optionally filtered by owning document title."""
    res = []
    for title, doc in doc_windows(pid):
        if title_prefix and not title.startswith(title_prefix):
            continue
        for c, _ in walk(doc, max_depth=16):
            if aid_of(c) == EDITOR_AID:
                res.append((title, c))
                break
    return res


def dump_text(pid, out, log, title_prefix='', st_path=''):
    eds = editors(pid, title_prefix)
    log.append('editors found: %d (filter=%r)' % (len(eds), title_prefix))
    if not eds:
        log.append('NO SyntaxEditor (textEditor) — 该页可能不是 ST，或编辑器未打开')
        return 1
    rc = 0
    for i, (title, ed) in enumerate(eds):
        try:
            raw = ed.GetTextPattern().DocumentRange.GetText(-1)
        except Exception as e:
            log.append('[%d] %s GetText failed: %r' % (i, title, e))
            rc = 1
            continue
        t = norm(raw)
        path = st_path or (out + ('.st' if len(eds) == 1 else '.%d.st' % i))
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(t)
        lines = t.split('\n')
        log.append('[%d] doc=%r chars=%d lines=%d sha256=%s st=%s'
                   % (i, title, len(t), len(lines), sha(t), path))
        log.append('[%d] first=%r' % (i, lines[0][:120]))
        log.append('[%d] last=%r' % (i, lines[-1][:120]))
    return rc


def mode_toolbox(pid, out, log, expand=False):
    mw = ss.main_hwnd(pid)
    root = auto.ControlFromHandle(wt.HWND(mw))
    box = find_aid(root, TOOLBOX_AID)
    if box is None:
        log.append('NO toolbox (aid=%s) — 先打开一个程序编辑器，工具箱才会出现' % TOOLBOX_AID)
        return 1
    if expand:
        groups = [c for c, _ in walk(box) if aid_of(c) == GROUP_AID]
        for g in groups:
            try:
                if g.GetTogglePattern().ToggleState == 0:      # Off -> expand
                    g.GetTogglePattern().Toggle()
                    time.sleep(0.3)
            except Exception:
                pass
        box = find_aid(auto.ControlFromHandle(wt.HWND(mw)), TOOLBOX_AID) or box

    group = '(no group)'
    n_group = n_pou = 0
    for c, _ in walk(box):
        a = aid_of(c)
        nm = name_of(c)
        if a == GROUP_AID:
            group = nm
            n_group += 1
            log.append('group %r' % nm)
            continue
        if c.ControlTypeName != 'ButtonControl':
            continue
        # a POU entry: Button > Edit|textBox > Text  (LD function / FB toolbox control)
        label = ''
        for d, _dd in walk(c, max_depth=4):
            if d is c:
                continue
            if aid_of(d) == 'textBox':
                label = name_of(d) or label
                for t, _t2 in walk(d, max_depth=3):
                    if t.ControlTypeName == 'TextControl' and name_of(t):
                        label = name_of(t)
                        break
                break
        if label:
            n_pou += 1
            log.append('  POU %r  (group=%r)' % (label.strip(), group))
    log.append('# groups=%d pous=%d' % (n_group, n_pou))
    return 0 if n_group else 1


def mode_goto(pid, out, log, x, y, item='转到下层', do_text=True, title_prefix=''):
    mw = ss.main_hwnd(pid)
    ss.force_foreground(mw)
    time.sleep(0.4)
    p = wt.POINT()
    u.GetCursorPos(ctypes.byref(p))
    old = (p.x, p.y)
    before = {t for t, _ in doc_windows(pid)}
    log.append('before docs: %r' % (sorted(before),))
    try:
        ss.click_at(x, y, kind='rclick')
        time.sleep(0.9)
        got = invoke_menu_item(pid, item, log)
        time.sleep(1.6)
        after = {t for t, _ in doc_windows(pid)}
        log.append('after docs: %r' % (sorted(after),))
        log.append('invoked=%r new_docs=%r' % (got, sorted(after - before)))
        if not got:
            return 1
        if not (after - before):
            log.append('WARN: 菜单点了但没开新文档（坐标可能没落在 FB 实例上）')
            return 1
        if do_text:
            return dump_text(pid, out, log, title_prefix=title_prefix)
        return 0
    finally:
        try:
            u.SetCursorPos(old[0], old[1])
        except Exception:
            pass


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    pid = ss.resolve_pid(argv[0])
    out = argv[1]
    mode = argv[2]
    rest = argv[3:]
    opts = {'expand': '--no-expand' not in rest, 'no-text': '--no-text' in rest}
    title = ''
    item = '转到下层'
    st_path = ''
    pos = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == '--title' and i + 1 < len(rest):
            title = rest[i + 1]; i += 2; continue
        if a.startswith('--title='):
            title = a.split('=', 1)[1]; i += 1; continue
        if a == '--item' and i + 1 < len(rest):
            item = rest[i + 1]; i += 2; continue
        if a.startswith('--item='):
            item = a.split('=', 1)[1]; i += 1; continue
        if a == '--st' and i + 1 < len(rest):
            st_path = rest[i + 1]; i += 2; continue
        if a.startswith('--st='):
            st_path = a.split('=', 1)[1]; i += 1; continue
        if not a.startswith('--'):
            pos.append(a)
        i += 1

    log = []
    rc = 2
    if mode == 'toolbox':
        rc = mode_toolbox(pid, out, log, expand=opts['expand'])
    elif mode == 'text':
        rc = dump_text(pid, out, log, title_prefix=title, st_path=st_path)
    elif mode == 'goto':
        if len(pos) < 2:
            log.append('goto needs <x> <y>')
        else:
            rc = mode_goto(pid, out, log, int(float(pos[0])), int(float(pos[1])),
                           item=item, do_text=not opts['no-text'], title_prefix=title)
    else:
        log.append('unknown mode %r (toolbox|goto|text)' % mode)

    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(log))
    print('\n'.join(log))
    return rc


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
