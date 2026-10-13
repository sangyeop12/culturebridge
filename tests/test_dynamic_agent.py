from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents.autonomous import AutonomousRequest, run_autonomous
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.official_models import OfficialSearchResult
from culturebridge.main import app
from culturebridge.services import agent_discovery_service as discovery
from culturebridge.services import dynamic_heritage_service as dynamic
from culturebridge.services.catalog_service import get_heritage
from culturebridge.services.comparison_service import get_saved_comparison
from culturebridge.services.quiz_service import grade_quiz
from culturebridge.services.unesco_service import UnescoRecord, UnescoResult


@pytest.fixture
def configured(tmp_path, monkeypatch):
    from culturebridge.services import name_registry_service

    monkeypatch.setattr(name_registry_service, "ensure_name", lambda *a: None)
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "dynamic.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    records = {
        "101": UnescoRecord(
            id="101",
            name="Test Buddhist Temple",
            countries="India",
            inscription_year="2000",
            source_url="https://whc.unesco.org/en/list/101/",
            description="Built in the 8th century. It is a Buddhist temple with a wooden layout.",
        ),
        "202": UnescoRecord(
            id="202",
            name="Another Buddhist Temple",
            countries="Japan",
            inscription_year="2001",
            source_url="https://whc.unesco.org/en/list/202/",
            description="Built in the 7th century. It is a Buddhist temple with a wooden layout.",
        ),
    }
    calls = []

    def search(query, **kwargs):
        calls.append(query)
        selected = [records[query]] if query in records else [records["202"]]
        return UnescoResult(
            records=selected,
            total=len(selected),
            retrieved_at=datetime.now(UTC),
            cached=True,
            stale=False,
        )

    monkeypatch.setattr(dynamic, "search_unesco", search)
    monkeypatch.setattr(discovery, "search_unesco", search)
    monkeypatch.setattr(
        discovery,
        "search_official_heritages",
        lambda *args, **kwargs: OfficialSearchResult(items=[], total=0, page=1, page_size=10),
    )
    return records, calls


def test_new_official_target_runs_end_to_end_without_catalog_code(configured):
    result = run_autonomous(
        AutonomousRequest(target=dynamic.OfficialTarget(provider="unesco", record_id="101"))
    )
    assert result["target"]["id"] == "unesco:101"
    assert result["comparison"]["right"]["id"] == "unesco:202"
    assert len(result["quiz"]["items"]) == 5
    assert result["comparison"]["common_evidence"]
    assert get_heritage("unesco:101").period == "근거 부족"  # no registration-time fact promotion
    saved = get_saved_comparison(result["comparison"]["saved_id"]).comparison
    assert saved.left.id == "unesco:101" and len(saved.extracted_fields) == 8
    assert grade_quiz(result["quiz"]["quiz_id"], [0, 3, 2, 1, 0]).score == 5
    assert "Buddhist" in configured[1]


def test_no_semantic_candidate_holds_without_fake_comparison(configured):
    configured[0]["202"].description = "A modern industrial location."
    configured[0]["202"].name = "Industrial site"
    result = run_autonomous(
        AutonomousRequest(target=dynamic.OfficialTarget(provider="unesco", record_id="101"))
    )
    assert not result["candidates"]
    assert result["comparison"] is result["quiz"] is None


def test_planner_selects_provider_search_queries_and_only_returned_candidates(
    configured, monkeypatch
):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(
        discovery,
        "_model_plan",
        lambda *args: discovery.SearchPlan(
            queries=["Buddhist"], reason="원문 불교 배경에 따른 검색"
        ),
    )
    monkeypatch.setattr(
        discovery,
        "_model_selection",
        lambda *args: discovery.CandidateSelection(
            indices=[0], reason="확보한 후보의 불교 구조 비교"
        ),
    )
    # Only discovery uses the model; subsequent extraction/quiz isn't needed for this assertion.
    _, candidates, trace, used_ai = discovery.discover_candidates(
        dynamic.OfficialTarget(provider="unesco", record_id="101")
    )
    assert used_ai and candidates[0].heritage.id == "unesco:202"
    assert any("선택" in step for step in trace)


def test_unesco_entity_scope_is_not_a_member_building(configured):
    configured[0]["101"].name = "Two Temples and their Surroundings"
    detail, source = dynamic.fetch_target(
        dynamic.OfficialTarget(provider="unesco", record_id="101")
    )
    assert detail.name == "Two Temples and their Surroundings"
    assert source.content_kind == "listed_text" and "전체" in source.scope_note
    assert detail.period != "2000"  # inscription year is never used as construction


def test_api_rejects_arbitrary_url_and_incomplete_ids(configured):
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/autonomous-explorations",
                json={"target": {"provider": "unesco", "record_id": "http://127.0.0.1/"}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/autonomous-explorations", json={"target": {"provider": "khs"}}
            ).status_code
            == 422
        )
        result = client.post(
            "/api/autonomous-explorations",
            json={"target": {"provider": "unesco", "record_id": "101"}},
        )
    assert result.status_code == 200 and result.json()["comparison"]


def test_discovery_page_waits_before_remote_calls(configured, monkeypatch):
    from culturebridge.ui import pages

    def fail(*args):
        pytest.fail("Remote work must await browser connection")

    monkeypatch.setattr(pages, "run_autonomous", fail)
    with TestClient(app) as client:
        response = client.get("/discover/unesco/101")
    assert response.status_code == 200 and "비교 후보를 탐색" in response.text


def test_new_targets_questions_use_same_snapshot_and_quiz_requires_evidence(configured):
    from culturebridge.services.question_service import answer_question

    result = run_autonomous(
        AutonomousRequest(target=dynamic.OfficialTarget(provider="unesco", record_id="101"))
    )
    comparison = result["comparison"]
    answer = answer_question(
        "unesco:101",
        "unesco:202",
        "두 유산의 재료는?",
        comparison["level"],
        comparison_id=comparison["saved_id"],
        use_ai=False,
    )
    assert "wooden" in answer.answer and answer.source_ids
    assert answer.verification_status.value == "needs_review"
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/quizzes", json={"left_id": "unesco:101", "right_id": "unesco:202"}
            ).status_code
            == 422
        )


def test_same_korean_country_label_does_not_score_as_foreign():
    assert not discovery._different_country("대한민국", "Republic of Korea")
    assert discovery._different_country("대한민국", "China")


def test_model_cannot_choose_an_index_outside_official_results(configured, monkeypatch):
    from types import SimpleNamespace

    class FakeClient:
        models = SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(
                text='{"indices":[99],"reason":"없는 후보"}'
            )
        )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(discovery.genai, "Client", lambda **kwargs: FakeClient())
    detail, _ = dynamic.fetch_target(dynamic.OfficialTarget(provider="unesco", record_id="101"))
    target = dynamic.OfficialTarget(provider="unesco", record_id="202")
    with pytest.raises(ValueError):
        discovery._model_selection(
            detail,
            "compare",
            [(1, target, "Test", "Japan", set())],
            {target.id: (target, "Test", "Japan", "Buddhist temple")},
        )


def test_model_discovery_is_not_limited_to_local_theme_dictionary(configured, monkeypatch):
    configured[0]["101"].name = "An unclassified ceremonial site"
    configured[0]["101"].description = "A landscape containing archaeological evidence."
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(
        discovery,
        "_model_plan",
        lambda *args: discovery.SearchPlan(
            queries=["archaeological"], reason="제공 원문을 기준으로 탐색"
        ),
    )
    monkeypatch.setattr(
        discovery,
        "_model_selection",
        lambda *args: discovery.CandidateSelection(
            indices=[0], reason="검색된 후보 중 검토 대상으로 선정"
        ),
    )
    _, candidates, _, used_ai = discovery.discover_candidates(
        dynamic.OfficialTarget(provider="unesco", record_id="101")
    )
    assert used_ai and candidates
    assert "추가 검토" in candidates[0].criteria[0]
