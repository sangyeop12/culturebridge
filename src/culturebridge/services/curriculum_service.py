from culturebridge.domain.models import LearningAmount, LearningGoal, LearningLevel

AMOUNT_LABELS = {
    "brief": "짧게 · 핵심 2항목",
    "standard": "기본 · 목표 항목",
    "deep": "깊게 · 원문 대조",
}

GOAL_LABELS = {
    "observe": "모양·재료 관찰",
    "compare": "시대·구조 비교",
    "religion": "종교적 배경과 맥락",
    "verify": "출처와 근거 검토",
}
FOCUS = {
    LearningGoal.OBSERVE: ["재료", "구조"],
    LearningGoal.COMPARE: ["시대", "구조", "재료", "종교적 배경"],
    LearningGoal.RELIGION: ["종교적 배경", "구조"],
    LearningGoal.VERIFY: ["시대", "구조", "재료", "종교적 배경"],
}

GOAL_WORDS = {
    "시대": ("시대", "연대", "연도", "건립", "창건", "재건", "복원", "언제"),
    "구조": ("구조", "모양", "배치", "평면", "양식"),
    "재료": ("재료", "돌", "나무", "석재", "목재", "벽돌"),
    "종교적 배경": ("종교", "불교", "힌두", "이슬람", "기독교", "신앙", "의례"),
}


def required_categories(goal_text):
    requested = {
        category for category, words in GOAL_WORDS.items() if any(w in goal_text for w in words)
    }
    mode = goal_text.split(" ", 1)[0]
    if mode == "religion":
        requested.add("종교적 배경")
    elif mode == "observe":
        requested.update(("재료", "구조"))
    return requested


def evidence_suits_goal(left_categories, right_categories, goal_text):
    shared = set(left_categories) & set(right_categories)
    return len(shared) >= 2 and required_categories(goal_text) <= shared


def plan_learning(
    level: LearningLevel,
    goal: LearningGoal,
    goal_text: str = "",
    amount: LearningAmount = LearningAmount.STANDARD,
):
    focus = list(FOCUS[goal])
    requested = []
    for category, words in GOAL_WORDS.items():
        positions = [goal_text.find(word) for word in words if word in goal_text]
        if positions:
            requested.append((min(positions), category))
    priority = [category for _, category in sorted(requested)]
    focus = priority + [category for category in focus if category not in priority]
    if amount is LearningAmount.BRIEF:
        focus = focus[:2]
    labels = {
        LearningLevel.BEGINNER: {
            "시대": "언제 만들었는지 보기",
            "구조": "모양 보기",
            "재료": "무엇으로 만들었는지 보기",
            "종교적 배경": "종교와 관련된 표현 찾기",
        },
        LearningLevel.INTERMEDIATE: {
            key: key + "의 공통점·차이점 비교" for key in FOCUS[LearningGoal.COMPARE]
        },
        LearningLevel.ADVANCED: {
            key: key + "의 주장과 원문 범위 대조" for key in FOCUS[LearningGoal.COMPARE]
        },
    }[level]
    steps = [labels[item] for item in focus]
    if "재건" in goal_text or "복원" in goal_text:
        steps.insert(0, "창건·건립과 재건·복원의 사건별 연대를 구분하기")
    if "차이" in goal_text:
        steps.append("서로 다른 특징과 각각의 원문 근거 찾기")
    if "공통" in goal_text:
        steps.append("같은 표현이 같은 의미인지 양쪽 문맥 대조하기")
    if "영향" in goal_text or "교류" in goal_text:
        steps.append("유사성과 교류·영향의 직접 증거 구분하기")
    if amount is LearningAmount.DEEP:
        steps = [step + " → 양쪽 원문 인용·대상 범위 확인" for step in steps]
        steps.append("공통점 후보의 양쪽 근거와 대체 해석 검토")
    if goal is LearningGoal.VERIFY:
        steps.insert(0, "원문 출처와 조회일 확인")
    if level is not LearningLevel.BEGINNER:
        steps.append("근거 부족 항목과 해석의 한계 확인")
    steps.append("목표에 맞는 5문항 퀴즈")
    return steps, focus
