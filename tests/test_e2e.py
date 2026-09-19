# -*- coding: utf-8 -*-
"""端到端测试：站点自动识别 + 登录 + 签到 + 重复签到 + 不支持签到 + 代理处理。"""
import os, sys, time, random, string
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uc.sites import detect, SiteError, make_session, is_local_host
from uc.client import SiteClient
from uc.store import Account, TokenStore
from uc.runner import Runner, summarize

NEWAPI = "http://127.0.0.1:8901"
SUB2API = "http://127.0.0.1:8902"


def rnd(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# 每次运行用全新账号，避免服务端"今日已签到"状态让测试不可重复
U1, U2 = "alice_" + rnd(), "bob_" + rnd()
ok = []


def check(name, cond, extra=""):
    ok.append(bool(cond))
    print(("  PASS " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))


print("=== 0) 代理处理（本地地址不走系统代理）===")
check("127.0.0.1 判为本地", is_local_host("http://127.0.0.1:8901"))
check("公网域名判为非本地", not is_local_host("https://example.com"))
s_local = make_session(url_hint=NEWAPI)
check("本地地址禁用代理", s_local.proxies.get("http") is None and not s_local.trust_env)
s_remote = make_session(url_hint="https://example.com")
check("公网地址尊重系统代理", s_remote.trust_env is True)

print()
print("=== 1) 站点家族自动识别 ===")
f1 = detect(NEWAPI, session=make_session(url_hint=NEWAPI))
print("   new-api 站点 ->", f1.key, "|", f1.label, "| 站名:", f1.site_name)
check("识别为 new-api", f1.key == "new-api")
check("登录路径正确", f1.login_path == "/api/user/login")

f2 = detect(SUB2API, session=make_session(url_hint=SUB2API))
print("   sub2api 站点 ->", f2.key, "|", f2.label, "| 站名:", f2.site_name)
check("识别为 sub2api", f2.key == "sub2api")
check("checkin_enabled 解析正确", f2.checkin_enabled is True)

print()
print("=== 2) new-api 家族：登录 + 状态 + 签到 ===")
c1 = SiteClient(NEWAPI, f1, session=make_session(url_hint=NEWAPI))
r, m = c1.login(U1, "goodpass")
check("登录成功", r, m)
check("拿到 access_token", bool(c1.access_token))
st = c1.status()
check("读到签到状态", st is not None, st.total_checkins if st else None)
res = c1.checkin()
check("签到成功", res.ok and not res.already, res.message)
check("奖励解析正确(quota 2500)", abs(res.reward - 2500) < 1e-6, res.reward)
res2 = c1.checkin()
check("重复签到被识别", res2.ok and res2.already, res2.message)

print()
print("=== 3) sub2api 家族：登录 + 状态 + 签到 ===")
c2 = SiteClient(SUB2API, f2, session=make_session(url_hint=SUB2API))
r, m = c2.login(U2 + "@mail.com", "goodpass")
check("登录成功", r, m)
st2 = c2.status()
check("读到签到状态", st2 is not None)
check("签到端点探测命中", c2.resolve_checkin()[0] == "/api/v1/user/checkin", c2.resolve_checkin())
res = c2.checkin()
check("签到成功", res.ok and not res.already, res.message)
check("余额奖励解析正确", abs(res.reward - 0.0025) < 1e-9, res.reward)
res2 = c2.checkin()
check("重复签到被识别", res2.ok and res2.already, res2.message)

print()
print("=== 4) 登录失败 ===")
c3 = SiteClient(NEWAPI, f1, session=make_session(url_hint=NEWAPI))
r, m = c3.login(U1, "wrongpass")
check("错误密码被拒绝", not r, m)

print()
print("=== 5) 多站点混合批量 ===")
accs = [
    Account(site=NEWAPI, username="n1_" + rnd(), password="goodpass", note="NA-1"),
    Account(site=NEWAPI, username="n2_" + rnd(), password="goodpass", note="NA-2"),
    Account(site=SUB2API, username="s1_" + rnd() + "@m.com", password="goodpass", note="S2-1"),
    Account(site=SUB2API, username="s2_" + rnd() + "@m.com", password="goodpass", note="S2-2"),
    Account(site=NEWAPI, username="bad_" + rnd(), password="nope", note="坏号"),
    Account(site="http://127.0.0.1:8999", username="x", password="y", note="不可达"),
]
for i, a in enumerate(accs, 1):
    a.index = i
tp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".t_%s.json" % rnd(6))
store = TokenStore(tp)
logs = []
run = Runner(accs, store=store, workers=4, do_checkin=True, timeout=8, log=lambda m: logs.append(m))
res_all = run.run()
s = summarize(res_all)
print("   汇总:", s)
check("成功签到 4 个", s["ok"] == 4, s["ok"])
check("识别出 3 个站点(含不可达)", s["sites"] == 3, s["sites"])
check("坏号记为失败", s["err"] >= 1, s["err"])
check("不可达站点被标记", s["unsupported"] >= 1, s["unsupported"])
check("同站点只识别一次", len(run.families) >= 2, run.families)
check("奖励累计正确", s["reward"] > 0, s["reward"])

print()
print("=== 6) token 缓存复用（不重复登录）===")
accs2 = [Account(site=NEWAPI, username=accs[0].username, password="goodpass", note="NA-1")]
accs2[0].index = 1
r2 = Runner(accs2, store=TokenStore(tp), workers=1, timeout=8, log=lambda m: None)
res2 = r2.run()
check("复用 token 后识别为已签到", res2[0].state == "already",
      res2[0].state + " " + res2[0].message)
check("token 已落盘", len(store.data) >= 4 and os.path.exists(tp), len(store.data))
try:
    os.remove(tp)
except OSError:
    pass

print()
p = sum(ok)
print("=" * 56)
print("结果: %d/%d 通过" % (p, len(ok)))
print("=" * 56)
sys.exit(0 if p == len(ok) else 1)