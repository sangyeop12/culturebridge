from datetime import UTC, datetime

import pytest

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.models import (
    CollectedSource,
    ExtractedField,
    LearningAmount,
    LearningGoal,
    LearningLevel,
    VerificationStatus,
)
from culturebridge.services import quiz_draft_service as draft_service
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.curriculum_service import plan_learning
from culturebridge.services.quiz_service import generate_quiz, grade_quiz


@pytest.fixture
def comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "connections.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    source = CollectedSource(
        id="test",
        heritage_id="seokguram",
        title="Test",
        organization="Test",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        content="This is a Buddhist grotto built from granite.",
        content_kind="individual_text",
        status="fresh",
        retrieved_at=datetime.now(UTC),
        scope_note="Test",
    )
    field = ExtractedField(
        heritage_id="seokguram",
        category="종교적 배경",
        value="불교",
        source_id=source.id,
        source_url=source.source_url,
        evidence_quote=source.content,
        verification_status=VerificationStatus.NEEDS_REVIEW,
        note="Test",
    )
    return create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=[source],
        extracted_fields=[field],
        goal=LearningGoal.RELIGION,
        amount=LearningAmount.BRIEF,
    )


def valid_draft(comparison):
    return draft_service.QuizDraft(
        items=[
            draft_service.QuizDraftItem(
                question=f"자료 후보에 따르면 {comparison.left.name}의 종교적 배경은? ({i + 1})",
                choices=["불교", "산업화", "군사 시설", "농업"],
                correct_index=0,
                evidence_index=0,
                explanation="원문 자료에서 불교 표현을 찾았습니다.",
            )
            for i in range(5)
        ]
    )


def test_validated_gemini_questions_are_saved_and_graded(comparison, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(draft_service, "_generate", lambda *args: valid_draft(comparison))
    quiz = generate_quiz(
        "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comparison.saved_id
    )
    assert "Gemini 초안" in quiz.learning_goal
    assert len(quiz.items) == 5
    assert all("종교적 배경" in item.question for item in quiz.items)
    assert "correct_index" not in quiz.model_dump_json()
    grade = grade_quiz(quiz.quiz_id, [item.correct_index for item in quiz.items])
    assert grade.score == 5 and grade.evidence


@pytest.mark.parametrize(
    "defect", ["answer", "duplicate", "source", "target", "length", "multiple"]
)
def test_invalid_generated_question_falls_back(comparison, monkeypatch, defect):
    draft = valid_draft(comparison)
    if defect == "answer":
        draft.items[0].correct_index = 1
    elif defect == "duplicate":
        draft.items[0].choices[1] = "불교"
    elif defect == "source":
        draft.items[0].evidence_index = 9
    elif defect == "target":
        draft.items[0].question = "다른 유산은 무엇인가요?"
    elif defect == "multiple":
        draft.items[0].choices[1] = comparison.extracted_fields[0].evidence_quote
    else:
        draft.items[0].choices[1] = "가" * 121
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(draft_service, "_generate", lambda *args: draft)
    quiz = generate_quiz(
        "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comparison.saved_id
    )
    assert "검사 실패" in quiz.learning_goal
    assert len(quiz.items) == 5 and "종교적 배경" in quiz.items[0].question


@pytest.mark.parametrize("level", list(LearningLevel))
def test_learning_amount_changes_plan_and_preserves_quiz(level):
    brief, brief_focus = plan_learning(level, LearningGoal.COMPARE, amount=LearningAmount.BRIEF)
    deep, deep_focus = plan_learning(level, LearningGoal.COMPARE, amount=LearningAmount.DEEP)
    assert len(brief_focus) == 2 and len(deep_focus) == 4
    assert len(brief) < len(deep) and "5문항" in brief[-1] and "5문항" in deep[-1]


def test_comparison_prioritizes_goal_and_reports_missing_goal_evidence(comparison):
    assert comparison.differences[0].category == "종교적 배경"
    assert comparison.amount is LearningAmount.BRIEF
    assert any("종교적 배경" in notice for notice in comparison.learning_notices)


def test_environment_report_checks_lock_without_exposing_keys(tmp_path, monkeypatch):
    from importlib.metadata import version

    from culturebridge import check_environment

    lock = tmp_path / "requirements.txt"
    lock.write_text(f"pytest=={version('pytest')}\n", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "secret-not-for-output")
    report = check_environment.environment_report(lock)
    assert report["status"] == "ok"
    assert "secret-not-for-output" not in str(report)
    lock.write_text("pytest==0.0.0\n", encoding="utf-8")
    assert check_environment.environment_report(lock)["status"] == "mismatch"


def test_quota_error_has_safe_fallback_notice(comparison, monkeypatch):
    from google.genai.errors import ClientError

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)

    def limited(*args):
        raise ClientError(429, {"error": {"message": "private-diagnostic"}})

    monkeypatch.setattr(draft_service, "_generate", limited)
    quiz = generate_quiz(
        "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comparison.saved_id
    )
    assert "429" in quiz.learning_goal
    assert "private-diagnostic" not in quiz.learning_goal
    assert len(quiz.items) == 5


def test_ai_quiz_page_returns_loading_before_remote_generation(comparison, monkeypatch):
    from fastapi.testclient import TestClient

    from culturebridge.main import app
    from culturebridge.ui import pages

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)

    def fail(*args, **kwargs):
        pytest.fail("AI generation must wait for browser connection")

    monkeypatch.setattr(pages, "generate_quiz", fail)
    with TestClient(app) as client:
        response = client.get(f"/quiz/seokguram/horyuji?comparison_id={comparison.saved_id}")
    assert response.status_code == 200
    assert "퀴즈를 준비하고 있습니다" in response.text
