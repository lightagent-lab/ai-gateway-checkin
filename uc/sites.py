# -*- coding: utf-8 -*-
"""
站点家族自动识别 + 签到适配。

实测确认（对照上游源码）：

1) new-api 家族（Calcium-Ion/new-api、QuantumNous/new-api 及众多二开）
   - 前缀  /api
   - 响应  {"success": bool, "message": str, "data": {...}}
   - 登录  POST /api/user/login   {username, password}
           或启用加密时 {username, password_encrypted, encryption_key_id}
   - 鉴权  Authorization: Bearer <access_token>（另有 new_api_refresh cookie）
   - 状态  GET  /api/user/checkin?month=YYYY-MM
   - 签到  POST /api/user/checkin    （可能带 ?turnstile=<token>）
   - 识别  GET /api/status 返回 version/system_name/turnstile_check 等字段

2) sub2api 家族（Wei-Shaw/sub2api 及二开，签到为各站自行扩展）
   - 前缀  /api/v1
   - 响应  {"code": int, "message": str, "data": {...}}，code==0 为成功
   - 登录  POST /api/v1/auth/login {email, password} -> access_token/refresh_token
   - 鉴权  Authorization: Bearer <access_token>
   - 签到路径不固定，因此按候选表逐个探测
   - 识别  首页/签到页 HTML 内嵌 window.__APP_CONFIG__

注意：上游 sub2api 主干并没有签到功能，签到是各部署自行添加的，
所以本模块对 sub2api 家族采用「登录后探测候选路径 + 校验响应结构」的策略，
而不是写死单一路径。
"""

from __future__ import annotations

import json
import re
import ipaddress
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from urllib.parse import urlparse

import requests

from .crypto_util import build_login_payload

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class Family:
    """识别出的站点家族。"""

    key: str                      # new-api / sub2api
    label: str                    # 展示名
    api_prefix: str               # /api 或 /api/v1
    login_path: str
    refresh_path: Optional[str]
    status_path: Optional[str]    # 签到状态（已确认）
    checkin_path: Optional[str]   # 签到（已确认）
    checkin_enabled: Optional[bool] = None
    site_name: str = ""
    turnstile: bool = False
    turnstile_site_key: str = ""
    password_encryption: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class CheckinInfo:
    can_checkin: bool = True
    checked_in_today: bool = False
    total_checkins: int = 0
    total_reward: float = 0.0
    month_checkins: int = 0
    message: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class CheckinResult:
    ok: bool = False
    already: bool = False
    message: str = ""
    reward: float = 0.0
    raw: dict = field(default_factory=dict)


class SiteError(Exception):
    pass


# ------------------------------------------------------------------ 工具

def _json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def is_local_host(url: str) -> bool:
    """判断地址是否指向本机/内网（这类地址不应走代理）。"""
    try:
        host = urlparse(url if "://" in url else "http://" + url).hostname or ""
    except Exception:
        return False
    host = host.lower().strip("[]")
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if host.endswith(".local") or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def make_session(
    proxy: Optional[str] = None,
    device_id: str = "",
    url_hint: str = "",
    use_system_proxy: bool = True,
) -> requests.Session:
    """
    构造会话。

    代理策略（很重要）：
      - 显式传入 proxy            -> 用指定代理
      - url_hint 是本机/内网地址  -> 强制直连，忽略系统代理
      - 其它                      -> 尊重系统代理（很多用户靠代理才能访问站点）
    """
    s = requests.Session()
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if device_id:
        headers["X-Device-Id"] = device_id
    s.headers.update(headers)

    if proxy:
        s.proxies = {"http": proxy, "https": proxy}   # 显式代理优先
    elif url_hint and is_local_host(url_hint):
        # 本机/内网：绝不走代理，否则会被代理转发成 502/连接失败
        s.trust_env = False
        s.proxies = {"http": None, "https": None}
    elif not use_system_proxy:
        s.trust_env = False
        s.proxies = {"http": None, "https": None}
    return s


def normalize_base(url: str) -> str:
    """把用户填的各种写法归一成 https://host。"""
    url = (url or "").strip()
    if not url:
        raise SiteError("站点地址为空")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    m = re.match(r"^(https?://[^/]+)", url, re.I)
    if not m:
        raise SiteError(f"无法解析站点地址: {url}")
    return m.group(1).rstrip("/")


# ------------------------------------------------------------------ 识别

def detect(base_url: str, session: Optional[requests.Session] = None, timeout: int = 15) -> Family:
    """
    识别站点家族。先用 /api/status（new-api 特征），
    再看首页内嵌配置（sub2api 特征），最后回退到通用探测。
    """
    base = normalize_base(base_url)
    s = session or make_session(url_hint=base)
    notes: list[str] = []

    # --- 1) new-api：/api/status ---
    try:
        r = s.get(f"{base}/api/status", timeout=timeout)
        data = _json(r)
        if isinstance(data, dict) and (
            "version" in data or "system_name" in data or "turnstile_check" in data
        ):
            notes.append("命中 /api/status（new-api 特征）")
            return Family(
                key="new-api",
                label="new-api 家族",
                api_prefix="/api",
                login_path="/api/user/login",
                refresh_path="/api/user/auth/refresh",
                status_path="/api/user/checkin",
                checkin_path="/api/user/checkin",
                site_name=str(data.get("system_name") or ""),
                turnstile=bool(data.get("turnstile_check")),
                turnstile_site_key=str(data.get("turnstile_site_key") or ""),
                password_encryption=bool(data.get("password_login_encryption_enabled")),
                notes=notes,
            )
    except requests.RequestException as exc:
        notes.append(f"/api/status 请求失败: {exc.__class__.__name__}")

    # --- 2) sub2api：首页/签到页内嵌 __APP_CONFIG__ ---
    for path in ("/checkin", "/"):
        try:
            r = s.get(f"{base}{path}", timeout=timeout)
        except requests.RequestException as exc:
            notes.append(f"{path} 请求失败: {exc.__class__.__name__}")
            continue
        m = re.search(r"window\.__APP_CONFIG__\s*=\s*(\{.*?\})\s*;?\s*</script>", r.text, re.S)
        if not m:
            m = re.search(r"window\.__APP_CONFIG__\s*=\s*(\{.*?\});", r.text, re.S)
        if not m:
            continue
        try:
            cfg = json.loads(m.group(1))
        except ValueError:
            continue
        notes.append(f"命中 {path} 内嵌 __APP_CONFIG__（sub2api 特征）")
        enabled = cfg.get("checkin_enabled")
        if enabled is False:
            notes.append("站点配置里 checkin_enabled=false，该站未开启签到")
        return Family(
            key="sub2api",
            label="sub2api 家族",
            api_prefix="/api/v1",
            login_path="/api/v1/auth/login",
            refresh_path="/api/v1/auth/refresh",
            status_path="/api/v1/user/checkin",
            checkin_path="/api/v1/user/checkin",
            checkin_enabled=bool(enabled) if enabled is not None else None,
            site_name=str(cfg.get("site_name") or ""),
            turnstile=bool(cfg.get("turnstile_enabled")),
            turnstile_site_key=str(cfg.get("turnstile_site_key") or ""),
            notes=notes,
        )

    # --- 3) 回退：两边都探测一下可达性 ---
    notes.append("未命中已知特征，按通用方式尝试")
    for prefix, key, label in (("/api", "new-api", "new-api 家族(推测)"),
                               ("/api/v1", "sub2api", "sub2api 家族(推测)")):
        try:
            r = s.get(f"{base}{prefix}/status", timeout=timeout)
            if r.status_code not in (404, 502, 503):
                notes.append(f"{prefix}/status 返回 {r.status_code}")
                return Family(
                    key=key, label=label, api_prefix=prefix,
                    login_path=f"{prefix}/user/login" if key == "new-api" else f"{prefix}/auth/login",
                    refresh_path=None,
                    status_path=None, checkin_path=None, notes=notes,
                )
        except requests.RequestException:
            pass

    raise SiteError("无法识别站点类型（既不是 new-api 也不是 sub2api，或站点不可达）")
