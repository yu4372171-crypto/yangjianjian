"""Per-user account provisioning for the public Windows distribution.

No publisher account or password is shipped. The first successful local
login creates a salted password hash under the current user's application
data directory. Managed deployments can still supply the YJJ_ADMIN variables.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets


class AccountError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _matches(password: str, configured: str, plaintext: str) -> bool:
    if not configured:
        return bool(plaintext) and hmac.compare_digest(password.encode(), plaintext.encode())
    if configured.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, expected = configured.split("$", 3)
            iterations = int(iterations)
            if not 100000 <= iterations <= 2000000:
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), base64.urlsafe_b64decode(salt + "=" * (-len(salt) % 4)),
                iterations,
            )
            actual = base64.urlsafe_b64encode(digest).decode().rstrip("=")
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    configured = configured.removeprefix("sha256:").lower()
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), configured)


class LocalAccountStore:
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local/share")
        self.path = Path(path or os.environ.get("YJJ_ACCOUNT_FILE")
                         or base / "YangJianJian/public/account.json")

    @staticmethod
    def _environment():
        return (
            os.environ.get("YJJ_ADMIN_USER", "").strip(),
            os.environ.get("YJJ_ADMIN_PASSWORD_HASH", "").strip(),
            os.environ.get("YJJ_ADMIN_PASSWORD", ""),
        )

    def configured(self) -> bool:
        return any(self._environment()) or self.path.exists()

    def _read(self):
        try:
            record = json.loads(self.path.read_text("utf8"))
            if (
                record["schema"] != 1 or record["kdf"] != "pbkdf2_sha256"
                or not isinstance(record["username"], str)
                or not 600000 <= record["iterations"] <= 2000000
                or len(bytes.fromhex(record["salt"])) != 24
                or len(bytes.fromhex(record["digest"])) != 32
            ):
                raise ValueError("Invalid account format")
            return record
        except (ValueError, TypeError, KeyError, OSError) as error:
            raise AccountError("ACCOUNT_CONFIG_INVALID", "本地账号配置损坏，请先备份后联系维护者恢复。") from error

    def authenticate(self, username: str, password: str) -> str:
        if not isinstance(username, str) or not isinstance(password, str):
            raise AccountError("INVALID_CREDENTIALS", "请输入账号和密码。")
        username = username.strip()
        if not username or len(username) > 128 or not password or len(password) > 256:
            raise AccountError("INVALID_CREDENTIALS", "账号或密码格式不正确。")
        configured_user, password_hash, plaintext = self._environment()
        if configured_user or password_hash or plaintext:
            if not configured_user or not (password_hash or plaintext):
                raise AccountError("ACCOUNT_NOT_CONFIGURED", "管理员账号配置不完整。")
            if not (hmac.compare_digest(username.encode(), configured_user.encode())
                    and _matches(password, password_hash, plaintext)):
                raise AccountError("INVALID_CREDENTIALS", "账号或密码错误。")
            return configured_user
        if not self.path.exists():
            if len(password) < 8:
                raise AccountError("PASSWORD_TOO_SHORT", "首次创建账号请设置至少 8 位密码。")
            salt = secrets.token_bytes(24)
            record = {
                "schema": 1, "kdf": "pbkdf2_sha256", "username": username,
                "iterations": 600000, "salt": salt.hex(),
                "digest": hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000).hex(),
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("x", encoding="utf8") as stream:
                    json.dump(record, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                pass
            except OSError as error:
                raise AccountError("ACCOUNT_STORAGE_ERROR", "无法保存本地账号，请检查用户目录权限。") from error
        record = self._read()
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(record["salt"]), record["iterations"]
        )
        if not (hmac.compare_digest(username.encode(), record["username"].encode())
                and hmac.compare_digest(digest.hex(), record["digest"])):
            raise AccountError("INVALID_CREDENTIALS", "账号或密码错误。")
        return record["username"]


def install_legacy(scope: dict) -> None:
    """Adapt the maintainers' existing runtime to the public account store."""
    actions = scope["LicenseActions"]
    bridge_error = scope["BridgeError"]
    original_init = actions.__init__

    def initialize(self, api):
        original_init(self, api)
        self._public_account_store = LocalAccountStore()
        self._public_username = ""
        self._account_authenticated = False

    def state(self):
        active = self._account_authenticated is True
        first_run = not self._public_account_store.configured()
        return {
            "active": active, "required": not active,
            "status": "已登录" if active else "创建本地账号" if first_run else "请登录",
            "statusCode": "signed_in" if active else "login_required",
            "plan": "公开本地版", "remaining": "", "expiration": "",
            "detail": "首次使用：填写自定账号和至少 8 位密码，点击登录即创建本地账号。"
                      if first_run else "账号仅在本机验证，升级保留。",
            "machineId": "", "centerUrl": "", "canImport": False,
            "username": self._public_username if active else "", "firstRun": first_run,
        }

    def login(self, data):
        try:
            if not isinstance(data, dict):
                raise AccountError("INVALID_CREDENTIALS", "请输入账号和密码。")
            username = self._public_account_store.authenticate(data.get("username"), data.get("password"))
        except AccountError as error:
            raise bridge_error(error.code, str(error)) from error
        self._public_username = username
        self._account_authenticated = True
        self.changed(None)
        return self.state()

    actions.__init__ = initialize
    actions.state = state
    actions.license_login = login
    for name in ("_ACCOUNT_USERNAME", "_ACCOUNT_SALT_HEX", "_ACCOUNT_DIGEST_HEX"):
        scope[name] = ""
