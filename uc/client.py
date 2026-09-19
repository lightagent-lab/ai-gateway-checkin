# -*- coding: utf-8 -*-
"""站点客户端：登录、查状态、签到，含 sub2api 签到路径自动探测。"""

from __future__ import annotations

import time
from typing import Any, Optional

import requests

from .crypto_util import build_login_payload
from .sites import (
    Family,
    CheckinInfo,
    CheckinResult,
    _int,
    _json,
    _num,
    make_session,
    normalize_base,
)

# sub2api 二开常见的签到路径候选（签到是各站自行扩展的，故需探测）
SUB2API_CHECKIN_CANDIDATES = [
    ("/user/checkin", "/user/checkin"),
    ("/user/check-in", "/user/check-in"),
    ("/user/daily-checkin", "/user/daily-checkin"),
    ("/checkin", "/checkin"),
    ("/user/sign-in", "/user/sign-in"),
    ("/user/signin", "/user/signin"),
    ("/user/daily", "/user/daily"),
    ("/user/reward/checkin", "/user/reward/checkin"),
]

# 这些字段出现即说明该响应是「签到状态」结构
_STATUS_MARKERS = (
    "checked_in_today", "can_checkin", "total_checkins", "checkin_dates",
    "total_balance_awarded", "checkin_count", "total_quota", "last_checkin",
)


class SiteClient:
    """一个站点加一个账号的会话。"""

    def __init__(self, base_url, family, session=None, timeout=25):
        self.base = normalize_base(base_url)
        self.family = family
        self.timeout = timeout
        self.s = session or make_session()
        self.s.headers.setdefault("Origin", self.base)

        self.access_token = None
        self.refresh_token = None
        self.expire_at = 0.0
        self.user_label = ""
        self._checkin_paths = None
        self._probe_log = []

    # ---------------- 底层请求 ----------------
    def _req(self, method, path, json_body=None, params=None, auth=True,
             retry=3, allow_redirect=True):
        url = self.base + path
        headers = {}
        if auth and self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        last = (0, {"message": "未执行"})

        for attempt in range(1, retry + 1):
            try:
                r = self.s.request(method, url, json=json_body, params=params,
                                   headers=headers, timeout=self.timeout,
                                   allow_redirects=allow_redirect)
            except requests.RequestException as exc:
                last = (0, {"message": "网络错误: " + exc.__class__.__name__})
                time.sleep(1.2 * attempt)
                continue

            body = _json(r)
            if body is None:
                body = {"_text": r.text[:300], "_status": r.status_code}

            if r.status_code == 401 and auth and self.refresh_token and attempt < retry:
                if self.refresh():
                    headers["Authorization"] = "Bearer " + self.access_token
                    continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retry:
                last = (r.status_code, body)
                time.sleep(1.8 * attempt)
                continue
            return r.status_code, body

        return last

    # ---------------- 响应判定 ----------------
    def _ok(self, body):
        """同时兼容 {code:0} 与 {success:true} 两种信封。"""
        if not isinstance(body, dict):
            return False
        if "success" in body:
            return bool(body.get("success"))
        if "code" in body:
            c = body.get("code")
            return c == 0 or c == 200 or c == "0"
        return False

    def _payload(self, body):
        if isinstance(body, dict) and "data" in body:
            return body.get("data")
        return body

    def _err(self, body, fallback="未知错误"):
        if isinstance(body, dict):
            for k in ("message", "msg", "error", "detail"):
                if body.get(k):
                    return str(body[k])
            txt = body.get("_text")
            if txt:
                return str(txt)[:150]
        if isinstance(body, str) and body:
            return body[:150]
        return fallback

    # ---------------- 登录 ----------------
    def login(self, username, password):
        if self.family.key == "new-api":
            return self._login_newapi(username, password)
        return self._login_sub2api(username, password)

    def _login_newapi(self, username, password):
        key_info = None
        try:
            code, body = self._req("GET", "/api/user/login/encryption-key",
                                   auth=False, retry=1)
            data = self._payload(body)
            if isinstance(data, dict) and data.get("enabled"):
                key_info = data
        except Exception:
            pass

        payload = build_login_payload(username, password, key_info)
        code, body = self._req("POST", self.family.login_path,
                               json_body=payload, auth=False)
        if code != 200:
            return False, "HTTP " + str(code) + ": " + self._err(body)

        data = self._payload(body)
        if isinstance(data, dict) and data.get("require_2fa"):
            return False, "该账号开启了二次验证(2FA)，本工具暂不支持"

        token = None
        if isinstance(data, dict):
            token = data.get("access_token") or data.get("token")
        if not self._ok(body) or not token:
            return False, self._err(body, "登录失败")

        self.access_token = token
        if isinstance(data, dict):
            self.refresh_token = data.get("refresh_token") or None
            exp = data.get("expires_in") or data.get("access_expires_at")
            if isinstance(exp, (int, float)) and exp > 1e9:
                self.expire_at = float(exp)
            elif isinstance(exp, (int, float)):
                self.expire_at = time.time() + float(exp)
            else:
                self.expire_at = time.time() + 3600
            u = data.get("user") or {}
            if isinstance(u, dict):
                self.user_label = str(u.get("username") or u.get("email") or "")
        return True, "登录成功"

    def _login_sub2api(self, username, password):
        payload = {"email": username, "password": password}
        code, body = self._req("POST", self.family.login_path,
                               json_body=payload, auth=False)
        if code != 200:
            return False, "HTTP " + str(code) + ": " + self._err(body)

        data = self._payload(body)
        if not isinstance(data, dict) or not data.get("access_token"):
            return False, self._err(body, "登录失败")

        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token") or None
        exp = _num(data.get("expires_in"), 3600)
        self.expire_at = time.time() + (exp if exp > 0 else 3600)
        u = data.get("user") or {}
        if isinstance(u, dict):
            self.user_label = str(u.get("email") or u.get("username") or "")
        return True, "登录成功"

    def refresh(self):
        path = self.family.refresh_path
        if not path or not self.refresh_token:
            return False
        payload = {"refresh_token": self.refresh_token}
        code, body = self._req("POST", path, json_body=payload,
                               auth=False, retry=1)
        data = self._payload(body)
        if code == 200 and isinstance(data, dict) and data.get("access_token"):
            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token") or self.refresh_token
            self.expire_at = time.time() + _num(data.get("expires_in"), 3600)
            return True
        return False

    # ---------------- 探测签到端点 ----------------
    def _looks_like_status(self, data):
        if not isinstance(data, dict):
            return False
        for k in _STATUS_MARKERS:
            if k in data:
                return True
        return False

    def resolve_checkin(self):
        """返回 (status_path, claim_path)；探测失败返回 (None, None)。"""
        if self._checkin_paths is not None:
            return self._checkin_paths

        fam = self.family
        if fam.key == "new-api":
            code, body = self._req("GET", "/api/user/checkin", retry=1)
            data = self._payload(body)
            if isinstance(data, dict) and data.get("enabled") is False:
                self._probe_log.append("站点返回 enabled=false，未开启签到")
                self._checkin_paths = (None, None)
                return self._checkin_paths
            self._checkin_paths = ("/api/user/checkin", "/api/user/checkin")
            return self._checkin_paths

        prefix = fam.api_prefix
        for status_p, claim_p in SUB2API_CHECKIN_CANDIDATES:
            path = prefix + status_p
            code, body = self._req("GET", path, retry=1)
            self._probe_log.append("GET " + path + " -> " + str(code))
            if code in (404, 405):
                continue
            data = self._payload(body)
            if self._looks_like_status(data):
                self._checkin_paths = (path, prefix + claim_p)
                self._probe_log.append("命中签到端点: " + path)
                return self._checkin_paths
            if code == 200 and isinstance(data, dict) and data:
                self._checkin_paths = (path, prefix + claim_p)
                self._probe_log.append("命中签到端点(弱特征): " + path)
                return self._checkin_paths

        self._checkin_paths = (None, None)
        return self._checkin_paths

    @property
    def probe_log(self):
        return list(self._probe_log)

    # ---------------- 状态 ----------------
    def status(self):
        status_path, _ = self.resolve_checkin()
        if not status_path:
            return None

        params = {"month": time.strftime("%Y-%m")}
        if self.family.key != "new-api":
            params["timezone"] = "Asia/Shanghai"

        code, body = self._req("GET", status_path, params=params, retry=1)
        if code != 200 or not self._ok(body):
            return None

        data = self._payload(body) or {}
        if not isinstance(data, dict):
            return None
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else data

        info = CheckinInfo(raw=data)
        info.checked_in_today = bool(
            stats.get("checked_in_today", stats.get("checked_today", False))
        )
        info.total_checkins = _int(
            stats.get("total_checkins", stats.get("checkin_count", 0))
        )
        info.month_checkins = _int(stats.get("checkin_count", 0))
        info.total_reward = _num(
            stats.get("total_balance_awarded",
                      stats.get("total_quota", stats.get("total_reward", 0)))
        )
        if "can_checkin" in stats:
            info.can_checkin = bool(stats.get("can_checkin"))
        else:
            info.can_checkin = not info.checked_in_today
        info.message = str(data.get("message") or "")
        return info

    # ---------------- 签到 ----------------
    def checkin(self):
        status_path, claim_path = self.resolve_checkin()
        if not claim_path:
            return CheckinResult(ok=False, message="该站点未提供签到接口（未检测到签到功能）")

        code, body = self._req("POST", claim_path, json_body=None, retry=3)
        data = self._payload(body)
        res = CheckinResult(raw=body if isinstance(body, dict) else {})

        msg = self._err(body, "")
        if code == 200 and self._ok(body):
            res.ok = True
            if isinstance(data, dict):
                for k in ("balance_awarded", "quota_awarded", "reward",
                          "amount", "points_awarded", "quota"):
                    if data.get(k) is not None:
                        res.reward = _num(data.get(k))
                        break
            res.message = msg or "签到成功"
            return res

        low = (msg or "").lower()
        if any(t in msg for t in ("已签到", "已经签到", "重复签到")) or \
           any(t in low for t in ("already", "duplicate", "has checked")):
            res.ok = True
            res.already = True
            res.message = msg or "今日已签到"
            return res

        res.message = msg or ("签到失败 (HTTP " + str(code) + ")")
        return res