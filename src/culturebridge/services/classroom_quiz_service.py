"""Short, quote-grounded content questions. No inference from absent features."""

from itertools import zip_longest

from culturebridge.services.date_reading_service import read_period
from culturebridge.services.display_service import short_display_name
from culturebridge.services.evidence_reading_service import (
    material_scope,
    observation_scope,
    reading_units,
)
from culturebridge.services.subject_service import sentences

ALTERNATIVES = {
    "모양": ["둥근 모양", "직사각형", "여덟 모서리가 있는 모양", "삼각형", "반원형"],
    "배치": ["대칭 배치", "나선형 배치", "일렬 배치", "방사형 배치"],
    "공간": ["앞쪽 방", "중심 방", "안뜰", "기둥이 늘어선 통로", "지하 저장실"],
    "부분": ["지붕", "천장", "기둥", "드나드는 문", "가장자리의 난간"],
    "측정 기준": ["높이", "부지 넓이", "벽의 두께", "출입문의 너비"],
    "위치": [
        "사찰 안에 있는 위치",
        "궁궐 안에 있는 위치",
        "성벽 위에 있는 위치",
        "무덤 아래의 위치",
    ],
    "층수": ["한 층으로 된 구조", "두 층으로 된 구조", "세 층으로 된 구조", "다섯 층으로 된 구조"],
    "종교": ["불교", "힌두교", "이슬람", "기독교"],
    "경전": ["법화경", "코란", "성경", "베다"],
    "재료": ["돌", "나무", "벽돌", "금속", "대리석", "사암", "석회암"],
    "천장 구조": ["아치가 이어진 천장", "평평한 판형 천장", "격자형 천장", "천장이 없는 구조"],
    "창": ["색유리 창", "격자창", "종이를 바른 창", "창이 없는 벽"],
    "건축 방식": ["나무로 지은 건물", "벽돌로 지은 건물", "철골 건물", "흙을 다진 건물"],
    "무덤 형태": ["흙을 쌓은 봉분", "바위를 깎은 방", "지하 벽돌방", "나무로 짠 방"],
}


def _period(quote):
    period = read_period(quote)
    return list(period.choices) if period else None


def classroom_rows(fields, focus, names, left_id, right_id, level="beginner", sources=()):
    """Return up to four content items plus one paired reading task; correct choice is first."""
    left = [f for f in fields if f.heritage_id == left_id and f.category in focus]
    right = [f for f in fields if f.heritage_id == right_id and f.category in focus]
    balanced = [f for pair in zip_longest(left, right) for f in pair if f]
    candidates = []
    for field in balanced:
        units = reading_units(field.category, field.evidence_quote)
        # Prefer concrete shape/parts before merely sharing the word "height".
        units.sort(key=lambda item: item[0] == "측정 기준")
        if field.category == "시대":
            choices = _period(field.evidence_quote)
            if choices:
                candidates.append((field, "시기", choices[0], choices))
        for axis, answer in units:
            labels = {label for _, label in units}
            # Do not turn a true feature elsewhere in the source into a false choice.
            labels |= {
                label
                for source in sources
                if source.heritage_id == field.heritage_id
                for sentence in sentences(source.content)
                for context_axis, label in reading_units(field.category, sentence)
                if context_axis == axis
            }
            if axis == "재료" and answer in {"화강암", "대리석", "사암", "석회암"}:
                labels.add("돌")  # A broader true category must not become a distractor.
            if axis == "모양" and answer in {"둥근 봉분", "공을 반으로 자른 모양"}:
                labels.add("둥근 모양")
            if axis == "모양" and any(
                v in field.evidence_quote.lower() for v in ("arch", "dome", "아치", "돔")
            ):
                labels.add("둥근 모양")
            choices = [answer] + [v for v in ALTERNATIVES.get(axis, []) if v not in labels][:3]
            if len(choices) == 4:
                candidates.append((field, axis, answer, choices))
    chosen = []
    seen = set()
    seen_facts = set()
    covered = set()
    # Cover both sides and the selected categories before adding a second detail.
    for unique_fields in (True, False):
        for field, axis, answer, choices in candidates:
            key = (field.heritage_id, field.category, axis)
            field_key = (field.heritage_id, field.category)
            fact = (field.heritage_id, answer, field.evidence_quote)
            if key in seen or fact in seen_facts or (unique_fields and field_key in covered):
                continue
            seen.add(key)
            seen_facts.add(fact)
            covered.add(field_key)
            scope = (
                material_scope(field.evidence_quote)
                if field.category == "재료"
                else "설명 부분 미확인"
            )
            name = short_display_name(names[field.heritage_id])
            observed = observation_scope(answer, field.evidence_quote) if axis == "모양" else scope
            part = (
                f" · {observed}"
                if observed not in {"사용 부분 확인 필요", "설명 부분 미확인"}
                else ""
            )
            question = f"{name}{part}: 설명에서 확인할 수 있는 {axis} 표현은?"
            if level == "intermediate":
                question = f"{name}{part}: {axis}에 관한 설명으로 알맞은 것은?"
            elif level == "advanced":
                question = (
                    f"{name}{part}: 다른 부분으로 일반화하지 않고 "
                    f"원문으로 확인할 수 있는 {axis} 설명은?"
                )
                if len(chosen) == 3:
                    question = f"{name}{part}의 {axis}: 이 설명을 해석한 내용으로 적절한 것은?"
                    choices = [
                        f"'{answer}'은 이 문장이 설명한 부분의 특징으로 읽는다",
                        f"'{answer}'이므로 유산 전체의 모든 부분이 같은 특징이다",
                        f"'{answer}'이므로 다른 유산과 만드는 방법도 반드시 같다",
                        f"'{answer}'만 적혀 있으므로 나머지 특징은 실제로 없다",
                    ]
            explanation = (
                f"복습 항목: {field.category} · {axis}: {answer} · 원문: {field.evidence_quote} · "
                "표현이 가리키는 부분을 확인하세요. 다른 특징이 없다는 뜻은 아닙니다."
            )
            chosen.append((field, axis, answer, (question, choices, explanation)))
            if len(chosen) == 4:
                break
        if len(chosen) == 4:
            break
    rows = [row for _, _, _, row in chosen]
    # A paired question compares the same axis, not one object's date with another's material.
    pair = next(
        (
            ((left_field, left_answer), (right_field, right_answer))
            for left_field, left_axis, left_answer, _ in chosen
            for right_field, right_axis, right_answer, _ in chosen
            if left_field.heritage_id == left_id
            and right_field.heritage_id == right_id
            and left_axis == right_axis
            and left_field.category == right_field.category
        ),
        None,
    )
    if len(rows) == 4 and pair:
        a, b = pair
        name_a = short_display_name(names[left_id])
        name_b = short_display_name(names[right_id])
        correct = f"{name_a}: {a[1]} / {name_b}: {b[1]}"
        choices = [
            correct,
            f"{name_a}: {b[1]} / {name_b}: {a[1]}",
            f"양쪽 모두: {a[1]}",
            f"양쪽 모두: {b[1]}",
        ]
        if len(set(choices)) < 4:
            choices = [
                correct,
                "연결된 두 표현만으로 같은 건축법임을 확정한다",
                "한쪽에 없는 표현은 실제 특징도 없다는 뜻이다",
                "두 유산의 설명 범위를 구분할 필요가 없다",
            ]
        question = "두 문화유산과 설명을 올바르게 연결한 것은?"
        if level == "advanced":
            question = f"'{correct}'라는 관찰만으로 확정할 수 없는 주장은?"
            choices = [
                "두 유산 사이에 직접적인 기술 전파가 있었다",
                f"왼쪽 원문에서 '{a[1]}' 표현을 찾았다",
                f"오른쪽 원문에서 '{b[1]}' 표현을 찾았다",
                "두 자료가 설명한 대상과 부분의 범위를 함께 확인한다",
            ]
        elif level == "intermediate":
            question = f"'{correct}'를 비교할 때 먼저 확인할 기준은?"
            choices = [
                "같은 부분·사건을 설명하는지 원문 범위를 대조한다",
                "같은 단어가 있으면 같은 건축 방식으로 분류한다",
                "국가가 다르면 다른 재료라고 분류한다",
                "한쪽에 빠진 설명은 그 유산에 없는 특징으로 분류한다",
            ]
        rows.append(
            (
                question,
                choices,
                f"복습 항목: 비교 · 원문: {a[0].evidence_quote} · 원문: {b[0].evidence_quote} · "
                "같은 표현이어도 대상과 부분의 범위를 확인하세요.",
            )
        )
    return rows
