from __future__ import annotations

import argparse
import json
import random
import re
import uuid
from html import unescape
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree

import requests


DEFAULT_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        value = item.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def fetch_11st(keyword: str) -> list[str]:
    response = requests.get(
        "https://apis.11st.co.kr/search/api/tab",
        params={"kwd": keyword, "tabId": "TOTAL_SEARCH"},
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    keywords: list[str] = []
    for group in payload.get("data", []):
        for item in group.get("relatedKeywordList", []) or []:
            if isinstance(item, dict) and item.get("text"):
                keywords.append(item["text"])

    return unique(keywords)


def fetch_gmarket(keyword: str) -> list[str]:
    encoded = quote(keyword, safe="")
    response = requests.get(
        f"https://frontapi.gmarket.co.kr/autocompleteV2/kr/json/{encoded}",
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    return unique(
        item.get("Keyword", "")
        for item in payload.get("Data", [])
        if isinstance(item, dict)
    )


def fetch_auction(keyword: str) -> list[str]:
    body = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<soap:Envelope "
        "xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' "
        "xmlns:xsd='http://www.w3.org/2001/XMLSchema' "
        "xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>"
        "<soap:Body>"
        "<GetKeywordSuggest xmlns='ns'>"
        f"<keywordHint>{keyword}</keywordHint>"
        "</GetKeywordSuggest>"
        "</soap:Body>"
        "</soap:Envelope>"
    )
    response = requests.post(
        "https://suggest.auction.co.kr/Suggest/SuggestWebService.asmx",
        headers={
            "SOAPAction": '"ns/GetKeywordSuggest"',
            "User-Agent": USER_AGENT,
            "Content-Type": "text/xml; charset=utf-8",
        },
        data=body.encode("utf-8"),
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()

    root = ElementTree.fromstring(response.content)
    keywords = [
        node.attrib.get("Keyword", "")
        for node in root.iter()
        if node.tag.endswith("KeywordContents")
    ]
    return unique(keywords)


def fetch_naver_autocomplete(keyword: str) -> list[str]:
    response = requests.get(
        "https://ac.search.naver.com/nx/ac",
        params={
            "q": keyword,
            "st": "100",
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": "0",
            "q_enc": "UTF-8",
        },
        headers={"User-Agent": USER_AGENT, "Referer": "https://www.naver.com/"},
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    keywords: list[str] = []
    for group in payload.get("items", []):
        for row in group:
            if row:
                keywords.append(str(row[0]))
    return unique(keywords)


def fetch_coupang(keyword: str) -> list[str]:
    session = requests.Session()
    pcid = "".join(str(random.randrange(10)) for _ in range(23))
    sid = uuid.uuid4().hex

    session.cookies.set("PCID", pcid, domain=".coupang.com", path="/")
    session.cookies.set("MARKETID", pcid, domain=".coupang.com", path="/")
    session.cookies.set("sid", sid, domain=".coupang.com", path="/")

    callback = "jQuery111109759935840422647_1747133902535"
    response = session.get(
        "https://www.coupang.com/np/search/autoComplete",
        params={"callback": callback, "keyword": keyword, "_": "1747133902548"},
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/javascript, application/javascript, */*; q=0.01",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.coupang.com/",
            "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()

    match = re.match(r"^[^(]+\((.*)\);?\s*$", response.text, flags=re.S)
    if not match:
        raise ValueError("Unexpected Coupang JSONP response")

    payload = json.loads(match.group(1))
    return unique(item.get("keyword", "") for item in payload if isinstance(item, dict))


FETCHERS = {
    "11st": fetch_11st,
    "gmarket": fetch_gmarket,
    "auction": fetch_auction,
    "naver": fetch_naver_autocomplete,
    "coupang": fetch_coupang,
}


def collect(keyword: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for site, fetcher in FETCHERS.items():
        try:
            result[site] = fetcher(keyword)
        except Exception as exc:
            result[site] = {"error": f"{type(exc).__name__}: {exc}"}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch recommended/autocomplete keywords from shopping sites."
    )
    parser.add_argument("keyword", help="Search keyword, e.g. 버터")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print site sections instead of JSON.",
    )
    args = parser.parse_args()

    result = collect(args.keyword)
    if not args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for site, value in result.items():
        print(f"\n[{site}]")
        if isinstance(value, dict) and "error" in value:
            print(value["error"])
            continue
        for item in value:
            print(f"- {unescape(item)}")


if __name__ == "__main__":
    main()
