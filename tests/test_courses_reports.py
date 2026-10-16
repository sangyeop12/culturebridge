"""Offline privacy, goal preservation, source review, and classroom export contracts."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from culturebridge.api.router import router
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.models import CollectedSource, LearningGoal, LearningLevel
from culturebridge.services import course_service as courses
from culturebridge.services.comparison_service import (
    ComparisonNotFoundError,
    create_saved_comparison,
)
from culturebridge.services.dynamic_heritage_service import OfficialTarget
from culturebridge.services.evidence_reading_service import reading_units
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.learning_report_service import (
    LearningReportNotFoundError,
    _summary,
    learning_report,
    report_html,
    report_markdown,
)
from culturebridge.services.material_review_service import material_review, review_markdown
from culturebridge.services.navigation_service import search_return
from culturebridge.services.operation_service import session_owner
from culturebridge.services.quiz_service import generate_quiz, grade_quiz


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "gemini_enabled", False)
    monkeypatch.setattr(settings, "public_mode", False)
    initialize_database()
    token = session_owner.set(None)
    yield
    session_owner.reset(token)


def source(identity="seokguram", status="fresh"):
    return CollectedSource(
        id=identity,
        heritage_id=identity,
        title="Synthetic Hall",
        organization="Fixture",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        content_kind="individual_text",
        status=status,
        content="The hall was completed in 1511. The hall has a wooden roof. "
        "The hall is a Buddhist building. RAW_PROVIDER_SENTINEL",
        scope_note="Synthetic test, not heritage facts",
    )


def comparison():
    sources = [source(), source("horyuji")]
    return create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=extract_fields(sources, ["seokguram", "horyuji"]),
        goal=LearningGoal.OBSERVE,
    )


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_review_has_exactly_25_without_claiming_approval():
    rows = material_review()
    assert len(rows) == 25
    assert all(row["id"] != "official:horyuji-pagoda" for row in rows)
    assert all(row["name_status"] != "reviewed" for row in rows)
    assert all(row["usage_status"] != "reviewed" for row in rows)
    assert all(row["categories"] == [] for row in rows)
    assert all(row["scope_note"] and row["policy_note"] for row in rows)
    assert "권한 확인 필요" in review_markdown()
    assert "한국어 의미 승인이나 재이용 허가가 아닙니다" in review_markdown()


def test_korean_building_materials_are_read_without_overriding_negation():
    assert ("재료", "나무") in reading_units("재료", "오층탑은 목조 건축물입니다.")
    assert ("재료", "돌") in reading_units("재료", "석조 건물입니다.")
    assert reading_units("재료", "목조를 모방한 석조 건물입니다.") == []
    unknown_era = SimpleNamespace(category="시대", evidence_quote="시대 미상 원문 표식")
    assert "시대 미상 원문 표식" not in _summary(unknown_era)


def test_course_catalogue_and_typed_targets():
    assert len(courses.list_courses()) == 5
    for course in courses.list_courses():
        assert course["comparison_scope"] == "overseas"
        assert len(course["activities"]) == 3
        OfficialTarget(**course["left"])
        OfficialTarget(**course["right"])
    course = courses.get_course("pagoda-materials")
    course["activities"].clear()
    assert courses.get_course("pagoda-materials")["activities"]
    with pytest.raises(courses.CourseNotFoundError):
        courses.get_course("unknown")


def test_course_preserves_goals_and_progress_is_private(monkeypatch):
    comp = comparison()
    received = []

    def fetch(target):
        return SimpleNamespace(id=target.provider, country="Japan"), source()

    monkeypatch.setattr(courses, "fetch_target", fetch)

    def run(state):
        received.append(state)
        return {"comparison": {"saved_id": comp.saved_id}}

    monkeypatch.setattr(courses, "run_exploration", run)
    courses.start_course("pagoda-materials", "advanced")
    assert received[0]["level"] == "advanced"
    assert received[0]["goal_text"] == "구조와 재료"
    assert received[0]["goal"] == "observe"
    assert received[0]["comparison_scope"] == "overseas"
    assert courses.course_progress("pagoda-materials")[0]["status"] == "comparison_ready"
    token = session_owner.set("other")
    try:
        assert courses.course_progress("pagoda-materials") == []
    finally:
        session_owner.reset(token)
    with transaction() as connection:
        connection.execute("DELETE FROM comparisons WHERE id=?", (comp.saved_id,))
        assert connection.execute("SELECT count(*) FROM course_runs").fetchone()[0] == 0


@pytest.mark.parametrize("status", ["stale", "unavailable"])
def test_course_holds_without_fresh_evidence(monkeypatch, status):
    monkeypatch.setattr(
        courses,
        "fetch_target",
        lambda target: (SimpleNamespace(id="fixture", country="Japan"), source(status=status)),
    )
    monkeypatch.setattr(courses, "run_exploration", lambda state: pytest.fail("must not run"))
    with pytest.raises(courses.CourseNotReadyError):
        courses.start_course("pagoda-materials")


def test_course_holds_when_goal_not_supported(monkeypatch):
    thin = source().model_copy(update={"content": "The hall was completed in 1511."})
    monkeypatch.setattr(
        courses,
        "fetch_target",
        lambda target: (SimpleNamespace(id="fixture", country="Japan"), thin),
    )
    with pytest.raises(courses.CourseNotReadyError):
        courses.start_course("pagoda-materials")


def test_export_excludes_raw_source_and_unsubmitted_quiz():
    comp = comparison()
    generate_quiz("seokguram", "horyuji", comp.level, comparison_id=comp.saved_id)
    report = learning_report(comp.saved_id)
    assert report["assessment"] is None
    serialized = json.dumps(report, ensure_ascii=False)
    assert "RAW_PROVIDER_SENTINEL" not in serialized
    assert "correct_index" not in serialized and "choices" not in serialized
    assert "The hall has a wooden roof." not in serialized
    assert "PDF" in report_html(report)
    assert "## 퀴즈와 복습" in report_markdown(report)


def test_export_after_grading_has_score_and_review_not_answers():
    comp = comparison()
    quiz = generate_quiz("seokguram", "horyuji", comp.level, comparison_id=comp.saved_id)
    result = grade_quiz(quiz.quiz_id, [0] * len(quiz.items))
    report = learning_report(comp.saved_id, result.history_id)
    assert report["assessment"]["score"] == result.score
    assert report["assessment"]["total"] == result.total
    assert report["assessment"]["history_id"] == result.history_id
    assert "correct_answer" not in json.dumps(report)
    assert "explanations" not in json.dumps(report)
    with pytest.raises(LearningReportNotFoundError):
        learning_report(comp.saved_id, result.history_id + 100)


def test_exports_private_even_in_local_mode():
    comp = comparison()
    token = session_owner.set("other")
    try:
        with pytest.raises(ComparisonNotFoundError):
            learning_report(comp.saved_id)
        assert client().get(f"/api/comparisons/{comp.saved_id}/export").status_code == 404
    finally:
        session_owner.reset(token)


def test_export_formats_and_escaping():
    comp = comparison()
    report = learning_report(comp.saved_id)
    report["goal_text"] = '<script>alert("x")</script> | injected'
    assert "<script>" not in report_html(report)
    assert "&lt;script&gt;" in report_html(report)
    assert "\\| injected" in report_markdown(report)
    api = client()
    for format in ("html", "md", "json"):
        response = api.get(f"/api/comparisons/{comp.saved_id}/export?format={format}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
    assert api.get(f"/api/comparisons/{comp.saved_id}/export?format=pdf").status_code == 422
    assert api.get(f"/api/comparisons/{comp.saved_id}/export?history_id=0").status_code == 422


def test_new_api_routes_and_safe_course_returns():
    api = client()
    assert len(api.get("/api/courses").json()) == 5
    assert len(api.get("/api/material-review").json()) == 25
    assert api.get("/api/material-review?format=md").status_code == 200
    assert api.get("/api/courses/nope/progress").status_code == 404
    assert api.post("/api/courses/nope/start", json={}).status_code == 404
    assert search_return("/courses/pagoda-materials?level=advanced") == (
        "/courses/pagoda-materials?level=advanced"
    )
    for path in ("//evil/courses/a", "/courses/nope", "/courses/../a", "/courses/%2fevil"):
        assert search_return(path) == "/"
