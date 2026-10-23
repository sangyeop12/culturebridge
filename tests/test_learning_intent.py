from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import LearningDecision, LearningTurn
from culturebridge.main import app
from culturebridge.services.data_retention_service import delete_records
from culturebridge.services.learning_conversation_service import (
    ConversationConflictError,
    create_conversation,
    send_learning_turn,
)
from culturebridge.services.learning_intent_service import (
    LearningIntent,
    get_learning_intent,
    save_learning_intent,
)
from culturebridge.services.operation_service import session_owner


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "intent.db")
    initialize_database()
    marker = session_owner.set("intent-a")
    yield
    session_owner.reset(marker)


def send(state, text="역사 공부를 시작하고 싶어요", **kwargs):
    return send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=state.revision, text=text, **kwargs)
    )


def test_default_is_optional_and_normalizes_only_explicit_values(isolated):
    assert get_learning_intent() == LearningIntent()
    result = save_learning_intent(
        LearningIntent(interests=[" 궁궐 ", "궁궐", "석탑"], goal=" 구조 비교 ")
    )
    assert result.revision == 1 and result.interests == ["궁궐", "석탑"]
    assert result.goal == "구조 비교" and result.planning_context() == {}


def test_separate_sessions_and_revision_conflict(isolated):
    save_learning_intent(LearningIntent(interests=["궁궐"]))
    with pytest.raises(ConversationConflictError):
        save_learning_intent(LearningIntent(goal="stale edit"))
    marker = session_owner.set("intent-b")
    assert get_learning_intent().revision == 0
    save_learning_intent(LearningIntent(interests=["고분"]))
    session_owner.reset(marker)
    assert get_learning_intent().interests == ["궁궐"]


@pytest.mark.parametrize(
    "payload",
    [
        {"interests": ["x" * 41]},
        {"interests": [" "]},
        {"interests": ["x"] * 9},
        {"goal": "x" * 301},
        {"experience": "x" * 301},
        {"revision": -1},
        {"assessment": "mastered"},
    ],
)
def test_invalid_or_assessment_fields_rejected(payload):
    with pytest.raises(ValidationError):
        LearningIntent(**payload)


def test_intent_reaches_planner_but_never_becomes_understanding(isolated, monkeypatch):
    captured = []
    saved = save_learning_intent(
        LearningIntent(
            interests=["궁궐"],
            goal="생활 모습 비교",
            experience="저는 모두 이해했다고 생각해요",
            use_for_planning=True,
        )
    )

    def planner(state):
        captured.append(state["learner_intent"])
        return LearningDecision(action="ask", question="어떤 궁궐이 궁금한가요?")

    monkeypatch.setattr(learning, "_model_decision", planner)
    first = send(create_conversation())
    second = send(create_conversation())
    assert captured == [saved.planning_context()] * 2
    assert first.concepts == second.concepts == {}
    assert get_learning_intent() == saved
    saved.use_for_planning = False
    save_learning_intent(saved)
    send(first, "다른 이야기를 해보자")
    assert captured[-1] == {}


def test_control_requests_do_not_infer_or_overwrite_intent(isolated, monkeypatch):
    saved = save_learning_intent(LearningIntent(interests=["탑"], use_for_planning=True))
    monkeypatch.setattr(learning, "_model_decision", lambda _: pytest.fail("control called model"))
    state = send(create_conversation(), "로마 역사", control="change_topic")
    assert state.goal == "로마 역사" and state.concepts == {}
    assert get_learning_intent() == saved


def test_offline_interest_hint_is_not_used_over_a_current_question(isolated):
    save_learning_intent(LearningIntent(interests=["궁궐"], use_for_planning=True))
    first = send(create_conversation())
    assert "궁궐" in first.messages[-1].text
    assert first.concepts == {}
    second = send(create_conversation(), "오늘은 다른 시대 이야기가 궁금해요")
    assert "저장한 관심사" not in second.messages[-1].text


def test_actual_model_context_keeps_intent_distinct_from_concepts(isolated, monkeypatch):
    import json

    captured = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            captured.append(json.loads(kwargs["contents"]))
            assert "현재 발화와 주제 변경" in kwargs["config"].system_instruction
            return SimpleNamespace(
                text=LearningDecision(
                    action="ask", question="어느 시대가 궁금한가요?"
                ).model_dump_json()
            )

    save_learning_intent(LearningIntent(interests=["궁궐"], use_for_planning=True))
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only")
    monkeypatch.setattr(learning.genai, "Client", Client)
    send(create_conversation(), "오늘은 고분 이야기를 해줘")
    assert captured[0]["learner_confirmed_intent"]["interests"] == ["궁궐"]
    assert captured[0]["concepts"] == {}
    assert captured[0]["message"] == "오늘은 고분 이야기를 해줘"


def test_clear_and_full_deletion_do_not_affect_other_owners(isolated):
    saved = save_learning_intent(LearningIntent(interests=["궁궐"], use_for_planning=True))
    cleared = save_learning_intent(LearningIntent(revision=saved.revision))
    assert cleared.revision == 2 and cleared.planning_context() == {}
    marker = session_owner.set("intent-b")
    save_learning_intent(LearningIntent(interests=["석탑"]))
    session_owner.reset(marker)
    delete_records(owner="intent-a", apply=True)
    assert get_learning_intent().revision == 0
    marker = session_owner.set("intent-b")
    assert get_learning_intent().interests == ["석탑"]
    session_owner.reset(marker)


def test_age_cleanup_respects_owner_and_keeps_active_conversations(isolated):
    save_learning_intent(LearningIntent(interests=["궁궐"]))
    create_conversation()
    marker = session_owner.set("intent-b")
    save_learning_intent(LearningIntent(interests=["석탑"]))
    session_owner.reset(marker)
    with transaction() as connection:
        connection.execute("UPDATE learning_intents SET updated_at='2000-01-01'")
    cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    delete_records(owner="intent-a", cutoff=cutoff, apply=True)
    assert get_learning_intent().interests == ["궁궐"]
    marker = session_owner.set("intent-b")
    assert get_learning_intent().interests == ["석탑"]
    session_owner.reset(marker)
    delete_records(cutoff=cutoff, apply=True)
    marker = session_owner.set("intent-b")
    assert get_learning_intent() == LearningIntent()
    session_owner.reset(marker)


def test_api_and_optional_ui(isolated):
    with TestClient(app) as a, TestClient(app) as b:
        path = "/api/learning/intent"
        assert (
            a.put(path, json={"interests": ["궁궐"], "use_for_planning": True}).status_code == 200
        )
        assert a.get(path).json()["revision"] == 1
        assert b.get(path).json()["interests"] == []
        assert a.put(path, json={"goal": "stale"}).status_code == 409
        assert a.put(path, json={"interests": ["x" * 41]}).status_code == 422
        page = a.get("/learning-history")
        assert page.status_code == 200 and "내 관심사와 학습 목표" in page.text
