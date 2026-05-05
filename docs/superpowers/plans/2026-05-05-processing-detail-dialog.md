# Processing Detail Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an on-demand non-modal processing details dialog to the PySide6 product mapper.

**Architecture:** Create a dedicated `ProcessingDetailDialog` widget and wire it into `MainWindow`. Keep the existing processing loop, progress bar, table updates, and status label behavior intact.

**Tech Stack:** Python 3.11, PySide6, pytest.

---

### Task 1: Dialog Widget

**Files:**
- Create: `src/moamong_app/ui/processing_detail_dialog.py`
- Test: `tests/test_processing_detail_dialog.py`

- [ ] Write tests that instantiate the dialog, verify idle text, call `update_progress()`, and assert labels/table values.
- [ ] Run `pytest tests/test_processing_detail_dialog.py -v` and confirm the tests fail because the widget does not exist.
- [ ] Implement `ProcessingDetailDialog` with Qt labels, progress bar, and a two-column step table.
- [ ] Run `pytest tests/test_processing_detail_dialog.py -v` and confirm it passes.

### Task 2: Main Window Integration

**Files:**
- Modify: `src/moamong_app/ui/main_window.py`
- Test: `tests/test_ui_loading.py`

- [ ] Add a failing test that verifies `MainWindow` has a `Details` button and reuses a single dialog instance.
- [ ] Run the targeted test and confirm it fails because the button does not exist.
- [ ] Add `Details` button creation, `open_processing_details()`, dialog ownership, and updates from `_run_rows()`.
- [ ] Run the targeted test and confirm it passes.

### Task 3: Verification

**Files:**
- All changed files

- [ ] Run `pytest tests/test_processing_detail_dialog.py tests/test_ui_loading.py -v`.
- [ ] Run `pytest`.
- [ ] Confirm there are no test failures.
