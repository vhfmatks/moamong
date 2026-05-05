# Category Chroma Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh a local Chroma DB collection whenever a category Excel file is uploaded, storing `마이카테` as the id and embedding `마이카테명`.

**Architecture:** Add a focused `category_vector_store.py` module for record preparation, OpenAI-compatible embedding calls, and Chroma refresh. Keep Excel parsing in `excel_io.py`; update the category load worker to refresh Chroma after category parsing and return refresh success or error separately from the loaded categories.

**Tech Stack:** Python 3.11, requests, Chroma `PersistentClient`, PySide6 worker signals, pytest, openpyxl test workbooks.

---

## Implementation Context

This workspace is not a git repository. `git status --short` returns `fatal: not a git repository`, so commit steps are intentionally omitted. Use the checkbox list and test runs as the progress record.

Official Chroma APIs referenced:

- `PersistentClient(path=...)`, `get_or_create_collection(...)`, and `delete_collection(...)` from Chroma Python client docs.
- `collection.add(ids=..., documents=..., metadatas=..., embeddings=...)` from Chroma collection docs.
- Chroma docs state documents can be embedded by Chroma or inserted with precomputed embeddings; this plan precomputes embeddings through the app's existing OpenAI-compatible settings so `api_key` is not persisted inside Chroma collection configuration.

## File Structure

- Create `src/moamong_app/category_vector_store.py`
  - Owns category vector record construction, source hashing, embedding API calls, and Chroma refresh.
  - Lazily imports `chromadb` only inside the default client factory.
  - Exposes fake-friendly constructor injection for tests.
- Create `tests/test_category_vector_store.py`
  - Tests record construction, duplicate handling, embedding payload/parsing, and Chroma refresh with fake clients.
- Modify `src/moamong_app/ui/main_window.py`
  - Adds `CategoryLoadResult`.
  - Passes settings into category load worker.
  - Refreshes Chroma inside the existing background worker after category Excel parsing.
  - Keeps categories loaded when Chroma refresh fails.
- Modify `tests/test_ui_loading.py`
  - Adds worker tests for category Chroma success and failure without real Chroma or network calls.
- Modify `pyproject.toml`
  - Adds `chromadb>=1.1.13`.
- Update `uv.lock`
  - Regenerate after dependency change.

## Task 1: Category Vector Record Builder

**Files:**

- Create: `src/moamong_app/category_vector_store.py`
- Test: `tests/test_category_vector_store.py`

- [ ] **Step 1: Write the failing record-construction tests**

Create `tests/test_category_vector_store.py` with these initial tests:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from moamong_app.category_vector_store import (
    CategoryVectorStoreError,
    build_category_vector_records,
    file_sha256,
)
from moamong_app.models import Category


def test_build_category_vector_records_uses_mycate_as_id_and_name_as_document(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"category-bytes")

    records = build_category_vector_records(
        [
            Category(mycate=" WB100 ", name=" 생활용품 > 침구 > 베개 > "),
            Category(mycate="WB200", name="반려동물 > 관상어용품 > 수초관리 >"),
        ],
        source_path=source_path,
        source_hash="abc123",
    )

    assert records.ids == ["WB100", "WB200"]
    assert records.documents == [
        "생활용품 > 침구 > 베개 >",
        "반려동물 > 관상어용품 > 수초관리 >",
    ]
    assert records.metadatas == [
        {
            "mycate": "WB100",
            "name": "생활용품 > 침구 > 베개 >",
            "source_file": str(source_path),
            "source_hash": "abc123",
        },
        {
            "mycate": "WB200",
            "name": "반려동물 > 관상어용품 > 수초관리 >",
            "source_file": str(source_path),
            "source_hash": "abc123",
        },
    ]


def test_build_category_vector_records_keeps_later_duplicate_mycate_name(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"category-bytes")

    records = build_category_vector_records(
        [
            Category(mycate="WB100", name="생활용품 > 침구 > 베개 >"),
            Category(mycate="WB100", name="생활용품 > 침구 > 기능성베개 >"),
        ],
        source_path=source_path,
        source_hash="hash",
    )

    assert records.ids == ["WB100"]
    assert records.documents == ["생활용품 > 침구 > 기능성베개 >"]
    assert records.metadatas[0]["name"] == "생활용품 > 침구 > 기능성베개 >"


def test_build_category_vector_records_rejects_empty_usable_categories(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"category-bytes")

    with pytest.raises(CategoryVectorStoreError, match="No usable category records"):
        build_category_vector_records(
            [Category(mycate=" ", name=""), Category(mycate="", name="침구")],
            source_path=source_path,
            source_hash="hash",
        )


def test_file_sha256_hashes_file_contents(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"abc")

    assert file_sha256(source_path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py -q
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'moamong_app.category_vector_store'`.

- [ ] **Step 3: Add the minimal record builder implementation**

Create `src/moamong_app/category_vector_store.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moamong_app.models import Category


COLLECTION_NAME = "moamong_categories"
DEFAULT_BATCH_SIZE = 100


class CategoryVectorStoreError(RuntimeError):
    """Raised when category vector store refresh cannot be completed."""


@dataclass(frozen=True)
class CategoryVectorRecords:
    ids: list[str]
    documents: list[str]
    metadatas: list[dict[str, str]]


@dataclass(frozen=True)
class CategoryVectorRefreshResult:
    collection_name: str
    count: int
    db_path: Path
    source_hash: str


def default_chroma_path() -> Path:
    return Path.home() / ".moamong_product_mapper" / "chroma"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_category_vector_records(
    categories: list[Category],
    source_path: str | Path,
    source_hash: str,
) -> CategoryVectorRecords:
    source = Path(source_path)
    by_mycate: dict[str, str] = {}
    for category in categories:
        mycate = category.mycate.strip()
        name = category.name.strip()
        if not mycate or not name:
            continue
        by_mycate[mycate] = name

    if not by_mycate:
        raise CategoryVectorStoreError("No usable category records to embed")

    ids = list(by_mycate)
    documents = [by_mycate[mycate] for mycate in ids]
    metadatas = [
        {
            "mycate": mycate,
            "name": by_mycate[mycate],
            "source_file": str(source),
            "source_hash": source_hash,
        }
        for mycate in ids
    ]
    return CategoryVectorRecords(ids=ids, documents=documents, metadatas=metadatas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py -q
```

Expected: PASS for the four record-builder tests.

## Task 2: OpenAI-Compatible Embedding Client

**Files:**

- Modify: `src/moamong_app/category_vector_store.py`
- Modify: `tests/test_category_vector_store.py`

- [ ] **Step 1: Write failing embedding client tests**

Append these tests to `tests/test_category_vector_store.py`:

```python
from moamong_app.category_vector_store import OpenAICompatibleEmbeddingClient
from moamong_app.models import LlmSettings


class FakeEmbeddingResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.text = "response text"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeEmbeddingSession:
    def __init__(self, response: FakeEmbeddingResponse) -> None:
        self.response = response
        self.posts: list[dict[str, object]] = []

    def post(self, **kwargs: object) -> FakeEmbeddingResponse:
        self.posts.append(kwargs)
        return self.response


def test_openai_compatible_embedding_client_posts_embeddings_request() -> None:
    session = FakeEmbeddingSession(
        FakeEmbeddingResponse(
            {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }
        )
    )
    client = OpenAICompatibleEmbeddingClient(
        LlmSettings(
            base_url="https://llm.example.test/v1",
            api_key="secret-key",
            embedding_model="embed-model",
            timeout_seconds=12,
            retry_count=0,
        ),
        session=session,
    )

    embeddings = client.embed(["침구", "수초"])

    assert embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert session.posts == [
        {
            "url": "https://llm.example.test/v1/embeddings",
            "headers": {
                "Authorization": "Bearer secret-key",
                "Content-Type": "application/json",
            },
            "json": {"model": "embed-model", "input": ["침구", "수초"]},
            "timeout": 12,
        }
    ]


def test_openai_compatible_embedding_client_requires_api_key() -> None:
    client = OpenAICompatibleEmbeddingClient(LlmSettings(api_key=" "))

    with pytest.raises(CategoryVectorStoreError, match="API key is required"):
        client.embed(["침구"])


def test_openai_compatible_embedding_client_rejects_malformed_response() -> None:
    session = FakeEmbeddingSession(FakeEmbeddingResponse({"data": [{"index": 0}]}))
    client = OpenAICompatibleEmbeddingClient(
        LlmSettings(api_key="secret-key", retry_count=0),
        session=session,
    )

    with pytest.raises(CategoryVectorStoreError, match="embedding response item is invalid"):
        client.embed(["침구"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `OpenAICompatibleEmbeddingClient`.

- [ ] **Step 3: Add the embedding client**

Extend `src/moamong_app/category_vector_store.py`:

```python
from typing import Protocol

import requests

from moamong_app.models import Category, LlmSettings


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: LlmSettings, session: Any = requests) -> None:
        self.settings = settings
        self.session = session

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.api_key.strip():
            raise CategoryVectorStoreError("API key is required for category embedding refresh")
        if not texts:
            return []

        url = f"{self.settings.base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.settings.embedding_model, "input": texts}
        last_error: Exception | None = None
        attempts = max(1, self.settings.retry_count + 1)
        for _ in range(attempts):
            try:
                response = self.session.post(
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=self.settings.timeout_seconds,
                )
                response.raise_for_status()
                return _parse_embedding_response(response.json(), len(texts))
            except Exception as exc:
                last_error = exc

        raise CategoryVectorStoreError(f"embedding request failed: {last_error}") from last_error


def _parse_embedding_response(payload: Any, expected_count: int) -> list[list[float]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CategoryVectorStoreError("embedding response must contain a data list")

    embeddings_by_index: dict[int, list[float]] = {}
    for item in payload["data"]:
        if not isinstance(item, dict):
            raise CategoryVectorStoreError("embedding response item is invalid")
        index = item.get("index")
        embedding = item.get("embedding")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not isinstance(embedding, list)
            or not embedding
            or any(isinstance(value, bool) or not isinstance(value, int | float) for value in embedding)
        ):
            raise CategoryVectorStoreError("embedding response item is invalid")
        embeddings_by_index[index] = [float(value) for value in embedding]

    if sorted(embeddings_by_index) != list(range(expected_count)):
        raise CategoryVectorStoreError("embedding response count does not match request")
    return [embeddings_by_index[index] for index in range(expected_count)]
```

Ensure the final imports at the top are:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from moamong_app.models import Category, LlmSettings
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py -q
```

Expected: PASS for all category vector store tests so far.

## Task 3: Chroma Refresh Store

**Files:**

- Modify: `src/moamong_app/category_vector_store.py`
- Modify: `tests/test_category_vector_store.py`

- [ ] **Step 1: Write failing Chroma refresh tests**

Append these tests to `tests/test_category_vector_store.py`:

```python
from moamong_app.category_vector_store import CategoryVectorStore


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.seen_batches: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen_batches.append(list(texts))
        return [[float(index), float(index + 1)] for index, _ in enumerate(texts)]


class FakeCollection:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, object]] = []

    def add(self, **kwargs: object) -> None:
        self.add_calls.append(kwargs)


class FakeChromaClient:
    def __init__(self, collection: FakeCollection, *, delete_raises: Exception | None = None) -> None:
        self.collection = collection
        self.delete_raises = delete_raises
        self.deleted_names: list[str] = []
        self.created: list[dict[str, object]] = []

    def delete_collection(self, name: str) -> None:
        self.deleted_names.append(name)
        if self.delete_raises is not None:
            raise self.delete_raises

    def get_or_create_collection(self, **kwargs: object) -> FakeCollection:
        self.created.append(kwargs)
        return self.collection


def test_category_vector_store_refresh_rebuilds_collection_with_embeddings(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"category-bytes")
    collection = FakeCollection()
    client = FakeChromaClient(collection)
    embedding_client = FakeEmbeddingClient()
    store = CategoryVectorStore(
        db_path=tmp_path / "chroma",
        client_factory=lambda path: client,
        embedding_client=embedding_client,
        batch_size=10,
    )

    result = store.refresh(
        [
            Category(mycate="WB100", name="생활용품 > 침구 > 베개 >"),
            Category(mycate="WB200", name="반려동물 > 관상어용품 > 수초관리 >"),
        ],
        source_path=source_path,
        settings=LlmSettings(api_key="secret-key", embedding_model="embed-model"),
    )

    assert result.collection_name == "moamong_categories"
    assert result.count == 2
    assert result.db_path == tmp_path / "chroma"
    assert result.source_hash == file_sha256(source_path)
    assert client.deleted_names == ["moamong_categories"]
    assert client.created == [
        {
            "name": "moamong_categories",
            "metadata": {
                "source_file": str(source_path),
                "source_hash": result.source_hash,
                "embedding_model": "embed-model",
            },
        }
    ]
    assert embedding_client.seen_batches == [["생활용품 > 침구 > 베개 >", "반려동물 > 관상어용품 > 수초관리 >"]]
    assert collection.add_calls == [
        {
            "ids": ["WB100", "WB200"],
            "documents": ["생활용품 > 침구 > 베개 >", "반려동물 > 관상어용품 > 수초관리 >"],
            "metadatas": [
                {
                    "mycate": "WB100",
                    "name": "생활용품 > 침구 > 베개 >",
                    "source_file": str(source_path),
                    "source_hash": result.source_hash,
                },
                {
                    "mycate": "WB200",
                    "name": "반려동물 > 관상어용품 > 수초관리 >",
                    "source_file": str(source_path),
                    "source_hash": result.source_hash,
                },
            ],
            "embeddings": [[0.0, 1.0], [1.0, 2.0]],
        }
    ]


def test_category_vector_store_refresh_ignores_missing_collection_delete(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"category-bytes")
    collection = FakeCollection()
    client = FakeChromaClient(collection, delete_raises=ValueError("does not exist"))
    store = CategoryVectorStore(
        db_path=tmp_path / "chroma",
        client_factory=lambda path: client,
        embedding_client=FakeEmbeddingClient(),
    )

    result = store.refresh(
        [Category(mycate="WB100", name="생활용품 > 침구 > 베개 >")],
        source_path=source_path,
        settings=LlmSettings(api_key="secret-key"),
    )

    assert result.count == 1
    assert client.deleted_names == ["moamong_categories"]
    assert len(collection.add_calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `CategoryVectorStore`.

- [ ] **Step 3: Implement the refresh store**

Append this implementation to `src/moamong_app/category_vector_store.py`:

```python
class CategoryVectorStore:
    def __init__(
        self,
        db_path: str | Path | None = None,
        collection_name: str = COLLECTION_NAME,
        client_factory: Any | None = None,
        embedding_client: EmbeddingClient | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_chroma_path()
        self.collection_name = collection_name
        self.client_factory = client_factory if client_factory is not None else _create_chroma_client
        self.embedding_client = embedding_client
        self.batch_size = batch_size

    def refresh(
        self,
        categories: list[Category],
        source_path: str | Path,
        settings: LlmSettings,
    ) -> CategoryVectorRefreshResult:
        source = Path(source_path)
        source_hash = file_sha256(source)
        records = build_category_vector_records(
            categories,
            source_path=source,
            source_hash=source_hash,
        )
        embedding_client = self.embedding_client or OpenAICompatibleEmbeddingClient(settings)
        client = self.client_factory(self.db_path)

        try:
            client.delete_collection(name=self.collection_name)
        except Exception as exc:
            if not _looks_like_missing_collection_error(exc):
                raise CategoryVectorStoreError(f"failed to reset Chroma collection: {exc}") from exc

        collection = client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "source_file": str(source),
                "source_hash": source_hash,
                "embedding_model": settings.embedding_model,
            },
        )
        for start in range(0, len(records.ids), self.batch_size):
            end = start + self.batch_size
            documents = records.documents[start:end]
            collection.add(
                ids=records.ids[start:end],
                documents=documents,
                metadatas=records.metadatas[start:end],
                embeddings=embedding_client.embed(documents),
            )

        return CategoryVectorRefreshResult(
            collection_name=self.collection_name,
            count=len(records.ids),
            db_path=self.db_path,
            source_hash=source_hash,
        )


def _create_chroma_client(db_path: Path) -> Any:
    try:
        import chromadb
    except ImportError as exc:
        raise CategoryVectorStoreError(
            "chromadb is not installed. Install project dependencies before refreshing category embeddings."
        ) from exc

    db_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(db_path))


def _looks_like_missing_collection_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "does not exist" in message or "not found" in message or "not created" in message
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py -q
```

Expected: PASS for all category vector store tests.

## Task 4: Add Chroma Dependency

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Add Chroma to project dependencies**

Modify `pyproject.toml` dependency list to include:

```toml
  "chromadb>=1.1.13",
```

The dependency block should become:

```toml
dependencies = [
  "PySide6>=6.7",
  "chromadb>=1.1.13",
  "openpyxl>=3.1",
  "pandas>=2.2",
  "requests>=2.32"
]
```

- [ ] **Step 2: Regenerate the lock file**

Run:

```powershell
uv lock
```

Expected: `uv.lock` updates successfully.

- [ ] **Step 3: Verify imports still work**

Run:

```powershell
uv run python -c "from moamong_app.category_vector_store import CategoryVectorStore; print(CategoryVectorStore.__name__)"
```

Expected output:

```text
CategoryVectorStore
```

## Task 5: Category Load Worker Chroma Refresh

**Files:**

- Modify: `src/moamong_app/ui/main_window.py`
- Modify: `tests/test_ui_loading.py`

- [ ] **Step 1: Write failing worker tests for category refresh success and failure**

Append this helper and tests to `tests/test_ui_loading.py`:

```python
from openpyxl import Workbook

from moamong_app.category_vector_store import CategoryVectorRefreshResult, CategoryVectorStoreError
from moamong_app.models import Category, LlmSettings
from moamong_app.ui.main_window import CategoryLoadResult


def make_category_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Mycate1(1-2)"
    ws.append(["마이카테", "마이카테명"])
    ws.append(["WB100", "생활용품 > 침구 > 베개 >"])
    ws.append(["WB200", "반려동물 > 관상어용품 > 수초관리 >"])
    wb.save(path)


class SuccessfulVectorStore:
    def __init__(self) -> None:
        self.seen_categories: list[Category] | None = None
        self.seen_source_path: Path | None = None
        self.seen_settings: LlmSettings | None = None

    def refresh(
        self,
        categories: list[Category],
        source_path: str | Path,
        settings: LlmSettings,
    ) -> CategoryVectorRefreshResult:
        self.seen_categories = categories
        self.seen_source_path = Path(source_path)
        self.seen_settings = settings
        return CategoryVectorRefreshResult(
            collection_name="moamong_categories",
            count=len(categories),
            db_path=Path("C:/fake/chroma"),
            source_hash="hash",
        )


class FailingVectorStore:
    def refresh(
        self,
        categories: list[Category],
        source_path: str | Path,
        settings: LlmSettings,
    ) -> CategoryVectorRefreshResult:
        raise CategoryVectorStoreError("embedding failed")


def test_category_workbook_load_worker_refreshes_chroma_after_loading(tmp_path: Path) -> None:
    QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "category.xlsx"
    make_category_workbook(path)
    store = SuccessfulVectorStore()
    loaded: list[tuple[str, object]] = []
    failed: list[tuple[str, str]] = []
    settings = LlmSettings(api_key="secret-key", embedding_model="embed-model")
    worker = WorkbookLoadWorker(
        "category",
        path,
        settings=settings,
        vector_store_factory=lambda: store,
    )
    worker.loaded.connect(lambda kind, payload: loaded.append((kind, payload)))
    worker.failed.connect(lambda kind, message: failed.append((kind, message)))

    worker.run()

    assert failed == []
    assert loaded[0][0] == "category"
    payload = loaded[0][1]
    assert isinstance(payload, CategoryLoadResult)
    assert [category.mycate for category in payload.categories] == ["WB100", "WB200"]
    assert payload.vector_result is not None
    assert payload.vector_result.count == 2
    assert payload.vector_error == ""
    assert store.seen_categories == payload.categories
    assert store.seen_source_path == path
    assert store.seen_settings is settings


def test_category_workbook_load_worker_still_loads_categories_when_chroma_refresh_fails(tmp_path: Path) -> None:
    QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "category.xlsx"
    make_category_workbook(path)
    loaded: list[tuple[str, object]] = []
    failed: list[tuple[str, str]] = []
    worker = WorkbookLoadWorker(
        "category",
        path,
        settings=LlmSettings(api_key="secret-key"),
        vector_store_factory=FailingVectorStore,
    )
    worker.loaded.connect(lambda kind, payload: loaded.append((kind, payload)))
    worker.failed.connect(lambda kind, message: failed.append((kind, message)))

    worker.run()

    assert failed == []
    payload = loaded[0][1]
    assert isinstance(payload, CategoryLoadResult)
    assert [category.mycate for category in payload.categories] == ["WB100", "WB200"]
    assert payload.vector_result is None
    assert payload.vector_error == "embedding failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/test_ui_loading.py -q
```

Expected: FAIL with `ImportError` for `CategoryLoadResult` or unexpected `WorkbookLoadWorker` constructor arguments.

- [ ] **Step 3: Update main window imports and data class**

Modify `src/moamong_app/ui/main_window.py` imports:

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable
```

Add after `GENERATED_COLUMNS`:

```python
@dataclass(frozen=True)
class CategoryLoadResult:
    categories: list[Category]
    vector_result: CategoryVectorRefreshResult | None = None
    vector_error: str = ""
```

Add this import near other app imports:

```python
from moamong_app.category_vector_store import (
    CategoryVectorRefreshResult,
    CategoryVectorStore,
)
```

- [ ] **Step 4: Update `WorkbookLoadWorker` constructor and category run path**

Change `WorkbookLoadWorker.__init__` to:

```python
    def __init__(
        self,
        kind: str,
        path: str | Path,
        settings: LlmSettings | None = None,
        vector_store_factory: Callable[[], CategoryVectorStore] = CategoryVectorStore,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.path = Path(path)
        self.settings = settings
        self.vector_store_factory = vector_store_factory
```

Change the category branch in `WorkbookLoadWorker.run` to:

```python
            if self.kind == "category":
                categories = load_category_workbook(
                    self.path,
                    progress_callback=lambda current, total: self.progressed.emit(
                        self.kind,
                        current,
                        total,
                    ),
                )
                vector_result: CategoryVectorRefreshResult | None = None
                vector_error = ""
                if self.settings is not None:
                    try:
                        vector_result = self.vector_store_factory().refresh(
                            categories,
                            source_path=self.path,
                            settings=self.settings,
                        )
                    except Exception as exc:
                        vector_error = str(exc)
                self.loaded.emit(
                    self.kind,
                    CategoryLoadResult(
                        categories=categories,
                        vector_result=vector_result,
                        vector_error=vector_error,
                    ),
                )
                return
```

- [ ] **Step 5: Pass settings when starting category load**

Change `_start_workbook_load` worker creation:

```python
        self.load_worker = WorkbookLoadWorker(
            kind,
            path,
            settings=self.settings if kind == "category" else None,
        )
```

- [ ] **Step 6: Handle `CategoryLoadResult` in `_on_workbook_loaded`**

Replace the existing category payload block in `_on_workbook_loaded` with:

```python
        assert isinstance(payload, CategoryLoadResult)
        self.categories = payload.categories
        self.matcher = CategoryMatcher(self.categories)
        self._clear_results()
        if payload.vector_error:
            self.status_label.setText(
                f"Loaded categories: {len(self.categories)}. Chroma refresh failed: {payload.vector_error}"
            )
            QMessageBox.warning(self, "Category Chroma DB", payload.vector_error)
            return
        if payload.vector_result is not None:
            self.status_label.setText(
                f"Loaded categories: {len(self.categories)}. Chroma DB refreshed: {payload.vector_result.count}"
            )
            return
        self.status_label.setText(f"Loaded categories: {len(self.categories)}")
```

- [ ] **Step 7: Run worker tests to verify they pass**

Run:

```powershell
uv run pytest tests/test_ui_loading.py -q
```

Expected: PASS for UI loading tests.

## Task 6: Full Test Suite and Real Import Verification

**Files:**

- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
uv run pytest tests/test_category_vector_store.py tests/test_ui_loading.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Verify Chroma can be imported from the locked environment**

Run:

```powershell
uv run python -c "import chromadb; print(chromadb.__name__)"
```

Expected output:

```text
chromadb
```

- [ ] **Step 4: Optional manual smoke test with the real `category.xlsx`**

Run this only if an API key is configured in the app settings:

```powershell
uv run python -m moamong_app
```

Manual expected behavior:

- Load `category.xlsx`.
- Status text reports `Loaded categories: <count>. Chroma DB refreshed: <count>`.
- `Path.home() / ".moamong_product_mapper" / "chroma"` exists after refresh.

## Self-Review

Spec coverage:

- Category Excel upload triggers Chroma refresh: Task 5.
- `마이카테` as id and `마이카테명` as embedded text: Task 1 and Task 3.
- Metadata for lookup/audit: Task 1 and Task 3.
- Local Chroma path and collection name: Task 1 and Task 3.
- Separate refresh failure from Excel load failure: Task 5.
- Tests avoid real Chroma/network: Task 2, Task 3, and Task 5 use fakes.
- Product row Chroma lookup remains out of scope: no task modifies `RowProcessor` or `CategoryMatcher`.

Placeholder scan:

- No placeholder markers or unspecified edge-case steps remain.

Type consistency:

- `CategoryVectorRecords`, `CategoryVectorRefreshResult`, `CategoryVectorStoreError`, `OpenAICompatibleEmbeddingClient`, and `CategoryVectorStore` are introduced before later tasks use them.
- `CategoryLoadResult` carries `categories`, `vector_result`, and `vector_error`, and worker/main-window tests use the same names.
