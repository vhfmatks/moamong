from __future__ import annotations

from moamong_app.keyword_fetcher import SiteKeywordCollection
from moamong_app.keyword_processor import KeywordProcessor
from moamong_app.models import GeneratedRow, ProductRow, RowStatus


class StubCollector:
    def __init__(self) -> None:
        self.seen_keyword: str | None = None
        self.seen_sites: list[str] = []

    def collect(self, keyword: str) -> SiteKeywordCollection:
        self.seen_keyword = keyword
        return SiteKeywordCollection(
            keywords={
                "coupang": ["얼굴베개", "마사지얼굴쿠션"],
                "naver": ["안면베개"],
            },
            errors={"gmarket": "Timeout: slow"},
        )

    def collect_site(self, site: str, keyword: str) -> SiteKeywordCollection:
        self.seen_keyword = keyword
        self.seen_sites.append(site)
        if site == "coupang":
            return SiteKeywordCollection(
                keywords={"coupang": ["얼굴베개", "마사지얼굴쿠션"]},
                errors={},
            )
        if site == "naver":
            return SiteKeywordCollection(
                keywords={"naver": ["안면베개"]},
                errors={},
            )
        if site == "gmarket":
            return SiteKeywordCollection(
                keywords={"gmarket": []},
                errors={"gmarket": "Timeout: slow"},
            )
        return SiteKeywordCollection(keywords={site: []}, errors={})


class StubLlm:
    def __init__(self) -> None:
        self.seen_row: ProductRow | None = None
        self.seen_site_keywords: dict[str, list[str]] | None = None
        self.search_keyword = "얼굴 쿠션"

    def generate_site_search_keyword(self, row: ProductRow) -> str:
        self.seen_row = row
        return self.search_keyword

    def generate_product_keywords(
        self,
        row: ProductRow,
        site_keywords: dict[str, list[str]],
    ) -> GeneratedRow:
        self.seen_row = row
        self.seen_site_keywords = site_keywords
        return GeneratedRow(
            product_name="얼굴전용 마사지 베개",
            keywords=["얼굴베개", "마사지얼굴베개"],
        )


def test_keyword_processor_uses_original_product_name_and_preserves_category_scope() -> None:
    row = ProductRow(
        index=7,
        values={
            "상품명": "기존 상품명",
            "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개",
            "마이카테": "WB100",
        },
    )
    collector = StubCollector()
    llm = StubLlm()

    result = KeywordProcessor(collector=collector, llm=llm).process(row)

    assert collector.seen_keyword == "얼굴 쿠션"
    assert llm.seen_row is row
    assert llm.seen_site_keywords == {
        "coupang": ["얼굴베개", "마사지얼굴쿠션"],
        "naver": ["안면베개"],
        "11st": [],
        "auction": [],
        "gmarket": [],
    }
    assert result.row_index == 7
    assert result.status is RowStatus.DONE
    assert result.generated is not None
    assert result.generated.product_name == "얼굴전용 마사지 베개"
    assert result.generated.mycate == ""
    assert result.search_keyword == "얼굴 쿠션"
    assert result.site_keywords["coupang"] == ["얼굴베개", "마사지얼굴쿠션"]
    assert result.site_errors == {"gmarket": "Timeout: slow"}


def test_keyword_processor_emits_site_steps_before_llm_step() -> None:
    row = ProductRow(
        index=7,
        values={
            "상품명": "기존 상품명",
            "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개",
        },
    )
    collector = StubCollector()
    llm = StubLlm()

    steps = list(
        KeywordProcessor(
            collector=collector,
            llm=llm,
            sites=["coupang", "gmarket", "naver"],
        ).process_steps(row)
    )

    assert collector.seen_sites == ["coupang", "gmarket", "naver"]
    assert steps[0].status is RowStatus.PROCESSING
    assert steps[0].step_statuses == {"search_keyword": "처리중"}
    assert steps[1].step_statuses == {"search_keyword": "완료"}
    assert steps[1].search_keyword == "얼굴 쿠션"
    assert steps[2].step_statuses["coupang"] == "처리중"
    assert steps[3].step_statuses["coupang"] == "완료"
    assert steps[3].site_keywords == {"coupang": ["얼굴베개", "마사지얼굴쿠션"]}
    assert steps[5].step_statuses["gmarket"] == "실패: Timeout: slow"
    assert steps[7].step_statuses["naver"] == "완료"
    assert steps[8].step_statuses["llm"] == "처리중"
    assert steps[9].status is RowStatus.DONE
    assert steps[9].step_statuses["llm"] == "완료"
    assert steps[9].generated is not None
    assert llm.seen_site_keywords == {
        "coupang": ["얼굴베개", "마사지얼굴쿠션"],
        "gmarket": [],
        "naver": ["안면베개"],
    }


def test_keyword_processor_falls_back_to_original_name_when_search_keyword_generation_fails() -> None:
    row = ProductRow(
        index=7,
        values={
            "상품명": "기존 상품명",
            "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개",
        },
    )
    collector = StubCollector()
    llm = StubLlm()

    def fail_search_keyword(_: ProductRow) -> str:
        raise RuntimeError("llm unavailable")

    llm.generate_site_search_keyword = fail_search_keyword  # type: ignore[method-assign]

    steps = list(
        KeywordProcessor(
            collector=collector,
            llm=llm,
            sites=["coupang"],
        ).process_steps(row)
    )

    assert collector.seen_keyword == "마사지샵 얼굴 쿠션 베개"
    assert steps[1].search_keyword == "마사지샵 얼굴 쿠션 베개"
    assert steps[1].step_statuses["search_keyword"].startswith("실패: llm unavailable")
    assert steps[-1].status is RowStatus.DONE
