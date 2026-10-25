import logging
import re
import sqlite3
from contextvars import copy_context
from functools import partial
from urllib.parse import parse_qs, urlencode, urlsplit

from nicegui import run, ui

from culturebridge.agents.autonomous import AutonomousRequest, run_autonomous
from culturebridge.agents.quiz_agent import evaluate_learning_quiz
from culturebridge.agents.workflow import run_exploration
from culturebridge.config import get_settings
from culturebridge.domain.models import (
    CollectedSource,
    ComparisonScope,
    ExtractedField,
    LearningAmount,
    LearningGoal,
    LearningLevel,
)
from culturebridge.services.catalog_service import (
    HeritageNotFoundError,
    get_heritage,
    get_sources,
    list_heritages,
    recommend_related,
)
from culturebridge.services.claim_service import verify_claim
from culturebridge.services.comparison_scope_service import (
    SCOPE_LABELS,
    candidate_in_scope,
    validate_pair_scope,
)
from culturebridge.services.comparison_service import (
    LEARNING_VERSION,
    ComparisonNotFoundError,
    create_saved_comparison,
    get_saved_comparison,
    list_saved_comparisons,
)
from culturebridge.services.curriculum_service import AMOUNT_LABELS, GOAL_LABELS, plan_learning
from culturebridge.services.display_service import (
    display_country,
    display_name,
    korean_name,
    learner_status,
    learning_title,
    readable_reason,
    readable_trace,
)
from culturebridge.services.dynamic_heritage_service import OfficialTarget
from culturebridge.services.evidence_quiz_service import EvidenceQuizError
from culturebridge.services.home_search_service import get_home_suggestions, search_home
from culturebridge.services.learner_presentation_service import (
    learning_day,
    lesson_activity,
    owns_comparison,
    save_learning_note,
)
from culturebridge.services.learning_history_service import list_learning_reviews
from culturebridge.services.lesson_service import beginner_text, explain_source, official_source
from culturebridge.services.location_service import get_official_location
from culturebridge.services.navigation_service import (
    home_context,
    scope_return,
    search_level,
    search_return,
    with_return,
)
from culturebridge.services.official_service import (
    SEOKGURAM_CODES,
    OfficialDocumentNotFoundError,
    OfficialServiceError,
    get_official_document,
    search_official_heritages,
)
from culturebridge.services.operation_service import OperationBusyError, session_owner
from culturebridge.services.question_service import answer_question
from culturebridge.services.quiz_service import (
    InvalidQuizAttemptError,
    QuizNotFoundError,
    generate_quiz,
    load_quiz,
)
from culturebridge.services.relearning_service import relearn_saved_comparison
from culturebridge.services.source_claim_service import ClaimTargetMismatchError
from culturebridge.services.source_permission_service import policy_url
from culturebridge.services.subject_service import is_group
from culturebridge.services.unesco_service import (
    UNESCO_TERMS_URL,
    get_unesco_suggestions,
    normalize_search,
    search_unesco,
)
from culturebridge.ui.copy import service_text
from culturebridge.ui.learning_chat import learning_chat, learning_entry
from culturebridge.ui.learning_controls import tone_controls
from culturebridge.ui.learning_intent import learning_intent_editor
from culturebridge.ui.learning_steps import learning_steps
from culturebridge.ui.theme import ACCENT, BRAND, PALE, THEME_HEAD

logger = logging.getLogger(__name__)


def _conversation_review_button(history_id):
    from culturebridge.services.conversation_review_service import ReviewNotFoundError
    from culturebridge.services.learning_conversation_service import create_conversation

    async def start_review():
        button.disable()
        try:
            state = await _io_bound(create_conversation, review_history_id=history_id)
            ui.navigate.to(f"/learn?conversation_id={state.id}")
        except (ReviewNotFoundError, ValueError, OperationBusyError):
            ui.notify(
                "복습 대화를 열지 못했어요. 이 브라우저의 채점 기록을 확인해 주세요.",
                color="warning",
            )
        except sqlite3.Error:
            ui.notify("복습 기록을 저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.", color="warning")
        finally:
            button.enable()

    button = ui.button("대화로 다시 익히기", icon="forum", on_click=start_review).props("outline")


def _review_cards(items):
    for item in items:
        ui.label(f"{item['number']}번 · {item['question']}").classes("font-semibold")
        ui.label("내 답: " + item["selected"]).classes("cb-muted")
        ui.label("정답: " + item["correct_answer"])
        ui.label("다시 해보기 · " + item["activity"])
        if item.get("quote"):
            with ui.expansion("이 문항의 원문 근거"):
                ui.label(item["quote"])
                if item.get("source_url"):
                    ui.link("공식 출처 보기", item["source_url"], new_tab=True)


async def _io_bound(callback, *args, **kwargs):
    # NiceGUI's executor doesn't propagate ContextVars; keep anonymous ownership in workers.
    try:
        owner = getattr(ui.context.client.request.state, "cb_owner", None)
    except (RuntimeError, AttributeError):
        owner = None
    context = copy_context()
    if owner:
        context.run(session_owner.set, owner)
    return await run.io_bound(context.run, partial(callback, *args, **kwargs))


def _report_links(record_id, history_id=None):
    if not owns_comparison(record_id):
        ui.label(
            "이 기록은 함께 열람할 수 있어요. 파일 저장은 기록을 만든 브라우저에서 이용해 주세요."
        ).classes("cb-muted text-sm")
        return
    suffix = f"&history_id={history_id}" if history_id else ""
    with ui.row().classes("gap-4"):
        ui.link(
            "인쇄·PDF 저장",
            f"/api/comparisons/{record_id}/export?format=html" + suffix,
            new_tab=True,
        )
    with ui.expansion("다른 형식으로 저장하기").classes("w-full"):
        ui.link("편집용 학습지", f"/api/comparisons/{record_id}/export?format=md" + suffix)
        ui.link("학습 데이터", f"/api/comparisons/{record_id}/export?format=json" + suffix)
        ui.label(
            "내 학습 결과만 저장해요. 원문 전체와 퀴즈 문항·정답은 파일에 포함하지 않아요."
        ).classes("cb-muted text-sm")


def _learning_journal(identity):
    if not identity or not owns_comparison(identity):
        return
    activity = lesson_activity(identity)
    with ui.card().classes("cb-card w-full p-6 gap-3"):
        ui.label(activity["title"]).classes("cb-title text-2xl").props(
            "role=heading aria-level=2"
        ).props("role=heading aria-level=2")
        for step in activity["activities"]:
            ui.label("• " + step)
        ui.label("생각해 보기 · " + activity["reflection"])
        note = (
            ui.textarea(
                "내가 정리한 배움",
                value=activity["note"],
                placeholder="같은 점, 다른 점, 더 확인할 점을 내 말로 적어 보세요.",
            )
            .props("outlined maxlength=3000")
            .classes("w-full")
        )

        async def save():
            try:
                await _io_bound(save_learning_note, identity, note.value or "")
                ui.notify("정리한 내용을 저장했어요. 학습지에도 함께 담겨요.")
            except (ValueError, sqlite3.Error):
                ui.notify(
                    "정리한 내용을 저장하지 못했어요. 입력 내용을 복사한 뒤 다시 시도해 주세요.",
                    type="warning",
                )

        ui.button("내 정리 저장", on_click=save).props("outline")


KIOSK_MODE = "kiosk"
KIOSK_TIMEOUT_SECONDS = 300
LEVEL_LABELS = {
    LearningLevel.BEGINNER.value: "초급",
    LearningLevel.INTERMEDIATE.value: "중급",
    LearningLevel.ADVANCED.value: "고급",
}


def _base_styles() -> None:
    from culturebridge.api.pwa_router import PWA_HEAD

    ui.colors(primary=ACCENT, secondary="#977444", accent="#977444")
    ui.add_head_html(THEME_HEAD)
    ui.add_head_html(PWA_HEAD)


def _header() -> None:
    from culturebridge.ui.navigation import (
        primary_navigation,
        secondary_navigation,
        site_footer,
    )

    path = ui.context.client.request.url.path if ui.context.client.request else "/"
    with ui.header().classes("cb-header p-0"):
        ui.button(
            "본문 바로가기",
            on_click=lambda: ui.run_javascript(
                'const main=document.querySelector(".cb-shell");'
                'if(main){main.setAttribute("tabindex","-1");main.focus();main.scrollIntoView();}'
            ),
        ).classes("cb-skip-link")
        with ui.row().classes("cb-header-inner"):
            with (
                ui.link(target="/").classes("cb-brand").props('aria-label="CultureBridge 처음으로"')
            ):
                ui.icon("account_balance", size="22px").classes("cb-brand-mark").props(
                    "aria-hidden=true"
                )
                ui.label("CultureBridge")
            ui.space()
            primary_navigation(path)
            with (
                ui.link(target="/settings")
                .classes("cb-settings-link")
                .props(
                    'aria-label="설정"' + (' aria-current="page"' if path == "/settings" else "")
                )
            ):
                ui.icon("settings", size="22px").props("aria-hidden=true")
                ui.tooltip("설정")
    secondary_navigation(path)
    footer = site_footer()
    # The shared header is built before the page body. Move the footer after the
    # body on connection so visual, keyboard and screen-reader order agree.
    ui.context.client.on_connect(lambda: footer.move(target_index=-1))


def _kiosk_header() -> None:
    with (
        ui.header().style(f"background: {BRAND}").classes("cb-kiosk-header items-center px-8 py-4")
    ):
        with ui.column().classes("gap-0"):
            ui.label("CultureBridge").classes("text-2xl font-bold text-white")
            ui.label("박물관 터치 체험").classes("text-sm text-blue-100")
        ui.space()
        ui.button("처음으로", on_click=lambda: ui.navigate.to("/kiosk?reset=manual")).props(
            "unelevated icon=home"
        ).classes("cb-kiosk-action").style(f"background: white; color: {BRAND}")


def _enable_kiosk_timeout() -> None:
    ui.add_body_html(
        f"""
        <script>
            (() => {{
                window.addEventListener('pageshow', event => {{
                    if (event.persisted) window.location.reload();
                }});
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
    return "/kiosk?reset=manual" if _is_kiosk(mode) else "/"


def _return_button(return_to="", fallback="/", label="검색 결과로", mode="web"):
    destination = search_return(return_to, fallback)
    if _is_kiosk(mode):
        allowed = (
            "/kiosk",
            "/explore/",
            "/compare/",
            "/research/",
            "/quiz/",
            "/discover/",
            "/official/",
        )
        destination = (
            _route(destination, mode)
            if urlsplit(destination).path.startswith(allowed)
            else _home_route(mode)
        )
    root = urlsplit(destination).path
    if root == "/comparisons":
        label = "비교 기록으로"
    elif root == "/courses" or root.startswith("/courses/"):
        label = "학습 코스로"
    elif root == "/learning-history":
        label = "학습 기록으로"
    elif root in {"/", "/domestic"} and not parse_qs(urlsplit(destination).query).get("q"):
        label = "문화유산 선택으로"
    elif root == "/kiosk":
        label = "문화유산 선택으로"
    elif return_to and search_return(return_to, ""):
        label = "검색 결과로"
    ui.button("← " + label, on_click=lambda: ui.navigate.to(destination)).props(
        "outline no-caps"
    ).classes(_action_classes(mode))


def _restore_results(callback):
    client = ui.context.client

    async def restore():
        await client.connected()
        if not client.is_deleted:
            await callback()

    ui.timer(0.1, restore, once=True)


def _settings_from_return(return_to):
    query = parse_qs(urlsplit(search_return(return_to, "/")).query)
    return (
        query.get("goal", ["compare"])[0],
        query.get("goal_text", [""])[0][:200],
        query.get("amount", ["standard"])[0],
    )


def _goal_query(goal, goal_text="", amount="standard", comparison_scope=ComparisonScope.OVERSEAS):
    return urlencode(
        {
            "goal": goal,
            "goal_text": (goal_text or "")[:200],
            "amount": amount,
            "comparison_scope": comparison_scope,
        }
    )


def _comparison_entry(
    q="",
    level="beginner",
    comparison_scope=ComparisonScope.OVERSEAS,
    context=None,
    domestic_url=None,
):
    if comparison_scope is ComparisonScope.OVERSEAS:
        with ui.expansion("국내 문화유산과 비교").classes("w-full"):
            ui.label(
                "한국 문화유산끼리 비교하거나 해외 유산을 한국"
                " 유산과 비교하고 싶을 때 이용해 주세요."
            )
            ui.button(
                "국내 문화유산과 비교",
                on_click=lambda: ui.navigate.to(
                    domestic_url
                    or scope_return(
                        context() if context else home_context(q=q, level=level),
                        ComparisonScope.DOMESTIC,
                    )
                ),
            ).props("outline no-caps")
    else:
        ui.button(
            "해외 문화유산과 비교",
            on_click=lambda: ui.navigate.to(
                scope_return(
                    context() if context else home_context(q=q, level=level),
                    ComparisonScope.OVERSEAS,
                )
            ),
        ).props("flat no-caps")


def _amount(value):
    try:
        return LearningAmount(value)
    except ValueError:
        return LearningAmount.STANDARD


def _goal(value: str) -> LearningGoal:
    try:
        return LearningGoal(value)
    except ValueError:
        return LearningGoal.COMPARE


def _error_page(message: str, mode: str) -> None:
    with ui.column().classes("cb-shell gap-4 py-10"):
        ui.label(message).props("role=alert").classes("cb-title text-2xl").props(
            "role=heading aria-level=2"
        )
        ui.label("처음 화면에서 다시 선택해 주세요. 문제가 계속되면 잠시 후 다시 시도해 주세요.")
        ui.button("처음으로", on_click=lambda: ui.navigate.to(_home_route(mode))).classes(
            _action_classes(mode)
        )


def _learning_level(value: str) -> LearningLevel:
    try:
        return LearningLevel(value)
    except ValueError:
        ui.label("학습 수준을 확인할 수 없어 초급으로 안내합니다.").props("role=status")
        return LearningLevel.BEGINNER


def _extracted_field_cards(fields: list[ExtractedField], level=LearningLevel.BEGINNER) -> None:
    names = {item.id: item.name for item in list_heritages()}
    for field in fields:
        if field.heritage_id not in names:
            try:
                names[field.heritage_id] = get_heritage(field.heritage_id).name
            except HeritageNotFoundError:
                pass
    for field in fields:
        with ui.card().classes("cb-card w-full p-5 gap-2"):
            ui.label(
                display_name(field.heritage_id, names.get(field.heritage_id, field.heritage_id))
                + f" · {field.category}"
            ).classes("cb-title text-xl")
            ui.label("추가 확인 필요" if field.value else "근거 부족").classes("font-semibold")
            ui.label(
                beginner_text(field.category, field.evidence_quote)
                if field.value and level is LearningLevel.BEGINNER
                else field.value or "공식 설명에서 이 특징을 찾지 못했어요."
            )
            ui.label(field.note).classes("cb-muted")
            if field.date_event:
                ui.label("연대가 가리키는 사건: " + field.date_event).classes("cb-muted")
            if field.evidence_quote:
                with ui.expansion("공식 원문 근거 보기").classes("w-full"):
                    ui.label(field.evidence_quote).style("white-space: pre-wrap")
            if field.source_url:
                ui.link("근거 출처", str(field.source_url), new_tab=True)


def _lesson_content(source, level):
    lesson = explain_source(source, level)
    if level is not LearningLevel.ADVANCED and not re.search(r"[가-힣]", source.content):

        async def request_korean():
            from culturebridge.services.korean_lesson_service import korean_lesson

            translate_button.disable()
            try:
                draft = await _io_bound(korean_lesson, source, level)
                with translated:
                    translated.clear()
                    _render_lesson(draft, level)
            except OperationBusyError:
                ui.notify(
                    "다른 학습 작업을 처리 중입니다. 잠시 후 다시 시도해 주세요.", type="warning"
                )
            finally:
                translate_button.enable()

        translate_button = ui.button("한국어 풀이로 읽기", on_click=request_korean).props("outline")
        ui.label(
            "AI 풀이 초안은 공식 번역과 구분하며, 사용할 수 없으면 기본 도움말을 유지해요."
        ).classes("cb-muted")
    with ui.column().classes("w-full gap-3") as translated:
        _render_lesson(lesson, level)


def _render_lesson(lesson, level):
    ui.label(lesson.intro).classes("font-semibold")
    ui.label(lesson.notice).classes("cb-muted")
    if level is LearningLevel.ADVANCED:
        ui.label(lesson.original_text or "수집된 원문이 없습니다.").classes("cb-reading").style(
            "white-space: pre-wrap; overflow-wrap: anywhere"
        )
        ui.label(
            "검토할 점: 연대가 건립·재건 중 무엇을 뜻하는지, "
            "주변 건물과 대상이 구분되는지 확인해 주세요."
        ).classes("cb-muted")
    else:
        for section in lesson.sections:
            ui.label(section.heading).classes("cb-title text-lg")
            ui.label(section.text).classes("cb-reading").style(
                "white-space: pre-wrap; overflow-wrap: anywhere"
            )
            if section.category == "구조":
                from culturebridge.services.learning_diagram_service import shape_diagram

                diagram = shape_diagram(section.evidence_quote)
                if diagram:
                    ui.html(diagram)
            if section.check_question and level is LearningLevel.BEGINNER:
                ui.label("생각해 보기 · " + section.check_question).classes("cb-muted text-sm")
            if level is LearningLevel.INTERMEDIATE and section.event:
                ui.label("연대가 가리키는 사건: " + section.event).classes("cb-muted")
            if section.evidence_quote:
                with ui.expansion("이 항목의 공식 원문 근거").classes("w-full"):
                    ui.label(section.evidence_quote).style("white-space: pre-wrap")
        if lesson.glossary:
            with ui.expansion("어려운 용어 풀이").classes("w-full"):
                for term, meaning in lesson.glossary.items():
                    ui.label(term + ": " + meaning)
        with ui.expansion("공식 원문 전체 보기").classes("w-full"):
            ui.label(lesson.original_text or "수집된 원문이 없습니다.").style(
                "white-space: pre-wrap; overflow-wrap: anywhere"
            )
    ui.link("공식 원문 출처", str(lesson.source_url), new_tab=True)


def _collected_source_cards(sources: list[CollectedSource], level=LearningLevel.BEGINNER) -> None:
    labels = {
        "fresh": "새로 수집함",
        "cached": "저장된 공식 자료",
        "stale": "갱신 필요",
        "unavailable": "수집 실패",
    }
    for source in sources:
        with ui.card().classes("cb-card w-full p-5 gap-2"):
            ui.label(
                source.organization.replace("UNESCO", "유네스코(UNESCO)")
                + " · "
                + display_name(source.id, source.title)
            ).classes("cb-title text-xl")
            if source.status in {"stale", "unavailable"}:
                ui.label(labels[source.status]).classes("font-semibold")
            ui.label(source.scope_note).classes("cb-muted")
            ui.link("공식 자료 페이지", str(source.source_url), new_tab=True)
            terms = policy_url(source.source_url)
            if terms:
                ui.link("자료 이용 안내", terms, new_tab=True)
            if source.content:
                _lesson_content(source, level)


@ui.page("/")
def home_page(
    q: str = "",
    scope: str = "all",
    page: int = 1,
    level: str = "beginner",
    goal: str = "compare",
    goal_text: str = "",
    amount: str = "standard",
    auto: bool = False,
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
) -> None:
    from culturebridge.ui.heritage_art import heritage_art

    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-7 py-10"):
        with ui.column().classes("cb-hero cb-illustrated"):
            ui.label("공식 자료와 함께하는 역사 배움").classes("cb-eyebrow")
            ui.label("질문에서 시작하는\n나만의 역사 수업").classes("cb-hero-title").props(
                "role=heading aria-level=1"
            )
            ui.label(
                "궁금한 이야기를 들려주세요. 관심에 맞춰 살펴"
                "보고, 문화유산의 유사점과 차이점도 함께 알아"
                "봐요."
            ).classes("cb-hero-copy")
            with ui.row().classes("gap-2"):
                ui.label("국가유산청 · UNESCO 공식 자료").classes("cb-badge")
                ui.label("나에게 맞는 설명과 복습").classes("cb-badge")
            with ui.row().classes("cb-hero-actions gap-3 flex-wrap"):
                ui.link("역사 이야기 시작하기", "#history-start").classes("cb-link-primary")
                ui.link("문화유산 찾아보기", "#heritage-search").classes("cb-link-secondary")
            ui.html(
                '<div class="cb-study-step'
                's" aria-label="학습 과정"><sp'
                "an><b>1</b> 질문</span><spa"
                "n><b>2</b> 근거 살펴보기</span>"
                "<span><b>3</b> 내 말로 익히기</"
                "span></div>"
            )
            ui.label("유산 유형을 표현한 창작 삽화 · 실제 모습이나 복원도가 아니에요.").classes(
                "cb-art-caption"
            )
            ui.html(heritage_art(panoramic=True)).classes("cb-hero-art")

        learning_entry(_io_bound, embedded=True)
        with ui.column().classes("cb-section-heading gap-1 w-full"):
            ui.label("하나의 문화유산에서 세계로").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            ui.label("직접 유산을 찾고, 공식 설명을 읽으며 비교 학습을 시작해 보세요.").classes(
                "cb-muted"
            )

        with ui.element("section").classes("cb-mode-strip").props('aria-label="비교 범위"'):
            with ui.column().classes("gap-1"):
                ui.label(SCOPE_LABELS[comparison_scope.value]).classes("cb-title text-xl")
                ui.label(
                    "한국 밖의 유산을 추천해요."
                    if comparison_scope is ComparisonScope.OVERSEAS
                    else "한국의 유산을 추천해요."
                ).classes("cb-muted text-sm")
            _comparison_entry(q, level, comparison_scope, context=lambda: return_context(page))

        with ui.card().classes("cb-card w-full p-6 gap-5").props("id=heritage-search"):
            with ui.expansion("학습 설정 · 수준과 목표 바꾸기").classes("w-full"):
                ui.label("처음이라면 초급으로 시작해 보세요.").classes("cb-muted")
                level = (
                    ui.toggle(LEVEL_LABELS, value=_learning_level(level).value)
                    .classes("w-full")
                    .props('aria-label="학습 수준"')
                )
                with ui.element("div").classes("cb-form-grid"):
                    goal = (
                        ui.select(GOAL_LABELS, value=_goal(goal).value, label="학습 목표")
                        .props("outlined")
                        .classes("w-full")
                    )
                    amount = (
                        ui.select(AMOUNT_LABELS, value=_amount(amount).value, label="학습 분량")
                        .props("outlined")
                        .classes("w-full")
                    )
                goal_text = (
                    ui.input(
                        label="세부 목표 (선택)",
                        value=goal_text[:200],
                        placeholder="예: 재료와 불교의 관계가 궁금해요",
                    )
                    .props("outlined maxlength=200")
                    .classes("w-full")
                )
            ui.label("어떤 문화유산이 궁금한가요?").classes("cb-title text-xl cb-section-title")
            with ui.element("div").classes("cb-search-bar"):
                scope = (
                    ui.select(
                        {
                            "all": "통합 검색",
                            "korea": "한국 · 국가유산청",
                            "world": "세계 · UNESCO",
                        },
                        value=scope if scope in {"all", "korea", "world"} else "all",
                        label="검색 범위",
                    )
                    .props("outlined")
                    .classes("w-full")
                )
                search = (
                    ui.input(
                        label="문화유산 검색",
                        value=q[:100],
                        placeholder="예: 불국사, 경복궁, 만리장성, 타지마할, Japan",
                    )
                    .props("outlined clearable maxlength=100")
                    .classes("w-full")
                )
            ui.label(
                "한국은 국가유산청, 세계는 UNESCO 등재 목록에서 찾습니다. "
                "해외 문화유산은 등록된 한국어 명칭·공식 영문 이름·국가명으로 검색할 수 있습니다."
            ).classes("cb-muted text-sm")
            search_submit = ui.row().classes("cb-search-submit")
            suggestions = (
                ui.column().classes("w-full gap-1").props('role=group aria-label="홈 검색어 제안"')
            )
            results = ui.column().classes("w-full gap-3")
            official_results = (
                ui.column().classes("w-full gap-3").props("role=status aria-live=polite")
            )
            suggestion_index = get_home_suggestions(limit=6000, scope=scope.value)
            search.set_autocomplete([item.value for item in suggestion_index])
            search_version = 0
            busy = False

            def return_context(result_page=1):
                return home_context(
                    search.value,
                    scope.value,
                    result_page,
                    level.value,
                    goal.value,
                    goal_text.value,
                    amount.value,
                    comparison_scope,
                )

            def render_results() -> None:
                results.clear()
                with results:
                    ui.label("처음이라면 이 유산부터").classes("font-semibold")
                    items = list_heritages(search.value)
                    if scope.value == "korea":
                        items = [item for item in items if item.country == "대한민국"]
                    if scope.value == "world":
                        items = [item for item in items if item.country != "대한민국"]
                    if not items:
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
                                    with_return(
                                        f"/explore/{heritage_id}?level={level.value}&"
                                        + _goal_query(
                                            goal.value,
                                            goal_text.value,
                                            amount.value,
                                            comparison_scope,
                                        ),
                                        return_context(page),
                                    )
                                ),
                            ).props("unelevated").style(f"background: {ACCENT}").classes(
                                "cb-action"
                            )

            async def submit_search(page: int = 1) -> None:
                nonlocal busy, suggestion_index
                query = (search.value or "").strip()
                selected_scope = scope.value
                version = search_version
                if busy:
                    return
                if not 1 <= len(query) <= 100:
                    ui.notify("검색어를 1~100글자로 입력해 주세요.", color="warning")
                    return
                busy = True
                search_button.disable()
                official_results.clear()
                with official_results:
                    ui.label("국내·세계 공식 자료를 검색하고 있습니다…")
                    ui.spinner()
                try:
                    response = await _io_bound(search_home, query, selected_scope, page)
                    if version != search_version:
                        return  # Never show a completed search under a different input.
                    official_results.clear()
                    suggestion_index = get_home_suggestions(limit=6000, scope=selected_scope)
                    search.set_autocomplete([item.value for item in suggestion_index])
                    with official_results:
                        ui.label(f"'{query}' 공식 자료 검색 결과 · {page}페이지").classes(
                            "cb-title text-xl"
                        )
                        for notice in response.notices:
                            ui.label(service_text(notice)).props("role=alert")
                        ui.label(
                            "관심 있는 유산을 고르면 함께 살펴볼 유산과 "
                            "설명을 찾아드려요. 자료가 부족하면 판단을 보"
                            "류합니다."
                        )
                        if response.individual:
                            ui.label(f"해외 개별 문화유산 · {len(response.individual)}건").classes(
                                "font-semibold"
                            )
                            ui.label(
                                "공식 자료 연결 대상입니다. 선택한 뒤 원문 "
                                "연결과 학습 근거를 확인해요."
                            ).classes("cb-muted")
                            for item in response.individual:
                                with ui.card().classes("cb-card cb-result-card w-full p-4 gap-2"):
                                    ui.label(item.korean + " (" + item.name + ")").classes(
                                        "cb-title text-xl"
                                    )
                                    ui.label(
                                        display_country(item.country)
                                        + " · "
                                        + (
                                            "특정 유산의 경내 전체"
                                            if item.unit == "site"
                                            else "개별 건물"
                                        )
                                    )
                                    ui.link("공식 소개", item.source_url, new_tab=True)
                                    ui.button(
                                        "이 유산 알아보기",
                                        on_click=lambda selected=item: ui.navigate.to(
                                            with_return(
                                                f"/discover/official/{selected.id.split(':', 1)[1]}"
                                                f"?level={level.value}&"
                                                + _goal_query(
                                                    goal.value,
                                                    goal_text.value,
                                                    amount.value,
                                                    comparison_scope,
                                                ),
                                                return_context(page),
                                            )
                                        ),
                                    )
                        if response.korean is not None:
                            ui.label(
                                f"국가유산청 · 총 {response.korean.total}건 (최대 10건)"
                            ).classes("font-semibold")
                            for item in response.korean.items:
                                with ui.card().classes("cb-card cb-result-card w-full p-4 gap-2"):
                                    ui.label(item.name).classes("cb-title text-xl")
                                    ui.label(
                                        f"대한민국 · {item.designation} · {item.region} {item.city}"
                                    )
                                    ui.button(
                                        "공식 설명 보기",
                                        on_click=lambda selected=item, result_page=page: (
                                            ui.navigate.to(
                                                with_return(
                                                    f"/official/{selected.kind_code}/{selected.asset_number}/{selected.region_code}?level={level.value}&comparison_scope={comparison_scope.value}",
                                                    return_context(result_page),
                                                )
                                            )
                                        ),
                                    ).props("flat no-caps")
                                    ui.button(
                                        "이 유산 알아보기",
                                        on_click=lambda selected=item: ui.navigate.to(
                                            with_return(
                                                f"/discover/khs/{selected.kind_code}:{selected.asset_number}:{selected.region_code}"
                                                f"?level={level.value}&"
                                                + _goal_query(
                                                    goal.value,
                                                    goal_text.value,
                                                    amount.value,
                                                    comparison_scope,
                                                ),
                                                return_context(page),
                                            )
                                        ),
                                    )
                            ui.link(
                                "국가유산청 검색 화면에서 더 찾기",
                                home_context(
                                    query,
                                    "korea",
                                    page,
                                    level.value,
                                    goal.value,
                                    goal_text.value,
                                    amount.value,
                                    comparison_scope,
                                ),
                            )
                        if response.world is not None:
                            ui.label(f"UNESCO · 총 {response.world.total}건 (최대 10건)").classes(
                                "font-semibold"
                            )
                            if response.world.stale:
                                ui.label(
                                    "연결 실패로 이전 UNESCO 자료를 표시합니다. 갱신이 필요합니다."
                                )
                            for item in response.world.records:
                                with ui.card().classes("cb-card w-full p-4 gap-2"):
                                    ui.link(
                                        display_name("unesco:" + item.id, item.name),
                                        str(item.source_url),
                                        new_tab=True,
                                    )
                                    ui.button(
                                        "이 세계유산 알아보기",
                                        on_click=lambda selected=item: ui.navigate.to(
                                            with_return(
                                                f"/discover/unesco/{selected.id}?level={level.value}&"
                                                + _goal_query(
                                                    goal.value,
                                                    goal_text.value,
                                                    amount.value,
                                                    comparison_scope,
                                                ),
                                                return_context(page),
                                            )
                                        ),
                                    )
                                    ui.label(
                                        display_country(item.countries)
                                        + f" · 등재연도 {item.inscription_year}"
                                    )
                                    ui.label(
                                        "등재 유산군은 개별 건물과 다를 수 있습니다. "
                                        "등재연도는 건립연도가 아닙니다."
                                    )
                            ui.link(
                                "UNESCO 검색 화면에서 더 찾기",
                                home_context(
                                    query,
                                    "world",
                                    page,
                                    level.value,
                                    goal.value,
                                    goal_text.value,
                                    amount.value,
                                    comparison_scope,
                                ),
                            )
                            ui.link(
                                "UNESCO 데이터 출처·이용 조건",
                                response.world.license_url,
                                new_tab=True,
                            )
                        count = (
                            (response.korean.total if response.korean else 0)
                            + (response.world.total if response.world else 0)
                            + len(response.individual)
                        )
                        with ui.row().classes("gap-3"):
                            if page > 1:
                                ui.button("이전 결과", on_click=lambda: submit_search(page - 1))
                            largest = max(
                                response.korean.total if response.korean else 0,
                                response.world.total if response.world else 0,
                            )
                            if page * 10 < largest:
                                ui.button("다음 결과", on_click=lambda: submit_search(page + 1))
                        if not count:
                            ui.label(
                                "공식 자료 결과가 없습니다. "
                                "이름·국가명·영문 표기를 바꾸거나 다시 검색해 주세요."
                            )
                            from culturebridge.services.search_help_service import (
                                suggested_search_terms,
                            )

                            for term in suggested_search_terms(query):
                                ui.button(
                                    term + "로 다시 검색",
                                    on_click=lambda text=term: choose_suggestion(text),
                                ).props("outline")
                except (sqlite3.Error, ValueError):
                    if version == search_version:
                        official_results.clear()
                        with official_results:
                            ui.label("검색 자료를 확인하지 못했습니다. 다시 시도해 주세요.").props(
                                "role=alert"
                            )
                finally:
                    busy = False
                    search_button.enable()

            async def choose_suggestion(value: str) -> None:
                search.set_value(value)
                await submit_search()

            def input_changed() -> None:
                nonlocal search_version
                search_version += 1
                official_results.clear()
                render_results()
                suggestions.clear()
                term = normalize_search(search.value or "")
                if not term:
                    return
                options = [
                    item for item in suggestion_index if term in normalize_search(item.value)
                ]
                options.sort(
                    key=lambda item: (
                        normalize_search(item.value) != term,
                        not normalize_search(item.value).startswith(term),
                    )
                )
                with suggestions:
                    for item in options[:8]:
                        ui.button(
                            item.label, on_click=lambda value=item.value: choose_suggestion(value)
                        ).props("flat no-caps align=left").classes("w-full cb-action")

            def scope_changed() -> None:
                nonlocal suggestion_index
                suggestion_index = get_home_suggestions(limit=6000, scope=scope.value)
                search.set_autocomplete([item.value for item in suggestion_index])
                input_changed()

            search.on_value_change(lambda _: input_changed())
            scope.on_value_change(lambda _: scope_changed())
            search.on("keydown.enter", lambda _: submit_search())
            search_button = (
                ui.button("공식 자료 통합 검색", on_click=lambda: submit_search())
                .props("unelevated icon=search")
                .classes("cb-action")
            )
            search_button.move(search_submit)
            render_results()
            if auto and q.strip():
                _restore_results(lambda: submit_search(page=max(1, min(page, 10000))))


@ui.page("/learn")
def conversation_page(conversation_id: str = ""):
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-6 py-10"):
        learning_chat(_io_bound, conversation_id)


@ui.page("/settings")
def learning_settings_page():
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("설정").classes("cb-title text-3xl").props("role=heading aria-level=1")
        ui.label("나에게 편한 설명 방식을 골라보세요.").classes("cb-muted")
        ui.label(
            "이 브라우저의 대화 학습 설명에 적용돼요. 비교와 학습 코스의 수준·목표는 "
            "각 화면에서 선택해요. 대화 중에도 ‘더 쉽게’, ‘짧게 설명해줘’라고 요청할 수 있어요."
        ).classes("cb-muted")
        with ui.card().classes("cb-card w-full p-5 gap-3"):
            tone_controls(_io_bound, expanded=True)
        ui.link("관심사와 학습 목표 관리", "/learning-history#learning-profile")
        ui.link("대화 학습으로", "/learn")


@ui.page("/history-search")
def history_search_page():
    from culturebridge.services.history_search_service import search_history

    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("인물과 사건 자료 찾기").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label("국사편찬위원회 ‘신편 한국사’의 실제 검색 결과를 찾아요.").classes("cb-muted")
        ui.label(
            "제목을 고르면 공식 사이트의 원문을 읽을 수 있어요. "
            "검색 결과만으로 역사적 사실을 판단하거나 AI 설명을 만들지는 않아요."
        )
        query = (
            ui.input(label="인물·사건 이름", placeholder="예: 세종, 임진왜란")
            .props("outlined maxlength=80")
            .classes("w-full")
        )
        status = ui.label("궁금한 이름을 입력해 보세요.").props("role=status aria-live=polite")
        results = ui.column().classes("w-full gap-3").props('aria-label="역사 자료 검색 결과"')
        busy = False

        async def search():
            nonlocal busy
            if busy:
                return
            busy = True
            button.disable()
            results.clear()
            status.set_text("공식 자료에서 찾고 있어요…")
            try:
                records, notice = await _io_bound(search_history, query.value or "")
                status.set_text(f"자료 {len(records)}개. " + notice)
                with results:
                    for record in records:
                        with ui.card().classes("cb-card w-full p-5"):
                            ui.link(record["name"], record["reading_url"], new_tab=True)
                            ui.label(record["region"]).classes("cb-muted text-sm")
                            ui.label(record["match_note"]).classes("cb-muted text-sm")
            except ValueError as exc:
                status.set_text(str(exc))
            finally:
                busy = False
                button.enable()

        button = ui.button("역사 자료 검색", on_click=search, icon="search")
        query.on("keydown.enter", search)
        ui.link("대화 학습으로", "/learn")


@ui.page("/install")
def install_page():
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("홈 화면에 추가하기").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label("별도 앱 파일 없이 컬처브릿지를 홈 화면에 추가할 수 있어요.")
        ui.label("Android·PC: 브라우저 메뉴의 ‘앱 설치’ 또는 아래 버튼을 이용해 주세요.")
        ui.label("iPhone·iPad: Safari의 공유 메뉴 → ‘홈 화면에 추가’를 선택해 주세요.")
        ui.label("설치 버튼은 브라우저와 접속 환경에 따라 보이지 않을 수 있어요.")
        ui.html('<p id="cb-install-status" role="status" aria-live="polite"></p>')
        ui.html('<p id="cb-update-status" role="status" aria-live="polite"></p>')
        ui.html('<p id="cb-connection-status" role="status" aria-live="polite"></p>')
        with ui.dialog().props(
            'role=dialog aria-modal=true aria-label="새 버전 적용 확인"'
        ) as update_confirmation:
            with ui.card().classes("cb-card p-6 gap-4"):
                ui.label("새 버전으로 바꿀까요?").classes("cb-title text-xl")
                ui.label("작성 중인 입력은 사라질 수 있어요. 대화를 보낸 뒤 적용해 주세요.")
                with ui.row().classes("gap-3 flex-wrap"):
                    ui.button("계속 학습하기", on_click=update_confirmation.close).props("flat")
                    ui.button("지금 새 버전 적용", on_click=update_confirmation.close).on(
                        "click", js_handler="() => window.CultureBridgePWA?.applyUpdate()"
                    )
        ui.on("cb_pwa_update_confirm", update_confirmation.open)
        ui.button("홈 화면에 추가하기", icon="add_to_home_screen").on(
            "click", js_handler="() => window.CultureBridgePWA?.install()"
        )
        ui.button("새 버전 적용", icon="refresh").on(
            "click", js_handler="() => window.CultureBridgePWA?.update()"
        ).props("outline")
        ui.label(
            "대화·검색에는 인터넷과 실행 중인 서버가 필요해요. 오프라인에서는 연결 안내만 보여줘요."
        )
        ui.label("실제 기기에서는 HTTPS 주소가 필요해요. 홈 화면 추가는 서버를 대신 켜주지 않아요.")
        ui.label("기록은 이 브라우저에 연결돼요. 다른 기기·설치 환경과 자동 공유되지 않아요.")
        ui.link("대화 학습으로", "/learn")


@ui.page("/domestic")
def domestic_comparison_page(
    q: str = "",
    scope: str = "all",
    page: int = 1,
    level: str = "beginner",
    goal: str = "compare",
    goal_text: str = "",
    amount: str = "standard",
    auto: bool = False,
):
    home_page(
        q=q,
        scope=scope,
        page=page,
        level=level,
        goal=goal,
        goal_text=goal_text,
        amount=amount,
        auto=auto,
        comparison_scope=ComparisonScope.DOMESTIC,
    )


@ui.page("/kiosk")
def kiosk_page(reset: str | None = None) -> None:
    _base_styles()
    _kiosk_header()
    _enable_kiosk_timeout()
    with ui.column().classes("cb-shell cb-kiosk gap-8 py-10"):
        if reset in {"manual", "timeout"}:
            ui.label("이전 체험을 종료했어요. 새로운 체험을 시작할 수 있어요.").classes(
                "w-full rounded-xl bg-blue-50 p-4 text-center text-lg font-semibold text-blue-900"
            ).props("role=status aria-live=polite")

        with ui.column().classes("w-full items-center gap-3 text-center"):
            ui.label("문화유산 비교 체험").classes("cb-title text-5xl").props(
                "role=heading aria-level=1"
            )
            ui.label("학습 수준을 누른 뒤 문화유산을 선택해 주세요.").classes("cb-muted text-2xl")

        with ui.card().classes("cb-card w-full p-8 gap-6"):
            ui.label("1. 학습 수준").classes("cb-title text-3xl").props("role=heading aria-level=2")
            level = (
                ui.toggle(
                    LEVEL_LABELS,
                    value=LearningLevel.BEGINNER.value,
                )
                .props("spread unelevated")
                .classes("w-full cb-kiosk-action")
            )

            ui.label("2. 문화유산 선택").classes("cb-title text-3xl mt-2")
            goal = ui.select(GOAL_LABELS, value="observe", label="체험 목표").classes("w-full")
            amount = ui.select(AMOUNT_LABELS, value="brief", label="체험 분량").classes("w-full")
            with ui.element("div").classes("cb-kiosk-grid w-full gap-5"):
                for item in list_heritages():
                    with ui.card().classes("cb-kiosk-card w-full justify-between p-6 gap-3"):
                        ui.label(item.name).classes("cb-title text-2xl").props(
                            "role=heading aria-level=2"
                        )
                        ui.label(f"{item.country} · {item.period}").classes("cb-muted text-lg")
                        ui.button(
                            f"{item.name} 선택",
                            on_click=lambda heritage_id=item.id: ui.navigate.to(
                                f"/explore/{heritage_id}?level={level.value}&mode={KIOSK_MODE}&"
                                + _goal_query(goal.value, amount=amount.value)
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
    goal: str = "compare",
    goal_text: str = "",
    amount: str = "standard",
    return_to: str = "",
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
) -> None:
    _base_styles()
    _page_header(mode)
    if heritage_id.startswith(("khs:", "unesco:", "official:")):
        provider, identity = heritage_id.split(":", 1)
        with ui.column().classes("cb-shell py-10"):
            _return_button(return_to, _home_route(mode), mode=mode)
            ui.label("선택한 유산의 설명을 읽고 함께 살펴볼 유산을 찾아드려요.")
            ui.link(
                "함께 살펴볼 문화유산을 찾아요",
                with_return(
                    _route(
                        f"/discover/{provider}/{identity}?level={level}&"
                        + _goal_query(goal, goal_text, amount, comparison_scope),
                        mode,
                    ),
                    return_to,
                ),
            )
        return
    level = _learning_level(level).value
    learning_goal = _goal(goal)
    selected = next((item for item in list_heritages() if item.id == heritage_id), None)
    with ui.column().classes("cb-shell gap-6 py-10"):
        _return_button(return_to, _home_route(mode), mode=mode)
        if selected is None:
            ui.label("문화유산을 찾을 수 없습니다.").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            ui.button("처음으로", on_click=lambda: ui.navigate.to(_home_route(mode))).classes(
                _action_classes(mode)
            )
            return

        ui.label("함께 알아보면 좋은 문화유산").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label(SCOPE_LABELS[comparison_scope.value]).classes("font-semibold")
        candidates = [
            c
            for c in recommend_related(heritage_id, learning_goal)
            if candidate_in_scope(c.heritage.country, comparison_scope)
        ]
        if not candidates:
            ui.label("선택한 범위에 등록된 비교 예제가 없습니다. 다른 범위로 자동 전환하지 않아요.")
            if heritage_id == "seokguram" and comparison_scope is ComparisonScope.DOMESTIC:
                ui.link(
                    "국내 문화유산 자료에서 찾아보기",
                    with_return(
                        _route(
                            "/discover/khs/"
                            + ":".join(SEOKGURAM_CODES)
                            + f"?level={level}&"
                            + _goal_query(learning_goal.value, goal_text, amount, comparison_scope),
                            mode,
                        ),
                        return_to,
                    ),
                )
        ui.label(f"선택한 문화유산: {selected.name}").classes("text-lg font-semibold")
        from culturebridge.services.heritage_identity_service import canonical_id

        official_identity = canonical_id(heritage_id)
        provider, identifier = official_identity.split(":", 1)
        ui.link(
            "이 유산의 공식 자료로 탐구하기",
            with_return(
                _route(
                    f"/discover/{provider}/{identifier}?level={level}&"
                    + _goal_query(learning_goal.value, goal_text, amount, comparison_scope),
                    mode,
                ),
                return_to,
            ),
        )
        ui.label(f"학습 수준: {LEVEL_LABELS.get(level, '초급')}").classes("cb-muted")
        ui.label("학습 목표: " + GOAL_LABELS[learning_goal.value])
        ui.label("학습 분량: " + AMOUNT_LABELS[_amount(amount).value])
        if goal_text:
            ui.label("세부 목표: " + goal_text[:200])

        for candidate in candidates:
            with ui.card().classes("cb-card w-full p-6 gap-3"):
                ui.label(candidate.heritage.name).classes("cb-title text-2xl").props(
                    "role=heading aria-level=2"
                )
                ui.label(f"{candidate.heritage.country} · {candidate.heritage.period}").classes(
                    "cb-muted"
                )
                ui.label(candidate.reason).classes("text-base")
                ui.button(
                    "예제 자료로 비교",
                    on_click=lambda right_id=candidate.heritage.id: ui.navigate.to(
                        with_return(
                            _route(
                                f"/compare/{heritage_id}/{right_id}?level={level}&"
                                + _goal_query(
                                    learning_goal.value, goal_text, amount, comparison_scope
                                ),
                                mode,
                            ),
                            return_to,
                        )
                    ),
                ).props("unelevated").style(f"background: {ACCENT}").classes(_action_classes(mode))
                ui.button(
                    "두 문화유산 함께 알아보기",
                    on_click=lambda right_id=candidate.heritage.id: ui.navigate.to(
                        with_return(
                            _route(
                                f"/research/{heritage_id}/{right_id}?level={level}&"
                                + _goal_query(
                                    learning_goal.value,
                                    goal_text,
                                    _amount(amount).value,
                                    comparison_scope,
                                ),
                                mode,
                            ),
                            return_to,
                        )
                    ),
                ).classes(_action_classes(mode))

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
    return_to: str = "",
    goal: str = "compare",
    goal_text: str = "",
    amount: str = "standard",
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
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
            validate_pair_scope(get_heritage(right_id).country, comparison_scope)
            result = create_saved_comparison(
                left_id,
                right_id,
                learning_level,
                comparison_scope=comparison_scope,
                goal=_goal(goal),
                goal_text=goal_text[:200],
                amount=_amount(amount),
                curriculum=plan_learning(
                    learning_level, _goal(goal), goal_text[:200], _amount(amount)
                )[0],
                reuse=True,
            )
            sources = get_sources(result.source_ids)
    except (ComparisonNotFoundError, HeritageNotFoundError, ValueError):
        _error_page("비교 결과를 찾을 수 없습니다.", mode)
        return
    except sqlite3.Error:
        logger.exception("Comparison storage failed")
        _error_page("비교 결과를 저장하거나 불러올 수 없습니다.", mode)
        return

    with ui.column().classes(f"cb-shell gap-7 py-10 {'cb-kiosk' if _is_kiosk(mode) else ''}"):
        comparison_scope = result.comparison_scope or (
            ComparisonScope.DOMESTIC
            if candidate_in_scope(result.right.country, ComparisonScope.DOMESTIC)
            else ComparisonScope.OVERSEAS
        )
        recommendation_url = _route(
            f"/explore/{left_id}?level={learning_level.value}&"
            + _goal_query(
                result.goal.value if saved_id else goal,
                result.goal_text if saved_id else goal_text,
                result.amount.value if saved_id else amount,
                comparison_scope,
            ),
            mode,
        )
        for prefix, route in (
            ("official:", "/discover/official/"),
            ("khs:", "/discover/khs/"),
            ("unesco:", "/discover/unesco/"),
        ):
            if left_id.startswith(prefix):
                recommendation_url = recommendation_url.replace(
                    "/explore/" + left_id, route + left_id[len(prefix) :], 1
                )
                break
        _return_button(return_to, recommendation_url, "추천 화면으로", mode)
        with ui.column().classes("gap-1"):
            ui.label("유사점과 차이점 알아보기").classes("cb-title text-3xl").props(
                "role=heading aria-level=1"
            )
            ui.label(
                display_name(result.left.id, result.left.name)
                + " ↔ "
                + display_name(result.right.id, result.right.name)
            ).classes("text-xl font-semibold")
            ui.label(f"학습 수준: {LEVEL_LABELS[learning_level.value]}").classes("cb-muted")
            if result.learning_goal:
                ui.label(f"학습 목표: {result.learning_goal}").classes("text-lg font-semibold")
            if result.curriculum:
                ui.label("선택 목표: " + GOAL_LABELS[result.goal.value])
                if result.goal_text:
                    ui.label("세부 목표: " + result.goal_text)
                learning_steps(1, result.curriculum)
                ui.label("학습 분량: " + AMOUNT_LABELS[result.amount.value])
                for notice in result.learning_notices:
                    ui.label(service_text(notice)).classes("cb-muted")
            if saved_id and result.learning_version < LEARNING_VERSION:
                ui.label(
                    "이전 방식의 설명이에요. 아래 학습 기록 관리"
                    "에서 다시 탐구하면 개선된 설명으로 학습할 수"
                    " 있어요."
                ).props("role=note").classes("cb-muted")
            with ui.expansion("학습 기록 관리 · 저장과 다시 탐구").classes("w-full"):
                if saved_id:

                    async def relearn():
                        relearn_button.disable()
                        try:
                            updated = await _io_bound(relearn_saved_comparison, saved_id)
                            ui.navigate.to(
                                with_return(
                                    _route(
                                        f"/compare/{left_id}/{right_id}?saved_id={updated.saved_id}",
                                        mode,
                                    ),
                                    return_to,
                                )
                            )
                        except (
                            OfficialServiceError,
                            ValueError,
                            ComparisonNotFoundError,
                            OperationBusyError,
                            sqlite3.Error,
                        ):
                            ui.notify(
                                "다시 탐구하지 못했어요. 기존 기록은 그대로 "
                                "보존됩니다. 잠시 후 다시 시도해 주세요.",
                                color="warning",
                            )
                        finally:
                            relearn_button.enable()

                    relearn_button = ui.button(
                        "최신 근거로 다시 탐구하기", on_click=relearn
                    ).classes("cb-action")
                    ui.label(
                        "저장 당시의 비교와 출처입니다. 자유 질문도 이 저장본의 원문을 사용합니다."
                        if result.collected_sources
                        else "저장 당시의 비교와 출처입니다. "
                        "이 기본 예제의 자유 질문은 현재 등록된 요약 자료를 사용합니다."
                    ).classes("cb-muted")
                if result.saved_id and not _is_kiosk(mode):
                    ui.link(
                        "저장된 이 비교 다시 열기",
                        f"/compare/{left_id}/{right_id}?saved_id={result.saved_id}",
                    ).classes("text-blue-800")
                    ui.link("저장된 비교 목록", "/comparisons").classes("text-blue-800")
                if result.saved_id and not _is_kiosk(mode):
                    _report_links(result.saved_id)

        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("공통점 검토 안내" if result.basis == "extracted" else "공통점").classes(
                "cb-title text-2xl"
            )
            for point in result.common_points:
                ui.label(f"• {point}").classes("text-base")
            for common in result.common_evidence:
                ui.label(common.context_note).classes("cb-muted")
                with ui.expansion("함께 살펴본 특징의 양쪽 근거").classes("w-full"):
                    _extracted_field_cards(
                        [common.left_evidence, common.right_evidence], learning_level
                    )

        if result.collected_sources or result.extracted_fields:
            ui.label(
                "설명의 뜻과 대상은 추가 확인이 필요합니다. "
                "핵심 비교 아래에서 공식 원문과 상세 설명을 "
                "확인할 수 있어요."
            ).classes("cb-muted")
            with ui.expansion("자세한 설명과 공식 원문 읽기").classes("w-full"):
                if result.collected_sources:
                    _collected_source_cards(result.collected_sources, learning_level)
                if result.extracted_fields:
                    _extracted_field_cards(result.extracted_fields, learning_level)

        ui.label(
            "원문과 별도로 보는 항목별 비교"
            if learning_level is LearningLevel.ADVANCED
            else "항목별 비교"
        ).classes("cb-title text-2xl").props("role=heading aria-level=2")
        for point in result.differences:
            with ui.card().classes("cb-card w-full p-6 gap-3"):
                ui.label(point.category).classes("cb-title text-xl")
                with ui.element("div").classes("cb-compare-grid w-full gap-4"):
                    with ui.column().classes("gap-1 rounded-lg p-4").style(f"background: {PALE}"):
                        ui.label(display_name(result.left.id, result.left.name)).classes(
                            "font-bold"
                        )
                        ui.label(
                            beginner_text(point.category, point.left)
                            if learning_level is LearningLevel.BEGINNER
                            else point.left
                        )
                    with ui.column().classes("gap-1 rounded-lg p-4").style(f"background: {PALE}"):
                        ui.label(display_name(result.right.id, result.right.name)).classes(
                            "font-bold"
                        )
                        ui.label(
                            beginner_text(point.category, point.right)
                            if learning_level is LearningLevel.BEGINNER
                            else point.right
                        )
                ui.label(point.explanation).classes("cb-muted")

        if not _is_kiosk(mode):
            _learning_journal(result.saved_id)

        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("설명의 근거 확인하기").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            if "seokguram" in (left_id, right_id):
                ui.link(
                    "석굴암 원문 읽기",
                    _route("/official/" + "/".join(SEOKGURAM_CODES), mode),
                    new_tab=True,
                )
            status_label = {
                "verified": "확인됨",
                "needs_review": "추가 확인 필요",
                "insufficient_evidence": "근거 부족",
            }[result.verification_status.value]
            ui.label(status_label).classes("font-bold")
            ui.label(
                "연결된 원문을 바탕으로 정리했어요. 출처가 있"
                "다는 것과 해석이 확인됐다는 것은 달라요."
                if result.basis == "extracted"
                else result.verification_note
            ).classes("cb-muted")
            for source in sources:
                ui.link(
                    source.organization.replace("UNESCO", "유네스코(UNESCO)")
                    + " · "
                    + display_name(source.id, source.title),
                    str(source.url),
                    new_tab=True,
                ).classes("text-blue-700")
                if source.summary:
                    ui.label(source.summary).classes("text-sm")
                if source.scope_note:
                    ui.label(source.scope_note).classes("cb-muted text-sm")

        with ui.card().classes("cb-card w-full p-6 gap-4"):
            ui.label("궁금한 점 질문하기").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            ui.label(
                "시대·구조·재료·종교적 배경을 질문하면 어떤 자료로 답했는지, "
                "더 확인할 부분은 무엇인지 함께 알려드려요."
            ).classes("cb-muted")
            question_input = (
                ui.textarea(
                    label="문화유산 질문", placeholder="예: 두 문화유산의 재료는 어떻게 다른가요?"
                )
                .props("outlined autogrow maxlength=500")
                .classes("w-full")
            )
            answer_box = ui.column().props("role=status aria-live=polite").classes("w-full gap-3")
            chat_history = []
            chat_cards = []
            ui.label(
                "이전 대화는 질문을 이해하는 데만 참고해요. 역사적 사실의 근거로 쓰지는 않아요."
            ).classes("cb-muted text-sm")

            async def submit_question() -> None:
                question = (question_input.value or "").strip()
                if not 2 <= len(question) <= 500:
                    ui.notify("질문을 2~500글자로 입력해 주세요.", color="warning")
                    return
                ask_button.disable()
                try:
                    answer = await _io_bound(
                        answer_question,
                        left_id,
                        right_id,
                        question,
                        learning_level,
                        comparison_id=result.saved_id if result.collected_sources else None,
                        history=chat_history[-6:],
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
                chat_history.extend(
                    [
                        {"role": "user", "text": question},
                        {"role": "assistant", "text": answer.answer[:1500]},
                    ]
                )
                del chat_history[:-6]
                with answer_box:
                    with (
                        ui.column()
                        .classes("w-full gap-2 rounded-lg p-5")
                        .style(f"background: {PALE}")
                    ) as message:
                        ui.label("질문: " + question).classes("font-semibold")
                        ui.label(status_text).classes(f"font-bold {status_class}")
                        ui.label(answer.answer).classes("text-base")
                        ui.label(answer.verification_note).classes("cb-muted text-sm")
                        for citation in answer.citations:
                            with ui.expansion("이 문장의 근거"):
                                ui.label(citation.sentence)
                                ui.label(citation.quote).style("white-space:pre-wrap")
                        for source in answer.sources:
                            ui.link(source.title, str(source.url), new_tab=True)
                chat_cards.append(message)
                if len(chat_cards) > 3:
                    chat_cards.pop(0).delete()

            ask_button = (
                ui.button("질문하기", on_click=submit_question)
                .props("unelevated")
                .style(f"background: {ACCENT}")
                .classes(_action_classes(mode))
            )

        with ui.card().classes("cb-card w-full p-6 gap-4"):
            ui.label("이 설명은 근거가 있을까요?").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            if result.collected_sources:
                ui.label(
                    "이 비교에 사용된 공식 원문과 대조합니다. AI 검토 결과는 확정 판정이 아닙니다."
                )
            ui.label(
                "확인할 사실을 입력해 주세요. 여러 사실이 섞인 문장은 나누어 살펴봐요."
                if result.collected_sources
                else "한 가지 사실을 입력해 주세요. 예: 석굴암의 재료는 화강암이다"
            ).classes("cb-muted")
            claim_input = (
                ui.textarea(
                    label="확인하고 싶은 설명",
                    placeholder="예: 두 유산은 같은 재료로 만들어졌다.",
                )
                .props("outlined autogrow maxlength=500")
                .classes("w-full")
            )
            claim_box = ui.column().props("role=status aria-live=polite").classes("w-full gap-3")

            async def submit_claim() -> None:
                claim = (claim_input.value or "").strip()
                if not 2 <= len(claim) <= 500:
                    ui.notify("확인하고 싶은 설명을 2~500자로 입력해 주세요.", color="warning")
                    return
                claim_button.disable()
                claim_button.set_text("자료를 확인하고 있어요…")
                try:
                    checked = await _io_bound(
                        verify_claim,
                        left_id,
                        right_id,
                        claim,
                        comparison_id=result.saved_id if result.collected_sources else None,
                    )
                except (ComparisonNotFoundError, ClaimTargetMismatchError, sqlite3.Error):
                    ui.notify(
                        "대조에 필요한 저장 자료를 불러오지 못했어요. 다시 시도해 주세요.",
                        color="negative",
                    )
                    return
                finally:
                    claim_button.enable()
                    claim_button.set_text("자료와 대조하기")
                labels = {
                    "verified": "확인됨",
                    "needs_review": "추가 확인 필요",
                    "insufficient_evidence": "근거 부족",
                }
                claim_box.clear()
                with claim_box:
                    ui.label("확인할 설명: " + checked.claim)
                    ui.label(labels[checked.verification_status.value]).classes("cb-title text-xl")
                    ui.label(checked.explanation)
                    if checked.execution_trace:
                        with ui.expansion(
                            f"근거를 확인한 과정 · 추가 자료 확인 {checked.retry_count}회"
                        ):
                            for step in checked.execution_trace:
                                ui.label(step)
                        with ui.expansion("대조에 사용한 공식 설명"):
                            _collected_source_cards(checked.collected_sources, learning_level)
                    if checked.unsupported_parts:
                        ui.label("아직 근거를 찾지 못한 내용").classes("font-semibold")
                        for part in checked.unsupported_parts:
                            ui.label(part)
                    for entry in checked.evidence:
                        ui.label(
                            {
                                "supports": "설명을 뒷받침할 수 있는 근거",
                                "contradicts": "설명과 어긋날 수 있는 근거",
                                "related": "관련 근거",
                            }[entry.relation]
                        ).classes("font-semibold")
                        ui.label(entry.fact).classes("font-semibold")
                        if entry.evidence_quote:
                            ui.label("원문 근거: " + entry.evidence_quote).style(
                                "white-space: pre-wrap"
                            )
                        if entry.source_url:
                            ui.link("근거 원문", str(entry.source_url), new_tab=True)
                    for source in checked.sources:
                        ui.link(
                            source.organization.replace("UNESCO", "유네스코(UNESCO)")
                            + " · "
                            + display_name(source.id, source.title),
                            str(source.url),
                            new_tab=True,
                        )
                    ui.label(checked.scope_note).classes("cb-muted text-sm")

            claim_button = (
                ui.button("자료와 대조하기", on_click=submit_claim)
                .props("unelevated")
                .style(f"background: {ACCENT}")
                .classes(_action_classes(mode))
            )

        with ui.row().classes("gap-3"):
            ui.button(
                "학습 확인 퀴즈",
                on_click=lambda: ui.navigate.to(
                    with_return(
                        _route(
                            f"/quiz/{left_id}/{right_id}?level={learning_level.value}"
                            + f"&back_saved_id={result.saved_id}"
                            + (
                                f"&comparison_id={result.saved_id}"
                                if result.extracted_fields
                                else ""
                            ),
                            # The quiz must use the same saved extraction snapshot.
                            mode,
                        ),
                        return_to,
                    )
                ),
            ).props("unelevated").style(f"background: {ACCENT}").classes(_action_classes(mode))
            ui.button(
                "비교 후보로 돌아가기",
                on_click=lambda: ui.navigate.to(with_return(recommendation_url, return_to)),
            ).props("outline").classes(_action_classes(mode))
            ui.button(
                "처음으로",
                on_click=lambda: ui.navigate.to(_home_route(mode)),
            ).props("flat").classes(_action_classes(mode))


@ui.page("/quiz/{left_id}/{right_id}")
async def quiz_page(
    left_id: str,
    right_id: str,
    level: str = LearningLevel.BEGINNER.value,
    mode: str = "web",
    comparison_id: str | None = None,
    quiz_id: str | None = None,
    return_to: str = "",
    back_saved_id: str | None = None,
) -> None:
    _base_styles()
    _page_header(mode)
    learning_level = _learning_level(level)
    if left_id == right_id:
        _error_page("서로 다른 문화유산을 선택해 주세요.", mode)
        return
    loading = None
    settings = None
    if comparison_id and not quiz_id:
        from culturebridge.config import get_settings

        settings = get_settings()
    if settings and settings.gemini_api_key and settings.gemini_enabled:
        loading = ui.column().classes("cb-shell py-10").props("role=status aria-live=polite")
        with loading:
            ui.label("공식 근거에 맞는 퀴즈를 준비하고 있습니다…")
            ui.spinner()
        await ui.context.client.connected()
        if ui.context.client.is_deleted:
            return
    try:
        if quiz_id:
            quiz = load_quiz(quiz_id, left_id, right_id)
        elif loading:
            quiz = await _io_bound(
                generate_quiz,
                left_id,
                right_id,
                learning_level,
                comparison_id=comparison_id,
                reuse=True,
            )
        else:
            quiz = generate_quiz(
                left_id,
                right_id,
                learning_level,
                comparison_id=comparison_id,
                reuse=True,
            )
        comparison_id, learning_level = quiz.comparison_id, quiz.level
    except (ComparisonNotFoundError, EvidenceQuizError) as exc:
        _error_page(
            str(exc) if isinstance(exc, EvidenceQuizError) else "저장된 비교를 찾을 수 없습니다.",
            mode,
        )
        return
    except HeritageNotFoundError:
        _error_page("퀴즈에 사용할 문화유산을 찾을 수 없습니다.", mode)
        return
    except OperationBusyError as exc:
        _error_page(str(exc), mode)
        return
    except (QuizNotFoundError, InvalidQuizAttemptError):
        _error_page("저장된 퀴즈를 확인할 수 없습니다. 탐구를 다시 시작해 주세요.", mode)
        return
    except sqlite3.Error:
        logger.exception("Quiz storage failed")
        _error_page("퀴즈를 준비할 수 없습니다.", mode)
        return
    finally:
        if loading:
            loading.delete()
    radios = []
    back_record_id = comparison_id or back_saved_id
    if back_record_id:
        try:
            back_record = get_saved_comparison(back_record_id).comparison
            if (back_record.left.id, back_record.right.id) != (left_id, right_id):
                back_record_id = None
        except ComparisonNotFoundError:
            back_record_id = None
    comparison_url = with_return(
        _route(
            f"/compare/{left_id}/{right_id}?level={learning_level.value}"
            + (f"&saved_id={back_record_id}" if back_record_id else ""),
            mode,
        ),
        return_to,
    )

    with ui.column().classes(f"cb-shell gap-6 py-10 {'cb-kiosk' if _is_kiosk(mode) else ''}"):
        ui.button("← 비교 화면으로", on_click=lambda: ui.navigate.to(comparison_url)).props(
            "outline no-caps"
        ).classes(_action_classes(mode))
        with ui.column().classes("gap-1"):
            ui.label("배운 내용 퀴즈로 확인하기").classes("cb-title text-3xl").props(
                "role=heading aria-level=1"
            )
            if back_record_id:
                ui.label(
                    display_name(back_record.left.id, back_record.left.name)
                    + " ↔ "
                    + display_name(back_record.right.id, back_record.right.name)
                ).classes("cb-muted")
            if not _is_kiosk(mode):
                ui.link("지난 퀴즈와 오답 복습", "/learning-history")
            ui.label(f"{LEVEL_LABELS[quiz.level.value]} · {quiz.learning_goal}").classes(
                "text-lg font-semibold"
            )
            ui.label("5개 문항에 모두 답한 뒤 채점하세요.").classes("cb-muted text-lg")
            if back_record_id and back_record.learning_version < LEARNING_VERSION:
                ui.label(
                    "이전 방식의 저장본에 연결된 퀴즈예요. 비교 "
                    "화면에서 최신 근거로 다시 탐구하는 것을 권해"
                    "요."
                ).classes("cb-muted")
            if quiz.basis == "extracted":
                ui.label(
                    "공식 설명을 읽고 푸는 퀴즈예요. 설명의 뜻은 원문과 함께 더 확인해 주세요."
                )

        stage_box = ui.column().classes("w-full")
        with stage_box:
            learning_steps(2)
        for number, item in enumerate(quiz.items, start=1):
            with ui.card().classes("cb-card w-full p-6 gap-4"):
                ui.label(f"문제 {number} / 5").classes("cb-muted font-semibold")
                ui.label(item.question).classes("cb-title text-xl")
                options = {choice.id: choice.text for choice in item.choices}
                radios.append(
                    ui.radio(options)
                    .props(f'inline=false aria-label="문제 {number} 선택지"')
                    .classes("w-full")
                )

        result_box = (
            ui.column().props("role=status aria-live=polite tabindex=-1").classes("w-full gap-3")
        )

        async def submit_answers() -> None:
            answers = [radio.value for radio in radios]
            if any(answer is None for answer in answers):
                ui.notify("모든 문항에 답해 주세요.", color="warning")
                missing = next(radio for radio in radios if radio.value is None)
                ui.run_javascript(
                    f'document.getElementById("c{missing.id}")?.querySelector("[role=radio]")?.focus()'
                )
                return
            try:
                result = await _io_bound(
                    evaluate_learning_quiz, quiz.quiz_id, [int(answer) for answer in answers]
                )
            except OperationBusyError as exc:
                ui.notify(str(exc), color="warning")
                return
            except (QuizNotFoundError, InvalidQuizAttemptError):
                ui.notify("퀴즈를 확인할 수 없습니다. 새로 시작해 주세요.", color="warning")
                return
            except sqlite3.Error:
                logger.exception("Quiz grading storage failed")
                ui.notify("채점 결과를 저장하지 못했습니다. 다시 시도해 주세요.", color="negative")
                return
            stage_box.clear()
            with stage_box:
                learning_steps(3)
            result_box.clear()
            with result_box:
                with ui.card().classes("cb-card w-full p-6 gap-3"):
                    ui.label(f"채점 결과 {result.score} / {result.total}").classes(
                        "cb-title text-2xl"
                    )
                    if result.review_items:
                        ui.label("틀린 문제 다시 살펴보기").classes("cb-title text-xl")
                        _review_cards(
                            [item.model_dump(mode="json") for item in result.review_items]
                        )
                    else:
                        ui.label("모든 문항을 맞혔어요. 배운 내용을 다른 유산과 연결해 보세요.")
                    with ui.expansion("전체 문항 해설과 공식 근거"):
                        for explanation in result.explanations:
                            ui.label(explanation).classes("text-base")
                        if result.evidence:
                            _extracted_field_cards(result.evidence, learning_level)
                    if quiz.comparison_id and not _is_kiosk(mode):
                        _report_links(quiz.comparison_id, result.history_id)
                    if result.history_id and not _is_kiosk(mode):
                        _conversation_review_button(result.history_id)
            submit_button.disable()
            ui.run_javascript(
                f'document.getElementById("c{result_box.id}")?.scrollIntoView({{block:"start"}})'
            )

        submit_button = (
            ui.button("채점하고 해설 보기", on_click=submit_answers)
            .props("unelevated")
            .style(f"background: {ACCENT}")
            .classes(_action_classes(mode))
        )
        with ui.row().classes("gap-3"):
            ui.button(
                "비교 화면으로 돌아가기",
                on_click=lambda: ui.navigate.to(comparison_url),
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
        ui.label("다시 보는 비교 기록").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label(
            "이 브라우저에서 만든 비교 기록이에요. 브라우"
            "저를 닫거나 쿠키를 지우면 접근이 종료될 수 "
            "있어요."
            if get_settings().public_mode
            else "함께 사용하는 비교 기록이에요. 개인 대화 기록은 여기에 표시하지 않아요."
        ).classes("cb-muted")
        ui.link("퀴즈 결과와 오답 복습", "/learning-history")
        if not records:
            ui.label("아직 저장된 비교가 없습니다. 문화유산을 선택해 비교를 시작하세요.")
        for record in records[:20]:
            saved = get_saved_comparison(record.id)
            with ui.card().classes("cb-card w-full p-5 gap-2"):
                ui.label(f"{record.left_name} ↔ {record.right_name}").classes("cb-title text-xl")
                ui.label(
                    f"{LEVEL_LABELS[record.level.value]} · {learning_day(record.created_at)}"
                ).classes("cb-muted")
                ui.link(
                    "비교 다시 열기",
                    with_return(
                        f"/compare/{saved.comparison.left.id}/{saved.comparison.right.id}"
                        f"?saved_id={record.id}",
                        f"/comparisons?page={page}",
                    ),
                ).classes("text-blue-800 font-semibold")
        with ui.row().classes("gap-4"):
            if page > 1:
                ui.link("이전 페이지", f"/comparisons?page={page - 1}")
            if len(records) > 20:
                ui.link("다음 페이지", f"/comparisons?page={page + 1}")
            ui.link("새 비교 시작", "/")


@ui.page("/learning-history")
def learning_history_page(page: int = 1, level: str = "all") -> None:
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("나의 학습").classes("cb-title text-3xl").props("role=heading aria-level=1")
        ui.label("관심 있는 이야기와 지금까지의 배움을 함께 살펴봐요.").classes("cb-muted")
        ui.link("설명 방식 설정", "/settings")
        with ui.card().classes("cb-card w-full p-5 gap-3").props("id=learning-profile"):
            learning_intent_editor(_io_bound)
        ui.label("학습 기록과 오답 복습").classes("cb-title text-3xl").props(
            "role=heading aria-level=2"
        )
        ui.label(
            "이 브라우저의 학습 기록" if get_settings().public_mode else "함께 사용하는 학습 기록"
        ).classes("cb-muted")
        ui.label(
            "대화로 복습하기는 이 브라우저에서 채점한 기록"
            "에서만 열려요. 예전 공유 기록은 해설을 읽거"
            "나 퀴즈를 다시 풀어보세요."
        ).classes("cb-muted")
        page = max(1, min(page, 100000))
        level = level if level in LEVEL_LABELS else "all"
        ui.select(
            {"all": "모든 수준", **LEVEL_LABELS}, value=level, label="학습 수준"
        ).on_value_change(
            lambda e: ui.navigate.to("/learning-history?" + urlencode({"level": e.value}))
        )
        reviews = list_learning_reviews(limit=21, offset=(page - 1) * 20, level=level)
        if not reviews:
            ui.label("아직 퀴즈 기록이 없어요. 비교 학습을 마치고 퀴즈를 풀어보세요.")
        for review in reviews[:20]:
            with ui.card().classes("cb-card w-full p-5 gap-3"):
                title = display_name(review["heritage_id"], review["heritage_name"])
                if review["comparison_id"]:
                    try:
                        comp = get_saved_comparison(review["comparison_id"]).comparison
                        title = (
                            display_name(comp.left.id, comp.left.name)
                            + " ↔ "
                            + display_name(comp.right.id, comp.right.name)
                        )
                    except ComparisonNotFoundError:
                        pass
                ui.label(title).classes("cb-title text-xl")
                ui.label(
                    f"{LEVEL_LABELS[review['level']]} · {review['score']}/{review['total']} · "
                    f"{learning_day(review['created_at'])}"
                )
                items = review["result"].get("review_items", [])
                if items:
                    with ui.expansion("오답과 보충 학습 보기").classes("w-full"):
                        _review_cards(items)
                else:
                    for step in review["result"].get("review_steps", []):
                        ui.label(step)
                if review["score"] == review["total"] and review["total"] > 0:
                    ui.label("모든 문항을 맞혔어요. 원문 근거를 다시 확인해 보세요.")
                elif not items and not review["result"].get("review_steps"):
                    ui.label("이 기록에는 문항별 해설이 없어요. 설명을 다시 읽으며 복습해 주세요.")
                if review.get("can_conversation_review"):
                    _conversation_review_button(review["id"])
                if review["comparison_id"]:
                    try:
                        comparison = get_saved_comparison(review["comparison_id"]).comparison
                        if comparison.learning_version < LEARNING_VERSION:
                            ui.label(
                                "이전 학습 기록입니다. 설명 다시 읽기에서 최"
                                "신 근거로 재탐구할 수 있어요."
                            ).classes("cb-muted")
                        ui.link(
                            "설명 다시 읽기",
                            f"/compare/{comparison.left.id}/{comparison.right.id}?saved_id={comparison.saved_id}",
                        )
                        ui.link(
                            "퀴즈 다시 풀기",
                            f"/quiz/{comparison.left.id}/{comparison.right.id}?quiz_id={review['quiz_id']}",
                        )
                        _report_links(comparison.saved_id, review["id"])
                    except ComparisonNotFoundError:
                        ui.label("이 브라우저에서는 이 비교 기록을 열 수 없어요.")
        with ui.row():
            if page > 1:
                ui.link(
                    "이전 기록",
                    "/learning-history?" + urlencode({"page": page - 1, "level": level}),
                )
            if len(reviews) > 20:
                ui.link(
                    "다음 기록",
                    "/learning-history?" + urlencode({"page": page + 1, "level": level}),
                )
        ui.link("비교 기록 모아보기", "/comparisons")
        ui.link("학습 기록 보관·삭제 안내", "/data-policy")


@ui.page("/sources")
def source_catalogue_page():
    from culturebridge.services.material_review_service import material_review
    from culturebridge.services.open_record_service import AVAILABLE_OPEN_RECORDS
    from culturebridge.services.source_registry_service import source_overview

    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-4 py-10"):
        ui.label("학습에 사용하는 공식 자료").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label(
            "공식 원문과 연결 상태, 한국어 이름·이용 조건의 확인 상태를 살펴봐요. "
            "자료를 불러왔다고 역사적 해석이 정확하거나 재배포가 허용된 것은 아니에요."
        ).classes("cb-muted")
        rows = source_overview()
        checklist = {row["id"]: row for row in material_review()}
        ui.link("25개 자료 검토표 다운로드", "/api/material-review?format=md")
        ready = sum(r["connection_status"] == "fresh" for r in rows)
        ui.label(f"연결 확인 {ready}개 · 전체 등록 {len(rows)}개").classes("cb-muted")
        statuses = {
            "fresh": "자료 연결 확인",
            "stale": "최신 자료 확인 필요",
            "unavailable": "연결 보류",
            "not_checked": "자료 연결 확인 전",
        }
        usage = {
            "pending": "이용 허용 범위 확인 중",
            "reviewed": "이용 조건 검토 내역 제공",
            "restricted": "이용 제한 자료",
        }
        for row in rows:
            with ui.card().classes("cb-card w-full p-4 gap-2"):
                ui.label(row["korean_name"] + " (" + row["name"] + ")").classes("cb-title text-lg")
                ui.label(display_country(row["country"]) + " · " + row["organization"])
                ui.label(statuses.get(row["connection_status"], row["connection_status"]))
                ui.label(
                    "한국어 이름: "
                    + ("검토된 명칭" if row["name_status"] == "reviewed" else "학습용 안내명")
                    + " · "
                    + usage[row["usage_status"]]
                ).classes("cb-muted")
                if row["note"]:
                    ui.label(row["note"])
                if row["id"] in checklist:
                    checked = checklist[row["id"]]
                    with ui.expansion("이 자료의 검토 항목").classes("w-full"):
                        ui.label(checked["name_check"] + " · " + checked["explanation_check"])
                        ui.label(checked["desk_review"] + " · " + checked["desk_review_date"])
                        ui.label(checked["name_finding"])
                        ui.label(checked["scope_check"] + " · " + checked["scope_note"])
                        ui.label(checked["policy_note"])
                        ui.label(
                            checked["ai_permission"] + " · " + checked["translation_permission"]
                        )
                        ui.link("기관 이용 조건 참고", checked["policy_url"], new_tab=True)
                        ui.label(checked["classroom_usage"]["context"]).classes("cb-muted")
                        for purpose in checked["classroom_usage"]["purposes"].values():
                            ui.label(purpose["label"] + ": " + purpose["reason"])
                identity = row["id"].split(":", 1)[1]
                if identity in AVAILABLE_OPEN_RECORDS:
                    ui.link("다른 공식 기록도 함께 읽어요", "/sources/open/" + identity)
                ui.link("공식 원문 보기", row["source_url"], new_tab=True)
                if (
                    row["usage_status"] != "restricted"
                    and row["connection_status"] != "unavailable"
                ):
                    ui.link("이 유산 알아보기", "/discover/official/" + row["id"].split(":", 1)[1])


@ui.page("/sources/open/{identity}")
async def open_record_page(identity: str):
    from culturebridge.services.open_record_service import AVAILABLE_OPEN_RECORDS, fetch_open_record

    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-4 py-10"):
        ui.link("← 공식 자료 목록으로", "/sources")
        ui.label("다른 공식 기록도 함께 읽어요").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        if identity not in AVAILABLE_OPEN_RECORDS:
            ui.label("아직 연결하지 않은 추가 기록이에요.")
            return
        try:
            record = await run.io_bound(fetch_open_record, identity)
        except OfficialServiceError as exc:
            ui.label(str(exc))
            ui.link("이 유산 학습으로 돌아가기", "/discover/official/" + identity)
            return
        ui.label(record["scope"])
        language = {"fr": "프랑스어", "en": "영어"}[record["language"]]
        ui.label(record["organization"] + " · 원문 언어: " + language).classes("cb-muted")
        if record["guidance"]:
            ui.label(record["guidance"])
        with ui.card().classes("cb-card w-full p-5 gap-3"):
            for label, value in record["fields"].items():
                ui.label(label).classes("cb-title text-lg")
                ui.label(value).classes("whitespace-pre-wrap")
        ui.label("출처: " + record["attribution"])
        ui.link("공식 기록 확인", record["source_url"], new_tab=True)
        ui.link("공개 데이터 이용 조건", record["license_url"], new_tab=True)
        for note in record["notices"]:
            ui.label(note).classes("cb-muted")
        ui.link("이 유산 계속 학습하기", "/discover/official/" + identity)


@ui.page("/courses")
def courses_page():
    from culturebridge.services.course_service import list_courses
    from culturebridge.services.learning_path_service import personalized_courses
    from culturebridge.ui.heritage_art import course_art

    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("함께 배우는 문화유산").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label("목표를 정하고, 두 유산을 읽고, 퀴즈와 복습으로 마무리하는 대표 코스예요.")
        ui.label(
            "5개 코스는 학습 예시입니다. 전체 25개 자"
            "료는 홈 검색과 개별 탐구에서 계속 이용할 수"
            " 있어요."
        ).classes("cb-muted")
        ui.label("삽화는 학습 주제를 표현한 것으로, 실제 유산의 모습과 다를 수 있어요.").classes(
            "cb-art-caption"
        )
        courses, personalized = personalized_courses(list_courses())
        if personalized:
            ui.label(
                "관심사와 맞닿은 코스를 먼저 보여드려요. 다른 코스도 자유롭게 선택할 수 있어요."
            ).classes("cb-muted")
        with ui.element("div").classes("cb-course-grid"):
            for index, course in enumerate(courses, 1):
                with ui.card().classes("cb-card cb-course-card w-full"):
                    ui.html(course_art(course["id"])).classes("cb-course-art")
                    with ui.column().classes("cb-course-body w-full"):
                        ui.label(f"배움의 여정 {index:02d}").classes("cb-course-number")
                        ui.label(course["title"]).classes("cb-title text-xl").props(
                            "role=heading aria-level=2"
                        )
                        ui.label(
                            f"{LEVEL_LABELS[course['level']]} 권장 · 약 {course['minutes']}분"
                        ).classes("cb-muted text-sm")
                        ui.label(course["left_name"] + " ↔ " + course["right_name"])
                        ui.label(course["objective"]).classes("cb-muted")
                        ui.link("학습 코스 살펴보기 →", "/courses/" + course["id"])
        ui.link("문화유산 찾아보기", "/")


@ui.page("/courses/{course_id}")
def course_detail_page(course_id: str, level: str = ""):
    from culturebridge.services.course_service import (
        CourseNotFoundError,
        course_progress,
        get_course,
        start_course,
    )
    from culturebridge.ui.heritage_art import course_art

    _base_styles()
    _header()
    try:
        course = get_course(course_id)
        learning_level = LearningLevel(level or course["level"])
    except (CourseNotFoundError, ValueError):
        _error_page("학습 코스 또는 수준을 찾을 수 없습니다.", "web")
        return
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.link("← 학습 코스 목록", "/courses")
        ui.label(course["title"]).classes("cb-title text-3xl").props("role=heading aria-level=1")
        ui.label(course["left_name"] + " ↔ " + course["right_name"]).classes("text-xl")
        ui.label(f"권장 학습 시간: 약 {course['minutes']}분 · {GOAL_LABELS[course['goal']]}")
        with ui.card().classes("cb-card w-full p-5 gap-3"):
            ui.label("오늘의 학습 목표").classes("cb-title text-xl")
            ui.label(course["objective"])
            selected = ui.select(
                LEVEL_LABELS, value=learning_level.value, label="설명 수준"
            ).classes("w-full")
            start_actions = ui.row().classes("w-full")
            learning_steps(0)
            for index, activity in enumerate(course["activities"], 1):
                ui.label(f"{index}. {activity}")
            ui.label("마무리 질문: " + course["reflection"])
            ui.label(
                "시작하면 양쪽 원문과 목표 근거를 확인해요. "
                "자료가 부족하면 비교를 보류해요. 원문 이용 "
                "조건과 한국어 풀이 검토는 별도로 필요합니다."
            ).classes("cb-muted")
            status = ui.column().classes("w-full").props("role=status aria-live=polite")

            async def begin():
                start_button.disable()
                status.clear()
                with status:
                    ui.label("공식 자료를 확인하고 비교·퀴즈를 준비하고 있어요…")
                    ui.spinner()
                try:
                    result = await _io_bound(start_course, course_id, selected.value)
                    comp = result["comparison"]
                    return_to = "/courses/" + course_id + "?" + urlencode({"level": selected.value})
                    ui.navigate.to(
                        with_return(
                            f"/compare/{comp['left']['id']}/{comp['right']['id']}?saved_id={comp['saved_id']}",
                            return_to,
                        )
                    )
                except (OfficialServiceError, ValueError, sqlite3.Error, OperationBusyError):
                    status.clear()
                    with status:
                        ui.label(
                            "현재 양쪽 자료나 학습 근거를 준비하지 못했어"
                            "요. 잠시 후 다시 시작하거나 홈에서 다른 유"
                            "산을 선택해 주세요."
                        )
                        ui.link("다른 유산 찾아보기", "/")
                finally:
                    start_button.enable()

            with start_actions:
                start_button = ui.button("이 코스로 학습 시작", on_click=begin).classes("cb-action")
        ui.html(course_art(course_id)).classes("cb-course-banner")
        ui.label("학습 주제를 표현한 창작 삽화 · 실제 유산의 모습이나 복원도가 아니에요.").classes(
            "cb-art-caption"
        )
        progress = course_progress(course_id)
        if progress:
            ui.label("이 브라우저의 코스 학습 기록").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
        for item in progress:
            with ui.card().classes("cb-card w-full p-4 gap-2"):
                labels = {
                    "comparison_ready": "비교 준비됨",
                    "quiz_ready": "퀴즈 준비됨",
                    "review_ready": "퀴즈 제출 완료 · 복습하기",
                }
                ui.label(LEVEL_LABELS[item["level"]] + " · " + labels[item["status"]])
                root = f"{item['left_id']}/{item['right_id']}"
                ui.link(
                    "비교 이어 보기",
                    with_return(
                        "/compare/" + root + "?saved_id=" + item["comparison_id"],
                        "/courses/" + course_id + "?level=" + item["level"],
                    ),
                )
                if item["quiz_id"]:
                    ui.link(
                        "퀴즈·복습으로",
                        with_return(
                            "/quiz/"
                            + root
                            + "?quiz_id="
                            + item["quiz_id"]
                            + "&level="
                            + item["level"],
                            "/courses/" + course_id + "?level=" + item["level"],
                        ),
                    )
                if item["result"]:
                    ui.label(f"점수: {item['result']['score']} / {item['result']['total']}")
                    ui.link("오답과 보충 활동", "/learning-history")
                _report_links(item["comparison_id"], item["history_id"])


@ui.page("/data-policy")
def data_policy_page():
    from culturebridge.services.data_retention_service import delete_session_records

    _base_styles()
    _header()
    settings = get_settings()
    with ui.column().classes("cb-shell gap-4 py-10"):
        ui.label("학습 기록 보관과 삭제").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label(
            "대화·관심사·학습 목표·내가 적은 설명·설명 설정·"
            "이해도 검토 기록·비교 결과·퀴즈 답안·오답 복습을"
            " 현재 브라우저에 연결해 저장해요. 계정 로그"
            "인 방식이 아니므로 쿠키를 지우거나 다른 브라"
            "우저를 쓰면 이전 기록에 접근하지 못할 수 있"
            "어요."
        )
        if not settings.public_mode:
            ui.label(
                "현재 환경에서는 비교·퀴즈 기록을 함께 열람할"
                " 수 있어요. 개인 대화와 이해도 기록은 브라"
                "우저별로 분리해요. 파일 저장과 정리 수정·삭"
                "제는 기록을 만든 브라우저에서만 할 수 있어요"
                "."
            ).props("role=note")
        ui.label(
            "자유 질문과 공식 원문 일부는 AI 기능을 사"
            "용할 때 Gemini로 전달될 수 있어요. 이"
            "름·연락처·민감한 개인정보는 질문에 입력하지 "
            "마세요."
        )
        ui.label(
            f"기록은 {settings.record_retention_days}일이 지나면 자동 삭제 대상이 돼요."
            if settings.retention_enabled
            else "현재는 기록이 자동으로 삭제되지 않아요."
        )
        ui.label(
            f"자동 백업: {settings.maintenance_interval_hours}시간 간격 · "
            f"최근 {settings.backup_keep}개 보관"
            if settings.maintenance_enabled
            else "현재는 백업 사본이 자동으로 만들어지지 않아요."
        )
        ui.label(
            "아래 삭제는 이 브라우저의 대화·이해도·저장 "
            "비교·퀴즈·학습 결과에 적용돼요. 공용 공식 "
            "자료와 다른 브라우저의 기록은 유지돼요. 삭제"
            "한 기록은 되돌릴 수 없어요. 기존 백업 사본"
            "은 관리자 보관 주기에 따라 별도로 만료됩니다"
            "."
        ).classes("cb-muted")
        with ui.dialog() as dialog, ui.card():
            ui.label("이 브라우저의 학습 기록을 삭제할까요?")

            async def confirm_delete():
                try:
                    result = await _io_bound(delete_session_records)
                    ui.notify(
                        f"비교 {result['comparisons']}개·퀴즈 {result['quizzes']}개·"
                        f"학습 결과 {result['history']}개·대화 {result['conversations']}개와 "
                        "학습 이해도 기록을 삭제했습니다."
                    )
                    dialog.close()
                except (ValueError, OperationBusyError):
                    ui.notify("현재 학습 작업이 끝난 뒤 다시 시도해 주세요.", type="warning")

            ui.button("삭제", on_click=confirm_delete).props("color=negative")
            ui.button("취소", on_click=dialog.close).props("flat")
        ui.button("이 브라우저의 학습 기록 삭제", on_click=dialog.open).props(
            "outline color=negative"
        )
        ui.link("학습 기록으로", "/learning-history")


@ui.page("/official")
def official_search_page(
    q: str = "석굴암",
    level: str = "beginner",
    auto: bool = False,
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
) -> None:
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("한국 문화유산 둘러보기").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label(
            "국가유산청의 설명으로 우리 문화유산을 만나보세요. 원문 출처도 함께 확인할 수 있어요."
        )
        search = ui.input(label="국가유산 이름", value=q[:100]).props("outlined maxlength=100")

        async def submit_search() -> None:
            query = (search.value or "").strip()
            if not 1 <= len(query) <= 100:
                ui.notify("검색어를 1~100글자로 입력해 주세요.", color="warning")
                return
            search_button.disable()
            results.clear()
            try:
                response = await _io_bound(search_official_heritages, query)
            except OfficialServiceError as exc:
                with results:
                    ui.label(str(exc)).props("role=alert")
                return
            finally:
                search_button.enable()
            with results:
                ui.label(f"총 {response.total}건 · 첫 페이지 최대 10건 표시")
                if not response.items:
                    ui.label("이 이름으로 찾은 세계유산이 없어요. 다른 이름으로 검색해 주세요.")
                for item in response.items:
                    with ui.card().classes("cb-card w-full p-5 gap-2"):
                        ui.label(item.name).classes("cb-title text-xl")
                        ui.label(f"{item.designation} · {item.region} {item.city}")
                        ui.link(
                            "공식 설명 보기",
                            with_return(
                                f"/official/{item.kind_code}/{item.asset_number}/{item.region_code}?level={_learning_level(level).value}&comparison_scope={comparison_scope.value}",
                                "/official?"
                                + urlencode(
                                    {
                                        "q": query,
                                        "level": level,
                                        "auto": "1",
                                        "comparison_scope": comparison_scope.value,
                                    }
                                ),
                            ),
                        )

        search_button = ui.button("문화유산 찾기", on_click=submit_search).classes("cb-action")
        search.on("keydown.enter", submit_search)
        results = ui.column().classes("w-full gap-4").props("role=status aria-live=polite")
        ui.link("비교 학습 시작 화면", "/")
        if auto and q.strip():
            _restore_results(submit_search)


@ui.page("/official/{kind}/{number}/{region}")
async def official_detail_page(
    kind: str,
    number: str,
    region: str,
    level: str = "beginner",
    return_to: str = "",
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
    mode: str = "web",
) -> None:
    _base_styles()
    _page_header(mode)
    learning_level = _learning_level(level)
    try:
        document = await _io_bound(get_official_document, kind, number, region)
    except (OfficialServiceError, OfficialDocumentNotFoundError, ValueError):
        _error_page(
            "공식 자료를 불러올 수 없습니다. 조회 코드를 확인하거나 다시 시도해 주세요.", mode
        )
        return
    except sqlite3.Error:
        _error_page("공식 자료를 저장할 수 없습니다. 잠시 후 다시 시도해 주세요.", mode)
        return
    with ui.column().classes(f"cb-shell gap-5 py-10 {'cb-kiosk' if _is_kiosk(mode) else ''}"):
        back_search = search_return(
            return_to,
            "/official?"
            + urlencode(
                {
                    "q": document.name,
                    "level": learning_level.value,
                    "auto": "1",
                    "comparison_scope": comparison_scope.value,
                }
            ),
        )
        back_search = (
            _home_route(mode)
            if _is_kiosk(mode)
            else search_level(back_search, learning_level.value)
        )
        _return_button(back_search, mode=mode)
        with ui.column().classes("w-full gap-2"):
            ui.label(document.name).classes("cb-title text-3xl").props(
                "role=heading aria-level=1"
            ).props("role=heading aria-level=1")
            ui.label(f"{document.designation} · {document.period} · {document.address}")
            if document.stale:
                ui.label("갱신이 필요한 자료입니다.").classes("text-orange-800")
        ui.toggle(LEVEL_LABELS, value=learning_level.value).on_value_change(
            lambda e: ui.navigate.to(
                with_return(
                    _route(
                        f"/official/{kind}/{number}/{region}?level={e.value}&comparison_scope={comparison_scope.value}",
                        mode,
                    ),
                    search_level(back_search, e.value),
                )
            )
        ).props('aria-label="설명 학습 수준"')
        with ui.card().classes("cb-card w-full p-6 gap-3"):
            _lesson_content(official_source(document), learning_level)
        ui.link("국가유산청 원문 보기", str(document.source_url), new_tab=True)
        ui.button(
            "함께 살펴볼 문화유산을 찾아요",
            on_click=lambda: ui.navigate.to(
                with_return(
                    _route(
                        f"/discover/khs/{kind}:{number}:{region}?level={learning_level.value}&"
                        + _goal_query(*_settings_from_return(return_to), comparison_scope),
                        mode,
                    ),
                    back_search,
                )
            ),
        ).classes("cb-action")
        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("이 유산은 어디에 있을까요?").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            ui.label("공식 위치를 확인하고 지도에서 살펴보세요.")
            location_box = ui.column().classes("w-full gap-2").props("role=status aria-live=polite")

            async def load_location() -> None:
                location_button.disable()
                location_box.clear()
                try:
                    location = await _io_bound(get_official_location, kind, number, region)
                except OfficialDocumentNotFoundError:
                    with location_box:
                        ui.label("일치하는 공식 위치 자료가 없습니다.")
                    return
                except (OfficialServiceError, sqlite3.Error):
                    with location_box:
                        ui.label("위치정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
                    return
                finally:
                    location_button.enable()
                with location_box:
                    ui.label(location.location)
                    if location.stale:
                        ui.label("연결 실패로 이전 위치 자료를 표시합니다. 갱신이 필요합니다.")
                    ui.link("위치 자료 출처", str(location.source_url), new_tab=True)
                    if location.latitude is not None and location.longitude is not None:
                        ui.link("위도·경도 출처", str(location.geographic_source_url), new_tab=True)
                        ui.link(
                            "지도에서 위치 보기 (OpenStreetMap)",
                            "https://www.openstreetmap.org/?mlat="
                            + str(location.latitude)
                            + "&mlon="
                            + str(location.longitude)
                            + "#map=16/"
                            + str(location.latitude)
                            + "/"
                            + str(location.longitude),
                            new_tab=True,
                        )
                    else:
                        ui.label("유효한 위도·경도가 없어 외부 지도 링크를 표시하지 않습니다.")

            location_button = ui.button("위치 확인하기", on_click=load_location).classes(
                "cb-action"
            )
        if (kind, number, region) == SEOKGURAM_CODES:
            ui.label(
                "석굴암에 관해 질문하면 이 원문을 답변 근거로 참고해요. "
                "AI 설명은 원문과 함께 확인해 주세요."
            )
            ui.link(
                "석굴암 비교 학습",
                with_return(
                    _route(
                        f"/explore/seokguram?level={learning_level.value}&comparison_scope={comparison_scope.value}",
                        mode,
                    ),
                    back_search,
                ),
            )
        ui.link("공식 자료 다시 검색", back_search)


@ui.page("/unesco")
def unesco_page(
    q: str = "",
    level: str = "beginner",
    auto: bool = False,
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
) -> None:
    from culturebridge.ui.heritage_art import heritage_art

    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("세계유산 둘러보기").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        with (
            ui.element("section")
            .classes("cb-world-banner")
            .props('aria-label="세계유산 학습 안내"')
        ):
            with ui.column().classes("gap-1"):
                ui.label("서로 다른 모습, 함께 읽는 역사").classes("cb-title text-xl")
                ui.label("탑과 궁전, 성당까지. 이름을 찾아 유산의 이야기를 만나보세요.").classes(
                    "cb-muted"
                )
                ui.label("유형을 표현한 창작 삽화 · 실제 유산 사진이 아니에요.").classes(
                    "cb-art-caption"
                )
            ui.html(heritage_art(panoramic=True))
        ui.label(
            "한글 별칭·국가명과 공식 영문 이름으로 검색합니다. 등재연도는 건립연도가 아닙니다."
        )
        ui.link("자료 출처와 이용 안내", UNESCO_TERMS_URL, new_tab=True)
        ui.label("유네스코 등재 정보의 출처와 자료 이용 조건을 함께 확인해 주세요.")
        query = (
            ui.input(
                label="유산 이름·국가·등재번호",
                value=q[:100],
                placeholder="예: 타지마할, 호류지, 일본, 660",
            )
            .props("outlined clearable maxlength=100")
            .classes("w-full")
        )
        ui.label("한글 별칭: 석굴암·불국사·호류지·실크로드·대안탑 / 국가명: 한국·일본·중국")
        try:
            suggestion_index = get_unesco_suggestions(limit=2000)
        except (OfficialServiceError, sqlite3.Error):
            suggestion_index = []
        query.set_autocomplete([item.value for item in suggestion_index])
        suggestions = (
            ui.column().classes("w-full gap-1").props('role=group aria-label="검색어 제안"')
        )

        async def load(refresh: bool = False) -> None:
            nonlocal suggestion_index
            button.disable()
            refresh_button.disable()
            suggestions.clear()
            results.clear()
            try:
                response = await _io_bound(
                    search_unesco, (query.value or "")[:100], refresh=refresh
                )
                suggestion_index = await _io_bound(get_unesco_suggestions, "", 2000)
                query.set_autocomplete([item.value for item in suggestion_index])
            except OfficialServiceError as exc:
                with results:
                    ui.label(str(exc))
                    ui.label("세계유산 목록을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.")
                return
            except sqlite3.Error:
                with results:
                    ui.label("목록을 저장하거나 불러오지 못했습니다. 다시 시도해 주세요.")
                return
            finally:
                button.enable()
                refresh_button.enable()
            with results:
                ui.label(
                    f"검색 결과 {response.total}건"
                    + (" · 처음 20건 표시" if response.total > 20 else "")
                )
                if not response.records:
                    ui.label(
                        "이 이름으로 찾은 세계유산이 없어요. 다른 이"
                        "름이나 국가명으로 검색해 보세요."
                    ).props("role=status")
                    ui.link(
                        "개별 문화유산까지 통합 검색하기",
                        home_context(
                            q=query.value or "", level=level, comparison_scope=comparison_scope
                        ),
                    )
                ui.link("수집한 공식 데이터 출처", response.feed_source_url, new_tab=True)
                ui.link(
                    "DataHub 데이터셋·이용 조건 (CC BY-SA 4.0)"
                    if response.source_format == "json"
                    else "세계유산 목록 이용 조건",
                    response.license_url,
                    new_tab=True,
                )
                if response.stale:
                    ui.label("연결 실패로 이전 자료를 표시합니다. 갱신이 필요합니다.")
                for record in response.records:
                    with ui.card().classes("cb-card w-full p-5"):
                        ui.link(
                            display_name("unesco:" + record.id, record.name),
                            str(record.source_url),
                            new_tab=True,
                        )
                        ui.label(display_country(record.countries))
                        ui.label(f"등재연도 {record.inscription_year} · 등재번호 {record.id}")
                        ui.link(
                            "이 세계유산 알아보기",
                            with_return(
                                f"/discover/unesco/{record.id}?level={_learning_level(level).value}&comparison_scope={comparison_scope.value}",
                                "/unesco?"
                                + urlencode(
                                    {
                                        "q": query.value or "",
                                        "level": level,
                                        "auto": "1",
                                        "comparison_scope": comparison_scope.value,
                                    }
                                ),
                            ),
                        )
                if response.source_format == "json":
                    ui.label("출처: UNESCO · CC BY-SA 4.0")
                else:
                    copyright_notice = (
                        "Copyright © 1992 - 2026 UNESCO/World Heritage Centre. All rights reserved."
                    )
                    ui.label(copyright_notice)
                ui.link("UNESCO World Heritage Centre", "https://whc.unesco.org", new_tab=True)

        async def search_data() -> None:
            await load()

        async def choose_suggestion(value: str) -> None:
            query.set_value(value)
            await load()

        def render_suggestions() -> None:
            suggestions.clear()
            term = normalize_search(query.value or "")
            if not term:
                return
            options = [item for item in suggestion_index if term in normalize_search(item.value)]
            options.sort(
                key=lambda item: (
                    normalize_search(item.value) != term,
                    not normalize_search(item.value).startswith(term),
                )
            )
            with suggestions:
                for item in options[:8]:
                    ui.button(
                        item.label,
                        on_click=lambda value=item.value: choose_suggestion(value),
                    ).props("flat no-caps align=left").classes("w-full cb-action text-blue-900")

        query.on_value_change(lambda _: render_suggestions())
        query.on("keydown.enter", search_data)

        async def refresh_data() -> None:
            await load(refresh=True)

        with ui.row().classes("gap-3 flex-wrap"):
            button = ui.button("세계유산 찾기", on_click=search_data).classes("cb-action")
            refresh_button = (
                ui.button("최신 목록 확인하기", on_click=refresh_data)
                .classes("cb-action")
                .props("outline")
            )
        results = ui.column().classes("w-full gap-3").props("role=status aria-live=polite")
        ui.link("처음으로", "/")
        if auto:
            _restore_results(load)


@ui.page("/research/{left_id}/{right_id}")
async def research_page(
    left_id: str,
    right_id: str,
    level: str = "beginner",
    mode: str = "web",
    goal: str = "compare",
    goal_text: str = "",
    amount: str = "standard",
    return_to: str = "",
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
) -> None:
    _base_styles()
    _page_header(mode)
    learning_level = _learning_level(level)
    if left_id == right_id:
        _error_page("서로 다른 문화유산을 선택해 주세요.", mode)
        return
    with ui.column().classes("cb-shell gap-5 py-10"):
        _return_button(
            return_to,
            _route(
                f"/explore/{left_id}?level={learning_level.value}&"
                + _goal_query(goal, goal_text, amount, comparison_scope),
                mode,
            ),
            "추천 화면으로",
            mode,
        )
        ui.label("두 문화유산 함께 알아보기").classes("cb-title text-3xl").props(
            "role=heading aria-level=1"
        )
        ui.label(SCOPE_LABELS[comparison_scope.value]).classes("font-semibold")
        ui.label("두 유산의 이야기를 읽고 시대·모양·재료·종교적 배경을 함께 살펴봐요.")
        panel = ui.column().classes("w-full gap-3").props("role=status aria-live=polite")
        with panel:
            ui.label("두 유산의 이야기를 준비하고 있어요…")
            ui.spinner()
        client = ui.context.client
        await client.connected()
        if client.is_deleted:
            return
        try:
            state = await _io_bound(
                run_exploration,
                {
                    "heritage_id": left_id,
                    "comparison_id": right_id,
                    "level": learning_level.value,
                    "goal": _goal(goal).value,
                    "goal_text": goal_text[:200],
                    "amount": _amount(amount).value,
                    "comparison_scope": comparison_scope.value,
                },
            )
        except OperationBusyError as exc:
            panel.clear()
            _error_page(str(exc), mode)
            return
        except (HeritageNotFoundError, sqlite3.Error, ValueError):
            panel.clear()
            _error_page(
                "선택한 비교 범위에서 탐구 자료를 확인하지 못했습니다. "
                "한국의 유산과 비교하려면 ‘국내 문화유산과 비교’를 선택해 주세요.",
                mode,
            )
            return
        panel.clear()
        with panel:
            ui.label(
                "공식 설명에서 찾은 내용을 살펴봐요. 자료가 부족한 부분은 판단을 보류해요."
            ).classes("cb-muted")
            learning_steps(0, state["curriculum"])
            for notice in state["comparison"]["learning_notices"]:
                ui.label(service_text(notice)).classes("cb-muted")
            with ui.expansion("자료를 찾고 확인한 과정").classes("w-full"):
                ui.label(state["verification_note"])
                for step in state["execution_trace"]:
                    ui.label(readable_trace(step))
                ui.label(f"추가 자료 확인: {state['retry_count']}회")
            _collected_source_cards(
                [CollectedSource.model_validate(s) for s in state["collected_sources"]],
                learning_level,
            )
            ui.label("두 유산의 핵심 특징").classes("cb-title text-2xl").props(
                "role=heading aria-level=2"
            )
            _extracted_field_cards(
                [ExtractedField.model_validate(f) for f in state["extracted_fields"]],
                learning_level,
            )
            with ui.expansion("퀴즈 준비 안내").classes("w-full"):
                ui.label(state["quiz_notice"])
            if not state["quiz"]:
                ui.label("현재 자료로는 퀴즈를 준비하지 못했어요. 위 안내를 확인해 주세요.")
            if state["quiz"]:
                ready_quiz_id = state["quiz"]["quiz_id"]
                ui.button(
                    "배운 내용 퀴즈 풀기",
                    on_click=lambda: ui.navigate.to(
                        with_return(
                            _route(f"/quiz/{left_id}/{right_id}?quiz_id={ready_quiz_id}", mode),
                            return_to,
                        )
                    ),
                ).classes(_action_classes(mode))
            record_id = state["comparison"]["saved_id"]
            ui.button(
                "유사점과 차이점 알아보기",
                on_click=lambda: ui.navigate.to(
                    with_return(
                        _route(f"/compare/{left_id}/{right_id}?saved_id={record_id}", mode),
                        return_to,
                    )
                ),
            ).classes(_action_classes(mode))
            ui.button("처음으로", on_click=lambda: ui.navigate.to(_home_route(mode))).classes(
                _action_classes(mode)
            )


def register_pages() -> None:
    """Importing this module registers pages; this function documents that intent."""


@ui.page("/discover/{provider}/{identity}")
async def autonomous_page(
    provider: str,
    identity: str,
    level: str = "beginner",
    goal: str = "compare",
    goal_text: str = "",
    amount: str = "standard",
    return_to: str = "",
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
    mode: str = "web",
):
    _base_styles()
    _page_header(mode)

    def discovery_link(label, destination):
        if _is_kiosk(mode) and urlsplit(destination).path in {"/", "/domestic", "/official"}:
            destination = _home_route(mode)
        return ui.link(label, _route(destination, mode))

    try:
        if provider == "unesco":
            target = OfficialTarget(provider=provider, record_id=identity)
        elif provider == "official":
            target = OfficialTarget(provider=provider, official_id=identity)
        else:
            kind, number, region = identity.split(":")
            target = OfficialTarget(provider=provider, kind=kind, number=number, region=region)
        request = AutonomousRequest(
            target=target,
            level=_learning_level(level),
            goal=_goal(goal),
            goal_text=goal_text[:200],
            amount=_amount(amount),
            comparison_scope=comparison_scope,
        )
    except ValueError:
        _error_page("선택한 문화유산을 찾지 못했어요. 검색에서 다시 선택해 주세요.", mode)
        return
    with ui.column().classes(f"cb-shell gap-5 py-10 {'cb-kiosk' if _is_kiosk(mode) else ''}"):
        _return_button(
            return_to,
            _home_route(mode)
            if _is_kiosk(mode)
            else home_context(
                level=level,
                goal=goal,
                goal_text=goal_text,
                amount=amount,
                comparison_scope=comparison_scope,
            ),
            mode=mode,
        )
        title = (
            ui.label("함께 살펴볼 문화유산을 찾아요")
            .classes("cb-title text-3xl")
            .props("role=heading aria-level=1")
        )
        ui.label(SCOPE_LABELS[comparison_scope.value]).classes("font-semibold")
        _comparison_entry(
            level=level,
            comparison_scope=comparison_scope,
            domestic_url=_route(
                with_return(
                    f"/discover/{provider}/{identity}?level={level}&"
                    + _goal_query(goal, goal_text, amount, ComparisonScope.DOMESTIC),
                    scope_return(
                        return_to
                        or home_context(level=level, goal=goal, goal_text=goal_text, amount=amount),
                        ComparisonScope.DOMESTIC,
                    ),
                ),
                mode,
            ),
        )
        panel = ui.column().classes("w-full gap-3").props("role=status aria-live=polite")
        with panel:
            ui.label("공식 자료를 읽고 비교 후보를 탐색하고 있어요…")
            ui.spinner()
        client = ui.context.client
        await client.connected()
        if client.is_deleted:
            return
        try:
            result = await _io_bound(run_autonomous, request)
        except OperationBusyError as exc:
            panel.clear()
            with panel:
                ui.label(str(exc)).props("role=alert")
                ui.button("다시 시도", on_click=lambda: ui.navigate.to(str(client.request.url)))
            return
        except (ValueError, OfficialServiceError, HeritageNotFoundError, sqlite3.Error):
            panel.clear()
            with panel:
                ui.label(
                    "공식 자료를 확보하거나 탐구를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."
                )
                discovery_link(
                    "검색 결과로 돌아가기",
                    search_return(
                        return_to,
                        home_context(
                            level=level,
                            goal=goal,
                            goal_text=goal_text,
                            amount=amount,
                            comparison_scope=comparison_scope,
                        ),
                    ),
                )
            return
        panel.clear()
        with panel:
            target = result["target"]
            title.set_text(
                learning_title(korean_name(target["id"], target["name"]) or "선택한 유산")
            )
            ui.label("선택한 유산: " + display_name(target["id"], target["name"])).classes(
                "text-lg"
            )
            ui.label(
                "AI가 공식 자료를 읽고 검색 방법을 정했어요."
                if result["used_ai_planner"]
                else "AI 검색 대신 공식 자료의 특징을 바탕으로 찾았어요."
            )
            ui.label(learner_status(result, request.level is LearningLevel.BEGINNER))
            if not result["candidates"]:
                ui.label(
                    "선택한 범위에서 조건에 맞는 근거를 확보하지 "
                    "못해 비교를 보류했어요. 범위를 자동 변경하지"
                    " 않아요."
                ).classes("cb-muted")
                if request.target.provider == "khs":
                    discovery_link(
                        "선택한 유산의 설명 먼저 읽기",
                        with_return(
                            f"/official/{request.target.kind}/{request.target.number}/{request.target.region}"
                            f"?level={level}&comparison_scope={comparison_scope.value}",
                            return_to,
                        ),
                    )
                discovery_link(
                    "학습 목표를 바꾸어 다시 찾기",
                    search_return(
                        return_to,
                        home_context(
                            q=target["name"],
                            level=level,
                            goal=goal,
                            amount=amount,
                            comparison_scope=comparison_scope,
                        ),
                    ),
                )
            ui.label("한국어 이름은 학습용 안내 표기이며, 괄호 안은 공식 영문 이름입니다.").classes(
                "cb-muted text-sm"
            )
            with ui.expansion("자료를 찾고 비교한 과정 보기").classes("w-full"):
                ui.label(result["verification_note"])
                for step in result["execution_trace"]:
                    ui.label(readable_trace(step))
            for candidate in result["candidates"]:
                with ui.card().classes("cb-card w-full p-4"):
                    item = candidate["heritage"]
                    ui.label(display_name(item["id"], item["name"])).classes(
                        "cb-title text-xl"
                    ).style("overflow-wrap:anywhere")
                    ui.label(display_country(item["country"])).classes("cb-muted")
                    ui.label(
                        "여러 유산을 묶은 자료 · 전체 범위로 비교해요"
                        if is_group(item["name"])
                        else "개별 대상 비교 후보 · 원문의 설명 범위를 함께 확인해요"
                    ).classes("cb-muted text-sm")
                    ui.label(
                        readable_reason(
                            candidate.get("criteria", []), request.level is LearningLevel.BEGINNER
                        )
                    )
                    with ui.expansion("추천 이유 자세히 보기"):
                        ui.label(candidate["reason"])
                    discovery_link(
                        "이 유산과 비교하기",
                        with_return(
                            f"/research/{result['target']['id']}/{candidate['heritage']['id']}"
                            f"?level={level}&"
                            + _goal_query(goal, goal_text, amount, comparison_scope),
                            return_to,
                        ),
                    )
            if result["comparison"]:
                comparison = result["comparison"]
                discovery_link(
                    "먼저 살펴본 비교 결과 보기",
                    with_return(
                        f"/compare/{comparison['left']['id']}/{comparison['right']['id']}?saved_id={comparison['saved_id']}",
                        return_to,
                    ),
                )
                if result["quiz"]:
                    discovery_link(
                        "배운 내용 퀴즈 풀기",
                        with_return(
                            f"/quiz/{comparison['left']['id']}/{comparison['right']['id']}?quiz_id={result['quiz']['quiz_id']}",
                            return_to,
                        ),
                    )
                else:
                    ui.label(result["quiz_notice"])
            discovery_link(
                "검색 결과로 돌아가기",
                search_return(
                    return_to,
                    home_context(
                        level=level,
                        goal=goal,
                        goal_text=goal_text,
                        amount=amount,
                        comparison_scope=comparison_scope,
                    ),
                ),
            )
