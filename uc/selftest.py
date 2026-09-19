# -*- coding: utf-8 -*-
"""打包后自检：验证依赖完整性与网络功能（用于确认 exe 可用）。"""

from __future__ import annotations

import os
import sys
import traceback


def _out(lines):
    text = "\n".join(lines)
    try:
        print(text)
    except Exception:
        pass
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
        with open(os.path.join(base, "selftest.log"), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:
        pass
    return text


def selftest(target="https://ai.88wk.org"):
    """返回 (是否通过, 报告文本)。"""
    from uc import APP_NAME, __version__

    lines = ["%s v%s 自检" % (APP_NAME, __version__), "=" * 50]
    ok = True

    lines.append("[1] Python 环境")
    lines.append("    版本: %s" % sys.version.split()[0])
    lines.append("    打包运行: %s" % bool(getattr(sys, "frozen", False)))

    lines.append("[2] 核心依赖")
    for mod in ("requests", "tkinter", "json", "ssl"):
        try:
            __import__(mod)
            lines.append("    %-10s OK" % mod)
        except Exception as exc:
            ok = False
            lines.append("    %-10s 失败: %s" % (mod, exc))

    try:
        from uc.crypto_util import HAVE_CRYPTO
        lines.append("    %-10s %s" % ("cryptography", "OK" if HAVE_CRYPTO else "缺失(仅影响加密登录站点)"))
    except Exception as exc:
        lines.append("    %-10s 失败: %s" % ("cryptography", exc))

    lines.append("[3] 内部模块")
    try:
        from uc.sites import detect, make_session, is_local_host
        from uc.client import SiteClient
        from uc.runner import Runner, summarize
        from uc.store import Account, TokenStore
        lines.append("    uc.* 全部导入 OK")
    except Exception:
        ok = False
        lines.append("    导入失败:\n" + traceback.format_exc())

    lines.append("[4] 网络与站点识别 (%s)" % target)
    try:
        from uc.sites import detect, make_session
        fam = detect(target, session=make_session(url_hint=target), timeout=20)
        lines.append("    站点类型: %s" % fam.label)
        lines.append("    站点名称: %s" % (fam.site_name or "(未提供)"))
        lines.append("    签到功能: %s" % ("已开启" if fam.checkin_enabled is not False else "未开启"))
        lines.append("    识别依据: %s" % "; ".join(fam.notes))
    except Exception as exc:
        ok = False
        lines.append("    识别失败: %s: %s" % (type(exc).__name__, exc))

    lines.append("=" * 50)
    lines.append("结论: %s" % ("全部通过，可以正常使用" if ok else "存在问题，见上方日志"))
    return ok, _out(lines)


def show_message(title, text):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(title, text)
        r.destroy()
    except Exception:
        pass


def handle_cli(argv):
    """处理命令行参数，返回 True 表示已处理（无需启动 GUI）。"""
    if "--version" in argv or "-V" in argv:
        from uc import APP_NAME, __version__
        _out(["%s v%s" % (APP_NAME, __version__)])
        return True

    if "--selftest" in argv:
        target = "https://ai.88wk.org"
        for i, a in enumerate(argv):
            if a == "--selftest" and i + 1 < len(argv) and argv[i + 1].startswith("http"):
                target = argv[i + 1]
        passed, report = selftest(target)
        show_message("自检结果", report)
        return True

    if "--detect" in argv:
        i = argv.index("--detect")
        target = argv[i + 1] if i + 1 < len(argv) else ""
        if not target:
            _out(["用法: ai-gateway-checkin.exe --detect https://example.com"])
            return True
        try:
            from uc.sites import detect, make_session
            fam = detect(target, session=make_session(url_hint=target), timeout=20)
            msg = ("站点类型: %s\n站点名称: %s\n接口前缀: %s\n签到功能: %s\n人机验证: %s"
                   % (fam.label, fam.site_name or "(未提供)", fam.api_prefix,
                      "已开启" if fam.checkin_enabled is not False else "未开启",
                      "需要 Turnstile" if fam.turnstile else "无"))
        except Exception as exc:
            msg = "检测失败: %s: %s" % (type(exc).__name__, exc)
        _out([msg])
        show_message("站点检测", msg)
        return True

    if "--help" in argv or "-h" in argv:
        _out([
            "AI 中转站自动签到",
            "",
            "直接双击运行 = 打开图形界面",
            "",
            "命令行参数:",
            "  --selftest [URL]   自检（默认检测 ai.88wk.org）",
            "  --detect URL       检测指定站点类型",
            "  --version          显示版本",
        ])
        return True

    return False