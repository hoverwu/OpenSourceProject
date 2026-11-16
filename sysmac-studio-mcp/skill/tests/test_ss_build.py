"""Unit tests for ss_build: panel anchoring, key names, fresh-build verdict.

All UI objects are fakes; no Sysmac Studio / uiautomation UI is touched.
"""
import io
import itertools
import unittest
from contextlib import redirect_stdout

import _stubs
from _stubs import Ctrl, FakeAuto, FakeTime

import ss_build as B

# Default fake so pure-tree helpers (find_panel / read_grid / ...) can walk
# without a real UIA; classes that need specific behaviour override in setUp.
B.auto = FakeAuto()


def header_button(help_text, digit, label, left):
    return Ctrl('ButtonControl', help=help_text, rect=(left, 1085, left + 79, 1105),
                children=[Ctrl('TextControl', name=str(digit), rect=(left + 26, 1085, left + 34, 1105)),
                          Ctrl('TextControl', name=label, rect=(left + 38, 1085, left + 79, 1105))])


def make_panel(errs=3, warns=7, grid=True):
    kids = [header_button('显示或隐藏错误', errs, '错误', 279),
            header_button('显示或隐藏警告', warns, '警告', 366)]
    if grid:
        kids.append(Ctrl('DataGridControl', rect=(275, 1108, 1663, 1276)))
        kids.append(Ctrl('DataGridControl', aid='FilterResultList', rect=(0, 0, 0, 0)))
    return Ctrl('PaneControl', aid='buildWindowsViewWindow', name='编译',
                rect=(317, 1276, 359, 1303), children=kids)


class ParseCounts(unittest.TestCase):
    def test_both(self):
        r = (0, 0, 1, 1)
        pairs = [('0', r), ('错误', r), ('0', r), ('警告', r)]
        self.assertEqual(B.parse_counts(pairs), (0, 0))

    def test_errors_only(self):
        r = (0, 0, 1, 1)
        self.assertEqual(B.parse_counts([('385', r), ('错误', r)]), (385, None))

    def test_empty(self):
        self.assertEqual(B.parse_counts([]), (None, None))

    def test_non_digit_prev_ignored(self):
        r = (0, 0, 1, 1)
        self.assertEqual(B.parse_counts([('x', r), ('错误', r)]), (None, None))


class PanelAnchor(unittest.TestCase):
    def test_find_panel(self):
        panel = make_panel()
        root = Ctrl('WindowControl', children=[Ctrl('PaneControl', children=[panel])])
        self.assertIs(B.find_panel(root), panel)

    def test_find_panel_absent(self):
        root = Ctrl('WindowControl', children=[Ctrl('PaneControl', aid='other')])
        self.assertIsNone(B.find_panel(root))

    def test_panel_counts(self):
        self.assertEqual(B.panel_counts(make_panel(3, 7)), (3, 7))

    def test_panel_counts_missing_warning(self):
        panel = make_panel()
        panel._children = panel._children[:1]
        self.assertEqual(B.panel_counts(panel), (3, None))

    def test_header_pairs_sorted(self):
        pairs = B.header_pairs(make_panel())
        tops = [(p[1].top, p[1].left) for p in pairs]
        self.assertEqual(tops, sorted(tops))


class FindGrid(unittest.TestCase):
    def setUp(self):
        self._auto, self._rect = B.auto, B._hw_rect
        B._hw_rect = lambda hw: (0, 0, 1920, 1080)

    def tearDown(self):
        B.auto, B._hw_rect = self._auto, self._rect

    def test_grid_inside_panel_not_filter(self):
        panel = make_panel()
        root = Ctrl('WindowControl', children=[panel])
        B.auto = FakeAuto(root)
        grid = B.find_grid(1)
        self.assertIsNotNone(grid)
        self.assertEqual(grid.AutomationId, '')
        self.assertGreater(grid.BoundingRectangle.right, grid.BoundingRectangle.left)

    def test_geometry_fallback_bottom_only(self):
        top_grid = Ctrl('DataGridControl', rect=(100, 100, 1500, 300))
        bottom_grid = Ctrl('DataGridControl', rect=(275, 900, 1663, 1050))
        root = Ctrl('WindowControl', children=[top_grid, bottom_grid])
        B.auto = FakeAuto(root)
        self.assertIs(B.find_grid(1), bottom_grid)

    def test_geometry_fallback_excludes_filter(self):
        filt = Ctrl('DataGridControl', aid='FilterResultList', rect=(275, 900, 1663, 1050))
        root = Ctrl('WindowControl', children=[filt])
        B.auto = FakeAuto(root)
        self.assertIsNone(B.find_grid(1))


class Collect(unittest.TestCase):
    def setUp(self):
        self._auto, self._time = B.auto, B.time
        B.auto = FakeAuto()
        B.time = FakeTime()

    def tearDown(self):
        B.auto, B.time = self._auto, self._time

    def test_keyboard_fallback_uses_pagedown(self):
        def no_pattern():
            raise RuntimeError('no scroll pattern')

        grid = Ctrl('DataGridControl')
        grid.GetScrollPattern = no_pattern
        grid.SetFocus = lambda: None
        grid.GetChildren = lambda: []
        B.collect(grid)
        self.assertIn('{PAGEDOWN}', B.auto.sent)
        self.assertIn('{Ctrl}{Home}', B.auto.sent)
        self.assertNotIn('{PgDn}', B.auto.sent)

    def test_scroll_pattern_path_no_sendkeys(self):
        calls = []

        class SP:
            VerticallyScrollable = True

            def SetScrollPercent(self, h, v):
                calls.append(v)

        grid = Ctrl('DataGridControl')
        grid.GetScrollPattern = lambda: SP()
        grid.GetChildren = lambda: []
        B.collect(grid)
        self.assertEqual(B.auto.sent, [])
        self.assertIn(0, calls)
        self.assertIn(100, calls)


class ReadGrid(unittest.TestCase):
    def test_rows_keyed_by_number(self):
        row = Ctrl('DataItemControl', children=[
            Ctrl('TextControl', name='1'), Ctrl('TextControl', name='说明'),
            Ctrl('TextControl', name='程序'), Ctrl('TextControl', name='位置')])
        grid = Ctrl('DataGridControl', children=[row])
        self.assertEqual(B.read_grid(grid), {1: ['1', '说明', '程序', '位置']})


class BuildEvidence(unittest.TestCase):
    def test_no_change_no_busy_is_not_evidence(self):
        snap = ((0, 0), ())
        self.assertFalse(B.build_evidence(snap, snap, False))

    def test_busy_is_evidence(self):
        snap = ((0, 0), ())
        self.assertTrue(B.build_evidence(snap, snap, True))

    def test_totals_change_is_evidence(self):
        self.assertTrue(B.build_evidence(((12, 0), ()), ((0, 0), ()), False))

    def test_grid_change_is_evidence(self):
        self.assertTrue(B.build_evidence(((0, 0), ()), ((0, 0), ((1, ('x',)),)), False))

    def test_unreadable_to_known_totals_not_evidence(self):
        # 面板从读不到变读得到只是变可见，不是本轮编译证据。
        self.assertFalse(B.build_evidence(((None, None), ()), ((0, 0), ()), False))

    def test_grid_first_appearance_not_evidence(self):
        self.assertFalse(B.build_evidence(((0, 0), None), ((0, 0), ()), False))

    def test_partial_totals_not_evidence(self):
        self.assertFalse(B.build_evidence(((0, None), ()), ((0, 0), ()), False))

    def test_valid_totals_change_still_evidence(self):
        self.assertTrue(B.build_evidence(((0, 0), ()), ((3, 0), ()), False))


class IsBusy(unittest.TestCase):
    """is_busy must find the ProgressBar by CONTROL TYPE inside the status bar,
    not by Name (ss.find exact Name/id match never hits the unnamed ProgressBar)."""

    def setUp(self):
        self._auto, self._hw = B.auto, B.main_hw
        B.main_hw = lambda pid: 1

    def tearDown(self):
        B.auto, B.main_hw = self._auto, self._hw

    def _root(self, pb):
        sb = Ctrl('StatusBarControl', children=[Ctrl('TextControl'), pb])
        return Ctrl('WindowControl', children=[Ctrl('PaneControl', children=[sb])])

    def test_busy_when_progress_on_screen(self):
        B.auto = FakeAuto(self._root(Ctrl('ProgressBarControl', offscreen=False)))
        self.assertIs(B.is_busy(1), True)

    def test_idle_when_progress_offscreen(self):
        B.auto = FakeAuto(self._root(Ctrl('ProgressBarControl', offscreen=True)))
        self.assertIs(B.is_busy(1), False)

    def test_no_statusbar_is_unknown(self):
        B.auto = FakeAuto(Ctrl('WindowControl', children=[Ctrl('PaneControl')]))
        self.assertIsNone(B.is_busy(1))

    def test_progress_outside_statusbar_not_used(self):
        # 状态栏外的 ProgressBar 不算数（限定正确上下文），找不到 → 未知。
        root = Ctrl('WindowControl', children=[Ctrl('ProgressBarControl', offscreen=False)])
        B.auto = FakeAuto(root)
        self.assertIsNone(B.is_busy(1))

    def test_unreadable_offscreen_is_unknown(self):
        pb = Ctrl('ProgressBarControl')
        del pb.IsOffscreen
        B.auto = FakeAuto(self._root(pb))
        self.assertIsNone(B.is_busy(1))


class DoRun(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(B, k) for k in
                       ('main_hw', 'auto', 'time', 'is_busy', 'read_totals', 'grid_state', 'do_list')}
        self._ss = (B.ss.force_foreground, B.ss.click_at)
        B.main_hw = lambda pid: 1
        B.ss.force_foreground = lambda hw: True
        B.ss.click_at = lambda *a: None
        B.do_list = lambda pid, out: 0
        B.time = FakeTime()
        btn = Ctrl('ButtonControl', help='编译控制器(B)', rect=(100, 50, 140, 80))
        B.auto = FakeAuto(Ctrl('WindowControl', children=[btn]))

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(B, k, v)
        B.ss.force_foreground, B.ss.click_at = self._ss

    def _seq(self, totals, grid, busy):
        B.read_totals = lambda pid: next(totals)
        B.grid_state = lambda hw: next(grid)
        B.is_busy = lambda pid: next(busy)

    def test_stale_zero_is_rejected(self):
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()), itertools.repeat(False))
        self.assertEqual(B.do_run(1), 1)

    def test_busy_seen_accepts(self):
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()),
                  itertools.chain([True], itertools.repeat(False)))
        self.assertEqual(B.do_run(1), 0)

    def test_totals_change_accepts(self):
        self._seq(itertools.chain([(12, 0)], itertools.repeat((0, 0))),
                  itertools.repeat(()), itertools.repeat(False))
        self.assertEqual(B.do_run(1), 0)

    def test_unreadable_rejected(self):
        self._seq(itertools.repeat((None, None)), itertools.repeat(()), itertools.repeat(False))
        self.assertEqual(B.do_run(1), 1)

    def test_never_settles_rejected(self):
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()),
                  itertools.cycle([True, False]))
        self.assertEqual(B.do_run(1), 1)

    def _run_capture(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = B.do_run(1)
        return rc, buf.getvalue()

    def test_stale_zero_labels_inconclusive(self):
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()), itertools.repeat(False))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('INCONCLUSIVE', out)
        self.assertNotIn('build finished', out)

    def test_unreadable_labels_inconclusive(self):
        self._seq(itertools.repeat((None, None)), itertools.repeat(()), itertools.repeat(False))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('INCONCLUSIVE', out)

    def test_success_has_no_inconclusive(self):
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()),
                  itertools.chain([True], itertools.repeat(False)))
        rc, out = self._run_capture()
        self.assertEqual(rc, 0)
        self.assertIn('build finished', out)
        self.assertNotIn('INCONCLUSIVE', out)

    def test_busy_unknown_not_idle(self):
        # busy 一直读不到(None)：不能当空闲，无法确认结束 → INCONCLUSIVE。
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()), itertools.repeat(None))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('INCONCLUSIVE', out)

    def test_unreadable_to_known_not_fresh(self):
        # 计数从读不到变读得到、从未见忙：不是本轮证据 → INCONCLUSIVE。
        self._seq(itertools.chain([(None, None)], itertools.repeat((0, 0))),
                  itertools.repeat(()), itertools.repeat(False))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('INCONCLUSIVE', out)

    def test_short_build_busy_pulse_accepted(self):
        # ~2-3s 短编译：busy 只在前几轮短采样里出现一次，也应被抓住。
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()),
                  itertools.chain([False, True], itertools.repeat(False)))
        self.assertEqual(B.do_run(1), 0)

    def test_errors_nonzero_without_list(self):
        self._seq(itertools.chain([(0, 0)], itertools.repeat((3, 0))),
                  itertools.repeat(()), itertools.repeat(False))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('build finished', out)
        self.assertNotIn('INCONCLUSIVE', out)

    def test_warnings_only_exit_zero(self):
        self._seq(itertools.chain([(0, 0)], itertools.repeat((0, 5))),
                  itertools.repeat(()), itertools.repeat(False))
        self.assertEqual(B.do_run(1), 0)

    def test_errors_nonzero_even_with_list(self):
        calls = []
        B.do_list = lambda pid, out: calls.append(out) or 0
        self._seq(itertools.chain([(0, 0)], itertools.repeat((2, 0))),
                  itertools.repeat(()), itertools.repeat(False))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = B.do_run(1, 'all.txt')
        self.assertEqual(rc, 1)
        self.assertEqual(calls, ['all.txt'])      # 列表照常导出
        self.assertIn('build finished', buf.getvalue())

    def test_list_failure_nonzero(self):
        B.do_list = lambda pid, out: 1
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()),
                  itertools.chain([True], itertools.repeat(False)))
        self.assertEqual(B.do_run(1, 'all.txt'), 1)

    def test_delayed_errors_not_masked_by_cache(self):
        # 主审 P1 复现：i=0 读到编译中的陈旧 (0,0)，busy 随即转 idle；错误数 (3,0)
        # 稍后才发布。稳定若复用缓存就会在读到 (3,0) 前判 0/0 成功。必须重读新快照。
        calls = []

        def totals(pid):
            calls.append(1)
            return next(seq)

        seq = iter([(0, 0), (0, 0), (3, 0)] + [(3, 0)] * 50)
        B.read_totals = totals
        B.grid_state = lambda hw: ()
        B.is_busy = lambda pid: next(busy)
        busy = itertools.chain([True], itertools.repeat(False))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('errors=3', out)
        self.assertGreaterEqual(len(calls), 3)   # 基线之外还重读了完成后的新快照

    def test_baseline_cache_cannot_mask_reread_error(self):
        # 旧缓存代码：i=0 读基线 (0,0)，i=1/2/3 复用缓存判 stable>=2 提前退出，
        # 第二次空闲本该重读到的 (3,0) 被漏掉 → 误判 0/0 成功。新代码每次空闲重读
        # 新快照，第二个新快照读到 (3,0) → 重置稳定，最终判 3 错非 0。
        seq = iter([(0, 0), (0, 0), (3, 0)] + [(3, 0)] * 50)
        self._seq(seq, itertools.repeat(()),
                  itertools.chain([True], itertools.repeat(False)))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('errors=3', out)

    def test_delayed_busy_start_not_missed(self):
        # 编译稍晚才开始：头几次空闲无证据不得提前 break，须等到 busy 出现。
        self._seq(itertools.repeat((0, 0)), itertools.repeat(()),
                  itertools.chain([False, False, False, True], itertools.repeat(False)))
        rc, out = self._run_capture()
        self.assertEqual(rc, 0)
        self.assertIn('build finished', out)

    def test_read_cost_exhausts_deadline(self):
        # ss.find 全树遍历耗时须计入墙钟 deadline：读成本把时间耗尽 → 未稳定 INCONCLUSIVE，
        # 而不是按循环次数无视读成本继续判成功。
        t = B.time

        def costly_totals(pid):
            t.sleep(200)        # 模拟一次昂贵全树读
            return (0, 0)

        B.read_totals = costly_totals
        B.grid_state = lambda hw: ()
        B.is_busy = lambda pid: next(busy)
        busy = itertools.chain([True], itertools.repeat(False))
        rc, out = self._run_capture()
        self.assertEqual(rc, 1)
        self.assertIn('INCONCLUSIVE', out)
        self.assertIn('did not settle', out)


if __name__ == '__main__':
    unittest.main()