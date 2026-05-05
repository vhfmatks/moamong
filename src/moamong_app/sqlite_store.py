from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from moamong_app.excel_io import WorkbookData
from moamong_app.models import (
    Category,
    CategoryCandidate,
    GeneratedRow,
    ProductRow,
    RowProcessResult,
    RowStatus,
)


def default_database_path() -> Path:
    return Path.home() / ".moamong_product_mapper" / "moamong.sqlite3"


class SqliteStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_database_path()

    def save_product_workbook(self, workbook: WorkbookData) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM product_meta")
            conn.execute("DELETE FROM product_rows")
            conn.execute("DELETE FROM results")
            conn.execute(
                """
                INSERT INTO product_meta (id, path, sheet_name, columns_json)
                VALUES (1, ?, ?, ?)
                """,
                (
                    str(workbook.path),
                    workbook.sheet_name,
                    _to_json(workbook.columns),
                ),
            )
            conn.executemany(
                """
                INSERT INTO product_rows (row_index, values_json)
                VALUES (?, ?)
                """,
                [
                    (row.index, _to_json(row.values))
                    for row in workbook.rows
                ],
            )

    def load_product_workbook(self) -> WorkbookData | None:
        self._ensure_schema()
        with self._connect() as conn:
            meta = conn.execute(
                "SELECT path, sheet_name, columns_json FROM product_meta WHERE id = 1"
            ).fetchone()
            if meta is None:
                return None
            rows = [
                ProductRow(
                    index=int(row["row_index"]),
                    values=json.loads(str(row["values_json"])),
                )
                for row in conn.execute(
                    """
                    SELECT row_index, values_json
                    FROM product_rows
                    ORDER BY row_index
                    """
                )
            ]
        return WorkbookData(
            path=Path(str(meta["path"])),
            sheet_name=str(meta["sheet_name"]),
            columns=json.loads(str(meta["columns_json"])),
            rows=rows,
        )

    def save_categories(self, categories: list[Category]) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM categories")
            conn.executemany(
                """
                INSERT INTO categories (position, mycate, name)
                VALUES (?, ?, ?)
                """,
                [
                    (position, category.mycate, category.name)
                    for position, category in enumerate(categories)
                ],
            )

    def load_categories(self) -> list[Category]:
        self._ensure_schema()
        with self._connect() as conn:
            return [
                Category(mycate=str(row["mycate"]), name=str(row["name"]))
                for row in conn.execute(
                    """
                    SELECT mycate, name
                    FROM categories
                    ORDER BY position
                    """
                )
            ]

    def save_result(self, result: RowProcessResult) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO results (row_index, payload_json)
                VALUES (?, ?)
                ON CONFLICT(row_index) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (result.row_index, _to_json(_result_to_payload(result))),
            )

    def save_results(self, results: list[RowProcessResult]) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO results (row_index, payload_json)
                VALUES (?, ?)
                ON CONFLICT(row_index) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                [
                    (result.row_index, _to_json(_result_to_payload(result)))
                    for result in results
                ],
            )

    def load_results(self) -> list[RowProcessResult]:
        self._ensure_schema()
        with self._connect() as conn:
            return [
                _payload_to_result(json.loads(str(row["payload_json"])))
                for row in conn.execute(
                    """
                    SELECT payload_json
                    FROM results
                    ORDER BY row_index
                    """
                )
            ]

    def clear_results(self) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM results")

    def truncate(self) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("DELETE FROM product_meta")
            conn.execute("DELETE FROM product_rows")
            conn.execute("DELETE FROM categories")
            conn.execute("DELETE FROM results")

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    path TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    columns_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_rows (
                    row_index INTEGER PRIMARY KEY,
                    values_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    position INTEGER PRIMARY KEY,
                    mycate TEXT NOT NULL,
                    name TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS results (
                    row_index INTEGER PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _result_to_payload(result: RowProcessResult) -> dict[str, Any]:
    return {
        "row_index": result.row_index,
        "status": result.status.value,
        "generated": asdict(result.generated) if result.generated is not None else None,
        "message": result.message,
        "search_keyword": result.search_keyword,
        "category_candidates": [
            {
                "category": asdict(candidate.category),
                "score": candidate.score,
            }
            for candidate in result.category_candidates
        ],
        "site_keywords": result.site_keywords,
        "site_errors": result.site_errors,
        "step_statuses": result.step_statuses,
    }


def _payload_to_result(payload: dict[str, Any]) -> RowProcessResult:
    generated_payload = payload.get("generated")
    generated = (
        GeneratedRow(**generated_payload)
        if isinstance(generated_payload, dict)
        else None
    )
    candidates = []
    for candidate_payload in payload.get("category_candidates", []) or []:
        if not isinstance(candidate_payload, dict):
            continue
        category_payload = candidate_payload.get("category")
        if not isinstance(category_payload, dict):
            continue
        candidates.append(
            CategoryCandidate(
                category=Category(**category_payload),
                score=float(candidate_payload.get("score", 0.0)),
            )
        )

    return RowProcessResult(
        row_index=int(payload.get("row_index", 0)),
        status=_row_status(str(payload.get("status", RowStatus.FAILED.value))),
        generated=generated,
        message=str(payload.get("message", "")),
        search_keyword=str(payload.get("search_keyword", "")),
        category_candidates=candidates,
        site_keywords={
            str(site): [str(keyword) for keyword in keywords]
            for site, keywords in (payload.get("site_keywords", {}) or {}).items()
            if isinstance(keywords, list)
        },
        site_errors={
            str(site): str(message)
            for site, message in (payload.get("site_errors", {}) or {}).items()
        },
        step_statuses={
            str(step): str(status)
            for step, status in (payload.get("step_statuses", {}) or {}).items()
        },
    )


def _row_status(value: str) -> RowStatus:
    try:
        return RowStatus(value)
    except ValueError:
        return RowStatus.FAILED
