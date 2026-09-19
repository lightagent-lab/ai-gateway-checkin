#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 中转站自动签到 - 命令行版

用法:
    python cli.py check                      # 全部账号签到
    python cli.py status                     # 只看状态
    python cli.py detect https://site.com    # 检测站点类型
    python cli.py loop --at 08:30            # 常驻定时签到
    python cli.py -a accounts.txt -w 5 check
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uc import APP_NAME, __version__
from uc.runner import Runner, summarize, UNSUPPORTED
from uc.sites import detect, SiteError, make_session
from uc.store import TokenStore, dump_accounts, load_accounts

STATE_LABEL = {"ok": "成功", "already": "已签到", "err": "失败",
               "unsupported": "不支持", "": "-"}


def cmd_detect(args):
    site = args.site
    print("检测 %s ..." % site)
    try:
        fam = detect(site, session=make_session(url_hint=site), timeout=20)
    except SiteError as exc:
        print("  失败: %s" % exc)
        return 2
    print("  站点类型 : %s" % fam.label)
    print("  站点名称 : %s" % (fam.site_name or "(未提供)"))
    print("  接口前缀 : %s" % fam.api_prefix)
    print("  登录接口 : %s" % fam.login_path)
    print("  签到功能 : %s" % ("已开启" if fam.checkin_enabled is not False else "未开启"))
    print("  人机验证 : %s" % ("需要 Turnstile" if fam.turnstile else "无"))
    for n in fam.notes:
        print("  依据     : %s" % n)
    return 0


def cmd_run(args, do_checkin):
    accs = load_accounts(args.accounts, args.site or "")
    if not accs:
        print("没有读到账号。请创建 %s，格式：" % os.path.abspath(args.accounts))
        print("    站点 用户名 密码 [备注]")
        print("例: https://example.com  me@mail.com  mypass  小号A")
        return 2

    print("%s v%s" % (APP_NAME, __version__))
    print("账号 %d 个 | 并发 %d | %s" % (len(accs), args.workers,
                                      "签到" if do_checkin else "仅查状态"))
    print("-" * 68)

    run = Runner(accs, store=TokenStore(args.tokens), workers=args.workers,
                 do_checkin=do_checkin, timeout=args.timeout, log=print)
    results = run.run()
    s = summarize(results)

    print("-" * 68)
    if run.families:
        for k, v in run.families.items():
            print("站点 %s -> %s" % (k, v))
    print("合计: 成功 %d | 已签过 %d | 失败 %d | 不支持 %d | 奖励 %.8f"
          % (s["ok"], s["already"], s["err"], s["unsupported"], s["reward"]))

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["序号", "站点", "账号", "备注", "状态", "说明",
                        "本次奖励", "累计签到", "站点类型"])
            for a in results:
                w.writerow([a.index, a.site, a.username, a.note,
                            STATE_LABEL.get(a.state, a.state), a.message,
                            "%.8f" % a.reward, a.total_checkins, a.family])
        print("结果已导出: %s" % os.path.abspath(args.out))
    return 0


def main():
    ap = argparse.ArgumentParser(description=APP_NAME, add_help=True)
    ap.add_argument("action", nargs="?", default="check",
                    choices=["check", "status", "detect", "loop"],
                    help="check=签到 status=仅查状态 detect=检测站点 loop=定时循环")
    ap.add_argument("site", nargs="?", default="", help="detect 时的站点地址")
    ap.add_argument("-a", "--accounts", default="accounts.txt", help="账号文件")
    ap.add_argument("--tokens", default="tokens.json", help="token 缓存文件")
    ap.add_argument("-w", "--workers", type=int, default=3, help="并发数(1-20)")
    ap.add_argument("--timeout", type=int, default=25, help="请求超时秒数")
    ap.add_argument("--out", default="", help="导出 CSV 路径")
    ap.add_argument("--at", default="08:30", help="loop 模式每天执行时刻 HH:MM")
    ap.add_argument("--site", dest="site_default", default="", help="默认站点(账号文件里省略站点时使用)")
    args = ap.parse_args()

    if args.action == "detect":
        if not args.site:
            print("用法: python cli.py detect https://example.com")
            return 2
        return cmd_detect(args)

    args.site = args.site_default
    args.workers = max(1, min(20, args.workers))

    if args.action == "status":
        return cmd_run(args, False)
    if args.action == "check":
        return cmd_run(args, True)

    # loop
    while True:
        cmd_run(args, True)
        hh, mm = (int(x) for x in args.at.split(":"))
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            from datetime import timedelta
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        print("下次执行 %s（等待 %.1f 小时）" % (args.at, wait / 3600))
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            print("已退出")
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("已中断")