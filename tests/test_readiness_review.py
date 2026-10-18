from datetime import UTC, datetime

import pytest

from culturebridge.domain.models import CollectedSource
from culturebridge.services.extraction_service import DraftField, validate_extraction


@pytest.mark.parametrize("lifespan", ["(602-664)", "(602–664)", "（602—664）"])
def test_person_lifespan_is_not_a_building_date(lifespan):
    text = f"The pagoda construction was supervised by the monk Example {lifespan}."
    source = CollectedSource(
        id="test",
        heritage_id="test",
        title="Example Pagoda",
        organization="Synthetic",
        source_url="https://example.org/",
        feed_url="https://example.org/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        content=text,
        scope_note="Synthetic test fixture, not historical evidence.",
    )
    draft = DraftField(
        heritage_id="test", source_id="test", category="시대", value=text, evidence_quote=text
    )
    assert validate_extraction(draft, [source]) is None
    dated = text[:-1] + " in 650."
    source.content = dated
    draft.value = draft.evidence_quote = dated
    assert validate_extraction(draft, [source]) is not None


@pytest.mark.parametrize(
    "category,text",
    [
        (
            "시대",
            "Since 1979, the Palace has been listed as a World Heritage "
            "and is a great achievement of 17th century art.",
        ),
        (
            "재료",
            "The new palace was named Petit Palace to distinguish it "
            "from the existing Marble Palace.",
        ),
    ],
)
def test_listing_year_and_other_palace_material_are_not_subject_features(category, text):
    source = CollectedSource(
        id="test",
        heritage_id="test",
        title="Example Palace",
        organization="Synthetic",
        source_url="https://example.org/",
        feed_url="https://example.org/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        content=text,
        scope_note="Synthetic test fixture",
    )
    draft = DraftField(
        heritage_id="test", source_id="test", category=category, value=text, evidence_quote=text
    )
    assert validate_extraction(draft, [source]) is None


def test_parenthesised_era_is_not_a_person_lifespan():
    text = "The palace was built in the Edo period (1603–1867)."
    source = CollectedSource(
        id="test",
        heritage_id="test",
        title="Example Palace",
        organization="Synthetic",
        source_url="https://example.org/",
        feed_url="https://example.org/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        content=text,
        scope_note="Synthetic test fixture",
    )
    draft = DraftField(
        heritage_id="test", source_id="test", category="시대", value=text, evidence_quote=text
    )
    assert validate_extraction(draft, [source]) is not None
