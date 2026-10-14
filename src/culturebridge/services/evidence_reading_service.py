"""Small, quote-grounded reading units. Absence of a feature is not a difference."""

import re

FEATURES = {
    "재료": [
        (r"화강암|granite", "화강암", "재료"),
        (r"대리석|marble", "대리석", "재료"),
        (r"목재|목탑|wood(?:en)?", "나무", "재료"),
        (r"벽돌|brick", "벽돌", "재료"),
        (r"석재|석탑|\bstone\b", "돌", "재료"),
    ],
    "구조": [
        (r"팔각|octagonal", "여덟 모서리가 있는 모양", "모양"),
        (r"원형|circular", "둥근 모양", "모양"),
        (r"rectangular|직사각", "직사각형", "모양"),
        (r"symmetr|대칭", "대칭 배치", "배치"),
        (r"전실|antechamber", "앞쪽 방", "공간"),
        (r"주실|central (?:tomb )?chamber", "중심 방", "공간"),
        (r"기단", "건물을 받치는 아랫부분", "부분"),
        (r"난간|balustrade", "가장자리의 난간", "부분"),
        (r"높이|\bheight\b", "높이", "측정 기준"),
        (
            r"inside (?:the |a )?(?:Buddhist )?temple|사찰 안|사찰 내부",
            "사찰 안에 있는 위치",
            "위치",
        ),
        (
            r"\binside\s+(?:the\s+)?(?:[A-Z][A-Za-z’'-]*\s+){1,3}[Tt]emple\b",
            "사찰 안에 있는 위치",
            "위치",
        ),
        (r"single storey|single-storey|단층", "한 층으로 된 구조", "층수"),
        (r"five[- ]stor(?:i|e)ed|오층|5층", "다섯 층으로 된 구조", "층수"),
    ],
    "종교적 배경": [
        (r"불교|불상|부처|Buddhis|Buddha", "불교", "종교"),
        (r"이슬람|Islam|Muslim", "이슬람", "종교"),
        (r"힌두|Hindu", "힌두교", "종교"),
        (r"기독교|Christian", "기독교", "종교"),
        (r"법화경|Lotus Sutra", "법화경", "경전"),
        (r"Quran|Koran|코란", "코란", "경전"),
    ],
}


def reading_units(category, quote):
    # A bounded rule cannot resolve the scope of a negation or an imitated feature.
    if re.search(r"\bnot\b|without|아니|않|없|모방|imitat|본떠", quote, re.I):
        return []
    units = [
        (axis, label)
        for pattern, label, axis in FEATURES.get(category, [])
        if re.search(pattern, quote, re.I)
    ]
    if category == "재료" and any(label in {"화강암", "대리석"} for _, label in units):
        units = [unit for unit in units if unit[1] != "돌"]
    return list(dict.fromkeys(units))


def source_years(quote):
    return list(dict.fromkeys(re.findall(r"\b\d{3,4}(?=년|\))|(?<=in )\d{3,4}\b", quote, re.I)))
