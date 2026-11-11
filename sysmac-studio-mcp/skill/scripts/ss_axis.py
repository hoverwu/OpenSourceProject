# -*- coding: utf-8 -*-
"""ss_axis.py - read and write ONE axis-settings page (轴设置) of Sysmac Studio.

Author: hoverwu | version: 0.3.0 | unofficial. Must run ELEVATED (Sysmac runs High) + DPI aware.

v0.3.0 (2026-11-07): every command now roots the page with `page_root()`.  With the axis
documents open as TABS, `find_doc()` returns the DocumentWindow pane that is the TAB and a
walk down from it yields 2 nodes, so v0.2.0 answered 'NO SUCH SECTION (have )' for all 8
sections.  `read`/`set`/`apply` additionally check the page's 轴号
against the tree path before writing, and `apply` raises the tab first when it mismatches.

The axis page is one member of the ConfigurationView family (control-tree.md §16.4):
a left rail of 8 section icons plus a `HelpWithinSectionDetailsView` body made of
`ComponentsFieldView` rows (label Text + one control).  This script drives that page
directly instead of scraping it out of a full dump.

  ss_axis.py nav    <pid> <out> <tree.path>              open the axis page, list the 8 sections
  ss_axis.py read   <pid> <out> <tree.path> [aid,..]      every row of every section, one
        TAB-separated record per field:
        label \t kind \t VALUE \t how \t group \t enabled \t left \t top \t w \t h \t aid
        (columns are tab-separated on purpose - labels and values are Chinese and
        variable width, so fixed-width padding cannot be parsed back reliably.)
  ss_axis.py set    <pid> <out> <tree.path> <aid> <label> <value>
        write one field by its visible label.  Edits are committed with Tab and
        ALWAYS read back; the log line says read=... so a value that did not stick
        is visible instead of silent.
  ss_axis.py dump    <pid> <out>            raw UIA of the currently open axis page
  ss_axis.py close   <pid> <out> <doc-name>
  ss_axis.py add     <pid> <out> <tree.path> [--name NAME] [--item TEXT] [--list]
        insert ONE axis under 轴设置 with the recorded entry (pitfalls §42:
        right-click -> 添加 -> submenu), report the new tree row, optionally
        rename it.  --list records both menus and presses Esc, changing nothing.
        Measured 2026-11-06: the submenu only appears once the real cursor is
        nudged over 添加 (SetCursorPos alone does nothing), and its row is
        enumerated inside the PARENT menu's UIA subtree, so it is recognised by
        "UIA named it while undrawn, now it has a rectangle" - not by window or
        by name.  New row comes back as 'MC_AxisNNN (<轴号>,MC1)'.
  ss_axis.py rename  <pid> <out> <tree.path> <NAME>
        F2 a tree row and read the caption back; retries until the freshly
        inserted row is realised (a brand new row is absent from the tree's
        order map for a second or two).

`tree.path` is the project-tree index of the axis row, e.g. 0.4.0.4 (轴名示例).
Opening/closing reuses ss_uimap.cmd_open / close_document, so the same
click + real VK_RETURN rule applies (a message-only Enter does not open a page).
"""
import sys, time, json, os, re
import ctypes
import tempfile

try:
    import ctypes
    import ctypes.wintypes as wt
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import uiautomation as auto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss_uimap as U                                                    # noqa: E402

SEC_ORDER = ['basic_setting', 'axes_scale', 'axes_dynamics', 'axes_io', 'axes_limit',
             'back_original_point', 'count_mode_set', 'servo']
INTERACTIVE = ('EditControl', 'ComboBoxControl', 'CheckBoxControl', 'RadioButtonControl',
               'ButtonControl', 'TextControl', 'ListControl')
SETTLE = 4.0            # seconds a freshly opened page needs before UIA answers fully


def ustr(v):
    return ('' if v is None else str(v)).strip()


def log(*a):
    print(*a)
    sys.stdout.flush()


# ---------------------------------------------------------------- locating the page
def open_axis(pid, path_str, tmp=None):
    """Make sure the axis row opens, then return (mw, pane, doc_name).

    tmp 是 cmd_open 的运行时落盘文件（读完即弃）；默认放在系统临时目录，
    不往脚本目录写，调用方也可显式传入自己的路径。"""
    if tmp is None:
        tmp = os.path.join(tempfile.gettempdir(), 'ss_axis_open.txt')
    pid = U.resolve_pid(str(pid))
    _PID[0] = pid
    mw = U.main_window(pid)
    U.cmd_open([str(pid), tmp, path_str])
    name = None
    with open(tmp, encoding='utf-8') as fh:
        txt = fh.read()
    m = re.search(r'^\s+@@ (.+?)\|', txt, re.M)
    if not m:
        # the page was ALREADY open, so cmd_open reports the node label instead of a
        # new document: '## 0.4.0.4  轴名示例 (4,MC1)  enter then dblclick did not open'
        m = re.search(r'^##\s+\S+\s+(.+?)\s\s', txt, re.M)
    if m:
        name = m.group(1)
    # A page that has just been opened is not laid out yet: on 2026-11-06 every
    # ComboBox of a freshly opened axis page read back empty, while the same
    # fields on a page that had already been open answered fine.
    time.sleep(SETTLE)
    pane = U.find_doc(mw['hwnd'], name) if name else None
    return pid, mw, pane, name


def root_custom(pane):
    """The Custom page root inside a DocumentWindow pane."""
    for c in pane.GetChildren():
        if c.ControlTypeName == 'CustomControl' and (U.prop(c, 'ClassName') or ''):
            return c
    return pane


BODY_PTS = ((0.5, 0.45), (0.35, 0.30), (0.65, 0.60), (0.50, 0.25), (0.80, 0.45))


def page_root(mw, pane, logf=None):
    """A root whose subtree really contains the 8 section rail buttons.

    Measured 2026-11-07.  With the axis
    documents open as TABS, `find_doc()` returns the DocumentWindow pane that IS the tab:
    rect (541,119,714,151) - 173x32 px, one child, and a walk DOWN from it yields 2 nodes
    and no IconView, which is why `ss_axis.py read` answered
    'NO SUCH SECTION basic_setting (have )' for all 8 sections.
    The same pane nevertheless shows up as an ANCESTOR of the body when walking UP from
    `auto.ControlFromPoint(700,400)`, so parent->child navigation is broken for this
    document while child->parent is fine.  Hit-testing the body and walking up to
    Custom|ConfigurationView (rect 266,151,1654,783) gives a root with all 8 rails and
    86 nodes - that is what every read/set/apply has to use.

    The normal route is tried first and kept when it answers, so pages that do navigate
    down (the source instance, single-document layouts) are untouched.
    """
    r = root_custom(pane)
    if section_buttons(r):
        return r
    box = None
    p = pane
    for _ in range(8):
        if p is None:
            break
        if (U.prop(p, 'ClassName') or '') == 'TabbedMdiContainer':
            box = U.prop(p, 'BoundingRectangle')
            break
        p = p.GetParentControl()
    if box is None:
        box = U.prop(pane, 'BoundingRectangle')
    if box is None:
        return r
    w, h = box.right - box.left, box.bottom - box.top
    for fx, fy in BODY_PTS:
        x, y = int(box.left + w * fx), int(box.top + h * fy)
        try:
            node = auto.ControlFromPoint(x, y)
        except Exception:
            continue
        q = node
        for _ in range(10):
            if q is None:
                break
            if (U.prop(q, 'ClassName') or '') in ('ConfigurationView',
                                                  'HelpWithinSectionDetailsView'):
                if section_buttons(q):
                    if logf:
                        logf('root: hit-test (%d,%d) -> %s' % (x, y,
                                                               U.prop(q, 'ClassName')))
                    return q
            q = q.GetParentControl()
    if logf:
        logf('root: hit-test found no rail, using the pane subtree')
    return r


def section_buttons(root):
    """[(aid, ButtonControl)] for the left rail, in tree order."""
    out = []

    def rec(c, d):
        if d > 12:
            return
        if c.ControlTypeName == 'CustomControl' and U.prop(c, 'ClassName') == 'IconView':
            aid = U.prop(c, 'AutomationId') or ''
            btn = c.GetAncestorControl(lambda x, d: x.ControlTypeName == 'ButtonControl')
            if btn is not None and aid:
                out.append((aid, btn))
        for k in c.GetChildren():
            rec(k, d + 1)
    rail = None
    for c in U.find_by_type(root, ('PaneControl',), maxd=8):
        if U.prop(c, 'ClassName') == 'ScrollViewer':
            r = U.prop(c, 'BoundingRectangle')
            if r.right - r.left <= 120:
                rail = c
                break
    if rail is None:
        rail = root
    rec(rail, 0)
    return out


def goto_section(root, aid, wait=1.0):
    """Invoke the rail button of one section, unfold it; return the page title."""
    for a, btn in section_buttons(root):
        if a == aid:
            try:
                btn.GetInvokePattern().Invoke()
            except Exception as e:
                return 'INVOKE FAILED %s' % e.__class__.__name__
            time.sleep(wait)
            expand_groups(root)
            return page_title(root)
    return 'NO SUCH SECTION %s (have %s)' % (aid, ','.join(a for a, _ in section_buttons(root)))


def page_title(root):
    for c in U.find_by_type(root, ('TextControl',), maxd=14):
        if U.prop(c, 'AutomationId') == 'TitleTextBlock':
            return U.prop(c, 'Name') or ''
    return ''


# ---------------------------------------------------------------- reading the fields
def combo_selection(c):
    """Current text of a ComboBox WITHOUT opening it.

    Measured 2026-11-06: `SelectionPattern.GetSelection()` returns one
    unrealized `ListItem cls=ListBoxItem` whose only child is
    `Text cls=TextBlock Name='节点:29 R88D-KN04H-ECT(轴名示例)'` - i.e. the selected
    item's display text is readable while the drop-down is closed, the ComboBox has
    no children of its own, and MSAA gives ''.  This is the read path; Expand() is
    only needed to enumerate the alternatives.
    """
    try:
        sp = c.GetSelectionPattern()
    except Exception:
        return ''
    if sp is None:
        return ''
    for i in sp.GetSelection():
        t = item_text(i)
        if not t:
            sub = []
            U.walk(i, 0, dict(all=True, depth=4, max_lines=40, pat=False), sub)
            for s in sub:
                if '|Text|' in s or 'TextBlock' in s:
                    t = s.split('|')[1]
                    break
        if t:
            return t
    return ''


def value_of(c, allow_expand=False):
    """Best-effort current value of one control. Returns (text, how)."""
    if c.ControlTypeName == 'ComboBoxControl':
        t = combo_selection(c)
        if t:
            return t, 'SelText'
    try:
        v = c.GetValuePattern()
        if v is not None:
            return v.Value or '', 'Value'
    except Exception:
        pass
    try:
        lg = c.GetLegacyIAccessiblePattern()
        if lg is not None:
            val = (lg.Value or '').strip()
            if val:
                return val, 'MSAA'
    except Exception:
        pass
    if c.ControlTypeName == 'CheckBoxControl':
        try:
            t = c.GetTogglePattern()
            if t is not None:
                return {0: 'Unchecked', 1: 'Checked', 2: 'Indeterminate'}.get(
                    t.ToggleState, str(t.ToggleState)), 'Toggle'
        except Exception:
            pass
    if c.ControlTypeName == 'RadioButtonControl':
        try:
            s = c.GetSelectionItemPattern()
            if s is not None:
                return ('Checked' if s.IsSelected else 'Unchecked'), 'SelItem'
        except Exception:
            pass
    kids = c.GetChildren()
    for k in kids:
        if k.ControlTypeName == 'TextControl':
            n = U.prop(k, 'Name') or ''
            if n:
                return n, 'ChildText'
    if c.ControlTypeName == 'ComboBoxControl' and allow_expand:
        sel, n = combo_by_expand(c)
        return sel, ('ComboSel' if sel else 'ComboEmpty(%d)' % n)
    nm = U.prop(c, 'Name') or ''
    return nm, ('Name' if nm else 'none')


_PID = [0]


def field_value(root, ctrl, label=None):
    """Value of one field, with the two ComboBox realization traps handled.

    Measured 2026-11-06 on three different pages of the same project:

    * an already-open page answers `SelectionPattern.GetSelection()` straight away
      (19 fields read as SelText);
    * a page that was opened seconds earlier answers NOTHING on a closed box -
      every enabled ComboBox comes back empty (0 SelText,
      25 ComboEmpty);
    * and with the drop-down OPEN no item reports SelectionItem.IsSelected
      (39 node items, none flagged).

    So the order is: closed box first (never disturb another box), then for an
    enabled ComboBox that stayed empty, open/close the drop-down once - that
    realizes the selection container - and read the closed box again.  Only if
    that still says nothing is the ComboBox treated as genuinely unselected.
    """
    v, how = value_of(ctrl, allow_expand=False)
    if v or ctrl.ControlTypeName != 'ComboBoxControl' or label is None:
        return v, how
    if not U.prop(ctrl, 'IsEnabled', True):
        return '', how + '+disabled'
    c2 = find_field(root, label)
    if c2 is None:
        return v, how
    v2, how2 = value_of(c2, allow_expand=True)
    if v2:
        return v2, how2
    c3 = find_field(root, label)
    if c3 is not None:
        v3, how3 = value_of(c3, allow_expand=False)
        if v3:
            return v3, 'SelText!realized'
    return v2, how2


def combo_by_expand(c):
    """Open a ComboBox through UIA, report the selected item's text, close it again.

    Measured 2026-11-06: with the drop-down OPEN, no item reports
    SelectionItem.IsSelected - every one of the 39 node items came back unflagged
    while SelectionPattern on the closed box did name the selected one.  So this is
    only a fallback for the cases where the closed box yields nothing, and it can
    honestly say "no selection" - it returns (text, item_count), with text='' when
    nothing was flagged.  An empty ComboBox is then an empty ComboBox, not a read
    failure, which matters because the plan generator diffs on this value.

    The drop-down is a separate top-level HWND of the same pid (control-tree.md §15),
    so the items are looked for in the popup windows, not under the ComboBox - the
    collapsed ComboBox has no children at all.
    """
    try:
        ec = c.GetExpandCollapsePattern()
    except Exception:
        return '', 0
    if ec is None:
        return '', 0
    ec.Expand()
    time.sleep(0.8)
    seen, sel = [], ''
    for w in U.popup_roots(_PID[0]):
        try:
            top = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        except Exception:
            continue
        for i in U.find_by_type(top, ('ListItemControl',), maxd=12):
            t = item_text(i)
            if not t:
                continue
            seen.append(t)
            try:
                sp = i.GetSelectionItemPattern()
                if sp is not None and sp.IsSelected:
                    sel = t
            except Exception:
                pass
    try:
        ec.Collapse()
    except Exception:
        U.esc(1)
    time.sleep(0.4)
    return sel, len(seen)


def item_text(i):
    """Display text of one list item: its child Text, never the ViewModel Name."""
    for k in i.GetChildren():
        if k.ControlTypeName == 'TextControl':
            n = U.prop(k, 'Name') or ''
            if n:
                return n
    nm = U.prop(i, 'Name') or ''
    return '' if '.' in nm else nm


def expand_groups(root):
    """Open every folded Expander of the current section body.

    Measured 2026-11-06: while the `subsectionExpander` groups are
    folded, the settings rows are not in the UIA tree at all - 单位换算设置 reported
    exactly one row (显示单位 + one unselected RadioButton).  So a read that skips
    this step silently under-reports the page; this is the same folded-subtree trap
    as pitfalls §57, only here the fold is a pattern ExpandCollapse.Expand() fixes.

    It is deliberately NOT limited to AutomationId=='subsectionExpander':
    轴基本设置 hides its PDO table behind a second expander named 详细设置
    (a MultiPDOTableFieldView, see control-tree.md §15) and the per-axis PDO
    function numbers only become readable once that one is open too.
    """
    n = 0
    for g in U.find_by_type(root, ('GroupControl', 'CustomControl'), maxd=20):
        try:
            ec = g.GetExpandCollapsePattern()
        except Exception:
            continue
        if ec is None:
            continue
        try:
            if ec.ExpandCollapseState == 0:            # Collapsed
                ec.Expand()
                n += 1
                time.sleep(0.5)
        except Exception:
            pass
    return n


FIELD_KINDS = ('EditControl', 'ComboBoxControl', 'CheckBoxControl', 'RadioButtonControl',
               'ListControl', 'SliderControl')


def rect_of(c):
    r = U.prop(c, 'BoundingRectangle')
    try:
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return (0, 0, 0, 0)


def rid(c):
    try:
        return tuple(c.GetRuntimeId())
    except Exception:
        return id(c)


def collect_body(root):
    """Everything worth knowing inside the section body, in reading order."""
    texts, ctrls, groups = [], [], []

    def rec(c, d, group):
        if d > 26:
            return
        ct = c.ControlTypeName
        aid = U.prop(c, 'AutomationId') or ''
        if ct == 'GroupControl' and aid == 'subsectionExpander':
            group = U.prop(c, 'Name') or group
            groups.append(c)
        if ct == 'TextControl':
            nm = U.prop(c, 'Name') or ''
            r = rect_of(c)
            if nm and r[2] > r[0] and aid != 'TitleTextBlock':
                texts.append((nm, r, group, c))
        elif ct in FIELD_KINDS:
            ctrls.append((c, rect_of(c), group, ct))
        for k in c.GetChildren():
            rec(k, d + 1, group)
    for k in root.GetChildren():
        if k.ControlTypeName == 'CustomControl' and U.prop(k, 'ClassName') == \
                'HelpWithinSectionDetailsView':
            for g in k.GetChildren():
                rec(g, 0, '')
    if not ctrls:
        rec(root, 0, '')
    return texts, ctrls, groups


def label_for(ctrl, rect, texts, taken):
    """The Text sitting immediately left of `ctrl` on the same row (§15 pairing rule).

    Returns (label, text_element).  A label is consumed by the first control it
    serves, so a row with one label and two boxes cannot hand the same name to both.
    """
    best, bx, bel = '', -10 ** 9, None
    cy = (rect[1] + rect[3]) / 2.0
    for nm, tr, grp, c in texts:
        if rid(c) in taken:
            continue
        tcy = (tr[1] + tr[3]) / 2.0
        if abs(tcy - cy) > 12:
            continue
        if tr[2] > rect[0] + 2:                  # label must end before the control starts
            continue
        if tr[2] > bx:
            best, bx, bel = nm, tr[2], c
    return best, bel


def fields(root):
    """[(key, control, group, kind)] for every interactive control of the section.

    Two row shapes exist and both have to be covered, measured 2026-11-06:
      * `ComponentsFieldView` rows - label Text + control, one row per setting
        (轴基本设置 / 操作设置 / 限位设置 / 原点返回设置 / 位置计数设置 / 伺服驱动设置);
      * `TravelDistanceSettingFieldView` (单位换算设置) - a flat canvas where the
        labels and the Edit boxes are siblings, so a row-walking reader sees nothing
        and only geometric pairing works.
    Key = the control's own UIA Name (radio buttons, check boxes) else the label found
    to its left.  Repeated keys get '#2', '#3' in top-to-bottom order, so the second
    通道 box stays addressable without guessing.
    """
    texts, ctrls, _ = collect_body(root)
    out, used, taken = [], {}, set()
    ctrls.sort(key=lambda t: (t[1][1], t[1][0]))
    for c, rect, group, ct in ctrls:
        own = U.prop(c, 'Name') or ''
        key, src = (own, None) if own and '.' not in own else label_for(c, rect, texts, taken)
        if src is not None:
            taken.add(rid(src))
        if not key:
            continue
        used[key] = used.get(key, 0) + 1
        if used[key] > 1:
            key = '%s#%d' % (key, used[key])
        out.append((key, c, group, ct.replace('Control', '')))
    return out


def cmd_nav(argv):
    """ss_axis.py nav <pid> <out> <tree.path>"""
    pid, mw, pane, name = open_axis(argv[0], argv[2] if len(argv) > 2 else '0.4.0.0')
    if pane is None:
        log('NO PANE for %r' % name)
        return 1
    root = page_root(mw, pane, log)
    lines = ['# nav pid=%s doc=%r' % (pid, name),
             '# root %s' % U.line_of(root, True),
             '# rail (tree order) %s' % [a for a, _ in section_buttons(root)]]
    for aid in SEC_ORDER:
        t = goto_section(root, aid)
        lines.append('  %-20s -> title=%-14s rows=%d' % (aid, t, len(fields(root))))
    U.dump(argv[1], lines[0], lines[1:])
    log('lines=%d -> %s' % (len(lines), argv[1]))
    return 0


def cmd_read(argv):
    """ss_axis.py read <pid> <out> <tree.path> [aid,aid,...]"""
    pid, mw, pane, name = open_axis(argv[0], argv[2])
    if pane is None:
        log('NO PANE for %r' % name)
        return 1
    root = page_root(mw, pane, log)
    want = argv[3].split(',') if len(argv) > 3 else SEC_ORDER
    num = argv[2].split('.')[-1]
    shown = verify_axis(root, num)
    if shown and shown != num:
        log('ABORT: path %s wants 轴号 %s, the page in front shows %s'
            % (argv[2], num, shown))
        return 4
    lines = ['# read pid=%s doc=%r 轴号=%s  (field rows are TAB-separated: label kind VALUE how group enabled left top w h id)' % (pid, name, shown)]
    for aid in want:
        t = goto_section(root, aid)
        lines.append('===== %s  [%s]' % (aid, t))
        for label, ctrl, group, kind in fields(root):
            v, how = field_value(root, ctrl, label)
            r = U.prop(ctrl, 'BoundingRectangle')
            lines.append('\t'.join(str(x) for x in (
                label, kind,
                (v or '')[:60].replace('\n', '\\n').replace('\t', ' '), how,
                group or '-', U.prop(ctrl, 'IsEnabled', True),
                r.left, r.top, r.right - r.left, r.bottom - r.top,
                U.prop(ctrl, 'AutomationId') or '')))
    U.dump(argv[1], lines[0], lines[1:])
    log('lines=%d -> %s' % (len(lines), argv[1]))
    return 0


def cmd_dump(argv):
    """ss_axis.py dump <pid> <out> <doc-name> [section-aid]"""
    pid = U.resolve_pid(str(argv[0]))
    _PID[0] = pid
    mw = U.main_window(pid)
    pane = U.find_doc(mw['hwnd'], argv[2])
    if pane is None:
        log('no pane %r' % argv[2])
        return 1
    root = page_root(mw, pane, log)
    if len(argv) > 3:
        goto_section(root, argv[3])
    lines = []
    U.walk(root, 0, dict(all=True, depth=24, max_lines=20000, pat=True), lines)
    U.dump(argv[1], '# dump %r pid=%s section=%s' % (argv[2], pid, argv[3:4]), lines)
    log('lines=%d -> %s' % (len(lines), argv[1]))
    return 0


def cmd_close(argv):
    """ss_axis.py close <pid> <out> <doc-name>"""
    pid = U.resolve_pid(str(argv[0]))
    mw = U.main_window(pid)
    U.dump(argv[1], '# close', [U.close_document(mw['hwnd'], argv[2])])
    log('close %r done' % argv[2])
    return 0


def find_field(root, label):
    for lb, ctrl, group, kind in fields(root):
        if lb == label:
            return ctrl
    return None


def raise_tab(hwnd, name):
    """Click a document TAB so its page comes to the front; True if one was clicked.

    Needed because page_root() reads whatever body is in front, and `cmd_open` on a node
    whose document is ALREADY open does not necessarily activate that tab.
    """
    for c in U.find_by_type(auto.ControlFromHandle(wt.HWND(hwnd)),
                            ('PaneControl',), maxd=24):
        if (U.prop(c, 'ClassName') or '') != 'DocumentWindow':
            continue
        if (U.prop(c, 'Name') or '') != name:
            continue
        r = U.prop(c, 'BoundingRectangle')
        U.left_click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(1.2)
        return True
    return False


def verify_axis(root, num):
    """Return the 轴号 the root actually shows, or '' when the field is not there.

    Safety net for page_root(): the hit-test route reads whatever document is in FRONT,
    and cmd_open does not always raise the tab it opened.  Writing 轴1's plan into 轴4
    would be silent and destructive, so every apply/set checks the number first.
    """
    goto_section(root, 'basic_setting')
    c = find_field(root, '轴号')
    if c is None:
        return ''
    return ustr(value_of(c)[0])


def center(c):
    r = U.prop(c, 'BoundingRectangle')
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def set_edit(ctrl, value, mw):
    """TextBox: real click + Ctrl+A + type the value + real Tab, then read back.

    Measured 2026-11-06: `auto.SendKeys('^a')` puts the
    LITERAL characters `^a` in the field, so the old select-all/paste route wrote
    '^a^v262144' instead of '262144'.  Accelerators must be issued as separate key
    events (combo()) and a plain ASCII value is simply typed - the click selects
    the whole field, so the first character replaces it.

    ValuePattern.SetValue is still tried first and only kept when the value both
    reads back and survives the Tab - WPF bindings are LostFocus-triggered, so a
    bare SetValue can sit in the control without ever reaching the project
    (pitfalls §30).
    """
    res = []
    try:
        vp = ctrl.GetValuePattern()
        if vp is not None:
            vp.SetValue(str(value))
            time.sleep(0.3)
            res.append('SetValue->%r' % (vp.Value or ''))
    except Exception as e:
        res.append('SetValue!%s' % e.__class__.__name__)
    U.force_foreground(mw['hwnd'])
    ctrl.Click()
    time.sleep(0.25)
    combo(0x11, 0x41)                                   # Ctrl+A = whole field
    time.sleep(0.25)
    if str(value).isascii():
        auto.SendKeys(str(value), interval=0.03)
        how = 'typed'
    else:
        auto.SetClipboardText(ustr(value))
        combo(0x11, 0x56)                               # Ctrl+V
        how = 'pasted'
    time.sleep(0.3)
    U.key(0x09)                                         # real VK_TAB commits
    U.key(0x09, up=True)
    time.sleep(0.4)
    res.append('%s->%r' % (how, value_of(ctrl)[0] or ''))
    return ' '.join(res)


def popup_list(pid):
    """[(text, ctrl, rect, offscreen)] for every ListItem in this pid's popups."""
    out = []
    for w in U.popup_roots(pid):
        try:
            top = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        except Exception:
            continue
        for i in U.find_by_type(top, ('ListItemControl',), maxd=12):
            t = item_text(i)
            if not t:
                continue
            r = U.prop(i, 'BoundingRectangle')
            out.append((t, i, (r.left, r.top, r.right, r.bottom),
                        bool(U.prop(i, 'IsOffscreen', False))))
    return out


def visible_match(lst, value):
    """Exact caption first, substring only when unique - and only REALISED rows.

    Measured 2026-11-07: the 输出设备1 list is virtualised, so an
    item can be enumerated with a stale rect and IsOffscreen=True.  Clicking that rect hits
    whatever row is actually painted there - the first run bound 轴1 to the wrong slave
    because the device-name keyword was a substring of four captions and only the later rows
    were on screen.  Off-screen rows are therefore never a click target.
    """
    vis = [x for x in lst if not x[3]]
    ex = [x for x in vis if x[0] == value]
    if ex:
        return ex[0]
    subs = [x for x in vis if value and value in x[0]]
    return subs[0] if len(subs) == 1 else None


def combo_scroll_pick(ctrl, value):
    """Open the drop-down with a REAL click and click the wanted row, wheeling to it.

    Measured 2026-11-07: the ListBoxItems of a Sysmac ComboBox
    drop-down answer SelectionItemPattern with None (AttributeError on .Select()), and
    UIA Expand() opens the list WITHOUT keyboard focus, so neither Select() nor
    VK_DOWN x n + Enter can reach it.  A real click on the box both opens it and focuses
    it, and then the row is a plain mouse target.  This is what made 轴1's
    输出设备1 = '节点:20 伺服轴1(轴1)' stick.
    """
    r = U.prop(ctrl, 'BoundingRectangle')
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    U.left_click(cx, cy)
    time.sleep(1.2)
    hit = visible_match(popup_list(_PID[0]), value)
    for dy, n in ((2, 12), (-2, 20)):
        # both directions: the freshly opened list is already scrolled to the middle, so
        # 'wheel down until it appears' alone would run off the end and never find it
        for _ in range(n):
            if hit is not None:
                break
            U.wheel(dy, cx + 120, cy + 40)
            time.sleep(0.7)
            hit = visible_match(popup_list(_PID[0]), value)
        if hit is not None:
            break
    if hit is None:
        U.esc(1)
        return 'SCROLL-NO-VISIBLE-ITEM %r' % (value,)
    br = hit[2]
    U.left_click((br[0] + br[2]) // 2, (br[1] + br[3]) // 2)
    time.sleep(0.9)
    return 'clicked-row(%s)' % value


def set_combo(ctrl, value, real=False):
    """ComboBox: UIA Expand + Select, and when that does not take, click the row."""
    try:
        ec = ctrl.GetExpandCollapsePattern()
    except Exception as e:
        return 'no-expand %s' % e.__class__.__name__
    if ec is None:
        return 'no-expand'
    ec.Expand()
    time.sleep(0.8)
    lst = popup_list(_PID[0])
    names = [t for t, i, r, off in lst]
    exact = [x for x in lst if x[0] == value]
    subs = [x for x in lst if value and value in x[0] and x[0] != value]
    # 轴使用 is the trap: the wanted item '使用的轴' is a substring of BOTH
    # '未使用的轴(不可更改为使用轴)' and '未使用的轴(可以更改为使用轴)', so a first
    # substring hit would silently pick 未使用的轴.  Exact match wins; a substring is
    # only used when exactly one item contains it.
    hit = exact[0][1] if exact else (subs[0][1] if len(subs) == 1 else None)
    if hit is None:
        try:
            ec.Collapse()
        except Exception:
            U.esc(1)
        return 'NO-ITEM %r among %s' % (value, names[:25])
    how = ''
    try:
        sp = hit.GetSelectionItemPattern()
        if sp is None:
            raise AttributeError('SelectionItemPattern is None')
        sp.Select()
        how = 'Select'
    except Exception as e:
        how = 'Select!%s' % e.__class__.__name__
    try:
        ec.Collapse()
    except Exception:
        pass
    time.sleep(0.5)
    if combo_selection(ctrl) != ustr(value):
        how += '+scroll'
        how += ' ' + combo_scroll_pick(ctrl, value)
    time.sleep(0.4)
    return '%s(%s)' % (how, value)


def set_toggle(ctrl, value):
    want = str(value).strip().lower() in ('1', 'true', 'checked', 'y', '是', '勾选')
    try:
        t = ctrl.GetTogglePattern()
    except Exception as e:
        return 'no-toggle %s' % e.__class__.__name__
    if t is None:
        return 'no-toggle'
    cur = t.ToggleState == 1
    if cur == want:
        return 'already'
    t.Toggle()
    time.sleep(0.4)
    return 'toggled->%s' % t.ToggleState


def set_field(root, mw, aid, label, value):
    """One labelled field on one section.  Returns a log line, and whether it looks done."""
    goto_section(root, aid)
    ctrl = find_field(root, label)
    if ctrl is None:
        return 'MISS  %-20s %-14s no such label' % (aid, label), False
    if not U.prop(ctrl, 'IsEnabled', True):
        return 'SKIP  %-20s %-14s disabled (cur=%s)' % (aid, label, field_value(root, ctrl, label)[0]), True
    kind = ctrl.ControlTypeName.replace('Control', '')
    before = field_value(root, ctrl, label)[0]
    if kind == 'Edit':
        how = set_edit(ctrl, value, mw)
    elif kind == 'ComboBox':
        how = set_combo(ctrl, value)
    elif kind == 'CheckBox':
        how = set_toggle(ctrl, value)
    elif kind == 'RadioButton':
        ok = str(value).strip().lower() in ('1', 'true', 'checked', 'y', '是', '选中')
        try:
            if ok and not ctrl.GetSelectionItemPattern().IsSelected:
                ctrl.GetSelectionItemPattern().Select()
                how = 'selected'
            else:
                how = 'already'
        except Exception as e:
            how = 'radio!%s' % e.__class__.__name__
    else:
        return 'CANT  %-20s %-14s kind=%s' % (aid, label, kind), False
    time.sleep(0.3)
    after = field_value(root, ctrl, label)[0]
    good = (after or '') == ustr(value)
    return '%-5s %-20s %-14s %r -> %r  want=%r  [%s]' % (
        'OK' if good else 'CHECK', aid, label, before, after, value, how), good


def cmd_set(argv):
    """ss_axis.py set <pid> <out> <tree.path> <aid> <label> <value>"""
    pid, mw, pane, name = open_axis(argv[0], argv[2])
    if pane is None:
        log('NO PANE for %r' % name)
        return 1
    root = page_root(mw, pane, log)
    num = argv[2].split('.')[-1]
    shown = verify_axis(root, num)
    if shown and shown != num:
        log('ABORT: path %s wants 轴号 %s, the page in front shows %s'
            % (argv[2], num, shown))
        return 4
    line, good = set_field(root, mw, argv[3], argv[4], argv[5])
    U.dump(argv[1], '# set pid=%s doc=%r' % (pid, name), [line])
    log(line)
    return 0 if good else 3


def cmd_apply(argv):
    """ss_axis.py apply <pid> <out> <plan.json> [path_filter,...]

    plan.json = [{"path":"0.4.0.0","sets":[{"section","label","value"}...]}]
    One process per plan entry: the page is opened once and every field of that axis
    is written in the same UIA session (no re-open per field, no keyboard shortcuts
    that could leak into another page).
    """
    out = argv[1]
    plan = json.load(open(argv[2], encoding='utf-8'))
    filt = argv[3].split(',') if len(argv) > 3 else None
    lines, n_ok, n_bad = [], 0, 0
    for entry in plan:
        p = entry['path']
        if filt and p not in filt:
            lines.append('#### %s skipped by filter' % p)
            continue
        pid, mw, pane, name = open_axis(argv[0], p)
        if pane is None:
            lines.append('#### %s NO PANE (%r)' % (p, name))
            n_bad += 1
            continue
        root = page_root(mw, pane, log)
        num = p.split('.')[-1]
        shown = verify_axis(root, num)
        if shown and shown != num:
            raised = raise_tab(mw['hwnd'], name)
            root = page_root(mw, pane, log)
            shown = verify_axis(root, num)
            lines.append('#### %s tab raised=%s, 轴号 now=%s' % (p, raised, shown))
        if shown and shown != num:
            lines.append('#### %s ABORT 轴号=%r (page in front is not this axis)'
                         % (p, shown))
            n_bad += 1
            continue
        lines.append('#### %s  doc=%r  轴号=%s  fields=%d'
                     % (p, name, shown, len(entry.get('sets', []))))
        for s in entry.get('sets', []):
            line, good = set_field(root, mw, s['section'], s['label'], s['value'])
            lines.append(line)
            n_ok += 1 if good else 0
            n_bad += 0 if good else 1
        if entry.get('close'):
            lines.append('#### close %r -> %s' % (name, U.close_document(mw['hwnd'], name)))
    lines.append('#### TOTAL ok=%d check/miss=%d' % (n_ok, n_bad))
    U.dump(out, '# apply %s' % argv[2], lines)
    log('apply done ok=%d bad=%d -> %s' % (n_ok, n_bad, out))
    return 0 if n_bad == 0 else 3


def cmd_probe(argv):
    """ss_axis.py probe <pid> <out> <tree.path> <aid> <key>

    One control, everything UIA will say about it: patterns, Name/HelpText,
    SelectionPattern.GetSelection(), and (with the drop-down opened through UIA)
    every candidate item with its own selected flag.  This is how the read path for
    a new control shape gets decided instead of guessed.
    """
    pid, mw, pane, name = open_axis(argv[0], argv[2])
    if pane is None:
        log('NO PANE')
        return 1
    root = page_root(mw, pane, log)
    goto_section(root, argv[3])
    ctrl = find_field(root, argv[4])
    lines = ['# probe pid=%s doc=%r %s/%s' % (pid, name, argv[3], argv[4])]
    if ctrl is None:
        lines.append('NOT FOUND; keys=%s' % [k for k, _, _, _ in fields(root)])
        U.dump(argv[1], lines[0], lines[1:])
        log('not found')
        return 3
    lines.append('line  %s' % U.line_of(ctrl, True))
    try:
        sel = ctrl.GetSelectionPattern()
        if sel is not None:
            for i in sel.GetSelection():
                lines.append('  SelectionPattern -> %s' % U.line_of(i, True))
                sub = []
                U.walk(i, 0, dict(all=True, depth=6, max_lines=200, pat=True), sub)
                lines.extend(['    ' + s for s in sub])
    except Exception as e:
        lines.append('  SelectionPattern! %s' % e.__class__.__name__)
    for nm in ('Value', 'LegacyIAccessible', 'RangeValue', 'Toggle', 'SelectionItem'):
        try:
            p = getattr(ctrl, 'Get%sPattern' % nm)()
        except Exception:
            p = None
        if p is None:
            continue
        if nm == 'Value':
            lines.append('  Value=%r' % p.Value)
        elif nm == 'LegacyIAccessible':
            lines.append('  MSAA name=%r value=%r desc=%r' % (p.Name, p.Value, p.Description))
        elif nm == 'RangeValue':
            lines.append('  RangeValue=%r min=%r max=%r' % (p.Value, p.Minimum, p.Maximum))
        else:
            lines.append('  %s ok' % nm)
    if ctrl.ControlTypeName == 'ComboBoxControl':
        try:
            ctrl.GetExpandCollapsePattern().Expand()
        except Exception:
            pass
        time.sleep(0.8)
        for w in U.popup_roots(pid):
            try:
                top = auto.ControlFromHandle(wt.HWND(w['hwnd']))
            except Exception:
                continue
            for i in U.find_by_type(top, ('ListItemControl',), maxd=12):
                flag = ''
                try:
                    sp = i.GetSelectionItemPattern()
                    if sp is not None and sp.IsSelected:
                        flag = ' SELECTED'
                except Exception:
                    flag = ' select?'
                lines.append('  item %s%s  childtext=%r' % (
                    U.line_of(i, False), flag, item_text(i)))
        try:
            ctrl.GetExpandCollapsePattern().Collapse()
        except Exception:
            U.esc(1)
    U.dump(argv[1], lines[0], lines[1:])
    log('lines=%d -> %s' % (len(lines), argv[1]))
    return 0


def menu_leaves(pid, skip=()):
    """[(MenuItemControl, name, rect, enabled)] in the open context menus.

    Measured 2026-11-06: Sysmac's node menus are NOT
    #32768 windows - they are `WindowsForms10.Window.20808.app...` popups plus a
    SysShadow window, and a submenu is a SECOND such popup window with its own
    HWND, whose items UIA already lists as children of the parent item while the
    submenu is still undrawn (rect (0,0,0,0)).  `skip` is the set of popup hwnds to
    ignore, which is how a caller looks at only the submenu that just appeared.
    """
    out = []
    for w, c, _n in U.menu_popups(pid):
        if w['hwnd'] in skip:
            continue
        for k in U.find_by_type(c, ('MenuItemControl',), maxd=8):
            r = U.prop(k, 'BoundingRectangle')
            out.append((k, (U.prop(k, 'Name') or '').strip(),
                        (r.left, r.top, r.right - r.left, r.bottom - r.top),
                        U.prop(k, 'IsEnabled', True)))
    return out


def pick_menu(items, want):
    """Menu item by exact name, else by '&' mnemonic letter, else by prefix."""
    for it, nm, rect, en in items:
        if nm == want:
            return it, nm, rect, en
    for it, nm, rect, en in items:
        if nm.replace(' ', '').lower().startswith(want.replace(' ', '').lower()):
            return it, nm, rect, en
    return None, None, None, None


def hover(x, y):
    """Move the real cursor over (x,y) with a 1 px nudge.

    Measured 2026-11-06: `SetCursorPos` alone (and even an explicit WM_MOUSEMOVE
    posted to the window under the point) does NOT open a Win32 submenu - the menu
    modal loop only reacts to moves that come through the raw input queue
    (实测：添加 highlighted nothing, no second
    popup).  mouse_event(MOUSEEVENTF_MOVE) by ±1 px does get seen, so hover is
    always issued as a two-step move.
    """
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.2)
    u.mouse_event(0x0001, 1, 0, 0, 0)          # MOUSEEVENTF_MOVE, dx=+1 (relative)
    time.sleep(0.15)
    u.mouse_event(0x0001, ctypes.c_int(-1).value, 0, 0, 0)
    time.sleep(0.7)


def menu_windows(pid):
    """[(hwnd, [(name, rect, enabled), ...])] for every open menu popup window.

    Recorded because the popup topology is what decides how a submenu is found:
    2026-11-06 the 添加 submenu does get its OWN
    `WindowsForms10.Window.20808.app...` window, but UIA still enumerates
    `运动控制轴(M)` inside the PARENT menu's tree - so excluding the parent window
    by hwnd loses exactly the row we are hunting for.
    """
    res = []
    for w, c, _n in U.menu_popups(pid):
        rows = []
        for k in U.find_by_type(c, ('MenuItemControl',), maxd=8):
            r = U.prop(k, 'BoundingRectangle')
            rows.append(((U.prop(k, 'Name') or '').strip(),
                         (r.left, r.top, r.right - r.left, r.bottom - r.top),
                         U.prop(k, 'IsEnabled', True)))
        res.append((w['hwnd'], rows))
    return res


def drawn_since(pid, hidden):
    """Menu items UIA already NAMED while undrawn that now have a real rectangle.

    That identity test - not a window filter - is what recognizes the submenu:
    `hidden` is the set of names the parent menu reported with rect (0,0,0,0)
    before hovering, and the submenu rows are those same names, drawn.
    """
    return [(it, nm, rect, en) for it, nm, rect, en in menu_leaves(pid)
            if rect[2] > 0 and nm in hidden]


def open_submenu(pid, mi_rect, hidden):
    """Try every recorded way to get 添加's submenu on screen; return its items.

    Ladder: hover (nudging the cursor), then the keyboard.  Measured 2026-11-06:
    the hover nudge is what actually draws the submenu,
    while VK_DOWN + VK_RIGHT on top of an already-open submenu DISMISSES the whole
    menu ("after VK_RIGHT" only a tooltip window is left), so the
    keyboard is a fallback only when the cursor never got the submenu out.
    """
    mx, my = mi_rect[0] + mi_rect[2] // 2, mi_rect[1] + mi_rect[3] // 2
    for _attempt in range(3):
        hover(mx, my)
        time.sleep(0.4)
        got = drawn_since(pid, hidden)
        if got:
            return got, 'hover'
    U.key(0x28)                                    # VK_DOWN -> first item (添加)
    time.sleep(0.4)
    U.key(0x27)                                    # VK_RIGHT -> open the submenu
    time.sleep(0.8)
    got = drawn_since(pid, hidden)
    if got:
        return got, 'keyboard'
    return [], ''


def combo(vk_mod, vk):
    """A real modifier+key press (down/down/up/up) through keybd_event.

    Measured 2026-11-06: `auto.SendKeys('^a')` typed the
    literal characters `^a` into the F2 box - uiautomation's parser does not treat
    `^` as CTRL here - so accelerators have to be issued as separate events.
    """
    U.key(vk_mod)
    time.sleep(0.05)
    U.key(vk)
    time.sleep(0.05)
    U.key(vk, up=True)
    time.sleep(0.05)
    U.key(vk_mod, up=True)


def put_name(name):
    """Get NAME into the F2 edit box, by the route that actually works.

    The box opens with the whole old name selected, so the first typed character
    replaces it (`^a^v` landed in place of `MC_Axis000`).  Plain ASCII
    names are typed; anything else goes through the clipboard with a real Ctrl+V.
    """
    if name.isascii():
        auto.SendKeys(name, interval=0.03)
        return 'typed'
    auto.SetClipboardText(name)
    combo(0x11, 0x41)                       # Ctrl+A
    time.sleep(0.2)
    combo(0x11, 0x56)                       # Ctrl+V
    return 'pasted'


def doc_names(mw):
    """Names of the open editor panes - the MODEL's own titles.

    Measured 2026-11-06: the tree row text goes stale
    after an inline rename.  Axis 1 was `AxisA` in the tree while its open
    document was still `MC_Axis001 (1,MC1)`; after renaming it to AxisB the
    pane re-titled to `AxisB (1,MC1)` while the row read back the previous
    `AxisA`.  So a rename is only proven by the pane title, never by the caption.
    """
    r = auto.ControlFromHandle(wt.HWND(mw['hwnd']))
    return [k.split('|')[0] for k in U.doc_panes(r)
            if k.endswith('|PaneControl')]


def doc_has(mw, name):
    """Is an editor open for the object literally named `name`?

    Compares the name part before ' (' - a prefix test would read the pane
    'AxisB (1,MC1)' as proof that AxisA exists (measured 2026-11-06:
    axis 1's model name was still the scratch AxisB).
    """
    return any(d.split(' (')[0] == name for d in doc_names(mw))


def name_state(cap, name):
    """'renamed' / 'label-only' / 'other' for a tree caption after a rename.

    Measured 2026-11-06: Sysmac renders a motion axis row as
    '<轴名> (<轴号>,MC1)' - every row of the source project has that suffix,
    and in the Copy the two rows that came out
    'AxisA (0,MC1)' / 'AxisC (2,MC1)' also re-titled their open document
    pane, while 'AxisD' / 'AxisE' / 'AxisF' / 'AxisG' kept a
    'MC_Axis00N (N,MC1)' pane.  So the suffix is the visible marker that the
    rename reached the model; a bare caption means only the row text changed.
    """
    if not cap:
        return 'other'
    if cap.startswith(name + ' (') and cap.endswith(')'):
        return 'renamed'
    if cap == name:
        return 'label-only'
    return 'other'


def rename_via_menu(pid, thw, mw, h, path, name, lines):
    """Right-click the row -> 重命名(R) -> write the name -> Enter.

    Measured 2026-11-06: an axis row's context menu is
    编辑(E) / 剪切(T) / 复制(C) / 删除(D) / 重命名(R) / 开始MC试运行(S) /
    停止MC试运行(O), all with real rectangles, so the app's own rename command can
    be taken by a click without handing keyboard focus to the tree.
    """
    pt = U.row_hit(pid, thw, mw, h, path)
    lines.append('# menu rename: hit=%s' % (pt,))
    if not pt:
        return False
    U.right_click(pt[0], pt[1])
    time.sleep(0.9)
    mi, nm, rect, en = pick_menu(menu_leaves(pid), '重命名')
    if mi is None or rect[2] <= 0 or not en:
        lines.append('# NO 重命名 ITEM (%r %s enabled=%s)' % (nm, rect, en))
        U.esc(2)
        return False
    U.left_click(rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)
    time.sleep(0.9)
    how = put_name(name)
    time.sleep(0.4)
    U.key(0x0D)
    U.key(0x0D, up=True)
    time.sleep(1.5)
    cap, _f = U.node_text(pid, thw, h)
    lines.append('# menu rename wrote %r by %s -> caption=%r [%s]'
                 % (name, how, cap, name_state(cap, name)))
    return name_state(cap, name) == 'renamed'


def rename_row(pid, thw, mw, h, path, name, lines, tries=5):
    """F2 the tree row -> write the name -> real VK_RETURN, then read it back.

    Measured 2026-11-06: a freshly
    inserted row is NOT in the tree's realised order map for a second or two,
    and `row_hit` starts by checking that map, so calling it straight after the
    insert returns None - the same handle 2 s later gives a hit point.  The
    rename therefore retries until the row is realised.

    The row is clicked once by row_hit to prove the tree names it back, which
    also selects it, so no extra click is issued - a second click this close
    would read as a double-click and open the axis editor.
    """
    cap0, _f0 = U.node_text(pid, thw, h)
    pt = None
    for _t in range(tries):
        pt = U.row_hit(pid, thw, mw, h, path)
        if pt:
            break
        time.sleep(1.5)
    lines.append('# rename %r -> %r hit=%s' % (cap0, name, pt))
    if not pt:
        lines.append('# NOT RENAMED - row never came back into the order map')
        return False
    U.force_foreground(mw['hwnd'])
    U.key(0x71)                                   # F2 = inline rename
    U.key(0x71, up=True)
    time.sleep(0.8)
    how = put_name(name)
    time.sleep(0.4)
    lines.append('# wrote %r by %s' % (name, how))
    U.key(0x0D)                                   # real VK_RETURN commits
    U.key(0x0D, up=True)
    time.sleep(1.5)
    cap1, full1 = U.node_text(pid, thw, h)
    # the tree caption carries the axis number and controller AFTER the name -
    # 'AxisA (0,MC1)' - so the read-back is compared on
    # the name part only, never against the whole caption.
    got = re.sub(r'\s*\([^)]*\)\s*$', '', cap1 or '')
    lines.append('# after F2 caption=%r full=%r name=%r' % (cap1, full1, got))
    return got == name


def cmd_rename(argv):
    """ss_axis.py rename <pid> <out> <tree.path> <NAME>

    Rename ONE tree row (an axis node straight after it was inserted) and read
    the caption back; exits 1 when the name did not take.
    """
    pid = U.resolve_pid(argv[0])
    out, ps, name = argv[1], argv[2], argv[3]
    mw = U.main_window(pid)
    thw = U.tree_hwnd(pid)
    path = [int(x) for x in ps.split('.')]
    U.force_foreground(mw['hwnd'])
    for k in range(1, len(path)):
        a = U.node_at(thw, path[:k])
        if a:
            U.expand_node(pid, thw, mw, a)
    h = U.node_at(thw, path)
    lines = ['# rename pid=%s path=%s' % (pid, ps)]
    if not h:
        lines.append('NO NODE %s' % ps)
        U.dump(out, lines[0], lines[1:])
        log('no node %s' % ps)
        return 1
    cap0, _f0 = U.node_text(pid, thw, h)
    lines.append('# before caption=%r docs=%s' % (cap0, doc_names(mw)))
    # The open editor pane title is the model's name, so it - not the (stale)
    # tree caption - decides whether the rename happened.  An axis with no open
    # document has no title to read, and then the caption is the only signal.
    def ok_now():
        d = doc_names(mw)
        if d:
            return doc_has(mw, name)
        return name_state(U.node_text(pid, thw, h)[0], name) == 'renamed'
    if not doc_has(mw, name):
        if name_state(cap0, name) == 'label-only':
            # The row text already equals the target while the model was never
            # told, and typing the SAME text again is something the app ignores:
            # 'AxisA' -> 'AxisA' stayed uncommitted through both the context
            # menu and F2, while 'AxisA' -> 'AxisB' committed
            # at once (pane became 'AxisB (1,MC1)').
            lines.append('# label-only: bouncing through %r' % (name + '_TMP',))
            rename_via_menu(pid, thw, mw, h, path, name + '_TMP', lines)
        if not doc_has(mw, name):
            rename_via_menu(pid, thw, mw, h, path, name, lines)
        if not doc_has(mw, name):
            rename_row(pid, thw, mw, h, path, name, lines)
    ok = ok_now()
    lines.append('# after caption=%r docs=%s -> %s'
                 % (U.node_text(pid, thw, h)[0], doc_names(mw), 'OK' if ok else 'NOT OK'))
    U.dump(out, lines[0], lines[1:])
    log('%s -> %s' % ('RENAMED' if ok else 'FAILED', out))
    return 0 if ok else 1


def cmd_add(argv):
    """ss_axis.py add <pid> <out> <tree.path> [--name NAME] [--item TEXT] [--list]

    Insert ONE axis under the 轴设置 node the way pitfalls §42 recorded it
    (right-click the node -> 添加 -> submenu), read the new tree row back, and
    optionally rename it inline with F2.  Nothing here is guessed:

      --list    open the menus, record them, press Esc, change nothing;
      --item    which submenu entry to take (default: first enabled one);
      --name    rename the new row (F2 -> clipboard paste -> Enter);
    """
    pid = U.resolve_pid(argv[0])
    out, ps = argv[1], argv[2]
    do_list = '--list' in argv
    name = argv[argv.index('--name') + 1] if '--name' in argv else None
    want = argv[argv.index('--item') + 1] if '--item' in argv else None
    mw = U.main_window(pid)
    thw = U.tree_hwnd(pid)
    path = [int(x) for x in ps.split('.')]
    U.force_foreground(mw['hwnd'])
    for k in range(1, len(path)):
        a = U.node_at(thw, path[:k])
        if a:
            U.expand_node(pid, thw, mw, a)
    h = U.node_at(thw, path)
    if not h:
        U.dump(out, '# add pid=%s %s' % (pid, ps), ['NO NODE %s' % ps])
        log('no node %s' % ps)
        return 1
    kids0 = U.kids_of(thw, h)
    cap = U.node_text(pid, thw, h)[0]
    pt = U.row_hit(pid, thw, mw, h, path)
    lines = ['# add pid=%s path=%s node=%r children=%d hit=%s' %
             (pid, ps, cap, len(kids0), pt)]
    if not pt:
        lines.append('NO HIT - the row never came back into view')
        U.dump(out, lines[0], lines[1:])
        log('no hit')
        return 1
    U.right_click(pt[0], pt[1])
    time.sleep(0.9)
    top = menu_leaves(pid)
    lines.append('# context menu:')
    for _it, nm, rect, en in top:
        lines.append('  %-22r enabled=%s %s' % (nm, en, rect))
    mi, mi_nm, mi_rect, mi_en = pick_menu(top, '添加')
    if mi is None:
        lines.append('NO 添加 ITEM')
        U.esc(2)
        U.dump(out, lines[0], lines[1:])
        log('no 添加 in %s' % [n for _i, n, _r, _e in top])
        return 1
    hidden = {nm for _i, nm, rect, _e in top if rect[2] <= 0}
    lines.append('# entries the parent menu already names but has not drawn: %r'
                 % sorted(hidden))
    sub, how_open = open_submenu(pid, mi_rect, hidden)
    lines.append('# submenu via %r: %s' % (
        how_open, [(nm, rect, en) for _i, nm, rect, en in sub]))
    for hw, rows in menu_windows(pid):
        lines.append('#  popup hwnd=%d -> %s' % (hw, [(nm, rect) for nm, rect, _e in rows]))
    if do_list:
        U.esc(3)
        U.dump(out, lines[0], lines[1:])
        log('list only -> %s' % out)
        return 0
    cand = sub or [(it, nm, rect, en) for it, nm, rect, en in top if rect[2] <= 0]
    target, tnm, trect, ten = (pick_menu(cand, want) if want
                               else ((None, None, None, None)))
    if target is None and not want:
        for it, nm, rect, en in cand:
            if en:
                target, tnm, trect = it, nm, rect
                break
    if target is None:
        lines.append('NO TARGET ITEM (%r) - nothing clicked' % want)
        U.esc(3)
        U.dump(out, lines[0], lines[1:])
        log('no target')
        return 1
    lines.append('# take %r %s' % (tnm, trect))
    if trect[2] > 0:
        U.left_click(trect[0] + trect[2] // 2, trect[1] + trect[3] // 2)
        lines.append('# real clicked')
    else:
        try:
            target.GetInvokePattern().Invoke()
            lines.append('# invoked through UIA')
        except Exception as e:
            lines.append('# invoke failed (%s)' % e.__class__.__name__)
    time.sleep(2.5)
    kids1 = U.kids_of(thw, h)
    lines.append('# children %d -> %d' % (len(kids0), len(kids1)))
    newh = kids1[-1] if len(kids1) > len(kids0) else None
    if newh:
        ncap, nfull = U.node_text(pid, thw, newh)
        lines.append('# new row h=%d caption=%r full=%r' % (newh, ncap, nfull))
        if name:
            rename_row(pid, thw, mw, newh, path + [len(kids1) - 1], name, lines)
    else:
        lines.append('# NO NEW ROW - the insert did not take effect')
    U.dump(out, lines[0], lines[1:])
    log('add done, new row=%s -> %s' % (
        [l for l in lines if l.startswith('# new row')], out))
    return 0


CMDS = dict(nav=cmd_nav, read=cmd_read, dump=cmd_dump, close=cmd_close,
            set=cmd_set, apply=cmd_apply, probe=cmd_probe, add=cmd_add,
            rename=cmd_rename)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        log(__doc__)
        return 2
    if not U.is_admin():
        log('WARN: not elevated')
    return CMDS[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    sys.exit(main())
