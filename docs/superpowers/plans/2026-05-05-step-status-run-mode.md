# Step Status Run Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make row processing visible step-by-step and add a run mode that can skip already completed rows.

**Architecture:** Add step status fields to row results, expose single-site keyword fetching, and make `KeywordProcessor` emit incremental snapshots. The UI consumes snapshots immediately and filters rows based on current or loaded `LLM_status` before a run.

**Tech Stack:** Python 3.11, PySide6, requests, openpyxl, pytest.

---

### Task 1: Step Status Model And Processor

**Files:**
- Modify: `src/moamong_app/models.py`
- Modify: `src/moamong_app/keyword_fetcher.py`
- Modify: `src/moamong_app/keyword_processor.py`
- Test: `tests/test_keyword_fetcher.py`
- Test: `tests/test_keyword_processor.py`

- [ ] Add failing tests for single-site keyword collection and processor snapshots.
- [ ] Run targeted tests and confirm failure.
- [ ] Implement `site_status_column`, single-site collection, `step_statuses`, and `process_steps`.
- [ ] Run targeted tests and confirm pass.

### Task 2: UI Step Columns And Run Mode

**Files:**
- Modify: `src/moamong_app/ui/main_window.py`
- Test: `tests/test_ui_loading.py`

- [ ] Add failing tests for step status columns, loaded completion detection, and generated row filtering.
- [ ] Run targeted tests and confirm failure.
- [ ] Add status columns, display/foreground/background support, and run mode filtering.
- [ ] Run targeted tests and confirm pass.

### Task 3: Export Step Statuses

**Files:**
- Modify: `src/moamong_app/excel_io.py`
- Test: `tests/test_excel_io.py`

- [ ] Add failing test for site and LLM step status export.
- [ ] Run targeted test and confirm failure.
- [ ] Append status columns during export and write values from `step_statuses`.
- [ ] Run full test suite.
