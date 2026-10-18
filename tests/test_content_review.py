from datetime import UTC, datetime

import pytest

from culturebridge.domain.models import CollectedSource, ExtractedField
from culturebridge.services.classroom_quiz_service import _period, classroom_rows
from culturebridge.services.date_reading_service import read_period
from culturebridge.services.evidence_reading_service import material_scope, reading_units
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.learning_analysis_service import comparison_explanation
from culturebridge.services.lesson_service import beginner_text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The chapel was built around 1130.", "약 1130년"),
        ("The cathedral was built between 1093 and 1133.", "1093~1133년"),
        ("It was built between 1078-1100.", "1078~1100년"),
        ("The tower was built in the late 13th century.", "13세기 후반"),
        ("It was built in the middle of the 13th century.", "13세기 중엽"),
        ("기원전 3세기에 건립되었다.", "기원전 3세기"),
        ("1768년에 완공되었다.", "1768년"),
        ("1093년부터 1133년 사이에 건립되었다.", "1093~1133년"),
    ],
)
def test_period_readings_preserve_original_precision(text, expected):
    assert read_period(text).text == expected
    assert _period(text)[0] == expected
    assert expected in beginner_text("시대", text)
    assert len(set(_period(text))) == 4


@pytest.mark.parametrize(
    "text",
    [
        "It was built in several stages: 5000 years ago and in 2500 BC.",
        "The chapel was built in 1130 and restored in 1845.",
        "히메지성은 600년 전에 지어졌습니다.",
        "It was not built in 1709.",
    ],
)
def test_multi_event_relative_and_negative_dates_are_not_exact_quiz_answers(text):
    assert read_period(text) is None
    assert _period(text) is None


def field(identity, category, quote):
    return ExtractedField(
        heritage_id=identity,
        category=category,
        value=quote,
        evidence_quote=quote,
        date_event="건립·창건",
        note="Synthetic regression fixture",
    )


def test_approximate_date_comparison_does_not_compute_an_exact_gap():
    left = field("left", "시대", "The chapel was built around 1130.")
    right = field("right", "시대", "The hall was built in 1230.")
    text = comparison_explanation("시대", left, right)
    assert "정확한 건립연도 차이로 계산하지" in text
    assert "100년" not in text


def test_gold_leaf_is_a_surface_finish_not_the_buildings_bulk_material():
    assert material_scope("금박으로 덮인 3층 누각입니다.") == "표면 마감"
    assert reading_units("재료", "금박으로 덮인 3층 누각입니다.") == [("재료", "얇게 편 금")]
    assert "표면 마감" in beginner_text("재료", "금박으로 덮인 3층 누각입니다.")


def test_positive_wood_columns_are_kept_when_nails_are_negated_in_another_clause():
    quote = "목재 기둥이 받치는 13m 높이 구조물로서, 못을 전혀 사용하지 않고 지었습니다."
    assert ("재료", "나무") in reading_units("재료", quote)
    assert "나무" in beginner_text("재료", quote)
    assert not reading_units("재료", "목재를 전혀 사용하지 않고 지었습니다.")


def test_concrete_parts_precede_parent_building_names_in_beginner_guides():
    guide = beginner_text("구조", "The palace has a roof with a balustrade and a courtyard.")
    assert "지붕" in guide and "난간" in guide
    assert "궁전이 설명" not in guide


def test_christian_relics_are_read_as_context_not_chronological_bc():
    text = "The chapel was built to house relics of the Passion of Christ and the True Cross."
    source = CollectedSource(
        id="test",
        heritage_id="test",
        title="Example Chapel",
        organization="Synthetic",
        source_url="https://example.org/",
        feed_url="https://example.org/",
        content=text,
        content_kind="individual_text",
        status="fresh",
        retrieved_at=datetime.now(UTC),
        scope_note="Synthetic educational fixture",
    )
    drafts = [d for d in _local_extraction([source]) if d.category == "종교적 배경"]
    assert drafts and validate_extraction(drafts[0], [source])
    assert ("종교", "기독교") in reading_units("종교적 배경", text)
    assert not reading_units("종교적 배경", "It was built 200 years before Christ.")


def test_advanced_quiz_keeps_three_content_questions_and_one_interpretation():
    fields = [
        field("left", "구조", "The palace has an octagonal plan with a courtyard."),
        field("right", "구조", "The palace has a rectangular plan and a roof."),
        field("left", "재료", "The palace is made of marble."),
        field("right", "재료", "The palace is made of wood."),
    ]
    rows = classroom_rows(
        fields,
        ["구조", "재료"],
        {"left": "첫 궁전", "right": "둘째 궁전"},
        "left",
        "right",
        "advanced",
    )
    assert len(rows) == 5 and len({q for q, _, _ in rows}) == 5
    assert sum("이 설명을 해석" in q for q, _, _ in rows) == 1
