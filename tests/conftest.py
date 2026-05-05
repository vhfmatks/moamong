from __future__ import annotations

import pytest


@pytest.fixture
def sample_rows() -> list[dict[str, str]]:
    return [
        {
            "상품코드": "P001",
            "상품명": "얼굴배게",
            "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개",
            "옵션명": "",
            "키워드": "마사지베개,얼굴쿠션",
            "마이카테": "WB100",
        },
        {
            "상품코드": "P002",
            "상품명": "가위",
            "원본상품명(참고용)": "수초 가위",
            "옵션명": "",
            "키워드": "수초가위,수족관관리",
            "마이카테": "WB200",
        },
    ]
