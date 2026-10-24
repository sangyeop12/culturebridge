"""Consistent, accessible learning stages; not a claim that a stage is completed."""

from nicegui import ui

STAGES = ("자료 읽기", "핵심 비교", "퀴즈", "복습·학습지")


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
                ui.label(f"{index}. {step}")
