from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from nicegui import Client
from nicegui.elements.button import Button
from nicegui.elements.input import Input
from nicegui.elements.toggle import Toggle

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.models import ComparisonScope
from culturebridge.domain.official_models import (
    OfficialDocument,
    OfficialHeritageItem,
    OfficialSearchResult,
)
from culturebridge.main import app
from culturebridge.services import agent_discovery_service as discovery
from culturebridge.services import dynamic_heritage_service as dynamic
from culturebridge.services.comparison_scope_service import candidate_in_scope
from culturebridge.services.dynamic_heritage_service import OfficialTarget
from culturebridge.services.navigation_service import home_context, with_return
from culturebridge.services.unesco_service import UnescoRecord, UnescoResult
from culturebridge.ui import pages


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "scope.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    state = {"foreign": True, "calls": []}
    records = {
        "200": UnescoRecord(
            id="200",
            name="Stone Pagoda",
            countries="China",
            inscription_year="2000",
            source_url="https://whc.unesco.org/en/list/200/",
            description="Built in 700. A Buddhist stone pagoda.",
        ),
        "201": UnescoRecord(
            id="201",
            name="Korean Stone Pagoda",
            countries="Republic of Korea",
            inscription_year="2000",
            source_url="https://whc.unesco.org/en/list/201/",
            description="Built in 700. A Buddhist stone pagoda.",
        ),
    }

    def document(kind, number, region, **kw):
        name = "다보탑" if number == "20" else "삼층석탑"
        return OfficialDocument(
            kind_code=kind,
            asset_number=number,
            region_code=region,
            name=name,
            content=f"{name}은 751년에 건립한 석탑이다. {name}은 불교와 법화경의 내용을 표현했다.",
            source_url="https://www.khs.go.kr/",
            retrieved_at=datetime.now(UTC),
        )

    def search_unesco(q, **kw):
        state["calls"].append(("unesco", q))
        rows = [records[q]] if q in records else list(records.values()) if state["foreign"] else []
        return UnescoResult(
            records=rows, total=len(rows), retrieved_at=datetime.now(UTC), cached=True, stale=False
        )

    def search_khs(q, **kw):
        state["calls"].append(("khs", q))
        return OfficialSearchResult(
            items=[
                OfficialHeritageItem(
                    kind_code="11", asset_number="21", region_code="37", name="삼층석탑"
                )
            ],
            total=1,
            page=kw.get("page", 1),
            page_size=10,
        )

    monkeypatch.setattr(dynamic, "get_official_document", document)
    monkeypatch.setattr(dynamic, "search_unesco", search_unesco)
    monkeypatch.setattr(discovery, "search_unesco", search_unesco)
    monkeypatch.setattr(discovery, "search_official_heritages", search_khs)
    return state


@pytest.mark.parametrize(
    "country,scope,expected",
    [
        ("대한민국", "domestic", True),
        ("Republic of Korea", "domestic", True),
        ("대한민국", "overseas", False),
        ("Republic of Korea", "overseas", False),
        ("Japan", "overseas", True),
        ("China", "domestic", False),
        ("Republic of Korea; Japan", "overseas", False),
        ("Republic of Korea; Japan", "domestic", False),
        ("", "overseas", False),
        ("unknown", "overseas", False),
    ],
)
def test_scope_is_korea_based_not_relative_to_selected_country(country, scope, expected):
    assert candidate_in_scope(country, ComparisonScope(scope)) is expected


def test_default_candidates_only_overseas(configured):
    _, candidates, trace, _ = discovery.discover_candidates(
        OfficialTarget(provider="khs", kind="11", number="20", region="37"), "compare"
    )
    assert [c.heritage.id for c in candidates] == ["unesco:200"]
    assert not any(provider == "khs" for provider, _ in configured["calls"])
    assert any("해외 문화유산과 비교" in t for t in trace)


def test_overseas_shortage_retries_then_holds_without_domestic_replacement(configured):
    configured["foreign"] = False
    _, candidates, trace, _ = discovery.discover_candidates(
        OfficialTarget(provider="khs", kind="11", number="20", region="37"), "compare"
    )
    assert not candidates and any("검색어 변경" in t for t in trace)
    assert not any(provider == "khs" for provider, _ in configured["calls"])


def test_domestic_is_explicit_and_only_uses_korean_candidates(configured):
    _, candidates, _, _ = discovery.discover_candidates(
        OfficialTarget(provider="khs", kind="11", number="20", region="37"),
        "compare",
        comparison_scope=ComparisonScope.DOMESTIC,
    )
    assert [c.heritage.id for c in candidates] == ["khs:11:21:37"]
    assert all(provider == "khs" for provider, _ in configured["calls"])


def test_scope_is_rechecked_against_detail_country(configured, monkeypatch):
    original = dynamic.search_unesco

    def detail(q, **kw):
        result = original(q, **kw)
        if q == "200":
            result.records = [
                result.records[0].model_copy(update={"countries": "Republic of Korea"})
            ]
        return result

    monkeypatch.setattr(dynamic, "search_unesco", detail)
    _, candidates, _, _ = discovery.discover_candidates(
        OfficialTarget(provider="khs", kind="11", number="20", region="37"), "compare"
    )
    assert not candidates


@pytest.mark.parametrize("scope,right", [("overseas", "unesco:200"), ("domestic", "khs:11:21:37")])
def test_autonomous_api_scope_persists_into_saved_comparison(configured, scope, right):
    with TestClient(app) as client:
        response = client.post(
            "/api/autonomous-explorations",
            json={
                "target": {"provider": "khs", "kind": "11", "number": "20", "region": "37"},
                "comparison_scope": scope,
            },
        )
        body = response.json()
        assert response.status_code == 200 and body["comparison_scope"] == scope
        assert body["comparison"]["right"]["id"] == right
        assert body["comparison"]["comparison_scope"] == scope
        assert len(body["quiz"]["items"]) == 5
        saved = client.get("/api/comparisons/" + body["comparison"]["saved_id"]).json()
        assert saved["comparison"]["comparison_scope"] == scope


def test_api_rejects_invalid_scope_and_implicit_domestic_pair(configured):
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/autonomous-explorations",
                json={
                    "target": {"provider": "unesco", "record_id": "200"},
                    "comparison_scope": "same_country",
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/explorations", json={"heritage_id": "horyuji", "comparison_id": "seokguram"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/comparisons", json={"left_id": "horyuji", "right_id": "seokguram"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/comparisons",
                json={
                    "left_id": "horyuji",
                    "right_id": "seokguram",
                    "comparison_scope": "domestic",
                },
            ).status_code
            == 200
        )
        domestic = client.get("/api/heritages/horyuji/related?comparison_scope=domestic").json()
        assert [c["heritage"]["id"] for c in domestic] == ["seokguram"]


def test_domestic_has_separate_entry_and_keeps_current_controls(configured, monkeypatch):
    destinations = []
    monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
    with TestClient(app) as client:
        response = client.get("/")
        page = next(
            c
            for c in reversed(list(Client.instances.values()))
            if any(
                isinstance(e, Input) and e._props.get("label") == "문화유산 검색"
                for e in c.elements.values()
            )
        )
        with page:
            next(
                e
                for e in page.elements.values()
                if isinstance(e, Input) and e._props.get("label") == "문화유산 검색"
            ).set_value("불국사")
            next(e for e in page.elements.values() if isinstance(e, Toggle)).set_value("advanced")
            button = next(
                e
                for e in page.elements.values()
                if isinstance(e, Button) and e.text == "국내 문화유산과 비교"
            )
            next(
                listener
                for listener in button._event_listeners.values()
                if listener.type == "click"
            ).handler(None)
        url = destinations[-1]
        parsed = urlsplit(url)
        assert parsed.path == "/domestic"
        assert parse_qs(parsed.query)["q"] == ["불국사"] and parse_qs(parsed.query)["level"] == [
            "advanced"
        ]
        domestic = client.get("/domestic?q=불국사&level=advanced")
    assert response.status_code == domestic.status_code == 200
    assert "한국의 유산을 추천해요" in domestic.text
    assert "국내 문화유산과 비교" in response.text
    assert "부가 기능" not in domestic.text
    assert "부가 기능" not in response.text
    assert "기본 학습" not in domestic.text
    assert "기본 학습" not in response.text


def test_domestic_context_stays_domestic_through_navigation():
    root = home_context("불국사", level="advanced", comparison_scope=ComparisonScope.DOMESTIC)
    url = with_return("/discover/khs/11:20:37?comparison_scope=domestic", root)
    returned = parse_qs(urlsplit(url).query)["return_to"][0]
    assert urlsplit(returned).path == "/domestic"
    assert parse_qs(urlsplit(returned).query)["comparison_scope"] == ["domestic"]
