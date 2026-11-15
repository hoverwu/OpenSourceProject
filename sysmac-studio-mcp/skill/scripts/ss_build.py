"""ss_build.py - compile and read the whole compile message list. Must run ELEVATED + DPI aware.

  ss_build.py totals <pid|auto>              panel header only: "N 错误 / M 警告"
  ss_build.py list   <pid|auto> <out.txt>    every row of the message grid, UTF-8, tab separated
  ss_build.py run    <pid|auto> [out.txt]    click 编译控制器(B), verify a FRESH build, then list

Why a separate file: the message list is a WPF DataGridControl that is NOT reachable by
"find by Name" - you have to grab the grid under the panel, scroll it with ScrollPattern,
and write UTF-8 (the console is GBK, Chinese comes out mojibake).

Column layout (实测 V1.68): 编号 | 说明 | 程序 | 位置

定位（0.12.0 起，不再用绝对 Y 常量）：
* 优先按 AutomationId='buildWindowsViewWindow' 锚定编译面板（control-tree §9），
  计数读面板内 HelpText='显示或隐藏错误/警告' 两个按钮的子 Text 数字;
* 面板 id 找不到时退回**相对主窗口**的下半部几何（窗口矩形现读，随位置/缩放自适应）。

run 的结束判据（缺一不可，否则判 INCONCLUSIVE 返回非 0，绝不判 PASS）：
1. 头部两个计数都读到；2. **明确观测到**进度条空闲（busy 必须是 False；读不到=None
   是"未知"，不能当空闲），且空闲后**重新采集**计数/网格新快照，连续两个有效稳定
   新快照才算结束——稳定**绝不复用缓存快照**（否则编译中读到的陈旧 (0,0) 会被当成
   稳定结果，稍后发布的错误数被漏读）；忙/未知一律重置稳定；
3. 有"本轮真的编译过"的证据：见过忙 / 计数变化 / 网格内容变化。
   计数/网格变化只在**前后两次都读得到**时才算数——"读不到→读得到"或面板
   首次出现只是变可见，不是编译证据（否则旧面板会被误当 fresh）。
   **没有证据前不累计稳定**，避免稍晚才开始的编译在头几次空闲被提前判稳定。
忙闲看状态栏 ProgressBar（按**控件类型**在 StatusBar 上下文里找，不是按 Name；
ss.find 是 Name/Aid 精确匹配，找不到无名的 ProgressBar），**不用 CPU 增长单独判
PASS**（CPU 涨只证明进程在干活，频繁 UIA 也抬 CPU）。busy 以短周期（POLL_S）采样
以抓住约 2~3s 的短编译；计时用 time.monotonic 真实墙钟 deadline（RUN_TIMEOUT_S），
ss.find 全树遍历的读成本计入超时。刚点完编译读到的可能是上一轮的陈旧计数——没有
证据时宁可报 INCONCLUSIVE（无法判定），也不把陈旧的 0 错当成本轮成功（offline-surgery §8.4）。

run 的退出码（与"是否编译过"分开判）：证据不足/读不到/未稳定 → INCONCLUSIVE 非 0；
确认本轮编译过后，**errors>0 一律非 0**（即使已导出列表），warnings 单独不判失败
（0 错 N 警告仍返回 0）；给了 out.txt 时列表照常导出，导出失败也非 0。

验证状态（0.12.0）：上述纯逻辑（计数解析 / 面板锚定 / 键盘兜底键名 / 新鲜度判定 /
退出码策略 / 新快照稳定 / 墙钟 deadline）由 tests/ 单测覆盖（注入假 UI 对象 + 假时钟，
不需要 Sysmac）;**面板锚定、真机计数读取、证据轮询、短周期 busy 采样、StatusBar/
ProgressBar 类型锚点这些 UI 行为尚未真机回归**（is_busy 锚点无可靠实测前可能恒为
None=未知，绝不伪称有效检测；需工程方提供状态条/编译按钮证据），见 extending.md
回归清单 15b/17c 与待验证清单。未经实测前不要把新锚定/采样周期当成跨版本/跨机器常量。
"""
import sys
import time
import ctypes
import ctypes.wintypes as wt
import uiautomation as auto

import ss

u = ctypes.windll.user32

PANEL_ID = 'buildWindowsViewWindow'
FILTER_GRID_ID = 'FilterResultList'
HEADER_BUTTONS = (('显示或隐藏错误', 'errors'), ('显示或隐藏警告', 'warnings'))
TEXT_TYPES = ('TextControl', 'ButtonControl', 'TabItemControl')

# run 轮询：busy 短周期采样以抓住 ~2-3s 短编译；**明确空闲后才重新采集计数/网格新
# 快照**，稳定只基于本轮新快照（不复用缓存，避免编译中读到的陈旧计数被当成稳定结果）。
# 计时用 time.monotonic 真实墙钟 deadline，ss.find 全树遍历的读成本计入超时。
# 这些周期是启发式默认值，尚未真机回归（见模块 docstring 验证状态）。
POLL_S = 0.5          # 每轮 sleep + 读一次 busy（生命周期采样）
RUN_TIMEOUT_S = 150   # 轮询墙钟上限（含读成本）
STATUSBAR_TYPE = 'StatusBarControl'
PROGRESS_TYPE = 'ProgressBarControl'


def main_hw(pid):
    hw = ss.main_hwnd(pid)
    if not hw:
        raise SystemExit('no main window for pid %s' % pid)
    return hw


def _walk(root, maxDepth=24):
    for d in auto.WalkControl(root, maxDepth=maxDepth):
        yield d[0] if isinstance(d, tuple) else d


def _text(c):
    try:
        return (c.Name or '') or (c.HelpText or '')
    except Exception:
        return ''


def find_panel(root):
    """The compile panel Pane (id=buildWindowsViewWindow), or None."""
    for c in _walk(root):
        try:
            if c.AutomationId == PANEL_ID:
                return c
        except Exception:
            pass
    return None


def parse_counts(pairs):
    """[(text, rect)] in reading order -> (errors, warnings); None for a missing one.

    The header renders as a digit Text immediately followed by '错误' / '警告'.
    """
    errs = warns = None
    for i in range(1, len(pairs)):
        t = pairs[i][0].strip()
        prev = pairs[i - 1][0].strip()
        if not prev.isdigit():
            continue
        if t == '错误' and errs is None:
            errs = int(prev)
        elif t == '警告' and warns is None:
            warns = int(prev)
    return errs, warns


def _first_digit_text(button):
    for c in _walk(button, maxDepth=4):
        try:
            if c.ControlTypeName == 'TextControl':
                t = (c.Name or '').strip()
                if t.isdigit():
                    return int(t)
        except Exception:
            pass
    return None


def panel_counts(panel):
    """Read both counts from the two header buttons inside the compile panel."""
    found = {}
    for c in _walk(panel):
        try:
            if c.ControlTypeName != 'ButtonControl':
                continue
            ht = c.HelpText or ''
            for label, key in HEADER_BUTTONS:
                if label in ht and key not in found:
                    n = _first_digit_text(c)
                    if n is not None:
                        found[key] = n
        except Exception:
            pass
    return found.get('errors'), found.get('warnings')


def header_pairs(panel):
    """Text/Button/TabItem (name, rect) inside the panel, sorted top-to-bottom."""
    out = []
    for c in _walk(panel):
        try:
            if c.ControlTypeName in TEXT_TYPES:
                t = _text(c)
                if t:
                    out.append((t, c.BoundingRectangle))
        except Exception:
            pass
    out.sort(key=lambda p: (p[1].top, p[1].left))
    return out


def texts_near(hw, top_lo, top_hi):
    """TextControl / ButtonControl names whose rect.top is inside a band."""
    out = []
    try:
        root = auto.ControlFromHandle(hw)
    except Exception:
        return out
    for c in _walk(root):
        try:
            r = c.BoundingRectangle
            if top_lo < r.top < top_hi and c.ControlTypeName in TEXT_TYPES:
                t = _text(c)
                if t:
                    out.append((t, r))
        except Exception:
            pass
    return out


def _hw_rect(hw):
    r = wt.RECT()
    try:
        if u.GetWindowRect(wt.HWND(hw), ctypes.byref(r)):
            return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        pass
    return None


def read_totals(pid):
    """(errors, warnings) from the compile panel; (None, None) when unreadable.

    Panel-id anchor first, then a window-relative geometry fallback. No absolute
    screen constants: the panel moves with the window / dock layout / DPI.
    """
    hw = main_hw(pid)
    try:
        root = auto.ControlFromHandle(hw)
    except Exception:
        return None, None
    panel = find_panel(root)
    if panel is not None:
        errs, warns = panel_counts(panel)
        if errs is not None and warns is not None:
            return errs, warns
        errs, warns = parse_counts(header_pairs(panel))
        if errs is not None and warns is not None:
            return errs, warns
    rect = _hw_rect(hw)
    if rect is not None:
        _l, t, _w, h = rect
        band = texts_near(hw, t + h * 0.55, t + h * 2)
        band.sort(key=lambda p: (p[1].top, p[1].left))
        errs, warns = parse_counts(band)
        if errs is not None and warns is not None:
            return errs, warns
    return None, None


def totals(pid):
    errs, warns = read_totals(pid)
    if errs is None or warns is None:
        print('header not found - is the 编译 panel visible?')
        return None
    print('errors=%d warnings=%d' % (errs, warns))
    return errs, warns


def _grid_in(panel):
    for c in _walk(panel):
        try:
            if c.ControlTypeName == 'DataGridControl' and \
                    (c.AutomationId or '') != FILTER_GRID_ID:
                r = c.BoundingRectangle
                if r.right > r.left and r.bottom > r.top:
                    return c
        except Exception:
            pass
    return None


def find_grid(hw):
    """The message DataGridControl: inside the compile panel, else bottom-of-window."""
    try:
        root = auto.ControlFromHandle(hw)
    except Exception:
        return None
    panel = find_panel(root)
    if panel is not None:
        g = _grid_in(panel)
        if g is not None:
            return g
    rect = _hw_rect(hw)
    if rect is None:
        return None
    _l, t, w, h = rect
    for c in _walk(root):
        try:
            if c.ControlTypeName != 'DataGridControl' or \
                    (c.AutomationId or '') == FILTER_GRID_ID:
                continue
            r = c.BoundingRectangle
            if r.top > t + h * 0.55 and (r.right - r.left) > w * 0.4:
                return c
        except Exception:
            pass
    return None


def read_grid(grid):
    seen = {}
    for ch in grid.GetChildren():
        vals = []
        for c in _walk(ch, maxDepth=4):
            try:
                if c.ControlTypeName == 'TextControl' and (c.Name or ''):
                    vals.append(c.Name)
            except Exception:
                pass
        if vals and vals[0].strip().isdigit():
            seen[int(vals[0])] = vals
    return seen


def collect(grid):
    seen = {}
    sp = None
    try:
        sp = grid.GetScrollPattern()
    except Exception:
        pass
    if sp is not None and sp.VerticallyScrollable:
        for i in range(0, 101, 5):
            try:
                sp.SetScrollPercent(-1, i)
            except Exception:
                pass
            time.sleep(0.35)
            seen.update(read_grid(grid))
        try:
            sp.SetScrollPercent(-1, 0)
        except Exception:
            pass
    else:
        try:
            grid.SetFocus()
        except Exception:
            pass
        time.sleep(0.2)
        # uiautomation SpecialKeyNames has PAGEDOWN, not PGDN: an unknown {name}
        # is treated as a literal Unicode char and ord() raises TypeError.
        auto.SendKeys('{Ctrl}{Home}', waitTime=0.15)
        time.sleep(0.3)
        for _ in range(80):
            before = len(seen)
            seen.update(read_grid(grid))
            auto.SendKeys('{PAGEDOWN}', waitTime=0.15)
            time.sleep(0.25)
            if len(seen) == before:
                break
    return seen


def grid_state(hw):
    """Fingerprint of the currently visible message rows; None when no grid."""
    g = find_grid(hw)
    if g is None:
        return None
    d = read_grid(g)
    return tuple(sorted((k, tuple(v)) for k, v in d.items()))


def find_progressbar(root):
    """The status-bar ProgressBar, found by CONTROL TYPE within the status bar.

    control-tree §10 (实测): StatusBar holds a Text + a ProgressBar, and the
    ProgressBar has no usable Name/AutomationId — so ss.find(pid,'ProgressBar')
    (exact Name/id match, ss.py:166) never hits it and is_busy would be stuck at
    None. Anchor on the StatusBar container TYPE, then the ProgressBar TYPE inside
    it. This anchor is NOT yet regression-tested on a real machine in `run`; when
    it is absent we return None (unknown) rather than pretend detection works.
    """
    for c in _walk(root):
        try:
            if c.ControlTypeName != STATUSBAR_TYPE:
                continue
        except Exception:
            continue
        for p in _walk(c, maxDepth=4):
            try:
                if p.ControlTypeName == PROGRESS_TYPE:
                    return p
            except Exception:
                pass
    return None


def is_busy(pid):
    """True/False from the status-bar ProgressBar; None when it cannot be read.

    Busy = ProgressBar on-screen (IsOffscreen False), idle = IsOffscreen True
    (control-tree §10). None means UNKNOWN (no status bar / progress bar found, or
    read failed) and must NEVER be treated as observed idle. The status-bar anchor
    is unverified on real hardware; engineering must supply status-bar/build-button
    evidence before this counts as a reliable lifecycle signal.
    """
    hw = main_hw(pid)
    try:
        root = auto.ControlFromHandle(hw)
    except Exception:
        return None
    pb = find_progressbar(root)
    if pb is None:
        return None
    try:
        return not bool(pb.IsOffscreen)
    except Exception:
        return None


def build_evidence(before, cur, busy_seen):
    """Pure: is there proof a build ran THIS round (not a stale panel read)?

    before/cur are (totals, grid_state) snapshots. Evidence is either an observed
    busy lifecycle, or a change between two VALID comparable reads. A snapshot
    going unreadable->readable (None totals, or a grid that first appears) is the
    panel becoming visible, NOT proof of a build, so it is deliberately ignored.
    """
    if busy_seen:
        return True
    bt, bg = before
    ct, cg = cur
    if bt[0] is not None and bt[1] is not None and ct[0] is not None and ct[1] is not None:
        if bt != ct:
            return True
    if bg is not None and cg is not None and bg != cg:
        return True
    return False


def find_build_button(root):
    for c in _walk(root, maxDepth=22):
        try:
            if c.ControlTypeName == 'ButtonControl' and '编译控制器' in (c.HelpText or ''):
                return c
        except Exception:
            pass
    return None


def do_list(pid, out_path):
    hw = main_hw(pid)
    grid = find_grid(hw)
    if grid is None:
        print('no message grid - compile first')
        return 1
    seen = collect(grid)
    lines = ['%03d\t%s' % (k, '\t'.join(seen[k][1:6])) for k in sorted(seen)]
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    print('rows=%d -> %s' % (len(seen), out_path))
    return 0


def do_run(pid, out_path=None):
    hw = main_hw(pid)
    ss.force_foreground(hw)
    time.sleep(0.5)
    root = auto.ControlFromHandle(hw)
    btn = find_build_button(root)
    if btn is None:
        print('编译控制器(B) button not found - toolbar hidden or wrong view?')
        return 1
    before = (read_totals(pid), grid_state(hw))
    r = btn.BoundingRectangle
    ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    print('build clicked')
    busy_seen = False
    prev_fresh = None
    stable = 0
    last = ((None, None), None)
    deadline = time.monotonic() + RUN_TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(POLL_S)
        busy = is_busy(pid)
        if busy is True:
            busy_seen = True
        # 忙/未知都重置稳定：只有**明确空闲**才采新快照累计稳定。
        if busy is not False:
            stable = 0
            prev_fresh = None
            continue
        # 明确空闲：重新采集**新**快照（绝不复用缓存）。稳定只能基于本轮新快照，
        # 否则编译中读到的陈旧 (0,0) 会被当成稳定结果，稍后发布的错误数被漏读。
        cur = (read_totals(pid), grid_state(hw))
        last = cur
        if cur[0][0] is None or cur[0][1] is None:
            stable = 0
            prev_fresh = None
            continue
        # 没有本轮编译证据前不累计稳定——避免稍晚才开始的编译在头几次空闲被提前判稳定。
        if not build_evidence(before, cur, busy_seen):
            stable = 0
            prev_fresh = None
            continue
        if prev_fresh is not None and cur == prev_fresh:
            stable += 1
        else:
            stable = 1
        prev_fresh = cur
        if stable >= 2:
            break
    (errs, warns), _g = last
    if errs is None or warns is None:
        print('INCONCLUSIVE: build result UNREADABLE (header not found) - '
              'compile start/end not observed, NOT a pass')
        return 1
    if stable < 2:
        print('INCONCLUSIVE: build did not settle before timeout - '
              'compile end not observed, NOT a pass')
        return 1
    if not build_evidence(before, last, busy_seen):
        print('INCONCLUSIVE: no evidence a build ran (counts/grid unchanged, '
              'never busy) - stale result NOT accepted')
        return 1
    print('build finished errors=%d warnings=%d (warnings alone do not fail)' % (errs, warns))
    rc = 0
    if out_path:
        # 列表照常导出，但导出结果不得吞掉编译判定。
        if do_list(pid, out_path) != 0:
            rc = 1
    if errs > 0:
        print('FAIL: compile reported %d error(s)' % errs)
        rc = 1
    return rc


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == 'totals':
        pid = ss.resolve_pid(sys.argv[2] if len(sys.argv) > 2 else 'auto')
        return 0 if totals(pid) is not None else 1
    if cmd == 'list':
        pid = ss.resolve_pid(sys.argv[2])
        return do_list(pid, sys.argv[3] if len(sys.argv) > 3 else 'build_all.txt')
    if cmd == 'run':
        pid = ss.resolve_pid(sys.argv[2])
        out = sys.argv[3] if len(sys.argv) > 3 else None
        return do_run(pid, out)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())