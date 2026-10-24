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
from culturebridge.ui.copy import service_text
from culturebridge.ui.learning_controls import voice_controls


def learning_entry(worker, *, embedded=False):
    with ui.card().classes("cb-card cb-learning-start w-full p-6 gap-4").props("id=history-start"):
        ui.label("궁금한 역사 이야기부터 시작해요").classes(
            "cb-title " + ("text-2xl" if embedded else "text-3xl")
        ).props(f"role=heading aria-level={2 if embedded else 1}")
        ui.label("수준이나 문화유산을 먼저 고르지 않아도 괜찮아요.").classes("cb-muted")
        with ui.expansion("어떤 자료로 배우나요?").classes("w-full"):
            ui.label(
                "한국 문화유산은 국가유산청 자료, 세계유산 검색은 UNESCO 등재 목록을 이용해요."
            )
            ui.label(
                "해외 상세 학습은 연결된 개별 유산 자료를 사용해요. "
                "모든 해외 유산을 지원하는 것은 아니에요."
            )
            ui.label(
                "인물·사건은 ‘신편 한국사’ 검색 결과에서 공식 원문으로 이동해 읽어요. "
                "해당 본문을 AI가 읽거나 요약하지는 않아요."
            )
        prompt = (
            ui.textarea(
                label="어떤 이야기가 궁금한가요?",
                placeholder="예: 역사를 잘 모르는데 어디부터 시작할까?",
            )
            .props("outlined autogrow maxlength=1000")
            .classes("w-full")
        )
        with ui.expansion("말로 질문하기", icon="mic").classes("w-full"):
            mic = voice_controls(prompt)

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

        with ui.row().classes("cb-start-actions"):
            button = ui.button("함께 알아보기", on_click=start, icon="arrow_forward").props(
                "unelevated"
            )
            if embedded:
                ui.link("이전 대화 이어가기", "/learn#conversation-list")
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
        conversations = list_conversations()
        learning_entry(worker)
        with ui.column().classes("w-full gap-3").props("id=conversation-list"):
            ui.label("이어서 나누는 역사 이야기").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            ui.label(
                "이 브라우저에서 나눈 대화를 이어갈 수 있어요"
                ". 다른 기기와 자동으로 연결되지는 않아요."
            ).classes("cb-muted text-sm")
            for item in conversations:
                ui.link(item["goal"], f"/learn?conversation_id={item['id']}").classes(
                    "cb-conversation-link"
                )
            if not conversations:
                ui.label(
                    "아직 나눈 이야기가 없어요. 첫 질문으로 나만의 배움을 시작해 보세요."
                ).classes("cb-muted")
        return

    ui.label("함께 알아가는 역사").classes("cb-title text-3xl").props("role=heading aria-level=1")
    ui.link("대화 목록으로", "/learn")
    if state.quiz_review:
        ui.link("퀴즈 해설과 학습 기록으로", "/learning-history")
        ui.label(
            "퀴즈 문항·답안·채점 근거로 복습해요. 대화를"
            " 보내면 AI가 이 내용을 함께 참고할 수 있"
            "어요."
        ).classes("cb-muted")
    transcript = ui.column().classes("cb-transcript w-full gap-4")
    status = ui.label().props("role=status aria-live=polite").classes("cb-muted")
    prompt = (
        ui.textarea(label="이야기 이어가기")
        .props("outlined autogrow maxlength=1000")
        .classes("cb-composer w-full")
    )
    with ui.expansion("말로 질문하기", icon="mic").classes("cb-chat-options"):
        controls = [voice_controls(prompt)]
    pending = None
    busy = False
    send_button = None
    quiz_controls = []

    async def submit(control="message", source_id="", answers=None):
        nonlocal state, pending, busy
        if busy:
            return
        text = control_text(control, prompt.value or "")
        if control in {"message", "correct"} and not text:
            ui.notify("내용을 입력해 주세요.", color="warning")
            return
        # Keep the same ID after an uncertain transport failure; never duplicate a turn on retry.
        signature = (state.revision, text, control, source_id, tuple(answers or []))
        if pending is None or pending[0] != signature:
            pending = (
                signature,
                LearningTurn(
                    request_id=uuid4(),
                    revision=state.revision,
                    text=text,
                    control=control,
                    source_id=source_id,
                    answers=answers or [],
                ),
            )
        busy = True
        ui.run_javascript("window.CultureBridgeVoice?.cancel()")
        for button in controls + quiz_controls:
            button.disable()
        status.set_text("자료와 다음 학습을 살펴보고 있어요…")
        try:
            state = await worker(send_learning_turn, state.id, pending[1])
            if control in {"message", "correct", "change_topic"}:
                prompt.set_value("")
            pending = None
            render()
            status.set_text("")
        except ConversationConflictError:
            state = await worker(get_conversation, state.id)
            pending = None
            render()
            status.set_text("대화가 바뀌었어요. 최신 내용을 불러왔으니 확인 후 다시 보내주세요.")
        except (ValueError, OperationBusyError) as exc:
            status.set_text(service_text(str(exc)))
        except Exception:
            status.set_text(
                "처리 결과를 확인하지 못했어요. 같은 내용으로 다시 보내면 중복을 확인해요."
            )
        finally:
            busy = False
            for button in controls + quiz_controls:
                button.enable()

    def render():
        nonlocal quiz_controls
        quiz_controls = []
        preferences = get_preferences()
        transcript.clear()
        with transcript:
            if state.goal:
                ui.label("지금 함께 살펴볼 목표: " + state.goal).classes("cb-title text-lg")
            if state.learning_plan:
                labels = {
                    "search": "자료 찾기",
                    "read": "근거 읽기",
                    "explain": "내용 익히기",
                    "compare": "유사점과 차이점",
                    "quiz": "학습 확인",
                    "review": "복습",
                }
                with ui.expansion("이번 학습 계획").classes("w-full"):
                    for index, action in enumerate(state.learning_plan, 1):
                        ui.label(f"{index}. {labels.get(action, action)}")
                    ui.label(
                        "찾은 자료와 내 설명에 따라 계획을 조절해요. 숙달 완료 표시는 아니에요."
                    )
            if state.notice:
                ui.label(display_notice(state.notice)).classes("cb-muted").props("role=status")
            if state.status == "paused":
                ui.label("잠시 멈춘 대화예요. ‘이어서 학습’을 누르면 다시 시작해요.")
            for message in state.messages:
                with ui.card().classes(
                    "cb-card cb-message w-full "
                    + ("cb-message-user" if message.role == "user" else "cb-message-assistant")
                ):
                    ui.label("나" if message.role == "user" else "컬처브릿지").classes(
                        "font-semibold"
                    )
                    ui.label(message_body(message, preferences)).classes("cb-message-body")
                    if message.kind == "dictionary" and message.citations:
                        ui.label("출처: 국립국어원 표준국어대사전 · 뜻풀이 원문 그대로")
                        ui.link(
                            "CC BY-SA 2.0 대한민국",
                            message.citations[0]["license_url"],
                            new_tab=True,
                        )
                    for citation in message.citations:
                        with ui.expansion("설명의 공식 근거 · 원문 보기"):
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
            if (
                state.active_quiz
                and not state.active_quiz.get("submitted")
                and state.status != "paused"
            ):
                with ui.card().classes("cb-card w-full gap-4"):
                    ui.label("배운 내용 확인하기").classes("cb-title text-xl")
                    radios = []
                    for number, item in enumerate(state.active_quiz["items"], 1):
                        ui.label(f"{number}. {item['question']}")
                        radios.append(
                            ui.radio({c["id"]: c["text"] for c in item["choices"]}).props(
                                f'aria-label="대화 퀴즈 {number}번 선택지"'
                            )
                        )

                    async def answer_quiz():
                        answers = [radio.value for radio in radios]
                        if any(answer is None for answer in answers):
                            ui.notify("모든 문항에 답해 주세요.", color="warning")
                            return
                        await submit("submit_quiz", answers=answers)

                    quiz_controls.append(
                        ui.button("답안 제출하고 이어서 학습", on_click=answer_quiz)
                    )
                    ui.label("답안은 직접 골라요. 제출 후 결과에 맞춰 다음 활동을 계획해요.")
            if state.tool_observations:
                with ui.expansion("자료를 찾고 학습을 이어간 과정").classes("w-full"):
                    status_names = {
                        "ok": "확인",
                        "empty": "결과 없음",
                        "error": "연결 확인 필요",
                        "blocked": "조건 확인 필요",
                        "insufficient": "근거 부족",
                        "duplicate": "중복 방지",
                        "waiting": "답변 기다림",
                        "budget": "이번 탐색 종료",
                    }
                    for entry in state.tool_observations[-12:]:
                        name = {
                            "search": "국내 유산 찾기",
                            "search_world": "해외 유산 찾기",
                            "search_history": "인물·사건 찾기",
                            "read": "공식 근거 읽기",
                            "define": "용어 찾기",
                            "discover": "비교 후보 찾기",
                            "compare": "근거 비교",
                            "quiz": "확인 퀴즈",
                            "review_quiz": "오답 근거 읽기",
                            "submit_quiz": "답안 채점",
                        }.get(entry["tool"], "학습 활동")
                        ui.label(name + " · " + status_names.get(entry["status"], "추가 확인"))
                        if entry.get("reason"):
                            ui.label(entry["reason"])
                        ui.label(
                            "AI가 선택한 실행"
                            if entry.get("planner") == "ai"
                            else "직접 제출한 답안"
                            if entry.get("planner") == "learner"
                            else "기본 처리"
                        )
            if state.search_results:
                with ui.expansion("찾은 공식 자료 살펴보기").classes("w-full"):
                    for result in state.search_results:
                        if result.get("metadata_only"):
                            ui.link(result["name"], result["reading_url"], new_tab=True)
                            ui.label(
                                "신편 한국사 검색 결과 · 공식 원문에서 읽기"
                                if result.get("catalogue") == "history"
                                else "세계유산 등재 목록 · 공식 사이트에서 읽기"
                            ).classes("cb-muted")
                        else:
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
            if state.concepts or state.task_contract:
                from culturebridge.services.learning_outcome_service import outcome_summary

                outcomes = outcome_summary(state)
                with ui.expansion("이번 학습에서 확인한 점"):
                    ui.label(outcomes["notice"])
                    if outcomes["comparison_goal_met"] is not None:
                        ui.label(
                            "선택한 비교 항목의 양쪽 근거를 확보했어요."
                            if outcomes["comparison_goal_met"]
                            else "선택한 비교 항목의 근거를 더 확인해야 해요."
                        )
                    for item in outcomes["explanation_observations"]:
                        if item["explanation_improved_observation"]:
                            ui.label(
                                item["concept"] + ": 이전 설명보다 근거와 맞는 답변이 관찰됐어요."
                            )
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
        if send_button is not None:
            send_button.set_text("이어서 학습" if state.status == "paused" else "보내기")
            send_button.props("icon=play_arrow" if state.status == "paused" else "icon=send")

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
    with ui.row().classes("cb-composer-actions flex-wrap"):
        send_button = ui.button(
            "이어서 학습" if state.status == "paused" else "보내기",
            icon="play_arrow" if state.status == "paused" else "send",
            on_click=lambda: submit("resume" if state.status == "paused" else "message"),
        ).props("unelevated")
        controls.append(send_button)
        ui.button("잠시 중단", on_click=stop).props("outline no-caps")
    with ui.expansion("학습 진행 방식 바꾸기", icon="tune").classes("cb-chat-options"):
        with ui.row().classes("flex-wrap gap-2"):
            for label, control in (
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


def message_body(message, preferences):
    """Avoid repeating the same quote in prose and its source panel; keep stored text intact."""
    text = present_message(message, preferences)
    if message.role == "assistant" and message.kind != "dictionary":
        for citation in message.citations:
            quote = citation.get("quote", "")
            if quote:
                text = text.replace("\n\n공식 원문: " + quote, "", 1)
    return text


def display_notice(text):
    return service_text(text)


def control_text(control, draft):
    """Progress controls must not accidentally transmit an unfinished draft."""
    return draft.strip() if control in {"message", "correct", "change_topic"} else ""
