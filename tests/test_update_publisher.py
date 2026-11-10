"""A release must be verifiable by customers before its feed is published."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


class UpdatePublisherTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "update_publisher", ROOT / "scripts/publish-update.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)
        self.module.APP = self.app
        self.key = Ed25519PrivateKey.generate()
        self.public = base64.b64encode(
            self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()
        (self.app / "update-channel.json").write_text(json.dumps({
            "schema": 1, "channel": "stable", "publicKey": self.public,
            "manifestUrl": "https://github.com/example/editor/releases/latest/download/latest.json",
        }), encoding="utf8")
        self.private = self.app / "private.key"
        self.write_key(self.key)
        self.installer = self.app / "setup.exe"
        self.installer.write_bytes(b"MZ" + b"release-test" * 100)
        self.args = types.SimpleNamespace(
            installer=str(self.installer), version="2026.11.10.1",
            private_key=str(self.private), url="https://github.com/example/editor/releases/download/v2026.11.10.1",
            notes="Release validation", notes_file="", out=str(self.app / "out"),
            app_root=str(self.app),
        )

    def write_key(self, key):
        self.private.write_text(base64.b64encode(key.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )).decode(), encoding="ascii")

    def test_different_publisher_key_does_not_create_an_unusable_release(self):
        self.write_key(Ed25519PrivateKey.generate())
        with self.assertRaises(SystemExit):
            self.module.publish(self.args)
        self.assertFalse((self.app / "out/latest.json").exists())

    def test_package_on_another_origin_is_rejected_before_publication(self):
        self.args.url = "https://downloads.example.org/release"
        with self.assertRaises(SystemExit):
            self.module.publish(self.args)
        self.assertFalse((self.app / "out/latest.json").exists())

    def test_non_windows_download_is_never_offered_as_an_installer(self):
        self.installer.write_bytes(b"<html>download failed</html>")
        with self.assertRaises(SystemExit):
            self.module.publish(self.args)

    def test_signed_release_round_trips_through_the_customer_verifier(self):
        from app_updates import UpdateService
        (self.app / "app-version.json").write_text(
            '{"version":"2026.10.27.1"}', encoding="utf8"
        )
        self.module.publish(self.args)
        envelope = json.loads((self.app / "out/latest.json").read_text("utf8"))
        verified = UpdateService(self.app)._verified_manifest(envelope)
        self.assertEqual(verified["version"], "2026.11.10.1")
        self.assertEqual(verified["size"], 1202)
        envelope["payload"]["notes"] = "Tampered after signing"
        with self.assertRaises(ValueError):
            UpdateService(self.app)._verified_manifest(envelope)


if __name__ == "__main__":
    unittest.main()
