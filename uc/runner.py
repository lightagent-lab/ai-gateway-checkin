# -*- coding: utf-8 -*-
"""批量执行引擎：按站点分组识别，并发登录+签到。"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .client import SiteClient
from .sites import SiteError, detect, make_session
from .store import Account, TokenStore

UNSUPPORTED = "unsupported"


class Runner:
    """一次批量任务的执行器。"""

    def __init__(
        self,
        accounts: list,
        store: Optional[TokenStore] = None,
        workers: int = 3,
        do_checkin: bool = True,
        timeout: int = 25,
        log: Optional[Callable[[str], None]] = None,
        on_account: Optional[Callable[[Account], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        self.accounts = accounts
        self.store = store or TokenStore()
        self.workers = max(1, min(20, workers))
        self.do_checkin = do_checkin
        self.timeout = timeout
        self.log = log or (lambda _m: None)
        self.on_account = on_account or (lambda _a: None)
        self.stop_event = stop_event or threading.Event()
        self._family_cache: dict[str, object] = {}
        self._lock = threading.Lock()

    # ---------------- 站点识别（同站点只识别一次） ----------------
    def _family_for(self, site: str):
        with self._lock:
            if site in self._family_cache:
                return self._family_cache[site]
        cache_key = site
        try:
            fam = detect(site, session=make_session(url_hint=site), timeout=self.timeout)
        except SiteError as exc:
            fam = exc
        with self._lock:
            self._family_cache[cache_key] = fam
        return fam

    # ---------------- 单账号 ----------------
    def run_one(self, acc: Account) -> Account:
        if self.stop_event.is_set():
            acc.state, acc.message = "err", "已取消"
            return acc

        fam = self._family_for(acc.site)
        if isinstance(fam, SiteError):
            acc.state, acc.message = UNSUPPORTED, str(fam)
            self.log("[SKIP] %s @ %s  %s" % (acc.label, acc.site, acc.message))
            return acc

        acc.family = getattr(fam, "label", "")
        client = SiteClient(
            acc.site, fam,
            session=make_session(
                proxy=acc.proxy, device_id=acc.device, url_hint=acc.site
            ),
            timeout=self.timeout,
        )

        # 1) 复用缓存 token
        cached = self.store.get(acc)
        used_cache = False
        if cached and cached.get("access_token") and cached.get("expire_at", 0) > time.time():
            client.access_token = cached["access_token"]
            client.refresh_token = cached.get("refresh_token")
            used_cache = True

        # 2) 校验 / 登录
        st = None
        if used_cache:
            st = client.status()
            if st is None and not client.refresh():
                used_cache = False
        if not used_cache or st is None:
            ok, msg = client.login(acc.username, acc.password)
            if not ok:
                acc.state, acc.message = "err", msg
                self.log("[ERR] %s @ %s  %s" % (acc.label, acc.site, msg))
                return acc
            if client.access_token:
                self.store.put(acc, client.access_token, client.refresh_token, client.expire_at)
            st = client.status()

        # 3) 站点不支持签到
        if st is None:
            _, claim = client.resolve_checkin()
            if not claim:
                acc.state = UNSUPPORTED
                acc.message = "该站点未检测到签到功能"
                acc.probe = " | ".join(client.probe_log[-3:])
                self.log("[SKIP] %s @ %s  %s" % (acc.label, acc.site, acc.message))
                return acc

        # 4) 应用状态
        if st is not None:
            acc.total_checkins = st.total_checkins
            acc.total_reward = st.total_reward
            if st.checked_in_today:
                acc.state, acc.message = "already", "今日已签到"
                self.log("[ -- ] %s @ %s  今日已签到" % (acc.label, acc.site))
                return acc
            if not st.can_checkin:
                acc.state = "err"
                acc.message = st.message or "当前不可签到"
                self.log("[ERR] %s @ %s  %s" % (acc.label, acc.site, acc.message))
                return acc

        if not self.do_checkin:
            acc.state, acc.message = "ok", "仅查询状态"
            self.log("[ q ] %s @ %s  状态正常" % (acc.label, acc.site))
            return acc

        # 5) 签到
        res = client.checkin()
        acc.probe = " | ".join(client.probe_log[-3:])
        if res.ok:
            acc.state = "already" if res.already else "ok"
            acc.reward = res.reward
            acc.message = res.message
            acc.total_checkins += 0 if res.already else 1
            acc.total_reward += res.reward
            tag = " -- " if res.already else " OK "
            self.log("[%s] %s @ %s  %s%s" % (
                tag, acc.label, acc.site, res.message,
                ("  +%.6f" % res.reward) if res.reward else ""))
        else:
            acc.state, acc.message = "err", res.message
            self.log("[ERR] %s @ %s  %s" % (acc.label, acc.site, res.message))
        return acc

    # ---------------- 批量 ----------------
    def run(self) -> list:
        results = []
        if not self.accounts:
            return results
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futs = {pool.submit(self.run_one, a): a for a in self.accounts}
            for fut in as_completed(futs):
                try:
                    acc = fut.result()
                except Exception as exc:
                    acc = futs[fut]
                    acc.state, acc.message = "err", "%s: %s" % (exc.__class__.__name__, exc)
                    self.log("[ERR] %s  %s" % (acc.label, acc.message))
                results.append(acc)
                try:
                    self.on_account(acc)
                except Exception:
                    pass
        return sorted(results, key=lambda a: a.index or 0)

    @property
    def families(self) -> dict:
        out = {}
        for k, v in self._family_cache.items():
            out[k] = getattr(v, "label", str(v))
        return out


def summarize(results: list) -> dict:
    ok = [a for a in results if a.state == "ok"]
    already = [a for a in results if a.state == "already"]
    err = [a for a in results if a.state == "err"]
    unsupported = [a for a in results if a.state == UNSUPPORTED]
    return {
        "total": len(results),
        "ok": len(ok),
        "already": len(already),
        "err": len(err),
        "unsupported": len(unsupported),
        "reward": sum(a.reward for a in ok),
        "sites": len(set(a.site for a in results if a.site)),
    }
