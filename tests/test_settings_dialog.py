from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from moamong_app.llm_client import AvailableModels
from moamong_app.models import LlmSettings
from moamong_app.ui.settings_dialog import SettingsDialog


def test_settings_dialog_returns_embedding_model_from_input() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="chat-model",
            embedding_model="initial-embedding-model",
        )
    )

    dialog.embedding_model_combo.setEditText("updated-embedding-model")

    settings = dialog.to_settings()

    assert app is not None
    assert settings.embedding_model == "updated-embedding-model"


def test_settings_dialog_loads_models_into_selectable_fields() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    seen_settings: list[LlmSettings] = []

    def fake_loader(settings: LlmSettings) -> AvailableModels:
        seen_settings.append(settings)
        return AvailableModels(
            llm_models=["chat-a", "chat-b"],
            embedding_models=["embed-a", "embed-b"],
            all_models=["chat-a", "chat-b", "embed-a", "embed-b"],
        )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="chat-b",
            embedding_model="embed-b",
        ),
        model_loader=fake_loader,
    )

    dialog.load_models()

    assert app is not None
    assert seen_settings[0].base_url == "https://llm.example.test/v1"
    assert seen_settings[0].api_key == "secret-key"
    assert dialog.model_combo.currentText() == "chat-b"
    assert dialog.embedding_model_combo.currentText() == "embed-b"
    assert [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())] == ["chat-a", "chat-b"]
    assert [dialog.embedding_model_combo.itemText(i) for i in range(dialog.embedding_model_combo.count())] == ["embed-a", "embed-b"]
