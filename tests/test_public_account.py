from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

try:
    from public_account import AccountError, LocalAccountStore
except ImportError:
    AccountError = None
    LocalAccountStore = None


class PublicAccountTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(LocalAccountStore, "Public distribution needs a local account store")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "account.json"
        self.env = patch.dict(os.environ, {
            "YJJ_ADMIN_USER": "", "YJJ_ADMIN_PASSWORD": "", "YJJ_ADMIN_PASSWORD_HASH": ""
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_first_login_creates_only_salted_hash_and_survives_restart(self):
        store = LocalAccountStore(self.path)
        self.assertFalse(store.configured())
        self.assertEqual("creator", store.authenticate("creator", "Choose-your-own-984!"))
        record = json.loads(self.path.read_text("utf8"))
        self.assertNotIn("Choose-your-own-984!", self.path.read_text("utf8"))
        self.assertGreaterEqual(record["iterations"], 600000)
        restarted = LocalAccountStore(self.path)
        self.assertTrue(restarted.configured())
        self.assertEqual("creator", restarted.authenticate("creator", "Choose-your-own-984!"))
        with self.assertRaises(AccountError):
            restarted.authenticate("creator", "wrong-password")
        with self.assertRaises(AccountError):
            restarted.authenticate("other", "Choose-your-own-984!")

    def test_short_password_cannot_create_an_account(self):
        with self.assertRaises(AccountError):
            LocalAccountStore(self.path).authenticate("creator", "short")
        self.assertFalse(self.path.exists())

    def test_existing_corrupt_config_fails_without_replacing_it(self):
        self.path.write_text("{broken", "utf8")
        with self.assertRaises(AccountError):
            LocalAccountStore(self.path).authenticate("creator", "Choose-your-own-984!")
        self.assertEqual("{broken", self.path.read_text("utf8"))

    def test_environment_account_does_not_create_shared_disk_credentials(self):
        with patch.dict(os.environ, {
            "YJJ_ADMIN_USER": "managed-owner", "YJJ_ADMIN_PASSWORD": "Managed-secret-984!"
        }):
            store = LocalAccountStore(self.path)
            self.assertTrue(store.configured())
            self.assertEqual("managed-owner", store.authenticate("managed-owner", "Managed-secret-984!"))
            with self.assertRaises(AccountError):
                store.authenticate("creator", "Choose-your-own-984!")
            self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
