# Site Keyword Product Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a product-name/keyword generation flow that uses shopping-site keyword suggestions and leaves `마이카테` untouched.

**Architecture:** Keep the existing category mapper code available, but route the current Run Sample / Run Full Auto actions through a new keyword-only processor. Site keyword lookup is isolated in one service, LLM JSON parsing is expanded with a category-free parser, and UI/export consume the new result metadata.

**Tech Stack:** Python 3.11, PySide6, requests, openpyxl, pytest.

---

### Task 1: Site Keyword Collector

**Files:**
- Create: `src/moamong_app/keyword_fetcher.py`
- Test: `tests/test_keyword_fetcher.py`

- [ ] **Step 1: Write failing tests**

Create tests for successful per-site collection and per-site failure isolation.

- [ ] **Step 2: Run red test**

Run: `uv run pytest tests/test_keyword_fetcher.py -q`
Expected: import failure for `moamong_app.keyword_fetcher`.

- [ ] **Step 3: Implement collector**

Move the `sample.py` fetcher behavior into a focused app module, preserving site-specific network logic and returning normalized `dict[str, list[str]]` plus `dict[str, str]` errors.

- [ ] **Step 4: Run green test**

Run: `uv run pytest tests/test_keyword_fetcher.py -q`
Expected: all tests pass.

### Task 2: Category-Free LLM Product Generation

**Files:**
- Modify: `src/moamong_app/models.py`
- Modify: `src/moamong_app/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

Add tests for parsing JSON with `product_name`, `keywords`, and `review_reason`, and for prompts that include site keywords but no category candidates.

- [ ] **Step 2: Run red test**

Run: `uv run pytest tests/test_llm_client.py -q`
Expected: missing parser/client method failures.

- [ ] **Step 3: Implement parser and client method**

Add a product-keyword parser and `generate_product_keywords(row, site_keywords)` method. Keep existing category generation method intact.

- [ ] **Step 4: Run green test**

Run: `uv run pytest tests/test_llm_client.py -q`
Expected: all tests pass.

### Task 3: Row Processor and UI Model

**Files:**
- Create: `src/moamong_app/keyword_processor.py`
- Modify: `src/moamong_app/ui/main_window.py`
- Test: `tests/test_keyword_processor.py`
- Test: `tests/test_ui_loading.py`

- [ ] **Step 1: Write failing tests**

Add processor and UI model tests that verify site keyword columns, row-by-row result updates, and yellow background for generated cells.

- [ ] **Step 2: Run red tests**

Run: `uv run pytest tests/test_keyword_processor.py tests/test_ui_loading.py -q`
Expected: missing processor and missing column/highlight behavior failures.

- [ ] **Step 3: Implement processor and UI model changes**

Route Run Sample / Run Full Auto through keyword-only processing. Do not require a category workbook to run this flow.

- [ ] **Step 4: Run green tests**

Run: `uv run pytest tests/test_keyword_processor.py tests/test_ui_loading.py -q`
Expected: all tests pass.

### Task 4: Export Behavior

**Files:**
- Modify: `src/moamong_app/excel_io.py`
- Test: `tests/test_excel_io.py`

- [ ] **Step 1: Write failing test**

Add export assertions for site keyword columns and for preserving original `마이카테`.

- [ ] **Step 2: Run red test**

Run: `uv run pytest tests/test_excel_io.py -q`
Expected: site keyword export missing or `마이카테` overwritten.

- [ ] **Step 3: Implement export**

Append site keyword columns and update only `상품명` and `키워드` for generated product-keyword results.

- [ ] **Step 4: Run full verification**

Run: `uv run pytest -q`
Expected: full suite passes.
