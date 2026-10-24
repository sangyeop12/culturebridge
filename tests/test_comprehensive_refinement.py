"""Regressions from the whole-service audit; synthetic sources and isolated databases only."""

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from culturebridge.agents import learning, workflow
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import ConversationMessage, LearningConversation, LearningTurn
from culturebridge.domain.models import CollectedSource, LearningAmount, LearningGoal, LearningLevel
from culturebridge.services import question_service as questions
from culturebridge.services.adaptive_learning_service import activity_question
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.conversation_source_policy import conversation_ai_allowed
from culturebridge.services.curriculum_service import plan_learning, required_categories
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.operation_service import clear_operation_cache, session_owner
from culturebridge.services.quiz_service import generate_quiz


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "audit.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    monkeypatch.setattr(get_settings(), "public_mode", False)
    initialize_database()
    token = session_owner.set("audit-owner")
    yield
    clear_operation_cache()
    session_owner.reset(token)


@pytest.mark.parametrize("goal", [LearningGoal.RELIGION, LearningGoal.OBSERVE])
def test_short_lesson_keeps_all_explicit_goal_axes(goal):
    text = "재료와 구조, 종교적 배경을 알고 싶어요"
    steps, focus = plan_learning(LearningLevel.BEGINNER, goal, text, LearningAmount.BRIEF)
    assert required_categories(goal.value + " " + text) <= set(focus)
    assert len(focus) == 3 and len(steps) >= 3


def restricted_conversation():
    return LearningConversation(
        id=uuid4(),
        revision=0,
        messages=[
            ConversationMessage(
                role="assistant",
                text="archived restricted material",
                citations=[{"url": "https://example.org/restricted", "quote": "archived secret"}],
            )
        ],
    )


def test_topic_change_preserves_archive_but_releases_new_topic(isolated):
    original = restricted_conversation()
    assert not conversation_ai_allowed(original)
    updated = learning.run_learning_turn(
        original,
        LearningTurn(
            request_id=uuid4(),
            revision=0,
            control="change_topic",
            text="세종",
        ),
    )
    assert conversation_ai_allowed(updated)
    assert updated.messages[0].text == original.messages[0].text
    assert updated.topic_start == 2
    # A restricted citation in the new topic must still block AI use.
    updated.messages.append(original.messages[0])
    assert not conversation_ai_allowed(updated)


def test_new_topic_model_input_does_not_leak_archived_sources(isolated, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "synthetic-test-key")
    c = restricted_conversation()
    c.topic_start = 1
    c.messages.append(ConversationMessage(role="user", text="세종"))
    c.concepts = {
        "재료": {
            "status": "unclear",
            "observations": [
                {"source_id": "old", "judgment": "unclear", "reason": "archived secret"},
            ],
        }
    }
    captured = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            captured.append(kwargs["contents"])
            return SimpleNamespace(text='{"action":"ask","question":"무엇이 궁금한가요?"}')

    monkeypatch.setattr(learning.genai, "Client", Client)
    learning._model_decision(
        {
            "conversation": c,
            "request": SimpleNamespace(text="세종", control="message"),
            "seen": [],
            "deadline": time.monotonic() + 30,
        }
    )
    assert "archived" not in captured[0] and "restricted" not in captured[0]


@pytest.mark.parametrize(
    "text,action",
    [
        ("세종에 대해 알려줘", "search_history"),
        ("경복궁 알려줘", "search"),
        ("더 쉽게 설명해줘", "explain"),
    ],
)
def test_outage_respects_new_question_instead_of_old_source(text, action):
    c = LearningConversation(id=uuid4(), revision=0, sources=[{"id": "old_tower"}])
    decision = learning._fallback(
        {"conversation": c, "request": SimpleNamespace(text=text), "seen": []}
    )
    assert decision.action == action
    if action != "explain":
        assert not decision.source_id


@pytest.mark.parametrize(
    "sentence,quote",
    [
        ("이 탑은 나무로 만들었습니다.", "이 탑의 주요 건축 재료는 돌이다."),
        ("이 탑은 700년에 건립되었습니다.", "이 탑은 800년에 건립되었다."),
        ("이 탑은 700년에 건립되었습니다.", "이 탑은 700년에 건립된 것으로 추정된다."),
    ],
)
def test_exact_quote_does_not_allow_changed_fact(sentence, quote):
    assert not questions.citation_preserves_facts(sentence, quote)


@pytest.mark.parametrize(
    "supported,scope,accepted",
    [
        (True, True, True),
        (False, True, False),
        (True, False, False),
    ],
)
def test_question_requires_independent_semantic_review(supported, scope, accepted):
    quote = "이 탑의 주요 건축 재료는 돌이다."
    responses = iter(
        [
            {
                "citations": [
                    {"sentence": "이 탑은 돌로 만들었어요.", "source_id": "test", "quote": quote}
                ]
            },
            {"supported": supported, "preserves_scope_and_uncertainty": scope, "reason": "test"},
        ]
    )
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(
                text=json.dumps(next(responses), ensure_ascii=False)
            )
        )
    )
    context = {"sources": [{"id": "test", "summary": quote}], "comparison": {}}
    if accepted:
        result = questions._generate_gemini_answer(client, context, "재료는?", ["test"])
        assert result.used_ai and result.verification_status.value == "needs_review"
    else:
        with pytest.raises(ValueError, match="semantic"):
            questions._generate_gemini_answer(client, context, "재료는?", ["test"])


def sample_sources():
    return [
        CollectedSource(
            id="fixture:" + identity,
            heritage_id=identity,
            title=identity,
            organization="Synthetic official source",
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


def test_exploration_reuses_comparison_and_quiz_after_request_cache_clear(isolated):
    state = {
        "heritage_id": "seokguram",
        "comparison_id": "horyuji",
        "level": "beginner",
        "goal": "compare",
        "goal_text": "",
        "amount": "standard",
        "curriculum": [],
        "collected_sources": [s.model_dump(mode="json") for s in sample_sources()],
        "extracted_fields": [],
        "verification_note": "",
        "missing_heritages": [],
        "execution_trace": [],
    }
    # Use real persisted comparisons; explicit new-analysis saves remain available separately.
    first = workflow.build_comparison(state)["comparison"]
    clear_operation_cache()
    assert workflow.build_comparison(state)["comparison"]["saved_id"] == first["saved_id"]
    sources = sample_sources()
    fields = extract_fields(sources, ["seokguram", "horyuji"])
    comp = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=fields,
        reuse=True,
    )
    quiz = generate_quiz(
        "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comp.saved_id, reuse=True
    )
    clear_operation_cache()
    assert (
        generate_quiz(
            "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comp.saved_id, reuse=True
        ).quiz_id
        == quiz.quiz_id
    )
    with transaction() as connection:
        assert (
            connection.execute("SELECT count(DISTINCT quiz_id) FROM quiz_items").fetchone()[0] == 1
        )
    later = [
        s.model_copy(update={"retrieved_at": s.retrieved_at + timedelta(hours=1)}) for s in sources
    ]
    assert (
        create_saved_comparison(
            "seokguram",
            "horyuji",
            LearningLevel.BEGINNER,
            collected_sources=later,
            extracted_fields=fields,
            reuse=True,
        ).saved_id
        == comp.saved_id
    )


def test_remediation_modes_and_source_anchors_are_distinct():
    quote = "이 탑은 화강암으로 만들었다."
    questions = {
        activity_question("재료", {"mode": mode}, i, quote)
        for mode in ("scaffold", "contrast", "remediate", "deepen")
        for i in range(3)
    }
    assert len(questions) == 12
    assert all(quote in question for question in questions)


def test_personalized_course_order_respects_opt_out(isolated, monkeypatch):
    from culturebridge.services import learning_path_service as paths
    from culturebridge.services.learning_intent_service import LearningIntent

    courses = [{"id": "palace", "title": "궁전"}, {"id": "tower", "title": "탑과 재료"}]
    monkeypatch.setattr(
        paths,
        "get_learning_intent",
        lambda: LearningIntent(
            interests=["탑"],
            use_for_planning=True,
            infer_from_dialogue=False,
        ),
    )
    ordered, matched = paths.personalized_courses(courses)
    assert matched and ordered[0]["id"] == "tower"
    monkeypatch.setattr(
        paths,
        "get_learning_intent",
        lambda: LearningIntent(
            interests=["탑"],
            use_for_planning=False,
            infer_from_dialogue=False,
        ),
    )
    ordered, matched = paths.personalized_courses(courses)
    assert not matched and ordered == courses
