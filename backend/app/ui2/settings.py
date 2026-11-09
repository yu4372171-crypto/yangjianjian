"""Settings and diagnostics commands used by the desktop UI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.config.settings import DEFAULTS, app_data_dir
from app.ui2.common import BridgeError


SCHEMA = [
    {"key": "ui_theme", "label": "界面主题", "group": "基础设置", "type": "select",
     "options": [
         {"label": "跟随系统", "value": "system"},
         {"label": "浅色", "value": "light"},
         {"label": "深色", "value": "dark"},
         {"label": "赛博蓝", "value": "cyber-blue"},
         {"label": "赛博青", "value": "cyber-teal"},
         {"label": "赛博紫", "value": "cyber-violet"},
     ]},
    {"key": "ui2_scale", "label": "界面缩放", "group": "基础设置", "type": "number"},
    {"key": "ffmpeg_dir", "label": "FFmpeg 目录", "group": "剪辑", "type": "text"},
    {"key": "ai_provider", "label": "AI 服务商", "group": "AI模型与识别", "type": "select"},
    {"key": "ai_api_key", "label": "API 密钥", "group": "AI模型与识别", "type": "password"},
    {"key": "ai_base_url", "label": "OpenAI 兼容接口", "group": "AI模型与识别", "type": "text"},
    {"key": "ai_llm_model", "label": "语言模型", "group": "AI模型与识别", "type": "text"},
    {"key": "ai_vision_model", "label": "视觉模型", "group": "AI模型与识别", "type": "text"},
    {"key": "local_models_dir", "label": "本地模型目录", "group": "AI下载", "type": "text"},
    {"key": "asr_models_dir", "label": "语音模型目录", "group": "AI下载", "type": "text"},
    {"key": "tts_provider", "label": "配音服务", "group": "配音", "type": "select"},
    {"key": "ai_concurrency", "label": "并发任务数", "group": "性能与缓存", "type": "number"},
]


class SettingsActions:
    def __init__(self, api):
        self.api = api
        self.ctx = api.ctx

    def get(self):
        return self.ctx.settings.snapshot()

    def settings_get(self, data):
        return self.get()

    def settings_getSchema(self, data):
        return SCHEMA

    def settings_getProviders(self, data):
        return [
            {
                "id": "mock",
                "name": "模拟模式",
                "hint": "不发送网络请求，用于本地界面和基础剪辑测试。",
                "models": [],
            },
            {
                "id": "openai",
                "name": "OpenAI 兼容协议",
                "hint": "填写服务地址、模型名和密钥。",
                "models": [],
            },
            {
                "id": "ollama",
                "name": "Ollama",
                "hint": "连接本地 Ollama 服务。",
                "models": [],
            },
        ]

    def settings_save(self, data):
        values = data.get("values", data) if isinstance(data, dict) else None
        if not isinstance(values, dict):
            raise BridgeError("SETTINGS_INVALID", "设置内容必须是对象")
        self.ctx.settings.update(values)
        self.ctx.settings.save()
        if "ffmpeg_dir" in values:
            self.ctx.reset_ffmpeg()
        return self.get()

    def settings_getCache(self, data):
        cache = app_data_dir() / "cache"
        size = 0
        if cache.is_dir():
            for path in cache.rglob("*"):
                if path.is_file():
                    try:
                        size += path.stat().st_size
                    except OSError:
                        pass
        return {"cache": size}

    def settings_clearCache(self, data):
        if not isinstance(data, dict) or not data.get("confirmed"):
            raise BridgeError("CONFIRM_REQUIRED", "请确认清理可重建缓存")
        cache = app_data_dir() / "cache"
        removed = 0
        if cache.is_dir():
            for path in cache.rglob("*"):
                if path.is_file():
                    try:
                        removed += path.stat().st_size
                        path.unlink()
                    except OSError:
                        pass
        return {"removed": removed}

    def settings_getLogs(self, data):
        folder = app_data_dir() / "logs"
        lines = []
        for path in sorted(folder.glob("*.log"))[-3:]:
            try:
                lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:])
            except OSError:
                continue
        return {"lines": lines[-1000:]}

    def settings_exportDiagnostics(self, data):
        folder = app_data_dir() / "diagnostics"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / "diagnostics.json"
        safe = {
            "version": self.api.version,
            "python": os.sys.version,
            "settings": {
                key: ("***" if "key" in key.lower() or "secret" in key.lower() else value)
                for key, value in self.get().items()
            },
        }
        output.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": str(output)}

    def settings_getAnnouncementConfig(self, data):
        return {"enabled": False, "items": []}

    def settings_fetchModels(self, data):
        raise BridgeError(
            "MODEL_DISCOVERY_REQUIRES_PROVIDER",
            "请在视频工具的模型连接窗口填写接口地址和密钥后读取模型。",
        )
