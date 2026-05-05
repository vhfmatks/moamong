# Site Keyword Product Generation Design

## Goal

Use `원본상품명(참고용)` to collect shopping-site keyword suggestions, then use those suggestions as LLM context to generate only the store-facing `상품명` and `키워드` values.

## Scope

- In scope: site keyword collection, site keyword columns in the grid/export, LLM JSON parsing for product name and keywords, row-by-row UI updates, yellow highlighting for changed/generated cells.
- Out of scope: `마이카테`, `마이카테명`, category workbook mapping, RAG/category matching during this flow.

## Data Flow

1. The product workbook is loaded as before.
2. When a row is processed, the app reads `원본상품명(참고용)`.
3. The app queries the shopping-site keyword providers currently represented in `sample.py`.
4. The grid receives one generated column per site, such as `쿠팡_키워드` and `네이버_키워드`.
5. The app sends the original product name and site keyword lists to the LLM.
6. The LLM returns strict JSON with `product_name`, `keywords`, and optional `review_reason`.
7. The app updates the current row immediately. Generated/changed cells are highlighted yellow.

## Components

- `keyword_fetcher.py`: owns shopping-site keyword lookup and site display names.
- `llm_client.py`: adds product-keyword JSON parsing and an LLM call that excludes category fields.
- `keyword_processor.py`: orchestrates one row of site keyword lookup and LLM generation.
- `ProductTableModel`: displays site keyword columns and generated result columns, and highlights generated cells.
- `excel_io.py`: exports generated site keyword columns and final `상품명`/`키워드` values without changing `마이카테`.

## Error Handling

- If a site keyword lookup fails, that site column shows an error marker for the row and processing continues.
- If the LLM response is invalid JSON or missing required fields, the row status becomes `실패`.
- A row with no `원본상품명(참고용)` falls back to `상품명` for keyword lookup.

## Testing

- Unit tests cover site keyword collection normalization and per-site error isolation.
- Unit tests cover product-keyword JSON parsing and prompt content.
- Processor tests verify that site keywords are passed into the LLM and row results preserve source category values.
- UI model tests verify generated columns and yellow highlighting.
- Export tests verify that `마이카테` is not modified by product-keyword generation.
