# LLM Model Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Settings dialog support for testing both the selected chat LLM model and selected embedding model.

**Architecture:** Keep network calls in `moamong_app.llm_client`, expose small model-test helpers, and let `SettingsDialog` orchestrate loading model lists plus invoking an injected tester. Preserve the existing editable combo-box behavior so manually entered model ids remain valid even when `/models` does not return them.

**Tech Stack:** Python 3.11, PySide6, requests, pytest, OpenAI-compatible `/models`, `/chat/completions`, and `/embeddings` endpoints.

---

## Implementation Context

This workspace is not a git repository. `git status --short` returns `fatal: not a git repository`, so commit steps are intentionally omitted. Use the checkbox list and test runs as the progress record.

The approved spec is `docs/superpowers/specs/2026-05-05-llm-model-test-design.md`.

## File Structure

- Modify `src/moamong_app/llm_client.py`
  - Owns OpenAI-compatible model lookup and model smoke tests.
  - Adds `ModelTestResult`, `test_chat_model`, `test_embedding_model`, and `test_llm_models`.
- Modify `src/moamong_app/ui/settings_dialog.py`
  - Adds `model_tester` dependency injection.
  - Runs both model tests after `/models` succeeds and combo boxes are refreshed.
- Modify `tests/test_llm_client.py`
  - Adds focused tests for chat request payloads, embedding request payloads, malformed embedding responses, and combined test result.
- Modify `tests/test_settings_dialog.py`
  - Updates existing model-loading test to inject a fake model tester.
  - Adds failure-path coverage for model-test warnings.

## Task 1: LLM Client Model Test API

**Files:**

- Modify: `tests/test_llm_client.py`
- Modify: `src/moamong_app/llm_client.py`

- [ ] **Step 1: Write failing client tests**

Add these imports to the existing import block in `tests/test_llm_client.py`:

```python
    ModelTestResult,
    test_chat_model,
    test_embedding_model,
    test_llm_models,
```

Append these tests to `tests/test_llm_client.py`:

```python
def test_chat_model_posts_minimal_chat_completion_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "{\"ok\": true}"
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    content = test_chat_model(
        LlmSettings(
            base_url="https://llm.example.test/v1/",
            api_key="secret-key",
            model="chat-model",
            timeout_seconds=7,
            retry_count=0,
        )
    )

    assert content == "{\"ok\": true}"
    assert captured["args"] == ("https://llm.example.test/v1/chat/completions",)
    assert captured["kwargs"]["headers"] == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
    }
    assert captured["kwargs"]["timeout"] == 7
    payload = captured["kwargs"]["json"]
    assert payload["model"] == "chat-model"
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"


def test_embedding_model_posts_embeddings_request_and_returns_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "index": 0,
                        "embedding": [0.1, 0.2, 0.3],
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    dimension = test_embedding_model(
        LlmSettings(
            base_url="https://llm.example.test/v1/",
            api_key="secret-key",
            embedding_model="embed-model",
            timeout_seconds=9,
            retry_count=0,
        )
    )

    assert dimension == 3
    assert captured["args"] == ("https://llm.example.test/v1/embeddings",)
    assert captured["kwargs"]["headers"] == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
    }
    assert captured["kwargs"]["json"] == {
        "model": "embed-model",
        "input": ["테스트"],
    }
    assert captured["kwargs"]["timeout"] == 9


def test_embedding_model_rejects_malformed_embedding_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"index": 0, "embedding": []}]}

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    with pytest.raises(LlmResponseError, match="embedding response item is invalid"):
        test_embedding_model(LlmSettings(api_key="secret-key", retry_count=0))


def test_llm_models_returns_combined_success_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(settings: LlmSettings) -> str:
        assert settings.model == "chat-model"
        return "{\"ok\": true}"

    def fake_embedding(settings: LlmSettings) -> int:
        assert settings.embedding_model == "embed-model"
        return 3

    monkeypatch.setattr("moamong_app.llm_client.test_chat_model", fake_chat)
    monkeypatch.setattr("moamong_app.llm_client.test_embedding_model", fake_embedding)

    result = test_llm_models(
        LlmSettings(
            model="chat-model",
            embedding_model="embed-model",
        )
    )

    assert result == ModelTestResult(
        chat_model="chat-model",
        embedding_model="embed-model",
        chat_ok=True,
        embedding_ok=True,
        chat_message="Received non-empty chat response",
        embedding_message="Received 3-dimension embedding",
    )
```

- [ ] **Step 2: Run the failing client tests**

Run:

```powershell
uv run pytest tests/test_llm_client.py::test_chat_model_posts_minimal_chat_completion_request tests/test_llm_client.py::test_embedding_model_posts_embeddings_request_and_returns_dimension tests/test_llm_client.py::test_embedding_model_rejects_malformed_embedding_response tests/test_llm_client.py::test_llm_models_returns_combined_success_result -q
```

Expected: FAIL during import because `ModelTestResult`, `test_chat_model`, `test_embedding_model`, and `test_llm_models` do not exist yet.

- [ ] **Step 3: Add the client model-test implementation**

In `src/moamong_app/llm_client.py`, add this dataclass after `AvailableModels`:

```python
@dataclass(frozen=True)
class ModelTestResult:
    chat_model: str
    embedding_model: str
    chat_ok: bool
    embedding_ok: bool
    chat_message: str
    embedding_message: str
```

Add these functions after `fetch_available_models`:

```python
def test_llm_models(settings: LlmSettings) -> ModelTestResult:
    try:
        test_chat_model(settings)
    except LlmResponseError as exc:
        raise LlmResponseError(f"Chat model test failed: {exc}") from exc

    try:
        embedding_dimension = test_embedding_model(settings)
    except LlmResponseError as exc:
        raise LlmResponseError(f"Embedding model test failed: {exc}") from exc

    return ModelTestResult(
        chat_model=settings.model,
        embedding_model=settings.embedding_model,
        chat_ok=True,
        embedding_ok=True,
        chat_message="Received non-empty chat response",
        embedding_message=f"Received {embedding_dimension}-dimension embedding",
    )


def test_chat_model(settings: LlmSettings) -> str:
    if not settings.api_key.strip():
        raise LlmResponseError("API key is required for chat model test")
    if not settings.model.strip():
        raise LlmResponseError("chat model is required")

    payload = {
        "model": settings.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "Return only strict JSON.",
            },
            {
                "role": "user",
                "content": "Return {\"ok\": true}.",
            },
        ],
    }
    content = _chat_completion_content(settings, payload).strip()
    if not content:
        raise LlmResponseError("chat model test returned empty content")
    return content


def test_embedding_model(settings: LlmSettings) -> int:
    if not settings.api_key.strip():
        raise LlmResponseError("API key is required for embedding model test")
    if not settings.embedding_model.strip():
        raise LlmResponseError("embedding model is required")

    url = f"{settings.base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.embedding_model, "input": ["테스트"]}

    last_error: Exception | None = None
    attempts = max(1, settings.retry_count + 1)
    for _ in range(attempts):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.timeout_seconds,
            )
            _raise_for_status(response)
            return len(_extract_single_embedding(response.json()))
        except (requests.RequestException, LlmResponseError, ValueError) as exc:
            last_error = exc

    raise LlmResponseError(f"embedding model test failed: {last_error}") from last_error
```

Add this helper near the existing response helper functions:

```python
def _extract_single_embedding(payload: Any) -> list[float]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise LlmResponseError("embedding response must contain a data list")

    data = payload["data"]
    if not data:
        raise LlmResponseError("embedding response must contain at least one item")

    item = data[0]
    if not isinstance(item, dict):
        raise LlmResponseError("embedding response item is invalid")

    embedding = item.get("embedding")
    if (
        not isinstance(embedding, list)
        or not embedding
        or any(
            isinstance(value, bool) or not isinstance(value, int | float)
            for value in embedding
        )
    ):
        raise LlmResponseError("embedding response item is invalid")

    return [float(value) for value in embedding]
```

- [ ] **Step 4: Run the client tests until they pass**

Run:

```powershell
uv run pytest tests/test_llm_client.py::test_chat_model_posts_minimal_chat_completion_request tests/test_llm_client.py::test_embedding_model_posts_embeddings_request_and_returns_dimension tests/test_llm_client.py::test_embedding_model_rejects_malformed_embedding_response tests/test_llm_client.py::test_llm_models_returns_combined_success_result -q
```

Expected: PASS for all four tests.

## Task 2: Settings Dialog Orchestration

**Files:**

- Modify: `tests/test_settings_dialog.py`
- Modify: `src/moamong_app/ui/settings_dialog.py`

- [ ] **Step 1: Write failing dialog tests**

Update imports in `tests/test_settings_dialog.py`:

```python
from moamong_app.llm_client import AvailableModels, ModelTestResult
```

Replace the body of `test_settings_dialog_loads_models_into_selectable_fields` with this version:

```python
def test_settings_dialog_loads_models_into_selectable_fields() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    seen_loader_settings: list[LlmSettings] = []
    seen_tester_settings: list[LlmSettings] = []

    def fake_loader(settings: LlmSettings) -> AvailableModels:
        seen_loader_settings.append(settings)
        return AvailableModels(
            llm_models=["chat-a", "chat-b"],
            embedding_models=["embed-a", "embed-b"],
            all_models=["chat-a", "chat-b", "embed-a", "embed-b"],
        )

    def fake_tester(settings: LlmSettings) -> ModelTestResult:
        seen_tester_settings.append(settings)
        return ModelTestResult(
            chat_model=settings.model,
            embedding_model=settings.embedding_model,
            chat_ok=True,
            embedding_ok=True,
            chat_message="Received non-empty chat response",
            embedding_message="Received 3-dimension embedding",
        )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="chat-b",
            embedding_model="embed-b",
        ),
        model_loader=fake_loader,
        model_tester=fake_tester,
    )

    dialog.load_models()

    assert app is not None
    assert seen_loader_settings[0].base_url == "https://llm.example.test/v1"
    assert seen_loader_settings[0].api_key == "secret-key"
    assert seen_tester_settings[0].model == "chat-b"
    assert seen_tester_settings[0].embedding_model == "embed-b"
    assert dialog.model_combo.currentText() == "chat-b"
    assert dialog.embedding_model_combo.currentText() == "embed-b"
    assert [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())] == ["chat-a", "chat-b"]
    assert [dialog.embedding_model_combo.itemText(i) for i in range(dialog.embedding_model_combo.count())] == ["embed-a", "embed-b"]
    assert dialog.load_models_button.text() == "Loaded 4 Models / Chat OK / Embedding OK"
```

Append this failure-path test:

```python
def test_settings_dialog_warns_when_model_test_fails(monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    warnings: list[tuple[str, str]] = []

    def fake_loader(settings: LlmSettings) -> AvailableModels:
        return AvailableModels(
            llm_models=["chat-a"],
            embedding_models=["embed-a"],
            all_models=["chat-a", "embed-a"],
        )

    def failing_tester(settings: LlmSettings) -> ModelTestResult:
        raise RuntimeError("Chat model test failed: missing model")

    monkeypatch.setattr(
        "moamong_app.ui.settings_dialog.QMessageBox.warning",
        lambda parent, title, message: warnings.append((title, message)),
    )

    dialog = SettingsDialog(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            model="custom-chat",
            embedding_model="custom-embed",
        ),
        model_loader=fake_loader,
        model_tester=failing_tester,
    )

    dialog.load_models()

    assert app is not None
    assert warnings == [("Model Test", "Chat model test failed: missing model")]
    assert dialog.model_combo.currentText() == "custom-chat"
    assert dialog.embedding_model_combo.currentText() == "custom-embed"
```

- [ ] **Step 2: Run the failing dialog tests**

Run:

```powershell
uv run pytest tests/test_settings_dialog.py::test_settings_dialog_loads_models_into_selectable_fields tests/test_settings_dialog.py::test_settings_dialog_warns_when_model_test_fails -q
```

Expected: FAIL because `SettingsDialog.__init__()` does not accept `model_tester`.

- [ ] **Step 3: Update SettingsDialog imports**

In `src/moamong_app/ui/settings_dialog.py`, replace the LLM import with:

```python
from moamong_app.llm_client import (
    AvailableModels,
    ModelTestResult,
    fetch_available_models,
    test_llm_models,
)
```

- [ ] **Step 4: Add injectable model tester**

Change `SettingsDialog.__init__` signature to:

```python
    def __init__(
        self,
        settings: LlmSettings,
        parent: QWidget | None = None,
        model_loader: Callable[[LlmSettings], AvailableModels] = fetch_available_models,
        model_tester: Callable[[LlmSettings], ModelTestResult] = test_llm_models,
    ) -> None:
```

Inside `__init__`, after `self.model_loader = model_loader`, add:

```python
        self.model_tester = model_tester
```

- [ ] **Step 5: Run tests to confirm the failure moves to behavior**

Run:

```powershell
uv run pytest tests/test_settings_dialog.py::test_settings_dialog_loads_models_into_selectable_fields tests/test_settings_dialog.py::test_settings_dialog_warns_when_model_test_fails -q
```

Expected: FAIL because `load_models()` does not call `model_tester` and still sets the old button text.

- [ ] **Step 6: Extend `load_models()` to test both selected models**

Replace `SettingsDialog.load_models()` with:

```python
    def load_models(self) -> None:
        try:
            models = self.model_loader(self.to_settings())
        except Exception as exc:
            QMessageBox.warning(self, "Model Test", str(exc))
            return

        self._set_combo_items(self.model_combo, models.llm_models)
        self._set_combo_items(self.embedding_model_combo, models.embedding_models)

        try:
            test_result = self.model_tester(self.to_settings())
        except Exception as exc:
            QMessageBox.warning(self, "Model Test", str(exc))
            return

        self.load_models_button.setText(
            f"Loaded {len(models.all_models)} Models / "
            f"{'Chat OK' if test_result.chat_ok else 'Chat Failed'} / "
            f"{'Embedding OK' if test_result.embedding_ok else 'Embedding Failed'}"
        )
```

- [ ] **Step 7: Run dialog tests until they pass**

Run:

```powershell
uv run pytest tests/test_settings_dialog.py -q
```

Expected: PASS for all Settings dialog tests.

## Task 3: Full Verification

**Files:**

- No new source files.

- [ ] **Step 1: Run focused LLM and dialog tests**

Run:

```powershell
uv run pytest tests/test_llm_client.py tests/test_settings_dialog.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Optionally launch the app for manual Settings smoke test**

Run:

```powershell
uv run python -m moamong_app
```

Expected manual behavior:

- Settings opens.
- `Model` and `Embedding Model` remain editable.
- `Test / Load Models` loads available model ids.
- The same click tests the selected chat and embedding models.
- On success, the button text becomes `Loaded <N> Models / Chat OK / Embedding OK`.
- On failure, a `Model Test` warning identifies the failing stage.

## Self-Review

Spec coverage:

- Editable `Model` and `Embedding Model` settings remain unchanged in `SettingsDialog`.
- Existing `/models` loading remains in `fetch_available_models` and `SettingsDialog.load_models`.
- Chat model testing is covered by Task 1.
- Embedding model testing is covered by Task 1.
- Clear success and failure UI behavior is covered by Task 2.
- Network-free UI tests are covered by injected `model_loader` and `model_tester`.

Placeholder scan:

- No placeholder markers or unspecified implementation steps remain.

Type consistency:

- `ModelTestResult` fields in Task 1 match the import and UI behavior in Task 2.
- `test_llm_models(settings)` returns `ModelTestResult` and is used as the default `model_tester`.
- `test_chat_model(settings)` and `test_embedding_model(settings)` use `LlmSettings.model` and `LlmSettings.embedding_model` respectively.
