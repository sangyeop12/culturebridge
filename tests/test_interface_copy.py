import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import ConversationMessage
from culturebridge.main import app
from culturebridge.services.display_service import readable_trace
from culturebridge.services.learning_preferences import LearningPreferences
from culturebridge.ui.copy import service_text
from culturebridge.ui.learning_chat import message_body


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/learn",
        "/settings",
        "/official",
        "/unesco",
        "/courses",
        "/sources",
        "/comparisons",
        "/learning-history",
        "/data-policy",
        "/install",
        "/pwa/offline",
    ],
)
def test_public_screens_use_reviewed_interface_copy(path, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "copy.db")
    initialize_database()
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        for old in [
            "말투 바꾸기",
            "선호하는 말투",
            "로컬 XML",
            "로컬 공유 모드",
            "익명 브라우저 세션",
        ]:
            assert old not in response.text
        if path in {"/", "/learn"}:
            assert "설명 스타일" not in response.text
            assert "내 관심사와 학습 목표" not in response.text
            assert "함께 알아보기" in response.text
            assert "하십시오" not in response.text
        if path == "/settings":
            assert "설명 스타일" in response.text
            assert "설명 표현" in response.text
            assert "설명의 자세함" in response.text
            assert "설명 문체" not in response.text
            assert "친근하게" in response.text
        if path == "/learning-history":
            assert "앞으로 배우고 싶은 것" in response.text


def test_guidance_changes_preserve_official_quotes_and_record():
    quote = "여기서 멈출게요. 기록은 남겨 두었어요."
    message = ConversationMessage(
        role="assistant",
        text=quote + "\n인용: " + quote + "\n\n공식 원문: " + quote,
        citations=[{"quote": quote}],
    )
    before = message.model_dump_json()
    # All matching citation spans are protected, not only an appended source panel.
    assert message_body(message, LearningPreferences()) == message.text.replace(
        "\n\n공식 원문: " + quote, "", 1
    )
    assert message.model_dump_json() == before


@pytest.mark.parametrize("role,kind", [("user", "dialogue"), ("assistant", "dictionary")])
def test_learner_input_and_dictionary_are_never_rewritten(role, kind):
    text = "어떤 이야기가 궁금한가요? 여기서 멈출게요. 기록은 남겨 두었어요."
    message = ConversationMessage(role=role, kind=kind, text=text)
    assert message_body(message, LearningPreferences()) == text


def test_friendly_guidance_is_preserved_and_only_internal_notice_is_translated():
    message = ConversationMessage(
        role="assistant", text="이어서 살펴볼게요. 지금 궁금한 점을 들려주세요."
    )
    assert message_body(message, LearningPreferences()) == message.text
    assert "살펴볼게요" in message.text
    assert "기본 안내" in service_text(
        "AI 계획을 사용할 수 없어 제한된 안내로 이어가요. 이해도는 자동 평가하지 않아요."
    )


@pytest.mark.parametrize(
    "trace, expected",
    [
        ("target_tool: 선택한 공식 ID 확인·원문 수집", "선택한 유산의 공식 원문 확인"),
        ("scope_check: 해외 문화유산과 비교", "비교 범위 확인"),
        ("supplement_tool: 공식 상세 설명 추가 수집 cached", "보관 자료 확인"),
        ("individual_source_tool: 대안탑 · 유산군과 구분", "개별 유산 자료 확인"),
        ("comparison_tool: 4개 항목 추출", "시대·구조·재료·종교적 배경 찾기"),
        ("future_tool: 추가 근거 확인", "학습 과정: 추가 근거 확인"),
    ],
)
def test_activity_details_do_not_expose_internal_tool_names(trace, expected):
    shown = readable_trace(trace)
    assert expected in shown
    assert "_tool" not in shown
    assert "_agent" not in shown
    assert " ID " not in shown


def test_activity_wording_keeps_search_terms_and_source_titles():
    assert readable_trace("search_tool: UNESCO 'Horyu-ji' → 3건") == (
        "공식 자료 찾기: UNESCO 'Horyu-ji' → 3건"
    )
    assert readable_trace("출처 설명은 그대로") == "출처 설명은 그대로"
