from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from nicegui import Client

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.official_models import OfficialDocument
from culturebridge.main import app
from culturebridge.ui import pages


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "kiosk-navigation.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()


@pytest.mark.parametrize(
    "path",
    [
        "/explore/seokguram?mode=kiosk",
        "/compare/seokguram/horyuji?mode=kiosk",
    ],
)
def test_official_links_keep_kiosk_context(isolated, path):
    with TestClient(app) as client:
        assert client.get(path).status_code == 200
        page = next(reversed(list(Client.instances.values())))
        links = [e._props["href"] for e in page.elements.values() if "href" in e._props]
        official = [href for href in links if href.startswith(("/discover/", "/official/"))]
        assert official
        assert all("mode=kiosk" in href for href in official)


@pytest.mark.parametrize("reset", ["manual", "timeout"])
def test_reset_announces_new_experience(isolated, reset):
    with TestClient(app) as client:
        assert client.get(f"/kiosk?reset={reset}").status_code == 200
        page = next(reversed(list(Client.instances.values())))
        assert any(e._props.get("role") == "status" for e in page.elements.values())
        assert any(
            e._props.get("role") == "heading"
            and e._props.get("aria-level") == "1"
            and getattr(e, "text", "") == "문화유산 비교 체험"
            for e in page.elements.values()
        )


def test_official_detail_keeps_kiosk_controls(isolated, monkeypatch):
    document = OfficialDocument(
        kind_code="11",
        asset_number="20",
        region_code="37",
        name="다보탑",
        content="다보탑은 751년에 건립된 석탑이다.",
        source_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
    )
    monkeypatch.setattr(pages, "get_official_document", lambda *a: document)
    with TestClient(app) as client:
        response = client.get("/official/11/20/37?mode=kiosk")
        assert response.status_code == 200
        assert "박물관 터치 체험" in response.text
        assert "주요 메뉴" not in response.text
        page = next(reversed(list(Client.instances.values())))
        destinations = []
        monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
        button = next(
            e
            for e in page.elements.values()
            if getattr(e, "text", "") == "함께 살펴볼 문화유산을 찾아요"
        )
        with page:
            next(e for e in button._event_listeners.values() if e.type == "click").handler(None)
        assert "mode=kiosk" in destinations[-1]


def test_discovery_keeps_kiosk_header_without_running_remote_work(isolated, monkeypatch):
    monkeypatch.setattr(pages, "run_autonomous", lambda *a: pytest.fail("Not connected yet"))
    with TestClient(app) as client:
        response = client.get("/discover/khs/11:20:37?mode=kiosk")
        assert response.status_code == 200
        assert "박물관 터치 체험" in response.text
        assert "주요 메뉴" not in response.text
        page = next(reversed(list(Client.instances.values())))
        links = [e._props["href"] for e in page.elements.values() if "href" in e._props]
        assert all("mode=kiosk" in href for href in links if href.startswith("/discover/"))
