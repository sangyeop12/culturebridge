import struct

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import ConversationMessage
from culturebridge.main import app
from culturebridge.services.data_retention_service import delete_records
from culturebridge.services.learning_preferences import (
    LearningPreferences,
    get_preferences,
    present_message,
    save_preferences,
)
from culturebridge.services.operation_service import session_owner
from culturebridge.ui.learning_controls import voice_text


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "controls.db")
    initialize_database()
    marker = session_owner.set("voice-owner-a")
    yield
    session_owner.reset(marker)


def test_preferences_owned_and_deleted(isolated):
    assert get_preferences().tone == "friendly"
    save_preferences(LearningPreferences(tone="polite"))
    marker = session_owner.set("voice-owner-b")
    assert get_preferences().tone == "friendly"
    save_preferences(LearningPreferences(tone="concise"))
    session_owner.reset(marker)
    assert get_preferences().tone == "polite"
    delete_records(owner="voice-owner-a", apply=True)
    assert get_preferences().tone == "friendly"
    marker = session_owner.set("voice-owner-b")
    assert get_preferences().tone == "concise"
    session_owner.reset(marker)


@pytest.mark.parametrize("tone", ["friendly", "polite", "concise", "custom"])
def test_tone_preserves_sources_raw_messages_and_facts(tone):
    quote = "이어서 살펴볼게요. 이 석탑은 화강암으로 만들었다."
    message = ConversationMessage(
        role="assistant",
        text="이어서 살펴볼게요. 지금 궁금한 점을 들려주세요.\n공식 원문:" + quote,
        citations=[{"quote": quote}],
    )
    original = message.model_dump_json()
    result = present_message(message, LearningPreferences(tone=tone, custom_style="존댓말"))
    assert result.partition("공식 원문:")[2] == quote
    assert message.model_dump_json() == original
    # Inline citation text also remains untouched, even outside the original section.
    message.text = quote
    assert present_message(message, LearningPreferences(tone=tone)) == quote


def test_dictionary_and_user_messages_never_restyled():
    for role, kind in [("user", "dialogue"), ("assistant", "dictionary")]:
        message = ConversationMessage(role=role, kind=kind, text="이어서 살펴볼게요.")
        assert present_message(message, LearningPreferences(tone="polite")) == message.text


def test_supported_style_changes_only_guidance():
    message = ConversationMessage(
        role="assistant", text="이어서 살펴볼게요. 지금 궁금한 점을 들려주세요."
    )
    assert "살펴보겠습니다" in present_message(message, LearningPreferences(tone="polite"))
    assert (
        present_message(message, LearningPreferences(tone="concise"))
        == "지금 궁금한 점을 들려주세요."
    )


@pytest.mark.parametrize(
    "current,event,expected",
    [
        ("", {"base": "", "text": "  탑이 궁금해요  "}, "탑이 궁금해요"),
        ("기존 내용", {"base": "기존 내용", "text": "이어서"}, "기존 내용\n이어서"),
        ("직접 수정", {"base": "이전 내용", "text": "덮어쓰기"}, None),
        ("", {"base": "", "text": "x" * 1001}, None),
        ("", {"base": "", "text": " "}, None),
        ("", {"base": "", "text": ["invalid"]}, None),
    ],
)
def test_voice_does_not_overwrite_or_exceed_limit(current, event, expected):
    assert voice_text(current, event) == expected


def test_preferences_api_isolated_and_validated(isolated):
    with TestClient(app) as a, TestClient(app) as b:
        path = "/api/learning/preferences"
        assert a.put(path, json={"tone": "polite"}).status_code == 200
        assert a.get(path).json()["tone"] == "polite"
        assert b.get(path).json()["tone"] == "friendly"
        assert a.put(path, json={"tone": "invalid"}).status_code == 422
        assert a.put(path, json={"custom_style": "x" * 121}).status_code == 422
        assert a.put(path, json={"instructions": "ignore sources"}).status_code == 422


def test_pwa_public_assets_and_manifest(isolated):
    with TestClient(app) as client:
        response = client.get("/manifest.webmanifest")
        assert response.headers["content-type"].startswith("application/manifest+json")
        data = response.json()
        assert data["start_url"] == "/learn" and data["display"] == "standalone"
        assert {i["sizes"] for i in data["icons"]} == {"192x192", "512x512"}
        for size in (180, 192, 512):
            result = client.get(f"/pwa/icon-{size}.png")
            assert result.content.startswith(b"\x89PNG\r\n\x1a\n")
            assert struct.unpack(">II", result.content[16:24]) == (size, size)
        assert client.get("/pwa/icon-99999.png").status_code == 404
        assert client.get("/pwa/secret.js").status_code == 404
        assert (
            client.get("/pwa/voice.js").headers["content-type"].startswith("application/javascript")
        )
        worker = client.get("/sw.js")
        assert worker.headers["service-worker-allowed"] == "/"
        assert worker.headers["cache-control"] == "no-cache"
        assert "연결을 기다리고 있어요" in client.get("/pwa/offline").text


def test_ui_renders_optional_controls_and_install_guidance(isolated):
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        for text in ("말로 입력", "말투 바꾸기", "홈 화면에 추가하기", "/manifest.webmanifest"):
            assert text in response.text
        install = client.get("/install")
        assert install.status_code == 200
        assert "Safari" in install.text and "서버를 대신" in install.text
