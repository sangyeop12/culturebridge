import logging
import sqlite3

from nicegui import run, ui

from culturebridge.domain.models import LearningLevel
from culturebridge.services.catalog_service import (
    HeritageNotFoundError,
    get_sources,
    list_heritages,
    recommend_related,
)
from culturebridge.services.claim_service import verify_claim
from culturebridge.services.comparison_service import (
    ComparisonNotFoundError,
    create_saved_comparison,
    get_saved_comparison,
    list_saved_comparisons,
)
from culturebridge.services.question_service import answer_question
from culturebridge.services.quiz_service import (
    InvalidQuizAttemptError,
    QuizNotFoundError,
    generate_quiz,
    grade_quiz,
)

logger = logging.getLogger(__name__)

BRAND = "#173B63"
ACCENT = "#2F6FAF"
PALE = "#EAF3FB"
KIOSK_MODE = "kiosk"
KIOSK_TIMEOUT_SECONDS = 300
LEVEL_LABELS = {
    LearningLevel.BEGINNER.value: "초급",
    LearningLevel.INTERMEDIATE.value: "중급",
    LearningLevel.ADVANCED.value: "고급",
}


def _base_styles() -> None:
    ui.add_head_html(
        f"""
        <style>
            body {{ background: #f7f9fc; color: #17202a; }}
            .cb-shell {{ width: min(1120px, calc(100vw - 32px)); margin: 0 auto; }}
            .cb-card {{ background: white; border: 1px solid #d9e2ec; border-radius: 18px; }}
            .cb-title {{ color: {BRAND}; font-weight: 750; letter-spacing: -0.03em; }}
            .cb-muted {{ color: #526779; }}
            .cb-action {{ min-height: 52px; border-radius: 12px; font-weight: 700; }}
            .cb-choice {{ min-height: 62px; border: 1px solid #c7d8ea; border-radius: 12px; }}
            .cb-kiosk-action {{ min-height: 72px; border-radius: 16px; font-size: 1.15rem;
                font-weight: 750; padding: 0 28px; }}
            .cb-kiosk-card {{ min-height: 148px; border: 2px solid #c7d8ea;
                border-radius: 22px; }}
            :focus-visible {{ outline: 3px solid #b45309; outline-offset: 4px; }}
            .cb-shell a {{ display: inline-flex; align-items: center; min-height: 44px;
                overflow-wrap: anywhere; }}
            .cb-shell .q-radio {{ min-height: 52px; padding: 8px; }}
            .cb-kiosk .q-radio, .cb-kiosk .q-btn {{ min-height: 72px; }}
            .cb-kiosk .q-radio {{ font-size: 1.1rem; }}
            .cb-kiosk-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }}
            .cb-compare-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            @media (max-width: 720px) {{
                .cb-shell {{ width: min(100% - 20px, 1120px); }}
                .cb-compare-grid, .cb-kiosk-grid {{ grid-template-columns: minmax(0, 1fr); }}
            }}
        </style>
        <script>document.documentElement.lang = 'ko';</script>
        """
    )


def _header() -> None:
    with ui.header().style(f"background: {BRAND}").classes("items-center px-6 py-3"):
        ui.label("CultureBridge").classes("text-xl font-bold text-white")
        ui.space()
        ui.label("공식 자료로 비교하는 문화유산 학습").classes("text-sm text-blue-100")


def _kiosk_header() -> None:
    with ui.header().style(f"background: {BRAND}").classes("items-center px-8 py-4"):
        with ui.column().classes("gap-0"):
            ui.label("CultureBridge").classes("text-2xl font-bold text-white")
            ui.label("박물관 터치 체험").classes("text-sm text-blue-100")
        ui.space()
        ui.button("처음으로", on_click=lambda: ui.navigate.to("/kiosk")).props(
            "unelevated icon=home"
        ).classes("cb-kiosk-action").style("background: white; color: #173B63")


def _enable_kiosk_timeout() -> None:
    ui.add_body_html(
        f"""
        <script>
            (() => {{
                const timeoutMs = {KIOSK_TIMEOUT_SECONDS * 1000};
                const restartTimer = () => {{
                    window.clearTimeout(window.cultureBridgeKioskTimer);
                    window.cultureBridgeKioskTimer = window.setTimeout(
                        () => window.location.replace('/kiosk?reset=timeout'),
                        timeoutMs,
                    );
                }};
                ['pointerdown', 'keydown', 'touchstart'].forEach(
                    eventName => window.addEventListener(
                        eventName,
                        restartTimer,
                        {{passive: true}},
                    ),
                );
                restartTimer();
            }})();
        </script>
        """
    )


def _is_kiosk(mode: str) -> bool:
    return mode == KIOSK_MODE


def _page_header(mode: str) -> None:
    if _is_kiosk(mode):
        ui.add_head_html("<style>body { font-size: 18px; }</style>")
        _kiosk_header()
        _enable_kiosk_timeout()
    else:
        _header()


def _action_classes(mode: str) -> str:
    return "cb-kiosk-action" if _is_kiosk(mode) else "cb-action"


def _route(path: str, mode: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}mode={KIOSK_MODE}" if _is_kiosk(mode) else path


def _home_route(mode: str) -> str:
    return "/kiosk" if _is_kiosk(mode) else "/"


def _error_page(message: str, mode: str) -> None:
    with ui.column().classes("cb-shell gap-4 py-10"):
        ui.label(message).props("role=alert").classes("cb-title text-2xl")
        ui.label("처음 화면에서 다시 선택해 주세요. 문제가 계속되면 잠시 후 다시 시도하세요.")
        ui.button("처음으로", on_click=lambda: ui.navigate.to(_home_route(mode))).classes(
            _action_classes(mode)
        )


def _learning_level(value: str) -> LearningLevel:
    try:
        return LearningLevel(value)
    except ValueError:
        ui.label("학습 수준을 확인할 수 없어 초급으로 안내합니다.").props("role=status")
        return LearningLevel.BEGINNER


@ui.page("/")
def home_page() -> None:
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-7 py-10"):
        ui.link("저장된 비교 보기", "/comparisons").classes("text-blue-800 font-semibold")
        with ui.column().classes("gap-2"):
            ui.label("문화유산에서 시작하는 비교 탐구").classes("cb-title text-4xl")
            ui.label("한국·중국·일본의 불교 문화유산을 공식 출처와 함께 비교해 보세요.").classes(
                "cb-muted text-lg"
            )

        with ui.card().classes("cb-card w-full p-6 gap-5"):
            ui.label("1. 학습 수준을 선택하세요").classes("cb-title text-xl")
            level = ui.toggle(
                LEVEL_LABELS,
                value=LearningLevel.BEGINNER.value,
            ).classes("w-full")

            ui.label("2. 문화유산을 검색하세요").classes("cb-title text-xl")
            search = (
                ui.input(label="문화유산 검색", placeholder="예: 석굴암, 대한민국, 8세기")
                .props("outlined clearable maxlength=100")
                .classes("w-full")
            )
            results = ui.column().classes("w-full gap-3")

            def render_results() -> None:
                results.clear()
                with results:
                    items = list_heritages(search.value)
                    if not items:
                        ui.label("검색 결과가 없습니다. 다른 검색어를 입력해 보세요.").classes(
                            "cb-muted p-4"
                        )
                        return
                    for item in items:
                        with ui.row().classes(
                            "cb-choice w-full items-center justify-between px-5 py-3"
                        ):
                            with ui.column().classes("gap-0"):
                                ui.label(item.name).classes("font-bold text-lg")
                                ui.label(
                                    f"{item.country} · {item.period} · {item.location}"
                                ).classes("cb-muted text-sm")
                            ui.button(
                                "비교 후보 보기",
                                on_click=lambda heritage_id=item.id: ui.navigate.to(
                                    f"/explore/{heritage_id}?level={level.value}"
                                ),
                            ).props("unelevated").style(f"background: {ACCENT}").classes(
                                "cb-action"
                            )

            search.on("update:model-value", lambda _: render_results())
            render_results()


@ui.page("/kiosk")
def kiosk_page(reset: str | None = None) -> None:
    _base_styles()
    _kiosk_header()
    _enable_kiosk_timeout()
    with ui.column().classes("cb-shell cb-kiosk gap-8 py-10"):
        if reset == "timeout":
            ui.label("이전 체험을 안전하게 종료하고 처음 화면으로 돌아왔습니다.").classes(
                "w-full rounded-xl bg-blue-50 p-4 text-center text-lg font-semibold text-blue-900"
            )

        with ui.column().classes("w-full items-center gap-3 text-center"):
            ui.label("문화유산 비교 체험").classes("cb-title text-5xl")
            ui.label("학습 수준을 누른 뒤 문화유산을 선택하세요.").classes("cb-muted text-2xl")

        with ui.card().classes("cb-card w-full p-8 gap-6"):
            ui.label("1. 학습 수준").classes("cb-title text-3xl")
            level = (
                ui.toggle(
                    LEVEL_LABELS,
                    value=LearningLevel.BEGINNER.value,
                )
                .props("spread unelevated")
                .classes("w-full cb-kiosk-action")
            )

            ui.label("2. 문화유산 선택").classes("cb-title text-3xl mt-2")
            with ui.element("div").classes("cb-kiosk-grid w-full gap-5"):
                for item in list_heritages():
                    with ui.card().classes("cb-kiosk-card w-full justify-between p-6 gap-3"):
                        ui.label(item.name).classes("cb-title text-2xl")
                        ui.label(f"{item.country} · {item.period}").classes("cb-muted text-lg")
                        ui.button(
                            f"{item.name} 선택",
                            on_click=lambda heritage_id=item.id: ui.navigate.to(
                                f"/explore/{heritage_id}?level={level.value}&mode={KIOSK_MODE}"
                            ),
                        ).classes("cb-kiosk-action w-full").props("unelevated")

        ui.label("5분 동안 조작하지 않으면 개인정보 보호를 위해 자동으로 초기화됩니다.").classes(
            "cb-muted w-full text-center text-base"
        )


@ui.page("/explore/{heritage_id}")
def explore_page(
    heritage_id: str,
    level: str = LearningLevel.BEGINNER.value,
    mode: str = "web",
) -> None:
    _base_styles()
    _page_header(mode)
    level = _learning_level(level).value
    selected = next((item for item in list_heritages() if item.id == heritage_id), None)
    with ui.column().classes("cb-shell gap-6 py-10"):
        if selected is None:
            ui.label("문화유산을 찾을 수 없습니다.").classes("cb-title text-2xl")
            ui.button("처음으로", on_click=lambda: ui.navigate.to(_home_route(mode))).classes(
                _action_classes(mode)
            )
            return

        ui.label("비교 대상 추천").classes("cb-title text-3xl")
        ui.label(f"선택한 문화유산: {selected.name}").classes("text-lg font-semibold")
        ui.label(f"학습 수준: {LEVEL_LABELS.get(level, '초급')}").classes("cb-muted")

        for candidate in recommend_related(heritage_id):
            with ui.card().classes("cb-card w-full p-6 gap-3"):
                ui.label(candidate.heritage.name).classes("cb-title text-2xl")
                ui.label(f"{candidate.heritage.country} · {candidate.heritage.period}").classes(
                    "cb-muted"
                )
                ui.label(candidate.reason).classes("text-base")
                ui.button(
                    "비교 시작",
                    on_click=lambda right_id=candidate.heritage.id: ui.navigate.to(
                        _route(f"/compare/{heritage_id}/{right_id}?level={level}", mode)
                    ),
                ).props("unelevated").style(f"background: {ACCENT}").classes(_action_classes(mode))

        ui.button(
            "다른 문화유산 선택",
            on_click=lambda: ui.navigate.to(_home_route(mode)),
        ).classes(_action_classes(mode))


@ui.page("/compare/{left_id}/{right_id}")
def comparison_page(
    left_id: str,
    right_id: str,
    level: str = LearningLevel.BEGINNER.value,
    mode: str = "web",
    saved_id: str | None = None,
) -> None:
    _base_styles()
    _page_header(mode)
    learning_level = _learning_level(level)
    if left_id == right_id:
        _error_page("서로 다른 문화유산을 선택해 주세요.", mode)
        return
    try:
        if saved_id:
            saved = get_saved_comparison(saved_id)
            result = saved.comparison
            if result.left.id != left_id or result.right.id != right_id:
                raise ComparisonNotFoundError(saved_id)
            learning_level = result.level
            sources = saved.sources
        else:
            result = create_saved_comparison(left_id, right_id, learning_level)
            sources = get_sources(result.source_ids)
    except (ComparisonNotFoundError, HeritageNotFoundError):
        _error_page("비교 결과를 찾을 수 없습니다.", mode)
        return
    except sqlite3.Error:
        logger.exception("Comparison storage failed")
        _error_page("비교 결과를 저장하거나 불러올 수 없습니다.", mode)
        return

    with ui.column().classes(f"cb-shell gap-7 py-10 {'cb-kiosk' if _is_kiosk(mode) else ''}"):
        with ui.column().classes("gap-1"):
            ui.label("문화유산 비교").classes("cb-title text-3xl")
            ui.label(f"{result.left.name} ↔ {result.right.name}").classes("text-xl font-semibold")
            ui.label(f"학습 수준: {LEVEL_LABELS[learning_level.value]}").classes("cb-muted")
            if result.learning_goal:
                ui.label(f"학습 목표: {result.learning_goal}").classes("text-lg font-semibold")
            if saved_id:
                ui.label(
                    "저장 당시의 비교와 출처입니다. 아래 자유 질문·주장 검증·퀴즈는 "
                    "현재 등록된 학습 자료를 사용합니다."
                ).classes("cb-muted")
            if result.saved_id and not _is_kiosk(mode):
                ui.link(
                    "저장된 이 비교 다시 열기",
                    f"/compare/{left_id}/{right_id}?saved_id={result.saved_id}",
                ).classes("text-blue-800")
                ui.link("저장된 비교 목록", "/comparisons").classes("text-blue-800")

        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("공통점").classes("cb-title text-2xl")
            for point in result.common_points:
                ui.label(f"• {point}").classes("text-base")

        ui.label("항목별 차이").classes("cb-title text-2xl")
        for point in result.differences:
            with ui.card().classes("cb-card w-full p-6 gap-3"):
                ui.label(point.category).classes("cb-title text-xl")
                with ui.element("div").classes("cb-compare-grid w-full gap-4"):
                    with ui.column().classes("gap-1 rounded-lg p-4").style(f"background: {PALE}"):
                        ui.label(result.left.name).classes("font-bold")
                        ui.label(point.left)
                    with ui.column().classes("gap-1 rounded-lg p-4").style(f"background: {PALE}"):
                        ui.label(result.right.name).classes("font-bold")
                        ui.label(point.right)
                ui.label(point.explanation).classes("cb-muted")

        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("검증 상태와 출처").classes("cb-title text-2xl")
            status_label = (
                "확인됨" if result.verification_status.value == "verified" else "추가 확인 필요"
            )
            ui.label(status_label).classes("font-bold")
            ui.label(result.verification_note).classes("cb-muted")
            for source in sources:
                ui.link(
                    f"{source.organization} · {source.title}",
                    str(source.url),
                    new_tab=True,
                ).classes("text-blue-700")
                if source.summary:
                    ui.label(source.summary).classes("text-sm")
                if source.scope_note:
                    ui.label(source.scope_note).classes("cb-muted text-sm")

        with ui.card().classes("cb-card w-full p-6 gap-4"):
            ui.label("Agent에게 자유 질문").classes("cb-title text-2xl")
            ui.label(
                "시대·구조·재료·종교적 배경을 질문하면 근거 범위와 검증 상태를 함께 표시합니다."
            ).classes("cb-muted")
            question_input = (
                ui.textarea(
                    label="문화유산 질문", placeholder="예: 두 문화유산의 재료는 어떻게 다른가요?"
                )
                .props("outlined autogrow maxlength=500")
                .classes("w-full")
            )
            answer_box = ui.column().props("role=status aria-live=polite").classes("w-full gap-3")

            async def submit_question() -> None:
                question = (question_input.value or "").strip()
                if not 2 <= len(question) <= 500:
                    ui.notify("질문을 2~500글자로 입력해 주세요.", color="warning")
                    return
                ask_button.disable()
                try:
                    answer = await run.io_bound(
                        answer_question,
                        left_id,
                        right_id,
                        question,
                        learning_level,
                    )
                except Exception:
                    logger.exception("Question answering failed")
                    ui.notify(
                        "답변을 불러오지 못했습니다. 잠시 후 다시 질문해 주세요.", color="negative"
                    )
                    return
                finally:
                    ask_button.enable()
                status_labels = {
                    "verified": ("확인됨", "text-green-700"),
                    "needs_review": ("추가 확인 필요", "text-orange-700"),
                    "insufficient_evidence": ("근거 부족", "text-red-700"),
                }
                status_text, status_class = status_labels[answer.verification_status.value]
                answer_box.clear()
                with answer_box:
                    with (
                        ui.column()
                        .classes("w-full gap-2 rounded-lg p-5")
                        .style(f"background: {PALE}")
                    ):
                        ui.label(status_text).classes(f"font-bold {status_class}")
                        ui.label(answer.answer).classes("text-base")
                        ui.label(answer.verification_note).classes("cb-muted text-sm")

            ask_button = (
                ui.button("질문하기", on_click=submit_question)
                .props("unelevated")
                .style(f"background: {ACCENT}")
                .classes(_action_classes(mode))
            )

        with ui.card().classes("cb-card w-full p-6 gap-4"):
            ui.label("역사적 주장 검증").classes("cb-title text-2xl")
            ui.label("한 가지 사실을 입력하세요. 예: 석굴암의 재료는 화강암이다").classes(
                "cb-muted"
            )
            claim_input = (
                ui.textarea(
                    label="검증할 주장", placeholder="문화유산의 재료·시대·구조에 관한 주장"
                )
                .props("outlined autogrow maxlength=500")
                .classes("w-full")
            )
            claim_box = ui.column().props("role=status aria-live=polite").classes("w-full gap-3")

            def submit_claim() -> None:
                claim = (claim_input.value or "").strip()
                if not 2 <= len(claim) <= 500:
                    ui.notify("주장을 2~500글자로 입력해 주세요.", color="warning")
                    return
                checked = verify_claim(left_id, right_id, claim)
                labels = {
                    "verified": "확인됨",
                    "needs_review": "추가 확인 필요",
                    "insufficient_evidence": "근거 부족",
                }
                claim_box.clear()
                with claim_box:
                    ui.label(labels[checked.verification_status.value]).classes("cb-title text-xl")
                    ui.label(checked.explanation)
                    for entry in checked.evidence:
                        ui.label(entry.fact).classes("font-semibold")
                    for source in checked.sources:
                        ui.link(
                            f"{source.organization} · {source.title}",
                            str(source.url),
                            new_tab=True,
                        )
                    ui.label(checked.scope_note).classes("cb-muted text-sm")

            ui.button("주장 검증하기", on_click=submit_claim).props("unelevated").style(
                f"background: {ACCENT}"
            ).classes(_action_classes(mode))

        with ui.row().classes("gap-3"):
            ui.button(
                "학습 확인 퀴즈",
                on_click=lambda: ui.navigate.to(
                    _route(
                        f"/quiz/{left_id}/{right_id}?level={learning_level.value}",
                        mode,
                    )
                ),
            ).props("unelevated").style(f"background: {ACCENT}").classes(_action_classes(mode))
            ui.button(
                "비교 후보로 돌아가기",
                on_click=lambda: ui.navigate.to(
                    _route(f"/explore/{left_id}?level={learning_level.value}", mode)
                ),
            ).classes(_action_classes(mode))
            ui.button(
                "처음으로",
                on_click=lambda: ui.navigate.to(_home_route(mode)),
            ).classes(_action_classes(mode))


@ui.page("/quiz/{left_id}/{right_id}")
def quiz_page(
    left_id: str,
    right_id: str,
    level: str = LearningLevel.BEGINNER.value,
    mode: str = "web",
) -> None:
    _base_styles()
    _page_header(mode)
    learning_level = _learning_level(level)
    if left_id == right_id:
        _error_page("서로 다른 문화유산을 선택해 주세요.", mode)
        return
    try:
        quiz = generate_quiz(left_id, right_id, learning_level)
    except HeritageNotFoundError:
        _error_page("퀴즈에 사용할 문화유산을 찾을 수 없습니다.", mode)
        return
    except sqlite3.Error:
        logger.exception("Quiz storage failed")
        _error_page("퀴즈를 준비할 수 없습니다.", mode)
        return
    radios = []

    with ui.column().classes(f"cb-shell gap-6 py-10 {'cb-kiosk' if _is_kiosk(mode) else ''}"):
        with ui.column().classes("gap-1"):
            ui.label("학습 확인 퀴즈").classes("cb-title text-3xl")
            ui.label(f"{LEVEL_LABELS[quiz.level.value]} · {quiz.learning_goal}").classes(
                "text-lg font-semibold"
            )
            ui.label("5개 문항에 모두 답한 뒤 채점하세요.").classes("cb-muted text-lg")

        for number, item in enumerate(quiz.items, start=1):
            with ui.card().classes("cb-card w-full p-6 gap-4"):
                ui.label(f"문제 {number} / 5").classes("cb-muted font-semibold")
                ui.label(item.question).classes("cb-title text-xl")
                options = {choice.id: choice.text for choice in item.choices}
                radios.append(
                    ui.radio(options)
                    .props(f'inline=false aria-label="문제 {number}: {item.question}"')
                    .classes("w-full")
                )

        result_box = ui.column().props("role=status aria-live=polite").classes("w-full gap-3")

        def submit_answers() -> None:
            answers = [radio.value for radio in radios]
            if any(answer is None for answer in answers):
                ui.notify("모든 문항에 답해 주세요.", color="warning")
                return
            try:
                result = grade_quiz(quiz.quiz_id, [int(answer) for answer in answers])
            except (QuizNotFoundError, InvalidQuizAttemptError):
                ui.notify("퀴즈를 확인할 수 없습니다. 새로 시작해 주세요.", color="warning")
                return
            except sqlite3.Error:
                logger.exception("Quiz grading storage failed")
                ui.notify("채점 결과를 저장하지 못했습니다. 다시 시도해 주세요.", color="negative")
                return
            result_box.clear()
            with result_box:
                with ui.card().classes("cb-card w-full p-6 gap-3"):
                    ui.label(f"채점 결과 {result.score} / {result.total}").classes(
                        "cb-title text-2xl"
                    )
                    for explanation in result.explanations:
                        ui.label(explanation).classes("text-base")
            submit_button.disable()

        submit_button = (
            ui.button("채점하고 해설 보기", on_click=submit_answers)
            .props("unelevated")
            .style(f"background: {ACCENT}")
            .classes(_action_classes(mode))
        )
        with ui.row().classes("gap-3"):
            ui.button(
                "비교 화면으로 돌아가기",
                on_click=lambda: ui.navigate.to(
                    _route(
                        f"/compare/{left_id}/{right_id}?level={learning_level.value}",
                        mode,
                    )
                ),
            ).classes(_action_classes(mode))
            ui.button(
                "처음으로",
                on_click=lambda: ui.navigate.to(_home_route(mode)),
            ).classes(_action_classes(mode))


@ui.page("/comparisons")
def comparison_history_page(page: int = 1) -> None:
    _base_styles()
    _header()
    page = max(1, page)
    page = min(page, 1000000)
    try:
        records = list_saved_comparisons(limit=21, offset=(page - 1) * 20)
    except sqlite3.Error:
        logger.exception("Comparison history storage failed")
        _error_page("저장된 비교 목록을 불러올 수 없습니다.", "web")
        return
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("저장된 비교").classes("cb-title text-3xl")
        ui.label("이 기기에서 생성한 비교를 저장 당시 내용과 출처로 다시 볼 수 있습니다.").classes(
            "cb-muted"
        )
        if not records:
            ui.label("아직 저장된 비교가 없습니다. 문화유산을 선택해 비교를 시작하세요.")
        for record in records[:20]:
            saved = get_saved_comparison(record.id)
            with ui.card().classes("cb-card w-full p-5 gap-2"):
                ui.label(f"{record.left_name} ↔ {record.right_name}").classes("cb-title text-xl")
                ui.label(
                    f"{LEVEL_LABELS[record.level.value]} · "
                    f"{record.created_at.astimezone().strftime('%Y-%m-%d %H:%M')}"
                ).classes("cb-muted")
                ui.link(
                    "비교 다시 열기",
                    f"/compare/{saved.comparison.left.id}/{saved.comparison.right.id}"
                    f"?saved_id={record.id}",
                ).classes("text-blue-800 font-semibold")
        with ui.row().classes("gap-4"):
            if page > 1:
                ui.link("이전 페이지", f"/comparisons?page={page - 1}")
            if len(records) > 20:
                ui.link("다음 페이지", f"/comparisons?page={page + 1}")
            ui.link("새 비교 시작", "/")


def register_pages() -> None:
    """Importing this module registers pages; this function documents that intent."""
