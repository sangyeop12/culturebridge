import json

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents.learning import _model_decision
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.main import app


@pytest.mark.parametrize(
    "enabled,key,mode",
    [
        (False, "test-only-secret", "disabled"),
        (True, None, "missing_key"),
        (True, "test-only-secret", "configured"),
    ],
)
def test_runtime_status_distinguishes_disabled_and_missing_key(
    tmp_path, monkeypatch, enabled, key, mode
):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", tmp_path / "runtime.db")
    monkeypatch.setattr(settings, "gemini_enabled", enabled)
    monkeypatch.setattr(settings, "gemini_api_key", key)
    initialize_database()
    with TestClient(app) as client:
        response = client.get("/api/ai-status")
    assert response.status_code == 200
    assert response.json()["mode"] == mode
    assert response.json()["enabled"] is enabled
    assert response.json()["key_configured"] is bool(key)
    assert "test-only-secret" not in response.text


@pytest.mark.parametrize(
    "enabled,key,reason",
    [(False, "test-only-secret", "gemini_disabled"), (True, None, "gemini_key_missing")],
)
def test_unavailable_planner_reports_the_actual_configuration_problem(
    monkeypatch, enabled, key, reason
):
    monkeypatch.setattr(get_settings(), "gemini_enabled", enabled)
    monkeypatch.setattr(get_settings(), "gemini_api_key", key)
    with pytest.raises(ValueError, match=reason):
        _model_decision({})


def test_saved_disabled_reply_does_not_offer_manual_retry(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", tmp_path / "retry.db")
    monkeypatch.setattr(settings, "gemini_api_key", "test-only-secret")
    initialize_database()
    with TestClient(app) as client:
        state = client.post("/api/learning/conversations").json()
        state.update(
            pending_request="경복궁에 대해 말해주세요",
            notice="실행 중인 서버에서 Gemini가 꺼져 있거나 API 키를 읽지 못했어요.",
            plan_history=[{"planner_error": {"reason": "planner_not_available"}}],
        )
        with transaction() as connection:
            connection.execute(
                "UPDATE learning_conversations SET state_json=? WHERE id=?",
                (json.dumps(state), state["id"]),
            )
        path = f"/learn?conversation_id={state['id']}"
        monkeypatch.setattr(settings, "gemini_enabled", False)
        assert "AI로 다시 답변받기" not in client.get(path).text
        monkeypatch.setattr(settings, "gemini_enabled", True)
        page = client.get(path)
        assert "AI로 다시 답변받기" not in page.text
        assert "마지막 요청 결과:" in page.text
