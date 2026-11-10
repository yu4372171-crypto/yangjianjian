"""Exercise the public channel and upgrade settings with the real updater."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app_updates import UpdateService


class PublicUpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = Path(self.directory.name)
        (self.app / "app-version.json").write_text(
            '{"version":"2026.10.27.1"}', encoding="utf8"
        )
        self.feed = "https://github.com/example/editor/releases/latest/download/latest.json"
        self.channel = {
            "schema": 1,
            "channel": "stable",
            "manifestUrl": self.feed,
            "publicKey": base64.b64encode(bytes(range(32))).decode(),
        }

    def service(self, channel=None, settings=None):
        (self.app / "update-channel.json").write_text(
            json.dumps(channel or self.channel), encoding="utf8"
        )
        if settings is not None:
            cache = self.app / "Backend/runtime/app_updates"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "settings.json").write_text(json.dumps(settings), encoding="utf8")
        return UpdateService(self.app)

    def test_public_distribution_discovers_updates_without_an_account_server(self):
        channel = json.loads((ROOT / "update-channel.json").read_text("utf8"))
        service = self.service(channel=channel)
        status = service.status()
        self.assertTrue(status["configured"])
        self.assertFalse(status["onlineConfigured"])
        self.assertEqual(service.establish_session("local-user", "local-password"), status)

    def test_saved_empty_source_does_not_disable_the_new_public_channel(self):
        service = self.service(settings={"manifestUrl": "", "autoCheck": False})
        self.assertEqual(service.status()["manifestUrl"], self.feed)
        self.assertTrue(service.status()["configured"])
        self.assertFalse(service.status()["autoCheck"])

    def test_explicit_customer_source_and_check_preference_survive_upgrade(self):
        custom = "https://updates.example.org/managed/latest.json"
        service = self.service(settings={"manifestUrl": custom, "autoCheck": False})
        self.assertEqual(service.status()["manifestUrl"], custom)
        self.assertFalse(service.status()["autoCheck"])


if __name__ == "__main__":
    unittest.main()
