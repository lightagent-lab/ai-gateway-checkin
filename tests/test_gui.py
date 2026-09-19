# -*- coding: utf-8 -*-
"""GUI 冒烟测试：真实创建窗口，验证账号管理、站点检测、批量签到全链路。"""
import os, sys, time, random, string, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

spec = importlib.util.spec_from_file_location("gui", os.path.join(ROOT, "gui_app.py"))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)

import tkinter as tk
from uc.store import Account

NEWAPI = "http://127.0.0.1:8901"
SUB2API = "http://127.0.0.1:8902"
ok = []


def check(name, cond, extra=""):
    ok.append(bool(cond))
    print(("  PASS " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))


def rnd(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# 让配置写到测试目录，避免污染
gui.HERE = ROOT
root = tk.Tk()
app = gui.App(root)
root.update()

print("=== 1) 窗口构建 ===")
check("标题正确", "签到" in root.title(), root.title())
check("表格列数", len(app.tree["columns"]) == 7)

print()
print("=== 2) 账号录入（站点自己输入）===")
app.accounts = [
    Account(site=NEWAPI, username="g1_" + rnd(), password="goodpass", note="NA-A"),
    Account(site=SUB2API, username="g2_" + rnd() + "@m.com", password="goodpass", note="S2-A"),
]
app.refresh()
root.update()
check("表格渲染 2 行", len(app.tree.get_children()) == 2)
first = app.tree.item(app._items[app.accounts[0].key], "values")
check("站点列显示正确", "127.0.0.1:8901" in first[1], first[1])
check("备注列显示正确", first[2] == "NA-A", first[2])

print()
print("=== 3) 站点检测 ===")
app.default_site.set(NEWAPI)
app.probe()
t0 = time.time()
while time.time() - t0 < 20:
    root.update(); app._drain(); time.sleep(0.05)
    if "站点类型" in app.logbox.get("1.0", "end"):
        break
logtext = app.logbox.get("1.0", "end")
check("检测到 new-api", "new-api 家族" in logtext,
      [l.strip() for l in logtext.splitlines() if "站点类型" in l][-1:])

app.default_site.set(SUB2API)
before_len = len(app.logbox.get("1.0", "end"))
app.probe()
t0 = time.time()
while time.time() - t0 < 20:
    root.update(); app._drain(); time.sleep(0.05)
    newtext = app.logbox.get("1.0", "end")[before_len:]
    if "站点类型" in newtext:
        break
check("检测到 sub2api", "sub2api 家族" in app.logbox.get("1.0", "end")[before_len:],
      [l.strip() for l in app.logbox.get("1.0", "end")[before_len:].splitlines() if "站点类型" in l][:1])

print()
print("=== 4) 一键签到（混合站点）===")
app.accounts = [
    Account(site=NEWAPI, username="r1_" + rnd(), password="goodpass", note="NA-1"),
    Account(site=NEWAPI, username="r2_" + rnd(), password="goodpass", note="NA-2"),
    Account(site=SUB2API, username="r3_" + rnd() + "@m.com", password="goodpass", note="S2-1"),
    Account(site=SUB2API, username="r4_" + rnd() + "@m.com", password="goodpass", note="S2-2"),
    Account(site=NEWAPI, username="bad_" + rnd(), password="nope", note="坏号"),
    Account(site="http://127.0.0.1:8999", username="x", password="y", note="不可达"),
]
app.refresh()
root.update()
app.start(True)
t0 = time.time()
while app.busy and time.time() - t0 < 60:
    root.update(); app._drain(); time.sleep(0.05)
root.update(); app._drain(); root.update()

summary = app.summary.cget("text")
print("   汇总:", summary)
check("成功 4 个", "成功 4" in summary, summary)
check("记录了不支持站点", "不支持 1" in summary, summary)
check("失败 1 个", "失败 1" in summary, summary)

states = {}
for a in app.accounts:
    states[a.state] = states.get(a.state, 0) + 1
check("状态分布正确", states.get("ok") == 4 and states.get("err") == 1
      and states.get("unsupported") == 1, states)

print()
print("=== 5) 重复签到识别 ===")
app.start(True)
t0 = time.time()
while app.busy and time.time() - t0 < 60:
    root.update(); app._drain(); time.sleep(0.05)
root.update(); app._drain(); root.update()
s2 = app.summary.cget("text")
print("   第二轮:", s2)
check("第二轮全部已签到", "已签过 4" in s2, s2)

root.destroy()
p = sum(ok)
print()
print("=" * 56)
print("GUI 测试: %d/%d 通过" % (p, len(ok)))
print("=" * 56)
sys.exit(0 if p == len(ok) else 1)
