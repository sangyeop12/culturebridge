from datetime import UTC, datetime

import pytest

from culturebridge.config import get_settings
from culturebridge.domain.models import CollectedSource
from culturebridge.services import extraction_service as service


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    return CollectedSource(
        id="test-source",
        heritage_id="seokguram",
        title="Test source",
        organization="Test",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        status="cached",
        content_kind="individual_text",
        content="It was built in the 8th century. The grotto is built of granite.",
        scope_note="Test individual source",
    )


def draft(**updates):
    values = dict(
        heritage_id="seokguram",
        category="재료",
        value="화강암",
        source_id="test-source",
        evidence_quote="The grotto is built of granite.",
    )
    values.update(updates)
    return service.DraftField(**values)


def test_exact_quote_is_attached_but_not_semantically_verified(source):
    result = service.validate_extraction(draft(), [source])
    assert result.evidence_quote in source.content
    assert result.source_url == source.source_url
    assert result.verification_status.value == "needs_review"


@pytest.mark.parametrize(
    "updates",
    [
        {"evidence_quote": "This invented quote is not in the source."},
        {"heritage_id": "horyuji"},
        {"source_id": "missing"},
    ],
)
def test_wrong_source_or_invented_quote_is_rejected(source, updates):
    assert service.validate_extraction(draft(**updates), [source]) is None


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "stale"},
        {"status": "unavailable"},
        {"content_kind": "metadata"},
        {"content_kind": "group_text"},
    ],
)
def test_non_individual_and_outdated_sources_are_excluded(source, updates):
    altered = source.model_copy(update=updates)
    result = service.extract_fields([altered], ["seokguram"])
    assert len(result) == 3
    assert all(
        field.value is None and field.verification_status.value == "insufficient_evidence"
        for field in result
    )


def test_local_extraction_preserves_evidence_and_missing_target(source):
    result = service.extract_fields([source], ["seokguram", "horyuji"])
    assert len(result) == 6
    assert all(field.evidence_quote in source.content for field in result[:3])
    assert all(field.method == "local" for field in result[:3])
    assert all(field.value is None for field in result[3:])


def test_invalid_ai_quote_is_not_accepted(source, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(
        service,
        "_gemini_extraction",
        lambda sources: service.DraftExtraction(
            fields=[draft(evidence_quote="Fabricated evidence")]
        ),
    )
    assert all(field.value is None for field in service.extract_fields([source], ["seokguram"]))


def test_ai_failure_falls_back_to_local_source_sentences(source, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)

    def fail(sources):
        raise TimeoutError("Test failure")

    monkeypatch.setattr(service, "_gemini_extraction", fail)
    result = service.extract_fields([source], ["seokguram"])
    assert result[2].value and result[2].method == "local"
    assert "AI 추출 실패" in result[2].note
