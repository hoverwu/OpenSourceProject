# -*- coding: utf-8 -*-
"""del_screen.py - 按名字删除一个画面（只删指定名称；若出现“被引用”警告则点否）（hoverwu / 0.1.0）"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uiautomation as a
import ebx_screen_importer as imp

if len(sys.argv) > 1:
    TARGET = sys.argv[1]
else:
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "del_target.txt")
    TARGET = open(p, encoding="utf-8").read().strip()
win = imp.find_main()
if win is None:
    print("[ERR] EBX not running")
    sys.exit(1)
imp.activate(win)
imp.keys("esc")   # 退出可能存在的内联重命名
time.sleep(0.2)
max_left = imp.rect(win)[0] + 380
rows = imp.screen_rows(win, max_left)
print("[rows]", [r[0] for r in rows])
row = None
for r in rows:
    if r[0] == TARGET:
        row = r
if row is None:
    print("[ERR] not found")
    sys.exit(2)
imp.rclick(row[1] + 60, row[2] + 6)
print("[menu]", imp.menu_click(win.ProcessId, lambda n: n == "删除", 1.2))

# 检查是否弹了“正被使用”的确认框；点“否”保护
cancel = False
for c in a.GetRootControl().GetChildren():
    try:
        if c.ProcessId != win.ProcessId:
            continue
        l, t, w, h = imp.rect(c)
        if c.ClassName in ("#32770", "Qt5QWindowIcon") and c.Name != win.Name and w < 800:
            print("[dialog]", c.Name, (l, t, w, h))
            for e in imp.walk(c, 300):
                if e.ControlTypeName == "ButtonControl":
                    nm = (e.Name or "").strip()
                    print("   button:", repr(nm))
                    if nm in ("否", "No", "取消"):
                        bx, by, bw, bh = imp.rect(e)
                        imp.click(bx + bw // 2, by + bh // 2, 0.8)
                        cancel = True
    except Exception:
        pass
after = [r[0] for r in imp.screen_rows(win, max_left)]
print("[after]", after, "cancelled" if cancel else "deleted")
imp.keys("ctrl+s")
time.sleep(1.0)
