from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.official_models import OfficialHeritageItem, OfficialSearchResult
from culturebridge.main import app
from culturebridge.services import home_search_service as service
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.unesco_service import (
    UnescoRecord,
    UnescoResult,
    _matches_query,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "home.db")
    initialize_database()
    monkeypatch.setattr(service, "get_unesco_suggestions", lambda **kwargs: [])


def korean_result(name="경주 불국사"):
    return OfficialSearchResult(
        items=[
            OfficialHeritageItem(
                kind_code="13", asset_number="0000000000001", region_code="37", name=name
            )
        ],
        total=1,
        page=1,
        page_size=10,
    )


def world_result(name="Taj Mahal", country="India", record_id="252"):
    return UnescoResult(
        records=[
            UnescoRecord(
                id=record_id,
                name=name,
                countries=country,
                inscription_year="1983",
                source_url=f"https://whc.unesco.org/en/list/{record_id}/",
            )
        ],
        total=1,
        retrieved_at=datetime.now(UTC),
        cached=True,
        stale=False,
    )


def test_unregistered_korean_heritage_can_be_discovered_without_fake_comparison(monkeypatch):
    monkeypatch.setattr(service, "search_official_heritages", lambda *args, **kw: korean_result())
    monkeypatch.setattr(
        service,
        "search_unesco",
        lambda *args, **kw: world_result(
            "Seokguram Grotto and Bulguksa Temple", "Republic of Korea", "736"
        ),
    )
    with TestClient(app) as client:
        result = client.get("/api/search", params={"q": "불국사"})
    assert result.status_code == 200
    data = result.json()
    assert data["comparable"] == [] and data["korean"]["total"] == data["world"]["total"] == 1
    assert data["korean"]["items"][0]["name"] == "경주 불국사"
    assert any(s.value == "경주 불국사" for s in service.get_home_suggestions("불국"))


def test_partial_provider_failure_preserves_other_results(monkeypatch):
    def fail(*args, **kwargs):
        raise OfficialServiceError("Failed")

    monkeypatch.setattr(service, "search_official_heritages", fail)
    monkeypatch.setattr(service, "search_unesco", lambda *args, **kw: world_result())
    result = service.search_home("타지마할")
    assert result.world.total == 1 and result.korean is None
    assert "국가유산청" in result.notices[0]


def test_foreign_country_does_not_query_korean_name_api(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Foreign countries must not be sent as Korean heritage names")

    monkeypatch.setattr(service, "search_official_heritages", fail)
    monkeypatch.setattr(service, "search_unesco", lambda *args, **kw: world_result())
    assert service.search_home("인도").world.records[0].countries == "India"


def test_korean_country_requests_general_korean_list(monkeypatch):
    calls = []

    def collect(query, **kwargs):
        calls.append((query, kwargs))
        return korean_result()

    monkeypatch.setattr(service, "search_official_heritages", collect)
    assert service.search_home("한국", "korea").korean.total == 1
    assert calls == [("", {"allow_empty": True, "page": 1})]


@pytest.mark.parametrize(
    "term,record",
    [
        ("타지마할", ("252", "Taj Mahal", "India")),
        ("만리장성", ("438", "The Great Wall", "China")),
        ("이탈리아", ("91", "Historic Centre of Rome", "Italy; Holy See")),
    ],
)
def test_expanded_korean_names_and_countries_match_real_unesco_records(term, record):
    item = UnescoRecord(
        id=record[0],
        name=record[1],
        countries=record[2],
        inscription_year="1983",
        source_url="https://whc.unesco.org/",
    )
    assert _matches_query(item, term)


def test_typing_uses_local_suggestions_and_works_before_first_feed(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Typing must not contact external providers")

    monkeypatch.setattr(service, "search_official_heritages", fail)
    monkeypatch.setattr(service, "search_unesco", fail)
    assert service.get_home_suggestions("불국사")[0].value == "불국사"
    assert service.get_home_suggestions("타지")[0].value == "타지마할"
    assert not any(s.provider == "world" for s in service.get_home_suggestions("", scope="korea"))


def test_home_input_change_updates_results_instead_of_retaining_all_cards():
    from nicegui import Client
    from nicegui.elements.input import Input

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        page = next(
            c
            for c in reversed(list(Client.instances.values()))
            if any(
                isinstance(e, Input) and e._props.get("label") == "문화유산 검색"
                for e in c.elements.values()
            )
        )
        query = next(
            e
            for e in page.elements.values()
            if isinstance(e, Input) and e._props.get("label") == "문화유산 검색"
        )
        with page:
            query.set_value("불국사")
        texts = [getattr(e, "text", "") for e in page.elements.values()]
        assert "석굴암" not in texts and "호류지 불교 건축물" not in texts
        assert any("공식 자료 검색으로" in text for text in texts if isinstance(text, str))
        assert any("불국사" in text for text in texts if isinstance(text, str))
        with page:
            query.set_value("석굴암")
        assert "석굴암" in [getattr(e, "text", "") for e in page.elements.values()]


def test_search_api_validates_scope_and_length():
    with TestClient(app) as client:
        assert client.get("/api/search", params={"q": ""}).status_code == 422
        assert client.get("/api/search", params={"q": "a" * 101}).status_code == 422
        assert (
            client.get("/api/search", params={"q": "불국사", "scope": "invalid"}).status_code == 422
        )
        assert (
            client.get("/api/search/suggestions", params={"q": "불국"}).json()[0]["value"]
            == "불국사"
        )


def test_pagination_reaches_both_providers(monkeypatch):
    calls = []

    def korean(query, **kwargs):
        calls.append(("korea", kwargs["page"]))
        return korean_result()

    def world(query, **kwargs):
        calls.append(("world", kwargs["offset"]))
        return world_result()

    monkeypatch.setattr(service, "search_official_heritages", korean)
    monkeypatch.setattr(service, "search_unesco", world)
    result = service.search_home("유산", page=2)
    assert result.page == 2 and sorted(calls) == [("korea", 2), ("world", 10)]
