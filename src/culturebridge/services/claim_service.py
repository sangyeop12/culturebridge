"""Conservative comparison against curated facts; no live source retrieval."""

import re

from culturebridge.domain.models import (
    ClaimEvidence,
    ClaimResult,
    VerificationStatus,
)
from culturebridge.services.catalog_service import get_heritage, get_sources

ALIASES = {
    "seokguram": ("석굴암",),
    "horyuji": ("호류지 불교 건축물", "호류지"),
    "dayanta": ("대안탑",),
}
FIELDS = {"재료": "material", "시대": "period", "구조": "structure"}
SCOPE_NOTE = (
    "현재 등록된 공식 출처 기반 요약 데이터와 대조한 결과입니다. "
    "원문을 실시간 검색하거나 역사적 영향 관계를 검증한 결과는 아닙니다. "
    "확인됨은 표시된 한 가지 사실과 일치한다는 뜻입니다."
)


def verify_claim(left_id: str, right_id: str, claim: str) -> ClaimResult:
    items = [get_heritage(left_id), get_heritage(right_id)]
    claim = claim.strip()
    status = VerificationStatus.INSUFFICIENT_EVIDENCE
    explanation = (
        "이 문장 전체를 확인할 근거가 현재 데이터에 없습니다. "
        "예시처럼 문화유산 한 곳의 재료·시대·구조를 한 문장으로 입력해 주세요. "
        "영향 관계·인과관계·복합 주장은 추가 자료가 필요합니다."
    )
    evidence = []
    for item in items:
        aliases = "|".join(re.escape(name) for name in ALIASES[item.id])
        # Anchored templates intentionally reject extra clauses and negation.
        match = re.fullmatch(
            rf"(?:{aliases})(?:의|은|는)\s*(재료|시대|구조)(?:은|는|가)?\s*"
            r"(.+?)(?:이다|입니다)\s*[.!。]?",
            claim,
        )
        if not match:
            continue
        category, assertion = match.groups()
        fact = getattr(item, FIELDS[category])
        evidence.append(
            ClaimEvidence(
                heritage_id=item.id,
                category=category,
                fact=f"{item.name}의 {category}: {fact}",
                source_ids=item.source_ids,
            )
        )
        if assertion.strip() == fact:
            status = item.verification_status
            explanation = (
                "입력한 사실이 요약과 일치하지만 개별 원문 확인이 추가로 필요합니다."
                if status is VerificationStatus.NEEDS_REVIEW
                else "입력한 한 가지 사실이 등록된 요약 데이터와 정확히 일치합니다."
            )
        else:
            status = VerificationStatus.NEEDS_REVIEW
            explanation = (
                "입력한 표현이 등록된 사실과 일치하지 않습니다. "
                "아래 근거와 원문을 대조해 주세요. 표현 차이일 수도 있으므로 "
                "이 결과만으로 거짓이라고 단정하지 않습니다."
            )
        break
    source_ids = list(dict.fromkeys(sid for entry in evidence for sid in entry.source_ids))
    return ClaimResult(
        claim=claim,
        verification_status=status,
        explanation=explanation,
        evidence=evidence,
        sources=get_sources(source_ids),
        scope_note=SCOPE_NOTE,
    )
