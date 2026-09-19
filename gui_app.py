# -*- coding: utf-8 -*-
"""
AI 中转站自动签到 - 图形界面

支持 new-api / sub2api 家族站点自动识别，站点地址在界面里自己填。
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
from datetime import datetime

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "frozen", False):
    os.chdir(HERE)
    sys.path.insert(0, HERE)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from uc import APP_NAME, __version__
from uc.runner import Runner, summarize, UNSUPPORTED
from uc.sites import detect, SiteError, make_session
from uc.store import Account, TokenStore, dump_accounts, load_accounts

CONFIG_FILE = "config.json"


def config_path():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else HERE
    return os.path.join(base, CONFIG_FILE)


def data_path(name):
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else HERE
    return os.path.join(base, name)


class Config:
    def __init__(self):
        self.path = config_path()
        self.data = {"default_site": "", "workers": 3, "auto": False, "auto_time": "08:30"}
        try:
            import json
            with open(self.path, "r", encoding="utf-8") as fh:
                self.data.update(json.load(fh))
        except Exception:
            pass

    def save(self):
        try:
            import json
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass


class AccountDialog(tk.Toplevel):
    def __init__(self, master, default_site="", account=None):
        super().__init__(master)
        self.title("编辑账号" if account else "添加账号")
        self.resizable(False, False)
        self.transient(master)
        self.result = None

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        self.vars = {
            "site": tk.StringVar(value=account.site if account else default_site),
            "username": tk.StringVar(value=account.username if account else ""),
            "password": tk.StringVar(value=account.password if account else ""),
            "note": tk.StringVar(value=account.note if account else ""),
            "proxy": tk.StringVar(value=(account.proxy or "") if account else ""),
        }

        rows = [
            ("站点地址", "site", False, "https://example.com"),
            ("用户名/邮箱", "username", False, "登录用的账号"),
            ("密码", "password", True, ""),
            ("备注", "note", False, "给小号起个名"),
            ("代理(可空)", "proxy", False, "http://127.0.0.1:7890"),
        ]
        for r, (label, key, secret, hint) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=5, padx=(0, 10))
            ent = ttk.Entry(body, textvariable=self.vars[key], width=44,
                            show="*" if secret else "")
            ent.grid(row=r, column=1, sticky="ew", pady=5)
            if hint:
                ttk.Label(body, text=hint, foreground="#999").grid(
                    row=r, column=2, sticky="w", padx=(8, 0))
            if r == 0:
                ent.focus_set()

        ttk.Label(body, text="提示：不同的站点可以分别添加，本工具会自动识别站点类型",
                  foreground="#888").grid(row=len(rows), column=0, columnspan=3,
                                          sticky="w", pady=(10, 0))

        btns = ttk.Frame(body)
        btns.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="确定", command=self._ok).pack(side="right")

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self._center(master)

    def _center(self, master):
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))

    def _ok(self):
        site = self.vars["site"].get().strip()
        user = self.vars["username"].get().strip()
        pwd = self.vars["password"].get().strip()
        if not site or not user or not pwd:
            messagebox.showwarning("信息不全", "站点、用户名、密码都要填。", parent=self)
            return
        self.result = (site, user, pwd, self.vars["note"].get().strip(),
                       self.vars["proxy"].get().strip())
        self.destroy()
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = Config()
        self.accounts = []
        self.q = queue.Queue()
        self.busy = False
        self.stop_event = threading.Event()
        self.auto_done = None
        self._items = {}

        root.title("%s v%s" % (APP_NAME, __version__))
        root.geometry("1120x740")
        root.minsize(940, 620)

        self._style()
        self._toolbar()
        self._table()
        self._status()
        self._log()

        self.load()
        self.log("账号文件: %s" % data_path("accounts.txt"))
        if not self.accounts:
            self.log("还没有账号：点「＋ 添加账号」填入站点地址和账号密码。")

        self.root.after(120, self._drain)
        self.root.after(1000, self._auto_tick)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- UI ----------
    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("vista")
        except tk.TclError:
            pass
        s.configure("Treeview", rowheight=26, font=("Microsoft YaHei UI", 10))
        s.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Big.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 8))
        s.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(10, 5))
        s.configure("TLabel", font=("Microsoft YaHei UI", 9))

    def _toolbar(self):
        bar = ttk.Frame(self.root, padding=(12, 10, 12, 6))
        bar.pack(fill="x")

        self.btn_add = ttk.Button(bar, text="＋ 添加账号", command=self.add)
        self.btn_add.pack(side="left")
        ttk.Button(bar, text="导入文件", command=self.import_file).pack(side="left", padx=6)
        ttk.Button(bar, text="编辑", command=self.edit).pack(side="left")
        ttk.Button(bar, text="删除", command=self.delete).pack(side="left", padx=6)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10, pady=2)

        ttk.Label(bar, text="默认站点").pack(side="left")
        self.default_site = tk.StringVar(value=self.cfg.data.get("default_site", ""))
        e = ttk.Entry(bar, textvariable=self.default_site, width=26)
        e.pack(side="left", padx=(4, 2))
        e.bind("<FocusOut>", lambda _ev: self._save_default_site())
        e.bind("<Return>", lambda _ev: self._save_default_site())

        self.btn_probe = ttk.Button(bar, text="检测站点", command=self.probe)
        self.btn_probe.pack(side="left", padx=(2, 8))

        ttk.Label(bar, text="并发").pack(side="left")
        self.workers = tk.StringVar(value=str(self.cfg.data.get("workers", 3)))
        ttk.Spinbox(bar, from_=1, to=20, width=4, textvariable=self.workers).pack(side="left", padx=(4, 0))

        self.btn_stop = ttk.Button(bar, text="停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="right")

        self.btn_status = ttk.Button(bar, text="仅查状态", command=lambda: self.start(False))
        self.btn_status.pack(side="right", padx=6)

        self.btn_run = ttk.Button(bar, text="一键签到", style="Big.TButton",
                                  command=lambda: self.start(True))
        self.btn_run.pack(side="right")

        bar2 = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        bar2.pack(fill="x")
        self.only_sel = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text="只处理选中", variable=self.only_sel).pack(side="left")
        self.auto_var = tk.BooleanVar(value=bool(self.cfg.data.get("auto", False)))
        ttk.Checkbutton(bar2, text="每天定时自动签到", variable=self.auto_var,
                        command=self.toggle_auto).pack(side="left", padx=(14, 0))
        self.auto_time = tk.StringVar(value=self.cfg.data.get("auto_time", "08:30"))
        self.auto_entry = ttk.Entry(bar2, textvariable=self.auto_time, width=7,
                                    state="normal" if self.cfg.data.get("auto") else "disabled")
        self.auto_entry.pack(side="left", padx=6)
        ttk.Label(bar2, text="（窗口保持开着即可，格式 HH:MM）",
                  foreground="#888").pack(side="left")

    def _table(self):
        wrap = ttk.Frame(self.root, padding=(12, 0))
        wrap.pack(fill="both", expand=True)

        cols = ("idx", "site", "account", "state", "info", "reward", "total")
        heads = {
            "idx": ("#", 40, "center"),
            "site": ("站点", 210, "w"),
            "account": ("账号 / 备注", 190, "w"),
            "state": ("状态", 76, "center"),
            "info": ("说明", 260, "w"),
            "reward": ("本次奖励", 92, "e"),
            "total": ("累计签到", 78, "center"),
        }
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        for c in cols:
            t, w, a = heads[c]
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "info"))

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        self.tree.tag_configure("ok", foreground="#0f7b3c")
        self.tree.tag_configure("already", foreground="#8a8a8a")
        self.tree.tag_configure("err", foreground="#c0392b")
        self.tree.tag_configure("unsupported", foreground="#b8860b")

        self.tree.bind("<Double-1>", lambda _e: self.edit())
        self.tree.bind("<Delete>", lambda _e: self.delete())

    def _status(self):
        bar = ttk.Frame(self.root, padding=(12, 8, 12, 4))
        bar.pack(fill="x")
        self.summary = ttk.Label(bar, text="就绪", font=("Microsoft YaHei UI", 10, "bold"))
        self.summary.pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=300)
        self.progress.pack(side="right")

    def _log(self):
        wrap = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        wrap.pack(fill="both")
        self.logbox = tk.Text(wrap, height=8, wrap="word", font=("Consolas", 9),
                              background="#1e1e1e", foreground="#d4d4d4",
                              insertbackground="#d4d4d4", relief="flat", padx=8, pady=6)
        self.logbox.pack(side="left", fill="both", expand=True)
        ls = ttk.Scrollbar(wrap, orient="vertical", command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=ls.set, state="disabled")
        ls.pack(side="right", fill="y")

    def log(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.logbox.configure(state="normal")
        self.logbox.insert("end", "[%s] %s\n" % (stamp, msg))
        self.logbox.see("end")
        self.logbox.configure(state="disabled")
    # ---------- 账号 ----------
    def _save_default_site(self):
        self.cfg.data["default_site"] = self.default_site.get().strip()
        self.cfg.save()

    def load(self):
        path = data_path("accounts.txt")
        self.accounts = load_accounts(path, self.cfg.data.get("default_site", ""))
        self.refresh()

    def save(self):
        dump_accounts(self.accounts, data_path("accounts.txt"))

    def refresh(self):
        for i, a in enumerate(self.accounts, 1):
            a.index = i
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        for a in self.accounts:
            self._row(a)

    def _row(self, a):
        tag = a.state or ""
        state = {"ok": "成功", "already": "已签到", "err": "失败",
                 "unsupported": "不支持", "": "-"}.get(a.state, a.state)
        vals = (a.index, a.site.replace("https://", "").replace("http://", ""),
                a.note or a.username, state, a.message,
                ("%.6f" % a.reward) if a.reward else "",
                a.total_checkins or "")
        key = a.key
        if key in self._items:
            self.tree.item(self._items[key], values=vals, tags=(tag,) if tag else ())
        else:
            self._items[key] = self.tree.insert("", "end", values=vals,
                                                tags=(tag,) if tag else ())

    def _sel(self):
        s = set(self.tree.selection())
        return [a for a in self.accounts if self._items.get(a.key) in s]

    def add(self):
        d = AccountDialog(self.root, self.default_site.get().strip())
        self.root.wait_window(d)
        if not d.result:
            return
        site, user, pwd, note, proxy = d.result
        acc = Account(site=site, username=user, password=pwd, note=note, proxy=proxy or None)
        if any(a.key == acc.key for a in self.accounts):
            messagebox.showwarning("重复", "该站点下的这个账号已存在。")
            return
        self.accounts.append(acc)
        self.refresh()
        self.save()
        self.log("已添加 %s @ %s" % (user, site))

    def edit(self):
        sel = self._sel()
        if len(sel) != 1:
            messagebox.showinfo("请选择一个", "双击某行或选中一行后再点编辑。")
            return
        a = sel[0]
        d = AccountDialog(self.root, account=a)
        self.root.wait_window(d)
        if not d.result:
            return
        site, user, pwd, note, proxy = d.result
        a.site, a.username, a.password = site, user, pwd
        a.note, a.proxy = note, proxy or None
        a.state, a.message = "", ""
        self.refresh()
        self.save()
        self.log("已更新 %s @ %s" % (user, site))

    def delete(self):
        sel = self._sel()
        if not sel:
            messagebox.showinfo("没有选中", "先选中要删除的账号。")
            return
        if not messagebox.askyesno("确认", "删除选中的 %d 个账号？" % len(sel)):
            return
        keys = set(a.key for a in sel)
        self.accounts = [a for a in self.accounts if a.key not in keys]
        self.refresh()
        self.save()
        self.log("已删除 %d 个账号" % len(sel))

    def import_file(self):
        p = filedialog.askopenfilename(title="选择账号文件",
                                       filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not p:
            return
        got = load_accounts(p, self.default_site.get().strip())
        if not got:
            messagebox.showwarning("没读到", "文件里没有可识别的账号行。\n\n"
                                             "格式: 站点 用户名 密码 [备注]")
            return
        exist = set(a.key for a in self.accounts)
        n = 0
        for a in got:
            if a.key in exist:
                continue
            self.accounts.append(a)
            exist.add(a.key)
            n += 1
        self.refresh()
        self.save()
        self.log("导入 %d 个账号（跳过重复 %d 个）" % (n, len(got) - n))

    # ---------- 站点检测 ----------
    def probe(self):
        site = self.default_site.get().strip()
        if not site:
            sel = self._sel()
            if len(sel) == 1:
                site = sel[0].site
        if not site:
            messagebox.showinfo("请输入站点", "先在「默认站点」里填地址，或选中一个账号。")
            return
        self.log("正在检测 %s ..." % site)

        def work():
            try:
                fam = detect(site, session=make_session(url_hint=site), timeout=15)
                lines = ["检测结果：",
                         "  站点类型: %s" % fam.label,
                         "  站点名称: %s" % (fam.site_name or "(未提供)"),
                         "  接口前缀: %s" % fam.api_prefix,
                         "  签到功能: %s" % ("已开启" if fam.checkin_enabled is not False else "未开启"),
                         "  人机验证: %s" % ("需要 Turnstile" if fam.turnstile else "无")]
                if fam.notes:
                    lines.append("  识别依据: " + "; ".join(fam.notes))
                self.q.put(("msg", "\n".join(lines)))
            except SiteError as exc:
                self.q.put(("msgerr", "检测失败：%s" % exc))
            except Exception as exc:
                self.q.put(("msgerr", "检测异常：%s: %s" % (type(exc).__name__, exc)))

        threading.Thread(target=work, daemon=True).start()
    # ---------- 执行 ----------
    def start(self, do_checkin):
        if self.busy:
            return
        targets = self._sel() if self.only_sel.get() else list(self.accounts)
        if not targets:
            messagebox.showinfo("没有账号",
                                "列表里还没有账号，点「＋ 添加账号」先加几个。"
                                if not self.accounts else "没有选中任何账号。")
            return
        try:
            workers = max(1, min(20, int(self.workers.get())))
        except ValueError:
            workers = 3
        self.cfg.data["workers"] = workers
        self.cfg.save()
        self._save_default_site()

        self.busy = True
        self.stop_event.clear()
        for a in targets:
            a.state, a.message, a.reward = "", "", 0.0
            self._row(a)

        self.log("开始%s：%d 个账号，%d 并发" %
                 ("签到" if do_checkin else "查询状态", len(targets), workers))
        self.progress.configure(maximum=len(targets), value=0)
        self._running(True)

        run = Runner(
            targets, store=TokenStore(data_path("tokens.json")),
            workers=workers, do_checkin=do_checkin, timeout=25,
            log=lambda m: self.q.put(("log", m)),
            on_account=lambda a: self.q.put(("row", a)),
            stop_event=self.stop_event,
        )

        def work():
            try:
                res = run.run()
                self.q.put(("done", (res, summarize(res), do_checkin, run.families)))
            except Exception as exc:
                self.q.put(("log", "执行异常: %s: %s" % (type(exc).__name__, exc)))
                self.q.put(("done", ([], summarize([]), do_checkin, {})))

        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        self.stop_event.set()
        self.log("已请求停止…")
        self.btn_stop.configure(state="disabled")

    def _running(self, on):
        st = "disabled" if on else "normal"
        for b in (self.btn_run, self.btn_status, self.btn_add, self.btn_probe):
            b.configure(state=st)
        self.btn_stop.configure(state="normal" if on else "disabled")

    def _drain(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log(item[1])
                elif kind == "row":
                    self._row(item[1])
                    done = sum(1 for a in self.accounts if a.state)
                    self.progress.configure(value=done)
                elif kind == "msg":
                    self.log(item[1].replace("\n", "\n" + " " * 22))
                    messagebox.showinfo("检测结果", item[1])
                elif kind == "msgerr":
                    self.log(item[1])
                    messagebox.showerror("检测失败", item[1])
                elif kind == "done":
                    self._finish(*item[1])
        except queue.Empty:
            pass
        self.root.after(120, self._drain)

    def _finish(self, results, s, do_checkin, families):
        self.busy = False
        self._running(False)
        self.progress.configure(value=0)
        if families:
            self.log("站点识别: " + "; ".join("%s=%s" % kv for kv in families.items()))
        text = ("完成：成功 %d | 已签过 %d | 失败 %d | 不支持 %d | 入账 %.6f"
                % (s["ok"], s["already"], s["err"], s["unsupported"], s["reward"]))
        self.summary.configure(text=text)
        self.log(text)
        if do_checkin and s["ok"]:
            self.auto_done = datetime.now().strftime("%Y-%m-%d")

    # ---------- 定时 ----------
    def toggle_auto(self):
        on = self.auto_var.get()
        self.auto_entry.configure(state="normal" if on else "disabled")
        self.cfg.data["auto"] = on
        self.cfg.save()
        self.log("定时签到已%s" % (("开启：每天 %s" % self.auto_time.get()) if on else "关闭"))

    def _auto_tick(self):
        if self.auto_var.get() and not self.busy:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            want = self.auto_time.get().strip()
            if (len(want) == 5 and ":" in want
                    and now.strftime("%H:%M") >= want
                    and self.auto_done != today):
                self.log("到达定时时间 %s，自动开始签到" % want)
                self.cfg.data["auto_time"] = want
                self.cfg.save()
                self.start(True)
        self.root.after(20000, self._auto_tick)

    def _close(self):
        if self.busy and not messagebox.askyesno("任务进行中", "还有任务在跑，确定退出？"):
            return
        self.stop_event.set()
        self.cfg.data["auto_time"] = self.auto_time.get().strip()
        self.cfg.save()
        self.root.destroy()


def main():
    # 命令行参数优先处理（打包成 exe 后也支持 --selftest / --detect）
    try:
        from uc.selftest import handle_cli
        if handle_cli(sys.argv[1:]):
            return 0
    except Exception:
        pass

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
