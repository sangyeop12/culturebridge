import re

from pydantic import ValidationError

from culturebridge.domain.models import (
    CommonEvidence,
    ComparisonPoint,
    ComparisonResult,
    VerificationStatus,
)
from culturebridge.services.curriculum_service import plan_learning
from culturebridge.services.extraction_service import DraftField, validate_extraction


def supported_fields(comparison: ComparisonResult):
    sources = {(s.heritage_id, s.id): s for s in comparison.collected_sources}
    fields = []
    seen = set()
    for field in comparison.extracted_fields:
        try:
            candidate = DraftField(
                heritage_id=field.heritage_id,
                category=field.category,
                value=field.value,
                source_id=field.source_id,
                evidence_quote=field.evidence_quote,
            )
        except ValidationError:
            continue
        if validate_extraction(candidate, comparison.collected_sources) is None:
            continue
        source = sources.get((field.heritage_id, field.source_id))
        key = (field.heritage_id, field.category)
        if (
            source
            and source.status in {"fresh", "cached"}
            and source.content_kind == "individual_text"
            and field.value
            and field.evidence_quote
            and field.evidence_quote in source.content
            and field.source_url == source.source_url
            and field.verification_status is not VerificationStatus.INSUFFICIENT_EVIDENCE
            and field.heritage_id in {comparison.left.id, comparison.right.id}
            and key not in seen
        ):
            fields.append(field)
            seen.add(key)
    return fields


def apply_extracted_comparison(comparison: ComparisonResult) -> ComparisonResult:
    fields = supported_fields(comparison)
    lookup = {(f.heritage_id, f.category): f for f in fields}
    points = []
    _, focus = plan_learning(
        comparison.level, comparison.goal, comparison.goal_text, comparison.amount
    )
    categories = focus + [c for c in ("시대", "구조", "재료", "종교적 배경") if c not in focus]
    comparison.learning_notices = []
    for category in categories:
        left = lookup.get((comparison.left.id, category))
        right = lookup.get((comparison.right.id, category))
        if category in focus and (not left or not right):
            comparison.learning_notices.append(
                f"목표 항목 '{category}'의 양쪽 근거가 부족합니다. "
                "비교 판단은 보류하고 확보된 출처·자료 범위를 확인하세요."
            )
        points.append(
            ComparisonPoint(
                category=category,
                left=left.value if left else "근거 부족",
                right=right.value if right else "근거 부족",
                explanation=(
                    "두 유산의 원문을 함께 읽어 봐요. 없는 내용은 추측하지 않아요."
                    if comparison.level.value == "beginner"
                    else "같은 항목의 원문 범위와 의미를 대조합니다. 추출 후보는 검토가 필요합니다."
                ),
                source_ids=list(dict.fromkeys(f.source_id for f in (left, right) if f)),
            )
        )
    comparison.basis = "extracted"
    for point in points:
        if point.category not in focus:
            point.explanation = "보조 항목입니다. 이번 학습은 선택 목표 항목을 우선합니다."
        elif comparison.amount.value == "deep":
            point.explanation += " 각 원문이 개별 유산·건립·재건 중 무엇을 가리키는지 대조하세요."
    comparison.differences = points
    comparison.common_evidence = []
    shared_terms = {
        "종교적 배경": [(r"불교|Buddhis", "불교와 관련된 종교 맥락")],
        "재료": [
            (r"화강암|granite", "화강암 재료"),
            (r"목재|wood", "목재 재료"),
            (r"벽돌|brick", "벽돌 재료"),
        ],
        "구조": [(r"사찰|temple", "사찰 공간"), (r"탑|pagoda", "탑 형태")],
    }
    for category, terms in shared_terms.items():
        left, right = (
            lookup.get((comparison.left.id, category)),
            lookup.get((comparison.right.id, category)),
        )
        if not left or not right:
            continue
        for pattern, label in terms:
            if all(re.search(pattern, f.evidence_quote, re.IGNORECASE) for f in (left, right)):
                comparison.common_evidence.append(
                    CommonEvidence(
                        statement=f"양쪽 원문의 공통 후보: {label}. 범위 검토가 필요합니다.",
                        category=category,
                        left_evidence=left,
                        right_evidence=right,
                    )
                )
    comparison.common_points = [item.statement for item in comparison.common_evidence] or [
        "양쪽 원문에서 같은 특징의 근거를 확보하지 못했습니다. 공통점을 추측하지 않습니다."
    ]
    comparison.source_ids = list(dict.fromkeys(f.source_id for f in fields))
    comparison.verification_status = (
        VerificationStatus.NEEDS_REVIEW if fields else VerificationStatus.INSUFFICIENT_EVIDENCE
    )
    comparison.verification_note = (
        "저장된 공식 원문의 추출 후보로 구성한 비교입니다. 인용 일치는 의미 검증 완료가 아닙니다. "
        "근거 없는 항목은 기존 요약으로 채우지 않았습니다."
    )
    return comparison
