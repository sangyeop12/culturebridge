from culturebridge.services.personalized_explanation_service import ExplanationDraft, valid_draft


def test_rewrite_cannot_turn_estimated_date_into_certainty():
    quote = "탑이 건립된 시기는 통일신라 경덕왕 10년(751)으로 추측된다."

    def draft(text):
        return ExplanationDraft(sentences=[{"text": text, "evidence_quote": quote}])

    assert not valid_draft(draft("이 탑은 751년에 만들어졌어요."), quote)
    assert valid_draft(draft("이 탑은 751년에 세워진 것으로 추측해요."), quote)


def test_safe_diagnostic_never_includes_provider_error_message(monkeypatch):
    import time

    from culturebridge.config import get_settings
    from culturebridge.services import personalized_explanation_service as service
    from culturebridge.services.learning_preferences import LearningPreferences

    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "not-a-real-key")

    class ProviderError(Exception):
        code = 503

    def fail(*args):
        raise ProviderError("secret-token=never-print-this")

    monkeypatch.setattr(service, "_generate", fail)
    _, metadata = service.explain(
        "시대",
        "이 탑은 751년에 세워졌다.",
        LearningPreferences(),
        {"mode": "explain"},
        time.monotonic() + 30,
    )
    assert metadata["failure_kind"] == "provider_unavailable"
    assert "secret" not in str(metadata)
