import json

from culturebridge.domain.models import CollectedSource
from culturebridge.services.catalog_service import get_heritage
from culturebridge.services.official_service import (
    BASE_URL,
    SEOKGURAM_CODES,
    OfficialDocumentNotFoundError,
    OfficialServiceError,
    get_official_document,
)
from culturebridge.services.unesco_service import DATAHUB_URL, search_unesco

UNESCO_IDS = {"seokguram": "736", "horyuji": "660", "dayanta": "1442"}


def collect_official_sources(
    left_id: str, right_id: str, *, refresh: bool = False
) -> list[CollectedSource]:
    # Validate both IDs before any remote request.
    items = [get_heritage(left_id), get_heritage(right_id)]
    sources = []
    for item in items:
        if item.id == "seokguram":
            source_url = (
                BASE_URL + "SearchKindOpenapiDt.do?ccbaKdcd=11&ccbaAsno=0000240000000&ccbaCtcd=37"
            )
            try:
                document = (
                    get_official_document(*SEOKGURAM_CODES, refresh=True)
                    if refresh
                    else get_official_document(*SEOKGURAM_CODES)
                )
                sources.append(
                    CollectedSource(
                        id=document.record_id,
                        heritage_id=item.id,
                        title=document.name,
                        organization="국가유산청",
                        source_url=document.source_url,
                        feed_url=document.source_url,
                        retrieved_at=document.retrieved_at,
                        content=document.content,
                        content_kind="individual_text",
                        status="stale"
                        if document.stale
                        else "cached"
                        if document.cached
                        else "fresh",
                        scope_note="개별 유산의 원문입니다. 문장별 사실 검증은 별도 단계입니다.",
                    )
                )
            except (OfficialServiceError, OfficialDocumentNotFoundError):
                sources.append(
                    CollectedSource(
                        id="khs:11:0000240000000:37",
                        heritage_id=item.id,
                        title="석굴암 상세 자료",
                        organization="국가유산청",
                        source_url=source_url,
                        feed_url=source_url,
                        status="unavailable",
                        scope_note="상세 원문 수집 실패. 자료를 수집했다고 판단하지 않습니다.",
                    )
                )
        unesco_id = UNESCO_IDS[item.id]
        source_url = f"https://whc.unesco.org/en/list/{unesco_id}/"
        try:
            response = (
                search_unesco(unesco_id, refresh=True) if refresh else search_unesco(unesco_id)
            )
            if len(response.records) != 1 or response.records[0].id != unesco_id:
                raise OfficialServiceError("UNESCO 항목을 정확하게 찾을 수 없습니다.")
            record = response.records[0]
            if getattr(response, "source_format", "xml") == "json" and not record.description:
                response = search_unesco(unesco_id, refresh=True)
                if len(response.records) != 1 or response.records[0].id != unesco_id:
                    raise OfficialServiceError("UNESCO 상세 메타데이터를 찾지 못했습니다.")
                record = response.records[0]
            scope = "등재명·국가·등재연도 메타데이터입니다. 건립연도·구조·재료의 근거는 아닙니다."
            has_text = getattr(response, "source_format", "xml") == "json" and bool(
                record.description
            )
            if has_text:
                scope = (
                    "공식 DataHub의 영문 소개입니다. 소개 범위를 벗어난 사실을 추정하지 않습니다."
                )
            if item.id == "dayanta":
                scope += " 대안탑 개별 설명이 아닌 실크로드 등재 유산군 자료입니다."
            sources.append(
                CollectedSource(
                    id=f"unesco:{unesco_id}",
                    heritage_id=item.id,
                    title=record.name,
                    organization="UNESCO",
                    source_url=record.source_url,
                    feed_url=response.feed_source_url,
                    retrieved_at=response.retrieved_at,
                    content=record.description
                    if has_text
                    else json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
                    content_kind=("individual_text" if item.id == "horyuji" else "group_text")
                    if has_text
                    else "metadata",
                    status="stale" if response.stale else "cached" if response.cached else "fresh",
                    scope_note=scope,
                    license_url=response.license_url,
                )
            )
        except OfficialServiceError:
            sources.append(
                CollectedSource(
                    id=f"unesco:{unesco_id}",
                    heritage_id=item.id,
                    title=f"UNESCO 등재 ID {unesco_id}",
                    organization="UNESCO",
                    source_url=source_url,
                    feed_url=DATAHUB_URL,
                    status="unavailable",
                    scope_note="공식 등재 항목 수집 실패. 추가 자료 확인이 필요합니다.",
                )
            )
    return sources
