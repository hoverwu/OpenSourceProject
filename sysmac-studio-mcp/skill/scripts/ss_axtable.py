# -*- coding: utf-8 -*-
"""ss_axtable.py - 用真 Win32 组合框读写"轴设置表"的格子（UIA 对它全盲）。

作者：hoverwu ｜ 版本：0.1.0 ｜ 本版更新：2026-11-07

为什么要这个脚本：轴设置表是 WindowsFormsHost 里的 WinForms 网格，UIA 到
`PaneControl|WindowsForms10.Window.8.app...`（AutomationId=AxisGrid）就断了，一个单元
格都看不到（control-tree §17.1）。但**真点一格会浮出一个货真价
实的 Win32 编辑控件** `WindowsForms10.COMBOBOX.app.*`，于是 `CB_*` 消息就是这条通道：

  CB_GETCOUNT / CB_GETLBTEXT —— 列出所有 EtherCAT 从站（轴页顶上那个"输出设备1"
      下拉是**只显不写**的，见 pitfalls §59；这张表的组合框才是真句柄）
  CB_GETCURSEL —— 读回来的就是模型真值
  写：关闭态、有焦点的组合框上按 `{UP}`/`{DOWN}` —— 它会发 `CBN_SELCHANGE`，
      DataGridView 听得见；**`CB_SETCURSEL` 绝不使用**，它只改标题不发通知（§17.1.3）

坐标是 125% 缩放、1920×1080、主窗口最大化下的实测基线（`geom` 子命令可重新测量）；
**换分辨率/换缩放必须重新量**，不要照着缩放过的截图估，量完用环境变量覆盖（见下）。

用法（pid 可写进程号或名字片段）：

  python ss_axtable.py get   <pid> <out.txt> <列> <行>
  python ss_axtable.py set   <pid> <out.txt> <列> <行> <要选中的子串>
  python ss_axtable.py probe <pid> <out.txt> [列] [行]     列出所有可见 COMBOBOX/EDIT
  python ss_axtable.py geom  <png> [y0 y1]                 像素找列/行分隔线

  列 = 轴0 轴1 轴2 轴3 轴4 轴5（=值列，中心 x 见 COL；键名只是通用示例）
  行 = axis task use type fb in1 in1ch in2 in2ch in3 in3ch
       out1 out1ch out2 out2ch out3 out3ch（=ROW 里的行序，out1 在 y=523）

COL 的**键名是列头名**（每个轴一列），换工程就换键名；x 中心是"值列宽
150px 等距排列"量出来的基线。键名与几何都用环境变量覆盖，不必改代码：
  SS_AXTABLE_COLS   形如 "轴0=533,轴1=683,..."（键=列头名，值=中心 x；整体替换 COL）
  SS_AXTABLE_Y0     首数据行 top（默认 236）
  SS_AXTABLE_PITCH  行距（默认 25）
别的工程先 `probe`/`geom` 对齐再设环境变量。行序 ROW 是轴设置表本身的固定顺序，跨工程通用。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ctypes                                                             # noqa: E402
import ctypes.wintypes as wt                                              # noqa: E402
from ctypes import create_unicode_buffer                                  # noqa: E402
import ss_uimap as U                                                      # noqa: E402
import ss_axis as A                                                       # noqa: E402

u = U.u
# uiautomation 改过 SendMessageW 的原型，不手动复位就会把 hwnd 当整数截断（§17.1.4）
u.SendMessageW.restype = ctypes.c_ssize_t
u.SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]

CB_GETCOUNT, CB_GETCURSEL = 0x0146, 0x0147
CB_GETLBTEXTLEN, CB_GETLBTEXT = 0x0149, 0x0148
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK_UP, VK_DOWN = 0x26, 0x28

TAB = '轴设置表'
# 列中心 x / 首行 Y0 / 行距 PITCH 都是 125% 缩放、主窗口最大化下的实测基线；
# 换 DPI/分辨率用 geom 子命令重新测量，再用环境变量覆盖（见文件头），不要改代码。
# 键名只是通用示例（每个轴一列），换工程用 SS_AXTABLE_COLS 整体替换。
COL = {'轴0': 533, '轴1': 683, '轴2': 833, '轴3': 983, '轴4': 1133, '轴5': 1283}
_cols_env = os.environ.get('SS_AXTABLE_COLS', '')
if _cols_env:
    COL = {}
    for _part in _cols_env.split(','):
        if '=' in _part:
            _k, _v = _part.split('=', 1)
            COL[_k.strip()] = int(_v)
ROW = {'axis': 0, 'task': 1, 'use': 2, 'type': 3, 'fb': 4,
       'in1': 5, 'in1ch': 6, 'in2': 7, 'in2ch': 8, 'in3': 9, 'in3ch': 10,
       'out1': 11, 'out1ch': 12, 'out2': 13, 'out2ch': 14, 'out3': 15, 'out3ch': 16}
Y0 = int(os.environ.get('SS_AXTABLE_Y0', '236'))      # 首数据行 top（geom 可重量）
PITCH = int(os.environ.get('SS_AXTABLE_PITCH', '25'))  # 行距（geom 可重量）


def cell_xy(colname, rowname):
    return COL[colname], Y0 + PITCH * ROW[rowname] + PITCH // 2


def sm(h, m, wp=0, lp=0):
    return u.SendMessageW(h, m, wp, lp)


def items(h):
    n = sm(h, CB_GETCOUNT)
    out = []
    if not isinstance(n, int) or n <= 0 or n > 400:
        return out
    for i in range(n):
        ln = sm(h, CB_GETLBTEXTLEN, i)
        b = create_unicode_buffer(int(ln) + 1)
        sm(h, CB_GETLBTEXT, i, ctypes.cast(b, ctypes.c_void_p))
        out.append(b.value)
    return out


def cur_text(h):
    lst = items(h)
    c = sm(h, CB_GETCURSEL)
    return lst, c, (lst[c] if isinstance(c, int) and 0 <= c < len(lst) else '?')


def child_hwnds(mw_hwnd, want=('COMBOBOX', 'EDIT')):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cbf(h, l):
        buf = create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        cls = buf.value
        hot = any(w in cls.upper() for w in want)
        r = wt.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        vis = bool(u.IsWindowVisible(h))
        if hot or vis:
            found.append((h, cls, (r.left, r.top, r.right, r.bottom), vis))
        return True

    u.EnumChildWindows(wt.HWND(mw_hwnd), cbf, 0)
    return found


def open_cell(pid, mw, colname, rowname, lines):
    """把某格打开成编辑态并返回 (hwnd, rect)；打不开就写清楚原因。"""
    A.raise_tab(mw['hwnd'], TAB)
    time.sleep(1.0)
    x, y = cell_xy(colname, rowname)
    U.left_click(x, y)
    time.sleep(1.2)
    hs = [f for f in child_hwnds(mw['hwnd'], ('COMBOBOX',))
          if f[2][2] > 0 and f[3]]
    lines.append('## cell=(%d,%d) 可见 COMBOBOX=%d' % (x, y, len(hs)))
    for h, cls, rect, vis in hs:
        lines.append('   hwnd=%s class=%r rect=%s' % (h, cls, rect))
    if not hs:
        lines.append('NO EDITING COMBO - 格子不可编辑、或坐标/分辨率不对（跑 geom 重量）')
        return None
    return hs[0]


def cmd_get(argv):
    pid = U.resolve_pid(argv[0])
    out, colname, rowname = argv[1], argv[2], argv[3]
    lines = ['# ss_axtable get pid=%d %s/%s' % (pid, colname, rowname)]
    mw = U.main_window(pid)
    h = open_cell(pid, mw, colname, rowname, lines)
    rc = 3
    if h:
        lst, c, t = cur_text(h[0])
        lines.append('count=%d cursel=%s cur=%r' % (len(lst), c, t))
        lines.append('items=%r' % (lst,))
        print('%s/%s cursel=%s cur=%r -> %s' % (colname, rowname, c, t, out))
        rc = 0
    else:
        print('no editing combo -> %s' % out)
    U.dump(out, lines[0], lines[1:])
    return rc


def cmd_set(argv):
    pid = U.resolve_pid(argv[0])
    out, colname, rowname, want = argv[1], argv[2], argv[3], argv[4]
    lines = ['# ss_axtable set pid=%d %s/%s want=%r' % (pid, colname, rowname, want)]
    log = lines.append
    mw = U.main_window(pid)
    h = open_cell(pid, mw, colname, rowname, lines)
    if not h:
        U.dump(out, lines[0], lines[1:])
        print('no combo -> %s' % out)
        return 3
    hh = h[0]
    lst, cur, cur_t = cur_text(hh)
    log('combo hwnd=%s rect=%s count=%s cursel=%s cur=%r' % (hh, h[2], len(lst), cur, cur_t))
    tgt = [i for i, t in enumerate(lst) if want in t]
    log('targets for %r -> %s' % (want, [(i, lst[i]) for i in tgt]))
    if not tgt:
        log('要选的东西不在这个列表里 - 什么都没改')
        U.esc(1)
        U.dump(out, lines[0], lines[1:])
        return 4
    ti = tgt[0]
    if ti == cur:
        log('已经是目标值 - 不发按键（幂等）')
    else:
        step = -1 if ti < cur else 1
        tok = '{UP}' if step < 0 else '{DOWN}'
        vk = VK_UP if step < 0 else VK_DOWN
        import uiautomation as auto
        for k in range(abs(ti - cur)):
            auto.SendKeys(tok)
            time.sleep(0.12)
        mid = sm(hh, CB_GETCURSEL)
        log('键入 %d 次 %s 后 cursel=%s -> %r' % (abs(ti - cur), tok, mid,
                                                  lst[mid] if 0 <= mid < len(lst) else '?'))
        if mid == cur:
            log('前台按键没动（焦点丢了？），改用 PostMessage WM_KEYDOWN 兜底')
            for k in range(abs(ti - cur)):
                sm(hh, WM_KEYDOWN, vk, 0)
                sm(hh, WM_KEYUP, vk, 0)
                time.sleep(0.12)
            mid = sm(hh, CB_GETCURSEL)
            log('投递按键后 cursel=%s -> %r' % (mid, lst[mid] if 0 <= mid < len(lst) else '?'))
        U.left_click((h[2][0] + h[2][2]) // 2, (h[2][1] + h[2][3]) // 2)
        time.sleep(0.3)
        auto.SendKeys('{ENTER}')
        time.sleep(0.6)
    x, y = cell_xy(colname, rowname)
    U.left_click(x, y - PITCH)                       # 离开格子，让提交落地
    time.sleep(0.8)
    hs2 = [f for f in child_hwnds(mw['hwnd'], ('COMBOBOX',)) if f[2][2] > 0 and f[3]]
    log('离开后重开格子读到 %d 个组合框' % len(hs2))
    if hs2:
        _l2, c2, t2 = cur_text(hs2[0][0])
        log('re-open cursel=%s -> %r' % (c2, t2))
        log('#### %s' % ('OK 值已落进模型' if t2 and want in t2 else 'STILL WRONG'))
    U.dump(out, lines[0], lines[1:])
    print('-> %s' % out)
    return 0


def cmd_probe(argv):
    pid = U.resolve_pid(argv[0])
    out = argv[1]
    col = argv[2] if len(argv) > 2 else None
    row = argv[3] if len(argv) > 3 else None
    lines = ['# ss_axtable probe pid=%d' % pid]
    log = lines.append
    mw = U.main_window(pid)
    A.raise_tab(mw['hwnd'], TAB)
    time.sleep(1.0)
    if col and row:
        open_cell(pid, mw, col, row, lines)
    found = child_hwnds(mw['hwnd'])
    log('## %d 个可见/可疑子 HWND' % len(found))
    for h, cls, rect, vis in found:
        extra = ''
        if 'COMBOBOX' in cls.upper():
            lst, c, t = cur_text(h)
            extra = ' count=%d cursel=%s cur=%r' % (len(lst), c, t)
            if 0 < len(lst) <= 80:
                extra += '\n      ' + '\n      '.join(repr(x) for x in lst)
        log('hwnd=%s vis=%s class=%-42r rect=%s%s' % (h, vis, cls, rect, extra))
    U.dump(out, lines[0], lines[1:])
    print('%d child hwnds -> %s' % (len(found), out))
    return 0


def vlines(im, x0, x1, y0, y1, thresh=110):
    """列分隔线：竖直条带比左右邻居都暗的 x。"""
    px = im.load()
    ys = list(range(y0, y1, 3))
    out = []
    for x in range(x0, x1):
        v = sum(px[x, y] for y in ys) / len(ys)
        if v > thresh:
            continue
        l = sum(px[x - 2, y] for y in ys) / len(ys)
        r = sum(px[x + 2, y] for y in ys) / len(ys)
        if l > thresh + 20 and r > thresh + 20:
            out.append(x)
    return out


def hlines(im, x0, x1, y0, y1, thresh=110):
    px = im.load()
    xs = list(range(x0, x1, 3))
    out = []
    for y in range(y0, y1):
        v = sum(px[x, y] for x in xs) / len(xs)
        if v > thresh:
            continue
        up = sum(px[x, y - 2] for x in xs) / len(xs)
        dn = sum(px[x, y + 2] for x in xs) / len(xs)
        if up > thresh + 20 and dn > thresh + 20:
            out.append(y)
    return out


def cmd_geom(argv):
    from PIL import Image
    path = argv[0]
    y0 = int(argv[1]) if len(argv) > 2 else 200
    y1 = int(argv[2]) if len(argv) > 3 else 760
    im = Image.open(path).convert('L')
    print('size', im.size)
    print('V', vlines(im, 250, 1400, y0, y1))
    print('H', hlines(im, 700, 1300, y0, y1))
    return 0


CMDS = dict(get=cmd_get, set=cmd_set, probe=cmd_probe, geom=cmd_geom)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        return 2
    return CMDS[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    sys.exit(main())
