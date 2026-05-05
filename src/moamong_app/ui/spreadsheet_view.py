from __future__ import annotations

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QPoint,
    Qt,
)
from PySide6.QtGui import QGuiApplication, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QToolButton,
    QWidget,
)


def selection_to_tsv(view: QTableView) -> str:
    """Format the current selection as TSV (rows separated by \\n, cells by \\t)."""
    model = view.model()
    selection = view.selectionModel()
    if model is None or selection is None:
        return ""

    indexes = [index for index in selection.selectedIndexes() if index.isValid()]
    if not indexes:
        current = view.currentIndex()
        if not current.isValid():
            return ""
        text = model.data(current, Qt.ItemDataRole.DisplayRole)
        return "" if text is None else str(text)

    by_row: dict[int, dict[int, str]] = {}
    for index in indexes:
        text = model.data(index, Qt.ItemDataRole.DisplayRole)
        by_row.setdefault(index.row(), {})[index.column()] = (
            "" if text is None else str(text)
        )

    rows = sorted(by_row)
    cols = sorted({col for cells in by_row.values() for col in cells})
    return "\n".join(
        "\t".join(by_row[row].get(col, "") for col in cols)
        for row in rows
    )


def find_next_match(
    model: QAbstractItemModel,
    needle: str,
    start: QModelIndex | None,
    *,
    forward: bool,
) -> QModelIndex | None:
    """Search the model cell-by-cell for a case-insensitive substring match."""
    if not needle:
        return None
    rows = model.rowCount()
    cols = model.columnCount()
    if rows == 0 or cols == 0:
        return None

    total = rows * cols
    if start is not None and start.isValid():
        start_pos = start.row() * cols + start.column()
    else:
        start_pos = -1 if forward else total
    needle_lower = needle.lower()
    step = 1 if forward else -1
    for offset in range(1, total + 1):
        pos = (start_pos + step * offset) % total
        r = pos // cols
        c = pos % cols
        text = model.data(model.index(r, c), Qt.ItemDataRole.DisplayRole)
        if text is None:
            continue
        if needle_lower in str(text).lower():
            return model.index(r, c)
    return None


class FindBar(QWidget):
    """Inline find bar overlaid above the table viewport."""

    def __init__(self, view: "SpreadsheetView") -> None:
        super().__init__(view)
        self.view = view

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("찾기 (Enter: 다음, Shift+Enter: 이전, Esc: 닫기)")
        self.match_label = QLabel("", self)
        self.prev_button = QToolButton(self)
        self.prev_button.setText("◀")
        self.next_button = QToolButton(self)
        self.next_button.setText("▶")
        self.close_button = QToolButton(self)
        self.close_button.setText("✕")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(self.search_edit, stretch=1)
        layout.addWidget(self.match_label)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.close_button)
        self.setAutoFillBackground(True)

        self.search_edit.returnPressed.connect(self._on_return)
        self.search_edit.installEventFilter(self)
        self.next_button.clicked.connect(self.find_next)
        self.prev_button.clicked.connect(self.find_previous)
        self.close_button.clicked.connect(self.hide_bar)
        self.hide()

    def show_bar(self) -> None:
        self.show()
        self.raise_()
        self.reposition()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def hide_bar(self) -> None:
        self.hide()
        self.match_label.clear()
        self.view.setFocus()

    def find_next(self) -> None:
        self._find(forward=True)

    def find_previous(self) -> None:
        self._find(forward=False)

    def reposition(self) -> None:
        viewport = self.view.viewport()
        height = self.sizeHint().height()
        offset = viewport.mapTo(self.view, QPoint(0, 0))
        self.setGeometry(offset.x(), offset.y(), viewport.width(), height)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.search_edit and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key.Key_Escape:
                self.hide_bar()
                return True
        return super().eventFilter(watched, event)

    def _on_return(self) -> None:
        modifiers = QGuiApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self.find_previous()
        else:
            self.find_next()

    def _find(self, *, forward: bool) -> None:
        needle = self.search_edit.text().strip()
        if not needle:
            self.match_label.clear()
            return
        model = self.view.model()
        if model is None:
            return
        match = find_next_match(
            model,
            needle,
            self.view.currentIndex(),
            forward=forward,
        )
        if match is None:
            self.match_label.setText("없음")
            return
        self.view.setCurrentIndex(match)
        self.view.scrollTo(match)
        self.match_label.setText("찾음")


class SpreadsheetView(QTableView):
    """QTableView with copy-to-clipboard, find bar and an optional frozen first column."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setWordWrap(False)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.horizontalHeader().setDefaultSectionSize(140)
        self.horizontalHeader().setStretchLastSection(False)
        self.verticalHeader().setDefaultSectionSize(24)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._copy_shortcut.activated.connect(self.copy_selection_to_clipboard)
        self._find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self._find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._find_shortcut.activated.connect(self.show_find_bar)

        self._frozen_view: QTableView | None = None
        self._frozen_columns = 0

        self.find_bar = FindBar(self)

    def copy_selection_to_clipboard(self) -> None:
        text = selection_to_tsv(self)
        if not text:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def show_find_bar(self) -> None:
        self.find_bar.show_bar()

    def setModel(self, model: QAbstractItemModel) -> None:  # type: ignore[override]
        old_model = self.model()
        if old_model is not None:
            try:
                old_model.modelReset.disconnect(self._on_model_reset)
            except (RuntimeError, TypeError):
                pass
        super().setModel(model)
        if model is not None:
            model.modelReset.connect(self._on_model_reset)
        if self._frozen_view is not None:
            self._frozen_view.setModel(model)
            self._frozen_view.setSelectionModel(self.selectionModel())
            self._refresh_frozen_columns()
            self._update_frozen_geometry()

    def _on_model_reset(self) -> None:
        self._refresh_frozen_columns()
        self._update_frozen_geometry()

    def freeze_columns(self, count: int) -> None:
        if count <= 0:
            self._tear_down_frozen_view()
            return
        self._frozen_columns = count
        if self.model() is None:
            return
        if self._frozen_view is None:
            self._frozen_view = self._build_frozen_view()
        self._refresh_frozen_columns()
        self._update_frozen_geometry()

    def resizeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_frozen_geometry()
        if self.find_bar.isVisible():
            self.find_bar.reposition()

    def scrollTo(  # type: ignore[override]
        self,
        index: QModelIndex,
        hint: QTableView.ScrollHint = QTableView.ScrollHint.EnsureVisible,
    ) -> None:
        if (
            self._frozen_view is not None
            and 0 <= index.column() < self._frozen_columns
        ):
            return
        super().scrollTo(index, hint)

    def _build_frozen_view(self) -> QTableView:
        frozen = QTableView(self)
        frozen.setModel(self.model())
        frozen.setSelectionModel(self.selectionModel())
        frozen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        frozen.verticalHeader().hide()
        frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setStyleSheet(
            "QTableView { border: none; background-color: palette(alternate-base); }"
        )
        frozen.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        frozen.setAlternatingRowColors(self.alternatingRowColors())
        frozen.setShowGrid(self.showGrid())
        frozen.setTextElideMode(self.textElideMode())
        frozen.setWordWrap(self.wordWrap())
        frozen.setSortingEnabled(self.isSortingEnabled())
        frozen.setSelectionBehavior(self.selectionBehavior())
        frozen.setSelectionMode(self.selectionMode())

        self.viewport().stackUnder(frozen)
        frozen.show()

        self.verticalScrollBar().valueChanged.connect(
            frozen.verticalScrollBar().setValue
        )
        frozen.verticalScrollBar().valueChanged.connect(
            self.verticalScrollBar().setValue
        )
        self.horizontalHeader().sectionResized.connect(self._on_section_resized)
        self.verticalHeader().sectionResized.connect(self._on_row_resized)
        self.horizontalHeader().sortIndicatorChanged.connect(
            lambda col, order: frozen.horizontalHeader().setSortIndicator(col, order)
        )
        return frozen

    def _on_section_resized(
        self, logical_index: int, _old_size: int, new_size: int
    ) -> None:
        if self._frozen_view is None or logical_index >= self._frozen_columns:
            return
        self._frozen_view.setColumnWidth(logical_index, new_size)
        self._update_frozen_geometry()

    def _on_row_resized(
        self, logical_index: int, _old_size: int, new_size: int
    ) -> None:
        if self._frozen_view is None:
            return
        self._frozen_view.setRowHeight(logical_index, new_size)

    def _refresh_frozen_columns(self) -> None:
        frozen = self._frozen_view
        model = self.model()
        if frozen is None or model is None:
            return
        for col in range(model.columnCount()):
            hide = col >= self._frozen_columns
            frozen.setColumnHidden(col, hide)
            if not hide:
                frozen.setColumnWidth(col, self.columnWidth(col))

    def _update_frozen_geometry(self) -> None:
        frozen = self._frozen_view
        if frozen is None:
            return
        width = sum(
            self.columnWidth(col) for col in range(self._frozen_columns)
        )
        frozen.setGeometry(
            self.verticalHeader().width() + self.frameWidth(),
            self.frameWidth(),
            width,
            self.viewport().height() + self.horizontalHeader().height(),
        )

    def _tear_down_frozen_view(self) -> None:
        self._frozen_columns = 0
        if self._frozen_view is not None:
            self._frozen_view.setParent(None)
            self._frozen_view.deleteLater()
            self._frozen_view = None
