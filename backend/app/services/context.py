"""Project and runtime context for YangJianJian."""

from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from app.config.settings import AppSettings, app_data_dir
from app.database.db import DatabaseManager
from app.ffmpeg.wrapper import FFmpegTool
from app.ui2.common import BridgeError


PROJECT_FILE = ".yangjianjian-project.json"


def _safe_name(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value.strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:80] or "未命名项目"


class AppContext:
    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or AppSettings()
        self.db = DatabaseManager()
        self.ffmpeg: FFmpegTool | None = None
        self.project_id: str | None = None
        self._project_dir: Path | None = None
        self._project_meta: dict[str, Any] | None = None
        self._lock = threading.RLock()

    @property
    def project_dir(self) -> str:
        if self._project_dir is None:
            raise BridgeError("PROJECT_REQUIRED", "请先打开或新建项目")
        return str(self._project_dir)

    @property
    def project_meta(self) -> dict[str, Any]:
        if self._project_meta is None:
            raise BridgeError("PROJECT_REQUIRED", "请先打开或新建项目")
        return dict(self._project_meta)

    def ffmpeg_tool(self) -> FFmpegTool:
        if self.ffmpeg is None:
            self.ffmpeg = FFmpegTool(self.settings.get("ffmpeg_dir", ""))
        self.ffmpeg.require()
        return self.ffmpeg

    def reset_ffmpeg(self) -> None:
        self.ffmpeg = None

    def public_project(self) -> dict[str, Any] | None:
        if self._project_dir is None or self._project_meta is None:
            return None
        result = dict(self._project_meta)
        result.update(
            {
                "id": self.project_id,
                "path": str(self._project_dir),
                "database_path": str(self.db.engine.url.database),
            }
        )
        return result

    def create_project(
        self,
        parent_dir: str | Path | None,
        name: str,
        *,
        ratio: str = "9:16",
        template: str = "blank",
    ) -> dict[str, Any]:
        base = Path(
            parent_dir
            or self.settings.get("ui2_project_dir")
            or (app_data_dir() / "projects")
        ).expanduser()
        base.mkdir(parents=True, exist_ok=True)
        folder = base / _safe_name(name)
        if folder.exists() and any(folder.iterdir()):
            folder = base / f"{_safe_name(name)}-{uuid.uuid4().hex[:8]}"
        folder.mkdir(parents=True, exist_ok=False)
        project_id = uuid.uuid4().hex
        meta = {
            "id": project_id,
            "name": name.strip() or folder.name,
            "ratio": ratio,
            "template": template,
            "created_at": __import__("datetime").datetime.now().isoformat(
                timespec="seconds"
            ),
        }
        (folder / PROJECT_FILE).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.open_project(folder, name=meta["name"])
        return self.public_project() or {}

    def open_project(
        self,
        path: str | Path,
        *,
        name: str = "",
        remember_recent: bool = True,
    ) -> dict[str, Any]:
        candidate = Path(path).expanduser().resolve()
        if candidate.is_file():
            if candidate.name == PROJECT_FILE:
                folder = candidate.parent
            elif candidate.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
                folder = candidate.parent
            else:
                raise BridgeError("PROJECT_INVALID", "请选择羊剪剪项目目录")
        else:
            folder = candidate
        if not folder.is_dir():
            raise BridgeError("PROJECT_NOT_FOUND", "项目目录不存在")
        metadata_path = folder / PROJECT_FILE
        if metadata_path.is_file():
            try:
                meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise BridgeError("PROJECT_INVALID", "项目信息无法读取") from error
        else:
            meta = {
                "id": uuid.uuid4().hex,
                "name": name or folder.name,
                "ratio": "9:16",
                "template": "blank",
            }
            metadata_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if not isinstance(meta, dict):
            raise BridgeError("PROJECT_INVALID", "项目信息格式无效")

        with self._lock:
            self.close_project()
            database_path = folder / "project.sqlite3"
            self.db.open(database_path)
            self.project_id = str(meta.get("id") or uuid.uuid4().hex)
            meta["id"] = self.project_id
            self._project_dir = folder
            self._project_meta = dict(meta)
            if remember_recent:
                self._remember_project()
        return self.public_project() or {}

    def _remember_project(self) -> None:
        current = self.public_project()
        if current is None:
            return
        rows = [
            row
            for row in self.settings.get("ui2_project_registry", [])
            if isinstance(row, dict)
            and Path(str(row.get("path", ""))).resolve() != self._project_dir
        ]
        self.settings.set("ui2_project_registry", [current, *rows][:20])
        self.settings.set("recent_projects", [current["path"], *[row["path"] for row in rows]][:20])
        self.settings.save()

    def close_project(self) -> None:
        with self._lock:
            self.db.close()
            self.project_id = None
            self._project_dir = None
            self._project_meta = None

    def ensure_default_project(self) -> dict[str, Any]:
        if self.public_project():
            return self.public_project() or {}
        registry = self.settings.get("ui2_project_registry", [])
        for row in registry:
            if not isinstance(row, dict):
                continue
            path = Path(str(row.get("path", "")))
            if path.is_dir():
                try:
                    return self.open_project(path, remember_recent=False)
                except BridgeError:
                    continue
        return self.create_project(None, "默认项目")

    def replace_project_metadata(self, values: dict[str, Any]) -> dict[str, Any]:
        if self._project_dir is None or self._project_meta is None:
            raise BridgeError("PROJECT_REQUIRED", "请先打开或新建项目")
        merged = {**self._project_meta, **values, "id": self.project_id}
        (self._project_dir / PROJECT_FILE).write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._project_meta = merged
        self._remember_project()
        return self.public_project() or {}

    def forget_project(self, path: str) -> None:
        expected = Path(path).expanduser().resolve()
        rows = [
            row
            for row in self.settings.get("ui2_project_registry", [])
            if not (
                isinstance(row, dict)
                and row.get("path")
                and Path(str(row["path"])).resolve() == expected
            )
        ]
        self.settings.set("ui2_project_registry", rows)
        self.settings.set("recent_projects", [row["path"] for row in rows])
        self.settings.save()
