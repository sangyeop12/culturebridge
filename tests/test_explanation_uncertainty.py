import pytest

from culturebridge.services.personalized_explanation_service import (
    ExplanationDraft,
    readable_draft,
    valid_draft,
)


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


@pytest.mark.parametrize(
    "texts,expected",
    [
        (["탑의 아랫부분은 십자 모양이에요.", "네 방향에 돌계단이 있어요."], True),
        (["가" * 66], False),
        (["기단이 있어요. 탑신도 있어요."], False),
        (["짧은 설명이에요."] * 4, False),
    ],
)
def test_easy_explanations_use_short_separate_sentences(texts, expected):
    draft = ExplanationDraft(
        sentences=[{"text": t, "evidence_quote": "충분히 긴 공식 원문입니다."} for t in texts]
    )
    assert readable_draft(draft, detailed=False) is expected
    assert readable_draft(draft, detailed=True) is True


def test_long_easy_rewrite_falls_back_before_another_model_call(monkeypatch):
    import time

    from culturebridge.config import get_settings
    from culturebridge.services import personalized_explanation_service as service
    from culturebridge.services.learning_preferences import LearningPreferences

    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "not-a-real-key")
    calls = []
    quote = "이 석탑의 구조에는 기단과 탑신, 난간이 설명되어 있다."

    def generate(*args):
        calls.append(args)
        return ExplanationDraft(
            sentences=[{"text": "설명이 길어요. " * 9, "evidence_quote": quote}]
        )

    monkeypatch.setattr(service, "_generate", generate)
    _, meta = service.explain(
        "구조", quote, LearningPreferences(), {"mode": "explain"}, time.monotonic() + 30
    )
    assert len(calls) == 1
    assert meta["method"] == "local_guide"
    assert meta["failure_kind"] == "easy_readability_rejected"
