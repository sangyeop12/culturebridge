from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.models import (
    CollectedSource,
    ExtractedField,
    LearningLevel,
    VerificationStatus,
)
from culturebridge.main import app
from culturebridge.services import source_claim_service as service
from culturebridge.services.claim_service import verify_claim
from culturebridge.services.comparison_service import create_saved_comparison

QUOTE = "The grotto was constructed of granite."


@pytest.fixture
def comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "claims.db")
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    monkeypatch.setattr(
        service, "retry_missing_sources", lambda left, right, sources, targets: sources
    )
    initialize_database()
    source = CollectedSource(
        id="test",
        heritage_id="seokguram",
        title="Test source",
        organization="Test",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        content=QUOTE,
        content_kind="individual_text",
        status="cached",
        retrieved_at=datetime.now(UTC),
        scope_note="Test",
    )
    field = ExtractedField(
        heritage_id="seokguram",
        category="재료",
        value="화강암",
        source_id="test",
        evidence_quote=QUOTE,
        source_url=source.source_url,
        note="Candidate",
        verification_status=VerificationStatus.NEEDS_REVIEW,
    )
    return create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=[source],
        extracted_fields=[field],
    )


def cite(quote=QUOTE, heritage_id="seokguram", source_id="test", relation="supports"):
    return service.Citation(
        quote=quote, heritage_id=heritage_id, source_id=source_id, relation=relation
    )


def mock_ai(monkeypatch, report):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(service, "_assess_with_gemini", lambda claim, sources: report)


def test_exact_sentence_confirms_only_source_match(comparison):
    result = verify_claim("seokguram", "horyuji", QUOTE, comparison_id=comparison.saved_id)
    assert result.assessment == "source_match"
    assert result.verification_status is VerificationStatus.VERIFIED
    assert "독립 검증은 아닙니다" in result.explanation
    assert result.evidence[0].evidence_quote == QUOTE


@pytest.mark.parametrize(
    "citation",
    [cite(quote="Invented quote"), cite(heritage_id="horyuji"), cite(source_id="missing")],
)
def test_invalid_ai_evidence_is_not_attached(comparison, monkeypatch, citation):
    mock_ai(
        monkeypatch,
        service.ClaimReport(
            parts=[service.ClaimPart(statement="Test claim", citations=[citation])]
        ),
    )
    result = verify_claim(
        "seokguram", "horyuji", "주장의 근거를 확인한다", comparison_id=comparison.saved_id
    )
    assert result.evidence == [] and result.sources == []
    assert result.verification_status is VerificationStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    "relation,assessment",
    [("supports", "support_candidate"), ("contradicts", "contradiction_candidate")],
)
def test_ai_support_and_contradiction_are_review_candidates(
    comparison, monkeypatch, relation, assessment
):
    mock_ai(
        monkeypatch,
        service.ClaimReport(
            parts=[
                service.ClaimPart(statement="Claim to review", citations=[cite(relation=relation)])
            ]
        ),
    )
    result = verify_claim(
        "seokguram", "horyuji", "석굴암의 재료는 목재이다", comparison_id=comparison.saved_id
    )
    assert result.assessment == assessment
    assert result.verification_status is VerificationStatus.NEEDS_REVIEW
    assert result.sources[0].id == "test"


def test_compound_claim_with_missing_part_is_not_fully_confirmed(comparison, monkeypatch):
    mock_ai(
        monkeypatch,
        service.ClaimReport(
            parts=[
                service.ClaimPart(statement="재료 주장", citations=[cite()]),
                service.ClaimPart(statement="장인 만남 주장", citations=[]),
            ]
        ),
    )
    result = verify_claim(
        "seokguram",
        "horyuji",
        "재료와 장인들의 만남에 관한 주장",
        comparison_id=comparison.saved_id,
    )
    assert result.verification_status is VerificationStatus.NEEDS_REVIEW
    assert "1개" in result.explanation
    assert result.unsupported_parts == ["장인 만남 주장"]


def test_offline_field_claim_shows_related_quote_not_a_verdict(comparison):
    result = verify_claim(
        "seokguram", "horyuji", "석굴암의 재료는 목재이다", comparison_id=comparison.saved_id
    )
    assert result.verification_status is VerificationStatus.NEEDS_REVIEW
    assert result.evidence[0].relation == "related"
    assert result.evidence[0].evidence_quote == QUOTE


def test_api_rejects_missing_or_wrong_snapshot(comparison):
    client = TestClient(app)
    payload = {
        "left_id": "seokguram",
        "right_id": "horyuji",
        "claim": "주장을 확인한다",
        "comparison_id": "missing",
    }
    assert client.post("/api/claims/verify", json=payload).status_code == 404
    payload.update(left_id="horyuji", right_id="seokguram", comparison_id=comparison.saved_id)
    assert client.post("/api/claims/verify", json=payload).status_code == 422


@pytest.mark.parametrize(
    "update", [{"status": "stale"}, {"content_kind": "metadata"}, {"content_kind": "group_text"}]
)
def test_unusable_source_is_excluded_even_when_quote_exists(comparison, update):
    sources = [comparison.collected_sources[0].model_copy(update=update)]
    report = service.ClaimReport(parts=[service.ClaimPart(statement="Test", citations=[cite()])])
    evidence, missing = service._validate_report(report, sources)
    assert evidence == [] and missing == 1


@pytest.mark.parametrize("oversized", ["parts", "citations"])
def test_local_response_limits_remain_enforced_after_provider_schema_simplification(oversized):
    from pydantic import ValidationError

    part = {"statement": "Test", "citations": []}
    if oversized == "parts":
        payload = {"parts": [part] * 9}
    else:
        payload = {"parts": [{"statement": "Test", "citations": [cite().model_dump()] * 11}]}
    with pytest.raises(ValidationError):
        service.ClaimReport.model_validate(payload)


def test_missing_claim_retries_once_and_reassesses_without_changing_snapshot(
    comparison, monkeypatch
):
    reports = iter(
        [
            service.ClaimReport(parts=[service.ClaimPart(statement="석굴암 재료", citations=[])]),
            service.ClaimReport(
                parts=[service.ClaimPart(statement="석굴암 재료", citations=[cite()])]
            ),
        ]
    )
    calls = []
    mock_ai(monkeypatch, None)
    monkeypatch.setattr(service, "_assess_with_gemini", lambda *args: next(reports))

    def retry(left, right, sources, targets):
        calls.append(targets)
        return sources

    monkeypatch.setattr(service, "retry_missing_sources", retry)
    from culturebridge.services.comparison_service import get_saved_comparison

    before = get_saved_comparison(comparison.saved_id).model_dump_json()
    result = service.verify_source_claim(
        "seokguram", "horyuji", "석굴암의 재료는 화강암이다", comparison.saved_id
    )
    assert result.retry_count == 1 and calls == [["seokguram"]]
    assert result.assessment == "support_candidate" and result.used_ai
    assert len(result.execution_trace) == 3
    assert get_saved_comparison(comparison.saved_id).model_dump_json() == before


def test_unresolved_claim_stops_after_single_retry(comparison, monkeypatch):
    mock_ai(
        monkeypatch,
        service.ClaimReport(parts=[service.ClaimPart(statement="직접 영향 관계", citations=[])]),
    )
    result = service.verify_source_claim(
        "seokguram", "horyuji", "두 유산은 직접 영향을 주었다", comparison.saved_id
    )
    assert result.retry_count == 1
    assert result.verification_status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert result.unsupported_parts == ["직접 영향 관계"]
    assert "보류" in result.explanation


def test_source_match_does_not_retry(comparison, monkeypatch):
    def fail(*args):
        pytest.fail("A verbatim source match does not require research")

    monkeypatch.setattr(service, "retry_missing_sources", fail)
    result = service.verify_source_claim("seokguram", "horyuji", QUOTE, comparison.saved_id)
    assert result.retry_count == 0
