import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningDecision, LearningTurn
from culturebridge.services import dictionary_service
from culturebridge.services import term_explanation_service as service
from culturebridge.services.learning_conversation_service import (
    create_conversation,
    send_learning_turn,
)


@pytest.fixture
def term_client(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", tmp_path / "term.db")
    monkeypatch.setattr(settings, "gemini_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", "test-only")
    initialize_database()
    monkeypatch.setattr(
        learning, "_model_decision", lambda _: LearningDecision(action="define", query="기단")
    )
    calls = []
    answer = {
        "understood": True,
        "explanation": "기단은 건물이나 탑의 아래에서 몸체를 받치는 부분이에요.",
        "example": "받침대처럼 위의 몸체를 받쳐 준다고 생각하면 돼요.",
    }

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            if isinstance(answer.get("error"), Exception):
                raise answer["error"]
            return SimpleNamespace(text=json.dumps(answer, ensure_ascii=False))

    monkeypatch.setattr(service.genai, "Client", Client)
    return calls, answer


def ask():
    conversation = create_conversation()
    return send_learning_turn(
        conversation.id, LearningTurn(request_id=uuid4(), revision=0, text="기단이 뭐야?")
    )


@pytest.mark.parametrize(
    "status",
    ["not_configured", "not_found", "invalid_key", "unavailable", "rate_limited"],
)
def test_missing_dictionary_uses_ai_without_inventing_official_evidence(
    status, term_client, monkeypatch
):
    calls, _ = term_client
    monkeypatch.setattr(
        dictionary_service,
        "lookup_term",
        lambda term: dictionary_service.DictionaryResult(query=term, status=status),
    )
    result = ask()
    message = result.messages[-1]
    assert len(calls) == 1 and json.loads(calls[0]["contents"]) == {"term": "기단"}
    assert "몸체를 받치는 부분" in message.text and "공식 사전 뜻풀이는 아니에요" in message.text
    assert message.kind == "dictionary" and message.citations == []
    assert message.teaching["method"] == "gemini_term_help"
    assert not result.pending_request and not result.concepts and not result.sources
    assert result.tool_observations[-1]["summary"]["dictionary_status"] == status


def test_official_meaning_does_not_call_ai(term_client, monkeypatch):
    calls, _ = term_client
    monkeypatch.setattr(
        dictionary_service,
        "lookup_term",
        lambda term: dictionary_service.DictionaryResult(
            query=term,
            status="ok",
            meanings=[
                dictionary_service.DictionaryMeaning(
                    word=term,
                    entry_id="1",
                    definition="검사용 공식 뜻풀이.",
                    source_url="https://stdict.korean.go.kr/search/searchView.do?word_no=1",
                )
            ],
        ),
    )
    result = ask()
    assert not calls and "검사용 공식 뜻풀이." in result.messages[-1].text
    assert result.messages[-1].citations[0]["source_id"] == "stdict:1"


def test_unknown_ai_term_asks_for_context(term_client):
    calls, answer = term_client
    answer.update(understood=False, explanation="", example="")
    result = ask()
    assert len(calls) == 1 and "단어가 나온 문장" in result.messages[-1].text
    assert not result.messages[-1].citations and not result.concepts


class RateLimit(Exception):
    code = 429


def test_ai_term_quota_stops_without_retry(term_client):
    calls, answer = term_client
    answer["error"] = RateLimit("private provider details")
    result = ask()
    assert len(calls) == 1 and "사용량 한도" in result.messages[-1].text
    assert "private provider" not in result.messages[-1].text
    assert result.pending_request == "기단이 뭐야?"


def test_planner_quota_prevents_another_ai_call(term_client, monkeypatch):
    calls, _ = term_client

    def limited(_):
        raise RateLimit("private provider details")

    monkeypatch.setattr(learning, "_model_decision", limited)
    result = ask()
    assert not calls and "사용량 한도" in result.messages[-1].text


def test_successful_term_help_removes_stale_planner_failure_notice(term_client, monkeypatch):
    def planner_failure(_):
        raise ValueError("bad planner output")

    monkeypatch.setattr(learning, "_model_decision", planner_failure)
    result = ask()
    assert "몸체를 받치는 부분" in result.messages[-1].text
    assert "AI 연결이 복구되면" not in result.messages[-1].text
    assert not result.notice and not result.pending_request
    assert result.plan_history[-1]["planner"] == "limited_fallback"
    assert result.plan_history[-1]["explanation_method"] == "gemini_term_help"


def test_offline_mode_and_expired_deadline_never_call_ai(term_client, monkeypatch):
    calls, _ = term_client
    assert service.explain_term("기단", time.monotonic() - 1)["status"] == "unavailable"
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    result = ask()
    assert not calls and "사전 자동 조회" in result.messages[-1].text


def test_ai_term_transport_failure_keeps_friendly_notice(term_client):
    calls, answer = term_client
    answer["error"] = RuntimeError("private provider details")
    result = ask()
    assert len(calls) == 1 and "잠시 연결하지 못했어요" in result.messages[-1].text
    assert "private provider" not in result.messages[-1].text
