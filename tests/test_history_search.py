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


def test_title_ranking_distinguishes_partial_from_unconfirmed_results(monkeypatch):
    rows = [
        {"key": "nh_001_01", "title": "문자화의 긴 도정"},
        {"key": "nh_001_02", "title": "언문자모의 보급"},
        {"key": "nh_001_03", "title": "세종의 훈민정음 창제"},
    ]
    monkeypatch.setattr(history, "_request", lambda _: rows)
    records, notice = history.search_history("세종대왕 한글 창제")
    assert [r["title_relevance"] for r in records] == ["all_terms", "some_terms", "unconfirmed"]
    assert records[0]["title_matched_terms"] == ["세종", "훈민정음", "창제"]
    assert "관련성을 확인하지 못했어요" in records[-1]["match_note"]
    assert "원문" in notice
    assert all(r["metadata_only"] and "excerpts" not in r for r in records)
    assert len(records) == 3  # Do not hide uncertain catalogue results.


@pytest.mark.parametrize(
    "query,title,terms,total",
    [
        ("임진왜란", "임진왜란의 경과", ["임진왜란"], 1),
        ("세종대왕의 한글", "세종과 훈민정음", ["세종", "훈민정음"], 2),
        ("한글 훈민정음", "훈민정음", ["훈민정음"], 1),
        ("무령왕릉", "조선의 궁궐", [], 1),
    ],
)
def test_title_matching_reports_observed_words_only(query, title, terms, total):
    assert history.title_matches(query, title) == (terms, total)
