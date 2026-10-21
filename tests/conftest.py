import pytest

from culturebridge.config import get_settings


@pytest.fixture(autouse=True)
def offline_individual_sources(monkeypatch):
    # Live provider QA is separate; individual adapters have dedicated HTTP mocks.
    monkeypatch.setattr(get_settings(), "individual_sources_enabled", False)
    # A developer's real .env key must not turn ordinary regression tests into
    # paid, nondeterministic provider calls. AI tests opt in with mocked clients.
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    monkeypatch.setattr(get_settings(), "stdict_api_key", None)
    from culturebridge.services.operation_service import _cache, _requests

    _cache.clear()
    _requests.clear()
