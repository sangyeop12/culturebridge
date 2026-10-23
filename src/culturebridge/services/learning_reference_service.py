"""Extend learning discovery with registered world sources and explicit portal guidance.

No arbitrary URL fetching, new country registration, or unlicensed AI transmission.
"""

from culturebridge.services.display_service import display_country, display_name
from culturebridge.services.individual_source_service import (
    INDIVIDUALS,
    fetch_individual,
    search_individuals,
)
from culturebridge.services.unesco_service import search_unesco

HISTORY_REFERENCES = (
    ("한국사 자료 찾아보기 · 국사편찬위원회", "https://db.history.go.kr/"),
    ("문화유산 전문 자료 찾아보기 · 국립문화유산연구원", "https://portal.nrich.go.kr/"),
)


def world_learning_results(query):
    query = query.strip()
    if not query or len(query) > 80 or "://" in query:
        raise ValueError("검색할 유산 이름이나 국가를 알려주세요.")
    results = [
        {"id": hit.id, "name": f"{hit.korean} ({hit.name})", "region": hit.country, "city": ""}
        for hit in search_individuals(query)[:6]
    ]
    notices = []
    try:
        feed = search_unesco(query, limit=4)
        results.extend(
            {
                "id": "unesco:" + record.id,
                "name": display_name("unesco:" + record.id, record.name),
                "region": display_country(record.countries),
                "city": "",
                "reading_url": str(record.source_url),
                "metadata_only": True,
            }
            for record in feed.records[:4]
        )
        if feed.stale:
            notices.append("세계유산 목록이 최신인지 확인이 필요해요.")
    except Exception:
        notices.append("세계유산 목록 연결을 확인하지 못했어요. 개별 유산 결과는 유지해요.")
    return results[:10], " ".join(notices)


def individual_learning_record(identity):
    key = identity.removeprefix("official:")
    if not identity.startswith("official:") or key not in INDIVIDUALS:
        raise ValueError("검색 결과의 등록된 유산을 선택해 주세요.")
    record, source = INDIVIDUALS[key], fetch_individual(key)
    if source.status == "stale" or not source.content.strip():
        raise ValueError("최신 공식 원문을 확인하지 못했어요.")
    from culturebridge.services.extraction_service import _local_extraction, validate_extraction

    fields = [f for f in _local_extraction([source]) if validate_extraction(f, [source])]
    return {
        "id": identity,
        "name": record["korean"] + " (" + record["name"] + ")",
        "url": str(source.source_url),
        "reading_url": str(source.source_url),
        "comparison_url": "/discover/official/" + key,
        "excerpts": [
            {"concept": f.category, "quote": f.evidence_quote}
            for f in fields[:4]
            if len(f.evidence_quote) <= 700
        ],
    }
