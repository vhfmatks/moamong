# SQLite Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache loaded Excel data and row processing results in SQLite, then export from cached state.

**Architecture:** Add a focused SQLite repository that persists product workbook metadata, product rows, categories, and row results. Keep Excel parsing/export logic unchanged and wire the repository into the existing PySide window at load, run, startup, export, and truncate points.

**Tech Stack:** Python 3.11, stdlib `sqlite3`, PySide6, openpyxl, pytest.

---

### Task 1: SQLite Store

**Files:**
- Create: `src/moamong_app/sqlite_store.py`
- Create: `tests/test_sqlite_store.py`

- [ ] Write failing tests for saving/loading product workbook data, categories, row results, and truncate.
- [ ] Implement schema creation, JSON serialization, upsert methods, load methods, and truncate.
- [ ] Run `uv run pytest tests/test_sqlite_store.py`.

### Task 2: UI Wiring

**Files:**
- Modify: `src/moamong_app/ui/main_window.py`
- Modify: `tests/test_ui_loading.py`

- [ ] Load cached product/category/result state when the window starts.
- [ ] Save product/category Excel payloads into SQLite after successful load.
- [ ] Save row results while processing so export can use DB-backed state.
- [ ] Add a `Truncate DB` toolbar button that clears DB and current UI state after confirmation.
- [ ] Run `uv run pytest tests/test_ui_loading.py`.

### Task 3: Verification

- [ ] Run `uv run pytest`.
- [ ] Confirm existing Excel export behavior is unchanged.
