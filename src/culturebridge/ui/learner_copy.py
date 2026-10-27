"""Learning-facing presentation; internal records and official quotations stay intact."""

from culturebridge.services.date_reading_service import uncertain_date
from culturebridge.services.display_service import display_name, short_display_name
from culturebridge.services.evidence_comparison_service import supported_fields
from culturebridge.services.evidence_reading_service import reading_units, source_years


def error_notice(error):
    # Never expose raw service/provider exceptions, identifiers or diagnostic codes.
    return "지금은 요청을 처리하지 못했어요. 입력 내용을 확인하거나 잠시 후 다시 시도해 주세요."


def source_scope(source):
    return {
        "individual_text": "이 유산을 소개하는 공식 자료예요.",
        "group_text": "여러 유산을 함께 소개하는 자료예요. 선택한 유산의 설명을 살펴봐요.",
        "listed_text": "등재된 유산을 소개하는 공식 자료예요.",
        "metadata": "유산 목록의 기본 정보예요. 자세한 내용은 공식 원문에서 읽어보세요.",
    }[source.content_kind]


def _join(words):
    words = list(dict.fromkeys(words))
    if len(words) < 2:
        return words[0] if words else ""
    return _particle(words[0], "과", "와") + " " + words[1]


def _particle(text, closed, opened):
    last = text[-1]
    return text + (closed if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 else opened)


def _focus(quote):
    units = reading_units("구조", quote)
    parts = {"건물을 받치는 아랫부분": "기단", "가장자리의 난간": "난간"}
    named = [parts.get(label, label) for axis, label in units if axis == "부분"]
    if named:
        return _join(named) + "의 모양"
    if any(axis == "층수" for axis, _ in units):
        return "높이와 층수" if any(label == "높이" for _, label in units) else "층수"
    if any(axis in {"공간", "배치"} for axis, _ in units):
        return "공간과 건물 배치"
    return "건물의 모양"


def comparison_note(comparison, point):
    """Re-render old saved diagnostics from validated evidence, never from raw notes."""
    if not comparison.collected_sources:
        return ""
    fields = {(f.heritage_id, f.category): f for f in supported_fields(comparison)}
    left = fields.get((comparison.left.id, point.category))
    right = fields.get((comparison.right.id, point.category))
    if not left or not right:
        return "이 항목은 자료가 더 필요해요. 확인된 내용부터 살펴보세요."
    names = [
        short_display_name(display_name(h.id, h.name)) for h in (comparison.left, comparison.right)
    ]
    quotes = [left.evidence_quote, right.evidence_quote]
    if point.category == "구조":
        focuses = [_focus(q) for q in quotes]
        if focuses[0] != focuses[1]:
            return (
                f"{names[0]} 자료에서는 {_particle(focuses[0], '을', '를')}, "
                f"{names[1]} 자료에서는 {_particle(focuses[1], '을', '를')} 소개해요. "
                "그림이나 사진도 함께 보며 각 부분을 찾아보세요."
            )
        return "두 유산이 소개하는 부분을 함께 살펴보고, 각 유산의 모양과 쓰임을 찾아보세요."
    if point.category == "재료":
        values = [_join(label for _, label in reading_units("재료", q)) for q in quotes]
        if all(values):
            return (
                f"{names[0]} 자료에는 {_particle(values[0], '이', '가')}, "
                f"{names[1]} 자료에는 {_particle(values[1], '이', '가')} 재료로 나와요. "
                "어느 부분에 쓰였는지도 함께 살펴보세요."
            )
    if point.category == "시대":
        if any(uncertain_date(q) for q in quotes):
            return (
                "추정해서 소개한 시기가 있어요. "
                "정확한 연도 차이보다는 각 유산이 만들어진 시기를 살펴봐요."
            )
        if left.date_event != right.date_event or not left.date_event:
            return (
                "처음 세운 때와 다시 지은 때가 다를 수 있어요. "
                "각 시기에 어떤 일이 있었는지 살펴봐요."
            )
        years = [source_years(q) for q in quotes]
        if all(len(y) == 1 for y in years):
            return (
                f"{names[0]} 자료에는 {years[0][0]}년, "
                f"{names[1]} 자료에는 {years[1][0]}년이 나와요."
            )
    return "두 유산의 공식 설명을 함께 읽고, 배운 내용과 연결해 보세요."


def common_points(comparison):
    if not comparison.collected_sources:
        return comparison.common_points
    points = []
    valid = {field.model_dump_json() for field in supported_fields(comparison)}
    for item in comparison.common_evidence:
        if any(
            field.model_dump_json() not in valid
            for field in (item.left_evidence, item.right_evidence)
        ):
            continue
        left = set(reading_units(item.category, item.left_evidence.evidence_quote))
        right = set(reading_units(item.category, item.right_evidence.evidence_quote))
        labels = [label for axis, label in sorted(left & right) if axis != "건물 종류"]
        if labels:
            points.append("두 유산의 자료에서 ‘" + _join(labels) + "’를 함께 찾아볼 수 있어요.")
    return list(dict.fromkeys(points))


def comparable_points(comparison):
    """Hide incomplete categories without changing saved evidence or learning records."""
    if comparison.collected_sources or comparison.extracted_fields:
        fields = {(f.heritage_id, f.category) for f in supported_fields(comparison)}
        return [
            p
            for p in comparison.differences
            if all((h.id, p.category) in fields for h in (comparison.left, comparison.right))
        ]
    return [
        p
        for p in comparison.differences
        if all(
            text and text.strip() not in {"근거 부족", "정보 없음", "미확인"}
            for text in (p.left, p.right)
        )
    ]


def recommendation_note(criteria):
    """Use only reviewed learning categories; never print free-form planner reasons."""
    text = " ".join(criteria)
    categories = [c for c in ("시대", "구조", "재료", "종교적 배경") if c in text]
    if categories:
        return _join(categories) + " 중심으로 두 유산을 함께 살펴보세요."
    return "공식 설명을 읽고 두 유산의 유사점과 차이점을 알아보세요."
