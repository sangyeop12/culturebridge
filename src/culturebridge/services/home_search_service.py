"""Federated discovery. Official search hits are not automatically comparable items."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, Field

from culturebridge.database import transaction
from culturebridge.domain.models import HeritageSummary
from culturebridge.domain.official_models import OfficialSearchResult
from culturebridge.services.catalog_service import list_heritages
from culturebridge.services.individual_source_service import (
    INDIVIDUALS,
    IndividualHit,
    search_individuals,
)
from culturebridge.services.official_service import OfficialServiceError, search_official_heritages
from culturebridge.services.unesco_service import (
    COUNTRY_ALIASES,
    HERITAGE_ALIASES,
    UnescoResult,
    get_unesco_suggestions,
    normalize_search,
    search_unesco,
)

SearchScope = Literal["all", "korea", "world"]


class HomeSearchResult(BaseModel):
    query: str
    scope: SearchScope
    page: int = 1
    comparable: list[HeritageSummary]
    korean: OfficialSearchResult | None = None
    world: UnescoResult | None = None
    notices: list[str] = Field(default_factory=list)
    individual: list[IndividualHit] = Field(default_factory=list)


class HomeSuggestion(BaseModel):
    value: str
    label: str
    provider: Literal["local", "korea", "world"]


def search_home(query: str, scope: SearchScope = "all", page: int = 1) -> HomeSearchResult:
    query = query.strip()
    if (
        not 1 <= len(query) <= 100
        or scope not in {"all", "korea", "world"}
        or not 1 <= page <= 10000
    ):
        raise ValueError("검색어와 검색 범위를 확인해 주세요.")
    local = list_heritages(query)
    if scope == "korea":
        local = [item for item in local if item.country == "대한민국"]
    if scope == "world":
        local = [item for item in local if item.country != "대한민국"]
    result = HomeSearchResult(query=query, scope=scope, page=page, comparable=local)
    if scope != "korea" and page == 1:
        result.individual = search_individuals(query)
    country = COUNTRY_ALIASES.get(query)
    korean_country = country == "Republic of Korea"
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = {}
        if scope != "world" and (country is None or korean_country):
            jobs["korean"] = executor.submit(
                search_official_heritages,
                "" if korean_country else query,
                page=page,
                allow_empty=korean_country,
            )
        if scope != "korea":
            jobs["world"] = executor.submit(search_unesco, query, limit=10, offset=(page - 1) * 10)
        for provider, job in jobs.items():
            try:
                setattr(result, provider, job.result())
            except (OfficialServiceError, sqlite3.Error):
                name = "국가유산청" if provider == "korean" else "UNESCO"
                result.notices.append(
                    f"{name} 검색 연결 실패입니다. 다른 결과는 유지하며 재시도할 수 있습니다."
                )
    if result.korean:
        try:
            with transaction() as connection:
                connection.executemany(
                    """INSERT INTO official_search_terms(id,name) VALUES(?,?)
                    ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,updated_at=CURRENT_TIMESTAMP""",
                    [(item.record_id, item.name) for item in result.korean.items],
                )
        except sqlite3.Error:
            result.notices.append(
                "자동완성용 공식 이름 캐시를 저장하지 못했습니다. 검색 결과는 표시합니다."
            )
    return result


def get_home_suggestions(query: str = "", limit: int = 8, scope: SearchScope = "all"):
    """Local cache only; no provider or LLM call while typing."""
    options = []
    for item in list_heritages():
        if scope == "korea" and item.country != "대한민국":
            continue
        if scope == "world" and item.country == "대한민국":
            continue
        options.append(
            HomeSuggestion(value=item.name, label=item.name + " · 비교 학습 지원", provider="local")
        )
    if scope != "world":
        options.extend(
            HomeSuggestion(value=name, label=name + " · 한국 공식 자료 검색어", provider="korea")
            for name in ("불국사", "경복궁", "창덕궁", "첨성대", "종묘", "수원 화성", "해인사")
        )
        try:
            with transaction() as connection:
                rows = connection.execute(
                    "SELECT name FROM official_search_terms ORDER BY updated_at DESC,id LIMIT 2000"
                ).fetchall()
                documents = connection.execute(
                    "SELECT document_json FROM official_documents LIMIT 1000"
                ).fetchall()
            import json

            names = [row["name"] for row in rows] + [
                json.loads(row["document_json"])["name"] for row in documents
            ]
            options.extend(
                HomeSuggestion(value=name, label=name + " · 국가유산청", provider="korea")
                for name in names
            )
        except (sqlite3.Error, ValueError, KeyError):
            pass
    if scope != "korea":
        options.extend(
            HomeSuggestion(value=alias, label=alias + " · " + record["korean"], provider="world")
            for record in INDIVIDUALS.values()
            for alias in record.get("aliases", ())
        )
        options.extend(
            HomeSuggestion(
                value=item.korean, label=item.korean + " · 개별 공식 자료", provider="world"
            )
            for item in search_individuals()
        )
        options.extend(
            HomeSuggestion(value=alias, label=alias + " · UNESCO 검색어", provider="world")
            for aliases in HERITAGE_ALIASES.values()
            for alias in aliases
        )
        options.extend(
            HomeSuggestion(value=alias, label=alias + " · 국가명", provider="world")
            for alias in COUNTRY_ALIASES
        )
        try:
            options.extend(
                HomeSuggestion(value=s.value, label=s.label + " · UNESCO", provider="world")
                for s in get_unesco_suggestions(limit=2000)
            )
        except (sqlite3.Error, OfficialServiceError):
            pass
    term = normalize_search(query)
    selected = [option for option in options if term in normalize_search(option.value)]
    selected.sort(
        key=lambda option: (
            normalize_search(option.value) != term,
            not normalize_search(option.value).startswith(term),
            len(normalize_search(option.value)),
        )
    )
    unique = {}
    for option in selected:
        unique.setdefault(normalize_search(option.value), option)
    return list(unique.values())[:limit]
