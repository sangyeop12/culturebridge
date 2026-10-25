from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningConversation, LearningDecision
from culturebridge.main import app
from culturebridge.services import history_search_service as history


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "history.db")
    monkeypatch.setattr(get_settings(), "maintenance_enabled", False)
    initialize_database()


def test_catalogue_accepts_only_observed_fixed_collection_identifiers():
    parser = history.CatalogueParser()
    parser.feed("""<div class="list-item"><a href="https://evil.invalid/"
      onclick="fnGoItemLevel('nh', 'nh_024_0070_0020', '0'); return false;">세종 <em>도량형</em></a>
      <a onclick="fnGoItemLevel('nh', 'https://evil.invalid', '1'); return false;">bad</a>
      <a onclick="alert('execute')">bad</a></div>""")
    assert parser.items == [{"key": "nh_024_0070_0020", "title": "세종 도량형"}]


@pytest.mark.parametrize("query", ["", "x" * 81, "https://evil.invalid", "세종|*", "<script>"])
def test_query_is_bounded_plain_search(query):
    with pytest.raises(ValueError):
        history.search_history(query)


def test_title_search_then_one_bounded_full_text_fallback(monkeypatch):
    calls = []

    def request(params):
        calls.append(dict(params))
        return [] if "titleWord" in params else [{"key": "nh_024_0070", "title": "조선"}]

    monkeypatch.setattr(history, "_request", request)
    records, notice = history.search_history("세종")
    assert len(calls) == 2 and calls[0]["titleWord"] == "세종"
    assert records[0]["metadata_only"] and records[0]["catalogue"] == "history"
    assert records[0]["reading_url"].startswith("https://db.history.go.kr/diachronic/level.do?")
    assert "본문" in notice and "excerpts" not in records[0]


def test_remote_failure_never_becomes_empty_success(monkeypatch):
    monkeypatch.setattr(
        history, "_request", lambda _: (_ for _ in ()).throw(RuntimeError("secret"))
    )
    with pytest.raises(ValueError, match="연결하지 못했어요") as exc:
        history.search_history("임진왜란")
    assert "secret" not in str(exc.value)


def test_history_search_remains_in_bounded_agent_loop(monkeypatch):
    monkeypatch.setattr(history, "search_history", lambda _: ([{"id": "nikh:nh_01_02"}], "확인"))
    state = {
        "conversation": LearningConversation(id=uuid4(), revision=0),
        "decision": LearningDecision(action="search_history", query="세종"),
        "steps": 0,
        "seen": [],
    }
    result = learning.tool(state)
    assert result["steps"] == 1 and state["conversation"].search_results
    assert not state["conversation"].sources
    state["decision"] = LearningDecision(action="read", source_id="nikh:nh_01_02")
    state["conversation"].search_results[0]["metadata_only"] = True
    assert "전송하지" in learning.tool(state)["notice"]
    assert not state["conversation"].sources


def test_history_page_has_accessible_search_and_no_request_on_render(monkeypatch):
    def forbidden(*args):
        raise AssertionError("page render must not search")

    monkeypatch.setattr(history, "search_history", forbidden)
    with TestClient(app) as client:
        response = client.get("/history-search")
        assert response.status_code == 200
        assert "인물·사건 이름" in response.text
        assert "aria-live=polite" in response.text or "aria-live" in response.text
        assert "AI 설명을 만들지는" in response.text


def test_payload_format_and_size_are_bounded(monkeypatch):
    class Response:
        headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_bytes(self):
            yield b"x" * 1_500_001

    class Client(Response):
        def __init__(self, **kwargs):
            pass

        def stream(self, *args, **kwargs):
            assert args[1] == history.ORIGIN + history.SEARCH_PATH
            return Response()

    monkeypatch.setattr(history.httpx, "Client", Client)
    with pytest.raises(ValueError, match="too_large"):
        history._request({})
