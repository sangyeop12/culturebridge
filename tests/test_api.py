import sqlite3

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_api_database(tmp_path, monkeypatch):
    path = tmp_path / "api.db"
    monkeypatch.setattr(get_settings(), "db_path", path)
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    initialize_database(path)
    from culturebridge.services import source_collection_service as collector
    from culturebridge.services.official_service import OfficialServiceError

    def no_remote(*args, **kwargs):
        raise OfficialServiceError("External requests disabled in API tests")

    monkeypatch.setattr(collector, "get_official_document", no_remote)
    monkeypatch.setattr(collector, "search_unesco", no_remote)


def test_complete_local_learning_flow():
    from culturebridge.database import connect, load_quiz_items

    search = client.get("/api/heritages", params={"q": "석굴암"}).json()
    selected_id = search[0]["id"]
    candidates = client.get(f"/api/heritages/{selected_id}/related").json()
    right_id = candidates[0]["heritage"]["id"]
    exploration_response = client.post(
        "/api/explorations",
        json={"heritage_id": selected_id, "comparison_id": right_id, "level": "advanced"},
    )
    assert exploration_response.status_code == 200
    comparison = exploration_response.json()["comparison"]
    saved_id = comparison["saved_id"]
    saved = client.get(f"/api/comparisons/{saved_id}").json()
    assert saved["comparison"] == comparison
    assert {source["id"] for source in saved["sources"]} == set(comparison["source_ids"])
    answer = client.post(
        "/api/questions",
        json={"left_id": selected_id, "right_id": right_id, "question": "재료는 무엇인가요?"},
    ).json()
    assert answer["used_ai"] is False
    assert "화강암" in answer["answer"]
    claim = client.post(
        "/api/claims/verify",
        json={"left_id": selected_id, "right_id": right_id, "claim": "석굴암의 재료는 화강암이다"},
    ).json()
    assert claim["verification_status"] == "verified"
    quiz = client.post(
        "/api/quizzes",
        json={"left_id": selected_id, "right_id": right_id, "level": "advanced"},
    ).json()
    answers = [row["correct_index"] for row in load_quiz_items(quiz["quiz_id"])]
    grade = client.post(
        "/api/quiz-attempts", json={"quiz_id": quiz["quiz_id"], "answers": answers}
    ).json()
    assert grade["score"] == grade["total"] == 5
    with connect() as connection:
        history = connection.execute(
            "SELECT level, score FROM learning_history WHERE session_id = ?", (quiz["quiz_id"],)
        ).fetchone()
    assert history["level"] == "advanced" and history["score"] == 5
    assert len(client.get("/api/comparisons").json()) == 1


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "path,message",
    [
        ("/quiz/unknown/horyuji", "퀴즈에 사용할 문화유산을 찾을 수 없습니다."),
        ("/compare/seokguram/seokguram", "서로 다른 문화유산을 선택해 주세요."),
        ("/quiz/seokguram/seokguram?mode=kiosk", "서로 다른 문화유산을 선택해 주세요."),
        ("/compare/seokguram/horyuji?saved_id=missing", "비교 결과를 찾을 수 없습니다."),
        ("/explore/seokguram?level=invalid", "학습 수준을 확인할 수 없어 초급으로 안내합니다."),
    ],
)
def test_invalid_ui_routes_show_recovery(path, message):
    response = client.get(path)
    assert response.status_code == 200
    assert message in response.text


def test_database_failure_returns_recoverable_api_error(monkeypatch):
    from culturebridge.api import router as api_module

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("private database path")

    monkeypatch.setattr(api_module, "list_saved_comparisons", fail)
    response = client.get("/api/comparisons")
    assert response.status_code == 503
    assert "잠시 후 다시 시도" in response.json()["detail"]
    assert "private database path" not in response.text


def test_database_failure_shows_ui_recovery(monkeypatch):
    from culturebridge.ui import pages

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("test unavailable")

    monkeypatch.setattr(pages, "create_saved_comparison", fail)
    response = client.get("/compare/seokguram/horyuji")
    assert response.status_code == 200
    assert "비교 결과를 저장하거나 불러올 수 없습니다." in response.text


def test_claim_api_validation_and_evidence() -> None:
    payload = {
        "left_id": "seokguram",
        "right_id": "horyuji",
        "claim": "석굴암의 재료는 화강암이다",
    }
    response = client.post("/api/claims/verify", json=payload)
    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"
    assert response.json()["sources"][0]["organization"] == "국가유산청 국가유산포털"
    payload["claim"] = "   "
    assert client.post("/api/claims/verify", json=payload).status_code == 422
    payload["claim"] = "석굴암의 재료는 화강암이다"
    payload["left_id"] = "unknown"
    assert client.post("/api/claims/verify", json=payload).status_code == 404


def test_comparison_endpoint() -> None:
    response = client.post(
        "/api/comparisons",
        json={"left_id": "seokguram", "right_id": "horyuji", "level": "beginner"},
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"


def test_saved_comparison_roundtrip_and_reopening_does_not_duplicate() -> None:
    created = client.post(
        "/api/comparisons",
        json={"left_id": "seokguram", "right_id": "horyuji", "level": "advanced"},
    ).json()
    record_id = created["saved_id"]
    assert record_id
    saved = client.get(f"/api/comparisons/{record_id}")
    assert saved.status_code == 200
    assert saved.json()["comparison"] == created
    assert len(saved.json()["sources"]) == 3
    assert client.get("/api/comparisons").json()[0]["id"] == record_id
    reopened = client.get(f"/compare/seokguram/horyuji?saved_id={record_id}")
    assert reopened.status_code == 200
    assert "학습 수준: 고급" in reopened.text
    assert len(client.get("/api/comparisons").json()) == 1
    assert client.get("/api/comparisons/missing").status_code == 404
    assert client.get("/api/comparisons?limit=101").status_code == 422
    assert client.get("/api/comparisons?offset=-1").status_code == 422
    assert client.get("/comparisons").status_code == 200


def test_exploration_runs_all_agent_stages() -> None:
    response = client.post(
        "/api/explorations",
        json={"heritage_id": "seokguram", "level": "intermediate"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["comparison_id"] in {"horyuji", "dayanta"}
    assert result["verification_status"] == "needs_review"
    assert len(result["curriculum"]) == 4
    record_id = result["comparison"]["saved_id"]
    assert client.get(f"/api/comparisons/{record_id}").json()["comparison"] == result["comparison"]


def test_question_endpoint_returns_sources_and_status() -> None:
    response = client.post(
        "/api/questions",
        json={
            "left_id": "seokguram",
            "right_id": "horyuji",
            "question": "두 문화유산의 구조는 어떻게 다른가요?",
            "level": "beginner",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["verification_status"] == "verified"
    assert len(result["source_ids"]) == 3
    assert result["used_ai"] is False


def test_unknown_heritage_returns_404() -> None:
    response = client.get("/api/heritages/unknown")
    assert response.status_code == 404


def test_quiz_generation_and_grading() -> None:
    quiz_response = client.post(
        "/api/quizzes",
        json={"left_id": "seokguram", "right_id": "horyuji", "level": "beginner"},
    )
    assert quiz_response.status_code == 200
    quiz = quiz_response.json()
    assert len(quiz["items"]) == 5
    assert "correct_index" not in quiz["items"][0]

    grade_response = client.post(
        "/api/quiz-attempts",
        json={"quiz_id": quiz["quiz_id"], "answers": [0, 1, 0, 0, 0]},
    )
    assert grade_response.status_code == 200
    assert grade_response.json()["total"] == 5


def test_kiosk_flow_pages_are_available() -> None:
    kiosk_response = client.get("/kiosk")
    assert kiosk_response.status_code == 200
    assert "박물관 터치 체험" in kiosk_response.text
    assert "5분 동안 조작하지 않으면" in kiosk_response.text

    explore_response = client.get("/explore/seokguram?level=beginner&mode=kiosk")
    assert explore_response.status_code == 200
    assert "처음으로" in explore_response.text

    compare_response = client.get("/compare/seokguram/horyuji?level=beginner&mode=kiosk")
    assert compare_response.status_code == 200
    assert "박물관 터치 체험" in compare_response.text

    quiz_response = client.get("/quiz/seokguram/horyuji?level=beginner&mode=kiosk")
    assert quiz_response.status_code == 200
    assert "채점하고 해설 보기" in quiz_response.text
