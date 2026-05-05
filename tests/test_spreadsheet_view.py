from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QSortFilterProxyModel, Qt
from PySide6.QtGui import QGuiApplication, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication

from moamong_app.ui.spreadsheet_view import (
    SpreadsheetView,
    find_next_match,
    selection_to_tsv,
)


def ensure_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_model(rows: list[list[str]], headers: list[str]) -> QStandardItemModel:
    model = QStandardItemModel(len(rows), len(headers))
    model.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            model.setItem(r, c, QStandardItem(value))
    return model


def test_selection_to_tsv_formats_rectangular_selection_as_tabs_and_newlines() -> None:
    ensure_app()
    model = make_model(
        [["P001", "얼굴배게", "마사지"], ["P002", "가위", "수초"]],
        ["코드", "상품", "키워드"],
    )
    view = SpreadsheetView()
    view.setModel(model)

    selection = view.selectionModel()
    selection.select(
        model.index(0, 0),
        QItemSelectionModel.SelectionFlag.Select,
    )
    selection.select(
        model.index(0, 1),
        QItemSelectionModel.SelectionFlag.Select,
    )
    selection.select(
        model.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select,
    )
    selection.select(
        model.index(1, 1),
        QItemSelectionModel.SelectionFlag.Select,
    )

    text = selection_to_tsv(view)
    assert text == "P001\t얼굴배게\nP002\t가위"


def test_copy_selection_to_clipboard_writes_tab_separated_values() -> None:
    ensure_app()
    model = make_model([["A", "B"], ["C", "D"]], ["c1", "c2"])
    view = SpreadsheetView()
    view.setModel(model)
    selection = view.selectionModel()
    selection.select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    selection.select(model.index(0, 1), QItemSelectionModel.SelectionFlag.Select)

    clipboard = QGuiApplication.clipboard()
    clipboard.setText("")  # reset so we can detect the copy

    view.copy_selection_to_clipboard()
    assert clipboard.text() == "A\tB"


def test_find_next_match_wraps_around_when_no_current_index_set() -> None:
    ensure_app()
    model = make_model(
        [["하나", "alpha"], ["둘", "beta"], ["셋", "ALPHA-2"]],
        ["c1", "c2"],
    )

    forward = find_next_match(model, "alpha", None, forward=True)
    assert forward is not None
    assert (forward.row(), forward.column()) == (0, 1)

    backward = find_next_match(model, "alpha", None, forward=False)
    assert backward is not None
    assert (backward.row(), backward.column()) == (2, 1)


def test_find_next_match_skips_current_and_finds_next_match() -> None:
    ensure_app()
    model = make_model(
        [["alpha-1"], ["beta"], ["alpha-2"], ["alpha-3"]],
        ["c"],
    )

    match = find_next_match(model, "alpha", model.index(0, 0), forward=True)
    assert match is not None
    assert match.row() == 2

    match = find_next_match(model, "alpha", model.index(2, 0), forward=False)
    assert match is not None
    assert match.row() == 0


def test_find_next_match_returns_none_when_no_match() -> None:
    ensure_app()
    model = make_model([["foo"], ["bar"]], ["c"])
    assert find_next_match(model, "zzz", None, forward=True) is None


def test_proxy_filter_through_view_hides_rows_that_do_not_match() -> None:
    ensure_app()
    source = make_model(
        [["P001", "얼굴배게"], ["P002", "수초가위"], ["P003", "땅콩버터"]],
        ["코드", "상품"],
    )
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(source)
    proxy.setFilterKeyColumn(-1)
    proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    view = SpreadsheetView()
    view.setModel(proxy)

    proxy.setFilterFixedString("가위")
    assert view.model().rowCount() == 1
    assert view.model().data(view.model().index(0, 0)) == "P002"

    proxy.setFilterFixedString("")
    assert view.model().rowCount() == 3


def test_proxy_sort_through_view_orders_rows_by_clicked_column() -> None:
    ensure_app()
    source = make_model(
        [["b"], ["a"], ["c"]],
        ["c1"],
    )
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(source)

    view = SpreadsheetView()
    view.setModel(proxy)
    view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    rows = [view.model().data(view.model().index(r, 0)) for r in range(3)]
    assert rows == ["a", "b", "c"]


def test_freeze_columns_hides_those_columns_in_the_frozen_overlay_view() -> None:
    ensure_app()
    model = make_model(
        [["P001", "얼굴배게", "마사지"], ["P002", "가위", "수초"]],
        ["코드", "상품", "키워드"],
    )
    view = SpreadsheetView()
    view.setModel(model)
    view.freeze_columns(1)

    frozen = view._frozen_view
    assert frozen is not None
    assert frozen.isColumnHidden(0) is False
    assert frozen.isColumnHidden(1) is True
    assert frozen.isColumnHidden(2) is True

    view.freeze_columns(0)
    assert view._frozen_view is None


def test_freeze_columns_refreshes_after_model_reset_changes_column_count() -> None:
    ensure_app()
    model = make_model([["x"]], ["only"])
    view = SpreadsheetView()
    view.setModel(model)
    view.freeze_columns(1)

    bigger = make_model(
        [["P001", "상품A", "메모"], ["P002", "상품B", ""]],
        ["코드", "상품", "메모"],
    )
    view.setModel(bigger)

    frozen = view._frozen_view
    assert frozen is not None
    assert frozen.model() is bigger
    assert frozen.isColumnHidden(0) is False
    assert frozen.isColumnHidden(1) is True
    assert frozen.isColumnHidden(2) is True


def test_find_bar_drives_view_selection_and_reports_match_state() -> None:
    ensure_app()
    model = make_model([["alpha"], ["beta"]], ["c"])
    view = SpreadsheetView()
    view.setModel(model)

    view.show_find_bar()
    assert view.find_bar.isHidden() is False

    view.find_bar.search_edit.setText("beta")
    view.find_bar.find_next()
    assert view.currentIndex().row() == 1
    assert view.find_bar.match_label.text() == "찾음"

    view.find_bar.search_edit.setText("zzz")
    view.find_bar.find_next()
    assert view.find_bar.match_label.text() == "없음"

    view.find_bar.hide_bar()
    assert view.find_bar.isHidden() is True
    assert view.find_bar.match_label.text() == ""
