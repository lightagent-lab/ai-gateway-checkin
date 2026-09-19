# -*- coding: utf-8 -*-
"""账号模型、账号文件读写、token 缓存。"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

ACCOUNTS_FILE = "accounts.txt"
TOKEN_FILE = "tokens.json"


def device_for(seed: str) -> str:
    """由账号+站点派生稳定的伪设备 ID（同一账号保持一致，不同账号互不相同）。"""
    h = hashlib.sha256(("aicheckin|" + seed.lower()).encode()).hexdigest()
    return "web-" + h[:24]


@dataclass
class Account:
    index: int = 0
    site: str = ""
    username: str = ""
    password: str = ""
    note: str = ""
    proxy: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    # 运行结果
    state: str = ""            # "" | ok | already | err | unsupported
    message: str = ""
    reward: float = 0.0
    total_checkins: int = 0
    total_reward: float = 0.0
    family: str = ""
    probe: str = ""

    @property
    def key(self) -> str:
        return (self.site.rstrip("/") + "|" + self.username).lower()

    @property
    def label(self) -> str:
        return self.note or self.username

    @property
    def device(self) -> str:
        return device_for(self.key)


def parse_line(line: str) -> Optional[Account]:
    """
    每行一个账号，支持：
        site username password
        site,username,password
        site|username|password
        username----password        （站点留空，用默认站点）
    另支持后缀备注与代理：...,note,proxy
    """
    raw = line.strip().lstrip("\ufeff")
    if not raw or raw.startswith("#"):
        return None

    sep = None
    for cand in ("----", "|", ",", "\t"):
        if cand in raw:
            sep = cand
            break
    parts = [p.strip() for p in (raw.split(sep) if sep else raw.split())] if sep else raw.split()
    parts = [p for p in parts]

    if len(parts) < 2:
        return None

    # 判断首段是否是站点（含点或 http）
    first = parts[0]
    looks_site = ("://" in first) or ("." in first and " " not in first)

    if looks_site:
        site, username, password = parts[0], parts[1], parts[2] if len(parts) > 2 else ""
        rest = parts[3:]
    else:
        site, username, password = "", parts[0], parts[1]
        rest = parts[2:]

    if not username:
        return None
    note = rest[0] if len(rest) > 0 else ""
    proxy = rest[1] if len(rest) > 1 and rest[1] else None
    return Account(site=site, username=username, password=password, note=note, proxy=proxy)


def load_accounts(path: str, default_site: str = "") -> list:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            acc = parse_line(line)
            if not acc:
                continue
            if not acc.site:
                acc.site = default_site
            if not acc.site:
                continue
            acc.index = len(out) + 1
            out.append(acc)
    return out


def dump_accounts(accounts: list, path: str) -> None:
    lines = [
        "# AI 中转站签到账号表",
        "# 格式: 站点 用户名 密码 [备注] [代理]",
        "# 例:   https://example.com  me@mail.com  mypass  小号A",
        "# 也支持逗号/竖线分隔，或 用户名----密码（站点用界面里设置的默认站点）",
    ]
    for a in accounts:
        row = [a.site, a.username, a.password]
        if a.note or a.proxy:
            row.append(a.note)
        if a.proxy:
            if not a.note:
                row.append("")
            row.append(a.proxy)
        lines.append(" ".join(row))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


class TokenStore:
    """按 站点|用户名 缓存 access/refresh token。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or TOKEN_FILE
        self._lock = threading.Lock()
        self.data = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self.data = json.load(fh)
        except Exception:
            self.data = {}

    def get(self, acc: Account) -> Optional[dict]:
        return self.data.get(acc.key)

    def put(self, acc: Account, access: str, refresh: Optional[str], expires_at: float) -> None:
        with self._lock:
            self.data[acc.key] = {
                "site": acc.site,
                "username": acc.username,
                "access_token": access,
                "refresh_token": refresh,
                "expire_at": expires_at,
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.flush()

    def flush(self) -> None:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass