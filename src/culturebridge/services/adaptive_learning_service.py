"""Evidence-scoped teaching choices, not learner ability labels or mastery scores."""

import re


def teaching_route(conversation, source, concept, text=""):
    observations = [
        o
        for o in conversation.concepts.get(concept, {}).get("observations", [])
        if o.get("source_id") == source["id"]
        and not o.get("disputed_by_learner")
        and any(o.get("quote") and o["quote"] in e["quote"] for e in source["excerpts"])
    ][-5:]
    if conversation.concepts.get(concept, {}).get("status") == "disputed_by_learner":
        observations = []
    judgments = [o.get("judgment") for o in observations]
    repeated = sum(
        p.get("source_id") == source["id"]
        and p.get("concept") == concept
        and p.get("action") in {"explain", "review", "check"}
        for p in conversation.plan_history[-8:]
    )
    supporting = {
        o["learner_text"].strip()
        for o in observations[-3:]
        if o.get("judgment") == "tentative_support" and o.get("learner_text")
    }
    if re.search("쉽게|모르겠|이해.*안|다시 설명", text):
        mode, reason = "scaffold", "지금 요청한 쉬운 풀이를 먼저 제공해요."
    elif re.search("다른 문제|다른 질문|새 문제", text):
        mode, reason = "alternate_question", "같은 근거를 다른 관점에서 확인해요."
    elif judgments[-2:] == ["possible_misconception"] * 2:
        mode, reason = "contrast", "같은 근거에서 반복된 혼동을 작은 단계로 나누어 살펴봐요."
    elif judgments[-1:] == ["possible_misconception"]:
        mode, reason = "remediate", "방금 설명과 원문이 어긋난 부분을 다시 확인해요."
    elif judgments[-1:] == ["unclear"]:
        mode, reason = "scaffold", "이유가 아직 충분하지 않아 근거 찾기부터 이어가요."
    elif len(supporting) >= 2 and judgments[-1:] == ["tentative_support"]:
        mode, reason = (
            "deepen",
            ("서로 다른 설명 두 번을 참고해 해석 범위를 넓혀봐요. 숙달 확정은 아니에요."),
        )
    elif re.search("심화|더 깊|자세히", text):
        mode, reason = "deepen", "요청에 따라 원문의 해석 범위를 자세히 살펴봐요."
    elif repeated >= 2:
        mode, reason = "alternate_question", "같은 설명을 반복하기보다 다른 질문으로 확인해요."
    else:
        mode, reason = "explain", "현재 질문과 확보한 근거에서 설명을 시작해요."
    return {
        "mode": mode,
        "reason": reason,
        "observations": len(observations),
        "previous_explanations": repeated,
    }


def activity_question(concept, route, index=0):
    variants = {
        "시대": [
            "이 연대가 가리키는 사건은 무엇인가요? 원문의 표현으로 이유를 설명해 볼까요?",
            "원문에서 확실한 시기와 추정하는 시기를 어떻게 구분할 수 있을까요?",
        ],
        "구조": [
            "설명하는 부분과 그 특징을 각각 찾아 연결해 볼까요?",
            "이 문장은 유산 전체와 한 부분 중 무엇을 설명하나요? 근거를 찾아볼까요?",
        ],
        "재료": [
            "어떤 재료가 어느 부분에 쓰였는지 원문에서 찾아 설명해 볼까요?",
            "이 문장만으로 건물 전체의 재료까지 알 수 있을까요? 이유를 설명해 볼까요?",
        ],
        "종교적 배경": [
            "종교와 유산의 쓰임을 연결하는 표현을 찾아 설명해 볼까요?",
            "원문이 알려주는 종교적 맥락과 아직 알 수 없는 내용을 나눠볼까요?",
        ],
    }.get(
        concept,
        [
            "근거가 되는 짧은 표현을 찾고 그 뜻을 자기 말로 설명해 볼까요?",
            "원문으로 알 수 있는 점과 아직 판단하기 어려운 점은 무엇인가요?",
        ],
    )
    if route["mode"] in {"scaffold", "contrast"}:
        return "먼저 원문에서 중요한 표현 하나를 골라볼까요? 그 표현은 무엇을 설명하나요?"
    if route["mode"] == "deepen":
        return "이 근거로 알 수 있는 점과 알 수 없는 점을 구분하고, 더 필요한 자료를 제안해 볼까요?"
    return variants[index % len(variants)]
