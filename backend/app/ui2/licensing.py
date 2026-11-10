"""Local account authentication for the public YangJianJian build."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

from app.ui2.common import BridgeError
from public_account import AccountError, LocalAccountStore


PUBLIC_ACTIONS = {
    "app.bootstrap",
    "app.getLicense",
    "app.shutdown",
    "license.login",
    "license.logout",
}


def _password_matches(password: str, configured_hash: str, plaintext: str) -> bool:
    if configured_hash:
        if configured_hash.startswith("sha256:"):
            actual = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(actual, configured_hash[7:].lower())
        if configured_hash.startswith("pbkdf2_sha256$"):
            try:
                _, iterations, salt, expected = configured_hash.split("$", 3)
                actual = hashlib.pbkdf2_hmac(
                    "sha256",
                    password.encode("utf-8"),
                    base64.urlsafe_b64decode(salt + "=" * (-len(salt) % 4)),
                    int(iterations),
                )
                encoded = base64.urlsafe_b64encode(actual).decode("ascii").rstrip("=")
            except (ValueError, TypeError):
                return False
            return hmac.compare_digest(encoded, expected)
        return hmac.compare_digest(
            hashlib.sha256(password.encode("utf-8")).hexdigest(),
            configured_hash.lower(),
        )
    return bool(plaintext) and hmac.compare_digest(password, plaintext)


class LicenseActions:
    def __init__(self, api):
        self.api = api
        self._active = False
        self._username = ""
        self._account_store = LocalAccountStore()

    def _configured_account(self) -> tuple[str, str, str]:
        return (
            os.environ.get("YJJ_ADMIN_USER", "").strip(),
            os.environ.get("YJJ_ADMIN_PASSWORD_HASH", "").strip(),
            os.environ.get("YJJ_ADMIN_PASSWORD", ""),
        )

    def state(self) -> dict:
        active = bool(self._active)
        return {
            "active": active,
            "required": not active,
            "status": "本地管理员已登录" if active else "需要本地账号登录",
            "plan": "本地自托管",
            "remaining": "不限" if active else "登录后可用",
            "expiration": "本地会话",
            "username": self._username if active else "",
            "firstRun": not self._account_store.configured(),
            "detail": "首次使用：输入自定账号和至少 8 位密码，点击登录即创建本地账号。"
            if not self._account_store.configured() else "账号在本机验证，升级保留。",
        }

    def authorize(self, action: str) -> None:
        if self._active or action in PUBLIC_ACTIONS:
            return
        raise BridgeError("LOGIN_REQUIRED", "请先使用本地管理员账号登录")

    def changed(self, state=None) -> None:
        self.api.emit("license.changed", state or self.state())

    def license_login(self, data):
        if not isinstance(data, dict):
            raise BridgeError("INVALID_CREDENTIALS", "账号或密码错误")
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        try:
            configured_user = self._account_store.authenticate(username, password)
        except AccountError as error:
            raise BridgeError(error.code, str(error)) from error
        self._active = True
        self._username = configured_user
        state = self.state()
        self.changed(state)
        return state

    def license_logout(self, data):
        self._active = False
        self._username = ""
        state = self.state()
        self.changed(state)
        return state
