from datetime import UTC, datetime

import httpx
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
from culturebridge.services import research_retry_service as retry
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.evidence_comparison_service import apply_extracted_comparison
from culturebridge.services.extraction_service import DraftField, validate_extraction
from culturebridge.services.quiz_service import generate_quiz


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "quality.db")
    initialize_database()


def test_research_loading_response_does_not_start_remote_work_before_client_connection(monkeypatch):
    from culturebridge.ui import pages

    def fail(*args):
        pytest.fail("Research must wait for the browser connection")

    monkeypatch.setattr(pages, "run_exploration", fail)
    with TestClient(app) as client:
        response = client.get("/research/seokguram/horyuji")
    assert response.status_code == 200
    assert "두 유산의 이야기를 준비하고 있어요" in response.text
    assert "response_timeout" not in response.text


def test_alternative_source_is_targeted_and_cached(monkeypatch):
    original = httpx.Client
    calls = []
    payload = (
        b"<html><p>Other temple was built in 1466.</p>"
        b"<p>The Giant Wild Goose Pagoda is a Buddhist site. "
        b"Xuanzang (602-664) was a monk.</p></html>"
    )

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=payload)

    monkeypatch.setattr(
        retry.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    first, second = retry.collect_dayanta_alternative(), retry.collect_dayanta_alternative()
    assert "1466" not in first.content
    assert first.heritage_id == "dayanta" and second.status == "cached"
    assert len(calls) == 1


def test_common_point_requires_both_actual_evidence_quotes():
    sources, fields = [], []
    for heritage in ("seokguram", "horyuji"):
        source = CollectedSource(
            id=heritage,
            heritage_id=heritage,
            title=heritage,
            organization="Test",
            source_url="https://www.khs.go.kr/",
            feed_url="https://www.khs.go.kr/",
            status="cached",
            content_kind="individual_text",
            content="This is a Buddhist temple.",
            retrieved_at=datetime.now(UTC),
            scope_note="Test",
        )
        sources.append(source)
        fields.append(
            ExtractedField(
                heritage_id=heritage,
                category="종교적 배경",
                value="불교",
                source_id=source.id,
                source_url=source.source_url,
                evidence_quote=source.content,
                verification_status=VerificationStatus.NEEDS_REVIEW,
                note="Test",
            )
        )
    comparison = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=fields,
    )
    assert comparison.common_evidence[0].left_evidence.source_id == "seokguram"
    assert comparison.common_evidence[0].right_evidence.source_id == "horyuji"
    comparison.collected_sources[1].status = "stale"
    assert not apply_extracted_comparison(comparison).common_evidence


def test_person_lifespan_is_not_accepted_as_pagoda_construction_date():
    source = CollectedSource(
        id="xian:dayanta",
        heritage_id="dayanta",
        title="Official description",
        organization="Xi'an",
        source_url="https://en.xa.gov.cn/",
        feed_url="https://en.xa.gov.cn/",
        content="Xuanzang (602-664) was a Buddhist monk. The pagoda was built in 652.",
        content_kind="individual_text",
        status="fresh",
        retrieved_at=datetime.now(UTC),
        scope_note="Individual description",
    )
    draft = DraftField(
        heritage_id="dayanta",
        category="시대",
        value="602-664",
        source_id=source.id,
        evidence_quote="Xuanzang (602-664) was a Buddhist monk.",
    )
    assert validate_extraction(draft, [source]) is None
    draft.value = "652"
    draft.evidence_quote = "The pagoda was built in 652."
    assert validate_extraction(draft, [source]) is not None


def test_beginner_questions_do_not_require_long_english_quotes():
    source = CollectedSource(
        id="material",
        heritage_id="seokguram",
        title="Test",
        organization="국가유산청",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        content="The grotto is granite.",
        content_kind="individual_text",
        status="cached",
        retrieved_at=datetime.now(UTC),
        scope_note="Test",
    )
    field = ExtractedField(
        heritage_id="seokguram",
        category="재료",
        value="화강암",
        source_id="material",
        evidence_quote=source.content,
        source_url=source.source_url,
        verification_status=VerificationStatus.NEEDS_REVIEW,
        note="Test",
    )
    comparison = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=[source],
        extracted_fields=[field],
    )
    quiz = generate_quiz(
        "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comparison.saved_id
    )
    assert all(len(item.question) < 100 for item in quiz.items)
    assert all(source.content not in item.question for item in quiz.items)
    assert quiz.items[0].choices[quiz.items[0].correct_index].text == "화강암"
