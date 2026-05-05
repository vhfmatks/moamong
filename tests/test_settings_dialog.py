from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from moamong_app.llm_client import AvailableModels, ModelTestResult
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
    seen_loader_settings: list[LlmSettings] = []
    seen_tester_settings: list[LlmSettings] = []

    def fake_loader(settings: LlmSettings) -> AvailableModels:
        seen_loader_settings.append(settings)
        return AvailableModels(
            llm_models=["chat-a", "chat-b"],
            embedding_models=["embed-a", "embed-b"],
            all_models=["chat-a", "chat-b", "embed-a", "embed-b"],
        )

    def fake_tester(settings: LlmSettings) -> ModelTestResult:
        seen_tester_settings.append(settings)
        return ModelTestResult(
            chat_model=settings.model,
            embedding_model=settings.embedding_model,
            chat_ok=True,
            embedding_ok=True,
            chat_message="Received non-empty chat response",
            embedding_message="Received 3-dimension embedding",
        )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="chat-b",
            embedding_model="embed-b",
        ),
        model_loader=fake_loader,
        model_tester=fake_tester,
    )

    dialog.load_models()

    assert app is not None
    assert seen_loader_settings[0].base_url == "https://llm.example.test/v1"
    assert seen_loader_settings[0].api_key == "secret-key"
    assert seen_tester_settings[0].model == "chat-b"
    assert seen_tester_settings[0].embedding_model == "embed-b"
    assert dialog.model_combo.currentText() == "chat-b"
    assert dialog.embedding_model_combo.currentText() == "embed-b"
    assert [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())] == ["chat-a", "chat-b"]
    assert [dialog.embedding_model_combo.itemText(i) for i in range(dialog.embedding_model_combo.count())] == ["embed-a", "embed-b"]
    assert dialog.load_models_button.text() == "Loaded 4 Models / Chat OK / Embedding OK"


def test_settings_dialog_warns_when_model_test_fails(monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    warnings: list[tuple[str, str]] = []

    def fake_loader(settings: LlmSettings) -> AvailableModels:
        return AvailableModels(
            llm_models=["chat-a"],
            embedding_models=["embed-a"],
            all_models=["chat-a", "embed-a"],
        )

    def failing_tester(settings: LlmSettings) -> ModelTestResult:
        raise RuntimeError("Chat model test failed: missing model")

    monkeypatch.setattr(
        "moamong_app.ui.settings_dialog.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="custom-chat",
            embedding_model="custom-embed",
        ),
        model_loader=fake_loader,
        model_tester=failing_tester,
    )

    dialog.load_models()

    assert app is not None
    assert warnings == [("Model Test", "Chat model test failed: missing model")]
    assert dialog.model_combo.currentText() == "custom-chat"
    assert dialog.embedding_model_combo.currentText() == "custom-embed"


def test_settings_dialog_loader_failure_after_success_clears_success_text(monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    warnings: list[tuple[str, str]] = []
    tester_calls: list[LlmSettings] = []

    def successful_loader(settings: LlmSettings) -> AvailableModels:
        return AvailableModels(
            llm_models=["chat-a", "chat-b"],
            embedding_models=["embed-a", "embed-b"],
            all_models=["chat-a", "chat-b", "embed-a", "embed-b"],
        )

    def successful_tester(settings: LlmSettings) -> ModelTestResult:
        tester_calls.append(settings)
        return ModelTestResult(
            chat_model=settings.model,
            embedding_model=settings.embedding_model,
            chat_ok=True,
            embedding_ok=True,
            chat_message="Received non-empty chat response",
            embedding_message="Received 3-dimension embedding",
        )

    def failing_loader(settings: LlmSettings) -> AvailableModels:
        raise RuntimeError("model list unavailable")

    monkeypatch.setattr(
        "moamong_app.ui.settings_dialog.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="chat-b",
            embedding_model="embed-b",
        ),
        model_loader=successful_loader,
        model_tester=successful_tester,
    )
    dialog.load_models()
    old_success_text = "Loaded 4 Models / Chat OK / Embedding OK"
    assert dialog.load_models_button.text() == old_success_text
    assert len(tester_calls) == 1

    dialog.model_loader = failing_loader
    dialog.load_models()

    assert app is not None
    assert warnings == [("Model Test", "model list unavailable")]
    assert dialog.load_models_button.text() == "Testing Models..."
    assert dialog.load_models_button.text() != old_success_text
    assert len(tester_calls) == 1


def test_settings_dialog_tester_failure_after_success_clears_success_text(monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    warnings: list[tuple[str, str]] = []

    def successful_loader(settings: LlmSettings) -> AvailableModels:
        return AvailableModels(
            llm_models=["chat-a", "chat-b"],
            embedding_models=["embed-a", "embed-b"],
            all_models=["chat-a", "chat-b", "embed-a", "embed-b"],
        )

    def successful_tester(settings: LlmSettings) -> ModelTestResult:
        return ModelTestResult(
            chat_model=settings.model,
            embedding_model=settings.embedding_model,
            chat_ok=True,
            embedding_ok=True,
            chat_message="Received non-empty chat response",
            embedding_message="Received 3-dimension embedding",
        )

    def failing_tester(settings: LlmSettings) -> ModelTestResult:
        raise RuntimeError("embedding model test failed")

    monkeypatch.setattr(
        "moamong_app.ui.settings_dialog.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="chat-b",
            embedding_model="embed-b",
        ),
        model_loader=successful_loader,
        model_tester=successful_tester,
    )
    dialog.load_models()
    old_success_text = "Loaded 4 Models / Chat OK / Embedding OK"
    assert dialog.load_models_button.text() == old_success_text

    dialog.model_tester = failing_tester
    dialog.load_models()

    assert app is not None
    assert warnings == [("Model Test", "embedding model test failed")]
    assert dialog.load_models_button.text() == "Testing Models..."
    assert dialog.load_models_button.text() != old_success_text
