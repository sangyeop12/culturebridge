from types import SimpleNamespace

import pytest

from culturebridge.config import get_settings
from culturebridge.domain.models import LearningLevel
from culturebridge.services import question_service


@pytest.mark.parametrize("behavior", ["success", "empty", "timeout", "auth"])
def test_gemini_response_status_fallback_and_cleanup(monkeypatch, behavior):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only-key")
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self

        def generate_content(self, **kwargs):
            captured["request"] = kwargs
            if behavior == "timeout":
                raise TimeoutError("test")
            if behavior == "auth":
                raise RuntimeError("test auth rejection")
            return SimpleNamespace(text="AI 비교 초안" if behavior == "success" else "")

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(question_service.genai, "Client", FakeClient)
    result = question_service.answer_question(
        "seokguram", "horyuji", "두 유산의 재료는?", LearningLevel.BEGINNER, use_ai=True
    )
    assert captured["closed"]
    assert captured["http_options"].timeout == 15000
    assert captured["http_options"].retry_options.attempts == 1
    assert "scope_note" in captured["request"]["contents"]
    if behavior == "success":
        assert result.used_ai
        assert result.verification_status.value == "needs_review"
    else:
        assert not result.used_ai
        assert "화강암" in result.answer
        assert "AI 응답을 사용할 수 없어" in result.verification_note


def test_live_check_does_not_call_provider_without_key(monkeypatch, capsys):
    from culturebridge import check_gemini

    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    assert check_gemini.main() == 2
    assert "not_configured" in capsys.readouterr().out


def test_offline_mode_prevents_call_even_with_configured_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)

    def fail(**kwargs):
        pytest.fail("Offline mode must not create a Gemini client")

    monkeypatch.setattr(question_service.genai, "Client", fail)
    result = question_service.answer_question(
        "seokguram", "horyuji", "두 유산의 재료는?", LearningLevel.BEGINNER
    )
    assert result.used_ai is False
