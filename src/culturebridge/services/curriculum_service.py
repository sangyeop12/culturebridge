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


def plan_learning(
    level: LearningLevel,
    goal: LearningGoal,
    goal_text: str = "",
    amount: LearningAmount = LearningAmount.STANDARD,
):
    focus = list(FOCUS[goal])
    requested = []
    for category, words in {
        "시대": ("시대", "연대", "연도", "건립", "언제"),
        "구조": ("구조", "모양"),
        "재료": ("재료", "돌", "나무"),
        "종교적 배경": ("종교", "불교"),
    }.items():
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
    if amount is LearningAmount.DEEP:
        steps = [step + " → 양쪽 원문 인용·대상 범위 확인" for step in steps]
        steps.append("공통점 후보의 양쪽 근거와 대체 해석 검토")
    if goal is LearningGoal.VERIFY:
        steps.insert(0, "원문 출처와 조회일 확인")
    if level is not LearningLevel.BEGINNER:
        steps.append("근거 부족 항목과 해석의 한계 확인")
    steps.append("목표에 맞는 5문항 퀴즈")
    return steps, focus
