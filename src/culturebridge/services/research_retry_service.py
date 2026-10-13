from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import httpx

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource
from culturebridge.services.official_service import OfficialServiceError

DAYANTA_URL = "https://en.xa.gov.cn/CultureTravel/Attractions/1691691504798126082.html"


class _Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.current = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.active, self.current = True, []

    def handle_endtag(self, tag):
        if tag == "p" and self.active:
            self.paragraphs.append("".join(self.current))
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.current.append(data)


def collect_dayanta_alternative() -> CollectedSource:
    record_id = "xian:dayanta"
    with transaction() as connection:
        row = connection.execute(
            "SELECT source_json FROM agent_source_cache WHERE id=?", (record_id,)
        ).fetchone()
    if row:
        cached = CollectedSource.model_validate_json(row["source_json"])
        if datetime.now(UTC) - cached.retrieved_at < timedelta(
            hours=get_settings().heritage_cache_hours
        ):
            cached.status = "cached"
            return cached
    try:
        with httpx.Client(
            timeout=get_settings().heritage_timeout_seconds,
            headers={
                "User-Agent": "CultureBridge/0.1 (+https://github.com/sangyeop12/culturebridge)",
                "Accept": "text/html",
            },
        ) as client:
            with client.stream("GET", DAYANTA_URL) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("Response too large")
        parser = _Paragraphs()
        parser.feed(bytes(body).decode("utf-8"))
        paragraphs = [
            p for p in parser.paragraphs if p.strip().startswith("The Giant Wild Goose Pagoda is")
        ]
        if len(paragraphs) != 1:
            raise ValueError("Cannot identify individual pagoda paragraph")
        source = CollectedSource(
            id=record_id,
            heritage_id="dayanta",
            title="Giant Wild Goose Pagoda",
            organization="시안시 정부",
            source_url=DAYANTA_URL,
            feed_url=DAYANTA_URL,
            retrieved_at=datetime.now(UTC),
            content=paragraphs[0].strip(),
            status="fresh",
            content_kind="individual_text",
            license_url=DAYANTA_URL,
            scope_note="시안시 정부의 대안탑 소개입니다. 인물 생애 연대는 건립연도가 아닙니다.",
        )
        with transaction() as connection:
            connection.execute(
                """INSERT INTO agent_source_cache(id,source_json,retrieved_at) VALUES(?,?,?)
                ON CONFLICT(id) DO UPDATE SET source_json=excluded.source_json,
                retrieved_at=excluded.retrieved_at""",
                (record_id, source.model_dump_json(), source.retrieved_at.isoformat()),
            )
        return source
    except Exception as exc:
        if row:
            cached.status = "stale"
            return cached
        raise OfficialServiceError("대안탑의 추가 공식 소개를 수집하지 못했습니다.") from exc


def retry_missing_sources(left_id, right_id, sources, missing_heritages):
    from culturebridge.services.source_collection_service import collect_official_sources

    refreshed = collect_official_sources(left_id, right_id, refresh=True)
    by_key = {(s.heritage_id, s.id): s for s in sources}
    for source in refreshed:
        key = (source.heritage_id, source.id)
        old = by_key.get(key)
        if (
            source.status in {"fresh", "cached"}
            or old is None
            or old.status not in {"fresh", "cached"}
        ):
            by_key[key] = source
    if "dayanta" in missing_heritages:
        try:
            alternative = collect_dayanta_alternative()
            by_key[(alternative.heritage_id, alternative.id)] = alternative
        except OfficialServiceError:
            failed = CollectedSource(
                id="xian:dayanta",
                heritage_id="dayanta",
                title="Giant Wild Goose Pagoda",
                organization="시안시 정부",
                source_url=DAYANTA_URL,
                feed_url=DAYANTA_URL,
                content_kind="individual_text",
                status="unavailable",
                scope_note="추가 공식 출처 조회 실패입니다. 원문 수집 완료로 간주하지 않습니다.",
            )
            by_key[(failed.heritage_id, failed.id)] = failed
    return list(by_key.values())
