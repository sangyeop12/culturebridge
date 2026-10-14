"""Explicit comparison axes, not inferred influence or independent truth judgments."""

import re


def comparison_explanation(category, left, right, level="beginner"):
    if not left or not right:
        return "양쪽 근거를 모두 찾지 못해 이 항목의 비교는 보류해요."
    caution = " 이 차이만으로 교류나 영향 관계를 단정하지 않아요."
    if category == "재료":
        if any(
            re.search(r"\bnot\b|without|아니|않|없|모방|imitat", field.evidence_quote, re.I)
            for field in (left, right)
        ):
            return (
                "부정·모방 표현이 있어 재료를 단정하지 않아요. "
                "실제 재료와 표현한 양식을 구분하세요."
            )
        materials = [
            (r"화강암|granite", "화강암"),
            (r"목재|wood", "목재"),
            (r"벽돌|brick", "벽돌"),
            (r"대리석|marble", "대리석"),
            (r"석재|석탑|\bstone\b", "석재"),
        ]
        values = [
            next((label for pattern, label in materials if re.search(pattern, f.value, re.I)), None)
            for f in (left, right)
        ]
        if all(values):
            if values[0] == values[1]:
                return (
                    f"양쪽 자료에서 {values[0]}를 찾아볼 수 있어요. "
                    "재료가 같아도 만드는 방식은 다를 수 있어요."
                )
            return (
                f"자료에 나온 재료는 {values[0]}와 {values[1]}로 달라요. "
                "재료에 따라 구조를 어떻게 만들었는지 살펴보세요." + caution
            )
    if category == "시대":
        if left.date_event != right.date_event:
            return "두 연대가 가리키는 사건이 달라요. 건립과 재건을 구분한 뒤 비교하세요." + caution
        return (
            "같은 사건의 연대인지 먼저 확인하고, 어느 시기의 설명인지 순서대로 살펴보세요."
            + caution
        )
    if category == "종교적 배경":
        return (
            "종교 이름뿐 아니라 유산의 쓰임·예배 대상·경전과의 관계를 함께 비교하세요. "
            "같은 종교라도 역할은 다를 수 있어요." + caution
        )
    return (
        "두 자료에서 모양·공간 배치·층수 중 실제로 설명된 기준을 골라 비교하세요. "
        "겉모양의 유사성이 같은 건축법을 뜻하지는 않아요." + caution
    )
