from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from moamong_app.models import ProductRow, RowProcessResult, RowStatus
from moamong_app.ui.processing_detail_dialog import ProcessingDetailDialog


def make_app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_processing_detail_dialog_shows_idle_state() -> None:
    app = make_app()
    dialog = ProcessingDetailDialog()

    assert app is not None
    assert dialog.summary_label.text() == "No processing is running."
    assert dialog.progress_bar.value() == 0
    assert dialog.progress_bar.maximum() == 1
    assert dialog.row_label.text() == "-"
    assert dialog.product_label.text() == "-"
    assert dialog.search_keyword_label.text() == "-"
    dialog.close()


def test_processing_detail_dialog_updates_current_row_and_step_statuses() -> None:
    app = make_app()
    dialog = ProcessingDetailDialog()
    row = ProductRow(
        index=7,
        values={
            "상품코드": "P008",
            "상품명": "기존 상품명",
            "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개",
        },
    )
    result = RowProcessResult(
        row_index=7,
        status=RowStatus.PROCESSING,
        message="키워드 수집 중",
        search_keyword="얼굴 쿠션",
        step_statuses={
            "search_keyword": "완료",
            "coupang": "처리중",
            "naver": "대기",
            "llm": "대기",
        },
    )

    dialog.update_progress(current=3, total=10, row=row, result=result)

    assert app is not None
    assert dialog.summary_label.text() == "Processing row 3 of 10."
    assert dialog.progress_bar.value() == 3
    assert dialog.progress_bar.maximum() == 10
    assert dialog.row_label.text() == "8"
    assert dialog.product_label.text() == "마사지샵 얼굴 쿠션 베개"
    assert dialog.search_keyword_label.text() == "얼굴 쿠션"
    assert dialog.message_label.text() == "키워드 수집 중"
    assert dialog.step_status("검색어") == "완료"
    assert dialog.step_status("쿠팡") == "처리중"
    assert dialog.step_status("네이버") == "대기"
    assert dialog.step_status("LLM") == "대기"
    dialog.close()
