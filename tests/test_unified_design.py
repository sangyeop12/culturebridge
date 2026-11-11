from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from nicegui import Client
from nicegui.elements.button import Button
from nicegui.elements.expansion import Expansion

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
        ("/settings", "settings"),
    ],
)
def test_all_screen_families_share_navigation(path, section):
    assert section_for(path) == section
    assert len(PRIMARY) == 4  # The brand already links home; avoid a duplicate menu item.


def test_museum_illustration_is_local_and_labelled():
    from culturebridge.ui.heritage_art import museum_scene

    drawing = museum_scene()
    assert 'role="img"' in drawing
    assert "상상의 역사 전시관" in drawing
    assert "<script" not in drawing and "href=" not in drawing


def test_quiz_selection_progress_does_not_count_answer_changes_twice(tmp_path, monkeypatch):
    from nicegui.elements.radio import Radio

    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "quiz-progress.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    with TestClient(app) as client:
        assert client.get("/quiz/seokguram/horyuji").status_code == 200
        page = next(reversed(list(Client.instances.values())))
        progress = next(e for e in page.elements.values() if "cb-quiz-progress" in e._classes)
        radios = [e for e in page.elements.values() if isinstance(e, Radio)]
        assert progress.text == "0 / 5문제 선택했어요"
        with page:
            radios[0].set_value(next(iter(radios[0].options)))
            assert progress.text == "1 / 5문제 선택했어요"
            radios[0].set_value(list(radios[0].options)[1])
            assert progress.text == "1 / 5문제 선택했어요"
            for radio in radios[1:]:
                radio.set_value(next(iter(radio.options)))
            assert progress.text == "5 / 5문제 선택했어요"


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


def test_home_and_library_separate_start_flows_but_keep_learning_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / f"{uuid4()}.db")
    initialize_database()
    with TestClient(app) as client:
        page = client.get("/").text
        assert "history-start" in page and 'id="heritage-search"' not in page
        for text in [
            "함께 알아보기",
            "말로 질문하기",
            "/settings",
        ]:
            assert text in page
        assert "설명 스타일" not in page
        assert "내 관심사와 학습 목표" not in page
        library = client.get("/library").text
        assert "heritage-search" in library and "공식 자료 통합 검색" in library
        for path in ("/official", "/learning-history"):
            assert "cb-sidebar" in client.get(path).text


def test_comparison_keeps_tools_collapsed_and_quiz_before_extra_activities(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "simple-comparison.db")
    initialize_database()
    with TestClient(app) as client:
        assert client.get("/compare/seokguram/horyuji").status_code == 200
        page = next(reversed(list(Client.instances.values())))
        elements = list(page.elements.values())
        root = next(e for e in elements if "cb-shell" in e._classes)
        actions = next(e for e in elements if "cb-next-actions" in e._classes)
        assert any(
            isinstance(e, Button) and e.text == "학습 확인 퀴즈"
            for e in actions.default_slot.children
        )
        for label, button_text in (
            ("궁금한 점 질문하기", "질문하기"),
            ("이 설명은 근거가 있을까요?", "자료와 대조하기"),
            ("내 생각 정리하기", "내 정리 저장"),
        ):
            expansion = next(
                e for e in elements if isinstance(e, Expansion) and e._props.get("label") == label
            )
            assert expansion.value is False
            assert root.default_slot.children.index(actions) < root.default_slot.children.index(
                expansion
            )
            button = next(e for e in elements if isinstance(e, Button) and e.text == button_text)
            assert button.parent_slot.parent == expansion


def test_help_links_are_collapsed_in_shared_sidebar(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "simple-menu.db")
    initialize_database()
    with TestClient(app) as client:
        assert client.get("/learn").status_code == 200
        page = next(reversed(list(Client.instances.values())))
        menu = next(
            e
            for e in page.elements.values()
            if isinstance(e, Expansion) and e._props.get("label") == "도움말과 이용 안내"
        )
        assert menu.value is False
        links = {e._props.get("href") for e in menu.default_slot.children}
        assert {"/sources", "/data-policy", "/install", "/kiosk"} <= links
        assert not any("cb-context-wrap" in e._classes for e in page.elements.values())


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
