"""Compatibility actions used by the recovered YangJianJian Web UI.

The installed Web UI was built against a larger protocol surface than the
video engine alone.  These project-local actions provide the small persistence
and listing contracts needed by the editor, asset library, settings panels and
task history without weakening the path and command boundaries enforced by the
video engine.
"""

from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import json
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from app.ui2.common import BridgeError


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
    ".mts",
    ".m2ts",
    ".ts",
    ".mpeg",
    ".mpg",
    ".wmv",
    ".flv",
    ".3gp",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}

DEFAULT_EDITOR_CONFIG: dict[str, Any] = {
    "ratio": "9:16",
    "resolution": "1080x1920",
    "width": 1080,
    "height": 1920,
    "fpsPreset": "30",
    "fps": 30,
    "codec": "h264",
    "hw_encode": "auto",
    "voice_id": None,
    "duration_min": 0,
    "subtitle": {
        "enabled": False,
        "language": "auto",
        "template_id": "",
    },
    "bgm": {
        "enabled": False,
        "track": "",
        "volume": 0.2,
    },
}


def _error(message: str, code: str = "COMPATIBILITY_INVALID") -> None:
    raise BridgeError(code, message)


def _database(api) -> Path:
    value = getattr(api.ctx.db, "path", None)
    if value is None:
        _error("请先打开或新建项目", "PROJECT_REQUIRED")
    path = Path(value).resolve()
    if not path.is_file():
        _error("当前项目数据库不可用", "PROJECT_REQUIRED")
    return path


def _connect(api) -> sqlite3.Connection:
    connection = sqlite3.connect(str(_database(api)), timeout=15)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS compatibility_state "
        "(namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
        "PRIMARY KEY(namespace, key))"
    )
    return connection


def _load(api, namespace: str, key: str, default):
    with api.ctx._lock:
        with closing(_connect(api)) as connection, connection:
            row = connection.execute(
                "SELECT value FROM compatibility_state WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return default


def _save(api, namespace: str, key: str, value) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    with api.ctx._lock:
        with closing(_connect(api)) as connection, connection:
            connection.execute(
                "INSERT INTO compatibility_state(namespace,key,value) VALUES(?,?,?) "
                "ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value",
                (namespace, key, encoded),
            )


def _media_kind(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return None


def _material_rows(api) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = Path(api.ctx.project_dir) / "imports" / "dropped"
    if root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file() or path.name == "upload.part" or path.is_symlink():
                continue
            kind = _media_kind(path)
            if kind is None:
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(root.resolve())
                stat = resolved.stat()
            except (OSError, ValueError):
                continue
            identity = hashlib.sha256(str(resolved).casefold().encode("utf-8")).digest()
            identifier = int.from_bytes(identity[:4], "big") & 0x7FFFFFFF
            rows.append(
                {
                    "id": identifier,
                    "filename": resolved.name,
                    "file_path": str(resolved),
                    "kind": kind,
                    "status": "ready",
                    "analysis_status": "pending",
                    "duration": 0,
                    "width": 0,
                    "height": 0,
                    "custom_start": 0,
                    "custom_end": 0,
                    "usage_count": 0,
                    "size": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(
                        timespec="seconds"
                    ),
                    "tags": [],
                    "analysis": {},
                    "timeline": [],
                    "subtitles": [],
                }
            )
    return rows


class MaterialActions:
    def __init__(self, api):
        self.api = api

    def _all(self) -> list[dict[str, Any]]:
        overrides = _load(self.api, "material", "overrides", {})
        rows = _material_rows(self.api)
        if isinstance(overrides, dict):
            for row in rows:
                override = overrides.get(str(row["id"]))
                if isinstance(override, dict):
                    row.update(override)
        return rows

    def material_getList(self, data):
        data = data if isinstance(data, dict) else {}
        kind = data.get("kind")
        search = str(data.get("search") or "").casefold()
        rows = [
            row
            for row in self._all()
            if (not kind or row.get("kind") == kind)
            and (
                not search
                or search in str(row.get("filename", "")).casefold()
                or search in str(row.get("file_path", "")).casefold()
            )
        ]
        rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
        try:
            page = max(1, int(data.get("page", 1)))
            size = min(500, max(1, int(data.get("pageSize", 40))))
        except (TypeError, ValueError):
            _error("素材分页参数无效")
        start = (page - 1) * size
        return {"items": rows[start : start + size], "total": len(rows)}

    def material_getSources(self, data):
        return self.material_getList({**(data or {}), "pageSize": 500})["items"]

    def material_getDetails(self, data):
        identifier = (data or {}).get("id")
        row = next(
            (item for item in self._all() if str(item.get("id")) == str(identifier)),
            None,
        )
        if row is None:
            _error("素材不存在或已被移除", "MATERIAL_NOT_FOUND")
        return row

    def material_getTags(self, data):
        tags = _load(self.api, "material", "tags", [])
        return tags if isinstance(tags, list) else []

    def material_update(self, data):
        data = data if isinstance(data, dict) else {}
        identifiers = data.get("ids")
        fields = data.get("fields", {})
        if not isinstance(identifiers, list) or not isinstance(fields, dict):
            _error("素材修改参数无效")
        overrides = _load(self.api, "material", "overrides", {})
        overrides = overrides if isinstance(overrides, dict) else {}
        allowed = {"filename", "custom_start", "custom_end", "tags"}
        safe = {key: value for key, value in fields.items() if key in allowed}
        for identifier in identifiers:
            overrides[str(identifier)] = {
                **(
                    overrides.get(str(identifier))
                    if isinstance(overrides.get(str(identifier)), dict)
                    else {}
                ),
                **safe,
            }
        _save(self.api, "material", "overrides", overrides)
        return True

    def material_saveTimeline(self, data):
        identifier = str((data or {}).get("id"))
        _save(self.api, "material", f"timeline:{identifier}", (data or {}).get("rows", []))
        return True

    def material_saveSubtitles(self, data):
        identifier = str((data or {}).get("id"))
        _save(
            self.api,
            "material",
            f"subtitles:{identifier}",
            (data or {}).get("rows", []),
        )
        return True

    def material_editTimeline(self, data):
        data = data if isinstance(data, dict) else {}
        identifier = str(data.get("id"))
        key = f"timeline:{identifier}"
        rows = _load(self.api, "material", key, [])
        rows = rows if isinstance(rows, list) else []
        if data.get("operation") == "delete":
            rows = [
                row
                for row in rows
                if str(row.get("id")) != str(data.get("rowId"))
            ]
            _save(self.api, "material", key, rows)
            return True
        row = {
            "id": uuid.uuid4().hex,
            "start": 0,
            "end": 0,
            "action": "",
            "tags": "",
            "weight": 1,
            "used_count": 0,
        }
        rows.append(row)
        _save(self.api, "material", key, rows)
        return row

    def material_editTag(self, data):
        if not isinstance(data, dict) or not data.get("confirmed"):
            _error("请确认标签修改", "CONFIRM_REQUIRED")
        return True


class ResourceActions:
    def __init__(self, api):
        self.api = api

    def _key(self, kind: str) -> str:
        return f"resources:{kind}"

    def _items(self, kind: str) -> list[dict[str, Any]]:
        rows = _load(self.api, "resource", self._key(kind), [])
        return rows if isinstance(rows, list) else []

    def resource_getList(self, data):
        kind = str((data or {}).get("kind") or "")
        if not kind:
            _error("资源类型不能为空")
        return self._items(kind)

    def resource_getImagesPage(self, data):
        data = data if isinstance(data, dict) else {}
        rows = [row for row in _material_rows(self.api) if row["kind"] == "image"]
        return {"items": rows, "total": len(rows)}

    def resource_save(self, data):
        data = data if isinstance(data, dict) else {}
        kind = str(data.get("kind") or "")
        fields = data.get("fields")
        if not kind or not isinstance(fields, dict):
            _error("资源保存参数无效")
        rows = self._items(kind)
        identifier = data.get("id")
        record = next(
            (row for row in rows if str(row.get("id")) == str(identifier)),
            None,
        )
        if record is None:
            numeric_ids = [
                int(row["id"])
                for row in rows
                if isinstance(row.get("id"), int)
            ]
            record = {"id": max(numeric_ids, default=0) + 1}
            rows.append(record)
        record.update(fields)
        if fields.get("is_default"):
            for row in rows:
                if row is not record:
                    row["is_default"] = False
        _save(self.api, "resource", self._key(kind), rows)
        return record["id"]

    def resource_delete(self, data):
        data = data if isinstance(data, dict) else {}
        if not data.get("confirmed"):
            _error("请确认移除该资源记录", "CONFIRM_REQUIRED")
        kind = str(data.get("kind") or "")
        rows = [
            row
            for row in self._items(kind)
            if str(row.get("id")) != str(data.get("id"))
        ]
        _save(self.api, "resource", self._key(kind), rows)
        return True

    def resource_getLanguages(self, data):
        return [
            {"id": "auto", "name": "自动识别"},
            {"id": "zh", "name": "中文"},
            {"id": "en", "name": "English"},
            {"id": "ja", "name": "日本語"},
            {"id": "ko", "name": "한국어"},
            {"id": "es", "name": "Español"},
            {"id": "fr", "name": "Français"},
            {"id": "de", "name": "Deutsch"},
            {"id": "pt", "name": "Português"},
            {"id": "ar", "name": "العربية"},
        ]

    def resource_getVoiceCatalog(self, data):
        return self._items("voice")

    def resource_previewSubtitle(self, data):
        return {"contentBase64": "", "name": "subtitle-preview.txt"}


class EditingActions:
    def __init__(self, api):
        self.api = api

    def editing_getConfig(self, data):
        config = _load(
            self.api,
            "editing",
            "default-config",
            DEFAULT_EDITOR_CONFIG,
        )
        return config if isinstance(config, dict) else dict(DEFAULT_EDITOR_CONFIG)

    def editing_saveConfig(self, data):
        config = (data or {}).get("config")
        if not isinstance(config, dict):
            _error("剪辑参数必须是对象")
        merged = {**DEFAULT_EDITOR_CONFIG, **config}
        _save(self.api, "editing", "default-config", merged)
        return merged

    def editing_getEditorState(self, data):
        data = data if isinstance(data, dict) else {}
        mode = str(data.get("mode") or "smart")
        state = _load(self.api, "editing", f"state:{mode}", None)
        if not isinstance(state, dict):
            state = {
                "templateId": "",
                "config": self.editing_getConfig({}),
                "mode": mode,
            }
        return state

    def editing_saveEditorState(self, data):
        data = data if isinstance(data, dict) else {}
        mode = str(data.get("mode") or "smart")
        config = data.get("config")
        if not isinstance(config, dict):
            _error("编辑器配置必须是对象")
        state = {
            "templateId": str(data.get("templateId") or ""),
            "config": {**DEFAULT_EDITOR_CONFIG, **config},
            "mode": mode,
        }
        _save(self.api, "editing", f"state:{mode}", state)
        return True

    def editing_getDetails(self, data):
        data = data if isinstance(data, dict) else {}
        identifier = str(data.get("id") or "")
        records = _load(self.api, "copywriting", "records", [])
        record = next(
            (
                row
                for row in records
                if isinstance(records, list) and str(row.get("id")) == identifier
            ),
            None,
        )
        if record is None:
            _error("文案不存在", "COPYWRITING_NOT_FOUND")
        return {
            "script": record,
            "rows": record.get("segments", [])
            if isinstance(record.get("segments"), list)
            else [],
        }

    def editing_replace(self, data):
        return True


class CopywritingActions:
    def __init__(self, api):
        self.api = api

    def _rows(self) -> list[dict[str, Any]]:
        rows = _load(self.api, "copywriting", "records", [])
        return rows if isinstance(rows, list) else []

    def copywriting_getList(self, data):
        search = str((data or {}).get("search") or "").casefold()
        return [
            row
            for row in self._rows()
            if not search
            or search in str(row.get("title", "")).casefold()
            or search in str(row.get("content", "")).casefold()
        ]

    def copywriting_getDetails(self, data):
        identifier = str((data or {}).get("id") or "")
        record = next(
            (row for row in self._rows() if str(row.get("id")) == identifier),
            None,
        )
        if record is None:
            _error("文案不存在", "COPYWRITING_NOT_FOUND")
        return {**record, "segments": record.get("segments", [])}

    def copywriting_save(self, data):
        data = data if isinstance(data, dict) else {}
        fields = data.get("fields")
        if not isinstance(fields, dict):
            fields = {
                key: value
                for key, value in data.items()
                if key not in {"id"}
            }
        rows = self._rows()
        identifier = data.get("id")
        record = next(
            (row for row in rows if str(row.get("id")) == str(identifier)),
            None,
        )
        if record is None:
            identifier = int(
                max(
                    (
                        int(row["id"])
                        for row in rows
                        if isinstance(row.get("id"), int)
                    ),
                    default=0,
                )
                + 1
            )
            record = {
                "id": identifier,
                "title": "未命名文案",
                "content": "",
                "status": "draft",
                "segments": [],
            }
            rows.append(record)
        record.update(fields)
        _save(self.api, "copywriting", "records", rows)
        return identifier

    def copywriting_delete(self, data):
        if not (data or {}).get("confirmed"):
            _error("请确认删除文案", "CONFIRM_REQUIRED")
        identifier = str((data or {}).get("id") or "")
        _save(
            self.api,
            "copywriting",
            "records",
            [row for row in self._rows() if str(row.get("id")) != identifier],
        )
        return True

    def copywriting_duplicate(self, data):
        source = self.copywriting_getDetails(data)
        source.pop("id", None)
        source["title"] = f"{source.get('title', '未命名文案')} 副本"
        return self.copywriting_save({"fields": source})

    def copywriting_saveSegments(self, data):
        data = data if isinstance(data, dict) else {}
        return self.copywriting_save(
            {"id": data.get("id"), "fields": {"segments": data.get("segments", [])}}
        )

    def copywriting_getImportTemplate(self, data):
        content = "\ufeff标题,正文\n示例,在这里填写文案正文\n".encode("utf-8")
        return {
            "name": "文案批量导入模板.csv",
            "filter": "CSV 文件|*.csv",
            "contentBase64": base64.b64encode(content).decode("ascii"),
        }


class VisualActions:
    def __init__(self, api):
        self.api = api

    def _templates(self, kind: str) -> list[dict[str, Any]]:
        rows = _load(self.api, "visual", f"templates:{kind}", [])
        return rows if isinstance(rows, list) else []

    def visual_getCatalog(self, data):
        kind = str((data or {}).get("kind") or "")
        if kind not in {"image", "watermark"}:
            _error("未知的视觉模板类型")
        return self._templates(kind)

    def visual_getAssets(self, data):
        rows = _load(self.api, "visual", "assets", [])
        return rows if isinstance(rows, list) else []

    def visual_getDefaults(self, data):
        defaults = _load(
            self.api,
            "visual",
            "defaults",
            {
                "global": {
                    "image_motion": {"enabled": False},
                    "watermark": {"enabled": False},
                },
                "project": {},
                "inherited": True,
            },
        )
        return defaults if isinstance(defaults, dict) else {}

    def visual_saveDefaults(self, data):
        data = data if isinstance(data, dict) else {}
        config = data.get("config")
        scope = data.get("scope", "global")
        if not isinstance(config, dict) or scope not in {"global", "project"}:
            _error("视觉默认设置参数无效")
        defaults = self.visual_getDefaults({})
        defaults[scope] = config
        defaults["inherited"] = scope == "global"
        _save(self.api, "visual", "defaults", defaults)
        return defaults

    def visual_resetProject(self, data):
        defaults = self.visual_getDefaults({})
        defaults["project"] = {}
        defaults["inherited"] = True
        _save(self.api, "visual", "defaults", defaults)
        return defaults

    def visual_getReferences(self, data):
        return []

    def visual_getVideoConfig(self, data):
        identifier = str((data or {}).get("id") or "")
        values = _load(self.api, "visual", "video-config", {})
        return values.get(identifier, {}) if isinstance(values, dict) else {}

    def visual_saveVideoConfig(self, data):
        data = data if isinstance(data, dict) else {}
        identifier = str(data.get("id") or "")
        config = data.get("config", {})
        if not identifier or not isinstance(config, dict):
            _error("单视频视觉设置参数无效")
        values = _load(self.api, "visual", "video-config", {})
        values = values if isinstance(values, dict) else {}
        values[identifier] = config
        _save(self.api, "visual", "video-config", values)
        return True

    def visual_saveTemplate(self, data):
        data = data if isinstance(data, dict) else {}
        kind = str(data.get("kind") or "")
        template = data.get("template")
        if kind not in {"image", "watermark"} or not isinstance(template, dict):
            _error("视觉模板参数无效")
        rows = self._templates(kind)
        identifier = str(template.get("id") or "")
        if not identifier:
            identifier = uuid.uuid4().hex
        value = {**template, "id": identifier}
        index = next(
            (position for position, row in enumerate(rows) if str(row.get("id")) == identifier),
            None,
        )
        if index is None:
            rows.append(value)
        else:
            rows[index] = value
        _save(self.api, "visual", f"templates:{kind}", rows)
        return value

    def visual_deleteTemplate(self, data):
        data = data if isinstance(data, dict) else {}
        if not data.get("confirmed"):
            _error("请确认删除视觉模板", "CONFIRM_REQUIRED")
        kind = str(data.get("kind") or "")
        rows = [
            row
            for row in self._templates(kind)
            if str(row.get("id")) != str(data.get("id"))
        ]
        _save(self.api, "visual", f"templates:{kind}", rows)
        return True

    def visual_importTemplate(self, data):
        data = data if isinstance(data, dict) else {}
        path = Path(str(data.get("path") or "")).expanduser()
        if not path.is_absolute() or not path.is_file() or path.stat().st_size > 2_000_000:
            _error("请选择有效的模板 JSON 文件")
        try:
            template = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            _error(f"模板文件无法读取：{error}")
        if not isinstance(template, dict):
            _error("模板文件格式无效")
        kind = str(data.get("kind") or template.get("catalog") or "watermark")
        return self.visual_saveTemplate({"kind": kind, "template": template})

    def visual_exportTemplate(self, data):
        data = data if isinstance(data, dict) else {}
        kind = str(data.get("kind") or "")
        template = next(
            (
                row
                for row in self._templates(kind)
                if str(row.get("id")) == str(data.get("id"))
            ),
            None,
        )
        if template is None:
            _error("视觉模板不存在")
        content = json.dumps(template, ensure_ascii=False, indent=2).encode("utf-8")
        return {
            "name": f"{template.get('name', 'visual-template')}.json",
            "filter": "模板 JSON|*.json",
            "contentBase64": base64.b64encode(content).decode("ascii"),
        }

    def visual_removeAsset(self, data):
        if not (data or {}).get("confirmed"):
            _error("请确认移除素材", "CONFIRM_REQUIRED")
        identifier = str((data or {}).get("id") or "")
        rows = [
            row
            for row in self.visual_getAssets({})
            if str(row.get("id")) != identifier
        ]
        _save(self.api, "visual", "assets", rows)
        return True


class HistoryActions:
    def __init__(self, api):
        self.api = api

    def _history(self):
        video = self.api.groups.get("video")
        task_center = (
            getattr(video, "_smart_helpers", {}).get("_tasks_module")
            if video is not None
            else None
        )
        if task_center is None:
            _error("成片记录服务尚未加载")
        return task_center._history()

    def history_getList(self, data):
        data = data if isinstance(data, dict) else {}
        try:
            page = max(1, int(data.get("page", 1)))
            size = min(100, max(1, int(data.get("pageSize", 30))))
        except (TypeError, ValueError):
            _error("成片记录分页参数无效")
        search = str(data.get("search") or "")
        history = self._history()
        return {
            "items": history.list(size, (page - 1) * size, search),
            "total": history.count(search),
        }

    def history_getDetails(self, data):
        identifier = str((data or {}).get("id") or "")
        return self._history().get(identifier)

    def history_getReviewDetails(self, data):
        return {**self.history_getDetails(data), "review": {}, "segments": []}

    def history_replaceReview(self, data):
        data = data if isinstance(data, dict) else {}
        identifier = str(data.get("id") or "")
        values = _load(self.api, "history", "reviews", {})
        values = values if isinstance(values, dict) else {}
        values[identifier] = data.get("review", data.get("fields", {}))
        _save(self.api, "history", "reviews", values)
        return True


class ConversationActions:
    def __init__(self, api):
        self.api = api

    def conversation_getList(self, data):
        rows = _load(self.api, "conversation", "items", [])
        return {"items": rows if isinstance(rows, list) else []}

    def conversation_create(self, data):
        rows = self.conversation_getList({})["items"]
        row = {
            "id": uuid.uuid4().hex,
            "title": "新对话",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "messages": [],
        }
        rows.insert(0, row)
        _save(self.api, "conversation", "items", rows)
        return row

    def conversation_delete(self, data):
        data = data if isinstance(data, dict) else {}
        if not data.get("confirmed"):
            _error("请确认删除对话", "CONFIRM_REQUIRED")
        identifier = str(data.get("id") or "")
        rows = [
            row
            for row in self.conversation_getList({})["items"]
            if str(row.get("id")) != identifier
        ]
        _save(self.api, "conversation", "items", rows)
        return True


class SpeechActions:
    def __init__(self, api):
        self.api = api

    def speech_getStatus(self, data):
        return {
            "available": False,
            "running": False,
            "detail": "请在设置中下载本地语音模型，或在模型连接中填写可用服务。",
        }
