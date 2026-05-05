from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from moamong_app.models import ProductRow, RowProcessResult


STEP_ROWS = [
    ("search_keyword", "검색어"),
    ("coupang", "쿠팡"),
    ("naver", "네이버"),
    ("11st", "11번가"),
    ("auction", "옥션"),
    ("gmarket", "지마켓"),
    ("llm", "LLM"),
]


class ProcessingDetailDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Processing Details")
        self.setModal(False)

        self.summary_label = QLabel("No processing is running.")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)

        self.row_label = QLabel("-")
        self.product_label = QLabel("-")
        self.search_keyword_label = QLabel("-")
        self.message_label = QLabel("-")

        form = QFormLayout()
        form.addRow("Row", self.row_label)
        form.addRow("Product", self.product_label)
        form.addRow("Search keyword", self.search_keyword_label)
        form.addRow("Status", self.message_label)

        self.steps_table = QTableWidget(len(STEP_ROWS), 2)
        self.steps_table.setHorizontalHeaderLabels(["Step", "Status"])
        self.steps_table.verticalHeader().setVisible(False)
        self.steps_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.steps_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.steps_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.steps_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )

        self._step_rows_by_label: dict[str, int] = {}
        self._step_rows_by_key: dict[str, int] = {}
        for row_index, (key, label) in enumerate(STEP_ROWS):
            self._step_rows_by_key[key] = row_index
            self._step_rows_by_label[label] = row_index
            self.steps_table.setItem(row_index, 0, QTableWidgetItem(label))
            self.steps_table.setItem(row_index, 1, QTableWidgetItem("-"))

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(form)
        layout.addWidget(self.steps_table)
        self.resize(480, 360)

    def update_progress(
        self,
        *,
        current: int,
        total: int,
        row: ProductRow | None,
        result: RowProcessResult | None,
    ) -> None:
        if total <= 0:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.summary_label.setText("No processing is running.")
        else:
            safe_current = max(0, min(current, total))
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(safe_current)
            self.summary_label.setText(f"Processing row {safe_current} of {total}.")

        self.row_label.setText("-" if row is None else str(row.index + 1))
        self.product_label.setText(self._product_name(row))

        if result is None:
            self.search_keyword_label.setText("-")
            self.message_label.setText("-")
            self._set_step_statuses({})
            return

        self.search_keyword_label.setText(result.search_keyword or "-")
        self.message_label.setText(result.message or result.status.value)
        self._set_step_statuses(result.step_statuses)

    def step_status(self, label: str) -> str:
        row = self._step_rows_by_label[label]
        item = self.steps_table.item(row, 1)
        return "" if item is None else item.text()

    def _set_step_statuses(self, statuses: dict[str, str]) -> None:
        for key, row in self._step_rows_by_key.items():
            self.steps_table.setItem(row, 1, QTableWidgetItem(statuses.get(key, "-")))

    def _product_name(self, row: ProductRow | None) -> str:
        if row is None:
            return "-"
        return (
            row.text("원본상품명(참고용)")
            or row.text("상품명")
            or row.text("상품코드")
            or "-"
        )
