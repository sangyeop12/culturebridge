"""Additional licensed official records; never replace a subject or approve another source."""

import re
from datetime import date

import httpx

from culturebridge.config import get_settings
from culturebridge.services.official_service import OfficialServiceError

DATASET_ID = "5af120e5b595087cfabcde81"
RESOURCE_ID = "3a52af4a-f9da-4dcc-8110-b07774dfb3bc"
DATASET_URL = f"https://www.data.gouv.fr/api/1/datasets/{DATASET_ID}/"
CATALOGUE_URL = f"https://culture.data.gouv.fr/datasets/{DATASET_ID}"
RECORDS_URL = f"https://tabular-api.data.gouv.fr/api/resources/{RESOURCE_ID}/data/"
LICENSE_URL = "https://www.data.gouv.fr/pages/legal/licences/etalab-2.0"
PUBLISHER_ID = "534fff91a3a7292c64a77f73"

# Exact reference, title and locality, not a keyword guess about a similarly named building.
OPEN_RECORDS = {
    "mont-saint-michel-abbey": {
        "reference": "PA00110460",
        "title": "Abbaye et dépendances",
        "locality": "Mont-Saint-Michel (Le)",
        "scope": "몽생미셸 수도원과 부속 시설의 기록이에요. 섬·만 전체의 설명은 아니에요.",
    },
    "sainte-chapelle": {
        "reference": "PA00086001",
        "title": "Sainte-Chapelle",
        "locality": "Paris 1er Arrondissement",
        "scope": "파리의 생트샤펠 건물 기록이에요. 다른 도시의 동명 예배당과 구분해요.",
    },
}


def _get_json(client, url, params=None):
    with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > 1_000_000:
                raise ValueError("Record response too large")
    import json

    return json.loads(payload)


def fetch_open_record(identity):
    """No API key, foreign AI call, arbitrary URL, image download, or learner DB mutation."""
    if identity not in OPEN_RECORDS:
        raise KeyError(identity)
    selected = OPEN_RECORDS[identity]
    try:
        with httpx.Client(
            timeout=min(get_settings().heritage_timeout_seconds, 15),
            follow_redirects=False,
            headers={"User-Agent": "CultureBridge/0.1"},
        ) as client:
            dataset = _get_json(client, DATASET_URL)
            # Check the licence at the actual dataset, not the publisher's general website.
            if (
                dataset.get("license") != "lov2"
                or (dataset.get("organization") or {}).get("id") != PUBLISHER_ID
                or not any(r.get("id") == RESOURCE_ID for r in dataset.get("resources", []))
            ):
                raise ValueError("Dataset provenance or licence changed")
            response = _get_json(
                client,
                RECORDS_URL,
                {"Reference__exact": selected["reference"], "page_size": 1},
            )
        records = response.get("data", [])
        if len(records) != 1 or response.get("meta", {}).get("total") != 1:
            raise ValueError("Ambiguous record")
        record = records[0]
        if (
            record.get("Reference") != selected["reference"]
            or record.get("Titre_editorial_de_la_notice") != selected["title"]
            or record.get("Commune_forme_index") != selected["locality"]
        ):
            raise ValueError("Subject does not match")
        updated = record.get("Date_de_la_derniere_mise_a_jour", "")
        date.fromisoformat(updated)  # Required attribution must include the data's update date.
        fields = {
            "유산 이름": record["Titre_editorial_de_la_notice"],
            "지역": record["Commune_forme_index"],
            "건축 시기": record.get("Siecle_de_la_campagne_principale_de_construction"),
            "공식 역사 설명": record.get("Historique"),
            "공식 구조 설명": record.get("Description_de_l_edifice"),
        }
        century = fields["건축 시기"] or ""
        guidance = ""
        if re.fullmatch(r"\d{1,2}e siècle(?:;\d{1,2}e siècle)*", century):
            guidance = (
                "원문에 제시된 시기: "
                + " · ".join(part.removesuffix("e siècle") + "세기" for part in century.split(";"))
                + ". 시작·완공 연도나 연속 공사 기간을 단정하지 않아요."
            )
        return {
            "heritage_id": "official:" + identity,
            "reference": selected["reference"],
            "scope": selected["scope"],
            "language": "fr",
            "fields": {key: value for key, value in fields.items() if value},
            "guidance": guidance,
            "source_url": "https://pop.culture.gouv.fr/notice/merimee/" + selected["reference"],
            "dataset_url": CATALOGUE_URL,
            "license_url": LICENSE_URL,
            "license": "Licence Ouverte 2.0",
            "updated_at": updated,
            "attribution": "Ministère de la Culture · Monuments historiques · " + updated,
            "notices": [
                "공식 공개 데이터의 텍스트 필드만 연결했어요. 사진·로고는 포함하지 않아요.",
                "한국어 항목명과 시기 안내는 읽기 도움말이며 공식 번역·기관의 인증이 아니에요.",
                "이 데이터의 이용 조건을 다른 기관 원문에 적용하지 않아요.",
                "기존 비교·퀴즈의 근거를 자동으로 이 기록으로 바꾸지는 않아요.",
            ],
        }
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise OfficialServiceError(
            "추가 기록의 대상·이용 조건·연결을 확인하지 못했어요. "
            "기존 학습은 계속 이용할 수 있어요."
        ) from exc
