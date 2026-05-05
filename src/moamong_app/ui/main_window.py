from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    QThread,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.category_vector_store import CategoryVectorRefreshResult, CategoryVectorStore
from moamong_app.excel_io import (
    WorkbookData,
    export_results,
    load_category_workbook,
    load_product_workbook,
)
from moamong_app.keyword_fetcher import (
    SITE_KEYWORD_COLUMNS,
    SITE_ORDER,
    SITE_STATUS_COLUMNS,
    ShoppingKeywordCollector,
    site_keyword_column,
    site_status_column,
)
from moamong_app.keyword_processor import KeywordProcessor
from moamong_app.llm_client import OpenAICompatibleClient
from moamong_app.models import Category, LlmSettings, ProductRow, RowProcessResult, RowStatus
from moamong_app.settings import load_settings, save_settings
from moamong_app.sqlite_store import SqliteStore
from moamong_app.ui.processing_detail_dialog import ProcessingDetailDialog
from moamong_app.ui.settings_dialog import SettingsDialog
from moamong_app.ui.spreadsheet_view import SpreadsheetView


SITE_COLUMN_TO_ID = {site_keyword_column(site): site for site in SITE_ORDER}
SITE_STATUS_COLUMN_TO_ID = {site_status_column(site): site for site in SITE_ORDER}
GENERATED_CELL_BRUSH = QBrush(QColor("#fff59d"))
GENERATED_TEXT_BRUSH = QBrush(QColor("#111111"))
LLM_STEP_STATUS_COLUMN = "LLM_step_status"
SEARCH_KEYWORD_COLUMN = "LLM_검색어"
SEARCH_KEYWORD_STATUS_COLUMN = "검색어_status"
GENERATED_COLUMNS = [
    "LLM_상품명",
    "LLM_키워드",
    "LLM_마이카테",
    "LLM_마이카테명",
    "LLM_confidence",
    "LLM_status",
    "LLM_review_reason",
]


class RunMode(str, Enum):
    SKIP_DONE = "skip_done"
    RUN_ALL = "run_all"


def is_row_done_for_run_mode(
    row: ProductRow,
    results_by_index: dict[int, RowProcessResult],
) -> bool:
    current = results_by_index.get(row.index)
    if current is not None and current.status is RowStatus.DONE:
        return True
    return row.text("LLM_status") == RowStatus.DONE.value


def filter_rows_for_run_mode(
    rows: list[ProductRow],
    mode: RunMode,
    results_by_index: dict[int, RowProcessResult],
) -> list[ProductRow]:
    if mode is RunMode.RUN_ALL:
        return list(rows)
    return [
        row
        for row in rows
        if not is_row_done_for_run_mode(row, results_by_index)
    ]


@dataclass(frozen=True)
class CategoryLoadResult:
    categories: list[Category]
    vector_result: CategoryVectorRefreshResult | None = None
    vector_error: str = ""


class WorkbookLoadWorker(QObject):
    progressed = Signal(str, int, int)
    loaded = Signal(str, object)
    failed = Signal(str, str)

    def __init__(
        self,
        kind: str,
        path: str | Path,
        settings: LlmSettings | None = None,
        vector_store_factory: Callable[[], CategoryVectorStore] = CategoryVectorStore,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.path = Path(path)
        self.settings = settings
        self.vector_store_factory = vector_store_factory

    def run(self) -> None:
        try:
            if self.kind == "product":
                data = load_product_workbook(
                    self.path,
                    progress_callback=lambda current, total: self.progressed.emit(
                        self.kind,
                        current,
                        total,
                    ),
                )
                self.loaded.emit(self.kind, data)
                return
            if self.kind == "category":
                categories = load_category_workbook(
                    self.path,
                    progress_callback=lambda current, total: self.progressed.emit(
                        self.kind,
                        current,
                        total,
                    ),
                )
                vector_result: CategoryVectorRefreshResult | None = None
                vector_error = ""
                if self.settings is not None:
                    try:
                        vector_result = self.vector_store_factory().refresh(
                            categories,
                            source_path=self.path,
                            settings=self.settings,
                        )
                    except Exception as exc:
                        vector_error = str(exc)
                self.loaded.emit(
                    self.kind,
                    CategoryLoadResult(
                        categories=categories,
                        vector_result=vector_result,
                        vector_error=vector_error,
                    ),
                )
                return
            raise ValueError(f"Unknown workbook load kind: {self.kind}")
        except Exception as exc:
            self.failed.emit(self.kind, str(exc))


class ProductTableModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.workbook: WorkbookData | None = None
        self.columns: list[str] = []
        self.results_by_index: dict[int, RowProcessResult] = {}

    def set_workbook(self, workbook: WorkbookData | None) -> None:
        self.beginResetModel()
        self.workbook = workbook
        self.columns = [] if workbook is None else workbook.columns + [SEARCH_KEYWORD_COLUMN] + SITE_KEYWORD_COLUMNS + [SEARCH_KEYWORD_STATUS_COLUMN] + SITE_STATUS_COLUMNS + [LLM_STEP_STATUS_COLUMN] + GENERATED_COLUMNS
        self.results_by_index = {}
        self.endResetModel()

    def clear_results(self) -> None:
        if not self.results_by_index:
            return
        self.results_by_index = {}
        if self.workbook is not None and self.rowCount() > 0:
            first_column = 0
            last_column = len(self.columns) - 1
            self.dataChanged.emit(
                self.index(0, first_column),
                self.index(self.rowCount() - 1, last_column),
            )

    def set_result(self, result: RowProcessResult) -> None:
        self.results_by_index[result.row_index] = result
        if self.workbook is None:
            return
        first_column = 0
        last_column = len(self.columns) - 1
        self.dataChanged.emit(
            self.index(result.row_index, first_column),
            self.index(result.row_index, last_column),
        )

    def set_status(self, row_index: int, status: str) -> None:
        current = self.results_by_index.get(row_index)
        self.results_by_index[row_index] = RowProcessResult(
            row_index=row_index,
            status=RowStatus.PROCESSING,
            generated=current.generated if current is not None else None,
            message=status,
            search_keyword=current.search_keyword if current is not None else "",
            category_candidates=current.category_candidates if current is not None else [],
            site_keywords=current.site_keywords if current is not None else {},
            site_errors=current.site_errors if current is not None else {},
            step_statuses=current.step_statuses if current is not None else {},
        )
        if self.workbook is not None:
            status_column = self.columns.index("LLM_status")
            self.dataChanged.emit(
                self.index(row_index, status_column),
                self.index(row_index, status_column),
            )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() or self.workbook is None:
            return 0
        return len(self.workbook.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or self.workbook is None:
            return None
        if role == Qt.ItemDataRole.BackgroundRole:
            return GENERATED_CELL_BRUSH if self._is_highlighted(index) else None
        if role == Qt.ItemDataRole.ForegroundRole:
            return GENERATED_TEXT_BRUSH if self._is_highlighted(index) else None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None

        row = self.workbook.rows[index.row()]
        column = self.columns[index.column()]
        result = self.results_by_index.get(row.index)
        value = ""
        if column in self.workbook.columns:
            value = self._source_cell_value(row, column, result)
        elif column in SITE_COLUMN_TO_ID:
            value = self._site_keyword_text(result, SITE_COLUMN_TO_ID[column])
        elif column in SITE_STATUS_COLUMN_TO_ID:
            value = self._step_status_text(result, SITE_STATUS_COLUMN_TO_ID[column])
        elif column == SEARCH_KEYWORD_STATUS_COLUMN:
            value = self._step_status_text(result, "search_keyword")
        elif column == LLM_STEP_STATUS_COLUMN:
            value = self._step_status_text(result, "llm")
        elif result is not None:
            if column == SEARCH_KEYWORD_COLUMN:
                value = result.search_keyword
            else:
                generated = result.generated
                if column == "LLM_status":
                    value = result.status.value
                elif column == "LLM_review_reason":
                    value = (
                        generated.review_reason
                        if generated is not None and generated.review_reason
                        else result.message
                    )
                elif generated is not None:
                    if column == "LLM_상품명":
                        value = generated.product_name
                    elif column == "LLM_키워드":
                        value = generated.keywords_text
                    elif column == "LLM_마이카테":
                        value = generated.mycate
                    elif column == "LLM_마이카테명":
                        value = generated.mycate_name
                    elif column == "LLM_confidence":
                        value = f"{generated.confidence:.3f}"

        if role == Qt.ItemDataRole.ToolTipRole:
            text = str(value)
            return text if len(text) > 10 or "\n" in text else None
        return value

    def _step_status_text(
        self,
        result: RowProcessResult | None,
        step: str,
    ) -> str:
        if result is None:
            return ""
        return result.step_statuses.get(step, "")

    def _source_cell_value(
        self,
        row: ProductRow,
        column: str,
        result: RowProcessResult | None,
    ) -> str:
        generated = result.generated if result is not None else None
        if generated is None:
            return row.text(column)
        if column == "상품명":
            return generated.product_name
        if column == "키워드":
            return generated.keywords_text
        if column == "마이카테" and generated.mycate.strip():
            return generated.mycate
        return row.text(column)

    def _site_keyword_text(
        self,
        result: RowProcessResult | None,
        site: str,
    ) -> str:
        if result is None:
            return ""
        keywords = result.site_keywords.get(site, [])
        text = ",".join(keyword.strip() for keyword in keywords if keyword.strip())
        if text:
            return text
        if site in result.site_errors:
            return f"오류: {result.site_errors[site]}"
        return ""

    def _is_highlighted(self, index: QModelIndex) -> bool:
        if self.workbook is None:
            return False
        row = self.workbook.rows[index.row()]
        result = self.results_by_index.get(row.index)
        if result is None:
            return False

        column = self.columns[index.column()]
        generated = result.generated
        if column in SITE_COLUMN_TO_ID:
            site = SITE_COLUMN_TO_ID[column]
            return bool(result.site_keywords.get(site) or site in result.site_errors)
        if column in SITE_STATUS_COLUMN_TO_ID or column in (SEARCH_KEYWORD_STATUS_COLUMN, LLM_STEP_STATUS_COLUMN):
            return bool(self.data(index, Qt.ItemDataRole.DisplayRole))
        if column == SEARCH_KEYWORD_COLUMN:
            return bool(result.search_keyword.strip())
        if generated is None:
            return False
        if column in ("상품명", "키워드"):
            return True
        if column == "마이카테":
            return bool(generated.mycate.strip())
        return column in GENERATED_COLUMNS

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.columns[section] if 0 <= section < len(self.columns) else ""
        return section + 1


class MainWindow(QMainWindow):
    def __init__(
        self,
        parent: QWidget | None = None,
        store: SqliteStore | None = None,
        vector_store_factory: Callable[[], CategoryVectorStore] = CategoryVectorStore,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Moamong Product Mapper")

        self.settings: LlmSettings = load_settings()
        self.store = store if store is not None else SqliteStore()
        self.vector_store_factory = vector_store_factory
        self.product_data: WorkbookData | None = None
        self.categories: list[Category] = []
        self.matcher: CategoryMatcher | None = None
        self.results: list[RowProcessResult] = []
        self.load_thread: QThread | None = None
        self.load_worker: WorkbookLoadWorker | None = None
        self.processing_detail_dialog: ProcessingDetailDialog | None = None
        self._processing_detail_state: tuple[
            int,
            int,
            ProductRow | None,
            RowProcessResult | None,
        ] = (0, 0, None, None)

        self.table_model = ProductTableModel(self)
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setDynamicSortFilter(True)

        self.table = SpreadsheetView()
        self.table.setModel(self.proxy_model)
        self.table.freeze_columns(1)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "Filter rows (case-insensitive substring; matches any column)"
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.proxy_model.setFilterFixedString)

        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.filter_edit, stretch=1)

        self.status_label = QLabel("Load product and category Excel files.")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(filter_row)
        layout.addWidget(self.table)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        self.setCentralWidget(central)

        self._build_toolbar()
        self._load_cached_state()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.load_product_button = QPushButton("Load Product Excel")
        self.load_product_button.clicked.connect(self.load_product_excel)
        toolbar.addWidget(self.load_product_button)

        self.load_category_button = QPushButton("Load Category Excel")
        self.load_category_button.clicked.connect(self.load_category_excel)
        toolbar.addWidget(self.load_category_button)

        sample_widget = QWidget()
        sample_layout = QHBoxLayout(sample_widget)
        sample_layout.setContentsMargins(8, 0, 8, 0)
        sample_layout.addWidget(QLabel("Sample rows"))
        self.sample_row_spinbox = QSpinBox()
        self.sample_row_spinbox.setRange(1, 100000)
        self.sample_row_spinbox.setValue(20)
        sample_layout.addWidget(self.sample_row_spinbox)
        toolbar.addWidget(sample_widget)

        self.run_sample_button = QPushButton("Run Sample")
        self.run_sample_button.clicked.connect(self.run_sample)
        toolbar.addWidget(self.run_sample_button)

        self.run_full_button = QPushButton("Run Full Auto")
        self.run_full_button.clicked.connect(self.run_full_auto)
        toolbar.addWidget(self.run_full_button)

        self.export_button = QPushButton("Export Result")
        self.export_button.clicked.connect(self.export_result)
        toolbar.addWidget(self.export_button)

        self.truncate_button = QPushButton("Truncate DB")
        self.truncate_button.clicked.connect(self.truncate_database)
        toolbar.addWidget(self.truncate_button)

        self.processing_details_button = QPushButton("Details")
        self.processing_details_button.clicked.connect(self.open_processing_details)
        toolbar.addWidget(self.processing_details_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        toolbar.addWidget(self.settings_button)

    def open_processing_details(self) -> None:
        if self.processing_detail_dialog is None:
            self.processing_detail_dialog = ProcessingDetailDialog(self)
        current, total, row, result = self._processing_detail_state
        self.processing_detail_dialog.update_progress(
            current=current,
            total=total,
            row=row,
            result=result,
        )
        self.processing_detail_dialog.show()
        self.processing_detail_dialog.raise_()
        self.processing_detail_dialog.activateWindow()

    def _load_cached_state(self) -> None:
        try:
            product_data = self.store.load_product_workbook()
            categories = self.store.load_categories()
            results = self.store.load_results()
        except Exception as exc:
            self.status_label.setText(f"DB cache could not be loaded: {exc}")
            return

        if product_data is not None:
            self.product_data = product_data
            self.table_model.set_workbook(product_data)
            valid_results = [
                result
                for result in results
                if 0 <= result.row_index < len(product_data.rows)
            ]
            self.results = sorted(valid_results, key=lambda result: result.row_index)
            for result in self.results:
                self.table_model.set_result(result)
            self.status_label.setText(
                f"Loaded cached product rows: {len(product_data.rows)} from {product_data.path}"
            )

        if categories:
            self.categories = categories
            self.matcher = CategoryMatcher(categories)
            if product_data is None:
                self.status_label.setText(f"Loaded cached categories: {len(categories)}")

    def load_product_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Product Excel",
            "",
            "Excel files (*.xlsx)",
        )
        if not path:
            return
        if Path(path).suffix.lower() != ".xlsx":
            QMessageBox.warning(self, "Product Excel", "Only .xlsx files are supported.")
            return

        self._start_workbook_load("product", path)

    def load_category_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Category Excel",
            "",
            "Excel files (*.xlsx)",
        )
        if not path:
            return
        if Path(path).suffix.lower() != ".xlsx":
            QMessageBox.warning(self, "Category Excel", "Only .xlsx files are supported.")
            return

        self._start_workbook_load("category", path)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        self.settings = dialog.to_settings()
        try:
            save_settings(self.settings)
        except Exception as exc:
            QMessageBox.warning(self, "Settings", f"Settings could not be saved: {exc}")
            return
        self._clear_results()
        self.status_label.setText("Settings saved.")

    def _start_workbook_load(self, kind: str, path: str) -> None:
        self._set_controls_enabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Loading...")
        self.progress_bar.setVisible(True)
        self.status_label.setText(f"Loading {kind} Excel...")

        self.load_thread = QThread(self)
        self.load_worker = WorkbookLoadWorker(
            kind,
            path,
            settings=self.settings if kind == "category" else None,
            vector_store_factory=self.vector_store_factory,
        )
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)
        self.load_worker.progressed.connect(self._on_workbook_load_progress)
        self.load_worker.loaded.connect(self._on_workbook_loaded)
        self.load_worker.failed.connect(self._on_workbook_load_failed)
        self.load_worker.loaded.connect(self.load_thread.quit)
        self.load_worker.failed.connect(self.load_thread.quit)
        self.load_thread.finished.connect(self._finish_workbook_load)
        self.load_thread.finished.connect(self.load_worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)
        self.load_thread.start()

    def _on_workbook_load_progress(self, kind: str, current: int, total: int) -> None:
        if total <= 0:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.progress_bar.setFormat("0 / 0 rows")
            self.status_label.setText(f"Loading {kind} Excel... 0 / 0 rows")
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(current, total))
        self.progress_bar.setFormat(f"{current} / {total} rows")
        self.status_label.setText(f"Loading {kind} Excel... {current} / {total} rows")

    def _on_workbook_loaded(self, kind: str, payload: object) -> None:
        if kind == "product":
            self.product_data = payload
            assert isinstance(self.product_data, WorkbookData)
            self.results = []
            try:
                self.store.save_product_workbook(self.product_data)
            except Exception as exc:
                QMessageBox.warning(self, "Product Excel", f"DB save failed: {exc}")
            self.table_model.set_workbook(self.product_data)
            self.status_label.setText(
                f"Loaded product rows: {len(self.product_data.rows)} from {self.product_data.path}"
            )
            return

        assert isinstance(payload, CategoryLoadResult)
        self.categories = payload.categories
        self.matcher = CategoryMatcher(self.categories)
        try:
            self.store.save_categories(self.categories)
        except Exception as exc:
            QMessageBox.warning(self, "Category Excel", f"DB save failed: {exc}")
        self._clear_results()
        category_count = len(self.categories)
        if payload.vector_error:
            self.status_label.setText(
                f"Loaded categories: {category_count}. Chroma refresh failed: {payload.vector_error}"
            )
            QMessageBox.warning(self, "Category Excel", payload.vector_error)
        elif payload.vector_result is not None:
            self.status_label.setText(
                f"Loaded categories: {category_count}. Chroma DB refreshed: {payload.vector_result.count}"
            )
        else:
            self.status_label.setText(f"Loaded categories: {category_count}")

    def _on_workbook_load_failed(self, kind: str, message: str) -> None:
        title = "Product Excel" if kind == "product" else "Category Excel"
        self.status_label.setText(f"Failed to load {kind} Excel.")
        QMessageBox.warning(self, title, message)

    def _finish_workbook_load(self) -> None:
        self.progress_bar.setVisible(False)
        self._set_controls_enabled(True)
        self.load_worker = None
        self.load_thread = None

    def run_sample(self) -> None:
        if not self._validate_ready_to_run():
            return
        assert self.product_data is not None
        mode = self._choose_run_mode()
        if mode is None:
            return
        rows = filter_rows_for_run_mode(
            self.product_data.rows[: self.sample_row_spinbox.value()],
            mode,
            self.table_model.results_by_index,
        )
        self._run_rows(rows)

    def run_full_auto(self) -> None:
        if not self._validate_ready_to_run():
            return
        assert self.product_data is not None
        mode = self._choose_run_mode()
        if mode is None:
            return
        rows = filter_rows_for_run_mode(
            self.product_data.rows,
            mode,
            self.table_model.results_by_index,
        )
        self._run_rows(rows)

    def export_result(self) -> None:
        if self.product_data is None:
            QMessageBox.warning(self, "Export Result", "Load product Excel first.")
            return
        if not self.results:
            QMessageBox.warning(self, "Export Result", "Run sample or full auto before exporting results.")
            return

        source_path = self.product_data.path
        default_path = source_path.with_name(
            f"{source_path.stem}{self.settings.output_suffix}.xlsx"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Result",
            str(default_path),
            "Excel files (*.xlsx)",
        )
        if not path:
            return
        output_path = Path(path)
        if output_path.suffix.lower() != ".xlsx":
            output_path = output_path.with_suffix(".xlsx")

        try:
            output_path = export_results(self.product_data, self.results, output_path)
        except Exception as exc:
            QMessageBox.warning(self, "Export Result", str(exc))
            return

        self.status_label.setText(f"Exported result: {output_path}")

    def _validate_ready_to_run(self) -> bool:
        if self.product_data is None:
            QMessageBox.warning(self, "Run", "Load product Excel first.")
            return False
        if not self.settings.api_key.strip():
            QMessageBox.warning(self, "Run", "Open Settings and enter an API key first.")
            return False
        return True

    def _choose_run_mode(self) -> RunMode | None:
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Run Mode")
        message_box.setText("작업 모드를 선택하세요.")
        skip_button = message_box.addButton(
            "완료 제외",
            QMessageBox.ButtonRole.AcceptRole,
        )
        run_all_button = message_box.addButton(
            "모두 작업",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        message_box.addButton(QMessageBox.StandardButton.Cancel)
        message_box.setDefaultButton(skip_button)
        message_box.exec()

        clicked = message_box.clickedButton()
        if clicked == skip_button:
            return RunMode.SKIP_DONE
        if clicked == run_all_button:
            return RunMode.RUN_ALL
        return None

    def _run_rows(self, rows: list[ProductRow]) -> None:
        if not rows:
            self.status_label.setText("No rows to process.")
            self._update_processing_details(0, 0, None, None)
            return

        client = OpenAICompatibleClient(self.settings)
        processor = KeywordProcessor(ShoppingKeywordCollector(), client)
        existing_by_index: dict[int, RowProcessResult] = dict(
            self.table_model.results_by_index
        )

        self._set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(rows))
        self.progress_bar.setValue(0)
        try:
            total = len(rows)
            self._update_processing_details(0, total, None, None)
            for position, row in enumerate(rows, start=1):
                self.status_label.setText(f"Processing row {position} of {total}...")
                self.progress_bar.setFormat(f"{position - 1} / {total} rows")
                self._set_status(row.index, "처리중")
                self._update_processing_details(
                    position,
                    total,
                    row,
                    self.table_model.results_by_index.get(row.index),
                )
                QApplication.processEvents()

                result: RowProcessResult | None = None
                for step_result in processor.process_steps(row):
                    result = step_result
                    self._apply_result_to_table(step_result)
                    self._update_processing_details(position, total, row, step_result)
                    QApplication.processEvents()
                if result is None:
                    result = RowProcessResult(
                        row_index=row.index,
                        status=RowStatus.FAILED,
                        message="No processing steps were executed.",
                    )
                existing_by_index[row.index] = result
                self._apply_result_to_table(result)
                self._update_processing_details(position, total, row, result)
                self.progress_bar.setValue(position)
                self.progress_bar.setFormat(f"{position} / {total} rows")
                QApplication.processEvents()
        finally:
            self.progress_bar.setVisible(False)
            self._set_controls_enabled(True)

        self.results = sorted(existing_by_index.values(), key=lambda result: result.row_index)
        self.status_label.setText(f"Processed rows: {len(rows)}")

    def _clear_results(self) -> None:
        self.results = []
        try:
            self.store.clear_results()
        except Exception as exc:
            self.status_label.setText(f"DB result cache could not be cleared: {exc}")
        self.table_model.clear_results()

    def _refresh_table(self, show_progress: bool = False) -> None:
        if self.product_data is None:
            self.table_model.set_workbook(None)
            return
        self.table_model.set_workbook(self.product_data)

    def _apply_result_to_table(self, result: RowProcessResult) -> None:
        self.table_model.set_result(result)
        try:
            self.store.save_result(result)
        except Exception as exc:
            self.status_label.setText(f"DB result cache could not be saved: {exc}")

    def _set_status(self, row_index: int, status: str) -> None:
        self.table_model.set_status(row_index, status)

    def _update_processing_details(
        self,
        current: int,
        total: int,
        row: ProductRow | None,
        result: RowProcessResult | None,
    ) -> None:
        self._processing_detail_state = (current, total, row, result)
        if self.processing_detail_dialog is None:
            return
        self.processing_detail_dialog.update_progress(
            current=current,
            total=total,
            row=row,
            result=result,
        )

    def truncate_database(self) -> None:
        answer = QMessageBox.question(
            self,
            "Truncate DB",
            "SQLite DB에 저장된 상품, 카테고리, 처리 결과 캐시를 모두 삭제할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.store.truncate()
        except Exception as exc:
            QMessageBox.warning(self, "Truncate DB", str(exc))
            return

        self.product_data = None
        self.categories = []
        self.matcher = None
        self.results = []
        self.table_model.set_workbook(None)
        self.status_label.setText("SQLite DB cache truncated.")

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.load_product_button,
            self.load_category_button,
            self.sample_row_spinbox,
            self.run_sample_button,
            self.run_full_button,
            self.export_button,
            self.truncate_button,
            self.settings_button,
        ):
            widget.setEnabled(enabled)
