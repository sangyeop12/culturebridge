"""Bounded public catalogue search. Titles and official links, never AI source text.

This is the NIKH public website's search interface, not a contracted Open API.
No credentials, unrestricted crawling, full-text replication or AI transmission.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urlencode

import httpx

from culturebridge.config import get_settings

ORIGIN = "https://db.history.go.kr"
SEARCH_PATH = "/diachronic/search/searchResultList.do"


def title_matches(query, title):
    """Lexical title hints, not proof that an article answers the historical question."""
    aliases = {"세종대왕": ("세종대왕", "세종"), "한글": ("한글", "훈민정음", "언문")}
    groups = []
    for term in query.split():
        term = term.removesuffix("의") if len(term) > 2 else term
        if term in {"관한", "대한", "자료", "찾기"}:
            continue
        canonical = next((key for key, words in aliases.items() if term in words), term)
        words = aliases.get(canonical, (term,))
        if len(term) >= 2 and not any(key == canonical for key, _ in groups):
            groups.append((canonical, words))
    compact = re.sub(r"\s+", "", title).casefold()
    matched = [
        word
        for _, words in groups
        if (word := next((word for word in words if word.casefold() in compact), None))
    ]
    return matched, len(groups)


def clean_query(query):
    query = query.strip()
    if not query or len(query) > 80 or not re.fullmatch(r"[\w\s·ㆍ()\-]+", query):
        raise ValueError("인물이나 사건의 이름을 80자 이내로 입력해 주세요.")
    return query


class CatalogueParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            match = re.fullmatch(
                r"fnGoItemLevel\('nh',\s*'(nh_\d+(?:_\d+)+)',\s*'\d+'\);\s*return false;",
                attrs.get("onclick", "").strip(),
            )
            self.current = {"key": match[1], "text": []} if match else None

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            title = " ".join("".join(self.current["text"]).split())
            key = self.current["key"]
            if title and len(title) <= 300 and key not in {i["key"] for i in self.items}:
                self.items.append({"key": key, "title": title})
            self.current = None


def _request(params):
    with httpx.Client(timeout=min(get_settings().heritage_timeout_seconds, 15)) as client:
        with client.stream("GET", ORIGIN + SEARCH_PATH, params=params) as response:
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                raise ValueError("unexpected_history_format")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 1_500_000:
                    raise ValueError("history_response_too_large")
    html = content.decode("utf-8", errors="strict")
    if "search-result" not in html and "list-item" not in html:
        raise ValueError("history_search_changed")
    parser = CatalogueParser()
    parser.feed(html)
    return parser.items[:5]


def search_history(query):
    query = clean_query(query)
    params = {
        "searchItemId": "nh",
        "pageIndex": 1,
        "pageUnit": 5,
        "titleWord": query,
        "wordImages": query,
        "totalWord": query,
    }
    try:
        items = _request(params)
        title_only = True
        if not items:
            params.pop("titleWord")
            items = _request(params)
            title_only = False
    except Exception as exc:
        raise ValueError("역사 자료 검색에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.") from exc
    records = [
        {
            "id": "nikh:" + item["key"],
            "name": item["title"],
            "region": "국사편찬위원회 · 신편 한국사",
            "city": "",
            "metadata_only": True,
            "catalogue": "history",
            "reading_url": ORIGIN + "/diachronic/level.do?" + urlencode({"levelId": item["key"]}),
        }
        for item in items
    ]
    for record in records:
        matched, total = title_matches(query, record["name"])
        record["title_matched_terms"] = matched
        record["title_relevance"] = (
            "all_terms"
            if total and len(matched) == total
            else "some_terms"
            if matched
            else "unconfirmed"
        )
        record["match_note"] = (
            "제목에서 확인한 관련 표현: "
            + " · ".join(matched)
            + ". 원문 내용은 직접 확인해 주세요."
            if matched
            else "제목만으로 질문과의 관련성을 확인하지 못했어요. 원문을 먼저 살펴봐 주세요."
        )
    records.sort(key=lambda row: len(row["title_matched_terms"]), reverse=True)
    return records, (
        "제목에서 검색어를 확인한 자료를 먼저 표시해요. 질문의 답인지는 원문에서 확인해 주세요."
        if title_only and items
        else "본문 검색으로 찾은 목록이에요. 제목과 질문의 관련성은 아래 안내를 확인해 주세요."
        if items
        else "일치하는 자료를 찾지 못했어요. 짧은 인물·사건 이름으로 다시 찾아보세요."
    )
