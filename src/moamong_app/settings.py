from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from moamong_app.models import LlmSettings


def default_settings_path() -> Path:
    return Path.home() / ".moamong_product_mapper" / "settings.json"


def load_settings(path: str | Path | None = None) -> LlmSettings:
    settings_path = Path(path) if path is not None else default_settings_path()
    if not settings_path.exists():
        return LlmSettings()

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LlmSettings()
    if not isinstance(payload, dict):
        return LlmSettings()
    field_names = {field.name for field in fields(LlmSettings)}
    settings_values: dict[str, Any] = {
        key: value for key, value in payload.items() if key in field_names
    }
    return LlmSettings(**settings_values)


def save_settings(settings: LlmSettings, path: str | Path | None = None) -> Path:
    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return settings_path
