"""Level-specific reading aids; original provider text is never rewritten in storage."""

import re

from pydantic import BaseModel, Field, HttpUrl

from culturebridge.domain.models import CollectedSource, LearningLevel
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.subject_service import date_event

GLOSSARY = {
    "석탑": "돌로 만든 탑",
    "목탑": "나무로 만든 탑",
    "팔각형": "여덟 모서리가 있는 모양",
    "건립": "만듦",
    "창건": "처음 세움",
    "중건": "다시 세움",
    "중창": "다시 세우거나 크게 고침",
    "기단": "건물을 받치는 아랫부분",
    "탑신": "탑의 몸체",
    "전실": "앞쪽 방",
    "주실": "중심이 되는 방",
    "가람": "사찰의 건물과 배치",
    "봉분": "무덤 위에 쌓은 흙더미",
    "호석": "무덤 둘레를 보호하는 돌",
    "원분": "둥근 봉분",
    "석재": "돌로 된 재료",
    "화강암": "돌의 한 종류",
    "목재": "나무 재료",
    "난간": "가장자리에 세운 안전 울타리",
    "법궁": "왕이 주로 사용하는 중심 궁궐",
    "법화경": "불교 경전의 하나",
}
CATEGORY_LABELS = {
    "시대": "언제 만들어졌을까요?",
    "구조": "어떤 모양일까요?",
    "재료": "무엇으로 만들었을까요?",
    "종교적 배경": "종교와 어떤 관련이 있을까요?",
}


class LessonSection(BaseModel):
    category: str
    heading: str
    text: str
    evidence_quote: str
    event: str | None = None


class HeritageLesson(BaseModel):
    level: LearningLevel
    title: str
    intro: str
    sections: list[LessonSection] = Field(default_factory=list)
    original_text: str
    source_url: HttpUrl
    notice: str
    glossary: dict[str, str] = Field(default_factory=dict)


def easy_korean(text):
    # Expand terms only: dates, negation, attribution and uncertainty stay in place.
    return re.sub(
        "|".join(sorted(GLOSSARY, key=len, reverse=True)),
        lambda m: f"{m.group()}({GLOSSARY[m.group()]})",
        text,
    )


def beginner_text(category, quote):
    if re.search(r"[가-힣]", quote):
        if category == "시대":
            dates = list(
                dict.fromkeys(re.findall(r"\d{3,4}(?=년)|(?<=\()\d{3,4}(?=\))|\d{1,2}세기", quote))
            )
            if dates:
                when = " · ".join(d if d.endswith("세기") else d + "년" for d in dates)
                uncertain = bool(re.search(r"추측|추정|전해|알려|다고 한다", quote))
                caution = " 확정된 연대가 아니라 추정·전승 표현이 포함돼요." if uncertain else ""
                if re.search(r"아니|않|없", quote):
                    caution += " 부정 표현이 있어 연대를 단정하지 않아요."
                return f"원문에 나온 시기는 {when}이에요. 사건: {date_event(quote)}." + caution
        if len(quote) > 180:
            found = [
                term + "(" + meaning + ")" for term, meaning in GLOSSARY.items() if term in quote
            ]
            if found:
                return (
                    "이 항목에서 살펴볼 표현: "
                    + " · ".join(found[:3])
                    + ". 자세한 문맥은 공식 원문에서 확인해요."
                )
        return easy_korean(quote)
    # Conservative Korean reading guide for English sources, not a full translation.
    uncertain = bool(re.search(r"probably|estimated|possibly|believed", quote, re.I))
    if category == "시대":
        century = re.search(r"(\d{1,2})(?:st|nd|rd|th)[ -]century", quote, re.I)
        year = re.search(
            r"(?:built|constructed|erected|founded)\s+(?:in\s+)?(\d{3,4})", quote, re.I
        )
        if century or year:
            when = century.group(1) + "세기" if century else year.group(1) + "년"
            event = date_event(quote)
            suffix = "추정하는 표현이 있어요" if uncertain else "관련된 설명이 있어요"
            return f"원문에는 {when}에 {suffix}. 연대가 가리키는 사건: {event}."
    terms = {
        "재료": [
            (r"granite", "화강암"),
            (r"wood", "나무"),
            (r"brick", "벽돌"),
            (r"marble", "대리석"),
            (r"\bstone\b", "돌"),
        ],
        "구조": [
            (r"pagoda|stupa", "탑"),
            (r"grotto|cave", "석굴"),
            (r"temple", "사찰·사원"),
            (r"layout", "건물 배치"),
            (r"palace", "궁궐"),
            (r"tomb|mausoleum", "무덤"),
        ],
        "종교적 배경": [
            (r"Buddhis|Buddha", "불교"),
            (r"Hindu", "힌두교"),
            (r"Islam|Muslim", "이슬람"),
            (r"Christian", "기독교"),
        ],
    }
    found = [label for pattern, label in terms.get(category, []) if re.search(pattern, quote, re.I)]
    if found:
        caution = (
            " 부정·추정 표현이 있어 원문을 더 확인해야 해요."
            if re.search(r"\bnot\b|without|probably|estimated", quote, re.I)
            else ""
        )
        return "원문에서 찾아볼 표현은 " + " · ".join(found) + "이에요." + caution
    return "이 항목은 아래 공식 원문과 함께 살펴봐요. 뜻을 추측해서 채우지 않아요."


def official_source(document):
    return CollectedSource(
        id=document.record_id,
        heritage_id=document.record_id,
        title=document.name,
        organization="국가유산청",
        source_url=document.source_url,
        feed_url=document.source_url,
        retrieved_at=document.retrieved_at,
        content=document.content,
        content_kind="individual_text",
        status="stale" if document.stale else "cached" if document.cached else "fresh",
        scope_note="국가유산청 개별 원문",
    )


def explain_source(source, level=LearningLevel.BEGINNER):
    level = LearningLevel(level)
    lesson = HeritageLesson(
        level=level,
        title=source.title,
        original_text=source.content,
        source_url=source.source_url,
        intro={
            LearningLevel.BEGINNER: "초급 · 핵심 특징을 쉬운 말과 용어 풀이로 살펴봐요.",
            LearningLevel.INTERMEDIATE: "중급 · 시대·구조·재료·종교적 배경을 "
            "항목별로 읽고 비교하세요.",
            LearningLevel.ADVANCED: "고급 · 수집된 공식 원문을 수정 없이 읽고 "
            "대상·사건·해석의 범위를 검토하세요.",
        }[level],
        notice="학습용 설명은 원문에서 찾은 검토 후보입니다. 없는 내용은 채우지 않습니다.",
    )
    if level is LearningLevel.ADVANCED:
        lesson.notice = "아래 본문은 수집된 공식 원문 그대로입니다. 학습용 풀이와 구분합니다."
        return lesson
    if source.status not in {"fresh", "cached"}:
        lesson.notice = (
            "자료가 오래됐거나 수집에 실패해 학습용 설명을 보류합니다. 원문 상태를 확인하세요."
        )
        return lesson
    fields = [validate_extraction(d, [source]) for d in _local_extraction([source])]
    lookup = {f.category: f for f in fields if f}
    for category, heading in CATEGORY_LABELS.items():
        field = lookup.get(category)
        if not field:
            lesson.sections.append(
                LessonSection(
                    category=category,
                    heading=heading if level is LearningLevel.BEGINNER else category,
                    text="현재 공식 자료에서 이 항목의 직접 근거를 찾지 못했어요."
                    if level is LearningLevel.BEGINNER
                    else "직접 근거 부족 · 해당 항목의 판단을 보류합니다.",
                    evidence_quote="",
                )
            )
            continue
        lesson.sections.append(
            LessonSection(
                category=category,
                heading=heading if level is LearningLevel.BEGINNER else category,
                text=beginner_text(category, field.evidence_quote)
                if level is LearningLevel.BEGINNER
                else field.evidence_quote
                if re.search(r"[가-힣]", field.evidence_quote)
                else "원문 표현 해설: " + beginner_text(category, field.evidence_quote),
                evidence_quote=field.evidence_quote,
                event=field.date_event,
            )
        )
    lesson.glossary = {
        term: meaning
        for term, meaning in GLOSSARY.items()
        if any(term in section.evidence_quote for section in lesson.sections)
    }
    if not re.search(r"[가-힣]", source.content):
        lesson.notice += " 한국어 안내는 원문 표현의 읽기 도움말이며 전체 번역문이 아닙니다."
    return lesson
