from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents import workflow
from culturebridge.config import get_settings
from culturebridge.database import connect, initialize_database
from culturebridge.domain.models import CollectedSource, LearningGoal, LearningLevel
from culturebridge.main import app
from culturebridge.services.catalog_service import recommend_related
from culturebridge.services.curriculum_service import plan_learning
from culturebridge.services.quiz_service import load_quiz


def source(heritage, complete=True):
    text = (
        "Built in the 8th century. An artificial granite grotto."
        if heritage == "seokguram"
        else "Built in the 7th century. A wooden temple layout."
    )
    if complete:
        text += " It is a Buddhist temple."
    return CollectedSource(
        id="test:" + heritage,
        heritage_id=heritage,
        title=heritage,
        organization="Test official",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        content=text,
        content_kind="individual_text",
        status="cached",
        retrieved_at=datetime.now(UTC),
        scope_note="Test",
    )


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "adaptive.db")
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    initialize_database()
    settings = {"complete": True, "retry_fills": True, "retry_calls": 0}
    monkeypatch.setattr(
        workflow,
        "collect_official_sources",
        lambda left, right: [
            source(left, settings["complete"]),
            source(right, settings["complete"]),
        ],
    )

    def retry(left, right, old, missing):
        settings["retry_calls"] += 1
        return [source(left), source(right)] if settings["retry_fills"] else old

    monkeypatch.setattr(workflow, "retry_missing_sources", retry)
    return settings


def test_four_roles_and_tools_complete_without_unnecessary_retry(configured):
    result = workflow.exploration_graph.invoke(
        {"heritage_id": "seokguram", "comparison_id": "horyuji", "level": "beginner"}
    )
    assert result["retry_count"] == configured["retry_calls"] == 0
    assert len(result["extracted_fields"]) == 8
    assert len(result["comparison"]["differences"]) == 4
    assert result["comparison"]["common_evidence"]
    assert "불교" in result["comparison"]["common_points"][0]
    assert len(result["quiz"]["items"]) == 5
    for role in ("curriculum_agent", "history_agent", "verification_agent", "quiz_agent"):
        assert any(role in step for step in result["execution_trace"])


def test_missing_evidence_researches_once_then_saves_one_result(configured):
    configured["complete"] = False
    result = workflow.exploration_graph.invoke(
        {
            "heritage_id": "seokguram",
            "comparison_id": "horyuji",
            "level": "advanced",
            "goal": "religion",
        }
    )
    assert result["retry_count"] == configured["retry_calls"] == 1
    assert result["missing_heritages"] == []
    with connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM quiz_items").fetchone()[0] == 5


def test_unresolved_gap_stops_and_does_not_copy_old_summary(configured):
    configured.update(complete=False, retry_fills=False)
    result = workflow.exploration_graph.invoke(
        {"heritage_id": "seokguram", "comparison_id": "horyuji", "goal": "religion"}
    )
    assert result["retry_count"] == 1 and result["missing_heritages"]
    religion = next(
        p for p in result["comparison"]["differences"] if p["category"] == "종교적 배경"
    )
    assert religion["left"] == religion["right"] == "근거 부족"


@pytest.mark.parametrize("level", list(LearningLevel))
def test_goal_and_free_text_change_plan(level):
    observe, focus1 = plan_learning(level, LearningGoal.OBSERVE)
    religion, focus2 = plan_learning(level, LearningGoal.RELIGION)
    custom, focus3 = plan_learning(level, LearningGoal.OBSERVE, "종교에 대해 알고 싶어요")
    assert observe != religion and focus1 != focus2
    assert focus3[0] == "종교적 배경" and custom != observe


def test_recommendation_explains_goal_specific_suitability():
    observe = recommend_related("seokguram", LearningGoal.OBSERVE)
    verify = recommend_related("seokguram", LearningGoal.VERIFY)
    assert all(item.criteria and 0 <= item.score <= 1 for item in observe)
    assert [item.score for item in observe] != [item.score for item in verify]


def test_custom_goal_preserves_requested_topic_order():
    _, focus = plan_learning(
        LearningLevel.BEGINNER, LearningGoal.COMPARE, "재료를 먼저 보고 종교도 알아보고 싶어요"
    )
    assert focus[:2] == ["재료", "종교적 배경"]


def test_api_quiz_ready_and_ui_reuses_same_quiz(configured):
    client = TestClient(app)
    response = client.post(
        "/api/explorations",
        json={
            "heritage_id": "seokguram",
            "comparison_id": "horyuji",
            "goal": "religion",
            "goal_text": "불교 공간을 비교하고 싶어요",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["goal_text"] == "불교 공간을 비교하고 싶어요"
    quiz_id = result["quiz"]["quiz_id"]
    reused = load_quiz(quiz_id, "seokguram", "horyuji")
    assert reused.quiz_id == quiz_id and reused.comparison_id == result["comparison"]["saved_id"]
    page = client.get(f"/quiz/seokguram/horyuji?quiz_id={quiz_id}")
    assert page.status_code == 200
    with connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM quiz_items").fetchone()[0] == 5
