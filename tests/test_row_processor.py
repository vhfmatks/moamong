from __future__ import annotations

from moamong_app.models import (
    Category,
    CategoryCandidate,
    GeneratedRow,
    LlmSettings,
    ProductRow,
    RowStatus,
)
from moamong_app.row_processor import RowProcessor


class StubMatcher:
    def __init__(self, candidates: list[CategoryCandidate]) -> None:
        self.candidates = candidates
        self.seen_limit: int | None = None

    def match(self, row: ProductRow, limit: int = 8) -> list[CategoryCandidate]:
        self.seen_limit = limit
        return self.candidates


class StubLlm:
    def __init__(self, generated: GeneratedRow) -> None:
        self.generated = generated
        self.seen_row: ProductRow | None = None
        self.seen_candidates: list[CategoryCandidate] | None = None

    def generate(
        self, row: ProductRow, candidates: list[CategoryCandidate]
    ) -> GeneratedRow:
        self.seen_row = row
        self.seen_candidates = candidates
        return self.generated


class RaisingLlm:
    def generate(
        self, row: ProductRow, candidates: list[CategoryCandidate]
    ) -> GeneratedRow:
        raise RuntimeError("LLM unavailable")


def test_process_returns_done_for_high_confidence_candidate_result() -> None:
    row = ProductRow(index=3, values={"상품명": "얼굴배게"})
    candidates = [
        CategoryCandidate(Category("WB100", "생활용품 > 침구 > 베개"), 4.0),
        CategoryCandidate(Category("WB200", "생활용품 > 수족관"), 1.0),
    ]
    matcher = StubMatcher(candidates)
    generated = GeneratedRow(
        product_name="얼굴배게",
        keywords=["얼굴베개"],
        mycate="WB100",
        mycate_name="생활용품 > 침구 > 베개",
        confidence=0.95,
    )
    llm = StubLlm(generated)

    result = RowProcessor(
        matcher=matcher,
        llm=llm,
        settings=LlmSettings(category_candidate_count=2, confidence_threshold=0.8),
    ).process(row)

    assert matcher.seen_limit == 2
    assert llm.seen_row is row
    assert llm.seen_candidates == candidates
    assert result.row_index == 3
    assert result.status is RowStatus.DONE
    assert result.generated is generated
    assert result.message == ""
    assert result.category_candidates == candidates


def test_process_returns_needs_review_for_low_confidence_with_review_reason() -> None:
    row = ProductRow(index=4, values={"상품명": "얼굴배게"})
    candidates = [CategoryCandidate(Category("WB100", "생활용품 > 침구 > 베개"), 4.0)]
    generated = GeneratedRow(
        product_name="얼굴배게",
        keywords=["얼굴베개"],
        mycate="WB100",
        mycate_name="생활용품 > 침구 > 베개",
        confidence=0.62,
        review_reason="상품 설명이 부족합니다.",
    )

    result = RowProcessor(
        matcher=StubMatcher(candidates),
        llm=StubLlm(generated),
        settings=LlmSettings(confidence_threshold=0.8),
    ).process(row)

    assert result.status is RowStatus.NEEDS_REVIEW
    assert result.generated is generated
    assert result.message == "상품 설명이 부족합니다."
    assert result.category_candidates == candidates


def test_process_returns_needs_review_for_invalid_confidence() -> None:
    row = ProductRow(index=4, values={"상품명": "얼굴배게"})
    candidates = [CategoryCandidate(Category("WB100", "생활용품 > 침구 > 베개"), 4.0)]
    generated = GeneratedRow(
        product_name="얼굴배게",
        keywords=["얼굴베개"],
        mycate="WB100",
        mycate_name="생활용품 > 침구 > 베개",
        confidence=float("nan"),
    )

    result = RowProcessor(
        matcher=StubMatcher(candidates),
        llm=StubLlm(generated),
        settings=LlmSettings(confidence_threshold=0.8),
    ).process(row)

    assert result.status is RowStatus.NEEDS_REVIEW
    assert result.generated is generated
    assert result.message == "신뢰도 값이 유효하지 않습니다."


def test_process_returns_needs_review_when_generated_category_is_not_candidate() -> None:
    row = ProductRow(index=5, values={"상품명": "얼굴배게"})
    candidates = [CategoryCandidate(Category("WB100", "생활용품 > 침구 > 베개"), 4.0)]
    generated = GeneratedRow(
        product_name="얼굴배게",
        keywords=["얼굴베개"],
        mycate="WB999",
        mycate_name="없는 카테고리",
        confidence=0.95,
    )

    result = RowProcessor(
        matcher=StubMatcher(candidates),
        llm=StubLlm(generated),
        settings=LlmSettings(confidence_threshold=0.8),
    ).process(row)

    assert result.status is RowStatus.NEEDS_REVIEW
    assert result.generated is generated
    assert result.message == "선택된 카테고리가 후보 목록에 없습니다: WB999"
    assert result.category_candidates == candidates


def test_process_returns_failed_when_llm_raises() -> None:
    row = ProductRow(index=6, values={"상품명": "얼굴배게"})
    candidates = [CategoryCandidate(Category("WB100", "생활용품 > 침구 > 베개"), 4.0)]

    result = RowProcessor(
        matcher=StubMatcher(candidates),
        llm=RaisingLlm(),
        settings=LlmSettings(),
    ).process(row)

    assert result.status is RowStatus.FAILED
    assert result.generated is None
    assert result.message == "LLM unavailable"
    assert result.category_candidates == candidates
