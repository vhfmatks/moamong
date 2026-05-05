from __future__ import annotations

import json
from pathlib import Path

from moamong_app.models import LlmSettings
from moamong_app.settings import default_settings_path, load_settings, save_settings


def test_default_settings_path_uses_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: Path("C:/Users/TestUser"))

    assert default_settings_path() == Path("C:/Users/TestUser") / ".moamong_product_mapper" / "settings.json"


def test_load_settings_returns_defaults_when_file_is_missing(tmp_path) -> None:
    settings = load_settings(tmp_path / "missing.json")

    assert settings == LlmSettings()


def test_load_settings_returns_defaults_for_malformed_file(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{bad json", encoding="utf-8")

    settings = load_settings(settings_path)

    assert settings == LlmSettings()


def test_save_and_load_settings_round_trip_filters_unknown_fields(tmp_path) -> None:
    settings_path = tmp_path / "nested" / "settings.json"
    settings = LlmSettings(
        base_url="https://llm.example.test/v1",
        api_key="secret-key",
        model="custom-model",
        embedding_model="custom-embedding-model",
        temperature=0.7,
    )

    returned_path = save_settings(settings, settings_path)
    saved_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    saved_payload["unknown"] = "ignored"
    settings_path.write_text(json.dumps(saved_payload), encoding="utf-8")

    loaded = load_settings(settings_path)

    assert returned_path == settings_path
    assert loaded.base_url == "https://llm.example.test/v1"
    assert loaded.api_key == "secret-key"
    assert loaded.model == "custom-model"
    assert loaded.embedding_model == "custom-embedding-model"
    assert loaded.temperature == 0.7
