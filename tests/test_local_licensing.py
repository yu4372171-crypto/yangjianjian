from __future__ import annotations

import base64
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class LocalLicensingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temporary, True)
        self.apis = []
        modules = [name for name in sys.modules if name == "app" or name.startswith("app.")]
        for name in modules:
            sys.modules.pop(name, None)

    def build_api(self):
        from app.config.settings import AppSettings
        from app.services.context import AppContext
        from app.ui2.api import BusinessAPI

        settings = AppSettings(Path(self.temporary) / "settings.json")
        context = AppContext(settings)
        api = BusinessAPI(context, None, lambda _name, _data: None)
        self.apis.append(api)
        return api

    def tearDown(self) -> None:
        for api in self.apis:
            api.tasks.close()

    def test_login_is_required_and_success_activates_session(self) -> None:
        environment = {
            "YJJ_ADMIN_USER": "local-owner",
            "YJJ_ADMIN_PASSWORD": "A-test-password-123!",
        }
        with patch.dict(os.environ, environment, clear=False):
            api = self.build_api()
            initial = api.invoke("app.getLicense", {})
            self.assertFalse(initial["active"])
            self.assertTrue(initial["required"])

            active = api.invoke(
                "license.login",
                {"username": "local-owner", "password": "A-test-password-123!"},
            )
            self.assertTrue(active["active"])
            self.assertFalse(active["required"])

            logged_out = api.invoke("license.logout", {})
            self.assertFalse(logged_out["active"])
            self.assertTrue(logged_out["required"])

    def test_wrong_credentials_are_rejected_without_leaking_values(self) -> None:
        environment = {
            "YJJ_ADMIN_USER": "local-owner",
            "YJJ_ADMIN_PASSWORD": "A-test-password-123!",
        }
        with patch.dict(os.environ, environment, clear=False):
            api = self.build_api()
            with self.assertRaisesRegex(ValueError, "账号或密码错误") as raised:
                api.invoke(
                    "license.login",
                    {"username": "local-owner", "password": "wrong"},
                )
            self.assertNotIn("A-test-password-123!", str(raised.exception))
            self.assertFalse(api.licensing.state()["active"])

    def test_pbkdf2_password_hash_activates_session(self) -> None:
        password = "A-hashed-test-password-123!"
        salt = b"local-test-salt!"
        iterations = 600_000
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
        encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        environment = {
            "YJJ_ADMIN_USER": "local-owner",
            "YJJ_ADMIN_PASSWORD_HASH": (
                f"pbkdf2_sha256${iterations}${encoded_salt}${encoded_digest}"
            ),
        }
        with patch.dict(os.environ, environment, clear=False):
            api = self.build_api()
            state = api.invoke(
                "license.login",
                {"username": "local-owner", "password": password},
            )
            self.assertTrue(state["active"])
            self.assertFalse(state["required"])


if __name__ == "__main__":
    unittest.main()
