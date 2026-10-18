"""Small, quote-grounded reading units. Absence of a feature is not a difference."""

import re

FEATURES = {
    "재료": [
        (r"화강암|granite", "화강암", "재료"),
        (r"대리석|marble", "대리석", "재료"),
        (r"사암|sandstone", "사암", "재료"),
        (r"석회암|limestone", "석회암", "재료"),
        (r"금박|gold leaf", "얇게 편 금", "재료"),
        (r"stained glass|스테인드글라스", "색유리", "재료"),
        (r"목재|목탑|목조|\b나무\b|wood(?:en)?", "나무", "재료"),
        (r"벽돌|brick", "벽돌", "재료"),
        (r"석재|석탑|석조|깬돌|\b돌\b|\bstone\b", "돌", "재료"),
    ],
    "구조": [
        (r"\bpagoda\b|석탑|목탑", "탑", "건물 종류"),
        (r"\btemple\b|사찰|사원", "사찰", "건물 종류"),
        (r"\bhall\b|전각|대불전", "큰 전각", "건물 종류"),
        (r"\bpalace\b|궁전|궁궐", "궁전", "건물 종류"),
        (r"삼층|3층|three[- ]stor(?:i|e)ed", "세 층으로 된 구조", "층수"),
        (r"팔각|8각|octagonal", "여덟 모서리가 있는 모양", "모양"),
        (r"십(?:\(十\))?자|cruciform|cross-shaped", "십자 모양", "모양"),
        (r"네모난|square", "네모 모양", "모양"),
        (r"원형|circular", "둥근 모양", "모양"),
        (r"hemispher|반구형", "공을 반으로 자른 모양", "모양"),
        (r"\bdome\b|돔", "둥글게 덮은 지붕", "부분"),
        (r"\barches\b|\barch\b|아치", "위쪽이 둥근 아치", "부분"),
        (r"\broof\b|지붕", "지붕", "부분"),
        (r"\bceiling\b|천장", "천장", "부분"),
        (r"ribbed vault|\bvaults?\b|볼트", "아치가 이어진 천장", "천장 구조"),
        (r"stained glass|스테인드글라스", "색유리 창", "창"),
        (r"목조\s*건물|wooden building", "나무로 지은 건물", "건축 방식"),
        (r"six connected buildings", "여섯 동의 건물이 이어진 배치", "배치"),
        (r"courtyard|안뜰", "안뜰", "공간"),
        (r"peristyle|열주랑", "기둥이 늘어선 통로", "공간"),
        (r"원분", "둥근 봉분", "모양"),
        (r"봉분|burial mound", "흙을 쌓은 봉분", "무덤 형태"),
        (r"\bpillars?\b|\bcolumns?\b|기둥", "기둥", "부분"),
        (r"\bgateways?\b|출입문", "드나드는 문", "부분"),
        (r"\bramparts?\b|성벽", "성을 둘러싼 벽", "부분"),
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


NEGATION = r"\bnot\b|without|아니|않|없|모방|imitat|본떠"


def positive_clauses(quote):
    """Keep independently stated positive clauses; never strip a negative word alone."""
    clauses = re.split(r"[.;。]\s*|(?:있을\s*뿐|있지만|있으나)\s*|\b(?:but|whereas)\b", quote)
    return [c.strip() for c in clauses if c.strip() and not re.search(NEGATION, c, re.I)]


def reading_units(category, quote):
    quote = " ".join(positive_clauses(quote))
    units = [
        (axis, label)
        for pattern, label, axis in FEATURES.get(category, [])
        if re.search(pattern, quote, re.I)
    ]
    if category == "재료" and any(
        label in {"화강암", "대리석", "사암", "석회암"} for _, label in units
    ):
        units = [unit for unit in units if unit[1] != "돌"]
    return list(dict.fromkeys(units))


def observation_scope(label, quote):
    """A feature's part/axis, not the coarse category 'shape'. Unknown is not equivalent."""
    if label == "둥근 봉분" or label == "흙을 쌓은 봉분":
        return "봉분의 외형"
    if label == "위쪽이 둥근 아치":
        return "아치"
    if label == "둥글게 덮은 지붕":
        return "지붕"
    if label == "직사각형" and re.search(r"plan|평면|기단", quote, re.I):
        return "평면"
    if label == "십자 모양" and re.search(r"평면|plan", quote, re.I):
        return "평면"
    if label == "여덟 모서리가 있는 모양" and re.search(r"탑신", quote):
        return "탑신"
    if label == "네모 모양" and re.search(r"난간", quote):
        return "난간"
    return "설명 부분 미확인"


def usable_categories(fields):
    """Require interpretable evidence, not just a category assigned to a sentence."""
    return {
        f.category
        for f in fields
        if (
            f.category == "시대"
            and (
                source_years(f.evidence_quote)
                or re.search(r"\d{1,2}(?:세기|(?:st|nd|rd|th)[ -]century)", f.evidence_quote, re.I)
            )
        )
        or reading_units(f.category, f.evidence_quote)
    }


def material_scope(quote):
    """Describe the quoted part; never upgrade decoration into a building's main material."""
    for pattern, label in (
        (r"carvings?|조각|장식", "조각·장식"),
        (r"\broof\b|지붕", "지붕"),
        (r"\bceiling\b|천장|vault", "천장"),
        (r"봉분|호석|둘레돌|깬돌", "무덤 둘레"),
        (r"main structure|mausoleum|목조\s*건물", "건물"),
    ):
        if re.search(pattern, quote, re.I):
            return label
    return "사용 부분 확인 필요"


def source_years(quote):
    values = re.findall(r"\b\d{3,4}(?=년|\))|(?<=in )\d{3,4}\b", quote, re.I)
    for start, end in re.findall(
        r"\b(?:between|from)\s+(\d{3,4})\s+(?:and|to|[-–])\s+(\d{3,4})\b", quote, re.I
    ):
        values.extend((start, end))
    return list(dict.fromkeys(values))
