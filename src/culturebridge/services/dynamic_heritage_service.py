"""Resolve typed official identifiers; never fetch a user/model supplied URL."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource, HeritageDetail, VerificationStatus
from culturebridge.services.official_service import OfficialServiceError, get_official_document
from culturebridge.services.unesco_service import search_unesco


class OfficialTarget(BaseModel):
    provider: Literal["khs", "unesco"]
    record_id: str | None = Field(default=None, pattern=r"^\d{1,10}$")
    kind: str | None = Field(default=None, pattern=r"^\d{2}$")
    number: str | None = Field(default=None, pattern=r"^\d{1,20}$")
    region: str | None = Field(default=None, pattern=r"^\d{2}$")

    @model_validator(mode="after")
    def complete_identifier(self):
        if self.provider == "unesco" and not self.record_id:
            raise ValueError("UNESCO 등재 ID가 필요합니다.")
        if self.provider == "khs" and not all((self.kind, self.number, self.region)):
            raise ValueError("국가유산청 종목·번호·지역 코드가 필요합니다.")
        return self

    @property
    def id(self):
        return (
            f"unesco:{self.record_id}"
            if self.provider == "unesco"
            else f"khs:{self.kind}:{self.number}:{self.region}"
        )


def fetch_target(target: OfficialTarget, refresh=False):
    if target.provider == "khs":
        document = get_official_document(target.kind, target.number, target.region, refresh=refresh)
        source = CollectedSource(
            id=target.id,
            heritage_id=target.id,
            title=document.name,
            organization="국가유산청",
            source_url=document.source_url,
            feed_url=document.source_url,
            retrieved_at=document.retrieved_at,
            content=document.content,
            status="stale" if document.stale else "cached" if document.cached else "fresh",
            content_kind="individual_text",
            scope_note="선택한 공식 식별자의 개별 원문입니다.",
        )
        name, country, location = document.name, "대한민국", document.address
    else:
        result = search_unesco(target.record_id, refresh=refresh)
        if len(result.records) != 1 or result.records[0].id != target.record_id:
            raise OfficialServiceError("선택한 UNESCO 기록을 정확히 확인하지 못했습니다.")
        record = result.records[0]
        source = CollectedSource(
            id=target.id,
            heritage_id=target.id,
            title=record.name,
            organization="UNESCO",
            source_url=record.source_url,
            feed_url=result.feed_source_url,
            retrieved_at=result.retrieved_at,
            content=record.description,
            status="stale" if result.stale else "cached" if result.cached else "fresh",
            content_kind="listed_text" if record.description else "metadata",
            license_url=result.license_url,
            scope_note="공식 등재명 전체를 탐구 단위로 사용합니다. "
            "유산군을 구성 건물 하나로 바꾸지 않습니다. "
            "등재연도는 건립연도가 아닙니다.",
        )
        name, country, location = record.name, record.countries, record.countries
    detail = HeritageDetail(
        id=target.id,
        name=name,
        country=country,
        location=location,
        summary="공식 검색에서 선택한 동적 탐구 대상입니다. 항목별 근거 추출 전입니다.",
        period="근거 부족",
        structure="근거 부족",
        material="근거 부족",
        religious_context="근거 부족",
        source_ids=[source.id],
        verification_status=VerificationStatus.INSUFFICIENT_EVIDENCE,
    )
    with transaction() as connection:
        connection.execute(
            """INSERT INTO heritages(
            id,name,country,period,location,summary,structure,material,religious_context)
            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (
                detail.id,
                name,
                country,
                detail.period,
                location,
                detail.summary,
                detail.structure,
                detail.material,
                detail.religious_context,
            ),
        )
        connection.execute(
            """INSERT INTO dynamic_heritages(id,detail_json,source_json,target_json) VALUES(?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET detail_json=excluded.detail_json,
            source_json=excluded.source_json,target_json=excluded.target_json""",
            (
                target.id,
                detail.model_dump_json(),
                source.model_dump_json(),
                target.model_dump_json(),
            ),
        )
        if source.retrieved_at:
            connection.execute(
                """INSERT INTO sources(
                id,heritage_id,title,organization,url,retrieved_at,license_note,summary,scope_note)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,organization=excluded.organization,url=excluded.url,
                retrieved_at=excluded.retrieved_at,license_note=excluded.license_note,
                summary=excluded.summary,scope_note=excluded.scope_note""",
                (
                    source.id,
                    detail.id,
                    source.title,
                    source.organization,
                    str(source.source_url),
                    source.retrieved_at.date().isoformat(),
                    str(source.license_url) if source.license_url else None,
                    source.content,
                    source.scope_note,
                ),
            )
    return detail, source


def dynamic_source(heritage_id, refresh=False):
    with transaction() as connection:
        row = connection.execute(
            "SELECT * FROM dynamic_heritages WHERE id=?", (heritage_id,)
        ).fetchone()
    if not row:
        return None
    source = CollectedSource.model_validate_json(row["source_json"])
    expired = source.retrieved_at is None or datetime.now(UTC) - source.retrieved_at > timedelta(
        hours=get_settings().heritage_cache_hours
    )
    if refresh or expired:
        try:
            return fetch_target(OfficialTarget.model_validate_json(row["target_json"]), True)[1]
        except OfficialServiceError:
            source.status = "stale"
            source.scope_note += " 공식 재조회 실패로 갱신이 필요합니다."
    return source
