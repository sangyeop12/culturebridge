import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import LearningConversation, LearningDecision, LearningTurn
from culturebridge.services import personalized_explanation_service as personal
from culturebridge.services.learning_agent_tools import planning_tools
from culturebridge.services.learning_conversation_service import (
    create_conversation,
    send_learning_turn,
)
from culturebridge.services.learning_preferences import LearningPreferences
from culturebridge.services.operation_service import clear_operation_cache, session_owner

QUOTE = "다보탑은 대표적인 석탑이며 높이는 10.29m이다."
IDENTITY = "khs:11:0000200000000:37"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "continuity.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    token = session_owner.set("continuity-learner")
    yield
    clear_operation_cache()
    session_owner.reset(token)


def ready_conversation():
    state = create_conversation()
    state.goal = "다보탑의 재료 이해하기"
    state.sources = [
        {
            "id": IDENTITY,
            "name": "다보탑",
            "url": "https://www.khs.go.kr/",
            "reading_url": "/official",
            "excerpts": [{"concept": "재료", "quote": QUOTE}],
        }
    ]
    state.plan_history = [{"source_id": IDENTITY, "concept": "재료", "action": "explain"}]
    with transaction() as connection:
        connection.execute(
            "UPDATE learning_conversations SET state_json=? WHERE id=?",
            (state.model_dump_json(), str(state.id)),
        )
    return state


@pytest.mark.parametrize(
    "text",
    [
        "좀 더 쉽게 설명해 줘",
        "조금 더 쉽게 설명하고 확인 질문도 해 주세요",
        "이어서 설명해 주세요",
        "조금 더 쉬운 말로 설명해 주세요",
        "제가 이해했는지 확인해 주세요",
    ],
)
def test_failed_planner_keeps_current_source_goal_and_no_assessment(isolated, monkeypatch, text):
    calls = []

    class RateLimitError(Exception):
        code = 429

    def unavailable(_):
        calls.append(True)
        raise RateLimitError()

    monkeypatch.setattr(learning, "_model_decision", unavailable)
    state = ready_conversation()
    result = send_learning_turn(state.id, LearningTurn(request_id=uuid4(), revision=0, text=text))
    assert result.goal == state.goal and result.sources == state.sources
    assert result.messages[-1].citations[0]["source_id"] == IDENTITY
    assert "돌" in result.messages[-1].text
    assert result.pending_request == text
    assert calls == [True]
    assert "요청 한도" in result.notice
    assert not result.concepts
    assert result.plan_history[-1]["planner"] == "limited_fallback"
    if "확인 질문" in text:
        assert result.checkpoint["source_id"] == IDENTITY


def test_pending_comparison_is_not_replaced_by_local_explanation(isolated, monkeypatch):
    state = ready_conversation()
    state.pending_request = "다보탑과 해외 탑을 비교하고 퀴즈를 준비해 주세요"
    with transaction() as connection:
        connection.execute(
            "UPDATE learning_conversations SET state_json=? WHERE id=?",
            (state.model_dump_json(), str(state.id)),
        )
    monkeypatch.setattr(learning, "_model_decision", lambda _: (_ for _ in ()).throw(ValueError()))
    result = send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=0, text="이어서 진행해 주세요")
    )
    assert result.pending_request == state.pending_request
    assert result.plan_history[-1]["action"] == "ask"
    assert "다음 활동" in result.messages[-1].text


def test_planning_schema_excludes_unready_tools_and_fabricated_ids():
    state = LearningConversation(id=uuid4(), revision=0)
    tools, constraints, schema = planning_tools(state)
    assert not {"discover", "compare", "read", "quiz", "review_quiz"} & tools.keys()
    with pytest.raises(ValidationError):
        schema(action="discover", source_id="국가지정문화유산 다보탑")
    state.search_results = [
        {"id": IDENTITY, "name": "다보탑"},
        {"id": "unesco:660", "metadata_only": True},
    ]
    tools, constraints, schema = planning_tools(state)
    assert "discover" in tools and "compare" not in tools
    assert constraints["individual_ids"] == [IDENTITY]
    assert schema(action="discover", source_id=IDENTITY).source_id == IDENTITY
    with pytest.raises(ValidationError):
        schema(action="read", source_id="unesco:660")


def test_material_rewrite_rejects_height_drift_before_second_ai_call(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    calls = []

    def generate(*args):
        calls.append(1)
        return personal.ExplanationDraft(
            sentences=[
                personal.SupportedSentence(
                    text="이 석탑의 높이는 10.29m예요.", evidence_quote=QUOTE
                )
            ]
        )

    monkeypatch.setattr(personal, "_generate", generate)
    text, metadata = personal.explain(
        "재료",
        QUOTE,
        LearningPreferences(),
        {"mode": "explain"},
        time.monotonic() + 30,
        learner_text="무엇으로 만들었나요?",
    )
    assert calls == [1]
    assert metadata["failure_kind"] == "learning_focus_mismatch"
    assert "돌" in text and "10.29" not in text


@pytest.mark.parametrize("action,status", [("search", "empty"), ("search_history", "ok")])
def test_search_outcome_guidance_overrides_vague_question(isolated, monkeypatch, action, status):
    state = create_conversation()
    row = {
        "id": "nikh:nh_01",
        "name": "훈민정음",
        "metadata_only": True,
        "catalogue": "history",
        "reading_url": "https://db.history.go.kr/",
    }
    choices = iter(
        [
            LearningDecision(action=action, query="검색어"),
            LearningDecision(action="ask", question="더 알려 주실 수 있나요?"),
        ]
    )
    monkeypatch.setattr(learning, "_model_decision", lambda _: next(choices))

    def retrieval(turn):
        turn["conversation"].search_results = [row] if status == "ok" else []
        return {"tool_status": "ok"}

    monkeypatch.setattr(learning, "_retrieval_tool", retrieval)
    result = send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=0, text="검색어")
    )
    message = result.messages[-1]
    if status == "empty":
        assert "찾지 못했어요" in message.text and "다른 이름" in message.text
        assert "존재하지 않" not in message.text
    else:
        assert "공식 사이트" in message.text and "요약한 것은 아니에요" in message.text
        assert message.suggestions[0]["url"] == row["reading_url"]
