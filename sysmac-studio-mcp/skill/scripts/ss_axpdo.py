# -*- coding: utf-8 -*-
"""ss_axpdo.py - 驱动轴页 `轴基本设置 > 详细设置` 里的 PDO 映射网格（WPF DataGrid）。

作者：hoverwu ｜ 版本：0.6.0 ｜ 会改工程，跑前确认目标实例与轴

网格形状（实测 control-tree §17.2）：`MultiPDOTableFieldView` 下的 `DataGrid id='list'`，
列 = `功能名称 / 设备 / 过程数据`；三个组行 `输出(控制器到设备)`、`输入(设备到控制器)`、
`数字输入` 各带一个 `Button id='toggleUnit'`（`'+'`=折叠）。**组折叠时子行不在 UIA 树里**，
所以任何"读/写具体功能行"的动作都必须先 expand。

  python ss_axpdo.py collect  <pid|auto> <out> <轴树路径>    **只读**，不动折叠态；
        给 ss_axisplan.py 喂转储就用这条（expand 会把三组留在展开态）
  python ss_axpdo.py expand   <pid|auto> <out> <轴树路径>    展开三组 + 逐行读回
        **注意 1**：展开后**立刻**读行会把有值的单元格读成空（视图还没实化完；实测
        截图上是 `6040h-00.0(Controlword)`、日志里是 `""`）⇒ "读回为空"不等于"没写进去"，
        最终以 `ss_axcmp.py` 的归档为准。
        **注意 2**：`expand` 走完不会把三组折回去；但折回去也**改不动**
        `NexAxisPDOMappingTable`（见下面那段实测结论），纯为"别留展开态"而 `fold` 没有收益。
        要做"只读且不碰视图"的事一律用 `collect`。
  python ss_axpdo.py apply    <pid|auto> <out> <轴树路径> <plan.json>
  python ss_axpdo.py toggles  <pid|auto> <out> <轴树路径>    **只读**，报三组的状态：
        `glyph`（`'+'`=折叠 / `'-'`=展开）、`toggle_texts`（`+`/`-` 两个 Text 各自的
        `IsOffscreen`）、`ToggleState`。判"这组到底什么态"以它为准（第一遍读值会说谎）。
  python ss_axpdo.py peek     <pid|auto> <out> <轴树路径>    **只读**，把三个组行的整棵
        子树打出来（含 `PAT=` 列表）；换版本后先跑它确认 `toggleUnit` 还是不是 Button。

`collect` 故意不点任何 toggle：源工程的组可能"已经展开但 toggleUnit 还显示 `+`"，点它就
把参考页折上了。`apply` 的 plan 由 `ss_axisplan.py` 生成，每行
`{label, device, pdkey}`；`device` 走 `ss_axis.set_combo`（**当前值已对就跳过**——重设设备
会清掉该轴所有 PDO 映射，pitfalls §61），`pdkey` 走 `pick_prefix()`。

`pick_prefix()` 是本轮真正的技术含量（§62/§64）：
1. `SelectionItemPattern` 在这些行上是 `None`、`ScrollItemPattern` 在包装上直接
   `AttributeError` ⇒ UIA 的 Select/ScrollIntoView 两条正规路都不存在；
2. 下拉**打开时定位到当前选中项**（未分配=列表底部）⇒ 扫描必须**先向上再向下**；
3. 滚轮点必须落在**弹层自己的矩形中心**，落在"组合框+偏移"上会去滚网格；
4. 一次只实化约 60 项，其余 `IsOffscreen=True` 且矩形过期 ⇒ **绝不点 offscreen 行**；
5. 兜底：真点开下拉拿到焦点后**把键名敲进去**（WPF 文本检索跳到该项）再点/`Enter`。

匹配一律 `caption.startswith(key + '(')`，永不 substring：`'60FDh-00.1'` 是
`'60FDh-00.10'` 的子串，选错位是静默的错误。

写完还要**保存 + `ss_axcmp.py` 读归档**才算数：界面读回只说明"控件这么显示"。

**`fold`/`expand` 与 `NexAxisPDOMappingTable`（2026-11-07 实测，结论是"别追"）**：
`toggleUnit` 是 **Button**（`PAT=Toggle`），`'+'/'-'` 在它子节点 `Text id='toggleButton'` 上；
0.5.0 及更早按"AutomationId=='toggleUnit' 的 TextControl"找，**永远找不到**，于是
`expand_all/collapse_all` 走"找不到就当已经到位"的捷径 —— 日志写 `groups opened=[三组]`，
实际一次都没点（pitfalls §67.1）。0.6.0 起真点击，且判状态要**两次读一致**
（`stable_glyphs()`：刚 expand_groups/raise_tab 完的第一遍会把 `'+'` 读成 `'-'`）。
但即便真折叠/真展开、保存（sha 变了）、连该轴页签都关掉再保存，归档里
`NexAxisPDOMappingTable` **一字不变**：它是"该轴 PDO 单元格被界面提交过"的**只增不减**
历史标记，界面无清除通道（pitfalls §65.2）。⇒ 做"逐参数一模一样"时这一项属于
"如实报告"，不要为它反复点 toggle；只想看折叠态用 `toggles`（只读）。
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ctypes.wintypes as wt                                              # noqa: E402
import uiautomation as auto                                               # noqa: E402
import ss_uimap as U                                                      # noqa: E402
import ss_axis as A                                                       # noqa: E402

GROUPS = ('输出(控制器到设备)', '输入(设备到控制器)', '数字输入')


def page(pid_arg, path):
    """打开轴页并把**这根轴**放到前面，返回 (pid, mw, pane, doc名, root)。

    2026-11-07 实测：关掉一个页签以后，`cmd_open` 对"文档已经开着"的节点只做
    enter/双击、**不保证把那个页签切到前面**（`axis_open.txt`：
    `enter then dblclick did not open a document`），于是 `page_root()` 命中测试读到的是
    别的轴，PDO 表自然 `NO DATAGRID`。所以这里补 `raise_tab` + 轴号核对。
    """
    pid, mw, pane, name = A.open_axis(pid_arg, path)
    if name:
        A.raise_tab(mw['hwnd'], name)
        pane = U.find_doc(mw['hwnd'], name) or pane
    root = A.page_root(mw, pane, lambda m: None)
    A.goto_section(root, 'basic_setting')
    # PDO 表还藏在**第二层** Expander（`详细设置`，MultiPDOTableFieldView）后面：
    # 它折着的时候整张 DataGrid 都不在树里（实测 2026-11-07：关掉一个页签以后再开，
    # 详细设置回到折叠态，`grid_of` 直接 NO DATAGRID）。
    A.expand_groups(root)
    time.sleep(1.0)
    return pid, mw, pane, name, root


def axis_no_of(name):
    m = re.search(r'\((\d+),', name or '')
    return m.group(1) if m else ''


def grid_of(root):
    for g in U.find_by_type(root, ('DataGridControl',), maxd=30):
        if (U.prop(g, 'AutomationId') or '') in ('', 'list'):
            if [c for c in g.GetChildren() if c.ControlTypeName == 'DataItemControl']:
                return g
    return None


def row_info(row):
    """(label, toggle_ctrl, comboDevice, comboProcessData, rect, enabled).

    **2026-11-07 实测纠正**（`peek` 打出来的整棵子树）：折叠开关不是 Text，而是
    `Button id='toggleUnit'`（`PAT=Toggle`），它里面才套
    `Text id='toggleButton' Name='+'|'-'`。老代码按"AutomationId=='toggleUnit' 的
    **TextControl**"找，永远找不到 ⇒ `expand_all`/`collapse_all` 走的是
    "tg is None 就当已经到位"这条捷径，**一次都没点**，日志却报
    `groups opened/folded=[三组]`。这是"读起来对、归档不动"的典型假成功。
    """
    label, toggle, dev, pd = '', None, None, None
    for c in U.find_by_type(row, ('ButtonControl',), maxd=8):
        if (U.prop(c, 'AutomationId') or '') == 'toggleUnit':
            toggle = c
            break
    for c in U.find_by_type(row, ('TextControl',), maxd=8):
        t = (U.prop(c, 'Name') or '').strip()
        if (U.prop(c, 'AutomationId') or '') == 'toggleButton':
            if toggle is None:                       # 兜底：某些状态下只有 TextBlock
                toggle = c
        elif len(t) > 1 and t != '★':
            label = label or t
    for c in U.find_by_type(row, ('ComboBoxControl',), maxd=8):
        aid = U.prop(c, 'AutomationId') or ''
        if aid == 'comboDevice':
            dev = c
        elif aid == 'comboProcessData':
            pd = c
    br = U.prop(row, 'BoundingRectangle')
    rect = (br.left, br.top, br.right, br.bottom) if br else None
    return label, toggle, dev, pd, rect, bool(U.prop(row, 'IsEnabled'))


def grid_ready(root, log, tries=6):
    """等到 DataGrid 的 DataItem 行真的实化出来。

    实测 2026-11-07：`详细设置` 开着、`DataGrid id='list'` 也在树里（rect 765x82），
    但**刚重开的页**里它一个 `DataItemControl` 子节点都还没有，`grid_of()` 于是判
    "这页没有 PDO 表"。这是 pitfalls §57（折叠子树不实化）的第三种形态：容器在、行不在。
    滚一下 + 等一下就能实化。
    """
    for t in range(tries):
        g = grid_of(root)
        if g is not None:
            if t:
                log('grid 第 %d 次轮询才实化' % (t + 1))
            return g
        for d in U.find_by_type(root, ('DataGridControl',), maxd=30):
            if (U.prop(d, 'AutomationId') or '') in ('', 'list'):
                to_top(d)
                scroll(d, -1, 1)
                break
        time.sleep(1.5)
    return None


def toggle_texts(toggle):
    """toggleUnit 里所有 Name 是 '+'/'-' 的 Text，带 IsOffscreen。

    WPF 的模板经常把 `+` 和 `-` 两个 TextBlock 都留在树里、用 Visibility 切换，
    所以**必须挑没 offscreen 的那一个**；2026-11-07 实测：不挑的话 `glyph()` 会在
    明明折叠着（截图上是 `+`）的组上读出 `'-'`，`expand` 就"零点击成功"。
    """
    out = []
    if toggle is None:
        return out
    for c in U.find_by_type(toggle, ('TextControl',), maxd=4):
        t = (U.prop(c, 'Name') or '').strip()
        if t in ('+', '-'):
            out.append((bool(U.prop(c, 'IsOffscreen', False)), t))
    return out


def toggle_state(toggle):
    try:
        tp = toggle.GetTogglePattern()
    except Exception:
        return None
    if tp is None:
        return None
    try:
        return int(tp.ToggleState)          # 0=Off 1=On 2=Indeterminate
    except Exception:
        return None


def glyph(toggle):
    """'+' = 折叠着，'-' = 展开着；读不到返回 ''。"""
    if toggle is None:
        return ''
    if (U.prop(toggle, 'ControlTypeName') or '').startswith('Button'):
        txt = toggle_texts(toggle)
        for off, t in txt:
            if not off:
                return t
        if txt:
            return txt[0][1]
        st = toggle_state(toggle)
        return '' if st is None else {0: '+', 1: '-'}.get(st, '')
    return (U.prop(toggle, 'Name') or '').strip()


def grid_rows(g):
    return [c for c in g.GetChildren() if c.ControlTypeName == 'DataItemControl']


def to_top(g):
    try:
        sp = g.GetScrollPattern()
    except Exception:
        sp = None
    if sp is not None:
        try:
            sp.SetScrollPercent(0, 0)
            time.sleep(0.6)
            return True
        except Exception:
            pass
    return False


def scroll(g, dy, steps=1):
    br = U.prop(g, 'BoundingRectangle')
    cx, cy = (br.left + br.right) // 2, (br.top + br.bottom) // 2
    for _ in range(steps):
        U.wheel(dy, cx, cy)                       # NEGATIVE dy scrolls down
        time.sleep(0.45)


def click_toggle(tg):
    """切一组：先 TogglePattern（实测 toggleUnit 挂着它），不行再按矩形真点。"""
    try:
        tp = tg.GetTogglePattern()
        if tp is not None:
            tp.Toggle()
            time.sleep(0.9)
            return 'pattern'
    except Exception:
        pass
    br = U.prop(tg, 'BoundingRectangle')
    if not br or br.right <= 0:
        return 'no-rect'
    U.left_click((br.left + br.right) // 2, (br.top + br.bottom) // 2)
    time.sleep(0.9)
    return 'click'


def scan_glyphs(g):
    """label -> glyph，三组都扫到就停（组是上下叠的，视口小时要滚）。"""
    to_top(g)
    out = {}
    for _step in range(30):
        for row in grid_rows(g):
            label, tg, dev, pd, rect, en = row_info(row)
            if label in GROUPS and label not in out:
                out[label] = glyph(tg)
        if len(out) == len(GROUPS):
            break
        scroll(g, -2, 1)
    return out


def stable_glyphs(g, tries=4):
    """连读两次一致才算数。

    实测 2026-11-07（x_a4f/x_a4h）：刚 `expand_groups`/`raise_tab` 完的**第一次**扫描，
    三组会全读成 `'-'`，而 2 秒后和最终复查都是 `'+'`（截图也是 `+`）。按第一次读值判
    "已经是目标态"就会零点击"成功"。所以判状态一律要**两次一致**。
    """
    prev = scan_glyphs(g)
    for _ in range(tries):
        time.sleep(1.6)
        cur = scan_glyphs(g)
        if cur == prev and len(cur) == len(GROUPS):
            return cur
        prev = cur
    return prev


def find_group_row(g, label, log):
    for _step in range(30):
        for row in grid_rows(g):
            l, tg, dev, pd, rect, en = row_info(row)
            if l == label:
                return row
        scroll(g, -2, 1)
    return None


def set_groups(g, log, want, tag, max_rounds=4):
    """把三组都切到 want（'-'=展开 / '+'=折叠）；返回真正处于 want 的组名集合。

    判据 = `stable_glyphs()`（两次一致），点击后**再稳定复查一次**；
    读不到状态就记 UNKNOWN，绝不当作已到位。
    """
    cur = stable_glyphs(g)
    log('%s stable=%s want=%r' % (tag, cur, want))
    done = set(l for l, v in cur.items() if v == want)
    todo = [l for l in GROUPS if l in cur and cur[l] not in ('', want)]
    unknown = [l for l in GROUPS if cur.get(l, '') == '']
    for l in unknown:
        log('%s %s: glyph 读不到' % (tag, l))
    for r in range(max_rounds):
        if not todo:
            break
        label = todo.pop(0)
        row = find_group_row(g, label, log)
        if row is None:
            log('%s round %d: %s 行没实化' % (tag, r, label))
            continue
        _l, tg, _d, _p, _rect, _en = row_info(row)
        how = click_toggle(tg) if tg is not None else 'no-ctrl'
        after = stable_glyphs(g).get(label, '')
        log('%s round %d: %s %s -> %r' % (tag, r, label, how, after))
        if after == want:
            done.add(label)
        elif r + 1 < max_rounds:
            todo.append(label)
    log('%s reached=%s' % (tag, sorted(done)))
    return done


def expand_all(g, log, max_rounds=4):
    """open the three folded PDO groups; they are stacked, so scroll while looking."""
    return set_groups(g, log, '-', 'expand', max_rounds)


def collapse_all(g, log):
    """fold the three groups again - `NexAxisPDOMappingTable` records this state (§65.2)."""
    return set_groups(g, log, '+', 'fold')


def collect(g, log):
    """every realised row, top to bottom, as (label, device_text, pdata_text, enabled)."""
    to_top(g)
    out, seen, idle = [], set(), 0
    for _step in range(40):
        new = 0
        for row in grid_rows(g):
            label, tg, dev, pd, rect, en = row_info(row)
            if not label or label in seen:
                continue
            seen.add(label)
            out.append((label, A.combo_selection(dev), A.combo_selection(pd), en))
            new += 1
        if new == 0:
            idle += 1
            if idle >= 4:
                break
        else:
            idle = 0
        scroll(g, -2, 1)
    return out


def find_row(g, label, log):
    """scroll the virtualised grid until the row named LABEL is realised.

    Rows are looked up and written ONE AT A TIME: WPF row virtualisation recycles the
    DataGridRow elements while scrolling, so a control captured earlier is stale (§64).
    Going down first, then wrapping to the top, keeps the walk cheap when the plan is
    in grid order (which it is).
    """
    for dy, steps in ((0, 1), (-2, 30), (0, 1), (-2, 40)):
        if dy == 0 and steps == 1:
            to_top(g)
        for _ in range(1):
            for row in grid_rows(g):
                if row_info(row)[0] == label:
                    return row
            if dy:
                scroll(g, dy, 1)
    return None


def popup_win(pid):
    """((left, top, w, h), (cx, cy)) of the open drop-down, or (None, None).

    The wheel has to be sent over the POPUP, not over "combo centre + offset": the list
    can open upward, or the row can sit low enough that the offset point falls outside
    it, and then the wheel scrolls the grid behind instead and the list never moves.
    """
    best = None
    for w in U.popup_roots(pid):
        r = w['rect']                              # (left, top, width, height)
        if r[2] < 60 or r[3] < 40:
            continue                               # tooltips and 1px helper windows
        if best is None or r[2] * r[3] > best[2] * best[3]:
            best = r
    if best is None:
        return None, None
    return best, (best[0] + best[2] // 2, best[1] + best[3] // 2)


def pick_prefix(pid, ctrl, key, log):
    """Open the 过程数据 drop-down and pick the caption that starts with KEY+'('.

    One entry per BIT: '60FDh-00.1(Transmit PDO mapping 1_Digital inputs_60FD_00)',
    257 of them for one servo drive, ordered by PDO group then bit.  Match with
    caption.startswith(key + '(') - never substring ('60FDh-00.1' in '60FDh-00.10').
    See the module docstring for the five measured constraints this obeys.
    """
    U.esc(1)
    time.sleep(0.5)
    r = U.prop(ctrl, 'BoundingRectangle')
    if not r or r.right <= 0:
        return 'no-rect'
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    centre = None
    for how in ('click', 'expand'):
        if how == 'click':
            U.left_click(cx, cy)
        else:
            try:
                ctrl.GetExpandCollapsePattern().Expand()
            except Exception:
                continue
        time.sleep(1.2)
        _pr, centre = popup_win(pid)
        if centre:
            break
    if not centre:
        return 'NO-POPUP %r' % key

    def take(x, why):
        b = x[2]
        U.left_click((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
        time.sleep(0.9)
        return 'clicked %s (%s)' % (x[0], why)

    for dy, n in ((2, 30), (-2, 90)):           # up first: it opens at the tail
        last, stuck = None, 0
        for _ in range(n):
            lst = A.popup_list(pid)
            hit = [x for x in lst if x[0].startswith(key + '(')]
            vis = [x for x in hit if not x[3]]
            if vis:
                return take(vis[0], 'wheel %s' % ('up' if dy > 0 else 'down'))
            sig = ((lst[0][0] if lst else ''), (lst[-1][0] if lst else ''))
            stuck = stuck + 1 if sig == last else 0
            last = sig
            if stuck >= 3:
                break                            # this wheel is not moving the list
            U.wheel(dy, centre[0], centre[1])
            time.sleep(0.45)
    # keyboard fallback - WPF text search jumps the highlight to the caption
    U.esc(1)
    time.sleep(0.4)
    U.left_click(cx, cy)
    time.sleep(1.1)
    if not popup_win(pid)[1]:
        U.esc(1)
        return 'NO-POPUP2 %r' % key
    try:
        auto.SendKeys(key, waitTime=0.06)
    except Exception as ex:
        U.esc(1)
        return 'sendkeys!%s' % ex.__class__.__name__
    time.sleep(0.8)
    lst = A.popup_list(pid)
    hit = [x for x in lst if x[0].startswith(key + '(')]
    vis = [x for x in hit if not x[3]]
    if vis:
        return take(vis[0], 'typed')
    auto.SendKeys('{ENTER}')
    time.sleep(0.8)
    U.esc(1)
    return 'typed+enter (hits=%d vis=%d)' % (len(hit), len(vis))


def main():
    cmd, pid_arg, out_path, path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    pid, mw, pane, name, root = page(pid_arg, path)
    lines = ['# ss_axpdo %s pid=%s doc=%r path=%s' % (cmd, pid, name, path)]
    log = lines.append
    want = axis_no_of(name)
    if want:
        got = A.verify_axis(root, want)
        log('轴号 在前面的页=%r 期望=%r' % (got, want))
        if got != want:
            log('#### 停手：当前在前的不是这根轴（写错轴是静默的破坏）')
            U.dump(out_path, lines[0], lines[1:])
            print('wrong axis in front -> %s' % out_path)
            return 4
    g = grid_ready(root, log)
    if g is None:
        for d in U.find_by_type(root, ('DataGridControl', 'TableControl', 'ListControl',
                                       'CustomControl'), maxd=30)[:60]:
            if d.ControlTypeName == 'CustomControl' and (U.prop(d, 'ClassName') or '') \
                    not in ('MultiPDOTableFieldView',):
                continue
            log('  CAND %s' % U.line_of(d, True))
        for c in U.find_by_type(root, ('ButtonControl',), maxd=30):
            if (U.prop(c, 'Name') or '') == '恢复默认值':
                log('  恢复默认值 在 =%s（说明详细设置是开着的）' % U.line_of(c))
    if g is None:
        log('NO DATAGRID on this page - 这页没有 PDO 表（未绑设备的轴 / 节没切对）')
        U.dump(out_path, lines[0], lines[1:])
        print('no grid -> %s' % out_path)
        return 3
    log('grid rect=%s' % (U.prop(g, 'BoundingRectangle'),))
    if cmd == 'peek':           # 只读：把三组所在行的整棵子树打出来（找 toggleUnit 用）
        for row in grid_rows(g):
            label, tg, dev, pd, rect, en = row_info(row)
            if label not in GROUPS:
                continue
            log('== ROW %r toggle=%s' % (label, 'found' if tg is not None else 'NONE'))
            U.walk(row, 1, {'max_lines': 400, 'all': True, 'depth': 8, 'pat': True}, lines)
        U.dump(out_path, lines[0], lines[1:])
        print('peek -> %s' % out_path)
        return 0
    if cmd == 'toggles':        # 只读：三组的 toggleUnit 字符（'+'=折叠，'-'=展开）
        seen = {}
        for _step in range(30):
            rows = grid_rows(g)
            for i, row in enumerate(rows):
                label, tg, dev, pd, rect, en = row_info(row)
                if label not in GROUPS or label in seen:
                    continue
                kids = 0
                for r2 in rows[i + 1:]:
                    l2, t2, d2, p2, _r, _e = row_info(r2)
                    if glyph(t2) in ('+', '-'):
                        break
                    if d2 is not None or p2 is not None:
                        kids += 1
                    else:
                        break
                seen[label] = (glyph(tg), kids, toggle_texts(tg), toggle_state(tg))
            if len(seen) == len(GROUPS):
                break
            scroll(g, -3, 1)
        for label in GROUPS:
            log('TOGGLE %-22s %s' % (label, seen.get(label, 'NOT-SEEN')))
        U.dump(out_path, lines[0], lines[1:])
        print('toggles -> %s' % out_path)
        return 0
    if cmd == 'fold':                            # §65.2 - do NOT expand first
        log('groups folded=%s' % sorted(collapse_all(g, log)))
        U.dump(out_path, lines[0], lines[1:])
        print('fold done -> %s' % out_path)
        return 0
    if cmd == 'collect':
        rows = collect(g, log)                  # does NOT touch any toggle
    else:
        opened = expand_all(g, log)
        log('groups opened=%s' % sorted(opened))
        rows = collect(g, log) if cmd in ('expand', 'rows') else []
    if cmd in ('expand', 'rows', 'collect'):
        for label, dv, pd, en in rows:
            log('%s\t%s\t%s\t%s' % (label, en,
                                    json.dumps(dv, ensure_ascii=False),
                                    json.dumps(pd, ensure_ascii=False)))
        U.dump(out_path, lines[0], lines[1:])
        print('%d rows -> %s' % (len(rows), out_path))
        return 0
    if cmd == 'apply':
        plan = json.load(open(sys.argv[5], encoding='utf-8'))
        ok = miss = bad = 0
        for w in plan:
            label = w['label']
            row = find_row(g, label, log)
            if row is None:
                log('MISS  %-46s' % label)
                miss += 1
                continue
            _l, _t, dev, pd, _r, _e = row_info(row)
            good = True
            want_v = w.get('device')
            if want_v:
                cur = A.combo_selection(dev) if dev is not None else ''
                if cur == want_v:
                    log('dev    %-42s already' % label)
                else:
                    r = A.set_combo(dev, want_v) if dev is not None else 'no-ctrl'
                    log('dev    %-42s %r -> %s' % (label, want_v, r))
                    row = find_row(g, label, log) or row
                    _l, _t, dev, pd, _r, _e = row_info(row)
                    if A.combo_selection(dev) != want_v:
                        good = False
            key = w.get('pdkey')
            if key and good:
                row = find_row(g, label, log) or row
                _l, _t, dev, pd, _r, _e = row_info(row)
                r = pick_prefix(pid, pd, key, log) if pd is not None else 'no-ctrl'
                log('pd     %-42s %r -> %s' % (label, key, r))
                row = find_row(g, label, log) or row
                _l, _t, dev, pd, _r, _e = row_info(row)
                got = A.combo_selection(pd)
                log('       read-back %r' % (got,))
                if r.startswith('NO-') or r == 'no-ctrl' or not (got or '').startswith(key + '('):
                    good = False
            ok += 1 if good else 0
            bad += 0 if good else 1
        log('#### ok=%d bad=%d miss=%d of %d wanted' % (ok, bad, miss, len(plan)))
        U.dump(out_path, lines[0], lines[1:])
        print('ok=%d bad=%d miss=%d -> %s' % (ok, bad, miss, out_path))
        return 0 if not bad and not miss else 1
    log('unknown cmd')
    U.dump(out_path, lines[0], lines[1:])
    return 2


if __name__ == '__main__':
    sys.exit(main())
