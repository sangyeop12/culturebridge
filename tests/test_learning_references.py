import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningConversation, LearningDecision, LearningTurn
from culturebridge.services import learning_reference_service as references


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "references.db")
    initialize_database()


def state(action, **kwargs):
    return {
        "conversation": LearningConversation(id=uuid4(), revision=0),
        "request": LearningTurn(request_id=uuid4(), revision=0, text="세계유산이 궁금해요"),
        "decision": LearningDecision(action=action, **kwargs),
        "steps": 1,
        "seen": [],
        "deadline": time.monotonic() + 45,
    }


def test_world_search_keeps_individual_results_on_feed_failure(monkeypatch):
    hit = SimpleNamespace(
        id="official:dayanta", korean="대안탑", name="Giant Wild Goose Pagoda", country="China"
    )
    monkeypatch.setattr(references, "search_individuals", lambda _: [hit])
    monkeypatch.setattr(
        references, "search_unesco", lambda *a, **k: (_ for _ in ()).throw(ValueError())
    )
    results, notice = references.world_learning_results("대안탑")
    assert results[0]["id"] == "official:dayanta"
    assert "유지" in notice


def test_world_search_marks_feed_as_metadata_not_ai_evidence(monkeypatch):
    monkeypatch.setattr(references, "search_individuals", lambda _: [])
    record = SimpleNamespace(
        id="660",
        name="Horyu-ji",
        countries="Japan",
        source_url="https://whc.unesco.org/en/list/660/",
    )
    monkeypatch.setattr(
        references, "search_unesco", lambda *a, **k: SimpleNamespace(records=[record], stale=False)
    )
    results, _ = references.world_learning_results("호류지")
    assert results[0]["metadata_only"] is True
    assert "description" not in results[0]
    value = state("read", source_id="unesco:660")
    value["conversation"].search_results = results
    result = learning.tool(value)
    assert "전송하지" in result["notice"]
    assert not value["conversation"].sources


@pytest.mark.parametrize("query", ["", "https://evil.invalid/", "x" * 81])
def test_reference_queries_cannot_be_urls_or_unbounded(query):
    with pytest.raises(ValueError):
        references.world_learning_results(query)


def test_new_search_action_uses_existing_bounded_tool_loop(monkeypatch):
    monkeypatch.setattr(
        references,
        "world_learning_results",
        lambda _: ([{"id": "official:dayanta", "name": "대안탑"}], ""),
    )
    value = state("search_world", query="대안탑")
    assert learning.route(value) == "tool"
    result = learning.tool(value)
    assert result["steps"] == 2
    from culturebridge.services.learning_agent_tools import action_key

    assert result["seen"] == [action_key(value["decision"])]
    assert value["conversation"].search_results[0]["name"] == "대안탑"
    value.update(result)
    assert learning.route(value) == "plan"


def test_reading_only_registered_result_never_uses_model_url(monkeypatch):
    with pytest.raises(ValueError):
        references.individual_learning_record("official:not-registered")
    value = state("read", source_id="official:dayanta")
    value["conversation"].search_results = [{"id": "official:dayanta", "name": "대안탑"}]
    monkeypatch.setattr(
        references,
        "individual_learning_record",
        lambda identity: {"id": identity, "name": "대안탑", "excerpts": []},
    )
    learning.tool(value)
    assert value["conversation"].sources[0]["id"] == "official:dayanta"


def test_general_history_guidance_never_claims_a_retrieved_answer():
    value = state("references")
    result = learning.respond(value)["conversation"]
    message = result.messages[-1]
    assert "아직 원문을 수집하거나 답을 확인한 것은 아니에요" in message.text
    assert not message.citations
    assert {s["url"] for s in message.suggestions} == {
        "/history-search",
        "https://db.history.go.kr/",
        "https://portal.nrich.go.kr/",
    }
