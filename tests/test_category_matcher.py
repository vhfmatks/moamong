from __future__ import annotations

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.models import Category, ProductRow


def test_matcher_ranks_category_by_product_text() -> None:
    matcher = CategoryMatcher(
        [
            Category("WB100", "생활용품 > 침구 > 베개 >"),
            Category("WB200", "반려동물 > 관상어용품 > 수초관리 >"),
            Category("WB300", "문구 > 공예 > 비즈공예 >"),
        ]
    )
    row = ProductRow(
        index=0,
        values={
            "상품명": "가위",
            "원본상품명(참고용)": "수초 가위",
            "옵션명": "",
            "키워드": "수초가위,수족관관리",
        },
    )

    candidates = matcher.match(row, limit=2)

    assert candidates[0].category.mycate == "WB200"
    assert len(candidates) == 2
    assert candidates[0].score > candidates[1].score


def test_matcher_keeps_exact_existing_mycate_as_candidate() -> None:
    matcher = CategoryMatcher(
        [
            Category("WB100", "생활용품 > 침구 > 베개 >"),
            Category("WB200", "반려동물 > 관상어용품 > 수초관리 >"),
        ]
    )
    row = ProductRow(
        index=0,
        values={
            "마이카테": "WB100",
            "상품명": "알수없음",
            "원본상품명(참고용)": "",
            "옵션명": "",
            "키워드": "",
        },
    )

    candidates = matcher.match(row, limit=1)

    assert candidates[0].category.mycate == "WB100"
