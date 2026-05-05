from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from moamong_app.models import Category, LlmSettings


COLLECTION_NAME = "moamong_categories"
DEFAULT_BATCH_SIZE = 100


class CategoryVectorStoreError(RuntimeError):
    pass


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


@dataclass(frozen=True)
class CategoryVectorBatch:
    ids: list[str]
    documents: list[str]
    metadatas: list[dict[str, str]]
    embeddings: list[list[float]]


class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        pass


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: LlmSettings, session: Any = requests) -> None:
        self.settings = settings
        self.session = session

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self.settings.api_key.strip():
            raise CategoryVectorStoreError(
                "API key is required for category embedding refresh"
            )

        response = self._post_embeddings(texts)
        try:
            payload = response.json()
        except ValueError as exc:
            raise CategoryVectorStoreError(f"embedding response is invalid JSON: {exc}") from exc

        return _parse_embedding_response(payload, expected_count=len(texts))

    def _post_embeddings(self, texts: list[str]) -> Any:
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
                return response
            except Exception as exc:
                last_error = exc

        raise CategoryVectorStoreError(
            f"embedding request failed: {last_error}"
        ) from last_error


class CategoryVectorStore:
    def __init__(
        self,
        db_path: str | Path | None = None,
        collection_name: str = COLLECTION_NAME,
        client_factory: Any | None = None,
        embedding_client: EmbeddingClient | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if batch_size <= 0:
            raise CategoryVectorStoreError("batch_size must be positive")

        self.db_path = Path(db_path) if db_path is not None else default_chroma_path()
        self.collection_name = collection_name
        self.client_factory = client_factory if client_factory is not None else _create_chroma_client
        self.embedding_client = embedding_client
        self.batch_size = batch_size

    def refresh(
        self,
        categories: list[Category],
        *,
        source_path: str | Path,
        settings: LlmSettings,
    ) -> CategoryVectorRefreshResult:
        source_hash = file_sha256(source_path)
        records = build_category_vector_records(
            categories,
            source_path=source_path,
            source_hash=source_hash,
        )
        embedding_client = self.embedding_client or OpenAICompatibleEmbeddingClient(settings)

        prepared_batches: list[CategoryVectorBatch] = []
        for start in range(0, len(records.ids), self.batch_size):
            end = start + self.batch_size
            documents = records.documents[start:end]
            prepared_batches.append(
                CategoryVectorBatch(
                    ids=records.ids[start:end],
                    documents=documents,
                    metadatas=records.metadatas[start:end],
                    embeddings=embedding_client.embed(documents),
                )
            )

        client = self.client_factory(self.db_path)
        try:
            client.delete_collection(name=self.collection_name)
        except Exception as exc:
            if not _looks_like_missing_collection_error(exc):
                raise CategoryVectorStoreError(
                    f"failed to reset Chroma collection: {exc}"
                ) from exc

        collection = client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "source_file": str(Path(source_path)),
                "source_hash": source_hash,
                "embedding_model": settings.embedding_model,
            },
        )

        for batch in prepared_batches:
            collection.add(
                ids=batch.ids,
                documents=batch.documents,
                metadatas=batch.metadatas,
                embeddings=batch.embeddings,
            )

        return CategoryVectorRefreshResult(
            collection_name=self.collection_name,
            count=len(records.ids),
            db_path=self.db_path,
            source_hash=source_hash,
        )


def default_chroma_path() -> Path:
    return Path.home() / ".moamong_product_mapper" / "chroma"


def _create_chroma_client(db_path: Path) -> Any:
    try:
        import chromadb
    except ModuleNotFoundError as exc:
        raise CategoryVectorStoreError(
            "chromadb is not installed; install it to refresh category vectors"
        ) from exc

    db_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(db_path))


def _looks_like_missing_collection_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "does not exist" in message
        or "not found" in message
        or "not created" in message
    )


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_embedding_response(payload: Any, *, expected_count: int) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise CategoryVectorStoreError("embedding response data is invalid")

    data = payload.get("data")
    if not isinstance(data, list):
        raise CategoryVectorStoreError("embedding response data is invalid")
    if len(data) != expected_count:
        raise CategoryVectorStoreError("embedding response count does not match input count")

    embeddings_by_index: dict[int, list[float]] = {}
    vector_dimension: int | None = None
    for item in data:
        index, embedding = _parse_embedding_item(item)
        if index in embeddings_by_index:
            raise CategoryVectorStoreError("embedding response count does not match input count")
        if vector_dimension is None:
            vector_dimension = len(embedding)
        elif len(embedding) != vector_dimension:
            raise CategoryVectorStoreError("embedding response item is invalid")
        embeddings_by_index[index] = embedding

    expected_indices = list(range(expected_count))
    if sorted(embeddings_by_index) != expected_indices:
        raise CategoryVectorStoreError("embedding response count does not match input count")

    return [embeddings_by_index[index] for index in expected_indices]


def _parse_embedding_item(item: Any) -> tuple[int, list[float]]:
    if not isinstance(item, dict):
        raise CategoryVectorStoreError("embedding response item is invalid")

    index = item.get("index")
    embedding = item.get("embedding")
    if isinstance(index, bool) or not isinstance(index, int):
        raise CategoryVectorStoreError("embedding response item is invalid")
    if not isinstance(embedding, list) or not embedding:
        raise CategoryVectorStoreError("embedding response item is invalid")

    vector: list[float] = []
    for value in embedding:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise CategoryVectorStoreError("embedding response item is invalid")
        converted_value = float(value)
        if not math.isfinite(converted_value):
            raise CategoryVectorStoreError("embedding response item is invalid")
        vector.append(converted_value)

    return index, vector


def build_category_vector_records(
    categories: list[Category],
    *,
    source_path: str | Path,
    source_hash: str,
) -> CategoryVectorRecords:
    source_file = str(Path(source_path))
    by_mycate: dict[str, str] = {}

    for category in categories:
        mycate = category.mycate.strip()
        name = category.name.strip()
        if not mycate or not name:
            continue
        by_mycate[mycate] = name

    if not by_mycate:
        raise CategoryVectorStoreError("No usable category records")

    ids = list(by_mycate)
    documents = [by_mycate[mycate] for mycate in ids]
    metadatas = [
        {
            "mycate": mycate,
            "name": by_mycate[mycate],
            "source_file": source_file,
            "source_hash": source_hash,
        }
        for mycate in ids
    ]

    return CategoryVectorRecords(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )
