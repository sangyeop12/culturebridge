"""Presentation only. Never changes official names, identifiers or evidence quotes."""

import re

# Korean guidance names, not a claim that every entry has an official Korean title.
KOREAN_NAMES = {
    "660": "호류지 지역의 불교 건축물",
    "736": "석굴암과 불국사",
    "1442": "실크로드: 창안–톈산 회랑 도로망",
    "1675": "실크로드: 자라프샨–카라쿰 회랑",
    "561": "랑기리 담불라 석굴 사원",
    "1732": "옌뜨–빈응이엠–꼰선·끼엡박 유적 및 경관 복합단지",
    "1039": "윈강 석굴",
    "1003": "룽먼 석굴",
    "927": "사르나트 고대 불교 유적",
    "1139": "아스키아 무덤",
    "252": "타지마할",
    "438": "만리장성",
    "439": "베이징과 선양의 명·청 황궁",
    "1418": "후지산",
    "668": "앙코르 유적",
    "274": "마추픽추 역사 보호구역",
    "91": "로마 역사 지구와 교황청 관련 유산",
    "86": "멤피스와 네크로폴리스: 기자–다슈르 피라미드 지대",
    "83": "베르사유 궁전과 공원",
    "976": "경주 역사유적지구",
    "688": "고도 교토의 문화유산",
    "870": "고도 나라의 문화유산",
    "913": "닛코의 신사와 사찰",
    "734": "시라카와고와 고카야마의 역사 마을",
    "661": "히메지성",
    "776": "이쓰쿠시마 신사",
    "592": "보로부두르 사원군",
    "642": "프람바난 사원군",
    "1588": "바간",
    "707": "라싸 포탈라궁 역사 유적군",
    "1056": "보드가야 마하보디 사원군",
    "524": "산치 불교 유적",
    "242": "아잔타 석굴",
    "243": "엘로라 석굴",
    "816": "창덕궁",
    "738": "종묘",
    "817": "수원 화성",
    "737": "해인사 장경판전",
    "1477": "백제 역사유적지구",
    "1562": "산사, 한국의 산지 승원",
    "1498": "한국의 서원",
    "1666": "가야고분군",
}
COUNTRIES = {
    "Republic of Korea": "대한민국",
    "China": "중국",
    "Japan": "일본",
    "India": "인도",
    "Sri Lanka": "스리랑카",
    "Viet Nam": "베트남",
    "Kyrgyzstan": "키르기스스탄",
    "Kazakhstan": "카자흐스탄",
    "Tajikistan": "타지키스탄",
    "Uzbekistan": "우즈베키스탄",
    "Turkmenistan": "투르크메니스탄",
    "Mali": "말리",
    "Iran (Islamic Republic of)": "이란",
    "Cambodia": "캄보디아",
    "France": "프랑스",
    "Italy": "이탈리아",
    "Peru": "페루",
    "Egypt": "이집트",
    "United States of America": "미국",
    "Germany": "독일",
    "Spain": "스페인",
    "United Kingdom of Great Britain and Northern Ireland": "영국",
    "Holy See": "교황청",
}
THEME_LABELS = {
    "Buddhist": "불교 관련 문화",
    "Temple": "사찰·사원",
    "Pagoda": "탑",
    "Grotto": "석굴",
    "Palace": "궁전",
    "Fort": "성곽",
    "Tomb": "무덤·묘역",
    "Church": "교회",
    "Mosque": "모스크",
    "Islamic": "이슬람 관련 문화",
    "Hindu": "힌두교 관련 문화",
    "Hall": "전각·건물",
    "Gate": "문",
}


def korean_name(heritage_id: str, official_name: str) -> str | None:
    if heritage_id.startswith("official:"):
        from culturebridge.services.individual_source_service import INDIVIDUALS

        record = INDIVIDUALS.get(heritage_id.split(":", 1)[1])
        if record:
            return record["korean"]
    if re.search(r"[가-힣]", official_name):
        return official_name
    if heritage_id.startswith("unesco:"):
        from culturebridge.services.name_registry_service import names

        row = names().get(heritage_id)
        if row and row["official_name"] == official_name and row["status"] != "unavailable":
            return row["korean_name"]
        return KOREAN_NAMES.get(heritage_id.split(":", 1)[1])
    return None


def display_name(heritage_id: str, official_name: str) -> str:
    name = korean_name(heritage_id, official_name)
    if name == official_name:
        return official_name
    if name:
        from culturebridge.services.name_registry_service import names

        row = names().get(heritage_id)
        suffix = " · AI 번역 후보" if row and row["status"] == "ai_candidate" else ""
        return f"{name}({official_name}){suffix}"
    return f"한국어 이름 확인 필요({official_name})"


def display_country(country: str) -> str:
    return " · ".join(COUNTRIES.get(part.strip(), part.strip()) for part in country.split(";"))


def readable_reason(criteria: list[str], beginner: bool = True) -> str:
    text = " ".join(criteria)
    themes = [label for key, label in THEME_LABELS.items() if re.search(rf"\b{key}\b", text)]
    if themes:
        reason = "공식 소개에서 함께 찾아볼 표현: " + " · ".join(themes) + "."
        if "같은 핵심 유형" in text:
            reason = "같은 종류의 유산이라 구조를 함께 살펴볼 수 있어요. " + reason
    else:
        reason = "공식 자료에서 찾은 비교 후보예요. 어떤 점을 비교할 수 있는지 더 확인해야 해요."
    if "다른 국가" in text:
        reason += " 다른 나라에 있는 유산이에요."
    if beginner:
        reason += " 같은 모양이나 재료인지는 아직 판단하지 않았어요."
    else:
        reason += " 표현의 유사성만으로 같은 구조나 직접 영향을 확정하지 않습니다."
    return reason


def readable_trace(step):
    labels = {
        "target_tool": "선택 유산 확인",
        "planner_agent": "검색 방법 정하기",
        "selector_agent": "비교 대상 고르기",
        "search_tool": "공식 자료 찾기",
        "candidate_tool": "비교 대상 근거 확인",
        "decision_agent": "탐구 가능 여부 판단",
        "curriculum_agent": "학습 순서 정하기",
        "history_agent": "자료 수집",
        "comparison_tool": "근거 비교",
        "verification_agent": "근거 점검",
        "research_retry_tool": "자료 다시 찾기",
        "quiz_agent": "퀴즈 준비",
    }
    prefix, sep, body = step.partition(":")
    return labels.get(prefix, prefix) + sep + body


def learning_title(name):
    last = name[-1]
    particle = "과" if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 else "와"
    return name + particle + " 함께 살펴볼 문화유산"


def learner_status(result, beginner: bool):
    if not result.get("comparison"):
        if result.get("candidates"):
            return "비교 후보는 찾았지만, 선택한 유산의 자료가 부족해 자동 비교는 보류했어요."
        return "함께 비교할 자료를 충분히 찾지 못했어요. 다른 유산을 찾아보세요."
    if result.get("comparison", {}).get("learning_notices"):
        return (
            "자료에서 확인하지 못한 내용은 아직 판단하지 않았어요."
            if beginner
            else "비교에 필요한 일부 근거가 부족해 판단을 보류했습니다."
        )
    return (
        "공식 자료에서 찾은 설명이에요. 원문과 뜻을 함께 확인해 보세요."
        if beginner
        else "원문에 연결된 비교 후보입니다. 의미 검토는 별도로 필요합니다."
    )
