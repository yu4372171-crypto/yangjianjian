"""Protocol helpers and user-facing bridge errors."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path


class BridgeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def json_value(value):
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (tuple, list, set)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if hasattr(value, "__table__"):
        return {
            column.key: json_value(getattr(value, column.key))
            for column in value.__table__.columns
        }
    return value


def parse_json(value, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default
