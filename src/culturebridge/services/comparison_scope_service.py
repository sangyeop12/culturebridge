"""Domestic means Korea, not merely the same country as the selected heritage."""

import re

from culturebridge.domain.models import ComparisonScope

SCOPE_LABELS = {
    "overseas": "해외 문화유산과 비교",
    "domestic": "국내 문화유산과 비교",
}


def candidate_in_scope(country, scope=ComparisonScope.OVERSEAS):
    countries = {p.strip().casefold() for p in re.split(r"[;|]", country or "") if p.strip()}
    if not countries:
        return False
    if countries & {"unknown", "unspecified", "미상", "알 수 없음", "근거 부족"}:
        return False
    korea = {"대한민국", "한국", "republic of korea", "south korea", "korea, republic of"}
    if scope == ComparisonScope.DOMESTIC:
        return countries <= korea
    return countries.isdisjoint(korea)


def validate_pair_scope(right_country, scope):
    if not candidate_in_scope(right_country, scope):
        raise ValueError("선택한 비교 대상이 '" + SCOPE_LABELS[scope.value] + "' 범위와 다릅니다.")
