"""Workspace entry, shared history ownership and legacy search continuity."""

import pytest
from fastapi.testclient import TestClient
from nicegui import Client
from nicegui.elements.textarea import Textarea

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.main import app
from culturebridge.services.navigation_service import search_return
from culturebridge.ui.navigation import section_for


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "workspace.db")
    initialize_database()


@pytest.mark.parametrize("route", ["/", "/learn"])
def test_entry_has_one_prompt_and_does_not_create_a_conversation(route):
    with TestClient(app) as client:
        assert client.get(route).status_code == 200
        page = next(reversed(list(Client.instances.values())))
        prompts = [e for e in page.elements.values() if isinstance(e, Textarea)]
        assert len(prompts) == 1
        assert prompts[0]._props["label"] == "어떤 이야기가 궁금한가요?"
        assert len([e for e in page.elements.values() if "cb-thread-list" in e._classes]) == 1
        assert not any(e._props.get("label") == "문화유산 검색" for e in page.elements.values())
        assert client.get("/api/learning/conversations").json() == []


def test_recent_threads_are_owned_and_available_across_workspace_pages():
    with TestClient(app) as owner:
        conversation = owner.post("/api/learning/conversations").json()
        identity = conversation["id"]
        for route in ("/", "/library", "/courses", "/learning-history"):
            response = owner.get(route)
            assert response.status_code == 200
            assert f"/learn?conversation_id={identity}" in response.text
    with TestClient(app) as other:
        assert identity not in other.get("/").text


def test_thread_delete_is_owner_scoped_and_removes_it_from_sidebar():
    with TestClient(app) as owner:
        identity = owner.post("/api/learning/conversations").json()["id"]
        assert f"/learn?conversation_id={identity}" in owner.get("/").text
        with TestClient(app) as other:
            assert other.delete(f"/api/learning/conversations/{identity}").status_code == 404
        assert owner.delete(f"/api/learning/conversations/{identity}").status_code == 204
        assert owner.get(f"/api/learning/conversations/{identity}").status_code == 404
        assert f"/learn?conversation_id={identity}" not in owner.get("/").text


def test_long_thread_list_is_paged_with_more_button():
    with TestClient(app) as client:
        identities = [client.post("/api/learning/conversations").json()["id"] for _ in range(23)]
        page = client.get("/").text
        assert page.count("cb-thread-row") >= 20
        assert "더보기" in page
        assert f"/learn?conversation_id={identities[0]}" not in page
        assert len(client.get("/api/learning/conversations").json()) == 23


def test_library_and_bookmarked_home_search_share_search_controls():
    with TestClient(app) as client:
        for route in ("/library", "/?q=석굴암&level=advanced"):
            response = client.get(route)
            assert response.status_code == 200
            page = next(reversed(list(Client.instances.values())))
            assert any(e._props.get("label") == "문화유산 검색" for e in page.elements.values())
            assert not any("cb-learning-start" in e._classes for e in page.elements.values())
        assert search_return("/library?q=석굴암&level=advanced").startswith("/library?")
        assert section_for("/history-search") == section_for("/library") == "heritage"
