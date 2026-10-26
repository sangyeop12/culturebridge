from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import LearningConversation
from culturebridge.domain.models import CollectedSource, ExtractedField, LearningLevel
from culturebridge.main import app
from culturebridge.services.comparison_service import create_saved_comparison, get_saved_comparison
from culturebridge.ui.learner_copy import (
    comparison_note,
    error_notice,
    recommendation_note,
    source_scope,
)

INTERNAL = "INTERNAL_DIAGNOSTIC_target_tool_검사전용"


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "presentation.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    sources, fields = [], []
    for identity, quote in [
        ("seokguram", "화강암으로 만든 건물이다."),
        ("horyuji", "목재로 만든 건물이다."),
    ]:
        source = CollectedSource(
            id=identity + "-source",
            heritage_id=identity,
            title="공식 자료",
            organization="공식 기관",
            source_url="https://www.khs.go.kr/",
            feed_url="https://www.khs.go.kr/",
            retrieved_at=datetime.now(UTC),
            content=quote,
            status="cached",
            content_kind="individual_text",
            scope_note=INTERNAL,
        )
        sources.append(source)
        fields.append(
            ExtractedField(
                heritage_id=identity,
                category="재료",
                value=quote,
                source_id=source.id,
                source_url=source.source_url,
                evidence_quote=quote,
                verification_status="needs_review",
                note=INTERNAL,
            )
        )
    result = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=fields,
    )
    record = get_saved_comparison(result.saved_id)
    record.comparison.verification_note = INTERNAL
    for point in record.comparison.differences:
        point.explanation = INTERNAL
    for common in record.comparison.common_evidence:
        common.context_note = INTERNAL
    for source in record.sources:
        source.scope_note = INTERNAL
    with transaction() as connection:
        connection.execute(
            "UPDATE comparisons SET content_json=? WHERE id=?",
            (record.model_dump_json(), result.saved_id),
        )
    return record


def test_saved_page_does_not_render_internal_notes_or_change_records(saved):
    before = get_saved_comparison(saved.id).model_dump_json()
    with TestClient(app) as client:
        response = client.get(f"/compare/seokguram/horyuji?saved_id={saved.id}")
    assert response.status_code == 200
    assert INTERNAL not in response.text
    assert "화강암으로 만든 건물이다." in response.text
    assert "목재로 만든 건물이다." in response.text
    assert "공식 원문" in response.text
    assert get_saved_comparison(saved.id).model_dump_json() == before


def test_comparison_uses_evidence_not_stored_explanation(saved):
    result = saved.comparison
    point = next(p for p in result.differences if p.category == "재료")
    text = comparison_note(result, point)
    assert INTERNAL not in text
    assert "화강암" in text and "나무" in text
    assert "왼쪽" not in text and "오른쪽" not in text
    assert "교류" not in text and "영향 관계" not in text


def test_missing_evidence_is_not_invented(saved):
    result = saved.comparison
    result.collected_sources[0].status = "stale"
    point = next(p for p in result.differences if p.category == "재료")
    assert "자료가 더 필요" in comparison_note(result, point)
    assert "화강암" not in comparison_note(result, point)


def test_raw_errors_and_source_notes_are_not_exposed(saved):
    assert INTERNAL not in error_notice(RuntimeError(INTERNAL))
    for source in saved.comparison.collected_sources:
        assert INTERNAL not in source_scope(source)
        assert "공식 자료" in source_scope(source)


def test_recommendation_keeps_learning_focus_without_raw_criteria():
    text = recommendation_note(["함께 확인할 수 있는 항목: 구조 · 재료", INTERNAL])
    assert "구조" in text and "재료" in text
    assert INTERNAL not in text


def test_chat_keeps_activity_but_hides_planner_rationale(saved, monkeypatch):
    from importlib import import_module

    chat = import_module("culturebridge.ui.learning_chat")
    state = LearningConversation(
        id=uuid4(),
        revision=0,
        tool_observations=[{"tool": "read", "status": "ok", "reason": INTERNAL}],
        plan_history=[{"reason": INTERNAL}],
    )
    monkeypatch.setattr(chat, "get_conversation", lambda _: state)
    before = state.model_dump_json()
    with TestClient(app) as client:
        response = client.get(f"/learn?conversation_id={state.id}")
    assert response.status_code == 200
    assert INTERNAL not in response.text
    assert "공식 근거 읽기" in response.text
    assert state.model_dump_json() == before


def test_learning_steps_keep_topics_without_review_jargon():
    from culturebridge.ui.learning_steps import step_label

    assert step_label("구조의 주장과 원문 범위 대조") == "구조 살펴보기 · 공식 설명 함께 읽기"
    assert "공통점 후보" not in step_label("공통점 후보의 양쪽 근거와 대체 해석 검토")
    assert step_label("무엇으로 만들었는지 보기") == "무엇으로 만들었는지 보기"
