from __future__ import annotations

from pathlib import Path

from moamong_app.excel_io import WorkbookData
from moamong_app.models import Category, GeneratedRow, ProductRow, RowProcessResult, RowStatus
from moamong_app.sqlite_store import SqliteStore


def make_workbook_data(path: Path) -> WorkbookData:
    return WorkbookData(
        path=path,
        sheet_name="List1(1-2)",
        columns=["상품코드", "상품명", "키워드", "마이카테"],
        rows=[
            ProductRow(
                index=0,
                values={
                    "상품코드": "P001",
                    "상품명": "얼굴배게",
                    "키워드": "마사지베개",
                    "마이카테": "WB100",
                },
            ),
            ProductRow(
                index=1,
                values={
                    "상품코드": "P002",
                    "상품명": "가위",
                    "키워드": "수초가위",
                    "마이카테": "WB200",
                },
            ),
        ],
    )


def make_result(row_index: int = 1) -> RowProcessResult:
    return RowProcessResult(
        row_index=row_index,
        status=RowStatus.DONE,
        generated=GeneratedRow(
            product_name="수초 트리밍 가위",
            keywords=["수초가위", "수초 트리밍"],
            mycate="WB200",
            mycate_name="반려동물 > 관상어용품 > 수초관리",
            confidence=0.93,
            review_reason="추천 키워드와 카테고리가 일치합니다.",
            raw_response='{"ok": true}',
        ),
        search_keyword="수초 가위",
        site_keywords={"coupang": ["수초가위"], "naver": ["수초 관리 가위"]},
        site_errors={"gmarket": "Timeout: slow"},
        step_statuses={
            "search_keyword": "완료",
            "coupang": "완료",
            "gmarket": "실패: Timeout: slow",
            "llm": "완료",
        },
    )


def test_sqlite_store_saves_and_loads_product_workbook(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    workbook = make_workbook_data(tmp_path / "product.xlsx")

    store.save_product_workbook(workbook)
    loaded = store.load_product_workbook()

    assert loaded == workbook


def test_sqlite_store_saves_and_loads_categories(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    categories = [
        Category(mycate="WB100", name="생활용품 > 침구 > 베개 >"),
        Category(mycate="WB200", name="반려동물 > 관상어용품 > 수초관리 >"),
    ]

    store.save_categories(categories)

    assert store.load_categories() == categories


def test_sqlite_store_saves_and_loads_row_results(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    result = make_result()

    store.save_result(result)

    assert store.load_results() == [result]


def test_sqlite_store_replaces_product_and_clears_stale_results(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    first = make_workbook_data(tmp_path / "first.xlsx")
    second = make_workbook_data(tmp_path / "second.xlsx")
    second.rows = second.rows[:1]

    store.save_product_workbook(first)
    store.save_result(make_result(row_index=1))
    store.save_product_workbook(second)

    assert store.load_product_workbook() == second
    assert store.load_results() == []


def test_sqlite_store_truncates_all_cached_data(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "moamong.sqlite3")
    store.save_product_workbook(make_workbook_data(tmp_path / "product.xlsx"))
    store.save_categories([Category(mycate="WB100", name="생활용품")])
    store.save_result(make_result())

    store.truncate()

    assert store.load_product_workbook() is None
    assert store.load_categories() == []
    assert store.load_results() == []
