import logging
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningTurn
from culturebridge.main import app
from culturebridge.services import dictionary_service as service
from culturebridge.services.learning_conversation_service import (
    create_conversation,
    send_learning_turn,
)

KEY = "a" * 32


def payload():
    return {
        "channel": {
            "total": 2,
            "item": [
                {
                    "target_code": 1,
                    "word": "기단",
                    "pos": "명사",
                    "sense": {
                        "sense_no": "1",
                        "definition": "검증용 사전 뜻풀이 첫째.",
                        "cat": "건설",
                        "example": "이 용례는 수집하면 안 됩니다.",
                        "link": "https://evil.example/redirect",
                    },
                },
                {
                    "target_code": 2,
                    "word": "기단",
                    "sense": [
                        {"definition": "검증용 사전 뜻풀이 둘째.", "cat": "지구"},
                    ],
                },
            ],
        }
    }


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "dictionary.db")
    service._cache.clear()
    service._calls.clear()
    initialize_database()


def test_missing_key_never_contacts_provider(monkeypatch):
    monkeypatch.setattr(service, "_fetch", lambda *a: pytest.fail("missing key"))
    result = service.lookup_term("기단")
    assert result.status == "not_configured" and result.meanings == []
    assert "직접 확인" in result.notice


def test_verbatim_meanings_and_licence_no_examples_or_untrusted_links(monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    calls = []
    monkeypatch.setattr(service, "_fetch", lambda *a: calls.append(a) or payload())
    first = service.lookup_term("기단")
    second = service.lookup_term("기단")
    assert len(first.meanings) == 2
    assert first.meanings[0].definition == "검증용 사전 뜻풀이 첫째."
    assert first.modified is False and first.license_name == "CC BY-SA 2.0 KR"
    assert all(m.source_url.startswith("https://stdict.korean.go.kr/") for m in first.meanings)
    assert (
        "이 용례" not in first.model_dump_json() and "evil.example" not in first.model_dump_json()
    )
    assert second.cached and len(calls) == 1
    assert KEY not in first.model_dump_json()


@pytest.mark.parametrize("code", [20, "020", "021"])
def test_key_errors_are_not_exposed(code, monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(
        service,
        "_fetch",
        lambda *a: {
            "error": {
                "error_code": code,
                "message": "secret " + KEY,
            }
        },
    )
    result = service.lookup_term("석탑")
    assert result.status == "invalid_key" and KEY not in result.model_dump_json()


@pytest.mark.parametrize("bad", [{}, [], {"channel": {"total": 1, "item": []}}])
def test_bad_response_does_not_fabricate_definitions(bad, monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(service, "_fetch", lambda *a: bad)
    result = service.lookup_term("석탑")
    assert result.status == "unavailable" and not result.meanings


def test_provider_failure_never_leaks_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))

    def fail(*args):
        raise RuntimeError("https://stdict.korean.go.kr/api/search.do?key=" + KEY)

    monkeypatch.setattr(service, "_fetch", fail)
    result = service.lookup_term("석탑")
    assert result.status == "unavailable" and KEY not in result.model_dump_json()


def test_transport_contract_and_key_redaction(monkeypatch, caplog):
    original = httpx.Client
    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(200, json=payload())

    monkeypatch.setattr(
        service.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)),
    )
    caplog.set_level(logging.INFO, logger="httpx")
    data = service._fetch("기단", KEY)
    assert data["channel"]["total"] == 2
    assert captured[0].url.params["key"] == KEY
    assert captured[0].url.params["method"] == "exact"
    assert KEY not in caplog.text


def test_dictionary_question_is_routed_without_ai_or_heritage_choice(monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(service, "_fetch", lambda *a: payload())
    conversation = create_conversation()
    result = send_learning_turn(
        conversation.id, LearningTurn(request_id=uuid4(), revision=0, text="기단이 뭐야?")
    )
    message = result.messages[-1]
    assert message.kind == "dictionary"
    assert "검증용 사전 뜻풀이 첫째." in message.text
    assert "역사적 맥락" in message.text
    assert len(message.citations) == 2 and not result.search_results
    assert result.concepts == {}


def test_dictionary_text_not_automatically_forwarded_to_planner(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(service, "_fetch", lambda *a: payload())
    conversation = create_conversation()
    result = send_learning_turn(
        conversation.id, LearningTurn(request_id=uuid4(), revision=0, text="기단이 뭐야?")
    )

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            assert "검증용 사전 뜻풀이" not in kwargs["contents"]
            return SimpleNamespace(text='{"action":"ask","question":"어느 유산이 궁금한가요?"}')

    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only")
    monkeypatch.setattr(learning.genai, "Client", FakeClient)
    send_learning_turn(
        conversation.id,
        LearningTurn(request_id=uuid4(), revision=result.revision, text="역사적 맥락도 궁금해요"),
    )


def test_api_validation_and_not_found(monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(service, "_fetch", lambda *a: {"channel": {"total": 0}})
    with TestClient(app) as client:
        assert (
            client.get("/api/learning/terms", params={"q": "없는말"}).json()["status"]
            == "not_found"
        )
        assert (
            client.get("/api/learning/terms", params={"q": "https://evil.example"}).status_code
            == 422
        )


def test_local_throttle_is_not_provider_quota(monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(service, "_fetch", lambda *a: pytest.fail("local rate limit"))
    service._calls.extend([service.time.monotonic()] * 20)
    assert service.lookup_term("기단").status == "rate_limited"


def test_dictionary_ui_keeps_attribution_and_license_visible(monkeypatch):
    monkeypatch.setattr(get_settings(), "stdict_api_key", SecretStr(KEY))
    monkeypatch.setattr(service, "_fetch", lambda *a: payload())
    with TestClient(app) as client:
        state = client.post("/api/learning/conversations").json()
        path = f"/api/learning/conversations/{state['id']}/turns"
        result = client.post(
            path,
            json={
                "request_id": str(uuid4()),
                "revision": 0,
                "text": "기단이 뭐야?",
            },
        )
        assert result.status_code == 200
        page = client.get(f"/learn?conversation_id={state['id']}")
        assert page.status_code == 200
        assert "출처: 국립국어원 표준국어대사전" in page.text
        assert service.LICENSE_URL in page.text
