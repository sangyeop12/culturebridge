"""Regression checks for issues found by the simulated learner walkthrough."""

from datetime import UTC, datetime

import pytest

from culturebridge.config import get_settings
from culturebridge.data.material_review import SCOPE_NOTES
from culturebridge.data.source_audit import NAME_FINDINGS
from culturebridge.database import initialize_database
from culturebridge.domain.models import CollectedSource
from culturebridge.services.classroom_quiz_service import _period, classroom_rows
from culturebridge.services.extraction_service import (
    DraftField,
    _local_extraction,
    validate_extraction,
)
from culturebridge.services.learning_analysis_service import comparison_explanation
from culturebridge.services.material_review_service import material_review
from culturebridge.services.subject_service import focused_text


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "audit.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()


def source(title, content, identity="fixture"):
    return CollectedSource(
        id=identity,
        heritage_id=identity,
        title=title,
        organization="Synthetic fixture",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        content_kind="individual_text",
        status="fresh",
        content=content,
        scope_note="Synthetic fixture, not historical evidence",
    )


def test_exactly_25_desk_findings_never_become_a_permission():
    assert set(NAME_FINDINGS) == set(SCOPE_NOTES)
    rows = material_review()
    assert len(rows) == 25
    for row in rows:
        assert row["name_finding"] and row["desk_review_date"] == "2026-10-17"
        assert "미확인" in row["ai_permission"]
        assert row["usage_status"] == "pending"
        assert row["name_status"] == "guidance"
    xian = next(row for row in rows if row["id"] == "official:dayanta")
    assert xian["policy_status"] == "not_established"


def test_concrete_roof_is_preferred_over_a_hall_introduction():
    s = source("Great Hall", "The hall was built in 1511. Its wooden roof is well preserved.")
    field = next(f for f in _local_extraction([s]) if f.category == "구조")
    assert field.evidence_quote == "Its wooden roof is well preserved."


def test_tomb_material_does_not_come_from_entrance_towers():
    s = source(
        "Example Mausoleum",
        "Three other smaller gateways have red sandstone towers. "
        "The inner main structure is brick covered with marble, "
        "whereas adjoining structures are sandstone. "
        "The white marble gives this mausoleum its appearance.",
    )
    draft = DraftField(
        heritage_id=s.id,
        source_id=s.id,
        category="재료",
        value="sandstone",
        evidence_quote="Three other smaller gateways have red sandstone towers.",
    )
    assert validate_extraction(draft, [s]) is None
    assert next(f for f in _local_extraction([s]) if f.category == "재료").evidence_quote.endswith(
        "appearance."
    )


def test_a_hill_location_is_not_a_different_named_tomb():
    s = source("예시 왕릉", "서쪽 구릉의 동사면에 놓인 원분 가운데 가장 아래에 위치한다.")
    assert "원분" in focused_text(s)
    assert next(f for f in _local_extraction([s]) if f.category == "구조")


def test_material_comparison_keeps_the_used_part_visible():
    left = source("Example Palace", "The carvings are made of wood.", "left")
    right = source("Other Palace", "The palace is made of marble.", "right")
    fields = [
        next(validate_extraction(f, [s]) for f in _local_extraction([s]) if f.category == "재료")
        for s in (left, right)
    ]
    text = comparison_explanation("재료", *fields)
    assert "조각·장식" in text and "일반화하지" in text
    assert "돌와" not in text and "대리석로" not in text


@pytest.mark.parametrize(
    "quote,answer",
    [
        ("Built in the 13th century.", "13세기"),
        ("The hall was built between 1093 and 1133.", "1093~1133년"),
        ("Built in about 2500 BC.", "기원전 약 2500년"),
        ("Built in 2500 BC.", "기원전 2500년"),
    ],
)
def test_periods_do_not_mix_centuries_ranges_or_bce(quote, answer):
    result = _period(quote)
    assert (result[0] if result else None) == answer


@pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
def test_four_short_content_questions_and_one_level_specific_task(level):
    sources = [
        source("Left Hall", "The wooden roof has arches.", "left"),
        source("Right Hall", "The marble ceiling has vaults.", "right"),
    ]
    fields = [validate_extraction(f, [s]) for s in sources for f in _local_extraction([s])]
    fields = [f for f in fields if f]
    rows = classroom_rows(
        fields, ["구조", "재료"], {"left": "왼쪽", "right": "오른쪽"}, "left", "right", level
    )
    assert len(rows) == 5
    assert len({q for q, _, _ in rows}) == 5
    assert all(len(set(choices)) == 4 for _, choices, _ in rows)
    assert max(len(choice) for _, choices, _ in rows for choice in choices) < 80
    if level == "advanced":
        assert "확정할 수 없는" in rows[-1][0]
    elif level == "intermediate":
        assert "확인할 기준" in rows[-1][0]
    else:
        assert "문화유산과 설명" in rows[-1][0]


def test_negative_year_is_not_a_positive_date_question():
    assert _period("It was not built in 1709.") is None


def test_other_passage_material_is_not_used_as_an_incorrect_choice():
    s = source("Example Palace", "The palace has marble walls. It also uses brick.", "left")
    fields = [validate_extraction(f, [s]) for f in _local_extraction([s])]
    rows = classroom_rows(
        [f for f in fields if f], ["재료"], {"left": "궁전"}, "left", "right", sources=[s]
    )
    assert rows[0][1][0] == "대리석"
    assert "벽돌" not in rows[0][1][1:]


def test_round_mound_does_not_have_round_shape_as_a_false_choice():
    s = source("예시 왕릉", "원분 가운데 아래에 위치한다.", "left")
    fields = [validate_extraction(f, [s]) for f in _local_extraction([s])]
    rows = classroom_rows([f for f in fields if f], ["구조"], {"left": "왕릉"}, "left", "right")
    assert rows and rows[0][1][0] == "둥근 봉분"
    assert "둥근 모양" not in rows[0][1][1:]


def test_new_reading_axes_do_not_crash_legacy_quiz_fallback():
    from culturebridge.domain.models import LearningGoal, LearningLevel
    from culturebridge.services.comparison_service import create_saved_comparison
    from culturebridge.services.extraction_service import extract_fields
    from culturebridge.services.quiz_service import generate_quiz

    sources = [
        source("가상 전각", "목조 건물입니다.", "seokguram"),
        source("Other Hall", "It has stained glass windows. It has granite walls.", "horyuji"),
    ]
    comp = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=extract_fields(sources, ["seokguram", "horyuji"]),
        goal=LearningGoal.OBSERVE,
    )
    quiz = generate_quiz("seokguram", "horyuji", comp.level, comparison_id=comp.saved_id)
    assert len(quiz.items) == 5
    assert len({item.question for item in quiz.items}) == 5


def test_simulated_audit_refuses_enabled_external_ai(monkeypatch):
    from culturebridge.audit_learning import audit_courses

    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    with pytest.raises(ValueError, match="비활성화"):
        audit_courses()
