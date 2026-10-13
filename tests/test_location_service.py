from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.main import app
from culturebridge.services import location_service as location
from culturebridge.services import official_service as official

DETAIL = """<result><ccbaKdcd>11</ccbaKdcd><ccbaAsno>0000240000000</ccbaAsno>
<ccbaCtcd>37</ccbaCtcd><latitude>35.794852</latitude><longitude>129.349242</longitude>
<item><ccbaMnm1>경주 석굴암 석굴</ccbaMnm1><ccmaName>국보</ccmaName><ccsiName>경주시</ccsiName>
<content>위치 테스트</content></item></result>"""
SPCA = """<spca><ccbaMnm>경주 석굴암 석굴</ccbaMnm><ccmaName>국보</ccmaName>
<vlocName>경상북도 경주시</vlocName><cnX>1100000.5</cnX><cnY>1800000.5</cnY></spca>"""
FEED = '<ns2:response xmlns:ns2="http://gis-heritage.go.kr/">' + SPCA + "</ns2:response>"


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "locations.db")
    initialize_database()
    original = httpx.Client
    options = {"feed": FEED, "status": 200, "detail": DETAIL, "calls": 0}

    def handler(request):
        if request.url.path.endswith("spca.do"):
            options["calls"] += 1
            assert request.url.params["ccbaKdcd"] == "11"
            return httpx.Response(options["status"], text=options["feed"])
        return httpx.Response(200, text=options["detail"])

    monkeypatch.setattr(
        official.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    return options


def test_location_keeps_projected_and_geographic_coordinates_separate(upstream):
    first = location.get_official_location(*official.SEOKGURAM_CODES)
    second = location.get_official_location(*official.SEOKGURAM_CODES)
    assert first.projected_x == 1100000.5
    assert first.latitude == 35.794852 and first.longitude == 129.349242
    assert "UTM-K" in first.coordinate_system
    assert not first.cached and second.cached
    assert upstream["calls"] == 1
    assert "gis-heritage.go.kr" in str(first.source_url)


@pytest.mark.parametrize("change", ["different_name", "different_city", "duplicate", "zero", "nan"])
def test_mismatched_ambiguous_or_invalid_locations_are_not_attached(upstream, change):
    if change == "different_name":
        upstream["feed"] = FEED.replace("경주 석굴암 석굴", "다른 유산")
    elif change == "different_city":
        upstream["feed"] = FEED.replace("경상북도 경주시", "서울특별시 종로구")
    elif change == "duplicate":
        upstream["feed"] = FEED.replace(SPCA, SPCA + SPCA)
    else:
        upstream["feed"] = FEED.replace("1100000.5", "0" if change == "zero" else "NaN")
    with pytest.raises((official.OfficialDocumentNotFoundError, official.OfficialServiceError)):
        location.get_official_location(*official.SEOKGURAM_CODES)


def test_stale_location_cache_survives_upstream_failure(upstream):
    location.get_official_location(*official.SEOKGURAM_CODES)
    old_date = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    with transaction() as connection:
        connection.execute("UPDATE official_location_feeds SET retrieved_at=?", (old_date,))
    upstream["status"] = 503
    result = location.get_official_location(*official.SEOKGURAM_CODES)
    assert result.stale and result.cached


def test_location_api_and_missing_geographic_coordinates(upstream):
    upstream["detail"] = DETAIL.replace("35.794852", "0")
    response = TestClient(app).get("/api/official/heritages/11/0000240000000/37/location")
    assert response.status_code == 200
    assert response.json()["latitude"] is None
    assert response.json()["longitude"] is None
    assert response.json()["projected_x"] == 1100000.5
