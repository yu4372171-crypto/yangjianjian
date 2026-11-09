"""Project selection and metadata commands."""

from __future__ import annotations

from pathlib import Path

from app.ui2.common import BridgeError


class ProjectActions:
    def __init__(self, api):
        self.api = api
        self.ctx = api.ctx

    def project_getCurrent(self, data):
        return self.ctx.public_project()

    def project_getList(self, data):
        return self.project_getRecent(data)

    def project_getRecent(self, data):
        rows = []
        for row in self.ctx.settings.get("ui2_project_registry", []):
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                continue
            if Path(row["path"]).is_dir():
                rows.append(row)
        return rows[:20]

    def project_getDefaults(self, data):
        configured = self.ctx.settings.get("ui2_project_dir", "")
        return {
            "parent": configured or str(Path.home() / "Documents" / "YangJianJian"),
            "ratio": "9:16",
            "template": "blank",
        }

    def project_open(self, data):
        path = data.get("path") if isinstance(data, dict) else None
        if not isinstance(path, str) or not path.strip():
            raise BridgeError("PROJECT_INVALID", "请选择项目目录")
        project = self.ctx.open_project(path)
        self.api.emit("project.changed", project)
        return project

    def project_create(self, data):
        if not isinstance(data, dict):
            raise BridgeError("PROJECT_INVALID", "项目参数无效")
        name = str(data.get("name", "")).strip()
        if not name:
            raise BridgeError("PROJECT_INVALID", "请填写项目名称")
        project = self.ctx.create_project(
            data.get("path"),
            name,
            ratio=str(data.get("ratio", "9:16")),
            template=str(data.get("template", "blank")),
        )
        self.api.emit("project.changed", project)
        return project

    def project_close(self, data):
        self.ctx.close_project()
        self.api.emit("project.changed", None)
        return True

    def project_rename(self, data):
        name = str(data.get("name", "")).strip() if isinstance(data, dict) else ""
        if not name:
            raise BridgeError("PROJECT_INVALID", "请填写项目名称")
        project = self.ctx.replace_project_metadata({"name": name})
        self.api.emit("project.changed", project)
        return project

    def project_forget(self, data):
        path = data.get("path") if isinstance(data, dict) else ""
        if not isinstance(path, str) or not path:
            raise BridgeError("PROJECT_INVALID", "项目路径无效")
        self.ctx.forget_project(path)
        return True
