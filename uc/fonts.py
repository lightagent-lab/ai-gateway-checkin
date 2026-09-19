# -*- coding: utf-8 -*-
"""
字体加载与选择。

实测要点（Windows + Tk 8.6）：
  - PingFang SC 这个 OTF 在 Tk 里的家族名是「苹方-简」（中文名），
    不是 "PingFang SC"。直接写 "PingFang SC" 会被 Tk 静默回退到默认字体，
    而且不会报错——很难发现。
  - families() 里同时存在带 @ 前缀的竖排变体（如 @苹方-简），必须排除，
    否则可能选到竖排字体。
  - 若系统未安装该字体，可用 AddFontResourceEx(FR_PRIVATE) 私有加载，
    但必须在创建 Tk 根窗口之前调用，否则 Tk 看不到。

字体来源优先级：
  1) 配置文件里指定的 custom_font
  2) exe/脚本同目录的 assets/PingFangSC-Semibold.otf
  3) 打包进 exe 的资源（_MEIPASS）
  4) 常见下载目录
  5) 系统已安装的同类字体（回退到微软雅黑等）
"""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter.font as tkfont

ASSET_FONT_NAME = "PingFangSC-Semibold.otf"


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def _exe_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _here()


def _bundle_dir():
    """PyInstaller 解包目录。"""
    return getattr(sys, "_MEIPASS", "")


def candidate_font_files(custom: str = "") -> list:
    """按优先级返回候选字体文件路径。"""
    out = []
    if custom:
        out.append(custom)
    base = _exe_dir()
    out.extend([
        os.path.join(base, "assets", ASSET_FONT_NAME),
        os.path.join(base, ASSET_FONT_NAME),
        os.path.join(base, "fonts", ASSET_FONT_NAME),
    ])
    bd = _bundle_dir()
    if bd:
        out.extend([
            os.path.join(bd, "assets", ASSET_FONT_NAME),
            os.path.join(bd, ASSET_FONT_NAME),
        ])
    out.extend([
        os.path.join(_here(), "assets", ASSET_FONT_NAME),
        os.path.join(os.path.expanduser("~"), "Downloads", ASSET_FONT_NAME),
        os.path.join(os.path.expanduser("~"), "Downloads",
                     "Telegram Desktop", ASSET_FONT_NAME),
        r"C:\Users\Lenovo\Downloads\Telegram Desktop\PingFangSC-Semibold.otf",
        r"C:\Users\Lenovo\Downloads\PingFangSC-Semibold.otf",
    ])
    seen, res = set(), []
    for p in out:
        if not p:
            continue
        lp = os.path.normcase(os.path.abspath(p))
        if lp in seen:
            continue
        seen.add(lp)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 10240:
                res.append(p)
        except OSError:
            continue
    return res


# 按优先级排列的候选字体。
# 注意「苹方-简」是 PingFang SC 在 Tk 中的真实家族名。
PREFERRED = [
    "苹方-简",
    "PingFang SC",
    "PingFangSC-Semibold",
    "Microsoft YaHei UI",
    "微软雅黑",
    "Microsoft YaHei",
    "Noto Sans SC",
    "Source Han Sans SC",
    "思源黑体",
    "SimHei",
    "黑体",
    "SimSun",
    "宋体",
]

MONO_FALLBACK = [
    "Cascadia Mono", "Consolas", "JetBrains Mono",
    "Sarasa Mono SC", "Noto Sans Mono CJK SC", "Courier New", "Courier",
]

_resolved_family = None
_loaded_font_file = None
_load_detail = ""


def preload_font_file(path: str = "") -> bool:
    """
    在创建 Tk 根窗口之前私有加载字体文件。
    必须早于 Tk()，否则 Tk 的字体列表里看不到。
    """
    global _loaded_font_file, _load_detail
    if _loaded_font_file:
        return True
    if sys.platform != "win32":
        _load_detail = "非 Windows，跳过私有加载"
        return False

    cands = candidate_font_files(path)
    if not cands:
        _load_detail = "未找到字体文件，将使用系统字体"
        return False

    FR_PRIVATE = 0x10
    for p in cands:
        try:
            n = ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(p), FR_PRIVATE, 0)
            if n and n > 0:
                _loaded_font_file = p
                _load_detail = "已加载 %s" % os.path.basename(p)
                return True
        except Exception as exc:
            _load_detail = "加载异常: %s" % exc
    _load_detail = "字体加载失败，将使用系统字体"
    return False


def _clean(families) -> set:
    """排除 @ 开头的竖排变体。"""
    return set(f for f in families if not f.startswith("@"))


def resolve_family() -> str:
    global _resolved_family
    if _resolved_family:
        return _resolved_family
    try:
        have = _clean(tkfont.families())
    except Exception:
        return "TkDefaultFont"
    for name in PREFERRED:
        if name in have:
            _resolved_family = name
            return name
    try:
        _resolved_family = tkfont.nametofont("TkDefaultFont").actual().get("family") or "TkDefaultFont"
    except Exception:
        _resolved_family = "TkDefaultFont"
    return _resolved_family


def resolve_mono() -> str:
    try:
        have = _clean(tkfont.families())
    except Exception:
        return resolve_family()
    for name in MONO_FALLBACK:
        if name in have:
            return name
    return resolve_family()


def font(size: int = 10, weight: str = "normal", mono: bool = False) -> tuple:
    fam = resolve_mono() if mono else resolve_family()
    return (fam, size) if weight == "normal" else (fam, size, weight)


def apply_global_defaults(root) -> str:
    """统一 Tk 默认字体，让 ttk 自绘控件也一致。"""
    fam = resolve_family()
    mono = resolve_mono()
    size = 10
    targets = {
        "TkDefaultFont": (fam, size),
        "TkTextFont": (fam, size),
        "TkMenuFont": (fam, size),
        "TkHeadingFont": (fam, size),
        "TkCaptionFont": (fam, size),
        "TkSmallCaptionFont": (fam, size - 1),
        "TkIconFont": (fam, size),
        "TkTooltipFont": (fam, size - 1),
        "TkFixedFont": (mono, size),
    }
    for name, spec in targets.items():
        try:
            tkfont.nametofont(name).configure(family=spec[0], size=spec[1])
        except Exception:
            pass
    return fam


def status_text() -> str:
    fam = resolve_family()
    parts = ["UI 字体: %s" % fam]
    if _loaded_font_file:
        parts.append("字体文件: %s" % os.path.basename(_loaded_font_file))
    elif _load_detail:
        parts.append(_load_detail)
    return " | ".join(parts)


def font_available() -> bool:
    """目标字体（苹方）是否真的可用。"""
    return resolve_family() in ("苹方-简", "PingFang SC", "PingFangSC-Semibold")