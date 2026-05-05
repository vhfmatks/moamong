from __future__ import annotations

from moamong_app.keyword_fetcher import (
    collect_site_keyword,
    collect_site_keywords,
    site_keyword_column,
    site_status_column,
)


def test_collect_site_keywords_normalizes_each_site_result() -> None:
    result = collect_site_keywords(
        "마사지 얼굴 베개",
        fetchers={
            "naver": lambda keyword: [" 얼굴베개 ", "얼굴베개", "마사지쿠션"],
            "coupang": lambda keyword: ["안면베개"],
        },
    )

    assert result.keywords == {
        "naver": ["얼굴베개", "마사지쿠션"],
        "coupang": ["안면베개"],
    }
    assert result.errors == {}
    assert site_keyword_column("naver") == "네이버_키워드"
    assert site_keyword_column("coupang") == "쿠팡_키워드"


def test_collect_site_keywords_keeps_working_when_one_site_fails() -> None:
    def failing_fetcher(keyword: str) -> list[str]:
        raise RuntimeError("blocked")

    result = collect_site_keywords(
        "마사지 얼굴 베개",
        fetchers={
            "naver": lambda keyword: ["얼굴베개"],
            "coupang": failing_fetcher,
        },
    )

    assert result.keywords == {"naver": ["얼굴베개"], "coupang": []}
    assert result.errors == {"coupang": "RuntimeError: blocked"}


def test_collect_site_keyword_returns_one_site_result_and_status_column() -> None:
    result = collect_site_keyword(
        "naver",
        "마사지 얼굴 베개",
        fetchers={"naver": lambda keyword: [" 얼굴베개 ", "얼굴베개"]},
    )

    assert result.keywords == {"naver": ["얼굴베개"]}
    assert result.errors == {}
    assert site_status_column("naver") == "네이버_status"
