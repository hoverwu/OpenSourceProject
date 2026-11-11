"""ss_build.py - compile and read the whole compile message list. Must run ELEVATED + DPI aware.

  ss_build.py totals <pid|auto>              panel header only: "N 错误 / M 警告"
  ss_build.py list   <pid|auto> <out.txt>    every row of the message grid, UTF-8, tab separated
  ss_build.py run    <pid|auto> [out.txt]    click 编译控制器(B), poll until stable, then list

Why a separate file: the message list is a WPF DataGridControl that is NOT reachable by
"find by Name" - you have to grab the grid under the panel, scroll it with ScrollPattern,
and write UTF-8 (the console is GBK, Chinese comes out mojibake).

Column layout (实测 V1.68): 编号 | 说明 | 程序 | 位置
"""
import sys
import time
import ctypes
import uiautomation as auto

import ss

u = ctypes.windll.user32


def main_hw(pid):
    hw = ss.main_hwnd(pid)
    if not hw:
        raise SystemExit('no main window for pid %s' % pid)
    return hw


def texts_near(hw, top_lo, top_hi):
    """TextControl / ButtonControl names whose rect.top is inside a band."""
    out = []
    try:
        root = auto.ControlFromHandle(hw)
    except Exception:
        return out
    for d in auto.WalkControl(root, maxDepth=24):
        c = d[0] if isinstance(d, tuple) else d
        try:
            r = c.BoundingRectangle
            if top_lo < r.top < top_hi and c.ControlTypeName in (
                    'TextControl', 'ButtonControl', 'TabItemControl'):
                t = (c.Name or '') or (c.HelpText or '')
                if t:
                    out.append((t, r))
        except Exception:
            pass
    return out


def totals(pid):
    hw = main_hw(pid)
    band = texts_near(hw, 620, 690)
    errs = warns = None
    for i, (t, r) in enumerate(band):
        if t.strip() == '错误' and i > 0:
            prev = band[i - 1][0].strip()
            if prev.isdigit():
                errs = int(prev)
        if t.strip() == '警告' and i > 0:
            prev = band[i - 1][0].strip()
            if prev.isdigit():
                warns = int(prev)
    if errs is None:
        print('header not found - is the 编译 panel visible?')
        return None
    print('errors=%d warnings=%d' % (errs, warns))
    return errs, warns


def find_grid(hw):
    try:
        root = auto.ControlFromHandle(hw)
    except Exception:
        return None
    for d in auto.WalkControl(root, maxDepth=24):
        c = d[0] if isinstance(d, tuple) else d
        try:
            if c.ControlTypeName == 'DataGridControl' and c.BoundingRectangle.top > 630:
                return c
        except Exception:
            pass
    return None


def read_grid(grid):
    seen = {}
    for ch in grid.GetChildren():
        vals = []
        for d in auto.WalkControl(ch, maxDepth=4):
            c = d[0] if isinstance(d, tuple) else d
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
        auto.SendKeys('{Ctrl}{Home}', waitTime=0.15)
        time.sleep(0.3)
        for _ in range(80):
            before = len(seen)
            seen.update(read_grid(grid))
            auto.SendKeys('{PgDn}', waitTime=0.15)
            time.sleep(0.25)
            if len(seen) == before:
                break
    return seen


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
    btn = None
    for d in auto.WalkControl(root, maxDepth=22):
        c = d[0] if isinstance(d, tuple) else d
        try:
            if c.ControlTypeName == 'ButtonControl' and '编译控制器' in (c.HelpText or ''):
                btn = c
                break
        except Exception:
            pass
    if btn is None:
        print('编译控制器(B) button not found - toolbar hidden or wrong view?')
        return 1
    r = btn.BoundingRectangle
    ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    print('build clicked')
    prev = None
    stable = 0
    for _ in range(60):
        time.sleep(5)
        t = totals(pid)
        n = len(read_grid(find_grid(hw))) if find_grid(hw) else 0
        cur = (t, n)
        if cur == prev:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        prev = cur
    print('build finished')
    if out_path:
        return do_list(pid, out_path)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == 'totals':
        pid = ss.resolve_pid(sys.argv[2] if len(sys.argv) > 2 else 'auto')
        return 0 if totals(pid) else 1
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
