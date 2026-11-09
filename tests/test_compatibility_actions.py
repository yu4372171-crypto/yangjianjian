from __future__ import annotations

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


class CompatibilityActionTests(unittest.TestCase):
    def setUp(self) -> None:
        test_root = ROOT / ".test-data"
        test_root.mkdir(exist_ok=True)
        self.temporary = Path(
            tempfile.mkdtemp(prefix="compatibility-", dir=test_root)
        )
        self.addCleanup(shutil.rmtree, self.temporary, True)
        modules = [name for name in sys.modules if name == "app" or name.startswith("app.")]
        for name in modules:
            sys.modules.pop(name, None)
        environment = {
            "YJJ_ADMIN_USER": "local-owner",
            "YJJ_ADMIN_PASSWORD": "A-test-password-123!",
        }
        patch.dict(os.environ, environment, clear=False).start()
        self.addCleanup(patch.stopall)

        from app.config.settings import AppSettings
        from app.services.context import AppContext
        from app.ui2.api import BusinessAPI

        settings = AppSettings(self.temporary / "settings.json")
        context = AppContext(settings)
        self.api = BusinessAPI(context, None, lambda _name, _data: None)
        self.addCleanup(self.api.tasks.close)
        self.api.invoke(
            "license.login",
            {"username": "local-owner", "password": "A-test-password-123!"},
        )
        self.project = context.create_project(
            self.temporary / "projects",
            "兼容接口验收",
        )

    def test_editor_resource_visual_and_copywriting_contracts(self) -> None:
        state = self.api.invoke("editing.getEditorState", {"mode": "smart"})
        self.assertEqual("9:16", state["config"]["ratio"])
        self.assertTrue(
            self.api.invoke(
                "editing.saveEditorState",
                {"mode": "smart", "templateId": "", "config": {"width": 1280}},
            )
        )
        saved = self.api.invoke("editing.getEditorState", {"mode": "smart"})
        self.assertEqual(1280, saved["config"]["width"])

        template_id = self.api.invoke(
            "resource.save",
            {"kind": "template", "fields": {"name": "竖屏 1080p"}},
        )
        self.assertIsInstance(template_id, int)
        templates = self.api.invoke("resource.getList", {"kind": "template"})
        self.assertEqual("竖屏 1080p", templates[0]["name"])

        visual = self.api.invoke(
            "visual.saveTemplate",
            {
                "kind": "image",
                "template": {"name": "缓慢推近", "category": "基础"},
            },
        )
        catalog = self.api.invoke("visual.getCatalog", {"kind": "image"})
        self.assertEqual([visual["id"]], [row["id"] for row in catalog])
        self.assertTrue(self.api.invoke("visual.getDefaults", {})["inherited"])

        copy_id = self.api.invoke(
            "copywriting.save",
            {"fields": {"title": "开场文案", "content": "第一句"}},
        )
        self.assertEqual(1, copy_id)
        rows = self.api.invoke("copywriting.getList", {})
        self.assertEqual("开场文案", rows[0]["title"])

    def test_imported_media_is_listed_and_counted(self) -> None:
        imported = (
            Path(self.project["path"])
            / "imports"
            / "dropped"
            / "fixture"
            / "sample.mp4"
        )
        imported.parent.mkdir(parents=True)
        imported.write_bytes(b"not decoded by the listing endpoint")

        listing = self.api.invoke(
            "material.getList",
            {"page": 1, "pageSize": 40, "sort": "newest"},
        )
        self.assertEqual(1, listing["total"])
        self.assertEqual(str(imported.resolve()), listing["items"][0]["file_path"])
        self.assertEqual("video", listing["items"][0]["kind"])

        dashboard = self.api.invoke("dashboard.get", {})
        self.assertEqual(1, dashboard["counts"]["videos"])


if __name__ == "__main__":
    unittest.main()
