"""Allowlisted Historic England OGL data, not scraped web descriptions or photographs."""

from datetime import UTC, datetime

import httpx

from culturebridge.config import get_settings
from culturebridge.services.official_service import OfficialServiceError

ITEM_ID = "767f279327a24845bf47dfe5eae9862b"
ITEM_URL = f"https://www.arcgis.com/sharing/rest/content/items/{ITEM_ID}"
SERVICE_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/"
    "National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer"
)
TERMS_URL = "https://historicengland.org.uk/terms/website-terms-conditions/open-data-hub/"
LICENSE_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

ENGLISH_OPEN_RECORDS = {
    "white-tower": {
        "reference": 1260258,
        "layer": 0,
        "title": "THE WHITE TOWER",
        "scope": "화이트 타워 건물의 공식 등록 기록이에요. 런던탑 전체와 구분해요.",
    },
    "durham-cathedral": {
        "reference": 1161023,
        "layer": 0,
        "title": "CATHEDRAL CHURCH OF CHRIST AND ST MARY THE VIRGIN",
        "scope": "더럼 대성당 건물의 공식 등록 기록이에요. 더럼 성과 구분해요.",
    },
    "stonehenge": {
        "reference": 1010140,
        "layer": 6,
        "title": "Stonehenge, the Avenue, and three barrows adjacent to the Avenue "
        "forming part of a round barrow cemetery on Countess Farm",
        "scope": "스톤헨지와 진입로·인접 고분을 함께 지정한 기록이에요. "
        "스톤헨지 돌 구조물 하나의 설명으로 확대하지 않아요.",
    },
}


def fetch_english_open_record(identity):
    from culturebridge.services.open_record_service import _get_json

    if identity not in ENGLISH_OPEN_RECORDS:
        raise KeyError(identity)
    selected = ENGLISH_OPEN_RECORDS[identity]
    try:
        with httpx.Client(
            timeout=min(get_settings().heritage_timeout_seconds, 15), follow_redirects=False
        ) as client:
            item = _get_json(client, ITEM_URL, {"f": "json"})
            if (
                item.get("id") != ITEM_ID
                or item.get("owner") != "gis_historicengland"
                or item.get("url") != SERVICE_URL
                or TERMS_URL not in item.get("licenseInfo", "")
                or "Released under OGL" not in item.get("accessInformation", "")
            ):
                raise ValueError("Provider or licence changed")
            updated = datetime.fromtimestamp(item["modified"] / 1000, UTC).date().isoformat()
            result = _get_json(
                client,
                f"{SERVICE_URL}/{selected['layer']}/query",
                {
                    "f": "json",
                    "where": f"ListEntry={selected['reference']}",
                    "returnGeometry": "false",
                    "outFields": "ListEntry,Name,hyperlink",
                },
            )
        features = result.get("features", [])
        if len(features) != 1 or result.get("exceededTransferLimit"):
            raise ValueError("Ambiguous record")
        row = features[0]["attributes"]
        source_url = "https://historicengland.org.uk/listing/the-list/list-entry/" + str(
            selected["reference"]
        )
        if (
            row.get("ListEntry") != selected["reference"]
            or row.get("Name") != selected["title"]
            or row.get("hyperlink") != source_url
        ):
            raise ValueError("Subject does not match")
        year = updated[:4]
        return {
            "heritage_id": "official:" + identity,
            "reference": str(selected["reference"]),
            "scope": selected["scope"],
            "language": "en",
            "organization": "Historic England",
            "fields": {"공식 등록명": row["Name"], "등록 번호": str(row["ListEntry"])},
            "guidance": "공식 등록을 확인하는 보충 자료예요. "
            "등록 번호나 지정일은 건립 연도가 아니에요.",
            "source_url": source_url,
            "dataset_url": "https://www.arcgis.com/home/item.html?id=" + ITEM_ID,
            "license": "Open Government Licence v3.0",
            "license_url": LICENSE_URL,
            "terms_url": TERMS_URL,
            "updated_at": updated,
            "attribution": f"© Historic England {year}. Contains Ordnance Survey data "
            f"© Crown copyright and database right {year}.",
            "notices": [
                "무료 공개 데이터의 등록 정보만 사용해요. "
                "사진·로고·웹페이지의 긴 설명은 포함하지 않아요.",
                "한국어 항목명과 안내는 읽기 도움말이며 기관의 공식 번역·인증이 아니에요.",
                "이 기록이 원래 기관 설명문의 번역·AI 처리·재배포를 허가하는 것은 아니에요.",
                "기존 비교·퀴즈 근거는 자동으로 바꾸지 않아요.",
            ],
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise OfficialServiceError(
            "추가 공개 기록의 대상·이용 조건을 확인하지 못했어요. "
            "기존 학습은 계속 이용할 수 있어요."
        ) from exc
