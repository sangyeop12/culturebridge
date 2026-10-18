from copy import deepcopy

import httpx
import pytest

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.services import open_record_service as records
from culturebridge.services.classroom_usage_service import PURPOSE_LABELS, classroom_usage
from culturebridge.services.individual_source_service import search_individuals
from culturebridge.services.material_review_service import material_review, review_markdown
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.source_permission_service import (
    external_ai_allowed,
    permission_status,
    record_permission,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "usage.db")
    initialize_database()


def dataset():
    return {
        "license": "lov2",
        "organization": {"id": records.PUBLISHER_ID},
        "resources": [{"id": records.RESOURCE_ID}],
    }


def response(identity="mont-saint-michel-abbey"):
    expected = records.OPEN_RECORDS[identity]
    return {
        "meta": {"total": 1},
        "data": [
            {
                "Reference": expected["reference"],
                "Titre_editorial_de_la_notice": expected["title"],
                "Commune_forme_index": expected["locality"],
                "Date_de_la_derniere_mise_a_jour": "2026-03-04",
                "Siecle_de_la_campagne_principale_de_construction": "11e siècle;16e siècle",
                "Historique": "SYNTHETIC_TEXT",
                "image": "https://example.invalid/not-downloaded.jpg",
            }
        ],
    }


def mock_json(monkeypatch, metadata=None, payload=None):
    calls = []

    def get(client, url, params=None):
        calls.append((url, params))
        return (
            deepcopy(metadata if metadata is not None else dataset())
            if url == (records.DATASET_URL)
            else deepcopy(payload if payload is not None else response())
        )

    monkeypatch.setattr(records, "_get_json", get)
    return calls


def test_all_25_sources_keep_four_classroom_assessments_without_permission():
    before = [row.id for row in search_individuals()]
    rows = material_review()
    assert len(rows) == 25
    for row in rows:
        assessment = row["classroom_usage"]
        assert assessment["context"].startswith("비상업 개인·수업")
        assert set(assessment["purposes"]) == set(PURPOSE_LABELS)
        assert all(not item["approved"] for item in assessment["purposes"].values())
    assert [row.id for row in search_individuals()] == before
    assert "서버 저장·화면 표시" in review_markdown()


def test_education_exception_is_not_blanket_ai_or_translation_permission():
    result = classroom_usage("https://www.sainte-chapelle.fr/en/discover/example")
    assert result["purposes"]["storage_display"]["status"] == "educational_exception_review"
    assert result["purposes"]["ai"]["status"] == "not_established"
    assert result["purposes"]["translation"]["status"] == "not_established"
    assert not external_ai_allowed(["official:sainte-chapelle"])


def test_host_matching_does_not_trust_a_suffix_lookalike():
    row = classroom_usage("https://japan.travel.example.invalid/")
    assert row["policy_url"] is None
    assert all(p["status"] == "not_established" for p in row["purposes"].values())


def test_storage_purpose_is_separate_from_ai_and_translation():
    record_permission("toji-pagoda", "storage_display", True, "Synthetic fixture only")
    assert external_ai_allowed(["official:toji-pagoda"], "storage_display")
    assert not external_ai_allowed(["official:toji-pagoda"], "ai")
    assert not external_ai_allowed(["official:toji-pagoda"], "translation")


def test_recorded_approval_is_visible_without_approving_other_purposes():
    record_permission("toji-pagoda", "ai", True, "Synthetic fixture only, not a real grant")
    row = next(r for r in material_review() if r["id"] == "official:toji-pagoda")
    assert row["classroom_usage"]["purposes"]["ai"]["approved"]
    assert not row["classroom_usage"]["purposes"]["translation"]["approved"]
    assert "미확인" not in row["ai_permission"]
    record_permission("toji-pagoda", "ai", False, "Synthetic revocation")
    assert permission_status("toji-pagoda", "ai") == "denied"
    assert not external_ai_allowed(["official:toji-pagoda"])


def test_changing_source_url_requires_new_review(monkeypatch):
    from culturebridge.services.individual_source_service import INDIVIDUALS

    record_permission("toji-pagoda", "ai", True, "Synthetic fixture only")
    monkeypatch.setitem(INDIVIDUALS["toji-pagoda"], "url", "https://www.japan.travel/other/")
    assert permission_status("toji-pagoda", "ai") == "needs_rereview"
    assert not external_ai_allowed(["official:toji-pagoda"])


def test_legacy_unbound_approval_does_not_grant_a_new_source_permission():
    record_permission("toji-pagoda", "ai", True, "Synthetic legacy fixture")
    with transaction() as connection:
        connection.execute("DELETE FROM source_permission_bindings")
    assert permission_status("toji-pagoda", "ai") == "needs_rereview"
    assert not external_ai_allowed(["official:toji-pagoda"])


def test_invalid_purpose_is_rejected():
    with pytest.raises(ValueError):
        permission_status("toji-pagoda", "other")
    with pytest.raises(ValueError):
        record_permission("toji-pagoda", "other", True, "Synthetic fixture")


def test_open_record_has_attribution_scope_and_no_images(monkeypatch):
    calls = mock_json(monkeypatch)
    row = records.fetch_open_record("mont-saint-michel-abbey")
    assert row["heritage_id"] == "official:mont-saint-michel-abbey"
    assert "2026-03-04" in row["attribution"]
    assert "11세기 · 16세기" in row["guidance"]
    assert "연속 공사 기간을 단정하지" in row["guidance"]
    assert "not-downloaded" not in str(row)
    assert len(calls) == 2
    assert calls[1][1]["Reference__exact"] == "PA00110460"


@pytest.mark.parametrize("change", ["license", "publisher", "resource"])
def test_dataset_changes_fail_without_approving_or_replacing_originals(monkeypatch, change):
    metadata = dataset()
    if change == "license":
        metadata["license"] = "other"
    elif change == "publisher":
        metadata["organization"]["id"] = "other"
    else:
        metadata["resources"] = []
    calls = mock_json(monkeypatch, metadata=metadata)
    with pytest.raises(OfficialServiceError):
        records.fetch_open_record("mont-saint-michel-abbey")
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["reference", "title", "locality", "date", "count"])
def test_record_identity_and_update_date_required(monkeypatch, change):
    payload = response()
    key = {
        "reference": "Reference",
        "title": "Titre_editorial_de_la_notice",
        "locality": "Commune_forme_index",
        "date": "Date_de_la_derniere_mise_a_jour",
    }
    if change == "count":
        payload["meta"]["total"] = 2
    else:
        payload["data"][0][key[change]] = "different"
    mock_json(monkeypatch, payload=payload)
    with pytest.raises(OfficialServiceError):
        records.fetch_open_record("mont-saint-michel-abbey")


def test_second_record_and_unknown_target(monkeypatch):
    calls = mock_json(monkeypatch, payload=response("sainte-chapelle"))
    assert records.fetch_open_record("sainte-chapelle")["reference"] == "PA00086001"
    assert len(calls) == 2
    with pytest.raises(KeyError):
        records.fetch_open_record("https://example.invalid/")
    assert len(calls) == 2


def test_network_failure_preserves_original_path(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("synthetic failure")

    monkeypatch.setattr(records, "_get_json", fail)
    with pytest.raises(OfficialServiceError, match="기존 학습은 계속"):
        records.fetch_open_record("sainte-chapelle")


def test_json_response_size_is_bounded():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 1_000_001))
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError, match="too large"):
        records._get_json(client, "https://www.data.gouv.fr/test")
