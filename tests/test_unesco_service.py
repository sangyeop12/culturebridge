import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.main import app
from culturebridge.services import unesco_service as service
from culturebridge.services.official_service import OfficialServiceError

XML = b"""<query><row><id_number>660</id_number><site>Test Japanese monument</site>
<states>Japan</states><date_inscribed>1993</date_inscribed></row>
<row><id_number>736</id_number><site>Test Korean monument</site>
<states>Republic of Korea</states><date_inscribed>1995</date_inscribed></row></query>"""
JSON = json.dumps(
    [
        {
            "id_no": "660",
            "name_en": "Test Japanese monument",
            "states_names": ["Japan"],
            "date_inscribed": "1993",
        },
        {
            "id_no": "736",
            "name_en": "Test Korean monument",
            "states_names": ["Republic of Korea"],
            "date_inscribed": "1995",
        },
    ]
).encode()


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "unesco.db")
    initialize_database()


def test_import_search_pagination_and_no_network_on_fresh_cache(monkeypatch):
    assert service.import_unesco_xml(XML) == 2

    def fail():
        pytest.fail("A fresh imported feed must not make a network request")

    monkeypatch.setattr(service, "_download", fail)
    result = service.search_unesco("Japan")
    assert result.total == 1 and result.records[0].id == "660"
    assert result.records[0].inscription_year == "1993"
    assert result.cached and not result.stale
    assert str(result.records[0].source_url) == "https://whc.unesco.org/en/list/660/"
    assert service.search_unesco(limit=1, offset=1).records[0].id == "736"


@pytest.mark.parametrize(
    "payload",
    [
        b"<html>blocked</html>",
        b"<query/>",
        b"<query>",
        b'<!DOCTYPE query [<!ENTITY x "bad">]><query>&x;</query>',
        XML.replace(b"736", b"660"),
    ],
)
def test_invalid_import_does_not_replace_existing_feed(payload):
    service.import_unesco_xml(XML)
    with pytest.raises(OfficialServiceError):
        service.import_unesco_xml(payload)
    assert service.search_unesco().total == 2


def test_refresh_failure_keeps_stale_cache(monkeypatch):
    service.import_unesco_xml(XML)
    with transaction() as connection:
        connection.execute(
            "UPDATE unesco_feeds SET retrieved_at=?",
            ((datetime.now(UTC) - timedelta(days=2)).isoformat(),),
        )

    def fail():
        raise OfficialServiceError("403 Forbidden")

    monkeypatch.setattr(service, "_download", fail)
    result = service.search_unesco()
    assert result.stale and result.cached and result.total == 2


def test_numeric_id_search_does_not_include_partial_id_matches():
    service.import_unesco_xml(XML.replace(b"736", b"1660"))
    result = service.search_unesco("660")
    assert result.total == 1
    assert result.records[0].id == "660"


def test_download_failure_is_not_reported_as_success(monkeypatch):
    def fail():
        raise OfficialServiceError("UNESCO XML access denied")

    monkeypatch.setattr(service, "_download", fail)
    response = TestClient(app).get("/api/unesco/heritages?q=Japan")
    assert response.status_code == 502
    assert "access denied" in response.json()["detail"]


def test_successful_download_and_endpoint_validation(monkeypatch):
    monkeypatch.setattr(service, "_download", lambda: JSON)
    client = TestClient(app)
    result = client.get("/api/unesco/heritages?q=660")
    assert result.status_code == 200
    assert result.json()["records"][0]["id"] == "660"
    assert not result.json()["cached"]
    assert result.json()["source_format"] == "json"
    assert client.get("/api/unesco/heritages?limit=101").status_code == 422
    assert client.get("/unesco").status_code == 200


def test_refresh_replaces_xml_with_official_json_and_tracks_provenance(monkeypatch):
    service.import_unesco_xml(XML)
    monkeypatch.setattr(service, "_download", lambda: JSON)
    result = service.search_unesco(refresh=True)
    assert result.source_format == "json" and not result.cached and not result.stale
    assert result.feed_source_url == service.DATAHUB_URL
    assert result.license_url == service.DATAHUB_INFO_URL
    assert service.search_unesco().cached


def test_bad_json_refresh_preserves_imported_xml(monkeypatch):
    service.import_unesco_xml(XML)
    monkeypatch.setattr(service, "_download", lambda: b'{"error":"invalid response"}')
    result = service.search_unesco(refresh=True)
    assert result.source_format == "xml" and result.stale and result.total == 2
    assert service.search_unesco().source_format == "xml"


@pytest.mark.parametrize(
    "query, expected_id",
    [
        ("호류지", "660"),
        ("호 류 지", "660"),
        ("호류", "660"),
        ("법륭사", "660"),
        ("석굴암", "736"),
        ("불국사", "736"),
        ("６６０", "660"),
    ],
)
def test_korean_aliases_map_to_official_id_without_changing_names(query, expected_id):
    service.import_unesco_xml(XML)
    result = service.search_unesco(query)
    assert result.total == 1
    assert result.records[0].id == expected_id
    assert result.records[0].name.startswith("Test")


def test_country_alias_is_exact_country_not_name_keyword(monkeypatch):
    rows = json.loads(JSON)
    rows[0]["name_en"] = "China influence in Japan"
    rows.append(
        {
            "id_no": "1442",
            "name_en": "Silk Roads",
            "states_names": ["China", "Kazakhstan"],
            "date_inscribed": "2014",
        }
    )
    monkeypatch.setattr(service, "_download", lambda: json.dumps(rows).encode())
    service.search_unesco(refresh=True)
    assert [record.id for record in service.search_unesco("중국").records] == ["1442"]
    assert [record.id for record in service.search_unesco("일본").records] == ["660"]
    assert [record.id for record in service.search_unesco("한국").records] == ["736"]
    assert [record.id for record in service.search_unesco("대안탑").records] == ["1442"]


def test_suggestions_use_cache_only_and_only_suggest_present_aliases(monkeypatch):
    service.import_unesco_xml(XML)

    def fail():
        pytest.fail("Autocomplete must not call a remote API")

    monkeypatch.setattr(service, "_download", fail)
    suggestions = service.get_unesco_suggestions("호")
    assert suggestions[0].value == "호류지"
    assert suggestions[0].record_id == "660"
    assert service.search_unesco(suggestions[0].value).records[0].id == "660"
    assert not service.get_unesco_suggestions("대안")
    assert len(service.get_unesco_suggestions("", limit=3)) == 3
    client = TestClient(app)
    result = client.get("/api/unesco/suggestions?q=석")
    assert result.status_code == 200 and result.json()[0]["record_id"] == "736"
    assert client.get("/api/unesco/suggestions?limit=21").status_code == 422
