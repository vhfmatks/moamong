# Processing Detail Dialog Design

## Goal

Show detailed row-processing progress on demand while keeping the existing table, status label, and progress bar workflow unchanged.

## User Flow

The main toolbar gets a `Details` button. Clicking it opens a non-modal dialog that can stay visible while rows are processing. The dialog also works when processing is idle, showing the latest known processing state or an idle message.

## Dialog Content

The dialog shows:

- Overall row progress as `current / total rows`
- Current product row index and product name
- Generated search keyword
- Step statuses for search keyword generation, Coupang, Naver, 11st, Auction, Gmarket, and LLM
- Current final status or error message

## Architecture

Add a focused `ProcessingDetailDialog` class under `moamong_app.ui`. `MainWindow` owns at most one dialog instance and updates it from `_run_rows()` whenever row-level or step-level state changes. The processing loop remains synchronous and continues to call `QApplication.processEvents()` as it does today.

## Testing

Add PySide6 UI tests for dialog rendering and main-window integration:

- The dialog displays idle state before processing.
- Updating the dialog with a `RowProcessResult` reflects row progress, product name, search keyword, step statuses, and message.
- `MainWindow` exposes a `Details` button and opens the same dialog instance repeatedly instead of creating duplicates.
