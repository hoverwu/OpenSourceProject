# -*- coding: utf-8 -*-
"""ss_crashdlg.py - 发现并安全处理 Sysmac 的 .NET 未处理异常框（ThreadExceptionDialog）。

作者：hoverwu ｜ 版本：0.1.0 ｜ 本版更新：2026-11-07

为什么会碰到：2026-11-07 02:34 用方向键驱动轴设置表的"输出设备1"组合框时，Sysmac 弹出
了自己的 `Microsoft .NET Framework / 未将对象引用设置到对象的实例` 对话框。它是**模态**
的，会把之后所有 UIA 调用拖成长时间不返回（pitfalls §63）——所以"脚本跑了很久还没结束"
第一件要怀疑的事就是屏幕上压着这么一个框，而不是 UIA 慢了。

按钮布局固定是 `详细信息(D)` / `继续(C)` / 关闭(X)：
- **只点 `继续(C)`**：实测点完实例存活、已经写进模型的值都还在；
- `详细信息(D)`、标题栏 X **永不碰**（会带走进程或再开一层窗口）；
- 任何带"许可/License/序列号"字样的对话框都不在这个脚本的处理范围里，遇到就停下报告。

默认动作是**只报告不动手**；要真点就在命令行末尾加 `click`。

  python ss_crashdlg.py <pid> <out.txt>            列出该进程所有顶级窗口 + 异常框按钮
  python ss_crashdlg.py <pid> <out.txt> click      仅点击 继续(C)
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import uiautomation as auto                                               # noqa: E402
import ss_uimap as U                                                      # noqa: E402

SAFE_BUTTONS = ('继续',)          # 只有这两个字开头的按钮允许点
FORBIDDEN = ('详细信息', '关闭', '取消', '退出')
WATCH_WORDS = ('许可', 'License', '序列号', 'Serial')


def main():
    pid = U.resolve_pid(sys.argv[1])
    out = sys.argv[2]
    do = len(sys.argv) > 3 and sys.argv[3] == 'click'
    lines = ['# ss_crashdlg pid=%d click=%s' % (pid, do)]
    log = lines.append
    tops = list(U.wins_of(pid, only_visible=True))
    for w in tops:
        log('TOP hwnd=%s title=%r rect=%s' % (w['hwnd'], w['title'], w['rect']))
        if any(t in w['title'] for t in WATCH_WORDS):
            log('  !! 许可/序列号相关窗口 - 本脚本绝不操作，请人工处理')
    for w in tops:
        if '.NET' not in w['title'] and 'Framework' not in w['title']:
            continue
        log('== 异常框 hwnd=%s title=%r' % (w['hwnd'], w['title']))
        try:
            c = auto.ControlFromHandle(w['hwnd'])
        except Exception as e:
            log('  ControlFromHandle 失败 %s' % e.__class__.__name__)
            continue
        for b in U.find_by_type(c, ('ButtonControl',), maxd=12):
            name = (U.prop(b, 'Name') or '').strip()
            r = U.prop(b, 'BoundingRectangle')
            key = name.replace(' ', '').replace('(', '').replace('（', '')
            verdict = '允许点' if key.startswith(SAFE_BUTTONS) else '禁点'
            log('  button %r rect=%s %s PAT=%s' % (name, r, verdict, U.pats(b)))
            if not do or not key.startswith(SAFE_BUTTONS):
                continue
            U.left_click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            log('  已点击 %r' % name)
            time.sleep(1.5)
    if len(lines) == 1 + len(tops):
        log('没有 .NET 异常框（上面只是顶级窗口清单）')
    U.dump(out, lines[0], lines[1:])
    print('-> %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
