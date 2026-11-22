# -*- coding: utf-8 -*-
"""ss_libref.py <pid> <out.txt> <open|select|delete|add|confirm|replace|warn|list|yes> [参数] —— 库索引 .slr 引用管理（含替换/强制重载）
作者：hoverwu ｜ 版本：0.3.0 ｜ 实测：Sysmac Studio V1.68 64bit / Win11 / 125% DPI

用途：给工程挂 / 换 .slr 库引用。两个核心场景：
  (a) 替换同名库：新旧 .slr 内部 Library id 不同但库名相同，追加会撞名 ⇒ 必须"先删旧行再 + 新行"。
  (b) 强制重载库缓存：编辑被引用的 .slr 磁盘文件后，Sysmac 编译时仍用内存里的旧库（错误一条不少），
      且库索引的刷新(↻)键恒灰、用不了 ⇒ 唯一可行的强制重读 = 删旧引用行 + 重加同一路径。见 pitfalls §79。
库索引里的改动只在点「确定」后才提交，中途「关闭」可整体放弃，故 select/delete/add 阶段是安全的、可回退的。

模式：
  open     工程(P) → 库(L) → 显示索引(S)。**默认纯 UIA 模式**（ExpandCollapse/Invoke，不动鼠标）；
           加 --mouse 才走旧的鼠标悬停路径（旧行为保留作回退）
  select   选中第 N 行（--row N，默认 1）使删除按钮点亮
  delete   点工具条删除（第二个按钮）
  add      + → 引用库文件 → 剪贴板粘贴完整 .slr 路径 → 校验后才 打开(O) → 消 引用库 警告
  confirm  点库索引「确定」提交
  replace  一步换库/重载：select(--row) → delete → 消警告 → add(slr) → warn → confirm（需传 slr 路径）
  warn     补消可能 >2s 才冒出来的「引用库」/「重命名」模态警告（add 紧跟的 dismiss 会扑空时用）
  yes      点掉「库已经被引用。库将被一个新的所替换…」这类**替换确认框**的 是(Y)（旧 replace 会漏它）
  list     离线：不给界面，直接读 .smc2 里 ReferredLibrary/LibraryModel，打印已引用库的
           名称/版本/LibraryId/路径/IsSource/IsDisableSourceDisplay。用法 `... list <工程.smc2>`

关键实测教训：
- 打开子菜单只能鼠标悬停 库(L)（WPF 悬停才展开二级）；SetCursorPos alone 不触发菜单
  modal loop，需 mouse_event ±1px nudge。键盘 L/S 会被中文 IME 吞进候选窗。
  ——2026-11-21 补充：**这条只适用于鼠标路径**；纯 UIA 路径（工程(P) Expand → 库(L) Expand →
  显示索引(S) Invoke）在同一个提权进程里一次跑通，不移动鼠标、不受 IME 影响，已设为默认。
  注意 `库(L)` 在 **`工程(P)`** 下，不在 `控制器(C)` 下（找错父菜单会 0 命中）。
- 填文件名不要用 auto.SendKeys(路径)：IME 会把字母变候选、产生非法文件名并弹「重命名」
  模态错误，该模态会冻住后续所有 UIA 调用。用 Win32 剪贴板 + Ctrl+A/Ctrl+V（控制组合键
  不受 IME 影响）。SetValue 在该编辑框上可能抛 COMError，剪贴板法更稳。校验 Value==目标后才点打开。
- **Git Bash 会把 argv 里的 `盘符:\\…` 改写成 `盘符:/…`**，native 文件对话框直接报「文件名无效」，
  `MSYS_NO_PATHCONV=1` / `MSYS2_ARG_CONV_EXCL='*'` 都拦不住。解法：路径在 Python 里用 r"<盘符>:\\…"
  拼好再提交（或用本脚本的 `@file` 形式：把路径写进一个 UTF-8 文件，参数传 `@路径文件`）。
- 非提权进程的 mouse_event/keybd_event 被 UIPI 挡住，点不到提权的 Sysmac 窗口；本脚本
  必须跑在提权通道（elev-pyd.py / serve_http.py）。
- 工具条删除/刷新按钮 Name 与 AutomationId 均为空，按"＋右侧同 top 的按钮"定位；
  ＋ 的 AutomationId == 'CreateLibraryReference'。刷新键即使选中行也恒灰，不能用来重读文件引用。
- 表格行不暴露成 UIA DataItem/ListItem（`LibraryDataGrid` 是自绘控件，**连子节点都没有**），
  第一行点击坐标用窗口相对偏移（125% DPI 基线：left+196, top+85）。**行高不是常量**：
  多行时用 --row N + --row-h 覆盖，点完看 `select` 日志里的按钮态确认选中了。
- 「引用库」警告可能延迟 >2s 出现，replace 末尾再 warn 一次兜底。
- 替换同名库会先弹「库已经被引用。库将被一个新的所替换。确定要继续吗？ 库:<名>」，
  按钮是 是(Y) —— 这个框不点掉，后面的 add 会卡住。用 `yes` 模式或 replace 自动补一次。
"""
import sys, os, io, time, ctypes
import ctypes.wintypes as wt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss
import uiautomation as auto

auto.SetGlobalSearchTimeout(3)
u = ctypes.windll.user32
k = ctypes.windll.kernel32
k.GlobalAlloc.restype = ctypes.c_void_p
k.GlobalLock.restype = ctypes.c_void_p
k.GlobalLock.argtypes = [ctypes.c_void_p]
k.GlobalUnlock.argtypes = [ctypes.c_void_p]
u.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]

pid = int(sys.argv[1]); out = sys.argv[2]; mode = sys.argv[3]
_rest = sys.argv[4:]
SLR = ''
ROW = 1
ROW_H = 36
USE_MOUSE = False
for _a in _rest:
    if _a == '--mouse':
        USE_MOUSE = True
    elif _a.startswith('--row='):
        ROW = int(_a.split('=', 1)[1])
    elif _a.startswith('--row-h='):
        ROW_H = int(_a.split('=', 1)[1])
    elif not _a.startswith('--'):
        SLR = _a
# `@file` 形式：把路径写进 UTF-8 文件再传 @文件，绕开 Git Bash 对 `盘符:\…` 的改写
if SLR.startswith('@') and os.path.exists(SLR[1:]):
    SLR = io.open(SLR[1:], encoding='utf-8-sig').read().strip()

_main_hwnd = []


def main_hwnd():
    """Resolve the main window lazily — `list` runs fully offline (no Sysmac needed)."""
    if not _main_hwnd:
        _main_hwnd.append(ss.main_hwnd(pid))
    return _main_hwnd[0]


L = []


def log(m):
    L.append(m)


def set_clip(text):
    data = text.encode('utf-16-le') + b'\x00\x00'
    u.OpenClipboard(0); u.EmptyClipboard()
    h = k.GlobalAlloc(0x0002, len(data))
    p = k.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k.GlobalUnlock(h)
    u.SetClipboardData(13, h)
    u.CloseClipboard()


def combo(vk):
    u.keybd_event(0x11, 0, 0, 0); time.sleep(0.05)
    u.keybd_event(vk, 0, 0, 0); time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0); time.sleep(0.05)
    u.keybd_event(0x11, 0, 2, 0); time.sleep(0.2)


def hover(x, y):
    u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    u.mouse_event(0x0001, 1, 0, 0, 0); time.sleep(0.15)
    u.mouse_event(0x0001, ctypes.c_int(-1).value, 0, 0, 0); time.sleep(0.8)


def esc(n=2):
    for _ in range(n):
        u.keybd_event(0x1B, 0, 0, 0); u.keybd_event(0x1B, 0, 2, 0); time.sleep(0.25)


def wins():
    return ss.wins_of(pid, only_visible=True)


def win(title):
    for w in wins():
        if w['title'] == title:
            return w
    return None


def menu_items(minleft=0, mintop=40, maxtop=900):
    res = []
    for w in auto.GetRootControl().GetChildren():
        if w.ProcessId != pid:
            continue
        stack = [w]; n = 0
        while stack and n < 6000:
            c = stack.pop(); n += 1
            try:
                if c.ControlTypeName == 'MenuItemControl' and (c.Name or '').strip():
                    r = c.BoundingRectangle
                    if r.width() > 4 and r.left >= minleft and mintop < r.top < maxtop:
                        res.append((c.Name, r.left, r.top, r.right, r.bottom))
            except Exception:
                pass
            try:
                stack.extend(c.GetChildren())
            except Exception:
                pass
    return res


def buttons(hwnd):
    res = []
    root = auto.ControlFromHandle(wt.HWND(hwnd))
    for d in auto.WalkControl(root, maxDepth=14):
        c = d[0] if isinstance(d, tuple) else d
        try:
            if c.ControlTypeName == 'ButtonControl':
                r = c.BoundingRectangle
                res.append((c.Name or '', c.AutomationId or '',
                            (r.left, r.top, r.right, r.bottom), c.IsEnabled))
        except Exception:
            pass
    return res


def find_ctl(hwnd, ct, name):
    root = auto.ControlFromHandle(wt.HWND(hwnd))
    for d in auto.WalkControl(root, maxDepth=16):
        c = d[0] if isinstance(d, tuple) else d
        try:
            if c.ControlTypeName == ct and (c.Name or '') == name:
                return c
        except Exception:
            pass
    return None


def dismiss(title):
    w = win(title)
    if w is None:
        return False
    b = find_ctl(w['hwnd'], 'ButtonControl', '确定')
    if b is None:
        b = find_ctl(w['hwnd'], 'ButtonControl', '是(Y)')
    if b is not None:
        try:
            b.GetInvokePattern().Invoke()
            log('dismissed %s' % title)
            time.sleep(0.6)
            return True
        except Exception:
            pass
    return False


def shot(tag):
    from PIL import ImageGrab
    p = out.rsplit('.', 1)[0] + '_' + tag + '.png'
    ImageGrab.grab(all_screens=True).save(p)
    log('shot %s -> %s' % (tag, p))


def do_open():
    esc(3)
    u.SetCursorPos(1250, 820); time.sleep(0.3)
    m, _ = ss.find(pid, '工程(P)')
    if m is None:
        log('工程(P) not found')
    else:
        r = m.BoundingRectangle
        ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(0.8)
        lib = [t for t in menu_items(150) if t[0] in ('库(L)', '库(_L)')]
        if lib:
            t = lib[0]
            hover(t[1] + 60, t[2] + (t[4] - t[2]) // 2)
            time.sleep(0.6)
            sub = [t for t in menu_items(350) if t[0] in ('显示索引(S)', '显示索引(_S)')]
            if sub:
                s = sub[0]
                ss.click_at((s[1] + s[3]) // 2, (s[2] + s[4]) // 2)
                time.sleep(2.5)
            else:
                log('显示索引 not found'); esc(2)
        else:
            log('库(L) not found'); esc(2)
    log('库索引 open=%s' % (win('库索引') is not None))


def do_select():
    w = win('库索引')
    if w is None:
        log('NO 库索引')
    else:
        l, t, ww, hh = w['rect']
        # 第一行在 top+85（125% DPI 基线）；行高按 --row-h 覆盖（默认 36）
        y = t + 85 + (ROW - 1) * ROW_H
        ss.click_at(l + 196, y)
        time.sleep(0.6)
        log('select row=%d at y=%d (window top=%d, row_h=%d)' % (ROW, y, t, ROW_H))
        log('buttons=%r' % (buttons(w['hwnd']),))


def do_delete():
    w = win('库索引')
    if w is None:
        log('NO 库索引')
    else:
        bs = buttons(w['hwnd'])
        plus = [b for b in bs if b[1] == 'CreateLibraryReference']
        if not plus:
            log('no +')
        else:
            pr = plus[0][2]
            dele = [b for b in bs if b[2][1] == pr[1] and b[2][0] >= pr[2] and b[2][0] - pr[2] < 8]
            if dele and dele[0][3]:
                r = dele[0][2]
                ss.click_at((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
                time.sleep(1.0)
                log('deleted; buttons=%r' % (buttons(w['hwnd']),))
            else:
                log('delete disabled/not found %r' % (dele,))
    shot('delete')


def do_add(slr):
    dismiss('重命名')
    w = win('库索引')
    fd = win('引用库文件')
    if w is None:
        log('NO 库索引')
    else:
        if fd is None:
            plus = [b for b in buttons(w['hwnd']) if b[1] == 'CreateLibraryReference']
            if plus:
                r = plus[0][2]
                ss.click_at((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
                time.sleep(1.5)
                fd = win('引用库文件')
        if fd is None:
            log('引用库文件 not open'); shot('add_abort')
        elif not slr:
            log('no SLR path arg'); shot('add_abort')
        else:
            ss.force_foreground(fd['hwnd']); time.sleep(0.4)
            ed = find_ctl(fd['hwnd'], 'EditControl', '文件名(N):')
            ob = find_ctl(fd['hwnd'], 'ButtonControl', '打开(O)')
            if ed is None or ob is None:
                log('edit/open missing'); shot('add_abort')
            else:
                set_clip(slr)
                r = ed.BoundingRectangle
                ss.click_at((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                time.sleep(0.3)
                combo(0x41); combo(0x56)
                time.sleep(0.5)
                got = ''
                try:
                    got = ed.GetValuePattern().Value
                except Exception as e:
                    log('read err %s' % e)
                log('paste got=%r want=%r' % (got, slr))
                if got != slr:
                    log('MISMATCH abort (not opening)'); shot('add_abort')
                else:
                    ob.GetInvokePattern().Invoke()
                    time.sleep(2.0)
                    dismiss('引用库')
                    do_yes()            # 「库已经被引用…确定要继续吗？」→ 是(Y)
                    dismiss_text('当前控制器不支持')
                    time.sleep(0.8)
                    shot('add')


def dismiss_text(marker, button='确定'):
    """按**正文关键字**关模态框（标题不固定时用）：只点名字完全等于 button 的按钮。"""
    hit = 0
    for w in wins():
        try:
            root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
            txt, btn = '', None
            for d in auto.WalkControl(root, maxDepth=10):
                c = d[0] if isinstance(d, tuple) else d
                try:
                    if c.ControlTypeName == 'ButtonControl' and (c.Name or '').strip() == button:
                        btn = c
                    elif c.ControlTypeName == 'TextControl' and (c.Name or ''):
                        txt += c.Name
                except Exception:
                    pass
            if btn is not None and marker in txt:
                btn.GetInvokePattern().Invoke()
                hit += 1
                log('dismiss_text %r in %r' % (marker, w['title']))
                time.sleep(0.7)
        except Exception:
            pass
    return hit


def do_confirm():
    w = win('库索引')
    if w is None:
        log('NO 库索引')
    else:
        ok = find_ctl(w['hwnd'], 'ButtonControl', '确定')
        if ok is not None:
            ok.GetInvokePattern().Invoke()
            log('confirmed')
            time.sleep(1.5)
    shot('confirm')


def do_warn():
    # 「引用库」/「重命名」警告可能 >2s 才冒出来，add 紧跟的 dismiss 会扑空；此处兜底再消一次。
    hit = dismiss('引用库')
    hit2 = dismiss('重命名')
    hit3 = dismiss_text('当前控制器不支持')      # 「库中可能使用了当前控制器不支持的指令。…」
    log('warn dismissed 引用库=%s 重命名=%s 兼容性=%s' % (hit, hit2, hit3))
    shot('warn')


def do_yes():
    """点掉「库已经被引用。库将被一个新的所替换…」这类替换确认框的 是(Y)。

    只认"窗口里既有 是(Y) 按钮、正文又含『库』"的窗口，避免误点别的确认框。
    """
    hit = 0
    for w in wins():
        try:
            root = auto.ControlFromHandle(wt.HWND(w['hwnd']))
            txt, btn = '', None
            for d in auto.WalkControl(root, maxDepth=10):
                c = d[0] if isinstance(d, tuple) else d
                try:
                    if c.ControlTypeName == 'ButtonControl' and (c.Name or '').strip() == '是(Y)':
                        btn = c
                    elif c.ControlTypeName == 'TextControl' and (c.Name or ''):
                        txt += c.Name
                except Exception:
                    pass
            if btn is not None and '库' in txt:
                btn.GetInvokePattern().Invoke()
                hit += 1
                log('clicked 是(Y) in %r' % w['title'])
                time.sleep(0.8)
        except Exception as e:
            log('yes scan err %r: %r' % (w.get('title'), e))
    log('yes hit=%d' % hit)
    shot('yes')


def do_open_uia():
    """纯 UIA 打开库索引：工程(P) Expand → 库(L) Expand → 显示索引(S) Invoke。

    不移动鼠标、不吃 IME；`库(L)` 在 `工程(P)` 下（不在 `控制器(C)` 下）。
    """
    def find_menu(name):
        hits = []
        for w in auto.GetRootControl().GetChildren():
            try:
                if w.ProcessId != pid:
                    continue
            except Exception:
                continue
            for d in auto.WalkControl(w, maxDepth=14):
                c = d[0] if isinstance(d, tuple) else d
                try:
                    if c.ControlTypeName == 'MenuItemControl' and (c.Name or '').strip() == name:
                        hits.append(c)
                except Exception:
                    pass
        return hits

    def act(name, kind):
        hits = find_menu(name)
        log('%s hits=%d' % (name, len(hits)))
        if not hits:
            return False
        c = hits[-1]
        try:
            if kind == 'expand':
                c.GetExpandCollapsePattern().Expand()
            else:
                c.GetInvokePattern().Invoke()
            log('%s %s=ok' % (name, kind))
            return True
        except Exception as e:
            log('%s %s=%r' % (name, kind, e))
            return False

    esc(3)
    ok = act('工程(P)', 'expand')
    time.sleep(0.7)
    ok = act('库(L)', 'expand') and ok
    time.sleep(0.7)
    ok = act('显示索引(S)', 'invoke') and ok
    time.sleep(2.0)
    log('库索引 open=%s (uia)' % (win('库索引') is not None))
    if win('库索引') is None:
        log('UIA 路径未打开库索引；可加 --mouse 走旧的悬停路径')


def do_list(proj):
    """离线读 .smc2：ReferredLibrary/LibraryModel 的名称/版本/ID/路径/两个旗标。

    这是"库索引里到底挂了什么"唯一可靠的取证方式——`LibraryDataGrid` 不向 UIA 暴露行。
    """
    import zipfile
    import re as _re
    if not proj or not os.path.exists(proj):
        log('list needs an existing .smc2 path'); return
    n = 0
    with zipfile.ZipFile(proj) as z:
        for name in z.namelist():
            try:
                t = z.read(name).decode('utf-8-sig')
            except Exception:
                continue
            if '<ReferredLibrary>' not in t:
                continue
            for m in _re.finditer(r'<ReferredLibrary>.*?</ReferredLibrary>', t, _re.S):
                blk = m.group(0)
                def g(tag):
                    mm = _re.search(r'<%s>(.*?)</%s>' % (tag, tag), blk, _re.S)
                    return mm.group(1).strip() if mm else ''
                n += 1
                log('LIB[%d] name=%r version=%r id=%s' % (n, g('Name'), g('Version'), g('LibraryId')))
                log('       path=%r' % g('LibraryFilePath'))
                log('       IsSource=%r IsDisableSourceDisplay=%r NoSource=%r'
                    % (g('IsSource'), g('IsDisableSourceDisplay'), g('IsBackwardCompatibleNoSource')))
                log('       entry=%s' % name)
    log('# libraries=%d (offline, from %s)' % (n, proj))


UI_MODES = ('open', 'select', 'delete', 'add', 'confirm', 'warn', 'yes', 'replace')
if mode in UI_MODES:
    ss.force_foreground(main_hwnd()); time.sleep(0.4)

if mode == 'open':
    if USE_MOUSE:
        do_open()
    else:
        do_open_uia()
elif mode == 'select':
    do_select()
elif mode == 'delete':
    do_delete()
elif mode == 'add':
    do_add(SLR)
elif mode == 'confirm':
    do_confirm()
elif mode == 'warn':
    do_warn()
elif mode == 'yes':
    do_yes()
elif mode == 'list':
    do_list(SLR)
elif mode == 'replace':
    # 一步换库/强制重载：删旧行 → 重加同一路径（库缓存只有重加才会重读，刷新键恒灰）。
    if not SLR:
        log('replace needs SLR path arg')
    else:
        do_select(); do_delete()
        dismiss('引用库'); dismiss('重命名'); do_yes()
        do_add(SLR); do_warn(); do_confirm()
else:
    log('unknown mode %r' % mode)

io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
print('wrote', out, len(L), 'lines')
