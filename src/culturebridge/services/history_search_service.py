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
    return [
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
    ], (
        "제목이 일치하는 자료를 먼저 찾았어요."
        if title_only and items
        else "본문에 검색어가 포함된 자료예요. 제목과 원문 맥락을 함께 확인해 주세요."
        if items
        else "일치하는 자료를 찾지 못했어요. 짧은 인물·사건 이름으로 다시 찾아보세요."
    )
