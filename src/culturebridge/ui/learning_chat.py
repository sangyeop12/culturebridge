"""Conversation UI. Routine rendering never invokes remote AI or searches."""

from uuid import uuid4

from nicegui import ui

from culturebridge.domain.learning import LearningTurn
from culturebridge.services.learning_conversation_service import (
    ConversationConflictError,
    ConversationNotFoundError,
    create_conversation,
    get_conversation,
    list_conversations,
    request_learning_stop,
    send_learning_turn,
)
from culturebridge.services.learning_preferences import get_preferences, present_message
from culturebridge.services.operation_service import OperationBusyError
from culturebridge.ui.learning_controls import tone_controls, voice_controls
from culturebridge.ui.learning_intent import learning_intent_editor


def learning_entry(worker):
    with ui.card().classes("cb-card w-full p-6 gap-4"):
        ui.label("궁금한 역사 이야기부터 시작해요").classes("cb-title text-2xl").props(
            "role=heading aria-level=1"
        )
        ui.label("수준이나 문화유산을 먼저 고르지 않아도 괜찮아요.").classes("cb-muted")
        prompt = (
            ui.textarea(
                label="어떤 이야기가 궁금한가요?",
                placeholder="예: 역사를 잘 모르는데 어디부터 시작할까?",
            )
            .props("outlined autogrow maxlength=1000")
            .classes("w-full")
        )
        mic = voice_controls(prompt)
        tone_controls(worker)
        learning_intent_editor(worker)

        async def start():
            if not (prompt.value or "").strip():
                ui.notify("궁금한 점이나 관심사를 들려주세요.", color="warning")
                return
            button.disable()
            mic.disable()
            ui.run_javascript("window.CultureBridgeVoice?.cancel()")
            try:
                conversation = await worker(create_conversation)
                await worker(
                    send_learning_turn,
                    conversation.id,
                    LearningTurn(request_id=uuid4(), revision=0, text=prompt.value),
                )
                ui.navigate.to(f"/learn?conversation_id={conversation.id}")
            except (ValueError, OperationBusyError):
                ui.notify("대화를 시작하지 못했어요. 잠시 뒤 다시 시도해 주세요.", color="warning")
            finally:
                button.enable()
                mic.enable()

        button = ui.button("함께 알아보기", on_click=start).props("unelevated")
        ui.link("이전 대화 이어가기", "/learn")
        ui.link("홈 화면에 추가하기", "/install")


def learning_chat(worker, conversation_id=""):
    state = None
    if conversation_id:
        try:
            state = get_conversation(conversation_id)
        except ConversationNotFoundError:
            ui.label("이 대화를 찾을 수 없어요. 이 브라우저의 대화 목록에서 다시 골라주세요.")
            ui.link("대화 목록으로", "/learn")
            return
    if state is None:
        ui.label("이어서 나누는 역사 이야기").classes("cb-title text-2xl")
        ui.label(
            "대화는 현재 브라우저의 익명 세션에 연결돼요. 다른 기기와 자동 동기화되지는 않아요."
        )
        for item in list_conversations():
            ui.link(item["goal"], f"/learn?conversation_id={item['id']}")
        learning_entry(worker)
        return

    ui.label("함께 알아가는 역사").classes("cb-title text-2xl").props("role=heading aria-level=1")
    ui.link("대화 목록으로", "/learn")
    if state.quiz_review:
        ui.link("퀴즈 해설과 학습 기록으로", "/learning-history")
        ui.label(
            "퀴즈 문항·답안·채점 근거로 복습해요. "
            "대화를 보내면 AI가 이 내용을 함께 참고할 수 있어요."
        ).classes("cb-muted")
    transcript = ui.column().classes("w-full gap-4")
    status = ui.label().props("role=status aria-live=polite").classes("cb-muted")
    prompt = (
        ui.textarea(label="이야기 이어가기")
        .props("outlined autogrow maxlength=1000")
        .classes("w-full")
    )
    controls = [voice_controls(prompt)]
    pending = None
    busy = False

    refresh_intent = None

    async def submit(control="message", source_id=""):
        nonlocal state, pending, busy
        if busy:
            return
        text = (prompt.value or "").strip()
        if control in {"message", "correct"} and not text:
            ui.notify("내용을 입력해 주세요.", color="warning")
            return
        # Keep the same ID after an uncertain transport failure; never duplicate a turn on retry.
        signature = (state.revision, text, control, source_id)
        if pending is None or pending[0] != signature:
            pending = (
                signature,
                LearningTurn(
                    request_id=uuid4(),
                    revision=state.revision,
                    text=text,
                    control=control,
                    source_id=source_id,
                ),
            )
        busy = True
        ui.run_javascript("window.CultureBridgeVoice?.cancel()")
        for button in controls:
            button.disable()
        status.set_text("자료와 다음 학습을 살펴보고 있어요…")
        try:
            state = await worker(send_learning_turn, state.id, pending[1])
            if control != "review_question":
                prompt.set_value("")
            pending = None
            render()
            if refresh_intent:
                refresh_intent()
            status.set_text("")
        except ConversationConflictError:
            state = await worker(get_conversation, state.id)
            pending = None
            render()
            status.set_text("대화가 바뀌었어요. 최신 내용을 불러왔으니 확인 후 다시 보내주세요.")
        except (ValueError, OperationBusyError) as exc:
            status.set_text(str(exc))
        except Exception:
            status.set_text(
                "처리 결과를 확인하지 못했어요. 같은 내용으로 다시 보내면 중복을 확인해요."
            )
        finally:
            busy = False
            for button in controls:
                button.enable()

    def render():
        preferences = get_preferences()
        transcript.clear()
        with transcript:
            if state.goal:
                ui.label("지금 함께 살펴볼 목표: " + state.goal).classes("cb-title text-lg")
            if state.notice:
                ui.label(state.notice).classes("cb-muted").props("role=status")
            if state.status == "paused":
                ui.label("잠시 멈춘 대화예요. ‘이어서 학습’을 누르면 다시 시작해요.")
            for message in state.messages:
                with ui.card().classes("cb-card w-full p-5 gap-2"):
                    ui.label("나" if message.role == "user" else "컬처브릿지").classes(
                        "font-semibold"
                    )
                    ui.label(present_message(message, preferences)).style("white-space:pre-wrap")
                    if message.kind == "dictionary" and message.citations:
                        ui.label("출처: 국립국어원 표준국어대사전 · 뜻풀이 원문 그대로")
                        ui.link(
                            "CC BY-SA 2.0 대한민국",
                            message.citations[0]["license_url"],
                            new_tab=True,
                        )
                    for citation in message.citations:
                        with ui.expansion("설명의 공식 근거"):
                            ui.label(citation["quote"]).style("white-space:pre-wrap")
                            ui.link(citation["title"], citation["url"], new_tab=True)
                            if citation.get("license_url"):
                                ui.link(
                                    citation["license_name"], citation["license_url"], new_tab=True
                                )
                                ui.label(
                                    "뜻풀이 원문 그대로 · 용례와 멀티미디어는 수집하지 않아요."
                                )
                    for suggestion in message.suggestions:
                        ui.link(
                            suggestion["label"],
                            suggestion["url"],
                            new_tab=suggestion["url"].startswith(("https://", "http://")),
                        )
            if state.search_results:
                with ui.expansion("찾은 공식 자료 살펴보기").classes("w-full"):
                    for result in state.search_results:
                        ui.button(
                            result["name"],
                            on_click=lambda _, identity=result["id"]: submit(
                                "read_source", identity
                            ),
                        ).props("flat no-caps")
            if state.quiz_review.get("items"):
                with ui.expansion("다른 문항 다시 살펴보기").classes("w-full"):
                    ui.label("점수나 한 번의 오답만으로 이해도를 확정하지 않아요.")
                    for item in state.quiz_review["items"]:
                        number = str(item["number"])
                        ui.button(
                            f"{number}번 · {item['question']}",
                            on_click=lambda _, n=number: submit("review_question", n),
                        ).props("outline no-caps")
            if state.concepts:
                with ui.expansion("내 이해도에 대한 잠정 기록"):
                    ui.label(
                        "점수나 확정 등급이 아니에요. 다르게 느끼면 정정할 내용을 입력해 주세요."
                    )
                    labels = {
                        "tentative_support": "설명을 이해한 근거가 일부 있어요",
                        "possible_misconception": "다시 살펴볼 부분이 있어요",
                        "unclear": "아직 판단하기 어려워요",
                        "disputed_by_learner": "정정 요청으로 다시 확인 중이에요",
                    }
                    for concept, record in state.concepts.items():
                        ui.label(concept + ": " + labels.get(record["status"], "추가 확인 필요"))
                        for observation in record["observations"]:
                            if observation.get("question_number"):
                                ui.label(
                                    f"퀴즈 복습 {observation['question_number']}번에서 나눈 설명"
                                )
                            ui.label("내 설명: " + observation["learner_text"])
                            ui.label("확인 근거: " + observation["quote"])
            if state.plan_history:
                with ui.expansion("다음 학습을 이렇게 제안했어요"):
                    ui.label(state.plan_history[-1]["reason"])

    async def stop():
        if not busy:
            await submit("stop")
            return
        try:
            await worker(request_learning_stop, state.id, state.revision)
            status.set_text("중단을 요청했어요. 진행 중인 응답을 정리한 뒤 멈춰요.")
        except (ConversationNotFoundError, ConversationConflictError):
            status.set_text("요청이 끝났거나 대화가 바뀌었어요. 최신 내용을 확인해 주세요.")

    render()
    tone_controls(worker, render)
    refresh_intent = learning_intent_editor(worker)
    with ui.row().classes("flex-wrap gap-2"):
        for label, control in (
            ("보내기", "message"),
            ("건너뛰기", "skip"),
            ("다른 주제로", "change_topic"),
            ("이어서 학습", "resume"),
            ("입력한 내용으로 정정 요청", "correct"),
        ):
            controls.append(
                ui.button(label, on_click=lambda _, action=control: submit(action)).props(
                    "outline no-caps"
                )
            )
        ui.button("잠시 중단", on_click=stop).props("outline no-caps")
