from __future__ import annotations

import re
from collections import Counter

from moamong_app.models import Category, CategoryCandidate, ProductRow


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token) >= 2]


class CategoryMatcher:
    def __init__(self, categories: list[Category]) -> None:
        if not categories:
            raise ValueError("At least one category is required")

        self.categories = categories
        self.by_code = {category.mycate: category for category in categories}
        self.category_tokens = {
            category.mycate: Counter(tokenize(category.name.replace(">", " ")))
            for category in categories
        }

    def match(self, row: ProductRow, limit: int = 8) -> list[CategoryCandidate]:
        query_text = " ".join(
            [
                row.text("상품명"),
                row.text("원본상품명(참고용)"),
                row.text("옵션명"),
                row.text("키워드").replace(",", " "),
            ]
        )
        query_tokens = Counter(tokenize(query_text))
        existing_mycate = row.text("마이카테")

        candidates: list[CategoryCandidate] = []
        for category in self.categories:
            score = self._score_category(category, query_tokens, existing_mycate)
            candidates.append(CategoryCandidate(category=category, score=score))

        if not any(candidate.score > 0 for candidate in candidates):
            candidates = [
                CategoryCandidate(category=category, score=0.0)
                for category in self.categories[:limit]
            ]

        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.category.name,
                candidate.category.mycate,
            ),
        )[:limit]

    def _score_category(
        self,
        category: Category,
        query_tokens: Counter[str],
        existing_mycate: str,
    ) -> float:
        score = 0.0
        category_tokens = self.category_tokens[category.mycate]
        category_name = category.name.lower()

        for token, count in query_tokens.items():
            if token in category_tokens:
                score += count * 3.0
            elif token in category_name:
                score += count * 1.0

        if existing_mycate and category.mycate == existing_mycate:
            score += 2.5

        return score
