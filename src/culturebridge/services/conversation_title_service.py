"""Stable conversation labels from learner text, including existing saved chats."""

import re

_CONTROLS = {
    "안녕",
    "안녕하세요",
    "시작",
    "이어서",
    "이어서학습",
    "이어서이야기하기",
    "이어서진행해주세요",
    "이어서설명해주세요",
    "계속해주세요",
    "잠시중단",
    "이내용건너뛰기",
    "퀴즈답안을제출했어요",
    "선택한공식자료살펴보기",
}


def conversation_title(state):
    if state.get("title"):
        return _shorten(state["title"])
    for message in state.get("messages", []):
        if message.get("role") != "user":
            continue
        text = " ".join(message.get("text", "").split()).strip()
        if not text or re.sub(r"[\s.!?？]", "", text) in _CONTROLS:
            continue
        text = re.sub(r"^(?:다른 주제로|기록 정정 요청):\s*", "", text)
        text = re.sub(
            r"에\s*(?:대해|관해)\s*(?:알고|배우고|알아보고)\s*싶(?:어요|어|습니다)[.!?？]*$",
            " 알아보기",
            text,
        )
        return _shorten(text)
    fallback = state.get("pending_request") or state.get("goal") or ""
    if fallback and re.sub(r"[\s.!?？]", "", fallback) not in _CONTROLS:
        return _shorten(fallback)
    return "새 대화"


def conversation_preview(state):
    """A short learner-facing excerpt, not timestamps or internal execution metadata."""
    title = conversation_title(state)
    for message in reversed(state.get("messages", [])):
        if message.get("role") == "user":
            candidate = conversation_title({"messages": [message]})
            if candidate not in {title, "새 대화"}:
                return candidate
    for message in reversed(state.get("messages", [])):
        for paragraph in message.get("text", "").splitlines():
            if (
                re.search(r"[가-힣]", paragraph)
                and not re.search(
                    r"Gemini|API|SDK|검증 실패|공식 원문:|현재 자료와 요청|"
                    r"쉽게 풀어드릴게요|사용량 한도|사전 자동 조회",
                    paragraph,
                )
                and re.sub(r"[\s.!?？]", "", paragraph) not in _CONTROLS
            ):
                text = " ".join(paragraph.split())
                return text if len(text) <= 70 else text[:69].rstrip() + "…"
    return ""


def _shorten(text):
    text = " ".join(text.split())
    return text if len(text) <= 44 else text[:43].rstrip() + "…"
