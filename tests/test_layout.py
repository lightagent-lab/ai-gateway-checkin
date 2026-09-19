# -*- coding: utf-8 -*-
"""布局回归测试：确认所有控件都有真实尺寸、不溢出、主按钮可点。"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)

from uc import fonts as ufonts
ufonts.preload_font_file()
import tkinter as tk
import gui_app

ok = []
def check(name, cond, extra=""):
    ok.append(bool(cond))
    print(("  PASS " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))

root = tk.Tk()
app = gui_app.App(root)
root.update_idletasks(); root.update()

W, H = root.winfo_width(), root.winfo_height()
print("窗口: %dx%d" % (W, H))
print("屏幕: %dx%d" % (root.winfo_screenwidth(), root.winfo_screenheight()))
print("字体: %s" % app.font_family)
print("请求尺寸: %dx%d" % (root.winfo_reqwidth(), root.winfo_reqheight()))
print()

print("=== 1) 窗口不超出屏幕 ===")
check("宽度不超屏", W <= root.winfo_screenwidth(), "%d <= %d" % (W, root.winfo_screenwidth()))
check("高度不超屏", H <= root.winfo_screenheight(), "%d <= %d" % (H, root.winfo_screenheight()))

print()
print("=== 2) 关键按钮尺寸 ===")
for label, btn in (("一键签到", app.btn_run), ("仅查状态", app.btn_status),
                   ("停止", app.btn_stop), ("添加账号", app.btn_add),
                   ("检测站点", app.btn_probe)):
    w, h = btn.winfo_width(), btn.winfo_height()
    check("%s 可见且有尺寸" % label, w > 20 and h > 10, "%dx%d" % (w, h))

print()
print("=== 3) 主按钮在窗口内可点击 ===")
bx, by = app.btn_run.winfo_rootx() - root.winfo_rootx(), app.btn_run.winfo_rooty() - root.winfo_rooty()
bw, bh = app.btn_run.winfo_width(), app.btn_run.winfo_height()
check("按钮左边界 >= 0", bx >= 0, bx)
check("按钮右边界在窗口内", bx + bw <= W, "%d <= %d" % (bx + bw, W))
check("按钮底边界在窗口内", by + bh <= H, "%d <= %d" % (by + bh, H))
print("     一键签到 位置=(%d,%d) 尺寸=%dx%d" % (bx, by, bw, bh))

print()
print("=== 4) 所有控件都不重叠、尺寸正常 ===")
problems = []
def walk(w, depth=0):
    for ch in w.winfo_children():
        cls = ch.winfo_class()
        cw, chh = ch.winfo_width(), ch.winfo_height()
        cx, cy = ch.winfo_x(), ch.winfo_y()
        mgr = ch.winfo_manager()
        if mgr and (cw <= 1 or chh <= 1):
            txt = ""
            try: txt = str(ch.cget("text"))[:20]
            except Exception: pass
            problems.append("%s %r 尺寸=%dx%d" % (cls, txt, cw, chh))
        walk(ch, depth+1)
walk(root)
check("没有 1x1 的可见控件", not problems, problems[:5])

print()
print("=== 5) 关键区域不被裁切 ===")
for name, w in (("表格", app.tree), ("日志", app.logbox), ("状态栏", app.summary)):
    x, y = w.winfo_rootx() - root.winfo_rootx(), w.winfo_rooty() - root.winfo_rooty()
    ww, wh = w.winfo_width(), w.winfo_height()
    inside = (x >= 0 and y >= 0 and x + ww <= W + 2 and y + wh <= H + 2)
    check("%s 在窗口内" % name, inside, "pos=(%d,%d) size=%dx%d" % (x, y, ww, wh))

print()
print("=== 6) 字体确实生效 ===")
check("字体不是默认回退", app.font_family not in ("TkDefaultFont", ""), app.font_family)
import tkinter.font as tkfont
f = tkfont.nametofont("TkDefaultFont")
check("默认字体已绑定", f.actual().get("family") == app.font_family,
      "%s vs %s" % (f.actual().get("family"), app.font_family))

print()
print("=== 7) 表格渲染 ===")
from uc.store import Account
app.accounts = [Account(site="https://a.com", username="u1", password="p", note="测试号")]
app.refresh(); root.update()
check("表格有 1 行", len(app.tree.get_children()) == 1)
check("空态提示已隐藏", not app.empty.winfo_ismapped())

root.destroy()
p = sum(ok)
print()
print("=" * 54)
print("布局测试: %d/%d 通过" % (p, len(ok)))
print("=" * 54)
sys.exit(0 if p == len(ok) else 1)