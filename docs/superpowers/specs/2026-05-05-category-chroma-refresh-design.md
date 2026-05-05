# Category Chroma Refresh Design

Date: 2026-05-05

## Goal

When a category Excel file is uploaded, refresh a local Chroma DB category collection so future embedding lookup can find an appropriate `마이카테` code from category text.

This work only updates the category vector store. It does not connect Chroma lookup to product row processing yet.

## Scope

Included:

- Read category rows from the existing category Excel loader.
- Use `마이카테` as the stable category id.
- Use `마이카테명` as the embedded document text.
- Store category metadata needed for later lookup and auditing.
- Refresh Chroma after the category workbook loads successfully.
- Report Chroma refresh failure separately from Excel loading failure.
- Add focused tests for document construction, refresh behavior, and UI worker orchestration where practical.

Excluded:

- Product row category lookup through Chroma.
- Replacing the existing lexical `CategoryMatcher`.
- Incremental per-row updates inside Chroma.
- Background embedding progress per category batch beyond a coarse status message.

## Architecture

Add a new `category_vector_store.py` module that owns Chroma-specific behavior. The existing `excel_io.py` stays responsible only for workbook parsing.

The vector store API should be small:

- Build a deterministic source hash from the category Excel file contents.
- Convert `Category(mycate, name)` records into Chroma ids, documents, and metadata.
- Refresh the configured collection from a complete category list.

Default storage should live under the app data directory, near existing settings:

- Base app directory: `Path.home() / ".moamong_product_mapper"`
- Chroma path: `Path.home() / ".moamong_product_mapper" / "chroma"`
- Collection name: `moamong_categories`

The collection record shape:

- `id`: category `마이카테`
- `document`: category `마이카테명`
- `metadata.mycate`: category `마이카테`
- `metadata.name`: category `마이카테명`
- `metadata.source_file`: uploaded Excel file path
- `metadata.source_hash`: hash of the uploaded Excel file

## Data Flow

1. User clicks `Load Category Excel`.
2. The existing workbook worker parses `마이카테` and `마이카테명`.
3. After parsing succeeds, the same load flow refreshes Chroma with the parsed categories and source file path.
4. The UI still creates the in-memory `CategoryMatcher` from the parsed categories.
5. If Chroma refresh succeeds, the status includes the loaded category count and DB refresh result.
6. If Chroma refresh fails, the categories still remain loaded, but the user sees a warning/status message explaining the DB refresh failure.

## Embedding Provider

Use Chroma's embedding-function integration with the configured OpenAI-compatible settings where possible:

- API key: `settings.api_key`
- Base URL: `settings.base_url`
- Embedding model: `settings.embedding_model`

The implementation should keep the embedding dependency isolated so tests can inject a fake collection or fake vector store without making network calls.

## Refresh Semantics

The first implementation can rebuild the collection for the uploaded category source:

- Clear existing `moamong_categories` records.
- Add all valid category records from the uploaded Excel file.

This is simple and deterministic. File-hash reuse can be added as an optimization after the refresh API exists and is tested.

Duplicate `마이카테` rows should be deduplicated by keeping the last non-empty `마이카테명`, because Chroma ids must be unique and a later row usually represents the more recent source value.

## Error Handling

- Missing `chromadb` dependency: show a Chroma refresh error that explains the dependency is not installed.
- Missing API key: skip refresh and show that an API key is required for embedding.
- Embedding/API failure: keep loaded categories, clear no product data, and show the Chroma error.
- Empty category list: blocked by the existing category loader.
- Invalid category rows: skipped by the existing category loader when either `마이카테` or `마이카테명` is empty.

## Testing

Unit tests:

- Build Chroma ids/documents/metadata from `Category` records.
- Deduplicate duplicate `마이카테` values with the later name winning.
- Refresh calls collection delete/recreate or clear/add with expected ids, documents, and metadata.
- Missing API key returns or raises a controlled refresh error.

Integration-adjacent tests:

- Category workbook loading can feed the vector store refresh API without requiring real Chroma or network access.
- The UI load worker can emit a successful category payload even if vector refresh is handled separately by the main window.

Manual verification:

- Load `category.xlsx`.
- Confirm status reports category count and Chroma refresh success or a clear refresh error.
- Inspect the Chroma directory under `.moamong_product_mapper/chroma`.

## Implementation Notes

Add `chromadb` to project dependencies only when implementation begins. Tests should avoid importing the real package at module import time, so the rest of the app remains importable if Chroma is unavailable.

The future lookup API should return `CategoryCandidate` records so it can later replace or augment `CategoryMatcher.match()` without changing row-processing contracts.
