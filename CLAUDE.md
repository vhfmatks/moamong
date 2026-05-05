# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Moamong Product Mapper — a PySide6 desktop app for Korean ecommerce sellers. It loads product and category Excel workbooks, queries autocomplete APIs of five Korean shopping sites (11번가, 지마켓, 옥션, 네이버, 쿠팡), passes everything to an OpenAI-compatible LLM, and writes optimized 상품명 / 키워드 / 마이카테 back into a new xlsx. State (loaded workbooks, categories, per-row results) and a Chroma vector store of categories are cached under `~/.moamong_product_mapper/`.

Python 3.11+. Dependencies are pinned in `uv.lock` (project uses `uv`); the build is plain setuptools with `[tool.setuptools.packages.find] where = ["src"]`.

## Common commands

```bash
# Install (use uv since uv.lock is committed)
uv sync --extra dev

# Run the GUI app
uv run python -m moamong_app

# Run all tests
uv run pytest

# Run a single test file / test
uv run pytest tests/test_keyword_processor.py
uv run pytest tests/test_keyword_processor.py::TestName::test_case

# Headless UI tests (Qt needs a display; force offscreen if running over SSH/CI)
QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_loading.py

# Standalone keyword scraper CLI (bypasses the app entirely)
uv run python sample.py 버터 --pretty
```

`pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]` for pytest, so `import moamong_app...` works without installing.

## Architecture

The processing pipeline is what binds the modules together. Reading these in order will save time:

1. **`models.py`** — shared dataclasses. `RowStatus` is a `str` Enum with **Korean** values (`대기`, `처리중`, `완료`, `검수필요`, `실패`); these strings are persisted into Excel and SQLite, so do not localize them. `ProductRow.text(column)` is the canonical way to read row cells (handles None/strip).

2. **`keyword_processor.py` → `KeywordProcessor.process_steps(row)`** is the active pipeline. It is a generator that yields a `RowProcessResult` after every step so the UI can stream progress:
   - LLM extracts a concise site search query from the row (`generate_site_search_keyword`); on failure it falls back to `원본상품명(참고용)` or `상품명`.
   - For each site in `SITE_ORDER` (`11st, gmarket, auction, naver, coupang`), call `collector.collect_site(site, keyword)`.
   - LLM produces final `product_name` + `keywords` from all site suggestions (`generate_product_keywords`).
   - Step status keys in `result.step_statuses` are `search_keyword`, the five site IDs, and `llm`. Values are Korean (`처리중` / `완료` / `실패: ...`).

3. **`row_processor.py` → `RowProcessor`** is an **older** category-mapping flow (uses `CategoryMatcher` + LLM `generate` to pick a `마이카테` and emits `NEEDS_REVIEW` below `confidence_threshold`). The main UI now uses `KeywordProcessor` instead, but `RowProcessor` is still tested and importable. Don't conflate the two — `KeywordProcessor` does **not** assign `마이카테`.

4. **`llm_client.py` → `OpenAICompatibleClient`** posts to `{base_url}/chat/completions` with `response_format: {type: "json_object"}`. If the server returns "response_format … not supported", the request is retried without that key inside the same attempt before counting it against `retry_count`. Strict JSON parsing lives in `parse_generated_row`, `parse_generated_product_keywords`, `parse_site_search_keyword`; all raise `LlmResponseError`. The three `_build_*_prompt` functions encode product-business rules in Korean — keep edits minimal and aligned with the existing constraints (e.g. keyword counts: 10–20 for legacy `_build_prompt`, 20–30 for `_build_product_keyword_prompt`).

5. **`keyword_fetcher.py`** — five hand-rolled scrapers for site autocomplete endpoints (11st JSON, gmarket JSON, auction SOAP, naver `ac.search`, coupang JSONP with synthesized cookies). Endpoint quirks are documented in `docs/keyword-api-research.md`. `unique()` HTML-unescapes and dedupes. Display names: `11st→11번가, gmarket→지마켓, auction→옥션, naver→네이버, coupang→쿠팡`. Excel column helpers: `site_keyword_column(site)` → `"{display}_키워드"`, `site_status_column(site)` → `"{display}_status"`.

6. **`excel_io.py`** — reads with `openpyxl` in `read_only` mode. The product workbook **must** contain `상품코드, 상품명, 원본상품명(참고용), 옵션명, 키워드, 마이카테`; loader prefers the first sheet whose name starts with `List1`. Category workbook needs `마이카테, 마이카테명`. `export_results` opens the original workbook again (not read-only), appends any missing headers, and refuses to overwrite the source path. The exported `LLM_*` columns and the per-site keyword/status columns are added even if those columns weren't in the input.

7. **`category_vector_store.py`** — wraps a Chroma `PersistentClient` at `~/.moamong_product_mapper/chroma`, collection `moamong_categories`. `refresh()` recomputes embeddings via `OpenAICompatibleEmbeddingClient` (batched by `DEFAULT_BATCH_SIZE = 100`), deletes and recreates the collection, and stores `source_hash` (sha256 of source xlsx) in collection metadata. Refresh is triggered by the UI when the category workbook is loaded — it runs inside the load worker thread and a failure is surfaced via `CategoryLoadResult.vector_error`, not raised.

8. **`category_matcher.py`** — pure-Python lexical scorer (token bag with `ㄱ-ㅎ가-힣A-Za-z0-9` regex, weight 3 for token-in-name, 1 for substring, +2.5 boost if existing `마이카테` matches). Used by `RowProcessor`.

9. **`sqlite_store.py`** — single-file cache at `~/.moamong_product_mapper/moamong.sqlite3`. Tables: `product_meta` (single row), `product_rows`, `categories`, `results`. `RowProcessResult` is round-tripped through JSON via `_result_to_payload` / `_payload_to_result`. `truncate()` clears all four tables; the UI exposes this as the "Truncate DB" button.

10. **`settings.py`** — `LlmSettings` JSON at `~/.moamong_product_mapper/settings.json`. Defaults to OpenAI (`gpt-4.1-mini`, `text-embedding-3-small`); only fields present in `LlmSettings.fields` are read, so adding a new setting requires a default on the dataclass.

### UI layer (`src/moamong_app/ui/`)

- `MainWindow` (`main_window.py`) wires everything together. `WorkbookLoadWorker` runs Excel + Chroma refresh on a `QThread`. `_run_rows` runs the pipeline **on the GUI thread** with `QApplication.processEvents()` between rows/steps — long runs will freeze the window briefly per row; do not naively wrap `_run_rows` in a thread without porting `KeywordProcessor.process_steps` to signals.
- `ProductTableModel` shows the source workbook columns plus synthetic columns (`LLM_검색어`, `{site}_키워드`, `{site}_status`, `검색어_status`, `LLM_step_status`, and the `LLM_*` result columns). Generated/streaming cells are highlighted yellow.
- `RunMode` (`SKIP_DONE` / `RUN_ALL`) controls whether already-completed rows (`LLM_status == "완료"` either in memory or from the source workbook column) are reprocessed.
- `ProcessingDetailDialog` is non-modal and rendered every step via `_update_processing_details`.
- `SettingsDialog` "Test / Load Models" calls `fetch_available_models` (heuristic: ids containing `embed` go to embedding list) and then `test_llm_models` to sanity-check both endpoints.

## Conventions specific to this codebase

- **Korean strings are data, not UI copy.** Status enum values, step labels, and Excel headers are Korean and persisted; renaming them breaks the SQLite cache and any previously exported workbook.
- **All on-disk state lives in `~/.moamong_product_mapper/`** (settings.json, moamong.sqlite3, chroma/). Tests that touch settings/sqlite must take a `path=` override or the user's real cache will be mutated.
- **`from __future__ import annotations`** is used in every module — keep it when adding new files so PEP 604 unions and forward references stay valid on 3.11.
- **LLM responses must be JSON.** New prompts should follow the pattern in `_build_*_prompt`: a single `Return only a strict JSON object …` line, then explicit field rules. Add a parallel `parse_*` function that raises `LlmResponseError` rather than returning partial results.
- **`pytest` test discovery clash:** `test_llm_models` / `test_chat_model` / `test_embedding_model` in `llm_client.py` set `__test__ = False` so pytest doesn't pick them up as tests. Preserve that pattern when adding any other module-level callable starting with `test_`.
- The `_validate_candidate_choice` constraint in `llm_client.py` (mycate must come from the supplied candidates) is enforced **after** parsing — when adding new category fields, validate against `candidates` rather than trusting LLM output.

## Where to look

- `docs/keyword-api-research.md` — endpoint shapes, observed responses, auth requirements for the five sites.
- `docs/superpowers/plans/` and `docs/superpowers/specs/` — historical implementation plans (product mapper, sqlite cache, processing detail dialog, sales-oriented prompt, etc.). These describe the design intent; defer to the actual code when they conflict.
- `sample.py` — a self-contained copy of `keyword_fetcher.py`'s scrapers as a CLI; useful for debugging a single site without launching the GUI.
- `category.xlsx`, `product_list.xlsx` at repo root — real example workbooks matching the required schema.
