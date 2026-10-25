"""Automatic learning hints with optional user corrections; never ask to approve each guess."""

from nicegui import ui
from pydantic import ValidationError

from culturebridge.services.automatic_intent_service import (
    clear_automatic_intent,
    get_automatic_intent,
)
from culturebridge.services.learning_conversation_service import ConversationConflictError
from culturebridge.services.learning_intent_service import (
    LearningIntent,
    get_learning_intent,
    save_learning_intent,
)


def learning_intent_editor(worker, *, expanded=False):
    state = get_learning_intent()
    with ui.expansion("내 관심사와 학습 목표", icon="explore", value=expanded).classes("w-full"):
        ui.label("대화하면서 관심사와 목표를 파악해요. 매번 저장 여부를 묻지 않아요.")
        ui.label(
            "파악한 내용은 다음 대화에도 이어져요. "
            "추정이 틀릴 수 있고, 지금 하는 질문이 우선이에요. "
            "관심사나 스스로 적은 설명만으로 이해도 점수를 매기지 않아요."
        ).classes("cb-muted")

        @ui.refreshable
        def summary():
            profile = get_automatic_intent()
            policy = get_learning_intent()
            if not policy.infer_from_dialogue:
                ui.label("대화에서 관심사·목표를 자동으로 기록하는 기능이 꺼져 있어요.")
            if profile["interests"]:
                ui.label("최근 관심 주제: " + ", ".join(i["topic"] for i in profile["interests"]))
            if profile["goal"]:
                ui.label("현재 파악한 학습 목표: " + profile["goal"]["topic"])
            if not profile["interests"] and not profile["goal"]:
                ui.label("아직 파악 중이에요. 궁금한 이야기를 편하게 나눠주세요.")
            else:
                with ui.expansion("어떤 대화에서 파악했나요?"):
                    items = profile["interests"] + ([profile["goal"]] if profile["goal"] else [])
                    for item in items:
                        ui.label(item["topic"] + " · 대화에 따른 추정")
                        ui.label("내가 한 말: " + item["quote"])

        summary()
        automatic = ui.checkbox(
            "대화에서 관심사와 목표 자동 파악하기", value=state.infer_from_dialogue
        )
        ui.label("필요할 때만 아래에서 직접 지정하거나 수정할 수 있어요.").classes("cb-muted")
        interests = (
            ui.input(
                label="관심 있는 이야기",
                value=", ".join(state.interests),
                placeholder="예: 조선의 생활, 불교 건축, 세계의 궁궐",
            )
            .props("maxlength=334")
            .classes("w-full")
        )
        ui.label("쉼표로 구분해 최대 8개, 각각 40자까지 적어주세요.").classes("cb-muted text-sm")
        goal = (
            ui.textarea(label="앞으로 배우고 싶은 것", value=state.goal)
            .props("outlined autogrow maxlength=300")
            .classes("w-full")
        )
        experience = (
            ui.textarea(label="내가 알고 있는 것 (선택)", value=state.experience)
            .props("outlined autogrow maxlength=300")
            .classes("w-full")
        )
        enabled = ui.checkbox(
            "직접 지정한 관심사·목표를 학습 제안에 우선 참고하기", value=state.use_for_planning
        )
        ui.label(
            "이 선택은 직접 입력한 내용에만 적용돼요. 자동 파악은 위의 설정을 따라요. "
            "개인정보나 비밀은 적지 마세요. 해제 후 적용하면 다음 요청부터 추가 전달하지 않아요. "
            "이미 진행 중인 응답과 이전 대화는 바뀌지 않아요."
        ).classes("cb-muted text-sm")
        status = ui.label().props("role=status aria-live=polite")
        buttons = []

        def show(saved):
            nonlocal state
            state = saved
            interests.set_value(", ".join(saved.interests))
            goal.set_value(saved.goal)
            experience.set_value(saved.experience)
            enabled.set_value(saved.use_for_planning)
            automatic.set_value(saved.infer_from_dialogue)
            summary.refresh()

        async def save(clear=False):
            nonlocal state
            for button in buttons:
                button.disable()
            try:
                proposal = (
                    LearningIntent(revision=state.revision, infer_from_dialogue=automatic.value)
                    if clear
                    else LearningIntent(
                        revision=state.revision,
                        interests=[
                            s.strip() for s in (interests.value or "").split(",") if s.strip()
                        ],
                        goal=goal.value or "",
                        experience=experience.value or "",
                        use_for_planning=enabled.value,
                        infer_from_dialogue=automatic.value,
                    )
                )
                show(await worker(save_learning_intent, proposal))
                status.set_text(
                    "직접 입력한 내용을 비웠어요. 대화에서 파악한 내용과 이전 기록은 그대로예요."
                    if clear
                    else "저장했어요. 다음 요청부터 참고해요."
                    if state.use_for_planning
                    else "저장했어요. 학습 제안에는 참고하지 않아요."
                )
            except ValidationError:
                status.set_text(
                    "관심사는 8개·각 40자, 목표와 내가 알고 있는 내용은 각각 300자까지 적어주세요."
                )
            except ConversationConflictError:
                status.set_text(
                    "다른 화면에서 바뀐 내용이 있어요. 작성한 내용은 유지했어요. "
                    "‘저장한 내용 다시 불러오기’로 확인한 뒤 다시 저장해 주세요."
                )
            except Exception:
                status.set_text(
                    "설정을 저장하지 못했어요. 작성한 내용은 유지했으니 다시 시도해 주세요."
                )
            finally:
                for button in buttons:
                    button.enable()

        async def reload():
            for button in buttons:
                button.disable()
            try:
                show(await worker(get_learning_intent))
                status.set_text("저장한 내용을 다시 불러왔어요.")
            except Exception:
                status.set_text(
                    "불러오지 못했어요. 작성한 내용은 그대로 두었으니 다시 시도해 주세요."
                )
            finally:
                for button in buttons:
                    button.enable()

        async def reset_automatic():
            for button in buttons:
                button.disable()
            try:
                show(await worker(clear_automatic_intent))
                status.set_text(
                    "자동 파악을 끄고 추정 기록을 비웠어요. "
                    "직접 지정한 내용과 이전 대화는 그대로예요."
                )
            except Exception:
                status.set_text("변경하지 못했어요. 현재 설정을 다시 불러와 확인해 주세요.")
            finally:
                for button in buttons:
                    button.enable()

        with ui.row().classes("gap-2 flex-wrap"):
            buttons.append(
                ui.button("직접 수정한 내용과 설정 적용", on_click=lambda: save()).props("outline")
            )
            buttons.append(
                ui.button("직접 입력한 내용 비우기", on_click=lambda: save(True)).props("flat")
            )
            buttons.append(ui.button("저장한 내용 다시 불러오기", on_click=reload).props("flat"))
            buttons.append(
                ui.button("자동 파악 끄고 기록 비우기", on_click=reset_automatic).props("flat")
            )
    return summary.refresh
