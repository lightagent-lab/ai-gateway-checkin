# -*- coding: utf-8 -*-
"""可读性回归测试：用真实像素验证按钮文字对比度达标。

背景：Windows 的 vista 主题会忽略 ttk 的 background 配置，
导致设了白字的主按钮实际渲染成浅灰底 —— 白底白字完全看不清。
必须使用 clam 主题，并保证对比度 >= 4.5:1（WCAG AA）。
"""
import ctypes, os, sys, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")

ok = []
def check(name, cond, extra=""):
    ok.append(bool(cond))
    print(("  PASS " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from uc import fonts as ufonts
ufonts.preload_font_file()
import tkinter as tk
from tkinter import ttk
from PIL import ImageGrab
import gui_app


def lum(c):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c[:3]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    l1, l2 = lum(a), lum(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


root = tk.Tk()
app = gui_app.App(root)
root.geometry("+0+0")
root.attributes("-topmost", True)
root.update_idletasks(); root.update()
time.sleep(1.0); root.update()

print("=== 1) 主题必须是 clam ===")
st = ttk.Style()
check("使用 clam 主题（vista 会忽略自定义颜色）", st.theme_use() == "clam", st.theme_use())

print()
print("=== 2) 按钮真实像素对比度（>= 4.5:1）===")

def sample(widget):
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    w, h = widget.winfo_width(), widget.winfo_height()
    if w < 4 or h < 4:
        return None, None, None
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h)).convert("RGB")
    px = list(img.getdata())
    c = Counter(px)
    bg = c.most_common(1)[0][0]
    best = None
    for col, cnt in c.items():
        if cnt < 3:
            continue
        d = sum(abs(a - b) for a, b in zip(col, bg))
        if best is None or d > best[0]:
            best = (d, col)
    tc = best[1] if best else bg
    return bg, tc, contrast(tc, bg)

for label, btn in (("一键签到", app.btn_run), ("仅查状态", app.btn_status),
                   ("添加账号", app.btn_add), ("检测站点", app.btn_probe)):
    bg, tc, v = sample(btn)
    check("%s 对比度 >= 4.5" % label, v is not None and v >= 4.5,
          "%s on %s = %.2f:1" % (tc, bg, v or 0))

print()
print("=== 3) 主按钮必须是蓝底白字 ===")
bg, tc, v = sample(app.btn_run)
is_blue = bg and bg[2] > 150 and bg[0] < 100
is_white = tc and min(tc[:3]) > 200
check("背景是蓝色", bool(is_blue), str(bg))
check("文字是白色", bool(is_white), str(tc))

print()
print("=== 4) 表格与日志区域可读 ===")
for name, w in (("表格", app.tree), ("日志", app.logbox)):
    bg, tc, v = sample(w)
    check("%s 对比度 >= 4.5" % name, v is not None and v >= 4.5,
          "%.2f:1" % (v or 0))

root.destroy()
p = sum(ok)
print()
print("=" * 54)
print("可读性测试: %d/%d 通过" % (p, len(ok)))
print("=" * 54)
sys.exit(0 if p == len(ok) else 1)