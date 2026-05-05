# Sales Oriented Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the product-name/keyword LLM prompt for sales-oriented Korean ecommerce output.

**Architecture:** Keep the existing OpenAI-compatible client and parser. Update only the product-keyword prompt and tests that inspect the outgoing request.

**Tech Stack:** Python 3.11, pytest.

---

### Task 1: Prompt Contract Test

**Files:**
- Modify: `tests/test_llm_client.py`

- [ ] Add assertions that the product-keyword prompt includes sales/search conversion rules.
- [ ] Run `uv run pytest tests/test_llm_client.py::test_client_generates_product_keywords_without_category_prompt -q` and confirm failure.

### Task 2: Prompt Update

**Files:**
- Modify: `src/moamong_app/llm_client.py`

- [ ] Update `_build_product_keyword_prompt` and the system message for ecommerce SEO and conversion.
- [ ] Run the targeted test and confirm pass.
- [ ] Run `uv run pytest -q`.
