import pytest

from culturebridge.domain.models import LearningLevel
from culturebridge.services.catalog_service import (
    HeritageNotFoundError,
    compare_heritages,
    get_heritage,
    list_heritages,
    recommend_related,
)


def test_catalog_contains_three_initial_heritages() -> None:
    assert len(list_heritages()) == 3


def test_search_matches_name_and_country() -> None:
    assert [item.id for item in list_heritages("석굴암")] == ["seokguram"]
    assert [item.id for item in list_heritages("일본")] == ["horyuji"]


def test_related_excludes_selected_item() -> None:
    candidates = recommend_related("seokguram")
    assert {item.heritage.id for item in candidates} == {"horyuji", "dayanta"}


def test_comparison_has_sources_and_verification() -> None:
    result = compare_heritages("seokguram", "horyuji", LearningLevel.INTERMEDIATE)
    assert len(result.differences) == 4
    assert result.source_ids == ["src-seokguram-khs", "src-seokguram-unesco", "src-horyuji-unesco"]
    assert result.verification_status.value == "verified"


def test_unknown_heritage_raises_domain_error() -> None:
    with pytest.raises(HeritageNotFoundError):
        get_heritage("unknown")


def test_broad_corridor_source_does_not_verify_individual_facts():
    result = compare_heritages("seokguram", "dayanta", LearningLevel.ADVANCED)
    assert result.verification_status.value == "needs_review"
