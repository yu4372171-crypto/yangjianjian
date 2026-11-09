from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KNOWN_LEGACY_MARKER_SHA256 = {
    "0c57eb30285c05d5f50f42fe8bca52230161e0ac6914942b0cca868cfccc5d9e",
    "8d4006eef7fcae527714a390edb4f2dc51d52e2e31d74b7aefc78c64ba0863c6",
}


class RepositoryPolicyTests(unittest.TestCase):
    def test_required_public_files_exist(self) -> None:
        required = [
            "README.md",
            "LICENSE",
            "SECURITY.md",
            "CONTRIBUTING.md",
            "THIRD_PARTY_NOTICES.md",
            "apps/desktop/YangJianJian.Desktop.csproj",
            "backend/requirements.txt",
            "webui/index.html",
        ]
        for relative in required:
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_private_runtime_artifacts_are_absent(self) -> None:
        forbidden_names = {
            "account_config.ini",
            "update-publisher-private.key",
        }
        generated_parts = {
            ".git",
            ".venv",
            "__pycache__",
            "artifacts",
            "bin",
            "obj",
            "node_modules",
            ".test-data",
        }
        forbidden_parts = {"_internal", "webview2"}
        forbidden_suffixes = {
            ".pyc",
            ".pyo",
            ".exe",
            ".dll",
            ".pdb",
            ".gguf",
            ".safetensors",
            ".onnx",
            ".pt",
            ".pth",
            ".key",
            ".pfx",
        }
        offenders: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if any(part in generated_parts for part in relative.parts):
                continue
            if (
                path.name in forbidden_names
                or any(part in forbidden_parts for part in relative.parts)
                or path.suffix.lower() in forbidden_suffixes
            ):
                offenders.append(str(relative))
        self.assertEqual([], offenders)

    def test_known_secret_markers_are_absent(self) -> None:
        patterns = [
            re.compile(
                r"-----BEGIN (?:RSA |EC |OPENSSH )?"
                + "PRIVATE KEY"
                + r"-----"
            ),
            re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}"),
            re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
            re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        ]
        text_suffixes = {
            ".cs",
            ".csproj",
            ".css",
            ".html",
            ".js",
            ".json",
            ".md",
            ".ps1",
            ".py",
            ".txt",
            ".xaml",
            ".xml",
            ".yml",
            ".yaml",
        }
        findings: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            relative = path.relative_to(ROOT)
            if ".git" in relative.parts or ".venv" in relative.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in patterns:
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
            for token in re.findall(r"[A-Za-z0-9_-]{4,}", text):
                candidates = {token, token.lower()}
                if any(
                    hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                    in KNOWN_LEGACY_MARKER_SHA256
                    for candidate in candidates
                ):
                    findings.append(
                        f"{path.relative_to(ROOT)}: known legacy credential marker"
                    )
        self.assertEqual([], findings)

    def test_webui_html_references_existing_assets(self) -> None:
        index = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        references = re.findall(r'(?:src|href)="\./([^"]+)"', index)
        self.assertGreater(len(references), 0)
        for relative in references:
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / "webui" / relative).is_file())

    def test_release_metadata_is_valid_json(self) -> None:
        for relative in ("update-channel.json", "webui/app-release.json"):
            with self.subTest(relative=relative):
                value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                self.assertIsInstance(value, dict)


if __name__ == "__main__":
    unittest.main()
