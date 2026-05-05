# Step Status And Run Mode Design

## Goal

Split row processing into visible steps and let the user choose whether completed rows are skipped or processed again.

## Scope

- Site keyword extraction runs as separate row steps for 11번가, 지마켓, 옥션, 네이버, and 쿠팡.
- LLM product-name/keyword generation runs after site keyword steps.
- The grid shows a status column for each site step plus an `LLM_step_status` column.
- `Run Sample` and `Run Full Auto` ask for a run mode before processing:
  - `완료 제외`: skip rows whose current or loaded `LLM_status` is `완료`.
  - `모두 작업`: process selected rows even if they are already complete.

## Data Flow

1. A run starts and asks for the run mode.
2. The selected rows are filtered if the user chooses `완료 제외`.
3. For each row, the processor emits incremental `RowProcessResult` snapshots:
   - one after each site keyword step
   - one after the LLM step
4. The UI applies each snapshot immediately so status and keyword cells update step-by-step.
5. Export writes site keywords, site step statuses, LLM step status, and final generated fields.

## Failure Behavior

- A site keyword failure marks only that site status as `실패: ...`; the row continues.
- The LLM step failure marks the row as `실패`, preserves site keyword results, and writes `LLM_step_status`.
- Skipped rows are not modified during that run.
