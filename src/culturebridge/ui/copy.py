"""Translate known internal notices without changing the conversational tone or source text."""

SERVICE_NOTICES = {
    "AI 계획을 사용할 수 없어 제한된 안내로 이어가요. 이해도는 자동 평가하지 않아요.": (
        "지금은 맞춤 응답에 연결되지 않아 기본 안내로 이어가요. "
        "이 대화에서는 이해도를 판단하지 않아요."
    ),
    "자동완성용 공식 이름 캐시를 저장하지 못했습니다. 검색 결과는 표시합니다.": (
        "검색어 추천 정보를 갱신하지 못했어요. 검색 결과는 확인할 수 있어요."
    ),
    "같은 요청 번호에 다른 내용을 보낼 수 없어요.": (
        "이전 요청과 입력 내용이 달라요. 대화를 새로 불러온 뒤 다시 보내주세요."
    ),
}


def service_text(text):
    """Only approved system-message substitutions; no generic formality rewriting."""
    return SERVICE_NOTICES.get(text, text)
