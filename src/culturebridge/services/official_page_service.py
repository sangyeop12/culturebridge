"""One bounded supplemental WHC request. A 403 is not bypassed."""

import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import httpx

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.subject_service import is_group


class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "h2", "h3", "h4", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def parse_synthesis(html, title):
    parser = _Blocks()
    parser.feed(html)
    text = "".join(parser.parts)
    # Fail closed: don't turn navigation, dates of inscription, or other languages into evidence.
    if title.casefold() not in text.casefold():
        raise OfficialServiceError("공식 상세 페이지의 대상 이름을 확인하지 못했습니다.")
    match = re.search(
        r"Brief synthesis\s*(.+?)\s*(?:Integrity|Criterion\s*\(|Criteria\s*\()", text, re.S
    )
    if not match or len(match.group(1).strip()) < 80:
        raise OfficialServiceError("공식 상세 페이지의 영문 설명 범위를 확인하지 못했습니다.")
    return match.group(1).strip()[:20000]


def cached_supplement(heritage_id):
    with transaction() as connection:
        row = connection.execute(
            "SELECT source_json FROM agent_source_cache WHERE id=?", ("whc:" + heritage_id,)
        ).fetchone()
    if not row:
        return None
    source = CollectedSource.model_validate_json(row["source_json"])
    if source.retrieved_at and datetime.now(UTC) - source.retrieved_at < timedelta(
        hours=get_settings().heritage_cache_hours
    ):
        return source
    return None


def collect_supplement(source):
    if not re.fullmatch(r"unesco:\d{1,10}", source.heritage_id):
        return None
    cached = cached_supplement(source.heritage_id)
    if cached:
        return cached
    url = "https://whc.unesco.org/en/list/" + source.heritage_id.split(":")[1] + "/"
    supplement = CollectedSource.model_validate(
        {
            **source.model_dump(),
            "id": "whc:" + source.heritage_id,
            "source_url": url,
            "feed_url": url,
            "content": "",
            "status": "unavailable",
            "retrieved_at": datetime.now(UTC),
            "content_kind": "group_text"
            if is_group(source.title, source.content)
            else "individual_text",
            "license_url": "https://creativecommons.org/licenses/by-sa/3.0/igo/",
            "scope_note": "UNESCO 공식 상세 페이지 영문 설명의 추가 수집입니다. "
            "독립 기관의 교차 검증은 아닙니다.",
        }
    )
    try:
        with httpx.Client(
            timeout=get_settings().heritage_timeout_seconds, follow_redirects=False
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise OfficialServiceError("공식 상세 페이지가 허용 크기를 넘었습니다.")
        supplement.content = parse_synthesis(bytes(body).decode("utf-8"), source.title)
        supplement.status = "fresh"
    except (httpx.HTTPError, OfficialServiceError, UnicodeError):
        supplement.scope_note += (
            " 추가 수집 실패·근거로 사용하지 않습니다. 접근 제한을 우회하지 않습니다."
        )
    # Cache failures too, avoiding repeated requests to a blocked provider.
    with transaction() as connection:
        connection.execute(
            "INSERT INTO agent_source_cache(id,source_json,retrieved_at) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET source_json=excluded.source_json,"
            "retrieved_at=excluded.retrieved_at",
            (supplement.id, supplement.model_dump_json(), supplement.retrieved_at.isoformat()),
        )
    return supplement
