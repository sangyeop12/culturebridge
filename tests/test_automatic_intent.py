from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningDecision, LearningIntentSignal, LearningTurn
from culturebridge.main import app
from culturebridge.services.automatic_intent_service import (
    clear_automatic_intent,
    get_automatic_intent,
)
from culturebridge.services.data_retention_service import delete_records
from culturebridge.services.learning_conversation_service import (
    create_conversation,
    get_conversation,
    request_learning_stop,
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
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "automatic.db")
    initialize_database()
    marker = session_owner.set("automatic-a")
    yield
    session_owner.reset(marker)


def send(state, text, **kwargs):
    return send_learning_turn(
        state.id,
        LearningTurn(
            request_id=uuid4(),
            revision=state.revision,
            text=text,
            **kwargs,
        ),
    )


def planner(monkeypatch, signals, captured=None):
    def decision(state):
        if captured is not None:
            captured.append(state)
        return LearningDecision(
            action="ask", question="어떤 이야기를 더 살펴볼까요?", intent_signals=signals
        )

    monkeypatch.setattr(learning, "_model_decision", decision)


def test_automatic_inference_persists_without_confirmation_and_is_not_assessment(
    isolated, monkeypatch
):
    optional = LearningDecision.model_validate(
        {
            "action": "search",
            "query": "궁궐",
            "intent_signals": [{"kind": "invalid"}],
        }
    )
    assert optional.action == "search" and optional.intent_signals == []
    text = "궁궐에서 사람들이 어떻게 살았는지 알고 싶어요"
    signals = [
        LearningIntentSignal(kind="interest", topic="궁궐", quote="궁궐에서 사람들이"),
        LearningIntentSignal(kind="goal", topic="궁궐의 생활 이해", quote=text),
    ]
    captured = []
    planner(monkeypatch, signals, captured)
    state = send(create_conversation(), text)
    profile = get_automatic_intent()
    assert profile["interests"][0]["topic"] == "궁궐"
    assert profile["goal"]["topic"] == "궁궐의 생활 이해"
    assert profile["tentative"] and profile["not_an_assessment"]
    assert state.concepts == {} and "저장할까요" not in state.messages[-1].text
    assert get_learning_intent().interests == []  # Explicit user settings stay separate.
    send(create_conversation(), "다른 이야기도 궁금해요")
    assert captured[-1]["automatic_intent"]["goal"]["topic"] == "궁궐의 생활 이해"
    assert captured[-1]["learner_intent"] == {}


@pytest.mark.parametrize(
    "topic,quote,text",
    [
        ("궁궐", "원문에만 있는 궁궐", "이어서 알려줘"),
        ("고분", "궁궐의 생활", "궁궐의 생활 이야기를 들려줘"),
        ("연락", "연락 a@example.com", "연락 a@example.com"),
        ("비밀번호", "비밀번호 abc123", "비밀번호 abc123"),
    ],
)
def test_unanchored_or_sensitive_learning_hints_are_not_retained(
    isolated, monkeypatch, topic, quote, text
):
    planner(monkeypatch, [LearningIntentSignal(kind="interest", topic=topic, quote=quote)])
    send(create_conversation(), text)
    assert get_automatic_intent()["interests"] == []


def test_duplicate_request_does_not_count_interest_twice(isolated, monkeypatch):
    text = "궁궐의 생활을 알려줘"
    planner(monkeypatch, [LearningIntentSignal(kind="interest", topic="궁궐", quote=text)])
    state = create_conversation()
    request = LearningTurn(request_id=uuid4(), revision=0, text=text)
    first = send_learning_turn(state.id, request)
    assert send_learning_turn(state.id, request) == first
    assert get_automatic_intent()["interests"][0]["mentions"] == 1
    assert "_pending_intent_signals" not in first.model_dump_json()


def test_disable_blocks_collection_and_planner_context(isolated, monkeypatch):
    save_learning_intent(LearningIntent(infer_from_dialogue=False))
    captured = []
    planner(
        monkeypatch,
        [LearningIntentSignal(kind="interest", topic="궁궐", quote="궁궐이 궁금해요")],
        captured,
    )
    send(create_conversation(), "궁궐이 궁금해요")
    assert get_automatic_intent()["interests"] == []
    assert captured[0]["automatic_intent"] == {}
    assert captured[0]["automatic_intent_enabled"] is False


def test_explicit_offline_phrases_are_labeled_and_used_for_next_start(isolated):
    send(create_conversation(), "궁궐에 관심이 있어요")
    profile = get_automatic_intent()
    assert profile["interests"][0]["topic"] == "궁궐"
    assert profile["interests"][0]["method"] == "explicit_phrase"
    state = send(create_conversation(), "역사 공부를 시작하고 싶어요")
    assert "최근 궁금해한 ‘궁궐’" in state.messages[-1].text
    assert not state.concepts
    state = send(state, "궁궐에는 관심 없어요")
    assert not get_automatic_intent()["interests"]
    state = send(state, "고분의 구조를 비교하고 싶어요")
    assert get_automatic_intent()["goal"]["topic"] == state.goal == "고분의 구조를 비교하고 싶어요"
    send(state, "이전 목표는 취소할래요")
    assert get_automatic_intent()["goal"] is None


def test_goal_updates_and_explicit_rejection_does_not_touch_manual_goal(isolated, monkeypatch):
    save_learning_intent(LearningIntent(goal="직접 지정한 목표", use_for_planning=True))
    planner(
        monkeypatch,
        [
            LearningIntentSignal(
                kind="goal", topic="궁궐 생활 이해", quote="궁궐 생활을 배우고 싶어요"
            )
        ],
    )
    send(create_conversation(), "궁궐 생활을 배우고 싶어요")
    planner(
        monkeypatch,
        [
            LearningIntentSignal(
                kind="goal", topic="고분 구조 비교", quote="고분 구조를 비교하고 싶어요"
            )
        ],
    )
    send(create_conversation(), "고분 구조를 비교하고 싶어요")
    assert get_automatic_intent()["goal"]["topic"] == "고분 구조 비교"
    planner(
        monkeypatch,
        [
            LearningIntentSignal(
                kind="forget_goal", topic="이전 목표", quote="이전 목표는 취소할래요"
            )
        ],
    )
    send(create_conversation(), "이전 목표는 취소할래요")
    assert get_automatic_intent()["goal"] is None
    assert get_learning_intent().goal == "직접 지정한 목표"


def test_interest_denial_and_bounded_memory(isolated, monkeypatch):
    for number in range(10):
        topic = f"유산{number}"
        text = topic + "를 알려줘"
        planner(monkeypatch, [LearningIntentSignal(kind="interest", topic=topic, quote=text)])
        send(create_conversation(), text)
    assert len(get_automatic_intent()["interests"]) == 8
    planner(
        monkeypatch,
        [
            LearningIntentSignal(
                kind="forget_interest", topic="유산9", quote="유산9에는 관심 없어요"
            )
        ],
    )
    send(create_conversation(), "유산9에는 관심 없어요")
    assert "유산9" not in [i["topic"] for i in get_automatic_intent()["interests"]]
    planner(
        monkeypatch,
        [
            LearningIntentSignal(
                kind="interest",
                topic="유산9",
                quote="유산9에는 관심 없어요",
            )
        ],
    )
    send(create_conversation(), "유산9에는 관심 없어요")
    assert "유산9" not in [i["topic"] for i in get_automatic_intent()["interests"]]


def test_stop_does_not_commit_pending_guesses(isolated, monkeypatch):
    state = create_conversation()

    def decision(_):
        request_learning_stop(state.id, state.revision)
        return LearningDecision(
            action="ask",
            intent_signals=[
                LearningIntentSignal(
                    kind="interest",
                    topic="궁궐",
                    quote="궁궐이 궁금해요",
                )
            ],
        )

    monkeypatch.setattr(learning, "_model_decision", decision)
    assert send(state, "궁궐이 궁금해요").status == "paused"
    assert not get_automatic_intent()["interests"]


def test_clear_disables_and_preserves_manual_settings_and_dialogue(isolated):
    save_learning_intent(LearningIntent(goal="수동 목표"))
    state = send(create_conversation(), "궁궐에 관심이 있어요")
    cleared = clear_automatic_intent()
    assert not cleared.infer_from_dialogue and cleared.goal == "수동 목표"
    assert not get_automatic_intent()["interests"]
    assert get_conversation(state.id).messages


def test_owned_memory_and_full_session_deletion(isolated):
    send(create_conversation(), "궁궐에 관심이 있어요")
    marker = session_owner.set("automatic-b")
    assert not get_automatic_intent()["interests"]
    send(create_conversation(), "고분에 관심이 있어요")
    session_owner.reset(marker)
    delete_records(owner="automatic-a", apply=True)
    assert not get_automatic_intent()["interests"]
    marker = session_owner.set("automatic-b")
    assert get_automatic_intent()["interests"][0]["topic"] == "고분"
    session_owner.reset(marker)


def test_api_and_ui_do_not_request_confirmation(isolated):
    with TestClient(app) as client:
        assert client.get("/api/learning/intent/automatic").json()["enabled"] is True
        page = client.get("/").text
        assert "매번 저장 여부를 묻지 않아요" in page
        assert "자동 파악 끄고 기록 비우기" in page
        assert client.post("/api/learning/intent/automatic/reset").status_code == 200
        assert client.get("/api/learning/intent/automatic").json()["enabled"] is False


def test_actual_planner_payload_distinguishes_inferred_and_direct_settings(isolated, monkeypatch):
    import json
    from types import SimpleNamespace

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
            assert "저장 여부는 묻지 않는다" in kwargs["config"].system_instruction
            return SimpleNamespace(
                text=LearningDecision(
                    action="ask", question="어떤 궁궐이 궁금한가요?"
                ).model_dump_json()
            )

    send(create_conversation(), "궁궐에 관심이 있어요")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only")
    monkeypatch.setattr(learning.genai, "Client", Client)
    send(create_conversation(), "그럼 다른 나라의 궁궐은 어때요?")
    assert captured[0]["dialogue_inferred_intent"]["interests"][0]["topic"] == "궁궐"
    assert captured[0]["learner_confirmed_intent"] == {} and captured[0]["concepts"] == {}


def test_retention_clears_only_expired_owner_hints_without_live_dialogue(isolated):
    from culturebridge.database import transaction

    send(create_conversation(), "궁궐에 관심이 있어요")
    marker = session_owner.set("automatic-b")
    send(create_conversation(), "고분에 관심이 있어요")
    session_owner.reset(marker)
    with transaction() as connection:
        connection.execute("UPDATE inferred_learning_intents SET updated_at='2000-01-01'")
    delete_records(owner="automatic-a", cutoff="2026-01-01", apply=True)
    assert get_automatic_intent()["interests"]  # Recent conversation survives.
    with transaction() as connection:
        connection.execute("UPDATE learning_conversations SET updated_at='2000-01-01'")
    delete_records(owner="automatic-a", cutoff="2026-01-01", apply=True)
    assert not get_automatic_intent()["interests"]
    marker = session_owner.set("automatic-b")
    assert get_automatic_intent()["interests"][0]["topic"] == "고분"
    session_owner.reset(marker)
