from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, load_quiz_items
from culturebridge.domain.models import (
    CollectedSource,
    ExtractedField,
    LearningLevel,
    VerificationStatus,
)
from culturebridge.main import app
from culturebridge.services.comparison_service import create_saved_comparison, get_saved_comparison
from culturebridge.services.evidence_quiz_service import EvidenceQuizError
from culturebridge.services.quiz_service import generate_quiz, grade_quiz


@pytest.fixture
def comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "evidence.db")
    initialize_database()
    source = CollectedSource(
        id="test-material",
        heritage_id="seokguram",
        title="Test official source",
        organization="Test",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        status="cached",
        content_kind="individual_text",
        content="Test source states granite.",
        retrieved_at=datetime.now(UTC),
        scope_note="Test individual evidence",
    )
    field = ExtractedField(
        heritage_id="seokguram",
        category="재료",
        value="시험용 화강암 후보",
        source_id=source.id,
        evidence_quote=source.content,
        source_url=source.source_url,
        verification_status=VerificationStatus.NEEDS_REVIEW,
        method="gemini",
        note="Test candidate",
    )
    return create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=[source],
        extracted_fields=[field],
    )


def test_extracted_comparison_uses_candidate_and_never_fills_gaps(comparison):
    assert comparison.basis == "extracted"
    material = next(p for p in comparison.differences if p.category == "재료")
    assert material.left == "시험용 화강암 후보" and material.right == "근거 부족"
    assert material.source_ids == ["test-material"]
    assert comparison.source_ids == ["test-material"]
    assert comparison.verification_status is VerificationStatus.NEEDS_REVIEW
    saved = get_saved_comparison(comparison.saved_id)
    assert saved.sources[0].id == "test-material"
    assert saved.comparison == comparison


@pytest.mark.parametrize("level", list(LearningLevel))
def test_evidence_quiz_all_levels_grading_provenance_and_no_answer_leak(comparison, level):
    quiz = generate_quiz("seokguram", "horyuji", level, comparison_id=comparison.saved_id)
    assert quiz.basis == "extracted" and quiz.comparison_id == comparison.saved_id
    assert quiz.verification_status is VerificationStatus.NEEDS_REVIEW
    assert len(quiz.items) == 5
    assert all(len({c.text for c in item.choices}) == 4 for item in quiz.items)
    assert all("correct_index" not in item.model_dump() for item in quiz.items)
    rows = load_quiz_items(quiz.quiz_id)
    assert all(row["comparison_id"] == comparison.saved_id for row in rows)
    answers = [row["correct_index"] for row in rows]
    grade = grade_quiz(quiz.quiz_id, answers)
    assert grade.score == grade.total == 5
    assert grade.evidence[0].evidence_quote == "Test source states granite."


def test_quiz_does_not_mix_comparison_targets(comparison):
    with pytest.raises(EvidenceQuizError):
        generate_quiz(
            "horyuji", "seokguram", LearningLevel.BEGINNER, comparison_id=comparison.saved_id
        )


def test_no_evidence_cannot_generate_quiz(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "empty.db")
    initialize_database()
    empty = create_saved_comparison(
        "seokguram", "horyuji", LearningLevel.BEGINNER, extracted_fields=[]
    )
    assert empty.verification_status is VerificationStatus.INSUFFICIENT_EVIDENCE
    response = TestClient(app).post(
        "/api/quizzes",
        json={"left_id": "seokguram", "right_id": "horyuji", "comparison_id": empty.saved_id},
    )
    assert response.status_code == 422


def test_ui_quiz_link_and_return_keep_saved_snapshot(comparison):
    with TestClient(app) as client:
        page = client.get(f"/compare/seokguram/horyuji?saved_id={comparison.saved_id}")
        assert page.status_code == 200 and "공식 원문과 상세 설명" in page.text
        assert "설명의 뜻과 대상은 추가 확인이 필요" not in page.text
        quiz_page = client.get(f"/quiz/seokguram/horyuji?comparison_id={comparison.saved_id}")
        assert quiz_page.status_code == 200 and "설명의 뜻은 원문과 함께 더 확인" in quiz_page.text
