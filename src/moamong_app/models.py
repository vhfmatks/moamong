from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RowStatus(str, Enum):
    PENDING = "대기"
    PROCESSING = "처리중"
    DONE = "완료"
    NEEDS_REVIEW = "검수필요"
    FAILED = "실패"


@dataclass(frozen=True)
class Category:
    mycate: str
    name: str


@dataclass(frozen=True)
class CategoryCandidate:
    category: Category
    score: float


@dataclass
class ProductRow:
    index: int
    values: dict[str, Any]

    def text(self, column: str) -> str:
        value = self.values.get(column, "")
        if value is None:
            return ""
        return str(value).strip()


@dataclass
class LlmSettings:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    temperature: float = 0.2
    timeout_seconds: int = 60
    retry_count: int = 2
    category_candidate_count: int = 8
    confidence_threshold: float = 0.8
    output_suffix: str = "_mapped"


@dataclass
class GeneratedRow:
    product_name: str
    keywords: list[str]
    mycate: str = ""
    mycate_name: str = ""
    confidence: float = 1.0
    review_reason: str = ""
    raw_response: str = ""

    @property
    def keywords_text(self) -> str:
        return ",".join(k.strip() for k in self.keywords if k.strip())


@dataclass
class RowProcessResult:
    row_index: int
    status: RowStatus
    generated: GeneratedRow | None = None
    message: str = ""
    search_keyword: str = ""
    category_candidates: list[CategoryCandidate] = field(default_factory=list)
    site_keywords: dict[str, list[str]] = field(default_factory=dict)
    site_errors: dict[str, str] = field(default_factory=dict)
    step_statuses: dict[str, str] = field(default_factory=dict)
