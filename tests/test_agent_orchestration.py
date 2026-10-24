"""Execution contracts, not proof of historical accuracy or real-model quality."""

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from culturebridge.agents import learning, workflow
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, load_quiz_items, transaction
from culturebridge.domain.learning import LearningDecision, LearningTurn
from culturebridge.domain.models import CollectedSource
from culturebridge.services import learning_agent_tools as tools
from culturebridge.services.learning_conversation_service import (
    create_conversation,
    send_learning_turn,
)
from culturebridge.services.operation_service import clear_operation_cache, session_owner


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", tmp_path / "agent.db")
    monkeypatch.setattr(settings, "gemini_enabled", False)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "public_mode", False)
    monkeypatch.setattr(
        workflow, "retry_missing_sources", lambda left, right, sources, missing: sources
    )
    initialize_database()
    token = session_owner.set("agent-learner")
    clear_operation_cache()
    yield
    clear_operation_cache()
    session_owner.reset(token)


def send(state, text="탑을 비교해서 배우고 싶어요", **kwargs):
    return send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=state.revision, text=text, **kwargs)
    )


def persist(state):
    with transaction() as conn:
        conn.execute(
            "UPDATE learning_conversations SET state_json=? WHERE id=?",
            (state.model_dump_json(), str(state.id)),
        )


def known_pair():
    state = create_conversation()
    state.search_results = [
        {"id": "seokguram", "name": "석굴암"},
        {"id": "horyuji", "name": "호류지"},
    ]
    return state


def synthetic_sources():
    return [
        CollectedSource(
            id="fixture:" + identity,
            heritage_id=identity,
            title=identity,
            organization="Synthetic fixture",
            source_url="https://www.khs.go.kr/",
            feed_url="https://www.khs.go.kr/",
            retrieved_at=datetime.now(UTC),
            status="fresh",
            scope_note="Synthetic individual source",
            content_kind="individual_text",
            content=text,
        )
        for identity, text in [
            (
                "seokguram",
                "석굴암은 751년에 건립되었다. 석굴암은 화강암으로 만든 석굴이다. "
                "석굴암은 불교 유산이다.",
            ),
            (
                "horyuji",
                "Horyuji Temple was built in 700. The temple is made of wood. "
                "The temple is a Buddhist temple.",
            ),
        ]
    ]


def compare_fixture(monkeypatch, state):
    monkeypatch.setattr(workflow, "collect_official_sources", lambda *a, **kw: synthetic_sources())
    status, result = tools.run_tool(
        state,
        LearningDecision(action="compare", source_id="seokguram", target_id="horyuji"),
        time.monotonic() + 30,
    )
    assert status == "ok", result
    return result["comparison_id"]


def test_compare_does_not_automatically_generate_quiz(isolated, monkeypatch):
    state = known_pair()
    identity = compare_fixture(monkeypatch, state)
    with transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM quiz_items").fetchone()[0] == 0
    status, observation = tools.run_tool(
        state, LearningDecision(action="quiz", comparison_id=identity), time.monotonic() + 30
    )
    assert status == "ok" and observation["awaiting_learner"]
    assert state.active_quiz["items"]
    assert "correct_index" not in json.dumps(state.active_quiz)
    assert "explanation" not in json.dumps(state.active_quiz)
    assert state.goal_status == "practising" and not state.concepts


def test_user_goal_cannot_be_dropped_by_planner_goal_text(isolated, monkeypatch):
    from culturebridge.services.learning_outcome_service import outcome_summary, update_contract

    state = known_pair()
    update_contract(state, "석굴암과 해외 유산을 종교적 배경으로 비교하고 퀴즈도 준비해 주세요")
    sources = synthetic_sources()
    sources = [
        s.model_copy(
            update={
                "content": s.content.split("석굴암은 불교")[0].split("The temple is a Buddhist")[0]
            }
        )
        for s in sources
    ]
    monkeypatch.setattr(workflow, "collect_official_sources", lambda *a, **kw: sources)
    status, observation = tools.run_tool(
        state,
        LearningDecision(
            action="compare",
            source_id="seokguram",
            target_id="horyuji",
            goal="재료만 보기",
            goal_mode="observe",
        ),
        time.monotonic() + 30,
    )
    assert status == "insufficient" and not observation["goal_suitable"]
    assert not outcome_summary(state)["comparison_goal_met"]
    status, _ = tools.run_tool(
        state,
        LearningDecision(action="quiz", comparison_id=observation["comparison_id"]),
        time.monotonic() + 10,
    )
    assert status == "blocked"
    assert not state.active_quiz


def test_compare_quiz_human_grade_and_agent_review_same_conversation(isolated, monkeypatch):
    state = known_pair()
    monkeypatch.setattr(workflow, "collect_official_sources", lambda *a, **kw: synthetic_sources())
    persist(state)

    def planner(turn):
        conversation = turn["conversation"]
        if not conversation.learning_artifacts:
            return LearningDecision(action="compare", source_id="seokguram", target_id="horyuji")
        return LearningDecision(
            action="quiz", comparison_id=conversation.learning_artifacts[-1]["id"]
        )

    monkeypatch.setattr(learning, "_model_decision", planner)
    state = send(state)
    assert [o["tool"] for o in state.tool_observations] == ["compare", "quiz"]
    assert not state.active_quiz["submitted"]
    original_messages = len(state.messages)
    items = load_quiz_items(state.active_quiz["id"])
    answers = [(item["correct_index"] + 1) % 4 for item in items]

    def review_planner(turn):
        conversation = turn["conversation"]
        if not conversation.quiz_review:
            return LearningDecision(action="review_quiz")
        source = conversation.sources[0]
        return LearningDecision(
            action="review", source_id=source["id"], concept=source["excerpts"][0]["concept"]
        )

    monkeypatch.setattr(learning, "_model_decision", review_planner)
    state = send(state, text="", control="submit_quiz", answers=answers)
    assert state.active_quiz["submitted"] and state.active_quiz["score"] == 0
    assert len(state.messages) > original_messages
    assert state.messages[-2].text == "퀴즈 답안을 제출했어요."
    assert state.quiz_review["history_id"] == state.active_quiz["history_id"]
    assert state.messages[-1].citations and state.goal_status == "reviewing"
    assert not state.concepts  # An incorrect choice is not a semantic diagnosis.


def test_quiz_cannot_use_other_learner_comparison(isolated, monkeypatch):
    state = known_pair()
    identity = compare_fixture(monkeypatch, state)
    token = session_owner.set("different-learner")
    try:
        with pytest.raises(ValueError, match="학습자"):
            tools.run_tool(
                state,
                LearningDecision(action="quiz", comparison_id=identity),
                time.monotonic() + 30,
            )
    finally:
        session_owner.reset(token)


def test_failed_tool_observation_changes_next_action(isolated, monkeypatch):
    calls = []

    def retrieval(turn):
        calls.append(turn["decision"].query)
        if len(calls) == 1:
            raise TimeoutError("private provider diagnostics must not be copied")
        return {"tool_status": "ok"}

    def planner(turn):
        observations = turn["conversation"].tool_observations
        if not observations:
            return LearningDecision(action="search", query="다보탑")
        if observations[-1]["status"] == "error":
            return LearningDecision(action="search_world", query="pagoda")
        return LearningDecision(action="ask", question="다른 대상을 살펴볼까요?")

    monkeypatch.setattr(learning, "_model_decision", planner)
    monkeypatch.setattr(learning, "_retrieval_tool", retrieval)
    state = send(create_conversation())
    assert calls == ["다보탑", "pagoda"]
    assert [o["status"] for o in state.tool_observations] == ["error", "empty"]
    assert "private provider" not in state.model_dump_json()


def test_duplicate_tool_replans_without_reexecuting(isolated, monkeypatch):
    calls = []
    monkeypatch.setattr(
        learning, "_model_decision", lambda _: LearningDecision(action="search", query="탑")
    )
    monkeypatch.setattr(
        learning, "_retrieval_tool", lambda _: calls.append(1) or {"tool_status": "ok"}
    )
    state = send(create_conversation())
    assert calls == [1]
    assert any(o["status"] == "duplicate" for o in state.tool_observations)
    assert len(state.tool_observations) <= get_settings().learning_turn_steps + 2


@pytest.mark.parametrize(
    "decision",
    [
        LearningDecision(action="compare", source_id="unknown", target_id="horyuji"),
        LearningDecision(
            action="discover",
            source_id="seokguram",
            goal="해외 유산 비교",
            comparison_scope="domestic",
        ),
    ],
)
def test_unobserved_ids_and_silent_scope_change_blocked(isolated, decision):
    status, _ = tools.run_tool(known_pair(), decision, time.monotonic() + 30)
    assert status == "blocked"


def test_expired_budget_and_new_topic_invalidation(isolated):
    state = known_pair()
    assert tools.run_tool(state, LearningDecision(action="discover"), 0)[0] == "budget"
    state.learning_artifacts = [{"kind": "comparison", "id": "previous"}]
    state.active_quiz = {"id": "previous", "submitted": False}
    persist(state)
    state = send(state, control="change_topic", text="조선 궁궐")
    assert not state.active_quiz and not state.learning_artifacts
    assert state.messages and state.topic_start > 0


def test_scope_changes_only_from_user_request(isolated, monkeypatch):
    monkeypatch.setattr(
        learning,
        "_model_decision",
        lambda _: LearningDecision(
            action="ask", goal="국내 유산 재료 비교", question="어떤 자료가 궁금한가요?"
        ),
    )
    state = send(create_conversation(), text="해외 문화유산과 비교해 주세요")
    assert state.comparison_scope == "overseas"
    blocked, _ = tools.run_tool(
        state,
        LearningDecision(action="discover", comparison_scope="domestic", goal="국내 비교"),
        time.monotonic() + 30,
    )
    assert blocked == "blocked"
    state = send(state, text="이번에는 국내 문화유산끼리 비교해 주세요")
    assert state.comparison_scope == "domestic"


def test_model_cannot_submit_learner_answers():
    with pytest.raises(ValidationError):
        LearningDecision(action="submit_quiz")


def test_tool_identity_ignores_fields_not_used_by_tool():
    first = LearningDecision(action="search", query="탑", level="beginner")
    second = LearningDecision(action="search", query="탑", level="advanced", goal="다른 표현")
    assert tools.action_key(first) == tools.action_key(second)


def test_inline_quiz_renders_without_executing_planner(isolated, monkeypatch):
    from fastapi.testclient import TestClient

    from culturebridge.domain.learning import LearningConversation
    from culturebridge.main import app

    planner_calls = []

    def unexpected(*args, **kwargs):
        planner_calls.append(True)
        raise AssertionError("Rendering must not execute the model")

    monkeypatch.setattr(learning, "_model_decision", unexpected)
    with TestClient(app) as client:
        state = LearningConversation.model_validate(
            client.post("/api/learning/conversations").json()
        )
        state.learning_plan = ["compare", "quiz", "review"]
        state.active_quiz = {
            "id": "synthetic-render-only",
            "submitted": False,
            "items": [
                {
                    "question": "원문에서 확인한 재료는 무엇인가요?",
                    "choices": [
                        {"id": i, "text": text}
                        for i, text in enumerate(["화강암", "나무", "흙", "금속"])
                    ],
                }
            ],
        }
        tools.observe(state, "quiz", {}, "ok", {"awaiting_learner": True}, planner="ai")
        persist(state)
        response = client.get(f"/learn?conversation_id={state.id}")
        assert response.status_code == 200
        assert "답안 제출하고 이어서 학습" in response.text
        assert "이번 학습 계획" in response.text
        assert "원문에서 확인한 재료는 무엇인가요?" in response.text
        assert not planner_calls


def test_assessment_is_observation_not_forced_next_action(isolated, monkeypatch):
    from culturebridge.services import understanding_assessment_service as assessment

    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic-not-a-real-key")
    state = create_conversation()
    quote = "석굴암은 화강암으로 만들었다."
    source = {
        "id": "seokguram",
        "name": "석굴암",
        "url": "https://www.khs.go.kr/",
        "excerpts": [{"concept": "재료", "quote": quote}],
    }
    state.sources = [source]
    state.checkpoint = {"source_id": "seokguram", "concept": "재료", "quote": quote}
    monkeypatch.setattr(
        assessment,
        "assessment_decision",
        lambda _: LearningDecision(
            action="check",
            source_id="seokguram",
            concept="재료",
            assessment="tentative_support",
            assessment_quote=quote,
            reason="답과 근거가 일치함",
        ),
    )
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
            return SimpleNamespace(
                text=LearningDecision(
                    action="search_world", query="wooden temple", reason="다른 재료 사례 탐색"
                ).model_dump_json()
            )

    monkeypatch.setattr(learning.genai, "Client", Client)
    turn = {
        "conversation": state,
        "request": LearningTurn(request_id=uuid4(), revision=0, text="화강암으로 만들었어요"),
        "seen": [],
        "deadline": time.monotonic() + 40,
    }
    decision = learning._model_decision(turn)
    assert decision.action == "search_world"  # Not assessment's legacy check action.
    assert decision.source_id == decision.target_id == decision.comparison_id == ""
    assert captured[0]["understanding_feedback"]["judgment"] == "tentative_support"
    assert captured[0]["understanding_feedback"]["not_mastery"]
    assert state.concepts["재료"]["status"] == "tentative_support"
