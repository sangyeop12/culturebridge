import asyncio
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
from culturebridge.domain.models import LearningLevel
from culturebridge.domain.official_models import OfficialDocument
from culturebridge.main import app
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.home_search_service import HomeSearchResult
from culturebridge.services.navigation_service import (
    home_context,
    search_level,
    search_return,
    with_return,
)
from culturebridge.ui import pages


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "navigation.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/",
        "//evil.example/",
        "/\\evil.example/",
        "javascript:alert(1)",
        "/%2f%2fevil.example/",
        "/?q=%0aevil",
        "/unknown",
        "/../",
        "/?return_to=https://evil.example/",
    ],
)
def test_return_destination_is_local_and_non_recursive(value):
    target = search_return(value, "/official")
    assert not urlsplit(target).scheme and not urlsplit(target).netloc
    assert target.split("?", 1)[0] in {"/", "/official"}
    assert "return_to" not in parse_qs(urlsplit(target).query)


def test_context_survives_multiple_steps_without_nested_return_chain():
    root = home_context("불국사", "korea", 3, "advanced", "religion", "불교 공간", "deep")
    for path in [
        "/discover/khs/11:20:37",
        "/research/khs:11:20:37/unesco:660",
        "/compare/khs:11:20:37/unesco:660",
        "/quiz/khs:11:20:37/unesco:660",
    ]:
        url = with_return(path, root)
        restored = parse_qs(urlsplit(url).query)["return_to"][0]
        assert restored == root
        params = parse_qs(urlsplit(restored).query)
        assert params["q"] == ["불국사"] and params["page"] == ["3"]
        assert params["goal_text"] == ["불교 공간"] and params["level"] == ["advanced"]


def test_return_parameters_are_bounded_and_levels_updated():
    root = search_return("/?q=" + "가" * 150 + "&page=-1&level=expert&auto=bad&scope=unknown")
    params = parse_qs(urlsplit(root).query)
    assert len(params["q"][0]) == 100 and "page" not in params and "auto" not in params
    assert parse_qs(urlsplit(search_level(root, "advanced")).query)["level"] == ["advanced"]


def last_page(button_text=None, input_label=None):
    return next(
        c
        for c in reversed(list(Client.instances.values()))
        if any(
            (isinstance(e, Button) and e.text == button_text)
            if button_text
            else (isinstance(e, Input) and e._props.get("label") == input_label)
            for e in c.elements.values()
        )
    )


def click(page, text):
    button = next(e for e in page.elements.values() if isinstance(e, Button) and e.text == text)
    with page:
        next(
            listener for listener in button._event_listeners.values() if listener.type == "click"
        ).handler(None)


def test_home_restores_learning_and_search_controls_without_remote_work(isolated, monkeypatch):
    monkeypatch.setattr(
        pages, "search_home", lambda *a: pytest.fail("Must await client connection")
    )
    root = home_context("불국사", "korea", 3, "advanced", "religion", "불교 공간", "deep")
    with TestClient(app) as client:
        response = client.get(root)
        page = last_page(input_label="문화유산 검색")
        inputs = {
            e._props.get("label"): e.value for e in page.elements.values() if isinstance(e, Input)
        }
        values = [getattr(e, "value", None) for e in page.elements.values()]
        assert inputs["문화유산 검색"] == "불국사" and inputs["세부 목표 (선택)"] == "불교 공간"
        assert (
            "advanced" in values and "religion" in values and "korea" in values and "deep" in values
        )
    assert response.status_code == 200


def test_official_back_button_and_level_switch_preserve_search(isolated, monkeypatch):
    doc = OfficialDocument(
        kind_code="11",
        asset_number="20",
        region_code="37",
        name="다보탑",
        content="다보탑은 751년에 건립된 석탑이다.",
        source_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
    )
    monkeypatch.setattr(pages, "get_official_document", lambda *a: doc)
    destinations = []
    monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
    root = home_context("불국사", "korea", 2, "beginner")
    with TestClient(app) as client:
        response = client.get(with_return("/official/11/20/37?level=beginner", root))
        page = last_page("← 검색 결과로")
        click(page, "← 검색 결과로")
        assert destinations[-1] == root
        toggle = next(e for e in page.elements.values() if isinstance(e, Toggle))
        with page:
            toggle.set_value("advanced")
        changed = parse_qs(urlsplit(destinations[-1]).query)
        assert changed["level"] == ["advanced"]
        assert parse_qs(urlsplit(changed["return_to"][0]).query)["level"] == ["advanced"]
    assert response.status_code == 200


def test_basic_quiz_back_uses_same_saved_comparison_and_level(isolated, monkeypatch):
    saved = create_saved_comparison("seokguram", "horyuji", LearningLevel.ADVANCED)
    root = home_context("석굴암", level="advanced")
    destinations = []
    monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
    with TestClient(app) as client:
        client.get(with_return(f"/compare/seokguram/horyuji?saved_id={saved.saved_id}", root))
        page = last_page("학습 확인 퀴즈")
        click(page, "학습 확인 퀴즈")
        quiz_url = destinations[-1]
        assert parse_qs(urlsplit(quiz_url).query)["back_saved_id"] == [saved.saved_id]
        response = client.get(quiz_url)
        page = last_page("← 비교 화면으로")
        click(page, "← 비교 화면으로")
        query = parse_qs(urlsplit(destinations[-1]).query)
        assert query["saved_id"] == [saved.saved_id] and query["level"] == ["advanced"]
        assert query["return_to"] == [root]
    assert response.status_code == 200


def test_direct_detail_has_explicit_search_fallback(isolated, monkeypatch):
    doc = OfficialDocument(
        kind_code="11",
        asset_number="20",
        region_code="37",
        name="다보탑",
        content="다보탑은 석탑이다.",
        source_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
    )
    monkeypatch.setattr(pages, "get_official_document", lambda *a: doc)
    destinations = []
    monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
    with TestClient(app) as client:
        client.get("/official/11/20/37?level=advanced&return_to=https://evil.example/")
        page = last_page("← 검색 결과로")
        click(page, "← 검색 결과로")
    parsed = urlsplit(destinations[-1])
    assert parsed.path == "/official"
    assert parse_qs(parsed.query)["q"] == ["다보탑"]
    assert parse_qs(parsed.query)["level"] == ["advanced"]


def test_returned_home_reloads_the_same_search_page_only_after_connection(isolated, monkeypatch):
    scheduled, calls = [], []
    monkeypatch.setattr(pages.ui, "timer", lambda delay, callback, **kw: scheduled.append(callback))

    async def connected(self, *a, **kw):
        calls.append("connected")

    def search(query, scope, page):
        calls.append((query, scope, page))
        return HomeSearchResult(query=query, scope=scope, page=page, comparable=[])

    monkeypatch.setattr(Client, "connected", connected)
    monkeypatch.setattr(pages, "search_home", search)
    with TestClient(app) as client:
        client.get(home_context("불국사", "korea", 3, "advanced"))
        page = last_page(input_label="문화유산 검색")
        assert not calls and len(scheduled) == 1
        with page:
            asyncio.run(scheduled[0]())
        assert calls == ["connected", ("불국사", "korea", 3)]


def test_kiosk_quiz_return_preserves_mode_and_rejects_another_pairs_snapshot(isolated, monkeypatch):
    other = create_saved_comparison("seokguram", "dayanta", LearningLevel.BEGINNER)
    destinations = []
    monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
    with TestClient(app) as client:
        response = client.get(
            f"/quiz/seokguram/horyuji?level=intermediate&mode=kiosk&back_saved_id={other.saved_id}"
        )
        page = last_page("← 비교 화면으로")
        click(page, "← 비교 화면으로")
    query = parse_qs(urlsplit(destinations[-1]).query)
    assert response.status_code == 200 and query["mode"] == ["kiosk"]
    assert query["level"] == ["intermediate"] and "saved_id" not in query
