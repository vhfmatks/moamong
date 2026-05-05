from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from moamong_app.llm_client import AvailableModels, fetch_available_models
from moamong_app.models import LlmSettings


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: LlmSettings,
        parent: QWidget | None = None,
        model_loader: Callable[[LlmSettings], AvailableModels] = fetch_available_models,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.model_loader = model_loader

        self.base_url_edit = QLineEdit(settings.base_url)
        self.api_key_edit = QLineEdit(settings.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_combo = self._model_combo(settings.model)
        self.embedding_model_combo = self._model_combo(settings.embedding_model)
        self.load_models_button = QPushButton("Test / Load Models")
        self.load_models_button.clicked.connect(self.load_models)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(settings.temperature)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 3600)
        self.timeout_spin.setValue(settings.timeout_seconds)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 20)
        self.retry_spin.setValue(settings.retry_count)

        self.category_candidate_count_spin = QSpinBox()
        self.category_candidate_count_spin.setRange(1, 100)
        self.category_candidate_count_spin.setValue(settings.category_candidate_count)

        self.confidence_threshold_spin = QDoubleSpinBox()
        self.confidence_threshold_spin.setRange(0.0, 1.0)
        self.confidence_threshold_spin.setDecimals(2)
        self.confidence_threshold_spin.setSingleStep(0.05)
        self.confidence_threshold_spin.setValue(settings.confidence_threshold)

        self.output_suffix_edit = QLineEdit(settings.output_suffix)

        form = QFormLayout()
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("Model Test", self.load_models_button)
        form.addRow("Model", self.model_combo)
        form.addRow("Embedding Model", self.embedding_model_combo)
        form.addRow("Temperature", self.temperature_spin)
        form.addRow("Timeout Seconds", self.timeout_spin)
        form.addRow("Retry Count", self.retry_spin)
        form.addRow("Category Candidate Count", self.category_candidate_count_spin)
        form.addRow("Confidence Threshold", self.confidence_threshold_spin)
        form.addRow("Output Suffix", self.output_suffix_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def to_settings(self) -> LlmSettings:
        return LlmSettings(
            base_url=self.base_url_edit.text().strip(),
            api_key=self.api_key_edit.text(),
            model=self.model_combo.currentText().strip(),
            embedding_model=self.embedding_model_combo.currentText().strip(),
            temperature=self.temperature_spin.value(),
            timeout_seconds=self.timeout_spin.value(),
            retry_count=self.retry_spin.value(),
            category_candidate_count=self.category_candidate_count_spin.value(),
            confidence_threshold=self.confidence_threshold_spin.value(),
            output_suffix=self.output_suffix_edit.text().strip(),
        )

    def load_models(self) -> None:
        try:
            models = self.model_loader(self.to_settings())
        except Exception as exc:
            QMessageBox.warning(self, "Model Test", str(exc))
            return

        self._set_combo_items(self.model_combo, models.llm_models)
        self._set_combo_items(self.embedding_model_combo, models.embedding_models)
        self.load_models_button.setText(f"Loaded {len(models.all_models)} Models")

    def _model_combo(self, value: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        if value:
            combo.addItem(value)
            combo.setCurrentText(value)
        return combo

    def _set_combo_items(self, combo: QComboBox, items: list[str]) -> None:
        current = combo.currentText().strip()
        combo.clear()
        for item in items:
            combo.addItem(item)
        if current and current not in items:
            combo.addItem(current)
        if current:
            combo.setCurrentText(current)
