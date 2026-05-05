# Product Mapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop app that loads product and category Excel workbooks, processes rows with an OpenAI-compatible LLM, maps `마이카테`, and exports an updated workbook.

**Architecture:** Create a PySide6 app with a thin UI layer over testable services. Keep Excel loading/export, category matching, LLM calls, row processing, and settings persistence in separate modules.

**Tech Stack:** Python 3.11+, PySide6, pandas, openpyxl, requests, pytest, PyInstaller later for packaging.

---

## File Structure

- `pyproject.toml`: project metadata, runtime dependencies, pytest config.
- `src/moamong_app/__init__.py`: package marker.
- `src/moamong_app/__main__.py`: app entry point.
- `src/moamong_app/models.py`: dataclasses and status enum shared by services and UI.
- `src/moamong_app/settings.py`: load/save OpenAI-compatible LLM settings.
- `src/moamong_app/excel_io.py`: load product/category workbooks and export updated workbook.
- `src/moamong_app/category_matcher.py`: lexical category candidate matching.
- `src/moamong_app/llm_client.py`: OpenAI-compatible chat completions client and strict JSON parsing.
- `src/moamong_app/row_processor.py`: row orchestration, validation, and result status logic.
- `src/moamong_app/ui/main_window.py`: main window, run controls, result table, log panel.
- `src/moamong_app/ui/settings_dialog.py`: settings dialog.
- `tests/fixtures/`: small generated workbooks for tests.
- `tests/test_excel_io.py`: workbook loading/export tests.
- `tests/test_category_matcher.py`: category matching tests.
- `tests/test_llm_client.py`: LLM response parsing tests.
- `tests/test_row_processor.py`: row processing tests with fake LLM.

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/moamong_app/__init__.py`
- Create: `src/moamong_app/__main__.py`
- Create: `src/moamong_app/models.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create project metadata**

Create `pyproject.toml`:

```toml
[project]
name = "moamong-product-mapper"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "PySide6>=6.7",
  "openpyxl>=3.1",
  "pandas>=2.2",
  "requests>=2.32"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2"
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package marker**

Create `src/moamong_app/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

- [ ] **Step 3: Create shared models**

Create `src/moamong_app/models.py`:

```python
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
    mycate: str
    mycate_name: str
    confidence: float
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
    category_candidates: list[CategoryCandidate] = field(default_factory=list)
```

- [ ] **Step 4: Create app entry point**

Create `src/moamong_app/__main__.py`:

```python
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from moamong_app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1280, 820)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Create pytest fixture directory helper**

Create `tests/conftest.py`:

```python
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
```

- [ ] **Step 6: Run import check**

Run: `python -m pytest -q`

Expected: pytest starts and reports no tests collected or passes existing empty checks. If `python` is unavailable, use the Python runtime installed for the project.

## Task 2: Excel Loading and Export

**Files:**
- Create: `src/moamong_app/excel_io.py`
- Create: `tests/test_excel_io.py`

- [ ] **Step 1: Write failing Excel tests**

Create `tests/test_excel_io.py`:

```python
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from moamong_app.excel_io import (
    REQUIRED_PRODUCT_COLUMNS,
    WorkbookData,
    export_results,
    load_category_workbook,
    load_product_workbook,
)
from moamong_app.models import Category, GeneratedRow, RowProcessResult, RowStatus


def make_product_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "List1(1-2)"
    headers = list(REQUIRED_PRODUCT_COLUMNS) + ["등록일"]
    ws.append(headers)
    ws.append(["P001", "얼굴배게", "마사지샵 얼굴 쿠션 베개", "", "마사지베개", "WB100", "2026-05-05"])
    ws.append(["P002", "가위", "수초 가위", "", "수초가위", "WB200", "2026-05-05"])
    wb.save(path)


def make_category_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Mycate1(1-2)"
    ws.append(["마이카테", "마이카테명", "등록일"])
    ws.append(["WB100", "생활용품 > 침구 > 베개 >", "2026-05-05"])
    ws.append(["WB200", "반려동물 > 관상어용품 > 수초관리 >", "2026-05-05"])
    wb.save(path)


def test_load_product_workbook_reads_rows(tmp_path: Path) -> None:
    path = tmp_path / "product.xlsx"
    make_product_workbook(path)

    data = load_product_workbook(path)

    assert isinstance(data, WorkbookData)
    assert data.sheet_name == "List1(1-2)"
    assert len(data.rows) == 2
    assert data.rows[0].text("원본상품명(참고용)") == "마사지샵 얼굴 쿠션 베개"


def test_load_category_workbook_reads_mycate_columns(tmp_path: Path) -> None:
    path = tmp_path / "category.xlsx"
    make_category_workbook(path)

    categories = load_category_workbook(path)

    assert categories == [
        Category(mycate="WB100", name="생활용품 > 침구 > 베개 >"),
        Category(mycate="WB200", name="반려동물 > 관상어용품 > 수초관리 >"),
    ]


def test_export_results_updates_columns_and_adds_audit_columns(tmp_path: Path) -> None:
    product_path = tmp_path / "product.xlsx"
    output_path = tmp_path / "product_mapped.xlsx"
    make_product_workbook(product_path)
    data = load_product_workbook(product_path)
    result = RowProcessResult(
        row_index=0,
        status=RowStatus.DONE,
        generated=GeneratedRow(
            product_name="얼굴전용 마사지 베개",
            keywords=["마사지베개", "얼굴쿠션"],
            mycate="WB100",
            mycate_name="생활용품 > 침구 > 베개 >",
            confidence=0.91,
            review_reason="",
        ),
    )

    export_results(data, [result], output_path)

    wb = load_workbook(output_path)
    ws = wb["List1(1-2)"]
    headers = [cell.value for cell in ws[1]]
    row = [cell.value for cell in ws[2]]
    values = dict(zip(headers, row))
    assert values["상품명"] == "얼굴전용 마사지 베개"
    assert values["키워드"] == "마사지베개,얼굴쿠션"
    assert values["마이카테"] == "WB100"
    assert values["LLM_status"] == "완료"
    assert values["LLM_마이카테명"] == "생활용품 > 침구 > 베개 >"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_excel_io.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'moamong_app.excel_io'`.

- [ ] **Step 3: Implement Excel IO**

Create `src/moamong_app/excel_io.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl import load_workbook

from moamong_app.models import Category, ProductRow, RowProcessResult


REQUIRED_PRODUCT_COLUMNS = (
    "상품코드",
    "상품명",
    "원본상품명(참고용)",
    "옵션명",
    "키워드",
    "마이카테",
)


@dataclass
class WorkbookData:
    path: Path
    sheet_name: str
    rows: list[ProductRow]
    columns: list[str]


def _first_non_empty_sheet(path: Path) -> str:
    excel = pd.ExcelFile(path)
    for sheet_name in excel.sheet_names:
        preview = pd.read_excel(path, sheet_name=sheet_name, nrows=1)
        if len(preview.columns) > 0 and not preview.empty:
            return sheet_name
    return excel.sheet_names[0]


def _product_sheet_name(path: Path) -> str:
    excel = pd.ExcelFile(path)
    for sheet_name in excel.sheet_names:
        if sheet_name.startswith("List1"):
            return sheet_name
    return _first_non_empty_sheet(path)


def load_product_workbook(path: str | Path) -> WorkbookData:
    workbook_path = Path(path)
    sheet_name = _product_sheet_name(workbook_path)
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=str).fillna("")
    columns = [str(column) for column in df.columns]
    missing = [column for column in REQUIRED_PRODUCT_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Product workbook missing required columns: {', '.join(missing)}")
    rows = [ProductRow(index=i, values={str(k): v for k, v in record.items()}) for i, record in enumerate(df.to_dict(orient="records"))]
    return WorkbookData(path=workbook_path, sheet_name=sheet_name, rows=rows, columns=columns)


def load_category_workbook(path: str | Path) -> list[Category]:
    workbook_path = Path(path)
    sheet_name = _first_non_empty_sheet(workbook_path)
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=str).fillna("")
    missing = [column for column in ("마이카테", "마이카테명") if column not in df.columns]
    if missing:
        raise ValueError(f"Category workbook missing required columns: {', '.join(missing)}")
    categories: list[Category] = []
    for record in df[["마이카테", "마이카테명"]].to_dict(orient="records"):
        mycate = str(record["마이카테"]).strip()
        name = str(record["마이카테명"]).strip()
        if mycate and name:
            categories.append(Category(mycate=mycate, name=name))
    if not categories:
        raise ValueError("Category workbook has no usable category rows")
    return categories


def _ensure_headers(ws, headers: Iterable[str]) -> dict[str, int]:
    existing = [cell.value for cell in ws[1]]
    for header in headers:
        if header not in existing:
            ws.cell(row=1, column=len(existing) + 1, value=header)
            existing.append(header)
    return {str(header): idx + 1 for idx, header in enumerate(existing)}


def export_results(data: WorkbookData, results: list[RowProcessResult], output_path: str | Path) -> Path:
    output = Path(output_path)
    wb = load_workbook(data.path)
    ws = wb[data.sheet_name]
    headers = _ensure_headers(
        ws,
        [
            "LLM_상품명",
            "LLM_키워드",
            "LLM_마이카테",
            "LLM_마이카테명",
            "LLM_confidence",
            "LLM_status",
            "LLM_review_reason",
        ],
    )
    for result in results:
        excel_row = result.row_index + 2
        generated = result.generated
        ws.cell(excel_row, headers["LLM_status"], result.status.value)
        ws.cell(excel_row, headers["LLM_review_reason"], result.message)
        if generated is None:
            continue
        ws.cell(excel_row, headers["상품명"], generated.product_name)
        ws.cell(excel_row, headers["키워드"], generated.keywords_text)
        ws.cell(excel_row, headers["마이카테"], generated.mycate)
        ws.cell(excel_row, headers["LLM_상품명"], generated.product_name)
        ws.cell(excel_row, headers["LLM_키워드"], generated.keywords_text)
        ws.cell(excel_row, headers["LLM_마이카테"], generated.mycate)
        ws.cell(excel_row, headers["LLM_마이카테명"], generated.mycate_name)
        ws.cell(excel_row, headers["LLM_confidence"], generated.confidence)
        ws.cell(excel_row, headers["LLM_review_reason"], generated.review_reason or result.message)
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output
```

- [ ] **Step 4: Run Excel tests**

Run: `python -m pytest tests/test_excel_io.py -q`

Expected: PASS.

## Task 3: Category Matching

**Files:**
- Create: `src/moamong_app/category_matcher.py`
- Create: `tests/test_category_matcher.py`

- [ ] **Step 1: Write category matcher tests**

Create `tests/test_category_matcher.py`:

```python
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
    row = ProductRow(index=0, values={"마이카테": "WB100", "상품명": "알수없음", "원본상품명(참고용)": "", "옵션명": "", "키워드": ""})

    candidates = matcher.match(row, limit=1)

    assert candidates[0].category.mycate == "WB100"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_category_matcher.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'moamong_app.category_matcher'`.

- [ ] **Step 3: Implement category matcher**

Create `src/moamong_app/category_matcher.py`:

```python
from __future__ import annotations

import re
from collections import Counter

from moamong_app.models import Category, CategoryCandidate, ProductRow


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token.strip()) >= 2]


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
            score = 0.0
            for token, count in query_tokens.items():
                if token in self.category_tokens[category.mycate]:
                    score += count * 3.0
                elif token in category.name.lower():
                    score += count * 1.0
            if existing_mycate and category.mycate == existing_mycate:
                score += 2.5
            if score > 0:
                candidates.append(CategoryCandidate(category=category, score=score))
        if not candidates:
            candidates = [CategoryCandidate(category=category, score=0.0) for category in self.categories[:limit]]
        return sorted(candidates, key=lambda c: (-c.score, c.category.name, c.category.mycate))[:limit]
```

- [ ] **Step 4: Run matcher tests**

Run: `python -m pytest tests/test_category_matcher.py -q`

Expected: PASS.

## Task 4: LLM Client

**Files:**
- Create: `src/moamong_app/llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write LLM parser tests**

Create `tests/test_llm_client.py`:

```python
from __future__ import annotations

import pytest

from moamong_app.llm_client import LlmResponseError, parse_generated_row


def test_parse_generated_row_strict_json() -> None:
    generated = parse_generated_row(
        """
        {
          "product_name": "얼굴전용 마사지 베개",
          "keywords": ["마사지베개", "얼굴쿠션"],
          "mycate": "WB100",
          "mycate_name": "생활용품 > 침구 > 베개 >",
          "confidence": 0.91,
          "review_reason": ""
        }
        """
    )

    assert generated.product_name == "얼굴전용 마사지 베개"
    assert generated.keywords == ["마사지베개", "얼굴쿠션"]
    assert generated.confidence == 0.91


def test_parse_generated_row_rejects_missing_fields() -> None:
    with pytest.raises(LlmResponseError):
        parse_generated_row('{"product_name": "이름"}')
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_llm_client.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'moamong_app.llm_client'`.

- [ ] **Step 3: Implement LLM client**

Create `src/moamong_app/llm_client.py`:

```python
from __future__ import annotations

import json
import time
from typing import Any

import requests

from moamong_app.models import CategoryCandidate, GeneratedRow, LlmSettings, ProductRow


class LlmResponseError(ValueError):
    pass


def parse_generated_row(text: str) -> GeneratedRow:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmResponseError(f"LLM returned invalid JSON: {exc}") from exc
    required = ["product_name", "keywords", "mycate", "mycate_name", "confidence"]
    missing = [key for key in required if key not in data]
    if missing:
        raise LlmResponseError(f"LLM JSON missing fields: {', '.join(missing)}")
    if not isinstance(data["keywords"], list) or not all(isinstance(item, str) and item.strip() for item in data["keywords"]):
        raise LlmResponseError("LLM keywords must be a non-empty string list")
    try:
        confidence = float(data["confidence"])
    except (TypeError, ValueError) as exc:
        raise LlmResponseError("LLM confidence must be numeric") from exc
    if confidence < 0 or confidence > 1:
        raise LlmResponseError("LLM confidence must be between 0 and 1")
    generated = GeneratedRow(
        product_name=str(data["product_name"]).strip(),
        keywords=[item.strip() for item in data["keywords"] if item.strip()],
        mycate=str(data["mycate"]).strip(),
        mycate_name=str(data["mycate_name"]).strip(),
        confidence=confidence,
        review_reason=str(data.get("review_reason", "")).strip(),
        raw_response=text,
    )
    if not generated.product_name or not generated.keywords or not generated.mycate or not generated.mycate_name:
        raise LlmResponseError("LLM JSON contains empty required values")
    return generated


class OpenAICompatibleClient:
    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings

    def generate(self, row: ProductRow, candidates: list[CategoryCandidate]) -> GeneratedRow:
        content = self._build_prompt(row, candidates)
        response_text = self._chat(content)
        return parse_generated_row(response_text)

    def _chat(self, user_content: str) -> str:
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "You rewrite Korean shopping product rows. Return strict JSON only.",
                },
                {"role": "user", "content": user_content},
            ],
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.retry_count + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.settings.timeout_seconds)
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"])
            except Exception as exc:
                last_error = exc
                if attempt < self.settings.retry_count:
                    time.sleep(0.5 * (attempt + 1))
        raise LlmResponseError(f"LLM request failed: {last_error}")

    def _build_prompt(self, row: ProductRow, candidates: list[CategoryCandidate]) -> str:
        candidate_lines = "\n".join(
            f"- {candidate.category.mycate}: {candidate.category.name}"
            for candidate in candidates
        )
        return f"""
Rewrite this wholesale product row for my store.

Source row:
- 상품명: {row.text("상품명")}
- 원본상품명(참고용): {row.text("원본상품명(참고용)")}
- 옵션명: {row.text("옵션명")}
- 기존 키워드: {row.text("키워드")}
- 기존 마이카테: {row.text("마이카테")}

Category candidates:
{candidate_lines}

Rules:
- product_name: concise Korean product name.
- keywords: 10 to 20 Korean shopping search keywords, no duplicates.
- mycate: choose exactly one candidate code.
- mycate_name: matching candidate name.
- confidence: 0.0 to 1.0.
- review_reason: short Korean reason if confidence is low, otherwise empty string.

Return JSON with keys: product_name, keywords, mycate, mycate_name, confidence, review_reason.
""".strip()
```

- [ ] **Step 4: Run LLM tests**

Run: `python -m pytest tests/test_llm_client.py -q`

Expected: PASS.

## Task 5: Row Processor

**Files:**
- Create: `src/moamong_app/row_processor.py`
- Create: `tests/test_row_processor.py`

- [ ] **Step 1: Write row processor tests**

Create `tests/test_row_processor.py`:

```python
from __future__ import annotations

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.models import Category, GeneratedRow, LlmSettings, ProductRow, RowStatus
from moamong_app.row_processor import RowProcessor


class FakeLlm:
    def __init__(self, generated: GeneratedRow) -> None:
        self.generated = generated

    def generate(self, row, candidates):
        return self.generated


def test_row_processor_marks_done_for_valid_high_confidence_result() -> None:
    matcher = CategoryMatcher([Category("WB100", "생활용품 > 침구 > 베개 >")])
    generated = GeneratedRow("얼굴전용 마사지 베개", ["마사지베개"], "WB100", "생활용품 > 침구 > 베개 >", 0.91)
    processor = RowProcessor(matcher, FakeLlm(generated), LlmSettings(confidence_threshold=0.8))

    result = processor.process(ProductRow(0, {"상품명": "얼굴배게", "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개", "옵션명": "", "키워드": ""}))

    assert result.status == RowStatus.DONE
    assert result.generated == generated


def test_row_processor_marks_needs_review_for_low_confidence() -> None:
    matcher = CategoryMatcher([Category("WB100", "생활용품 > 침구 > 베개 >")])
    generated = GeneratedRow("얼굴전용 마사지 베개", ["마사지베개"], "WB100", "생활용품 > 침구 > 베개 >", 0.5, "카테고리 애매함")
    processor = RowProcessor(matcher, FakeLlm(generated), LlmSettings(confidence_threshold=0.8))

    result = processor.process(ProductRow(0, {"상품명": "얼굴배게", "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개", "옵션명": "", "키워드": ""}))

    assert result.status == RowStatus.NEEDS_REVIEW
    assert result.message == "카테고리 애매함"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_row_processor.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'moamong_app.row_processor'`.

- [ ] **Step 3: Implement row processor**

Create `src/moamong_app/row_processor.py`:

```python
from __future__ import annotations

from typing import Protocol

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.models import GeneratedRow, LlmSettings, ProductRow, RowProcessResult, RowStatus


class LlmGenerator(Protocol):
    def generate(self, row: ProductRow, candidates):
        ...


class RowProcessor:
    def __init__(self, matcher: CategoryMatcher, llm: LlmGenerator, settings: LlmSettings) -> None:
        self.matcher = matcher
        self.llm = llm
        self.settings = settings

    def process(self, row: ProductRow) -> RowProcessResult:
        candidates = self.matcher.match(row, limit=self.settings.category_candidate_count)
        try:
            generated: GeneratedRow = self.llm.generate(row, candidates)
            candidate_codes = {candidate.category.mycate for candidate in candidates}
            if generated.mycate not in candidate_codes:
                return RowProcessResult(
                    row_index=row.index,
                    status=RowStatus.NEEDS_REVIEW,
                    generated=generated,
                    message=f"선택된 카테고리가 후보 목록에 없습니다: {generated.mycate}",
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
                message="",
                category_candidates=candidates,
            )
        except Exception as exc:
            return RowProcessResult(
                row_index=row.index,
                status=RowStatus.FAILED,
                generated=None,
                message=str(exc),
                category_candidates=candidates,
            )
```

- [ ] **Step 4: Run row processor tests**

Run: `python -m pytest tests/test_row_processor.py -q`

Expected: PASS.

## Task 6: Settings Persistence

**Files:**
- Create: `src/moamong_app/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write settings tests**

Create `tests/test_settings.py`:

```python
from __future__ import annotations

from moamong_app.models import LlmSettings
from moamong_app.settings import load_settings, save_settings


def test_save_and_load_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    settings = LlmSettings(base_url="http://localhost:8000/v1", api_key="secret", model="test-model", temperature=0.1)

    save_settings(settings, path)
    loaded = load_settings(path)

    assert loaded.base_url == "http://localhost:8000/v1"
    assert loaded.api_key == "secret"
    assert loaded.model == "test-model"
    assert loaded.temperature == 0.1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_settings.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'moamong_app.settings'`.

- [ ] **Step 3: Implement settings**

Create `src/moamong_app/settings.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from moamong_app.models import LlmSettings


def default_settings_path() -> Path:
    return Path.home() / ".moamong_product_mapper" / "settings.json"


def load_settings(path: str | Path | None = None) -> LlmSettings:
    settings_path = Path(path) if path is not None else default_settings_path()
    if not settings_path.exists():
        return LlmSettings()
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    allowed = set(LlmSettings.__dataclass_fields__.keys())
    return LlmSettings(**{key: value for key, value in data.items() if key in allowed})


def save_settings(settings: LlmSettings, path: str | Path | None = None) -> Path:
    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return settings_path
```

- [ ] **Step 4: Run settings tests**

Run: `python -m pytest tests/test_settings.py -q`

Expected: PASS.

## Task 7: Desktop UI

**Files:**
- Create: `src/moamong_app/ui/__init__.py`
- Create: `src/moamong_app/ui/settings_dialog.py`
- Create: `src/moamong_app/ui/main_window.py`

- [ ] **Step 1: Create UI package marker**

Create `src/moamong_app/ui/__init__.py`:

```python
```

- [ ] **Step 2: Implement settings dialog**

Create `src/moamong_app/ui/settings_dialog.py`:

```python
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDoubleSpinBox, QFormLayout, QLineEdit, QPushButton, QSpinBox, QVBoxLayout

from moamong_app.models import LlmSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: LlmSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.base_url = QLineEdit(settings.base_url)
        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.model = QLineEdit(settings.model)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(settings.temperature)
        self.timeout_seconds = QSpinBox()
        self.timeout_seconds.setRange(5, 600)
        self.timeout_seconds.setValue(settings.timeout_seconds)
        self.retry_count = QSpinBox()
        self.retry_count.setRange(0, 10)
        self.retry_count.setValue(settings.retry_count)
        self.category_candidate_count = QSpinBox()
        self.category_candidate_count.setRange(1, 30)
        self.category_candidate_count.setValue(settings.category_candidate_count)
        self.confidence_threshold = QDoubleSpinBox()
        self.confidence_threshold.setRange(0.0, 1.0)
        self.confidence_threshold.setSingleStep(0.05)
        self.confidence_threshold.setValue(settings.confidence_threshold)
        self.output_suffix = QLineEdit(settings.output_suffix)

        form = QFormLayout()
        form.addRow("Base URL", self.base_url)
        form.addRow("API Key", self.api_key)
        form.addRow("Model", self.model)
        form.addRow("Temperature", self.temperature)
        form.addRow("Timeout seconds", self.timeout_seconds)
        form.addRow("Retry count", self.retry_count)
        form.addRow("Category candidates", self.category_candidate_count)
        form.addRow("Confidence threshold", self.confidence_threshold)
        form.addRow("Output suffix", self.output_suffix)

        save = QPushButton("Save")
        save.clicked.connect(self.accept)
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(save)
        self.setLayout(layout)

    def to_settings(self) -> LlmSettings:
        return LlmSettings(
            base_url=self.base_url.text().strip(),
            api_key=self.api_key.text().strip(),
            model=self.model.text().strip(),
            temperature=float(self.temperature.value()),
            timeout_seconds=int(self.timeout_seconds.value()),
            retry_count=int(self.retry_count.value()),
            category_candidate_count=int(self.category_candidate_count.value()),
            confidence_threshold=float(self.confidence_threshold.value()),
            output_suffix=self.output_suffix.text().strip() or "_mapped",
        )
```

- [ ] **Step 3: Implement main window**

Create `src/moamong_app/ui/main_window.py`:

```python
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from moamong_app.category_matcher import CategoryMatcher
from moamong_app.excel_io import WorkbookData, export_results, load_category_workbook, load_product_workbook
from moamong_app.llm_client import OpenAICompatibleClient
from moamong_app.models import LlmSettings, RowProcessResult, RowStatus
from moamong_app.row_processor import RowProcessor
from moamong_app.settings import load_settings, save_settings
from moamong_app.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    HEADERS = ["상품코드", "원본상품명", "LLM_상품명", "LLM_키워드", "LLM_마이카테명", "confidence", "status", "message"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Moamong Product Mapper")
        self.settings: LlmSettings = load_settings()
        self.product_data: WorkbookData | None = None
        self.matcher: CategoryMatcher | None = None
        self.results: list[RowProcessResult] = []

        self.product_label = QLabel("Product: not loaded")
        self.category_label = QLabel("Category: not loaded")
        self.sample_count = QSpinBox()
        self.sample_count.setRange(1, 10000)
        self.sample_count.setValue(20)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        load_product = QPushButton("Load Product Excel")
        load_product.clicked.connect(self.load_product)
        load_category = QPushButton("Load Category Excel")
        load_category.clicked.connect(self.load_category)
        run_sample = QPushButton("Run Sample")
        run_sample.clicked.connect(self.run_sample)
        run_full = QPushButton("Run Full Auto")
        run_full.clicked.connect(self.run_full)
        export = QPushButton("Export Result")
        export.clicked.connect(self.export_result)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.open_settings)

        toolbar = QHBoxLayout()
        for widget in [load_product, load_category, QLabel("Sample rows"), self.sample_count, run_sample, run_full, export, settings]:
            toolbar.addWidget(widget)
        toolbar.addStretch(1)

        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(self.product_label)
        layout.addWidget(self.category_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("Log"))
        layout.addWidget(self.log)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

    def append_log(self, message: str) -> None:
        self.log.append(message)

    def load_product(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load product workbook", "", "Excel files (*.xlsx)")
        if not path:
            return
        try:
            self.product_data = load_product_workbook(path)
            self.product_label.setText(f"Product: {path} ({len(self.product_data.rows)} rows)")
            self.populate_source_rows(self.product_data.rows[: min(100, len(self.product_data.rows))])
            self.append_log(f"Loaded product workbook: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def load_category(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load category workbook", "", "Excel files (*.xlsx)")
        if not path:
            return
        try:
            categories = load_category_workbook(path)
            self.matcher = CategoryMatcher(categories)
            self.category_label.setText(f"Category: {path} ({len(categories)} categories)")
            self.append_log(f"Loaded category workbook: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def populate_source_rows(self, rows) -> None:
        self.table.setRowCount(len(rows))
        for table_row, row in enumerate(rows):
            values = [row.text("상품코드"), row.text("원본상품명(참고용)"), "", "", "", "", RowStatus.PENDING.value, ""]
            for col, value in enumerate(values):
                self.table.setItem(table_row, col, QTableWidgetItem(value))

    def _ensure_ready(self) -> bool:
        if self.product_data is None:
            QMessageBox.warning(self, "Not ready", "Load product Excel first.")
            return False
        if self.matcher is None:
            QMessageBox.warning(self, "Not ready", "Load category Excel first.")
            return False
        if not self.settings.api_key:
            QMessageBox.warning(self, "Not ready", "Open Settings and enter API key.")
            return False
        return True

    def run_sample(self) -> None:
        if self.product_data is None:
            QMessageBox.warning(self, "Not ready", "Load product Excel first.")
            return
        self._run_rows(self.sample_count.value())

    def run_full(self) -> None:
        if self.product_data is None:
            QMessageBox.warning(self, "Not ready", "Load product Excel first.")
            return
        self._run_rows(len(self.product_data.rows))

    def _run_rows(self, count: int) -> None:
        if not self._ensure_ready() or self.product_data is None or self.matcher is None:
            return
        llm = OpenAICompatibleClient(self.settings)
        processor = RowProcessor(self.matcher, llm, self.settings)
        rows = self.product_data.rows[:count]
        self.populate_source_rows(rows)
        self.results = []
        for i, row in enumerate(rows):
            self.table.setItem(i, 6, QTableWidgetItem(RowStatus.PROCESSING.value))
            result = processor.process(row)
            self.results.append(result)
            self._update_result_row(i, result)
            self.append_log(f"Row {row.index + 1}: {result.status.value} {result.message}")

    def _update_result_row(self, table_row: int, result: RowProcessResult) -> None:
        generated = result.generated
        values = [
            generated.product_name if generated else "",
            generated.keywords_text if generated else "",
            generated.mycate_name if generated else "",
            str(generated.confidence) if generated else "",
            result.status.value,
            result.message,
        ]
        for offset, value in enumerate(values, start=2):
            item = QTableWidgetItem(value)
            if result.status == RowStatus.NEEDS_REVIEW:
                item.setBackground(Qt.GlobalColor.yellow)
            elif result.status == RowStatus.FAILED:
                item.setBackground(Qt.GlobalColor.red)
            self.table.setItem(table_row, offset, item)

    def export_result(self) -> None:
        if self.product_data is None or not self.results:
            QMessageBox.warning(self, "Nothing to export", "Run sample or full processing first.")
            return
        source = self.product_data.path
        default_path = source.with_name(f"{source.stem}{self.settings.output_suffix}{source.suffix}")
        path, _ = QFileDialog.getSaveFileName(self, "Export result workbook", str(default_path), "Excel files (*.xlsx)")
        if not path:
            return
        try:
            output = export_results(self.product_data, self.results, Path(path))
            self.append_log(f"Exported result workbook: {output}")
            QMessageBox.information(self, "Export complete", str(output))
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.to_settings()
            save_settings(self.settings)
            self.append_log("Settings saved.")
```

- [ ] **Step 4: Smoke check the app imports**

Run: `python -m moamong_app`

Expected: A desktop window opens. Close it manually after confirming the toolbar, table, log panel, and Settings dialog display.

## Task 8: Integration Verification

**Files:**
- Modify: no source files unless verification finds a defect.

- [ ] **Step 1: Run all tests**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Verify against provided files without calling real LLM**

Run this short script in the project root:

```python
from moamong_app.excel_io import load_category_workbook, load_product_workbook
from moamong_app.category_matcher import CategoryMatcher

products = load_product_workbook("product_list.xlsx")
categories = load_category_workbook("category.xlsx")
matcher = CategoryMatcher(categories)
print(len(products.rows), len(categories))
print([(c.category.mycate, c.category.name, c.score) for c in matcher.match(products.rows[0], limit=3)])
```

Expected: prints `4959 5950` and three category candidates.

- [ ] **Step 3: Run manual UI test**

Run: `python -m moamong_app`

Expected:

- Load `product_list.xlsx`.
- Load `category.xlsx`.
- Open Settings and enter OpenAI-compatible `base_url`, `api_key`, and `model`.
- Run Sample with 1 or 2 rows.
- Confirm statuses populate.
- Export result workbook.
- Open exported workbook in Excel and confirm `상품명`, `키워드`, `마이카테`, and `LLM_*` audit columns are present.

## Self-Review

- Spec coverage: covered Windows UI, file loading, OpenAI-compatible settings, sample/full processing, category matching, row validation, export, and tests.
- Scope control: wholesale-site download automation, non-OpenAI provider presets, local LLM setup, and marketplace category conversion remain outside this plan.
- Placeholder scan: no unresolved markers or open-ended implementation instructions remain.
- Type consistency: `LlmSettings`, `GeneratedRow`, `RowProcessResult`, `RowStatus`, `CategoryMatcher`, `OpenAICompatibleClient`, and `WorkbookData` signatures are consistent across tasks.
