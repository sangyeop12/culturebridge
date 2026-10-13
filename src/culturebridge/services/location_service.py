import math
from datetime import UTC, datetime, timedelta

from defusedxml.ElementTree import fromstring

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.domain.official_models import OfficialLocation
from culturebridge.services.official_service import (
    OfficialDocumentNotFoundError,
    OfficialServiceError,
    _fetch,
    _text,
    get_official_document,
)

GIS_BASE_URL = "https://gis-heritage.go.kr/openapi/xmlService/"


def _location_feed(kind: str):
    with transaction() as connection:
        cached = connection.execute(
            "SELECT raw_xml, retrieved_at FROM official_location_feeds WHERE kind_code = ?",
            (kind,),
        ).fetchone()
    now = datetime.now(UTC)
    if cached:
        fetched_at = datetime.fromisoformat(cached["retrieved_at"])
        if now - fetched_at < timedelta(hours=get_settings().heritage_cache_hours):
            return fromstring(cached["raw_xml"]), fetched_at, True, False
    try:
        root, raw_xml = _fetch(
            "spca.do", {"ccbaKdcd": kind}, base_url=GIS_BASE_URL, root_tag="response"
        )
    except OfficialServiceError:
        if cached:
            return fromstring(cached["raw_xml"]), fetched_at, True, True
        raise
    # Validate before caching: a response root alone may be an upstream error.
    if not root.findall("spca"):
        raise OfficialServiceError("공간정보 API에서 위치 목록을 받지 못했습니다.")
    with transaction() as connection:
        connection.execute(
            """INSERT INTO official_location_feeds(kind_code, raw_xml, retrieved_at)
            VALUES (?, ?, ?) ON CONFLICT(kind_code) DO UPDATE SET
            raw_xml=excluded.raw_xml, retrieved_at=excluded.retrieved_at""",
            (kind, raw_xml, now.isoformat()),
        )
    return root, now, False, False


def get_official_location(kind: str, number: str, region: str) -> OfficialLocation:
    document = get_official_document(kind, number, region)
    root, retrieved_at, cached, stale = _location_feed(kind)

    def normalize(value):
        return "".join(value.split())

    matches = [
        item
        for item in root.findall("spca")
        if normalize(_text(item, "ccbaMnm")) == normalize(document.name)
        and _text(item, "ccmaName") == document.designation
        and (not document.city or document.city in _text(item, "vlocName"))
    ]
    if not matches:
        raise OfficialDocumentNotFoundError(document.name)
    if len(matches) != 1:
        raise OfficialServiceError("같은 이름의 위치 자료가 여러 건이라 확정할 수 없습니다.")
    item = matches[0]
    try:
        x, y = float(_text(item, "cnX")), float(_text(item, "cnY"))
        if not math.isfinite(x) or not math.isfinite(y) or not x or not y:
            raise ValueError("Invalid projected coordinates")
    except ValueError as exc:
        raise OfficialServiceError("공식 위치 자료의 좌표를 확인할 수 없습니다.") from exc
    return OfficialLocation(
        name=document.name,
        designation=document.designation,
        location=_text(item, "vlocName"),
        projected_x=x,
        projected_y=y,
        latitude=None if document.stale else document.latitude,
        longitude=None if document.stale else document.longitude,
        source_url=GIS_BASE_URL + "spca.do?ccbaKdcd=" + kind,
        geographic_source_url=document.source_url,
        retrieved_at=retrieved_at,
        cached=cached,
        stale=stale,
    )
