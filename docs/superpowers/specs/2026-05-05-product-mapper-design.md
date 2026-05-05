# Moamong Product Mapper Design

Date: 2026-05-05

## Goal

Build a Windows desktop app that loads a wholesale product Excel file and a store category Excel file, then uses an LLM to rewrite each product row for the user's own store. The app updates product name, keywords, and `마이카테` while preserving the original workbook structure as much as practical.

## Inputs

- `product_list.xlsx`
  - Primary sheet: `List1(1-8555)`
  - Observed size: 4,959 rows, 49 columns
  - Relevant existing columns include `상품코드`, `상품명`, `원본상품명(참고용)`, `옵션명`, `키워드`, `마이카테`, image columns, and marketplace category columns.
- `category.xlsx`
  - Primary sheet: `Mycate1(1-5917)`
  - Observed size: 5,950 rows, 26 columns
  - Only `마이카테` and `마이카테명` are required for the first version.

## First-Version Scope

Included:

- Windows desktop UI.
- File picker for product workbook and category workbook.
- Settings dialog for OpenAI-compatible LLM configuration.
- Sample N-row processing mode.
- Full automatic processing mode.
- Row-by-row LLM processing with progress updates.
- Category candidate lookup from `category.xlsx`.
- Optional category RAG/index implementation if simple search quality is insufficient.
- Result table with row status and generated fields.
- Export to a new Excel workbook.

Excluded from the first version:

- Wholesale-site login or automatic download.
- Provider-specific presets beyond OpenAI-compatible API fields.
- Local LLM provider setup.
- Marketplace-specific category conversion for columns other than `마이카테`.

## Technology Choice

Use Python desktop app:

- UI: PySide6.
- Excel read/write: pandas for tabular loading and openpyxl for workbook-preserving export.
- LLM calls: OpenAI-compatible HTTP API using `base_url`, `api_key`, and `model`.
- Category matching: start with local keyword/vector candidate generation; use Chroma if stronger retrieval is needed.
- Packaging: PyInstaller for Windows executable packaging.

This stack is chosen because the hard parts are Excel processing, row orchestration, LLM calls, and category matching. Python has direct, mature libraries for those tasks and keeps the first version smaller than WPF/WinUI or Electron.

## UI Design

Main window:

- Top toolbar:
  - Load product Excel.
  - Load category Excel.
  - Run Sample.
  - Run Full Auto.
  - Pause/Stop.
  - Settings.
- Run controls:
  - Mode selector: sample or full.
  - Sample row count input.
  - Buttons for sample run and full run.
- Processing table:
  - Shows source identifiers and generated fields.
  - Suggested columns: `상품코드`, `원본상품명`, existing `상품명`, generated product name, generated keywords, generated `마이카테명`, generated `마이카테`, confidence, status.
- Summary panel:
  - Total rows.
  - Completed, needs-review, failed counts.
  - Current mode and progress.
  - Export button.
- Log panel:
  - File loading events.
  - LLM request errors.
  - Category lookup notes.
  - Export result.

Settings dialog:

- LLM `base_url`.
- LLM `api_key`.
- LLM `model`.
- Temperature.
- Retry count.
- Request timeout.
- Category candidate count.
- Output filename suffix.

## Data Flow

1. Load `product_list.xlsx`.
2. Detect the product sheet. Use `List1(1-8555)` when present; otherwise use the first non-empty sheet.
3. Load `category.xlsx`.
4. Extract category records from `마이카테` and `마이카테명`.
5. Build a category search index.
6. User runs either sample N rows or full automatic processing.
7. For each selected row:
   - Gather row context from `상품명`, `원본상품명(참고용)`, `옵션명`, existing `키워드`, existing `마이카테`, and relevant image URL text where useful.
   - Retrieve category candidates.
   - Call LLM with row context and candidates.
   - Parse strict JSON result.
   - Validate required fields.
   - Update in-memory row result and UI status.
8. User reviews failed or low-confidence rows if needed.
9. Export a new workbook with updated columns.

## LLM Contract

The row processor asks the LLM to return strict JSON:

```json
{
  "product_name": "string",
  "keywords": ["string"],
  "mycate": "WB...",
  "mycate_name": "string",
  "confidence": 0.0,
  "review_reason": "string"
}
```

Validation rules:

- `product_name` must be non-empty.
- `keywords` must contain at least one keyword.
- `mycate` must exist in the loaded category list.
- `confidence` must be a number from 0 to 1.
- Rows below the configured confidence threshold are marked `검수필요`.
- Rows with malformed JSON, missing fields, or unknown category codes are marked `실패` or `검수필요` depending on whether partial output can be shown.

## Category Matching

Initial implementation:

- Normalize `마이카테명` by splitting `>` paths and removing extra spaces.
- Build a searchable text string from category path tokens.
- Use simple lexical scoring to choose candidate categories from product name, original product name, and existing keywords.
- Pass top N category candidates to the LLM.

Optional enhancement:

- Add Chroma as a local vector store for `마이카테명` records.
- Rebuild the index when a different `category.xlsx` is loaded.
- Store the index under the app data directory, keyed by category file hash.

The design allows Chroma without requiring it in the first working version.

## Excel Output

The app writes a new workbook rather than overwriting the source by default.

Updated columns:

- `상품명`
- `키워드`
- `마이카테`

Additional audit columns may be appended:

- `LLM_상품명`
- `LLM_키워드`
- `LLM_마이카테`
- `LLM_마이카테명`
- `LLM_confidence`
- `LLM_status`
- `LLM_review_reason`

Default behavior should avoid destroying source data. The app can show an option to either update original columns directly, append audit columns, or do both.

## Error Handling

- Missing required workbook columns: block processing and show the missing column list.
- Empty category list: block processing.
- LLM request failure: retry according to settings, then mark row failed.
- LLM malformed response: mark row failed and keep raw response in the row log.
- Unknown category code: mark row as needs-review.
- User stop: finish the active row if practical, then stop the queue.
- Export failure: show the file path and exception message.

## Testing

Unit tests:

- Load product workbook sheet and detect columns.
- Load category workbook and extract `마이카테`/`마이카테명`.
- Category candidate scoring.
- LLM JSON parsing and validation.
- Row status transitions.

Integration tests:

- Run sample processing with a fake LLM client.
- Export updated workbook and verify the changed columns.

Manual verification:

- Load the provided `product_list.xlsx` and `category.xlsx`.
- Run sample mode on a small row count.
- Confirm generated fields display in the table.
- Export a workbook and open it in Excel.

## Implementation Defaults

- Confidence threshold for `검수필요`: default to `0.80`, configurable in Settings.
- Output behavior: append audit columns and also update the original `상품명`, `키워드`, and `마이카테` columns in the exported copy. The source workbook is never overwritten.
- Keyword constraint: generate 10 to 20 comma-separated Korean shopping search keywords, avoiding duplicates and avoiding claims not supported by the source row.
- Product name constraint: generate a concise Korean product name suitable for the user's store, based primarily on `원본상품명(참고용)`, `상품명`, and `옵션명`.
- Category candidate count: pass the top 8 candidate categories to the LLM by default, configurable in Settings.
