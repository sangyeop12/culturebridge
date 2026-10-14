import pytest

from culturebridge.config import get_settings


@pytest.fixture(autouse=True)
def offline_individual_sources(monkeypatch):
    # Live provider QA is separate; individual adapters have dedicated HTTP mocks.
    monkeypatch.setattr(get_settings(), "individual_sources_enabled", False)
    from culturebridge.services.operation_service import _cache, _requests

    _cache.clear()
    _requests.clear()
