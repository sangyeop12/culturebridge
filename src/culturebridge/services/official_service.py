import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urlencode

import httpx
from defusedxml.ElementTree import fromstring
from pydantic import ValidationError

from culturebridge.config import get_settings
from culturebridge.database import database_path, transaction
from culturebridge.domain.official_models import (
    OfficialDocument,
    OfficialHeritageItem,
    OfficialSearchResult,
)

BASE_URL = "https://www.khs.go.kr/cha/"
SEOKGURAM_CODES = ("11", "0000240000000", "37")


class OfficialServiceError(RuntimeError):
    pass


class OfficialDocumentNotFoundError(KeyError):
    pass


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "div"}:
            self.parts.append("\n")


def _text(node, name: str) -> str:
    return (node.findtext(name) or "").strip()


def _fetch(
    endpoint: str, params: dict, *, base_url: str = BASE_URL, root_tag: str = "result"
) -> tuple[object, str]:
    try:
        with httpx.Client(timeout=get_settings().heritage_timeout_seconds) as client:
            with client.stream("GET", base_url + endpoint, params=params) as response:
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    payload.extend(chunk)
                    if len(payload) > 2_000_000:
                        raise OfficialServiceError("공식 자료 응답이 너무 큽니다.")
        root = fromstring(bytes(payload))
        if root.tag.rsplit("}", 1)[-1] != root_tag:
            raise OfficialServiceError("공식 자료 응답 형식을 확인할 수 없습니다.")
        return root, bytes(payload).decode("utf-8-sig")
    except OfficialServiceError:
        raise
    except Exception as exc:
        raise OfficialServiceError(
            "국가유산청 자료를 불러오지 못했습니다. 잠시 후 다시 시도하세요."
        ) from exc


def search_official_heritages(query: str, page: int = 1, page_size: int = 10):
    if not 1 <= len(query.strip()) <= 100 or not 1 <= page <= 10000 or not 1 <= page_size <= 50:
        raise ValueError("검색어·페이지 범위를 확인해 주세요.")
    root, _ = _fetch(
        "SearchKindOpenapiList.do",
        {"ccbaMnm1": query.strip(), "pageIndex": page, "pageUnit": page_size},
    )
    try:
        items = [
            OfficialHeritageItem(
                kind_code=_text(item, "ccbaKdcd"),
                asset_number=_text(item, "ccbaAsno"),
                region_code=_text(item, "ccbaCtcd"),
                name=_text(item, "ccbaMnm1"),
                designation=_text(item, "ccmaName"),
                region=_text(item, "ccbaCtcdNm"),
                city=_text(item, "ccsiName"),
            )
            for item in root.findall("item")
            if _text(item, "ccbaCncl") != "Y"
        ]
        return OfficialSearchResult(
            items=items, total=int(_text(root, "totalCnt") or "0"), page=page, page_size=page_size
        )
    except (ValidationError, ValueError) as exc:
        raise OfficialServiceError("공식 검색 응답 형식을 확인할 수 없습니다.") from exc


def get_cached_document(kind: str, number: str, region: str) -> OfficialDocument | None:
    if not database_path().exists():
        return None
    with transaction() as connection:
        if (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='official_documents'"
            ).fetchone()
            is None
        ):
            return None
        row = connection.execute(
            "SELECT document_json, raw_xml FROM official_documents WHERE id = ?",
            (f"khs:{kind}:{number}:{region}",),
        ).fetchone()
    if row is None:
        return None
    document = OfficialDocument.model_validate_json(row["document_json"])
    if document.latitude is None or document.longitude is None:
        root = fromstring(row["raw_xml"])
        document.latitude, document.longitude = _geographic_coordinates(root)
    document.cached = True
    document.stale = datetime.now(UTC) - document.retrieved_at > timedelta(
        hours=get_settings().heritage_cache_hours
    )
    return document


def _geographic_coordinates(root) -> tuple[float | None, float | None]:
    try:
        latitude = float(_text(root, "latitude"))
        longitude = float(_text(root, "longitude"))
        if -90 <= latitude <= 90 and -180 <= longitude <= 180 and latitude and longitude:
            return latitude, longitude
    except ValueError:
        pass
    return None, None


def get_official_document(
    kind: str, number: str, region: str, *, refresh: bool = False
) -> OfficialDocument:
    if (
        not re.fullmatch(r"\d{2}", kind)
        or not re.fullmatch(r"\d{1,20}", number)
        or not re.fullmatch(r"\d{2}", region)
    ):
        raise ValueError("국가유산 조회 코드를 확인해 주세요.")
    cached = get_cached_document(kind, number, region)
    if cached and not cached.stale and not refresh:
        return cached
    params = {"ccbaKdcd": kind, "ccbaAsno": number, "ccbaCtcd": region}
    try:
        root, raw_xml = _fetch("SearchKindOpenapiDt.do", params)
    except OfficialServiceError:
        if cached:
            cached.notice = (
                "공식 API 연결 실패로 이전에 수집한 자료를 표시합니다. 조회일을 확인하세요."
            )
            return cached
        raise
    item = root.find("item")
    if item is None or not _text(item, "ccbaMnm1"):
        raise OfficialDocumentNotFoundError(number)
    if any(_text(root, key) != value for key, value in params.items()):
        raise OfficialServiceError("요청과 다른 국가유산의 응답을 받았습니다.")
    parser = _PlainText()
    parser.feed(_text(item, "content"))
    content = "".join(parser.parts).strip()
    if not content:
        raise OfficialServiceError("공식 자료의 설명이 비어 있습니다.")
    document = OfficialDocument(
        latitude=_geographic_coordinates(root)[0],
        longitude=_geographic_coordinates(root)[1],
        kind_code=kind,
        asset_number=number,
        region_code=region,
        name=_text(item, "ccbaMnm1"),
        designation=_text(item, "ccmaName"),
        region=_text(item, "ccbaCtcdNm"),
        city=_text(item, "ccsiName"),
        period=_text(item, "ccceName"),
        address=_text(item, "ccbaLcad"),
        content=content,
        source_url=BASE_URL + "SearchKindOpenapiDt.do?" + urlencode(params),
        retrieved_at=datetime.now(UTC),
    )
    with transaction() as connection:
        connection.execute(
            """INSERT INTO official_documents (id, document_json, raw_xml, retrieved_at)
            VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
            document_json=excluded.document_json, raw_xml=excluded.raw_xml,
            retrieved_at=excluded.retrieved_at""",
            (
                document.record_id,
                document.model_dump_json(),
                raw_xml,
                document.retrieved_at.isoformat(),
            ),
        )
    return document
