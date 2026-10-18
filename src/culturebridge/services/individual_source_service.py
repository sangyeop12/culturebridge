"""Allowlisted individual heritage sources, separate from UNESCO group records."""

import json
import ssl
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel

from culturebridge.config import get_settings
from culturebridge.data.individual_sources import EXTENDED_INDIVIDUALS
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.source_permission_service import policy_url

INDIVIDUALS = {
    "horyuji-pagoda": {
        "name": "Five-storied Pagoda",
        "korean": "호류지 오층탑",
        "country": "Japan",
        "parent": "unesco:660",
        "organization": "호류지 사찰 공식 사이트",
        "url": "https://www.horyuji.or.jp/en/garan/gojyunoto/",
        "type": "Pagoda",
        "starts": ("The Five-storied Pagoda",),
    },
    "dayanta": {
        "name": "Giant Wild Goose Pagoda",
        "korean": "대안탑",
        "country": "China",
        "parent": "unesco:1442",
        "organization": "시안시 정부",
        "url": "https://en.xa.gov.cn/CultureTravel/Attractions/1691691504798126082.html",
        "type": "Pagoda",
        "starts": ("The Giant Wild Goose Pagoda",),
    },
    "taj-mahal-mausoleum": {
        "name": "Taj Mahal Mausoleum",
        "korean": "타지마할 묘당",
        "country": "India",
        "parent": "unesco:252",
        "organization": "인도 우타르프라데시 관광부",
        "url": "https://www.tajmahal.gov.in/overview.aspx",
        "type": "Tomb",
        "starts": (
            "The Taj Mahal is",
            "The tomb laid",
            "The tomb is",
            "Thecentral hall",
            "Majestic and sensuous",
        ),
    },
    "grand-trianon": {
        "name": "Grand Trianon Palace",
        "korean": "그랑 트리아농 궁전",
        "country": "France",
        "parent": "unesco:83",
        "organization": "베르사유 궁전·박물관·국립영지",
        "url": "https://en.chateauversailles.fr/discover/estate/estate-trianon/grand-trianon",
        "type": "Palace",
        "starts": (
            "The Grand Trianon was",
            "“A little palace",
            '"A little palace',
            "Heavily influenced by Italian architecture",
            "In the Grand Trianon, the royal apartments",
        ),
    },
    **EXTENDED_INDIVIDUALS,
}


class IndividualHit(BaseModel):
    id: str
    name: str
    korean: str
    country: str
    primary_type: str
    parent_id: str
    source_url: str
    unit: str


def search_individuals(query=""):
    """Registered metadata only. A hit does not claim a successful live fetch."""
    from culturebridge.services.unesco_service import COUNTRY_ALIASES, normalize_search

    term = normalize_search(query)
    country = COUNTRY_ALIASES.get(query.strip(), query.strip())
    hits = []
    from culturebridge.services.source_registry_service import reviews

    reviewed = reviews()
    for key, record in INDIVIDUALS.items():
        review = reviewed.get(key, {})
        if review.get("usage_status") == "restricted":
            continue
        words = [
            key,
            record["name"],
            record["korean"],
            record["country"],
            *record.get("aliases", ()),
            review.get("korean_name", ""),
            *json.loads(review.get("aliases_json", "[]")),
        ]
        if (
            term
            and not any(term in normalize_search(word) for word in words)
            and country != record["country"]
        ):
            continue
        hits.append(
            IndividualHit(
                id="official:" + key,
                name=record["name"],
                korean=review.get("korean_name", record["korean"]),
                country=record["country"],
                primary_type=record["type"],
                parent_id=record["parent"],
                source_url=record["url"],
                unit=record.get("unit", "building"),
            )
        )
    return hits


def selected_paragraphs(record, paragraphs):
    """Exact provider excerpts, with optional sentence-level subject selectors."""
    from culturebridge.services.subject_service import sentences

    paragraphs = list(dict.fromkeys(p for p in paragraphs if p.startswith(record["starts"])))
    selected = paragraphs
    if record.get("sentence_starts"):
        selected = [
            s for p in selected for s in sentences(p) if s.startswith(record["sentence_starts"])
        ]
    selected = selected + [
        quote for quote in record.get("excerpts", ()) if any(quote in p for p in paragraphs)
    ]
    return selected


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
    from culturebridge.services.source_registry_service import reviews

    if reviews().get(identity, {}).get("usage_status") == "restricted":
        raise OfficialServiceError(
            "관리자가 이용 제한으로 표시한 자료입니다. 공식 출처를 직접 확인하세요."
        )
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
        return CollectedSource.model_validate(
            {
                **old.model_dump(),
                "status": "cached",
                "license_url": policy_url(record["url"]),
            }
        )
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
                    if len(body) > min(record.get("max_bytes", 2_000_000), 6_000_000):
                        raise ValueError("Source too large")
        parser = Paragraphs()
        parser.feed(body.decode("utf-8"))
        selected = selected_paragraphs(record, parser.rows)
        if not selected:
            raise ValueError("No individual subject paragraph")
        source = CollectedSource(
            id=source_id,
            heritage_id=source_id,
            title=record["korean"] if record.get("language") == "ko" else record["name"],
            organization=record["organization"],
            source_url=record["url"],
            feed_url=record["url"],
            retrieved_at=datetime.now(UTC),
            content="\n".join(selected),
            status="fresh",
            content_kind="individual_text",
            license_url=policy_url(record["url"]),
            scope_note=(
                "특정 유산 경내 전체의 공식 소개입니다. 개별 건물 하나의 설명과 다릅니다. "
                if record.get("unit") == "site"
                else "개별 건물의 공식 소개입니다. "
            )
            + "등록한 대상 문단·문장을 발췌했으며 UNESCO 등재 유산군과 구분합니다. "
            "각 기관의 원문 이용 조건과 역사적 의미를 별도로 확인하세요.",
        )
        with transaction() as connection:
            connection.execute(
                "INSERT INTO agent_source_cache VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "source_json=excluded.source_json,retrieved_at=excluded.retrieved_at",
                (source.id, source.model_dump_json(), source.retrieved_at.isoformat()),
            )
        from culturebridge.services.source_registry_service import record_attempt

        record_attempt(identity, "fresh")
        return source
    except Exception as exc:
        from culturebridge.services.source_registry_service import record_attempt

        error_code = (
            "HTTP_" + str(exc.response.status_code)
            if isinstance(exc, httpx.HTTPStatusError)
            else type(exc.__cause__ or exc).__name__
        )
        record_attempt(identity, "stale" if old else "unavailable", error_code)
        if old:
            return old.model_copy(update={"status": "stale"})
        raise OfficialServiceError("개별 해외 유산의 공식 소개를 수집하지 못했습니다.") from exc
