# -*- coding: utf-8 -*-
"""Mock 站点：同时模拟 new-api 和 sub2api 两个家族，用于测试自动识别与签到。"""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"checked": set(), "lock": threading.Lock()}
MODE = "auto"          # auto | new-api | sub2api，由命令行参数决定

NEWAPI = {
    "version": "0.8.9", "system_name": "MockNewAPI", "turnstile_check": False,
    "turnstile_site_key": "", "password_login_encryption_enabled": False,
    "email_verification": False, "register_enabled": True,
}

APP_CONFIG = {
    "site_name": "MockSub2API", "checkin_enabled": True, "turnstile_enabled": False,
    "turnstile_site_key": "", "risk_control_enabled": False, "registration_enabled": True,
}


class H(BaseHTTPRequestHandler):
    server_version = "MockSite/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json"):
        raw = json.dumps(obj).encode() if not isinstance(obj, bytes) else obj
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def _who(self):
        """用 Authorization + 设备号区分账号。"""
        auth = self.headers.get("Authorization") or ""
        dev = self.headers.get("X-Device-Id") or ""
        return (auth.strip() or dev.strip())

    def _host(self):
        return self.headers.get("Host", "")

    # 只有 mock-sub2api 走 sub2api 家族
    def _is_sub2api(self):
        if MODE == "sub2api":
            return True
        if MODE == "new-api":
            return False
        return "sub2api" in self._host()

    def do_GET(self):
        p = self.path.split("?")[0]
        if self._is_sub2api():
            return self._sub2api_get(p)
        return self._newapi_get(p)

    def do_POST(self):
        p = self.path.split("?")[0]
        if self._is_sub2api():
            return self._sub2api_post(p)
        return self._newapi_post(p)

    # ---------------- sub2api ----------------
    def _sub2api_get(self, p):
        if p in ("/", "/checkin"):
            html = ("<!doctype html><html><head></head><body><div id=app></div>"
                    "<script>window.__APP_CONFIG__=%s;</script></body></html>"
                    % json.dumps(APP_CONFIG))
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if p == "/api/v1/user/checkin":
            if not self.headers.get("Authorization"):
                return self._send(401, {"code": "UNAUTHORIZED", "message": "Authorization header is required"})
            who = self._who()
            with STATE["lock"]:
                done = who in STATE["checked"]
            return self._send(200, {"code": 0, "data": {
                "can_checkin": True, "checked_in_today": done,
                "cumulative_recharge": 5.0, "required_recharge": 1.0,
                "total_checkins": 7, "total_balance_awarded": 0.0175,
                "point_balance": 21, "timezone": "Asia/Shanghai",
                "checkin_dates": [], "holidays": [], "claims": [],
                "weekly_count": 3, "weekly_target": 5,
                "monthly_count": 7, "monthly_target": 20}})
        return self._send(404, "404 page not found", "text/plain")

    def _sub2api_post(self, p):
        body = self._body()
        if p == "/api/v1/auth/login":
            if body.get("password") == "goodpass":
                return self._send(200, {"code": 0, "data": {
                    "access_token": "tok_" + str(abs(hash(body.get("email", ""))) % 99999),
                    "refresh_token": "ref_x", "expires_in": 3600,
                    "user": {"email": body.get("email"), "id": 1}}})
            return self._send(401, {"code": "UNAUTHORIZED", "message": "invalid email or password"})
        if p == "/api/v1/auth/refresh":
            return self._send(200, {"code": 0, "data": {
                "access_token": "tok_refreshed", "refresh_token": "ref_y", "expires_in": 3600}})
        if p == "/api/v1/user/checkin":
            if not self.headers.get("Authorization"):
                return self._send(401, {"code": "UNAUTHORIZED", "message": "Authorization header is required"})
            who = self._who()
            with STATE["lock"]:
                if who in STATE["checked"]:
                    return self._send(200, {"code": 1, "message": "今日已签到"})
                STATE["checked"].add(who)
            return self._send(200, {"code": 0, "data": {
                "success": True, "balance_awarded": 0.0025, "points_awarded": 3}})
        return self._send(404, "404 page not found", "text/plain")

    # ---------------- new-api ----------------
    def _newapi_get(self, p):
        if p == "/api/status":
            return self._send(200, NEWAPI)
        if p == "/api/user/checkin":
            if not self.headers.get("Authorization"):
                return self._send(401, {"success": False, "code": "AUTH_NOT_LOGGED_IN", "message": "未登录"})
            who = self._who()
            with STATE["lock"]:
                done = who in STATE["checked"]
            return self._send(200, {"success": True, "data": {
                "enabled": True, "min_quota": 1000, "max_quota": 5000,
                "stats": {"total_quota": 21000, "total_checkins": 7,
                          "checkin_count": 7, "checked_in_today": done,
                          "records": []}}})
        if p == "/api/user/login/encryption-key":
            return self._send(200, {"success": True, "data": {"enabled": False}})
        return self._send(404, {"success": False, "message": "not found"})

    def _newapi_post(self, p):
        body = self._body()
        if p == "/api/user/login":
            if body.get("password") == "goodpass":
                return self._send(200, {"success": True, "message": "", "data": {
                    "access_token": "ntok_" + str(abs(hash(body.get("username", ""))) % 99999),
                    "token_type": "Bearer", "access_expires_at": 99999999999,
                    "user": {"id": 1, "username": body.get("username")}}})
            return self._send(200, {"success": False, "message": "用户名或密码错误"})
        if p == "/api/user/checkin":
            if not self.headers.get("Authorization"):
                return self._send(401, {"success": False, "message": "未登录"})
            who = self._who()
            with STATE["lock"]:
                if who in STATE["checked"]:
                    return self._send(200, {"success": False, "message": "今天已经签到过了"})
                STATE["checked"].add(who)
            return self._send(200, {"success": True, "message": "签到成功",
                                    "data": {"quota_awarded": 2500, "checkin_date": "2026-09-20"}})
        return self._send(404, {"success": False, "message": "not found"})


if __name__ == "__main__":
    import sys

    port = 8901
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        MODE = sys.argv[2]
        globals()["MODE"] = MODE
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("mock site on %d mode=%s" % (port, MODE))
    srv.serve_forever()
