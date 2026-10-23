from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from nicegui import Client
from nicegui.elements.button import Button

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import ConversationMessage
from culturebridge.main import app
from culturebridge.services.learning_preferences import LearningPreferences
from culturebridge.ui.learning_chat import control_text, message_body
from culturebridge.ui.navigation import PRIMARY, section_for


@pytest.mark.parametrize(
    "path,section",
    [
        ("/", "home"),
        ("/learn", "conversation"),
        ("/learning-history", "history"),
        ("/comparisons", "history"),
        ("/data-policy", "history"),
        ("/official", "heritage"),
        ("/unesco", "heritage"),
        ("/compare/a/b", "heritage"),
        ("/quiz/a/b", "heritage"),
        ("/research/a/b", "heritage"),
        ("/sources/open/dayanta", "heritage"),
        ("/courses/palaces", "courses"),
        ("/install", "guide"),
    ],
)
def test_all_screen_families_share_navigation(path, section):
    assert section_for(path) == section
    assert len(PRIMARY) == 5


def test_quote_is_available_once_without_hiding_followup_or_mutating_record():
    quote = "화강암으로 만든 석탑이다."
    message = ConversationMessage(
        role="assistant",
        text=("이 탑의 재료를 살펴봐요.\n\n공식 원문: " + quote + "\n\n왜 그렇게 생각하나요?"),
        citations=[{"quote": quote}],
    )
    before = message.model_dump_json()
    displayed = message_body(message, LearningPreferences())
    assert quote not in displayed and "왜 그렇게 생각하나요?" in displayed
    assert message.model_dump_json() == before and message.citations[0]["quote"] == quote
    for role, kind in [("user", "dialogue"), ("assistant", "dictionary")]:
        untouched = message.model_copy(update={"role": role, "kind": kind})
        assert message_body(untouched, LearningPreferences()) == untouched.text


@pytest.mark.parametrize("control", ["stop", "resume", "skip", "review_question", "read_source"])
def test_progress_buttons_never_send_an_unfinished_draft(control):
    assert control_text(control, "아직 보내지 않은 질문") == ""
    assert control_text("message", "  내가 전송한 질문  ") == "내가 전송한 질문"


def test_home_keeps_both_workflows_and_progressive_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / f"{uuid4()}.db")
    initialize_database()
    with TestClient(app) as client:
        page = client.get("/").text
        assert "history-start" in page and "heritage-search" in page
        for text in [
            "함께 알아보기",
            "공식 자료 통합 검색",
            "말로 질문하기",
            "설명 스타일",
            "내 관심사와 학습 목표",
        ]:
            assert text in page
        assert page.index("질문에서 시작하는") < page.index("궁금한 역사 이야기부터 시작해요")
        assert "현재 위치" in client.get("/official").text
        assert "관련 화면" in client.get("/learning-history").text


@pytest.mark.parametrize(
    "path,label", [("/official", "문화유산 찾기"), ("/unesco", "세계유산 찾기")]
)
def test_search_actions_stay_above_results(path, label, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "search-order.db")
    initialize_database()
    with TestClient(app) as client:
        assert client.get(path).status_code == 200
        page = next(
            c
            for c in reversed(list(Client.instances.values()))
            if any(isinstance(e, Button) and e.text == label for e in c.elements.values())
        )
        button = next(
            e for e in page.elements.values() if isinstance(e, Button) and e.text == label
        )
        root = next(e for e in page.elements.values() if "cb-shell" in e._classes)
        branch = button
        while branch.parent_slot.parent != root:
            branch = branch.parent_slot.parent
        children = root.default_slot.children
        result = next(e for e in children if e._props.get("role") == "status")
        assert children.index(branch) < children.index(result)
