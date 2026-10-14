"""Allowlisted individual heritage sources, separate from UNESCO group records."""

import ssl
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import httpx

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource
from culturebridge.services.official_service import OfficialServiceError

INDIVIDUALS = {
    "horyuji-pagoda": {
        "name": "Five-storied Pagoda",
        "korean": "호류지 오층탑",
        "country": "Japan",
        "parent": "unesco:660",
        "organization": "호류지 사찰 공식 사이트",
        "url": "https://www.horyuji.or.jp/en/garan/gojyunoto/",
        "type": "Pagoda",
    },
    "dayanta": {
        "name": "Giant Wild Goose Pagoda",
        "korean": "대안탑",
        "country": "China",
        "parent": "unesco:1442",
        "organization": "시안시 정부",
        "url": "https://en.xa.gov.cn/CultureTravel/Attractions/1691691504798126082.html",
        "type": "Pagoda",
    },
}


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.current = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.depth, self.current = 1, []

    def handle_endtag(self, tag):
        if tag == "p" and self.depth:
            self.rows.append(" ".join("".join(self.current).split()))
            self.depth = 0

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)


def fetch_individual(identity, refresh=False):
    record = INDIVIDUALS[identity]
    source_id = "official:" + identity
    with transaction() as connection:
        row = connection.execute(
            "SELECT source_json FROM agent_source_cache WHERE id=?", (source_id,)
        ).fetchone()
    old = CollectedSource.model_validate_json(row["source_json"]) if row else None
    if (
        old
        and not refresh
        and datetime.now(UTC) - old.retrieved_at
        < timedelta(hours=get_settings().heritage_cache_hours)
    ):
        return old.model_copy(update={"status": "cached"})
    try:
        with httpx.Client(
            verify=ssl.create_default_context(),
            timeout=get_settings().heritage_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "CultureBridge/0.1"},
        ) as client:
            with client.stream("GET", record["url"]) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("Source too large")
        parser = Paragraphs()
        parser.feed(body.decode("utf-8"))
        starts = ("The Five-storied Pagoda", "The Giant Wild Goose Pagoda")
        selected = [p for p in parser.rows if p.startswith(starts)]
        if not selected:
            raise ValueError("No individual subject paragraph")
        source = CollectedSource(
            id=source_id,
            heritage_id=source_id,
            title=record["name"],
            organization=record["organization"],
            source_url=record["url"],
            feed_url=record["url"],
            retrieved_at=datetime.now(UTC),
            content="\n".join(selected),
            status="fresh",
            content_kind="individual_text",
            license_url=record["url"],
            scope_note="개별 유산 공식 소개입니다. UNESCO 유산군 설명과 구분합니다. "
            "원문 이용 조건을 확인하세요.",
        )
        with transaction() as connection:
            connection.execute(
                "INSERT INTO agent_source_cache VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "source_json=excluded.source_json,retrieved_at=excluded.retrieved_at",
                (source.id, source.model_dump_json(), source.retrieved_at.isoformat()),
            )
        return source
    except Exception as exc:
        if old:
            return old.model_copy(update={"status": "stale"})
        raise OfficialServiceError("개별 해외 유산의 공식 소개를 수집하지 못했습니다.") from exc
