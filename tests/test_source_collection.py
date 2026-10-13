from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from culturebridge.agents.workflow import exploration_graph
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.services import source_collection_service as collector
from culturebridge.services.catalog_service import HeritageNotFoundError
from culturebridge.services.comparison_service import get_saved_comparison
from culturebridge.services.official_service import OfficialServiceError


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "research.db")
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    initialize_database()
    now = datetime.now(UTC)
    options = {"stale": False, "unavailable": False, "calls": []}

    def khs(*args):
        options["calls"].append("khs")
        if options["unavailable"]:
            raise OfficialServiceError("Test failure")
        return SimpleNamespace(
            record_id="khs:11:0000240000000:37",
            name="석굴암 상세",
            source_url="https://www.khs.go.kr/cha/SearchKindOpenapiDt.do",
            retrieved_at=now,
            content="수집 원문 테스트",
            stale=options["stale"],
            cached=True,
        )

    def unesco(record_id):
        options["calls"].append(record_id)
        if options["unavailable"]:
            raise OfficialServiceError("Test failure")
        from culturebridge.services.unesco_service import UnescoRecord

        return SimpleNamespace(
            records=[
                UnescoRecord(
                    id=record_id,
                    name="Official record " + record_id,
                    countries="Test",
                    inscription_year="1993",
                    source_url=f"https://whc.unesco.org/en/list/{record_id}/",
                )
            ],
            feed_source_url="https://data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json",
            retrieved_at=now,
            stale=options["stale"],
            cached=True,
            license_url="https://data.unesco.org/explore/dataset/whc001/information/",
        )

    monkeypatch.setattr(collector, "get_official_document", khs)
    monkeypatch.setattr(collector, "search_unesco", unesco)
    return options


def test_graph_collects_both_targets_and_persists_snapshot(sources):
    state = exploration_graph.invoke(
        {"heritage_id": "seokguram", "comparison_id": "horyuji", "level": "advanced"}
    )
    assert sources["calls"] == ["khs", "736", "660"]
    assert len(state["collected_sources"]) == 3
    saved = get_saved_comparison(state["comparison"]["saved_id"])
    assert [s.model_dump(mode="json") for s in saved.comparison.collected_sources] == state[
        "collected_sources"
    ]
    assert len(saved.comparison.extracted_fields) == 6
    assert [field.model_dump(mode="json") for field in saved.comparison.extracted_fields] == state[
        "extracted_fields"
    ]
    sources["unavailable"] = True
    assert (
        get_saved_comparison(saved.id).comparison.collected_sources[0].content == "수집 원문 테스트"
    )


@pytest.mark.parametrize("mode", ["stale", "unavailable"])
def test_failed_or_old_collection_does_not_claim_complete_verification(sources, mode):
    sources[mode] = True
    state = exploration_graph.invoke({"heritage_id": "seokguram", "level": "beginner"})
    assert state["verification_status"] == "needs_review"
    expected = "stale" if mode == "stale" else "unavailable"
    assert all(s["status"] == expected for s in state["collected_sources"])
    if mode == "unavailable":
        assert all(not s["content"] for s in state["collected_sources"])


def test_dayanta_is_scoped_to_group_metadata(sources):
    collected = collector.collect_official_sources("horyuji", "dayanta")
    assert sources["calls"] == ["660", "1442"]
    assert "유산군" in collected[1].scope_note
    assert "건립연도" in collected[1].scope_note


def test_bad_target_is_rejected_before_remote_collection(sources):
    with pytest.raises(HeritageNotFoundError):
        collector.collect_official_sources("seokguram", "missing")
    assert sources["calls"] == []
