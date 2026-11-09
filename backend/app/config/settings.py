"""Thread-safe JSON settings for the YangJianJian backend."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    configured = os.environ.get("AIVE_DATA_DIR") or os.environ.get("YJJ_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".yangjianjian"


DEFAULTS: dict[str, Any] = {
    "ffmpeg_dir": "",
    "ai_provider": "mock",
    "ai_api_key": "",
    "ai_base_url": "https://api.openai.com/v1",
    "ai_llm_model": "gpt-4o-mini",
    "ai_vision_model": "gpt-4o-mini",
    "ai_concurrency": 2,
    "ai_max_retries": 2,
    "ai_temperature": 0.2,
    "ai_max_tokens": 1024,
    "ai_timeout": 120,
    "ai_retries": 2,
    "local_vision_model_id": "",
    "local_text_model_id": "",
    "local_models_dir": "",
    "asr_model": "faster-whisper-base",
    "asr_models_dir": "",
    "tts_provider": "auto",
    "tts_api_key": "",
    "tts_base_url": "https://api.openai.com/v1",
    "tts_model": "tts-1",
    "tts_default_voice": "alloy",
    "ui_theme": "system",
    "ui_font_size": 13,
    "ui2_scale": 100,
    "ui2_project_dir": "",
    "ui2_project_registry": [],
    "ui2_editor_sessions": {},
    "recent_projects": [],
    "auto_scan_media": False,
    "auto_scan_interval_min": 10,
    "log_level": "INFO",
    "subtitle_style": {},
    "ai_composition_conversations": [],
    "ai_composition_active_conversation": "",
    "license_server": {
        "url": "",
        "public_key": "",
        "product_id": "YANGJIANJIAN_SOURCE",
        "center_url": "",
        "verify_interval_hours": 0,
        "offline_grace_days": 0,
        "timeout": 15,
        "retries": 0,
        "enforce": False,
        "gate_on_startup": False,
        "auto_verify_on_start": False,
        "show_startup_notice": False,
        "expiring_soon_days": 0,
    },
}


class AppSettings:
    """Simple key/value settings with atomic persistence."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else app_data_dir() / "settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(stored, dict):
            with self._lock:
                self._data.update(stored)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def save(self) -> None:
        with self._lock:
            payload = json.dumps(
                self._data,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
            try:
                for attempt in range(8):
                    try:
                        temporary.replace(self.path)
                        break
                    except PermissionError:
                        if attempt == 7:
                            # Some managed Windows folders reject rename even
                            # though replacing the file content is permitted.
                            self.path.write_text(payload, encoding="utf-8")
                            break
                        time.sleep(0.04 * (attempt + 1))
            finally:
                temporary.unlink(missing_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                return copy.deepcopy(self._data[key])
            if key in DEFAULTS:
                return copy.deepcopy(DEFAULTS[key])
            return default

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = copy.deepcopy(value)

    def update(self, values: dict[str, Any]) -> None:
        if not isinstance(values, dict):
            raise ValueError("设置内容必须是对象")
        with self._lock:
            for key, value in values.items():
                if not isinstance(key, str) or not key:
                    continue
                if (
                    isinstance(value, dict)
                    and isinstance(self._data.get(key), dict)
                ):
                    merged = copy.deepcopy(self._data[key])
                    merged.update(copy.deepcopy(value))
                    self._data[key] = merged
                else:
                    self._data[key] = copy.deepcopy(value)

    @property
    def recent_projects(self) -> list[str]:
        return [
            row["path"]
            for row in self.get("ui2_project_registry", [])
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        ]
