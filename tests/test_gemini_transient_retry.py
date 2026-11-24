import httpx
import pytest
from google import genai
from google.genai import types

from culturebridge.services.gemini_options import interactive_retry


@pytest.mark.parametrize("status,expected_calls", [(503, 2), (504, 2), (429, 2), (403, 1)])
def test_sdk_retries_transient_unavailability_but_not_quota_or_auth(status, expected_calls):
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, json={"error": {"code": status, "message": "test"}})
        return httpx.Response(
            200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]}
        )

    with genai.Client(
        api_key="test-only-key",
        http_options=types.HttpOptions(
            retry_options=interactive_retry(),
            client_args={"transport": httpx.MockTransport(handle)},
        ),
    ) as client:
        if status in {503, 504, 429}:
            assert client.models.generate_content(model="test-model", contents="test").text == "OK"
        else:
            with pytest.raises(genai.errors.ClientError):
                client.models.generate_content(model="test-model", contents="test")
    assert len(calls) == expected_calls


def test_sdk_stops_after_five_failed_retries():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"code": 503, "message": "test"}})

    with genai.Client(
        api_key="test-only-key",
        http_options=types.HttpOptions(
            retry_options=interactive_retry(),
            client_args={"transport": httpx.MockTransport(handle)},
        ),
    ) as client:
        with pytest.raises(genai.errors.ServerError):
            client.models.generate_content(model="test-model", contents="test")
    assert len(calls) == 6


def test_sdk_retries_a_connection_timeout():
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("test timeout")
        return httpx.Response(
            200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]}
        )

    with genai.Client(
        api_key="test-only-key",
        http_options=types.HttpOptions(
            retry_options=interactive_retry(),
            client_args={"transport": httpx.MockTransport(handle)},
        ),
    ) as client:
        assert client.models.generate_content(model="test-model", contents="test").text == "OK"
    assert len(calls) == 2
