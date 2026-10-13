from culturebridge.domain.models import ComparisonPoint, ComparisonResult, VerificationStatus


def supported_fields(comparison: ComparisonResult):
    sources = {(s.heritage_id, s.id): s for s in comparison.collected_sources}
    fields = []
    seen = set()
    for field in comparison.extracted_fields:
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
    for category in ("시대", "구조", "재료"):
        left = lookup.get((comparison.left.id, category))
        right = lookup.get((comparison.right.id, category))
        points.append(
            ComparisonPoint(
                category=category,
                left=left.value if left else "근거 부족",
                right=right.value if right else "근거 부족",
                explanation="원문 추출 후보를 나란히 표시합니다. 의미·범위 검토가 필요합니다.",
                source_ids=list(dict.fromkeys(f.source_id for f in (left, right) if f)),
            )
        )
    comparison.basis = "extracted"
    comparison.differences = points
    comparison.common_points = [
        "공통점은 양쪽 원문의 근거를 대조한 뒤 판단해야 합니다.",
        "자료의 유사성만으로 직접 영향이나 인과 관계를 확정하지 않습니다.",
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
