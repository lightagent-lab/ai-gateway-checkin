# -*- coding: utf-8 -*-
"""
new-api 家族的登录密码加密支持。

部分站点启用了 RSA 密码加密（PasswordLoginEncryptionEnabled）：
  1. GET /api/user/login/encryption-key -> {enabled, kid, public_key}
  2. 用公钥加密密码，提交 password_encrypted + encryption_key_id

服务端支持两种密文：
  - 旧版：裸 RSA-OAEP(SHA-256)，base64
  - v2  ："v2." + base64(RSA-OAEP 包裹的 32 字节 AES 密钥) + "." + base64(nonce)
          + "." + base64(AES-256-GCM 密文)
          RSA-OAEP label = b"password-v2"
          GCM AAD = b"password-v2:" + keyID

与上游 common/password_crypto.go 的 DecryptPassword 严格对应。
"""

from __future__ import annotations

import base64
import os
from typing import Optional, Tuple

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    HAVE_CRYPTO = True
except ImportError:  # pragma: no cover
    HAVE_CRYPTO = False


def encrypt_password(public_key_pem: str, key_id: str, password: str) -> Tuple[str, str]:
    """
    返回 (password_encrypted, encryption_key_id)。
    使用上游的 v2 信封格式（支持任意长度、Unicode 密码）。
    """
    if not HAVE_CRYPTO:
        raise RuntimeError("缺少 cryptography 依赖，无法加密密码：pip install cryptography")

    pub = serialization.load_pem_public_key(public_key_pem.encode())
    oaep = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=b"password-v2",
    )

    # RSA-OAEP 能包裹的长度有限，密码用 AES-256-GCM 加密，AES 密钥再用 RSA 包裹
    key = os.urandom(32)
    nonce = os.urandom(12)
    wrapped = pub.encrypt(key, oaep)
    aead = AESGCM(key)
    ct = aead.encrypt(nonce, password.encode("utf-8"), f"password-v2:{key_id}".encode())

    b64 = lambda b: base64.b64encode(b).decode()
    token = f"v2.{b64(wrapped)}.{b64(nonce)}.{b64(ct)}"
    return token, key_id


def encrypt_password_legacy(public_key_pem: str, password: str) -> str:
    """旧版格式：裸 RSA-OAEP(SHA-256)。密码过长会失败，仅作兜底。"""
    if not HAVE_CRYPTO:
        raise RuntimeError("缺少 cryptography 依赖")
    pub = serialization.load_pem_public_key(public_key_pem.encode())
    ct = pub.encrypt(
        password.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ct).decode()


def build_login_payload(
    username: str,
    password: str,
    key_info: Optional[dict],
) -> dict:
    """
    根据站点是否启用密码加密，构造 new-api 的登录请求体。
    key_info 为 /api/user/login/encryption-key 的 data 字段。
    """
    payload = {"username": username}
    if key_info and key_info.get("enabled") and key_info.get("public_key"):
        try:
            enc, kid = encrypt_password(
                key_info["public_key"], key_info.get("kid", ""), password
            )
            payload["password_encrypted"] = enc
            payload["encryption_key_id"] = kid
            return payload
        except Exception:
            pass  # 加密失败则退回明文，交给服务端判断
    payload["password"] = password
    return payload
