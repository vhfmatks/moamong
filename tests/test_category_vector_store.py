from __future__ import annotations

from pathlib import Path

import pytest

from moamong_app.category_vector_store import (
    CategoryVectorStore,
    CategoryVectorStoreError,
    OpenAICompatibleEmbeddingClient,
    build_category_vector_records,
    file_sha256,
)
from moamong_app.models import Category, LlmSettings


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


def test_openai_compatible_embedding_client_rejects_duplicate_extra_indexes() -> None:
    session = FakeEmbeddingSession(
        FakeEmbeddingResponse(
            {
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 1, "embedding": [0.5, 0.6]},
                ]
            }
        )
    )
    client = OpenAICompatibleEmbeddingClient(
        LlmSettings(api_key="secret-key", retry_count=0),
        session=session,
    )

    with pytest.raises(
        CategoryVectorStoreError,
        match="embedding response count does not match",
    ):
        client.embed(["침구", "수초"])


def test_openai_compatible_embedding_client_rejects_inconsistent_vector_dimensions() -> None:
    session = FakeEmbeddingSession(
        FakeEmbeddingResponse(
            {
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4, 0.5]},
                ]
            }
        )
    )
    client = OpenAICompatibleEmbeddingClient(
        LlmSettings(api_key="secret-key", retry_count=0),
        session=session,
    )

    with pytest.raises(
        CategoryVectorStoreError,
        match="embedding response item is invalid",
    ):
        client.embed(["침구", "수초"])


def test_openai_compatible_embedding_client_rejects_non_finite_embedding_values() -> None:
    session = FakeEmbeddingSession(
        FakeEmbeddingResponse(
            {
                "data": [
                    {"index": 0, "embedding": [0.1, float("nan")]},
                    {"index": 1, "embedding": [0.3, float("inf")]},
                ]
            }
        )
    )
    client = OpenAICompatibleEmbeddingClient(
        LlmSettings(api_key="secret-key", retry_count=0),
        session=session,
    )

    with pytest.raises(
        CategoryVectorStoreError,
        match="embedding response item is invalid",
    ):
        client.embed(["침구", "수초"])


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.seen_batches: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen_batches.append(list(texts))
        return [[float(index), float(index + 1)] for index, _ in enumerate(texts)]


class FailingFakeEmbeddingClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise CategoryVectorStoreError("embedding failed")


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


def test_category_vector_store_refresh_preserves_collection_when_embeddings_fail(tmp_path: Path) -> None:
    source_path = tmp_path / "category.xlsx"
    source_path.write_bytes(b"category-bytes")
    collection = FakeCollection()
    client = FakeChromaClient(collection)
    store = CategoryVectorStore(
        db_path=tmp_path / "chroma",
        client_factory=lambda path: client,
        embedding_client=FailingFakeEmbeddingClient(),
    )

    with pytest.raises(CategoryVectorStoreError, match="embedding failed"):
        store.refresh(
            [Category(mycate="WB100", name="생활용품 > 침구 > 베개 >")],
            source_path=source_path,
            settings=LlmSettings(api_key="secret-key"),
        )

    assert client.deleted_names == []
    assert client.created == []
    assert collection.add_calls == []


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


def test_category_vector_store_rejects_zero_batch_size(tmp_path: Path) -> None:
    with pytest.raises(CategoryVectorStoreError, match="batch_size must be positive"):
        CategoryVectorStore(db_path=tmp_path / "chroma", batch_size=0)


def test_category_vector_store_rejects_negative_batch_size(tmp_path: Path) -> None:
    with pytest.raises(CategoryVectorStoreError, match="batch_size must be positive"):
        CategoryVectorStore(db_path=tmp_path / "chroma", batch_size=-1)
