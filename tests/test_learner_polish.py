from datetime import UTC, datetime

import pytest

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.models import ExtractedField, LearningLevel
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.evidence_reading_service import reading_units, usable_categories
from culturebridge.services.learner_presentation_service import (
    learning_day,
    lesson_activity,
    owns_comparison,
    save_learning_note,
)
from culturebridge.services.learning_analysis_service import comparison_explanation
from culturebridge.services.learning_diagram_service import shape_diagram
from culturebridge.services.learning_report_service import (
    learning_report,
    report_html,
    report_markdown,
)
from culturebridge.services.lesson_service import beginner_text
from culturebridge.services.operation_service import session_owner
from culturebridge.services.source_permission_service import (
    external_ai_allowed,
    policy_url,
    record_permission,
)
from culturebridge.services.source_registry_service import save_review


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "polish.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    token = session_owner.set("learner-a")
    yield
    session_owner.reset(token)


def field(quote, category="구조", event=None):
    return ExtractedField(
        heritage_id="fixture",
        category=category,
        evidence_quote=quote,
        value=quote,
        note="",
        date_event=event,
    )


def test_mound_and_plan_are_not_same_axis():
    text = comparison_explanation(
        "구조", field("둥근 원분이다."), field("The plan is rectangular.")
    )
    assert "부분이 같지 않아" in text


def test_dabotap_three_shapes_survive_and_have_diagram():
    quote = "십(十)자 모양 평면의 기단에 8각형 탑신과 네모난 난간을 돌렸다."
    text = beginner_text("구조", quote)
    assert all(word in text for word in ("십자", "여덟", "네모"))
    diagram = shape_diagram(quote)
    assert diagram.count("<svg") == 3 and "복원도가 아니에요" in diagram


def test_negative_clause_does_not_erase_positive_stone():
    quote = "깬돌들이 일부 노출되어 있을 뿐 후대의 둘레돌은 꾸며지지 않았다."
    assert ("재료", "돌") in reading_units("재료", quote)
    assert not reading_units("재료", "The building is not made of stone.")
    assert "재료" not in usable_categories([field("The building is not made of stone.", "재료")])


def test_unknown_event_is_not_proof_of_difference():
    text = comparison_explanation(
        "시대", field("in 1700", "시대"), field("in 1800", "시대", "건립·창건")
    )
    assert "아직 확인하지 못했어요" in text and "사건이 달라요" not in text


def test_permission_is_explicit_per_purpose_and_restriction_wins():
    assert not external_ai_allowed(["official:toji-pagoda"])
    record_permission("toji-pagoda", "ai", True, "Synthetic test approval, not actual permission")
    assert external_ai_allowed(["official:toji-pagoda"])
    assert not external_ai_allowed(["official:toji-pagoda"], "translation")
    save_review("toji-pagoda", "도지 오층탑", usage_status="restricted")
    assert not external_ai_allowed(["official:toji-pagoda"])
    assert "terms-of-use" in policy_url("https://www.japan.travel/ko/spot/1186/")


def test_notes_owned_exported_escaped_and_deleted_with_comparison():
    comp = create_saved_comparison("seokguram", "horyuji", LearningLevel.BEGINNER)
    save_learning_note(comp.saved_id, "<script>alert(1)</script> 내가 비교한 내용")
    report = learning_report(comp.saved_id)
    assert "내가 비교한 내용" in report_markdown(report)
    output = report_html(report)
    assert "<script>alert(1)</script>" not in output
    assert "저장 시각" not in output and "학습 구성 버전" not in output
    token = session_owner.set("learner-b")
    try:
        assert not owns_comparison(comp.saved_id)
        with pytest.raises(ValueError):
            save_learning_note(comp.saved_id, "overwrite")
        assert not lesson_activity(comp.saved_id)["note"]
    finally:
        session_owner.reset(token)
    with transaction() as connection:
        connection.execute("DELETE FROM comparisons WHERE id=?", (comp.saved_id,))
        assert connection.execute("SELECT COUNT(*) FROM learning_notes").fetchone()[0] == 0


def test_learning_day_uses_korea_date_not_raw_timestamp():
    assert learning_day(datetime(2026, 10, 17, 18, 0, tzinfo=UTC)) == "10월 18일 학습"
    assert ":" not in learning_day("2026-10-17 18:00:00")


def test_interval_counts_as_evidence_without_becoming_one_year():
    from culturebridge.services.evidence_reading_service import source_years

    quote = "The cathedral was built between 1093 and 1133."
    assert source_years(quote) == ["1093", "1133"]
    assert "시대" in usable_categories([field(quote, "시대", "건립·창건")])
