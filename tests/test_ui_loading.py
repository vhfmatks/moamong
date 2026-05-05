from __future__ import annotations

import time
from pathlib import Path

from openpyxl import Workbook
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.category_vector_store import CategoryVectorRefreshResult, CategoryVectorStoreError
from moamong_app.excel_io import REQUIRED_PRODUCT_COLUMNS, WorkbookData
from moamong_app.models import Category, GeneratedRow, LlmSettings, ProductRow, RowProcessResult, RowStatus
from moamong_app.sqlite_store import SqliteStore
from moamong_app.ui.main_window import (
    CategoryLoadResult,
    MainWindow,
    ProductTableModel,
    RunMode,
    WorkbookLoadWorker,
    filter_rows_for_run_mode,
)


def make_product_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "List1(1-2)"
    ws.append(list(REQUIRED_PRODUCT_COLUMNS))
    ws.append(["P001", "얼굴배게", "마사지샵 얼굴 쿠션 베개", "", "마사지베개", "WB100"])
    ws.append(["P002", "가위", "수초 가위", "", "수초가위", "WB200"])
    wb.save(path)


def make_category_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Mycate1(1-2)"
    ws.append(["마이카테", "마이카테명"])
    ws.append(["WB100", "생활용품 > 침구 > 베개 >"])
    ws.append(["WB200", "반려동물 > 관상어용품 > 수초관리 >"])
    wb.save(path)


class SuccessfulVectorStore:
    def __init__(self) -> None:
        self.seen_categories: list[Category] | None = None
        self.seen_source_path: Path | None = None
        self.seen_settings: LlmSettings | None = None

    def refresh(
        self,
        categories: list[Category],
        *,
        source_path: str | Path,
        settings: LlmSettings,
    ) -> CategoryVectorRefreshResult:
        self.seen_categories = categories
        self.seen_source_path = Path(source_path)
        self.seen_settings = settings
        return CategoryVectorRefreshResult(
            collection_name="moamong_categories",
            count=len(categories),
            db_path=Path("C:/fake/chroma"),
            source_hash="hash",
        )


class FailingVectorStore:
    def refresh(
        self,
        categories: list[Category],
        *,
        source_path: str | Path,
        settings: LlmSettings,
    ) -> CategoryVectorRefreshResult:
        raise CategoryVectorStoreError("embedding failed")


def test_workbook_load_worker_emits_total_row_progress(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "product.xlsx"
    make_product_workbook(path)
    progress_events: list[tuple[str, int, int]] = []
    loaded: list[tuple[str, object]] = []
    failed: list[tuple[str, str]] = []
    worker = WorkbookLoadWorker("product", path)
    worker.progressed.connect(lambda kind, current, total: progress_events.append((kind, current, total)))
    worker.loaded.connect(lambda kind, payload: loaded.append((kind, payload)))
    worker.failed.connect(lambda kind, message: failed.append((kind, message)))

    worker.run()

    assert failed == []
    assert progress_events[0] == ("product", 0, 2)
    assert progress_events[-1] == ("product", 2, 2)
    assert loaded[0][0] == "product"
    assert isinstance(loaded[0][1], WorkbookData)


def test_category_workbook_load_worker_refreshes_chroma_after_loading(tmp_path: Path) -> None:
    QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "category.xlsx"
    make_category_workbook(path)
    store = SuccessfulVectorStore()
    loaded: list[tuple[str, object]] = []
    failed: list[tuple[str, str]] = []
    settings = LlmSettings(api_key="secret-key", embedding_model="embed-model")
    worker = WorkbookLoadWorker(
        "category",
        path,
        settings=settings,
        vector_store_factory=lambda: store,
    )
    worker.loaded.connect(lambda kind, payload: loaded.append((kind, payload)))
    worker.failed.connect(lambda kind, message: failed.append((kind, message)))

    worker.run()

    assert failed == []
    assert loaded[0][0] == "category"
    payload = loaded[0][1]
    assert isinstance(payload, CategoryLoadResult)
    assert [category.mycate for category in payload.categories] == ["WB100", "WB200"]
    assert payload.vector_result is not None
    assert payload.vector_result.count == 2
    assert payload.vector_error == ""
    assert store.seen_categories == payload.categories
    assert store.seen_source_path == path
    assert store.seen_settings is settings


def test_category_workbook_load_worker_still_loads_categories_when_chroma_refresh_fails(tmp_path: Path) -> None:
    QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "category.xlsx"
    make_category_workbook(path)
    loaded: list[tuple[str, object]] = []
    failed: list[tuple[str, str]] = []
    worker = WorkbookLoadWorker(
        "category",
        path,
        settings=LlmSettings(api_key="secret-key"),
        vector_store_factory=FailingVectorStore,
    )
    worker.loaded.connect(lambda kind, payload: loaded.append((kind, payload)))
    worker.failed.connect(lambda kind, message: failed.append((kind, message)))

    worker.run()

    assert failed == []
    payload = loaded[0][1]
    assert isinstance(payload, CategoryLoadResult)
    assert [category.mycate for category in payload.categories] == ["WB100", "WB200"]
    assert payload.vector_result is None
    assert payload.vector_error == "embedding failed"


def test_product_table_model_reads_source_and_generated_values(tmp_path: Path) -> None:
    data = WorkbookData(
        path=tmp_path / "product.xlsx",
        sheet_name="List1",
        columns=["상품코드", "상품명", "키워드"],
        rows=[
            ProductRow(index=0, values={"상품코드": "P001", "상품명": "얼굴배게", "키워드": "얼굴"}),
            ProductRow(index=1, values={"상품코드": "P002", "상품명": "가위", "키워드": "가위"}),
        ],
    )
    model = ProductTableModel()

    model.set_workbook(data)
    model.set_result(
        RowProcessResult(
            row_index=1,
            status=RowStatus.DONE,
            generated=GeneratedRow(
                product_name="수초 트리밍 가위",
                keywords=["수초가위"],
                mycate="WB200",
                mycate_name="반려동물 > 관상어용품 > 수초관리",
                confidence=0.95,
            ),
            site_keywords={
                "coupang": ["수초가위", "수초 트리밍"],
                "naver": ["수초 관리 가위"],
            },
            step_statuses={
                "search_keyword": "완료",
                "coupang": "완료",
                "naver": "완료",
                "llm": "완료",
            },
            search_keyword="수초 가위",
        )
    )

    assert model.rowCount() == 2
    assert model.columnCount() == 23
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "얼굴배게"
    assert model.data(model.index(1, 1), Qt.ItemDataRole.DisplayRole) == "수초 트리밍 가위"
    assert model.data(model.index(1, 1), Qt.ItemDataRole.ToolTipRole) is None
    assert model.data(model.index(1, 2), Qt.ItemDataRole.DisplayRole) == "수초가위"
    assert model.data(
        model.index(1, model.columns.index("쿠팡_키워드")),
        Qt.ItemDataRole.DisplayRole,
    ) == "수초가위,수초 트리밍"
    assert model.data(
        model.index(1, model.columns.index("쿠팡_키워드")),
        Qt.ItemDataRole.ToolTipRole,
    ) == "수초가위,수초 트리밍"
    assert model.data(
        model.index(1, model.columns.index("LLM_검색어")),
        Qt.ItemDataRole.DisplayRole,
    ) == "수초 가위"
    assert model.data(
        model.index(1, model.columns.index("검색어_status")),
        Qt.ItemDataRole.DisplayRole,
    ) == "완료"
    assert model.data(
        model.index(1, model.columns.index("쿠팡_status")),
        Qt.ItemDataRole.DisplayRole,
    ) == "완료"
    assert model.data(
        model.index(1, model.columns.index("LLM_step_status")),
        Qt.ItemDataRole.DisplayRole,
    ) == "완료"
    assert model.data(
        model.index(1, model.columns.index("LLM_status")),
        Qt.ItemDataRole.DisplayRole,
    ) == "완료"
    assert model.data(
        model.index(1, 1),
        Qt.ItemDataRole.BackgroundRole,
    ) is not None
    foreground = model.data(
        model.index(1, 1),
        Qt.ItemDataRole.ForegroundRole,
    )
    assert foreground is not None
    assert foreground.color().name() == "#111111"


def test_filter_rows_for_run_mode_skips_current_or_loaded_done_rows(tmp_path: Path) -> None:
    data = WorkbookData(
        path=tmp_path / "product.xlsx",
        sheet_name="List1",
        columns=["상품코드", "상품명", "LLM_status"],
        rows=[
            ProductRow(index=0, values={"상품코드": "P001", "상품명": "완료", "LLM_status": "완료"}),
            ProductRow(index=1, values={"상품코드": "P002", "상품명": "대기", "LLM_status": ""}),
            ProductRow(index=2, values={"상품코드": "P003", "상품명": "현재완료", "LLM_status": ""}),
        ],
    )
    model = ProductTableModel()
    model.set_workbook(data)
    model.set_result(RowProcessResult(row_index=2, status=RowStatus.DONE))

    rows = filter_rows_for_run_mode(
        data.rows,
        RunMode.SKIP_DONE,
        model.results_by_index,
    )

    assert [row.index for row in rows] == [1]
    assert [
        row.index
        for row in filter_rows_for_run_mode(
            data.rows,
            RunMode.RUN_ALL,
            model.results_by_index,
        )
    ] == [0, 1, 2]


def test_main_window_loads_cached_sqlite_state(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    data = WorkbookData(
        path=tmp_path / "product.xlsx",
        sheet_name="List1",
        columns=["상품코드", "상품명", "키워드"],
        rows=[
            ProductRow(index=0, values={"상품코드": "P001", "상품명": "얼굴배게", "키워드": "얼굴"}),
        ],
    )
    result = RowProcessResult(
        row_index=0,
        status=RowStatus.DONE,
        generated=GeneratedRow(product_name="얼굴 쿠션 베개", keywords=["얼굴쿠션"]),
        search_keyword="얼굴 쿠션",
    )
    categories = [Category(mycate="WB100", name="생활용품 > 침구 > 베개 >")]
    store.save_product_workbook(data)
    store.save_categories(categories)
    store.save_result(result)

    window = MainWindow(store=store)

    assert window.product_data == data
    assert window.categories == categories
    assert window.results == [result]
    assert window.table_model.rowCount() == 1
    assert window.table_model.data(
        window.table_model.index(0, window.table_model.columns.index("LLM_status")),
        Qt.ItemDataRole.DisplayRole,
    ) == "완료"
    window.close()


def test_load_product_excel_keeps_current_state_when_selected_file_is_not_xlsx(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    window = MainWindow(store=store)
    data = WorkbookData(
        path=tmp_path / "current.xlsx",
        sheet_name="List1",
        columns=["상품코드", "상품명", "키워드"],
        rows=[
            ProductRow(index=0, values={"상품코드": "P001", "상품명": "얼굴배게", "키워드": "얼굴"}),
        ],
    )
    result = RowProcessResult(row_index=0, status=RowStatus.DONE)
    window.product_data = data
    window.results = [result]
    window.table_model.set_workbook(data)
    window.table_model.set_result(result)
    monkeypatch.setattr(
        "moamong_app.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "not-product.txt"), ""),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    window.load_product_excel()

    assert window.product_data is data
    assert window.results == [result]
    assert window.table_model.workbook is data
    assert window.table_model.results_by_index == {0: result}
    window.close()


def test_load_category_excel_keeps_current_state_when_selected_file_is_not_xlsx(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    window = MainWindow(store=store)
    categories = [Category(mycate="WB100", name="생활용품 > 침구 > 베개 >")]
    matcher = CategoryMatcher(categories)
    data = WorkbookData(
        path=tmp_path / "product.xlsx",
        sheet_name="List1",
        columns=["상품코드", "상품명"],
        rows=[
            ProductRow(index=0, values={"상품코드": "P001", "상품명": "얼굴배게"}),
        ],
    )
    result = RowProcessResult(row_index=0, status=RowStatus.DONE)
    window.categories = categories
    window.matcher = matcher
    window.results = [result]
    window.table_model.set_workbook(data)
    window.table_model.set_result(result)
    monkeypatch.setattr(
        "moamong_app.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "not-category.txt"), ""),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    window.load_category_excel()

    assert window.categories == categories
    assert window.matcher is matcher
    assert window.results == [result]
    assert window.table_model.results_by_index == {0: result}
    window.close()


def test_start_workbook_load_category_thread_updates_state_and_cleans_up(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "category.xlsx"
    make_category_workbook(path)
    store = SuccessfulVectorStore()
    window = MainWindow(
        store=SqliteStore(tmp_path / "moamong.sqlite3"),
        vector_store_factory=lambda: store,
    )
    window.settings = LlmSettings(api_key="secret-key", embedding_model="embed-model")

    window._start_workbook_load("category", str(path))

    deadline = time.monotonic() + 5
    while window.load_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()

    assert window.load_thread is None
    assert window.load_worker is None
    assert [category.mycate for category in window.categories] == ["WB100", "WB200"]
    assert window.matcher is not None
    assert "Loaded categories: 2. Chroma DB refreshed: 2" in window.status_label.text()
    assert store.seen_source_path == path
    assert store.seen_settings is window.settings
    window.close()


def test_main_window_truncates_sqlite_and_clears_screen(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    data = WorkbookData(
        path=tmp_path / "product.xlsx",
        sheet_name="List1",
        columns=["상품코드", "상품명", "키워드"],
        rows=[
            ProductRow(index=0, values={"상품코드": "P001", "상품명": "얼굴배게", "키워드": "얼굴"}),
        ],
    )
    store.save_product_workbook(data)
    store.save_categories([Category(mycate="WB100", name="생활용품")])
    store.save_result(RowProcessResult(row_index=0, status=RowStatus.DONE))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = MainWindow(store=store)

    window.truncate_database()

    assert store.load_product_workbook() is None
    assert store.load_categories() == []
    assert store.load_results() == []
    assert window.product_data is None
    assert window.categories == []
    assert window.results == []
    assert window.table_model.rowCount() == 0
    window.close()


def test_main_window_opens_and_reuses_processing_detail_dialog(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(store=SqliteStore(tmp_path / "moamong.sqlite3"))

    assert window.processing_details_button.text() == "Details"

    window.open_processing_details()
    first_dialog = window.processing_detail_dialog

    assert first_dialog is not None
    assert first_dialog.isVisible()

    window.open_processing_details()

    assert window.processing_detail_dialog is first_dialog
    window.close()


def test_processing_details_button_stays_enabled_while_run_controls_are_disabled(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow(store=SqliteStore(tmp_path / "moamong.sqlite3"))

    window._set_controls_enabled(False)

    assert window.run_sample_button.isEnabled() is False
    assert window.processing_details_button.isEnabled() is True
    window.close()
