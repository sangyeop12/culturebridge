"""Consistent, accessible learning stages; not a claim that a stage is completed."""

from nicegui import ui

STAGES = ("자료 읽기", "핵심 비교", "퀴즈", "복습·학습지")


def step_label(step):
    replacements = {
        "의 주장과 원문 범위 대조": " 살펴보기 · 공식 설명 함께 읽기",
        " → 양쪽 원문 인용·대상 범위 확인": " · 두 유산의 원문 함께 읽기",
        "공통점 후보의 양쪽 근거와 대체 해석 검토": "공통점은 무엇인지 다른 관점에서도 생각해 보기",
        "원문 출처와 조회일 확인": "공식 자료의 출처 알아보기",
        "근거 부족 항목과 해석의 한계 확인": "자료에 나오지 않은 내용 구분하기",
        "같은 표현이 같은 의미인지 양쪽 문맥 대조하기": (
            "두 설명에서 같은 말이 어떻게 쓰였는지 살펴보기"
        ),
        "유사성과 교류·영향의 직접 증거 구분하기": (
            "닮은 모습과 실제로 영향을 주고받은 흔적 구분하기"
        ),
    }
    for original, label in replacements.items():
        step = step.replace(original, label)
    return step


def learning_steps(current=0, curriculum=()):
    with (
        ui.element("ol")
        .classes("flex flex-wrap gap-2 p-0 m-0 list-none")
        .props('aria-label="학습 단계"')
    ):
        for index, label in enumerate(STAGES):
            item = ui.element("li").classes("rounded-lg px-3 py-2 border text-sm")
            item.style("border-color:var(--cb-line);background:var(--cb-surface)")
            if current == index:
                item.props('aria-current="step"').classes("font-semibold")
                item.style(
                    "background:var(--cb-soft);border-color:var(--cb-green);color:var(--cb-green)"
                )
            with item:
                ui.label(f"{index + 1}. {label}")
    if curriculum:
        with ui.expansion("이번 학습에서 살펴볼 내용").classes("w-full"):
            for index, step in enumerate(curriculum, 1):
                ui.label(f"{index}. {step_label(step)}")
