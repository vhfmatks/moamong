# LLM Model Test Design

Date: 2026-05-05

## Goal

Extend the Settings dialog so the user can enter or select both the chat LLM model and embedding model, then test both models before running product processing or category embedding refresh.

## Current State

The app already has OpenAI-compatible settings:

- `base_url`
- `api_key`
- `model`
- `embedding_model`
- temperature, timeout, retry count, and other processing settings

The Settings dialog already provides editable combo boxes for `Model` and `Embedding Model`. It also has a `Test / Load Models` button that calls `/models`, separates likely chat models from likely embedding models, and fills the combo boxes. That button does not currently prove that the selected chat model can complete a chat request or that the selected embedding model can create embeddings.

## Scope

Included:

- Keep editable `Model` and `Embedding Model` settings.
- Extend the existing `Test / Load Models` flow to test both selected models.
- Test the selected chat model with a minimal `/chat/completions` request.
- Test the selected embedding model with a minimal `/embeddings` request.
- Surface clear success and failure messages in the Settings dialog.
- Add focused unit tests for request payloads, response validation, and dialog orchestration.

Excluded:

- Provider-specific model presets.
- Streaming tests.
- Long prompt or product-row quality tests.
- Automatic model selection.
- Background threading for the Settings dialog test flow.

## User Flow

1. User opens Settings.
2. User enters `Base URL`, `API Key`, `Model`, and `Embedding Model`, or loads available models.
3. User clicks `Test / Load Models`.
4. The app calls `/models` and updates the combo boxes when the endpoint is available.
5. The app tests the selected chat model.
6. The app tests the selected embedding model.
7. If all steps succeed, the button text reports model count plus chat and embedding success.
8. If a step fails, the dialog shows a warning that identifies the failed stage.

## API Design

Add a small result model in `llm_client.py`:

- `ModelTestResult`
  - `chat_model`: selected chat model id
  - `embedding_model`: selected embedding model id
  - `chat_ok`: bool
  - `embedding_ok`: bool
  - `chat_message`: short diagnostic string
  - `embedding_message`: short diagnostic string

Add test helpers:

- `test_chat_model(settings: LlmSettings) -> str`
  - Uses `settings.model`.
  - Sends a minimal OpenAI-compatible `/chat/completions` request.
  - Uses low-cost deterministic input.
  - Reuses the existing response-format fallback behavior where practical.
  - Validates that message content is a non-empty string.

- `test_embedding_model(settings: LlmSettings) -> int`
  - Uses `settings.embedding_model`.
  - Sends `["테스트"]` or equivalent short text to `/embeddings`.
  - Validates that the first embedding is a non-empty numeric vector.
  - Returns embedding dimension for a useful success message.

- `test_llm_models(settings: LlmSettings) -> ModelTestResult`
  - Runs both test helpers.
  - Raises `LlmResponseError` with a stage-specific message when either test fails.

## UI Design

Keep one button to avoid clutter:

- Existing label: `Test / Load Models`
- Success label example: `Loaded 12 Models / Chat OK / Embedding OK`

The dialog constructor should accept injectable callables:

- `model_loader: Callable[[LlmSettings], AvailableModels]`
- `model_tester: Callable[[LlmSettings], ModelTestResult]`

This matches the existing `model_loader` test pattern and keeps UI tests network-free.

On click:

1. Build `LlmSettings` from current field values.
2. Fetch available models.
3. Update model combo boxes without losing current custom values.
4. Test both selected models using the current combo values.
5. Update button text on success.

The selected model values must be preserved when `/models` returns a list that does not include a manually entered model.

## Error Handling

- `/models` failure: show `Model Test` warning with the lookup error and skip model tests.
- Chat test failure: show `Model Test` warning prefixed with `Chat model test failed`.
- Embedding test failure: show `Model Test` warning prefixed with `Embedding model test failed`.
- Empty API key: surface the controlled client error instead of making a request.
- Malformed chat response: fail if content is missing or not a string.
- Malformed embedding response: fail if embedding data is missing, empty, or contains non-numeric values.

## Testing

Unit tests in `tests/test_llm_client.py`:

- Chat model test posts to `{base_url}/chat/completions` using `settings.model`.
- Chat model test rejects empty or malformed content.
- Embedding model test posts to `{base_url}/embeddings` using `settings.embedding_model`.
- Embedding model test rejects malformed embedding vectors.
- Combined model test returns both selected model ids and success diagnostics.

UI tests in `tests/test_settings_dialog.py`:

- `load_models()` still loads selectable chat and embedding models.
- `load_models()` calls the injected tester after updating selectable fields.
- Button text reports loaded model count and both test successes.
- A tester failure displays a warning and does not overwrite valid combo values.

## Manual Verification

With a real API key configured:

1. Open the app.
2. Open Settings.
3. Enter an OpenAI-compatible base URL, chat model, and embedding model.
4. Click `Test / Load Models`.
5. Confirm the button reports loaded model count, chat success, and embedding success.
6. Save settings and run the normal category/product workflow.

## Implementation Notes

Keep network behavior in client modules, not UI code. The Settings dialog should only orchestrate user input, injected calls, combo-box updates, and user-visible messages.

The feature should remain compatible with providers that do not support JSON mode by relying on the existing chat request fallback for `response_format` where applicable.
