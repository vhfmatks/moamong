from __future__ import annotations

from typing import Protocol

from collections.abc import Iterator

from moamong_app.keyword_fetcher import SITE_ORDER, SiteKeywordCollection
from moamong_app.models import GeneratedRow, ProductRow, RowProcessResult, RowStatus


class KeywordCollector(Protocol):
    def collect(self, keyword: str) -> SiteKeywordCollection:
        ...

    def collect_site(self, site: str, keyword: str) -> SiteKeywordCollection:
        ...


class ProductKeywordGenerator(Protocol):
    def generate_site_search_keyword(self, row: ProductRow) -> str:
        ...

    def generate_product_keywords(
        self,
        row: ProductRow,
        site_keywords: dict[str, list[str]],
    ) -> GeneratedRow:
        ...


class KeywordProcessor:
    def __init__(
        self,
        collector: KeywordCollector,
        llm: ProductKeywordGenerator,
        sites: list[str] | None = None,
    ) -> None:
        self.collector = collector
        self.llm = llm
        self.sites = sites if sites is not None else SITE_ORDER

    def process(self, row: ProductRow) -> RowProcessResult:
        last_result: RowProcessResult | None = None
        for result in self.process_steps(row):
            last_result = result
        if last_result is None:
            return RowProcessResult(
                row_index=row.index,
                status=RowStatus.FAILED,
                message="No processing steps were executed.",
            )
        return last_result

    def process_steps(self, row: ProductRow) -> Iterator[RowProcessResult]:
        site_keywords: dict[str, list[str]] = {}
        site_errors: dict[str, str] = {}
        step_statuses: dict[str, str] = {}
        fallback_keyword = row.text("원본상품명(참고용)") or row.text("상품명")
        search_keyword = fallback_keyword
        try:
            step_statuses["search_keyword"] = "처리중"
            yield RowProcessResult(
                row_index=row.index,
                status=RowStatus.PROCESSING,
                search_keyword=search_keyword,
                site_keywords=dict(site_keywords),
                site_errors=dict(site_errors),
                step_statuses=dict(step_statuses),
            )
            try:
                generated_search_keyword = self.llm.generate_site_search_keyword(row)
                if generated_search_keyword.strip():
                    search_keyword = generated_search_keyword.strip()
                step_statuses["search_keyword"] = "완료"
            except Exception as exc:
                step_statuses["search_keyword"] = f"실패: {exc}; 원본 사용"
            yield RowProcessResult(
                row_index=row.index,
                status=RowStatus.PROCESSING,
                search_keyword=search_keyword,
                site_keywords=dict(site_keywords),
                site_errors=dict(site_errors),
                step_statuses=dict(step_statuses),
            )

            for site in self.sites:
                step_statuses[site] = "처리중"
                yield RowProcessResult(
                    row_index=row.index,
                    status=RowStatus.PROCESSING,
                    search_keyword=search_keyword,
                    site_keywords=dict(site_keywords),
                    site_errors=dict(site_errors),
                    step_statuses=dict(step_statuses),
                )
                collection = self.collector.collect_site(site, search_keyword)
                site_keywords[site] = collection.keywords.get(site, [])
                if site in collection.errors:
                    site_errors[site] = collection.errors[site]
                    step_statuses[site] = f"실패: {collection.errors[site]}"
                else:
                    step_statuses[site] = "완료"
                yield RowProcessResult(
                    row_index=row.index,
                    status=RowStatus.PROCESSING,
                    search_keyword=search_keyword,
                    site_keywords=dict(site_keywords),
                    site_errors=dict(site_errors),
                    step_statuses=dict(step_statuses),
                )

            step_statuses["llm"] = "처리중"
            yield RowProcessResult(
                row_index=row.index,
                status=RowStatus.PROCESSING,
                search_keyword=search_keyword,
                site_keywords=dict(site_keywords),
                site_errors=dict(site_errors),
                step_statuses=dict(step_statuses),
            )
            generated = self.llm.generate_product_keywords(row, site_keywords)
            step_statuses["llm"] = "완료"
            yield RowProcessResult(
                row_index=row.index,
                status=RowStatus.DONE,
                generated=generated,
                search_keyword=search_keyword,
                site_keywords=dict(site_keywords),
                site_errors=dict(site_errors),
                step_statuses=dict(step_statuses),
            )
        except Exception as exc:
            step_statuses["llm"] = f"실패: {exc}"
            yield RowProcessResult(
                row_index=row.index,
                status=RowStatus.FAILED,
                message=str(exc),
                search_keyword=search_keyword,
                site_keywords=dict(site_keywords),
                site_errors=dict(site_errors),
                step_statuses=dict(step_statuses),
            )
