"""Regression checks for the November 13 service review; no live provider requests."""

import asyncio
import inspect
import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from nicegui import Client
from nicegui.elements.button import Button

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import ConversationMessage, LearningConversation
from culturebridge.services.conversation_title_service import (
    conversation_preview,
    conversation_title,
)
from culturebridge.services.gemini_options import interactive_timeout, model_request_scope
from culturebridge.services.learning_outcome_service import update_contract
from culturebridge.services.learning_preferences import LearningPreferences, preferred_level
from culturebridge.ui.learner_copy import legacy_review, review_reading
from culturebridge.ui.learning_chat import explanation_origin


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "remediation.db")
    initialize_database()


@pytest.mark.parametrize(
    "question",
    [
        "다보탑과 다른 나라의 탑을 비교해줘",
        "다보탑을 호류지와 비교해줘",
        "다보탑이랑 다른 나라 탑 비교해줘",
        "다보탑과 호류지의 재료를 비교해줘",
        "다보탑하고 호류지를 비교해줘",
        "그러면 다보탑을 기준으로 비교해줘",
    ],
)
def test_explicit_comparison_anchor_under_natural_rephrasings(question):
    state = LearningConversation(id=uuid4(), revision=0)
    update_contract(state, question)
    assert state.task_contract["subject"] == "다보탑"


def test_category_request_does_not_replace_known_subject():
    state = LearningConversation(id=uuid4(), revision=0)
    update_contract(state, "다보탑과 다른 나라 탑을 비교해줘")
    update_contract(state, "재료와 구조를 비교해줘")
    assert state.task_contract["subject"] == "다보탑"
    assert state.task_contract["categories"] == ["구조", "재료"]


def test_followup_goal_change_keeps_anchor_and_pending_quiz():
    state = LearningConversation(id=uuid4(), revision=0)
    update_contract(state, "다보탑과 다른 나라 탑을 시대와 재료로 비교하고 퀴즈도 만들어줘")
    update_contract(state, "이제 시대는 빼고 구조와 재료를 비교해줘")
    assert state.task_contract["subject"] == "다보탑"
    assert state.task_contract["categories"] == ["구조", "재료"]
    assert state.task_contract["quiz_requested"]
    update_contract(state, "재료만 비교하고 퀴즈 없이 알려줘")
    assert state.task_contract["categories"] == ["재료"]
    assert not state.task_contract["quiz_requested"]


def test_model_request_limit_deadline_and_stop_are_checked_without_network():
    with model_request_scope(time.monotonic() + 5, lambda: False):
        assert 0 < interactive_timeout(time.monotonic() + 100, 15000) <= 2000
        for _ in range(11):
            interactive_timeout(time.monotonic() + 100, 15000)
        with pytest.raises(ValueError, match="learning_request_budget"):
            interactive_timeout(time.monotonic() + 100, 15000)
    with model_request_scope(time.monotonic() + 100, lambda: True):
        with pytest.raises(ValueError, match="learning_request_stopped"):
            interactive_timeout(time.monotonic() + 100, 15000)
    with pytest.raises(ValueError, match="learning_request_budget"):
        interactive_timeout(time.monotonic(), 15000)


def test_saved_title_survives_message_window_trimming():
    assert (
        conversation_title(
            {
                "title": "다보탑 알아보기",
                "messages": [{"role": "user", "text": "짧게 설명해줘"}],
            }
        )
        == "다보탑 알아보기"
    )


@pytest.mark.parametrize(
    "method,expected",
    [
        ("gemini_term_help", "일반적인 뜻"),
        ("gemini_grounded_rewrite", "공식 자료를 바탕"),
        ("gemini_failed", "준비하지 못했어요"),
        ("local_guide", "읽는 도움말"),
    ],
)
def test_explanation_labels_distinguish_general_knowledge_from_source_help(method, expected):
    message = ConversationMessage(role="assistant", text="설명", teaching={"method": method})
    label = explanation_origin(message)
    assert expected in label
    assert "Gemini" not in label and "검증 실패" not in label


def test_legacy_review_is_korean_and_source_text_is_not_rewritten():
    raw = (
        "2번 다시 보기: 예전 문제 → 정답: The stone tower · 복습 항목: 재료"
        " · 원문: Made of wood. · 해당 자료의 설명을 고르는 문제입니다. "
        "추출의 역사적 의미는 추가 검토가 필요합니다."
    )
    reading = legacy_review(raw)
    assert reading["quote"] == "Made of wood."
    assert "검토" not in reading["activity"]
    assert "나무" in review_reading(reading["quote"])
    assert "Toji" in review_reading("도지(Toji)의 재료는 무엇인가요?")


def test_preferred_level_respects_explicit_choice_and_course_recommendation(monkeypatch):
    from culturebridge.services import learning_preferences as preferences

    monkeypatch.setattr(
        preferences, "get_preferences", lambda: LearningPreferences(default_level="advanced")
    )
    assert preferred_level() == "advanced"
    assert preferred_level("beginner") == "beginner"
    monkeypatch.setattr(preferences, "get_preferences", lambda: LearningPreferences())
    assert preferred_level(fallback="intermediate") == "intermediate"


def test_empty_conversation_hidden_not_deleted_and_course_search_link(isolated):
    from culturebridge.main import app

    with TestClient(app) as client:
        empty = client.post("/api/learning/conversations").json()
        assert client.get("/api/learning/conversations").json() == []
        assert client.get(f"/api/learning/conversations/{empty['id']}").status_code == 200
        client.get("/courses")
        page = next(reversed(list(Client.instances.values())))
        assert any(e._props.get("href") == "/library" for e in page.elements.values())


def test_failure_notice_remains_visible_after_spinner_stops(isolated, monkeypatch):
    from culturebridge.main import app
    from culturebridge.ui import pages

    async def failed_worker(*args, **kwargs):
        raise ValueError("synthetic failure")

    monkeypatch.setattr(pages, "_io_bound", failed_worker)
    with TestClient(app) as client:
        state = client.post("/api/learning/conversations").json()
        state["messages"] = [{"role": "user", "text": "다보탑 설명"}]
        with transaction() as connection:
            connection.execute(
                "UPDATE learning_conversations SET state_json=? WHERE id=?",
                (json.dumps(state), state["id"]),
            )
        client.get(f"/learn?conversation_id={state['id']}")
        page = next(reversed(list(Client.instances.values())))
        button = next(
            e for e in page.elements.values() if isinstance(e, Button) and e.text == "보내기"
        )
        with page:
            prompt = next(
                e for e in page.elements.values() if e._props.get("label") == "이야기 이어가기"
            )
            prompt.set_value("설명해줘")
            callback = next(
                e.handler for e in button._event_listeners.values() if e.type == "click"
            )
            on_click = inspect.getclosurevars(callback).nonlocals["callback"]

            async def invoke():
                with page:
                    await on_click()

            asyncio.run(invoke())
        notice = next(
            e
            for e in page.elements.values()
            if "요청을 처리하지 못했어요" in str(getattr(e, "text", ""))
        )
        assert notice.visible and "cb-thinking" not in notice.parent_slot.parent._classes
        spinner = next(e for e in page.elements.values() if "cb-thinking" in e._classes)
        assert not spinner.visible


def test_preview_uses_followup_question_instead_of_provider_notice():
    state = {
        "title": "경복궁 알아보기",
        "messages": [
            {"role": "user", "text": "서원이 뭐야?"},
            {"role": "assistant", "text": "Gemini 설명 실패"},
        ],
    }
    assert conversation_preview(state) == "서원이 뭐야?"


def test_first_question_retry_reuses_the_same_conversation_and_request(isolated, monkeypatch):
    from culturebridge.main import app
    from culturebridge.ui import pages

    state = LearningConversation(id=uuid4(), revision=0)
    creates, requests, destinations = [], [], []

    async def worker(callback, *args, **kwargs):
        if callback.__name__ == "create_conversation":
            creates.append(True)
            return state
        requests.append(args[1].request_id)
        if len(requests) == 1:
            raise RuntimeError("synthetic uncertain transport")
        return state

    monkeypatch.setattr(pages, "_io_bound", worker)
    monkeypatch.setattr(pages.ui.navigate, "to", destinations.append)
    with TestClient(app) as client:
        client.get("/learn")
        page = next(reversed(list(Client.instances.values())))
        prompt = next(
            e
            for e in page.elements.values()
            if e._props.get("label") == "어떤 이야기가 궁금한가요?"
        )
        prompt.set_value("다보탑 설명해줘")
        button = next(
            e for e in page.elements.values() if isinstance(e, Button) and e.text == "함께 알아보기"
        )
        handler = next(e.handler for e in button._event_listeners.values() if e.type == "click")
        on_click = inspect.getclosurevars(handler).nonlocals["callback"]

        async def twice():
            with page:
                await on_click()
                await on_click()

        asyncio.run(twice())
    assert len(creates) == 1 and len(requests) == 2 and requests[0] == requests[1]
    assert destinations == [f"/learn?conversation_id={state.id}"]


def test_personal_and_shared_history_are_disjoint_and_public_mode_stays_private(
    isolated, monkeypatch
):
    from culturebridge.services.learning_history_service import list_learning_reviews
    from culturebridge.services.operation_service import session_owner

    with transaction() as connection:
        for owner in ("learner-a", "learner-b"):
            cursor = connection.execute(
                "INSERT INTO learning_history(session_id,heritage_id,level,score,total) "
                "VALUES(?, 'seokguram', 'beginner', 3, 5)",
                (owner,),
            )
            connection.execute(
                "INSERT INTO learning_reviews VALUES(?,?,?,?)",
                (cursor.lastrowid, owner + "-quiz", "{}", owner),
            )
    token = session_owner.set("learner-a")
    try:
        monkeypatch.setattr(get_settings(), "public_mode", False)
        mine = list_learning_reviews(records="mine")
        shared = list_learning_reviews(records="shared")
        assert len(mine) == len(shared) == 1
        assert mine[0]["can_conversation_review"] and not shared[0]["can_conversation_review"]
        monkeypatch.setattr(get_settings(), "public_mode", True)
        assert list_learning_reviews(records="shared") == []
        assert len(list_learning_reviews()) == 1
    finally:
        session_owner.reset(token)
