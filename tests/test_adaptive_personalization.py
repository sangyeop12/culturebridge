import time
from uuid import uuid4

import pytest

from culturebridge.config import get_settings
from culturebridge.domain.learning import ConversationMessage, LearningConversation
from culturebridge.services import personalized_explanation_service as personal
from culturebridge.services import understanding_assessment_service as assessment
from culturebridge.services.adaptive_learning_service import activity_question, teaching_route
from culturebridge.services.conversation_source_policy import conversation_ai_allowed, url_allowed
from culturebridge.services.learning_preferences import LearningPreferences

QUOTE = "이 석탑은 화강암으로 만든 탑이며 751년에 건립되었다."
SOURCE = {
    "id": "khs:test",
    "url": "https://www.khs.go.kr/",
    "excerpts": [{"concept": "재료", "quote": QUOTE}],
}


def state(judgments=(), source_id="khs:test"):
    return LearningConversation(
        id=uuid4(),
        revision=0,
        sources=[SOURCE],
        concepts={
            "재료": {
                "status": "tentative_support",
                "observations": [
                    {
                        "source_id": source_id,
                        "quote": QUOTE,
                        "judgment": j,
                        "learner_text": f"자기 말로 설명한 서로 다른 문장 {i}",
                    }
                    for i, j in enumerate(judgments)
                ],
            }
        },
    )


@pytest.mark.parametrize(
    "judgments,expected",
    [
        ([], "explain"),
        (["unclear"], "scaffold"),
        (["possible_misconception"], "remediate"),
        (["possible_misconception"] * 2, "contrast"),
        (["tentative_support"], "explain"),
        (["tentative_support"] * 2, "deepen"),
    ],
)
def test_multiple_evidence_not_single_score_selects_branch(judgments, expected):
    assert teaching_route(state(judgments), SOURCE, "재료")["mode"] == expected


def test_scope_latest_negative_and_current_request_override():
    assert (
        teaching_route(state(["tentative_support"] * 2, "other"), SOURCE, "재료")["mode"]
        == "explain"
    )
    s = state(["tentative_support", "tentative_support", "possible_misconception"])
    assert teaching_route(s, SOURCE, "재료")["mode"] == "remediate"
    assert teaching_route(s, SOURCE, "재료", "쉽게 설명해줘")["mode"] == "scaffold"
    assert teaching_route(s, SOURCE, "재료", "다른 문제")["mode"] == "alternate_question"


def test_repeating_same_answer_does_not_unlock_deeper_branch():
    s = state(["tentative_support"] * 2)
    s.concepts["재료"]["observations"][1]["learner_text"] = s.concepts["재료"]["observations"][0][
        "learner_text"
    ]
    assert teaching_route(s, SOURCE, "재료")["mode"] == "explain"


def test_disputed_observations_do_not_promote_after_reassessment():
    s = state(["tentative_support"] * 2)
    s.concepts["재료"]["status"] = "disputed_by_learner"
    assert teaching_route(s, SOURCE, "재료")["mode"] == "explain"
    s.concepts["재료"]["status"] = "tentative_support"
    s.concepts["재료"]["observations"][0]["disputed_by_learner"] = True
    assert teaching_route(s, SOURCE, "재료")["mode"] == "explain"


def test_repetition_changes_activity_and_rotates_question():
    s = state()
    s.plan_history = [{"action": "explain", "source_id": SOURCE["id"], "concept": "재료"}] * 2
    route = teaching_route(s, SOURCE, "재료")
    assert route["mode"] == "alternate_question"
    assert activity_question("재료", route, 0) != activity_question("재료", route, 1)


def test_local_style_and_depth_no_model_calls():
    route = {"mode": "deepen"}
    text, meta = personal.explain(
        "재료", QUOTE, LearningPreferences(tone="polite"), route, time.monotonic() + 5
    )
    assert "습니다" in text or "입니다" in text
    assert "사용한 부분" in text
    assert meta["method"] == "local_guide"
    easy, _ = personal.explain(
        "재료", QUOTE, LearningPreferences(explanation_depth="easy"), route, time.monotonic() + 5
    )
    assert len(easy) < len(text)


def test_rewrite_independently_checked_and_quotation_unchanged(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "mock-key")
    values = iter(
        [
            personal.ExplanationDraft(
                sentences=[
                    personal.SupportedSentence(
                        text="이 탑은 화강암으로 만들었어요.", evidence_quote=QUOTE
                    )
                ]
            ),
            personal.ExplanationReview(
                supported=True, preserves_scope_and_uncertainty=True, reason="원문과 일치"
            ),
        ]
    )
    monkeypatch.setattr(personal, "_generate", lambda *a: next(values))
    text, meta = personal.explain(
        "재료", QUOTE, LearningPreferences(), {"mode": "explain"}, time.monotonic() + 10
    )
    assert text == "이 탑은 화강암으로 만들었어요."
    assert meta["sentences"][0]["evidence_quote"] == QUOTE
    assert meta["method"] == "gemini_grounded_rewrite"


@pytest.mark.parametrize(
    "candidate,span,reviewed",
    [
        ("이 탑은 2026년에 만들어졌다.", QUOTE, True),
        ("이 탑은 목재로 만들었다.", QUOTE, False),
        ("화강암으로 만들었다.", "존재하지 않는 인용 근거", True),
    ],
)
def test_bad_rewrite_falls_back(monkeypatch, candidate, span, reviewed):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "mock-key")
    values = iter(
        [
            personal.ExplanationDraft(
                sentences=[personal.SupportedSentence(text=candidate, evidence_quote=span)]
            ),
            personal.ExplanationReview(
                supported=reviewed, preserves_scope_and_uncertainty=reviewed, reason="검토"
            ),
        ]
    )
    monkeypatch.setattr(personal, "_generate", lambda *a: next(values))
    text, meta = personal.explain(
        "재료", QUOTE, LearningPreferences(), {"mode": "explain"}, time.monotonic() + 10
    )
    assert meta["method"] == "local_guide" and candidate != text


def test_unapproved_archive_sources_never_enter_planner_context():
    s = state()
    assert conversation_ai_allowed(s)
    s.messages.append(
        ConversationMessage(
            role="assistant",
            text="이전 원문",
            citations=[{"url": "https://unapproved.example.org/heritage", "quote": "원문"}],
        )
    )
    assert not conversation_ai_allowed(s)
    assert not url_allowed("https://www.khs.go.kr.evil.example.org/")
    assert not url_allowed("https://user@evil.example.org/khs.go.kr")


def test_source_permissions_override_ai_available(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "mock-key")
    monkeypatch.setattr(
        personal, "_generate", lambda *a: pytest.fail("Must not send restricted text")
    )
    _, meta = personal.explain(
        "재료",
        QUOTE,
        LearningPreferences(),
        {"mode": "explain"},
        time.monotonic() + 10,
        allow_ai=False,
    )
    assert meta["method"] == "local_guide"


@pytest.mark.parametrize(
    "judgment,action",
    [("tentative_support", "check"), ("possible_misconception", "review"), ("none", "check")],
)
def test_separate_assessment_uses_trusted_checkpoint_not_model_ids(monkeypatch, judgment, action):
    from culturebridge.domain.learning import LearningTurn

    conversation = state()
    conversation.checkpoint = {"source_id": SOURCE["id"], "concept": "재료", "quote": QUOTE}
    monkeypatch.setattr(
        assessment,
        "_generate",
        lambda *a: assessment.UnderstandingAssessment(
            relevant=True,
            judgment=judgment,
            evidence_quote=QUOTE if judgment != "none" else "",
            reason="원문과 학습자의 설명 대조",
        ),
    )
    decision = assessment.assessment_decision(
        {
            "conversation": conversation,
            "request": LearningTurn(
                request_id=uuid4(), revision=0, text="원문에서 화강암이라고 했기 때문이에요"
            ),
            "deadline": time.monotonic() + 10,
        }
    )
    assert decision.source_id == SOURCE["id"] and decision.concept == "재료"
    assert decision.action == action


def test_separate_assessment_rejects_user_answer_as_original(monkeypatch):
    from culturebridge.domain.learning import LearningTurn

    conversation = state()
    conversation.checkpoint = {"source_id": SOURCE["id"], "concept": "재료", "quote": QUOTE}
    monkeypatch.setattr(
        assessment,
        "_generate",
        lambda *a: assessment.UnderstandingAssessment(
            relevant=True,
            judgment="tentative_support",
            evidence_quote="내가 생각하기에 나무로 만든 탑이다",
            reason="유효하지 않은 원문 인용",
        ),
    )
    with pytest.raises(ValueError, match="assessment_quote_not_supported"):
        assessment.assessment_decision(
            {
                "conversation": conversation,
                "request": LearningTurn(
                    request_id=uuid4(), revision=0, text="나무로 만든 탑이라고 생각해요"
                ),
                "deadline": time.monotonic() + 10,
            }
        )
