import json
import unicodedata
from datetime import UTC, datetime, timedelta

import httpx
from defusedxml.ElementTree import fromstring
from pydantic import BaseModel, Field, HttpUrl

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.services.official_service import OfficialServiceError, _PlainText

UNESCO_XML_URL = "https://whc.unesco.org/en/list/xml"
UNESCO_TERMS_URL = "https://whc.unesco.org/en/syndication"
MAX_BYTES = 10_000_000
DATAHUB_URL = "https://data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json"
DATAHUB_INFO_URL = "https://data.unesco.org/explore/dataset/whc001/information/"
HERITAGE_ALIASES = {
    "660": ("호류지", "법륭사", "호류지 불교 건축물"),
    "736": ("석굴암", "불국사", "석굴암과 불국사"),
    "1442": ("실크로드", "대안탑"),
    "1418": ("후지산", "일본 후지산"),
    "668": ("앙코르", "앙코르와트"),
    "439": ("자금성", "명청 황궁"),
    "438": ("만리장성",),
    "252": ("타지마할",),
    "274": ("마추픽추",),
    "91": ("로마 역사 지구", "콜로세움"),
    "86": ("기자 피라미드", "피라미드"),
    "83": ("베르사유", "베르사유 궁전"),
}
COUNTRY_ALIASES = {
    "한국": "Republic of Korea",
    "대한민국": "Republic of Korea",
    "일본": "Japan",
    "중국": "China",
    "인도": "India",
    "프랑스": "France",
    "이탈리아": "Italy",
    "영국": "United Kingdom of Great Britain and Northern Ireland",
    "미국": "United States of America",
    "이집트": "Egypt",
    "캄보디아": "Cambodia",
    "페루": "Peru",
    "그리스": "Greece",
    "스페인": "Spain",
    "독일": "Germany",
    "베트남": "Viet Nam",
}


def normalize_search(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split()).replace("-", "")


class UnescoSuggestion(BaseModel):
    value: str
    label: str
    record_id: str | None = None


def _matches_query(record, query: str) -> bool:
    # Country aliases match complete country tokens, not a word in a site's name.
    country = next(
        (
            name
            for alias, name in COUNTRY_ALIASES.items()
            if normalize_search(alias) == normalize_search(query)
        ),
        None,
    )
    if country:
        return country in [part.strip() for part in record.countries.split(";")]
    term = normalize_search(query)
    if term.isdecimal():
        return record.id == term
    aliases = HERITAGE_ALIASES.get(record.id, ())
    if any(term in normalize_search(alias) for alias in aliases):
        return True
    return term in normalize_search(record.name) or term in normalize_search(record.countries)


def get_unesco_suggestions(query: str = "", limit: int = 8) -> list[UnescoSuggestion]:
    """Use the local snapshot only: typing never invokes a remote API."""
    with transaction() as connection:
        cached = connection.execute("SELECT * FROM unesco_feeds WHERE language='en'").fetchone()
    if not cached:
        return []
    parser = parse_unesco_json if cached["format"] == "json" else parse_unesco_xml
    records = parser(cached["raw_xml"].encode("utf-8"))
    suggestions = []
    countries = {part.strip() for record in records for part in record.countries.split(";")}
    for record in records:
        for alias in HERITAGE_ALIASES.get(record.id, ()):
            label = f"{alias} · {record.name}"
            if alias == "대안탑":
                label = "대안탑 · 실크로드 등재 유산군"
            suggestions.append(UnescoSuggestion(value=alias, label=label, record_id=record.id))
    for alias, country in COUNTRY_ALIASES.items():
        if country in countries:
            suggestions.append(UnescoSuggestion(value=alias, label=f"{alias} · {country}"))
    suggestions.extend(
        UnescoSuggestion(
            value=record.name, label=f"{record.name} · ID {record.id}", record_id=record.id
        )
        for record in records
    )
    term = normalize_search(query)
    selected = [s for s in suggestions if term in normalize_search(s.value)]
    selected.sort(
        key=lambda s: (
            0
            if normalize_search(s.value) == term
            else 1
            if normalize_search(s.value).startswith(term)
            else 2
        )
    )
    unique = {}
    for suggestion in selected:
        unique.setdefault(normalize_search(suggestion.value), suggestion)
    return list(unique.values())[:limit]


class UnescoRecord(BaseModel):
    id: str = Field(pattern=r"^\d{1,10}$")
    name: str
    countries: str
    inscription_year: str
    source_url: HttpUrl
    description: str = ""


class UnescoResult(BaseModel):
    records: list[UnescoRecord]
    total: int
    retrieved_at: datetime
    cached: bool
    stale: bool
    terms_url: str = UNESCO_TERMS_URL
    notice: str = "세계유산 등재 목록입니다. 등재연도는 유산의 건립연도가 아닙니다."
    feed_source_url: str = UNESCO_XML_URL
    source_format: str = "xml"
    license_url: str = UNESCO_TERMS_URL


def parse_unesco_xml(payload: bytes) -> list[UnescoRecord]:
    try:
        if len(payload) > MAX_BYTES:
            raise ValueError("XML too large")
        root = fromstring(payload)
        if root.tag != "query":
            raise ValueError("Unexpected XML root")
        records = []
        seen = set()
        for row in root.findall("row"):
            record_id = (row.findtext("id_number") or "").strip()
            name_parser = _PlainText()
            name_parser.feed(row.findtext("site") or "")
            name = "".join(name_parser.parts).strip()
            if not name or record_id in seen:
                raise ValueError("Missing name or duplicate ID")
            records.append(
                UnescoRecord(
                    id=record_id,
                    name=name,
                    countries=(row.findtext("states") or "").strip(),
                    inscription_year=(row.findtext("date_inscribed") or "").strip(),
                    source_url=f"https://whc.unesco.org/en/list/{record_id}/",
                )
            )
            seen.add(record_id)
        if not records:
            raise ValueError("Empty feed")
        return records
    except Exception as exc:
        raise OfficialServiceError("UNESCO XML 형식을 확인할 수 없습니다.") from exc


def parse_unesco_json(payload: bytes) -> list[UnescoRecord]:
    try:
        if len(payload) > MAX_BYTES:
            raise ValueError("Feed too large")
        rows = json.loads(payload)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Empty or unexpected DataHub response")
        records = []
        seen = set()
        for row in rows:
            countries = row["states_names"]
            if isinstance(countries, list) and all(isinstance(c, str) for c in countries):
                countries = "; ".join(countries)
            if not isinstance(countries, str):
                raise ValueError("Invalid country names")
            record = UnescoRecord(
                id=str(row["id_no"]),
                name=row["name_en"],
                countries=countries,
                inscription_year=str(row["date_inscribed"]),
                source_url=f"https://whc.unesco.org/en/list/{row['id_no']}/",
                description=_plain_description(row.get("short_description_en") or ""),
            )
            if not record.name.strip() or record.id in seen:
                raise ValueError("Duplicate ID or missing name")
            records.append(record)
            seen.add(record.id)
        return records
    except Exception as exc:
        raise OfficialServiceError("UNESCO DataHub 응답 형식을 확인할 수 없습니다.") from exc


def _store_feed(payload: bytes, format_name: str, source_url: str, license_url: str) -> None:
    raw = payload.decode("utf-8-sig")
    with transaction() as connection:
        connection.execute(
            """INSERT INTO unesco_feeds
            (language, raw_xml, retrieved_at, format, source_url, license_url)
            VALUES ('en', ?, ?, ?, ?, ?)
            ON CONFLICT(language) DO UPDATE SET raw_xml=excluded.raw_xml,
            retrieved_at=excluded.retrieved_at, format=excluded.format,
            source_url=excluded.source_url, license_url=excluded.license_url""",
            (raw, datetime.now(UTC).isoformat(), format_name, source_url, license_url),
        )


def _plain_description(value: str) -> str:
    parser = _PlainText()
    parser.feed(value)
    return "".join(parser.parts).strip()


def import_unesco_xml(payload: bytes) -> int:
    records = parse_unesco_xml(payload)
    _store_feed(payload, "xml", UNESCO_XML_URL, UNESCO_TERMS_URL)
    return len(records)


def _download() -> bytes:
    try:
        with httpx.Client(timeout=get_settings().heritage_timeout_seconds) as client:
            with client.stream(
                "GET",
                DATAHUB_URL,
                params={"select": "id_no,name_en,states_names,date_inscribed,short_description_en"},
            ) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("XML too large")
                return bytes(data)
    except Exception as exc:
        raise OfficialServiceError(
            "UNESCO DataHub에 연결하지 못했습니다. 잠시 후 다시 시도하세요. "
            "기존 자료 또는 공식 XML 파일 가져오기를 사용할 수 있습니다."
        ) from exc


def search_unesco(
    query: str = "",
    limit: int = 20,
    offset: int = 0,
    *,
    refresh: bool = False,
    include_description: bool = False,
) -> UnescoResult:
    with transaction() as connection:
        cached = connection.execute("SELECT * FROM unesco_feeds WHERE language='en'").fetchone()
    stale = False
    from_cache = bool(cached)
    source_url, license_url, source_format = UNESCO_XML_URL, UNESCO_TERMS_URL, "xml"
    if cached:
        source_url, license_url, source_format = (
            cached["source_url"],
            cached["license_url"],
            cached["format"],
        )
        retrieved_at = datetime.fromisoformat(cached["retrieved_at"])
        stale = datetime.now(UTC) - retrieved_at > timedelta(
            hours=get_settings().heritage_cache_hours
        )
        parser = parse_unesco_json if source_format == "json" else parse_unesco_xml
        records = parser(cached["raw_xml"].encode("utf-8"))
    if not cached or stale or refresh:
        try:
            payload = _download()
            records = parse_unesco_json(payload)
            _store_feed(payload, "json", DATAHUB_URL, DATAHUB_INFO_URL)
            source_url, license_url, source_format = DATAHUB_URL, DATAHUB_INFO_URL, "json"
            with transaction() as connection:
                row = connection.execute(
                    "SELECT retrieved_at FROM unesco_feeds WHERE language='en'"
                ).fetchone()
            retrieved_at = datetime.fromisoformat(row["retrieved_at"])
            stale, from_cache = False, False
        except OfficialServiceError:
            if not cached:
                raise
            stale = True
    matches = [
        record
        for record in records
        if _matches_query(record, query)
        or (include_description and normalize_search(query) in normalize_search(record.description))
    ]
    return UnescoResult(
        records=matches[offset : offset + limit],
        total=len(matches),
        retrieved_at=retrieved_at,
        cached=from_cache,
        stale=stale,
        feed_source_url=source_url,
        source_format=source_format,
        license_url=license_url,
    )
