from __future__ import annotations

import math
from typing import Protocol

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.models import (
    CategoryCandidate,
    GeneratedRow,
    LlmSettings,
    ProductRow,
    RowProcessResult,
    RowStatus,
)


class LlmGenerator(Protocol):
    def generate(
        self, row: ProductRow, candidates: list[CategoryCandidate]
    ) -> GeneratedRow:
        ...


class RowProcessor:
    def __init__(
        self,
        matcher: CategoryMatcher,
        llm: LlmGenerator,
        settings: LlmSettings,
    ) -> None:
        self.matcher = matcher
        self.llm = llm
        self.settings = settings

    def process(self, row: ProductRow) -> RowProcessResult:
        candidates: list[CategoryCandidate] = []
        try:
            candidates = self.matcher.match(
                row,
                limit=self.settings.category_candidate_count,
            )
            generated = self.llm.generate(row, candidates)

            candidate_codes = {candidate.category.mycate for candidate in candidates}
            if generated.mycate not in candidate_codes:
                return RowProcessResult(
                    row_index=row.index,
                    status=RowStatus.NEEDS_REVIEW,
                    generated=generated,
                    message=f"선택된 카테고리가 후보 목록에 없습니다: {generated.mycate}",
                    category_candidates=candidates,
                )

            if not math.isfinite(generated.confidence) or not 0 <= generated.confidence <= 1:
                return RowProcessResult(
                    row_index=row.index,
                    status=RowStatus.NEEDS_REVIEW,
                    generated=generated,
                    message="신뢰도 값이 유효하지 않습니다.",
                    category_candidates=candidates,
                )

            if generated.confidence < self.settings.confidence_threshold:
                return RowProcessResult(
                    row_index=row.index,
                    status=RowStatus.NEEDS_REVIEW,
                    generated=generated,
                    message=generated.review_reason or "신뢰도가 기준값보다 낮습니다.",
                    category_candidates=candidates,
                )

            return RowProcessResult(
                row_index=row.index,
                status=RowStatus.DONE,
                generated=generated,
                category_candidates=candidates,
            )
        except Exception as exc:
            return RowProcessResult(
                row_index=row.index,
                status=RowStatus.FAILED,
                message=str(exc),
                category_candidates=candidates,
            )
