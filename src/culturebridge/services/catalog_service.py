import sqlite3
from collections.abc import Iterable

from culturebridge.data.catalog import HERITAGES, SOURCES
from culturebridge.database import transaction
from culturebridge.domain.models import (
    ComparisonPoint,
    ComparisonResult,
    HeritageDetail,
    HeritageSummary,
    LearningGoal,
    LearningLevel,
    RelatedHeritage,
    SourceRecord,
    VerificationStatus,
)


class HeritageNotFoundError(KeyError):
    pass


LEARNING_GOALS = {
    LearningLevel.BEGINNER: "문화유산의 위치·형태·재료를 관찰하고 구분하기",
    LearningLevel.INTERMEDIATE: "시대·구조·재료를 연결하여 두 문화유산 비교하기",
    LearningLevel.ADVANCED: "확인된 사실과 해석을 구분하고 출처의 범위와 한계 판단하기",
}


def _summary(item: HeritageDetail) -> HeritageSummary:
    return HeritageSummary(**item.model_dump(include=set(HeritageSummary.model_fields)))


def list_heritages(query: str | None = None) -> list[HeritageSummary]:
    items: Iterable[HeritageDetail] = HERITAGES.values()
    if query and query.strip():
        normalized = query.strip().casefold()
        items = (
            item
            for item in items
            if normalized
            in " ".join(
                [item.name, item.country, item.period, item.location, item.summary]
            ).casefold()
        )
    return [_summary(item) for item in items]


def get_heritage(heritage_id: str) -> HeritageDetail:
    try:
        return HERITAGES[heritage_id]
    except KeyError:
        try:
            with transaction() as connection:
                row = connection.execute(
                    "SELECT detail_json FROM dynamic_heritages WHERE id=?", (heritage_id,)
                ).fetchone()
            if row:
                return HeritageDetail.model_validate_json(row["detail_json"])
        except sqlite3.Error:
            pass
        raise HeritageNotFoundError(heritage_id) from None


def get_sources(source_ids: list[str]) -> list[SourceRecord]:
    records = [SOURCES[source_id] for source_id in source_ids if source_id in SOURCES]
    from culturebridge.services.dynamic_heritage_service import dynamic_source

    for source_id in source_ids:
        if source_id in SOURCES:
            continue
        source = dynamic_source(source_id)
        if source and source.retrieved_at:
            records.append(
                SourceRecord(
                    id=source.id,
                    title=source.title,
                    organization=source.organization,
                    url=source.source_url,
                    retrieved_at=source.retrieved_at.date(),
                    summary=source.content,
                    scope_note=source.scope_note,
                )
            )
    return records


def recommend_related(
    heritage_id: str, goal: LearningGoal = LearningGoal.COMPARE
) -> list[RelatedHeritage]:
    selected = get_heritage(heritage_id)
    candidates = []
    for item in HERITAGES.values():
        if item.id == selected.id:
            continue
        shared_religion = "불교" in selected.religious_context and "불교" in item.religious_context
        criteria = []
        score = 0.0
        if shared_religion:
            criteria.append("불교라는 공통 종교 맥락")
            score += 0.35 if goal is LearningGoal.RELIGION else 0.25
        if item.country != selected.country:
            criteria.append("다른 국가의 문화유산")
            score += 0.15
        if item.material != selected.material:
            criteria.append("재료 차이를 관찰할 수 있음")
            score += 0.25 if goal is LearningGoal.OBSERVE else 0.15
        if item.structure != selected.structure:
            criteria.append("구조 유형을 비교할 수 있음")
            score += 0.15
        if item.verification_status is VerificationStatus.VERIFIED:
            criteria.append("등록된 개별 자료의 확인 범위가 비교적 충분함")
            score += 0.25 if goal is LearningGoal.VERIFY else 0.15
        else:
            criteria.append("개별 원문이 부족해 추가 자료 확인 필요")
        reason = (
            " · ".join(criteria)
            + ". 자료 적합성에 따른 추천이며 역사적 영향 관계를 뜻하지 않습니다."
        )
        candidates.append(
            RelatedHeritage(
                heritage=_summary(item),
                reason=reason,
                score=min(score, 1),
                criteria=criteria,
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def compare_heritages(
    left_id: str,
    right_id: str,
    level: LearningLevel,
) -> ComparisonResult:
    left = get_heritage(left_id)
    right = get_heritage(right_id)
    if left_id not in HERITAGES or right_id not in HERITAGES:
        return ComparisonResult(
            left=_summary(left),
            right=_summary(right),
            level=level,
            common_points=["원문 분석 전입니다. 공통점을 추정하지 않습니다."],
            differences=[],
            source_ids=list(dict.fromkeys(left.source_ids + right.source_ids)),
            verification_status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            verification_note="동적 대상은 공식 Agent 탐구의 추출 근거로만 비교합니다.",
        )
    source_ids = list(dict.fromkeys([*left.source_ids, *right.source_ids]))
    explanations = {
        LearningLevel.BEGINNER: [
            "시대는 언제 만들어졌는지를 나타냅니다. 두 유산의 세기 표시를 찾아보세요.",
            "구조는 공간을 만드는 모양과 방식입니다. 두 유산의 구조 설명에서 다른 말을 찾아보세요.",
            f"{left.name}의 {left.material}와 {right.name}의 {right.material}를 구분해 보세요.",
            "두 유산 모두 불교와 관련됩니다. 불교는 공통점이고 지역은 차이점입니다.",
        ],
        LearningLevel.INTERMEDIATE: [
            f"{left.period}와 {right.period}를 나란히 놓고 시기가 겹치는지 살펴보세요. "
            "같은 세기라는 사실만으로 교류를 입증할 수는 없습니다.",
            "재료와 공간 구성을 함께 비교하세요. 구조 설명에서 공간의 연결 방식 또는 "
            "건축 부재를 찾아 공통점과 차이점을 정리할 수 있습니다.",
            f"{left.material}와 {right.material}라는 재료 정보는 구조 비교의 단서입니다. "
            "재료가 선택된 이유를 설명하려면 환경·시공에 관한 추가 자료가 필요합니다.",
            "불교라는 공통 맥락 안에서 예배 공간·사찰 배치·경전 전래 등 각 설명의 "
            "초점이 어떻게 다른지 비교하세요.",
        ],
        LearningLevel.ADVANCED: [
            "등록된 시대 정보는 사실 대조의 출발점입니다. 창건과 재건을 구분하는 "
            "세부 연대는 별도 자료가 필요하며, 시간적 근접성은 직접 영향의 증거가 아닙니다.",
            "구조의 유사성은 관찰 결과이고 기술 전파는 역사적 주장입니다. 전파를 "
            "입증하려면 문헌·고고학 자료 등 독립된 근거를 추가로 대조해야 합니다.",
            "재료 정보와 재료 선택의 원인을 분리하세요. 구조화된 재료 항목만으로 "
            "시공법·보존 상태·환경적 원인을 확정할 수 없습니다.",
            "지역별 불교 수용이라는 비교 관점과 개별 유산의 사실을 구분하세요. "
            "공식 소개 자료가 다루지 않는 영향 관계는 근거 부족으로 남겨야 합니다.",
        ],
    }[level]
    return ComparisonResult(
        learning_goal=LEARNING_GOALS[level],
        left=_summary(left),
        right=_summary(right),
        level=level,
        common_points=[
            "두 유산 모두 동아시아 불교문화의 전개를 보여 줍니다.",
            "건축과 종교적 기능을 함께 살펴봐야 의미를 이해할 수 있습니다.",
        ],
        differences=[
            ComparisonPoint(
                category="시대",
                left=left.period,
                right=right.period,
                explanation=explanations[0],
            ),
            ComparisonPoint(
                category="구조",
                left=left.structure,
                right=right.structure,
                explanation=explanations[1],
            ),
            ComparisonPoint(
                category="재료",
                left=left.material,
                right=right.material,
                explanation=explanations[2],
            ),
            ComparisonPoint(
                category="종교적 배경",
                left=left.religious_context,
                right=right.religious_context,
                explanation=explanations[3],
            ),
        ],
        source_ids=source_ids,
        verification_status=(
            VerificationStatus.NEEDS_REVIEW
            if VerificationStatus.NEEDS_REVIEW
            in (left.verification_status, right.verification_status)
            else VerificationStatus.VERIFIED
        ),
        verification_note=(
            "기본 사실은 등록된 공식 출처 기반 요약 데이터에 근거합니다. "
            "학습 안내는 비교 방법을 설명하며, 역사적 영향이나 인과 관계를 입증하지 않습니다."
            + (
                " 대안탑의 개별 사실은 추가 자료 확인이 필요합니다."
                if "dayanta" in (left_id, right_id)
                else ""
            )
        ),
    )
