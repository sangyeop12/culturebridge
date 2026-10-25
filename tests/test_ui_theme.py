import pytest
from fastapi.testclient import TestClient
from nicegui import Client
from nicegui.elements.button import Button
from nicegui.elements.input import Input

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.main import app
from culturebridge.ui.theme import THEME_HEAD


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "theme.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/domestic",
        "/official",
        "/unesco",
        "/comparisons",
        "/explore/seokguram",
        "/compare/seokguram/horyuji",
        "/quiz/seokguram/horyuji",
        "/research/seokguram/horyuji",
    ],
)
def test_learning_screens_share_theme_and_navigation(isolated, path):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert "--cb-paper: #F7F3E9" in response.text
    assert "cb-header-inner" in response.text
    assert "주요 메뉴" in response.text
    assert "CultureBridge 처음으로" in response.text


def test_search_action_precedes_results_and_all_controls_are_preserved(isolated):
    with TestClient(app) as client:
        response = client.get("/?q=불국사&level=advanced&goal=religion&amount=deep")
        page = next(
            c
            for c in reversed(list(Client.instances.values()))
            if any(
                isinstance(e, Input) and e._props.get("label") == "문화유산 검색"
                for e in c.elements.values()
            )
        )
        button = next(
            e
            for e in page.elements.values()
            if isinstance(e, Button) and e.text == "공식 자료 통합 검색"
        )
        parent = button.parent_slot.parent
        assert "cb-search-submit" in parent._classes
        assert parent.parent_slot.children.index(parent) < next(
            i for i, e in enumerate(parent.parent_slot.children) if e._props.get("role") == "status"
        )
        assert (
            next(
                e
                for e in page.elements.values()
                if isinstance(e, Input) and e._props.get("label") == "문화유산 검색"
            ).value
            == "불국사"
        )
    for label in ["학습 수준", "학습 목표", "학습 분량", "세부 목표 (선택)", "검색 범위"]:
        assert label in response.text


def test_theme_keeps_accessibility_and_kiosk_touch_targets():
    assert ":focus-visible" in THEME_HEAD
    assert "prefers-reduced-motion: reduce" in THEME_HEAD
    assert "@media (max-width: 720px)" in THEME_HEAD
    assert ".cb-kiosk .q-radio, .cb-kiosk .q-btn { min-height: 72px; }" in THEME_HEAD
    assert ".cb-shell.cb-kiosk .q-btn-toggle>.q-btn {min-height:72px}" in THEME_HEAD
    assert "@import" not in THEME_HEAD  # No external font/network dependency.
