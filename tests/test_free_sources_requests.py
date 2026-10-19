from copy import deepcopy

import httpx
import pytest

from culturebridge.data.material_review import SCOPE_NOTES
from culturebridge.services import english_open_record_service as english
from culturebridge.services import open_record_service as opened
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.permission_request_service import permission_requests


def fixture_item():
    return {
        "id": english.ITEM_ID,
        "owner": "gis_historicengland",
        "url": english.SERVICE_URL,
        "licenseInfo": english.TERMS_URL,
        "accessInformation": "Released under OGL.",
        "modified": 1789038492000,
    }


def fixture_feature(identity="white-tower"):
    selected = english.ENGLISH_OPEN_RECORDS[identity]
    return {
        "features": [
            {
                "attributes": {
                    "ListEntry": selected["reference"],
                    "Name": selected["title"],
                    "hyperlink": "https://historicengland.org.uk/listing/the-list/list-entry/"
                    + str(selected["reference"]),
                }
            }
        ]
    }


def mock_provider(monkeypatch, item=None, feature=None):
    calls = []

    def get(client, url, params=None):
        calls.append((url, params))
        return (
            deepcopy(item if item is not None else fixture_item())
            if url == (english.ITEM_URL)
            else deepcopy(feature if feature is not None else fixture_feature())
        )

    monkeypatch.setattr(opened, "_get_json", get)
    return calls


def test_free_supplementary_targets_keep_the_five_existing_subjects():
    assert len(opened.AVAILABLE_OPEN_RECORDS) == 5
    assert opened.AVAILABLE_OPEN_RECORDS <= set(SCOPE_NOTES)


@pytest.mark.parametrize("identity", list(english.ENGLISH_OPEN_RECORDS))
def test_english_records_are_licensed_metadata_not_new_construction_evidence(monkeypatch, identity):
    calls = mock_provider(monkeypatch, feature=fixture_feature(identity))
    row = opened.fetch_open_record(identity)
    assert row["language"] == "en" and "Open Government" in row["license"]
    assert "Historic England" in row["attribution"] and "Ordnance Survey" in row["attribution"]
    assert "건립 연도가 아니에요" in row["guidance"]
    assert set(row["fields"]) == {"공식 등록명", "등록 번호"}
    assert calls[1][1]["returnGeometry"] == "false"
    assert "image" not in row
    if identity == "stonehenge":
        assert "인접 고분" in row["scope"]


@pytest.mark.parametrize("field", ["id", "owner", "url", "licenseInfo", "accessInformation"])
def test_provider_or_licence_changes_do_not_get_silently_accepted(monkeypatch, field):
    item = fixture_item()
    item[field] = "unverified"
    calls = mock_provider(monkeypatch, item=item)
    with pytest.raises(OfficialServiceError):
        english.fetch_english_open_record("white-tower")
    assert len(calls) == 1


@pytest.mark.parametrize("field", ["ListEntry", "Name", "hyperlink"])
def test_wrong_building_is_not_accepted(monkeypatch, field):
    row = fixture_feature()
    row["features"][0]["attributes"][field] = "other"
    mock_provider(monkeypatch, feature=row)
    with pytest.raises(OfficialServiceError):
        english.fetch_english_open_record("white-tower")


def test_ambiguous_or_truncated_record_is_not_accepted(monkeypatch):
    row = fixture_feature()
    row["exceededTransferLimit"] = True
    mock_provider(monkeypatch, feature=row)
    with pytest.raises(OfficialServiceError):
        english.fetch_english_open_record("white-tower")


def test_network_failure_and_unknown_identity(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("synthetic")

    monkeypatch.setattr(opened, "_get_json", fail)
    with pytest.raises(OfficialServiceError):
        english.fetch_english_open_record("white-tower")
    with pytest.raises(KeyError):
        english.fetch_english_open_record("https://example.invalid/")


def test_requests_cover_all_25_grouped_by_rights_policy_and_commit_no_fee():
    rows = permission_requests("Synthetic school", "Synthetic course", "Synthetic student")
    assert len(rows) == 14
    assert {r["id"] for group in rows for r in group["sources"]} == set(SCOPE_NOTES)
    assert sum(len(group["sources"]) for group in rows) == 25
    for row in rows:
        assert row["free_only"] and row["status"] == "draft_not_sent"
        assert not row["recipient_verified"]
        assert "cannot accept any licence, processing, handling or other fee" in row["body"]
        assert "Please do not begin any chargeable work" in row["body"]
        assert "No response will be treated as no permission" in row["body"]
        assert all(f"{number}. " in row["body"] for number in range(1, 5))


def test_requests_are_drafts_even_if_a_reply_address_is_provided():
    rows = permission_requests("Synthetic school", "Course", "Student", "fixture@example.invalid")
    assert all(row["status"] == "draft_not_sent" for row in rows)


def test_blank_school_is_not_invented():
    with pytest.raises(ValueError):
        permission_requests("", "Course", "Student")
