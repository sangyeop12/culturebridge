"""Explicit comparison axes, not inferred influence or independent truth judgments."""

import re

from culturebridge.services.evidence_reading_service import reading_units, source_years


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
        materials = [reading_units(category, field.evidence_quote) for field in (left, right)]
        labels = [list(dict.fromkeys(label for _, label in units)) for units in materials]
        if any(len(row) > 1 for row in labels) and all(labels):
            shared = sorted(set(labels[0]) & set(labels[1]))
            return (
                f"왼쪽 원문에는 {'·'.join(labels[0])}, "
                f"오른쪽 원문에는 {'·'.join(labels[1])}가 나와요. "
                + (f"함께 언급된 재료는 {'·'.join(shared)}예요. " if shared else "")
                + "여러 재료의 쓰임과 사용한 부분을 대조하세요. "
                "언급되지 않은 재료가 없다는 뜻은 아니에요." + caution
            )
        values = [row[0] if row else None for row in labels]
        if all(values):
            if values[0] == values[1]:
                return (
                    f"양쪽 자료에서 {values[0]}를 찾아볼 수 있어요. "
                    "재료가 같아도 만드는 방식은 다를 수 있어요."
                )
            if any(v in {"돌", "석재"} for v in values) and any(
                v in {"화강암", "대리석", "사암", "석회암"} for v in values
            ):
                return (
                    "두 설명 모두 돌 재료와 관련돼요. "
                    "한쪽은 돌의 종류를 구체적으로 적고 다른 쪽은 석재라고만 적었어요. "
                    "이 표현 차이만으로 실제 재료가 다르다고 단정하지 않아요."
                )
            return (
                f"자료에 나온 재료는 {values[0]}와 {values[1]}로 달라요. "
                "재료에 따라 구조를 어떻게 만들었는지 살펴보세요." + caution
            )
    if category == "시대":
        if any(re.search(r"\b(?:BC|BCE)\b|기원전", f.evidence_quote, re.I) for f in (left, right)):
            return (
                "기원전과 기원후 표기를 먼저 구분하세요. 연대를 양수로 바꿔 단순히 빼지 않아요."
                + caution
            )
        if left.date_event != right.date_event:
            return "두 연대가 가리키는 사건이 달라요. 건립과 재건을 구분한 뒤 비교하세요." + caution
        years = [source_years(field.evidence_quote) for field in (left, right)]
        if all(len(value) == 1 for value in years) and left.date_event == "건립·창건":
            difference = abs(int(years[0][0]) - int(years[1][0]))
            uncertain = any(
                re.search(r"추측|추정|probably|estimated|believed", f.evidence_quote, re.I)
                for f in (left, right)
            )
            return (
                f"왼쪽 원문은 {years[0][0]}년, 오른쪽 원문은 {years[1][0]}년의 건립을 다뤄요. "
                + (
                    f"표기된 연도 사이에는 {difference}년 차이가 있어요."
                    if difference
                    else "표기된 건립 연도가 같아요."
                )
                + (" 추정·전승이 포함되므로 확정 연대의 차이는 아니에요." if uncertain else "")
                + caution
            )
        return (
            "같은 사건의 연대인지 먼저 확인하고, 어느 시기의 설명인지 순서대로 살펴보세요."
            + caution
        )
    if category in {"구조", "종교적 배경"}:
        units = [reading_units(category, field.evidence_quote) for field in (left, right)]
        common = [label for axis, label in units[0] if (axis, label) in units[1]]
        differences = []
        for axis in dict.fromkeys(axis for axis, _ in units[0]):
            a = [label for key, label in units[0] if key == axis]
            b = [label for key, label in units[1] if key == axis]
            if b and a != b:
                differences.append(
                    f"{axis} 설명은 왼쪽의 {'·'.join(a)}와 오른쪽의 {'·'.join(b)}로 달라요."
                )
        if common or differences:
            return (
                (
                    "양쪽 원문에서 함께 확인되는 특징은 " + "·".join(common) + "입니다. "
                    if common
                    else ""
                )
                + " ".join(differences)
                + " 한쪽에만 나온 특징은 다른 쪽에 없다고 단정하지 않아요."
                + caution
            )
        if all(units):
            return (
                "왼쪽 원문은 "
                + "·".join(label for _, label in units[0])
                + ", 오른쪽 원문은 "
                + "·".join(label for _, label in units[1])
                + "을 설명해요. 설명한 기준이 달라 같은 기준의 차이는 아직 판단하지 않아요."
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
