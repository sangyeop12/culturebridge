import logging
import sqlite3
from urllib.parse import parse_qs, urlencode, urlsplit

from nicegui import run, ui

from culturebridge.agents.autonomous import AutonomousRequest, run_autonomous
from culturebridge.agents.quiz_agent import evaluate_learning_quiz
from culturebridge.agents.workflow import exploration_graph
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
    ComparisonNotFoundError,
    create_saved_comparison,
    get_saved_comparison,
    list_saved_comparisons,
)
from culturebridge.services.curriculum_service import AMOUNT_LABELS, GOAL_LABELS
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
from culturebridge.services.question_service import answer_question
from culturebridge.services.quiz_service import (
    InvalidQuizAttemptError,
    QuizNotFoundError,
    generate_quiz,
    load_quiz,
)
from culturebridge.services.source_claim_service import ClaimTargetMismatchError
from culturebridge.services.subject_service import is_group
from culturebridge.services.unesco_service import (
    UNESCO_TERMS_URL,
    get_unesco_suggestions,
    normalize_search,
    search_unesco,
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
        ui.label("문화유산을 잇고, 배움을 넓히다").classes("text-sm text-blue-100")


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


def _return_button(return_to="", fallback="/", label="검색 결과로", mode="web"):
    destination = search_return(return_to, fallback)
    root = urlsplit(destination).path
    if root == "/comparisons":
        label = "비교 기록으로"
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
        with ui.expansion("부가 기능 · 국내 문화유산과 비교").classes("w-full"):
            ui.label(
                "한국 문화유산끼리 비교하거나 해외 유산을 한국 유산과 비교하고 싶을 때 이용하세요."
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
            "기본 학습 · 해외 문화유산과 비교",
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
                else field.value or "현재 자료에서 해당 항목을 추출하지 못했습니다."
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
    ui.label(lesson.intro).classes("font-semibold")
    ui.label(lesson.notice).classes("cb-muted")
    if level is LearningLevel.ADVANCED:
        ui.label(lesson.original_text or "수집된 원문이 없습니다.").style(
            "white-space: pre-wrap; overflow-wrap: anywhere"
        )
        ui.label(
            "검토할 점: 연대가 건립·재건 중 무엇을 뜻하는지, "
            "주변 건물과 대상이 구분되는지 확인하세요."
        ).classes("cb-muted")
    else:
        for section in lesson.sections:
            ui.label(section.heading).classes("cb-title text-lg")
            ui.label(section.text).style("white-space: pre-wrap; overflow-wrap: anywhere")
            if level is LearningLevel.INTERMEDIATE and section.event:
                ui.label("연대가 가리키는 사건: " + section.event).classes("cb-muted")
            if level is LearningLevel.INTERMEDIATE and section.evidence_quote:
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
            ui.label(labels[source.status]).classes("font-semibold")
            ui.label(source.scope_note).classes("cb-muted")
            if source.retrieved_at:
                ui.label(
                    "자료 조회 시각: " + source.retrieved_at.astimezone().strftime("%Y-%m-%d %H:%M")
                )
            ui.link("공식 자료 페이지", str(source.source_url), new_tab=True)
            ui.link("원본 데이터 보기", str(source.feed_url), new_tab=True)
            if source.license_url:
                ui.link("자료 이용 조건", str(source.license_url), new_tab=True)
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
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-7 py-10"):
        ui.label(SCOPE_LABELS[comparison_scope.value]).classes("cb-title text-xl")
        ui.label(
            "기본 학습 · 한국 밖의 유산을 추천해요."
            if comparison_scope is ComparisonScope.OVERSEAS
            else "부가 기능 · 한국의 유산을 추천해요."
        ).classes("cb-muted")
        _comparison_entry(q, level, comparison_scope, context=lambda: return_context(page))
        ui.link("비교 기록 모아보기", "/comparisons").classes("text-blue-800 font-semibold")
        ui.link("한국 문화유산 둘러보기", "/official").classes("text-blue-800 font-semibold")
        ui.link("세계유산 둘러보기", "/unesco").classes("text-blue-800 font-semibold")
        with ui.column().classes("gap-2"):
            ui.label("하나의 문화유산에서 세계로").classes("cb-title text-4xl")
            ui.label(
                "한국 문화유산과 세계유산을 검색하고, 지원 유산은 비교 학습으로 이어가세요."
            ).classes("cb-muted text-lg")

        with ui.card().classes("cb-card w-full p-6 gap-5"):
            ui.label("1. 학습 수준을 선택하세요").classes("cb-title text-xl")
            level = ui.toggle(
                LEVEL_LABELS,
                value=_learning_level(level).value,
            ).classes("w-full")
            goal = ui.select(GOAL_LABELS, value=_goal(goal).value, label="학습 목표").classes(
                "w-full"
            )
            amount = ui.select(
                AMOUNT_LABELS, value=_amount(amount).value, label="학습 분량"
            ).classes("w-full")
            goal_text = (
                ui.input(
                    label="세부 목표 (선택)",
                    value=goal_text[:200],
                    placeholder="예: 재료와 불교의 관계가 궁금해요",
                )
                .props("maxlength=200")
                .classes("w-full")
            )

            ui.label("2. 문화유산을 검색하세요").classes("cb-title text-xl")
            scope = ui.select(
                {"all": "통합 검색", "korea": "한국 · 국가유산청", "world": "세계 · UNESCO"},
                value=scope if scope in {"all", "korea", "world"} else "all",
                label="검색 범위",
            ).classes("w-full")
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
                "해외 유산은 등록된 한글 별칭·공식 영문 이름·국가명으로 검색하세요."
            ).classes("cb-muted text-sm")
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
                    ui.label("기본 탐구 예제 · 다른 유산은 아래 공식 검색에서 시작하세요").classes(
                        "font-semibold"
                    )
                    items = list_heritages(search.value)
                    if scope.value == "korea":
                        items = [item for item in items if item.country == "대한민국"]
                    if scope.value == "world":
                        items = [item for item in items if item.country != "대한민국"]
                    if not items:
                        ui.label(
                            "등록된 비교 유산은 없습니다. 공식 자료 검색으로 더 찾아보세요."
                        ).classes("cb-muted p-4")
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
                    response = await run.io_bound(search_home, query, selected_scope, page)
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
                            ui.label(notice).props("role=alert")
                        ui.label(
                            "관심 있는 유산을 고르면 함께 살펴볼 유산과 설명을 찾아드려요. "
                            "자료가 부족하면 판단을 보류합니다."
                        )
                        if response.korean is not None:
                            ui.label(
                                f"국가유산청 · 총 {response.korean.total}건 (최대 10건)"
                            ).classes("font-semibold")
                            for item in response.korean.items:
                                with ui.card().classes("cb-card w-full p-4 gap-2"):
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
                                "/official?"
                                + urlencode(
                                    {
                                        "q": query,
                                        "level": level.value,
                                        "comparison_scope": comparison_scope.value,
                                    }
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
                                "/unesco?"
                                + urlencode(
                                    {
                                        "q": query,
                                        "level": level.value,
                                        "comparison_scope": comparison_scope.value,
                                    }
                                ),
                            )
                            ui.link(
                                "UNESCO 데이터 출처·이용 조건",
                                response.world.license_url,
                                new_tab=True,
                            )
                        count = (response.korean.total if response.korean else 0) + (
                            response.world.total if response.world else 0
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
            search_button = ui.button(
                "공식 자료 통합 검색", on_click=lambda: submit_search()
            ).classes("cb-action")
            render_results()
            if auto and q.strip():
                _restore_results(lambda: submit_search(page=max(1, min(page, 10000))))


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
            goal = ui.select(GOAL_LABELS, value="observe", label="체험 목표").classes("w-full")
            amount = ui.select(AMOUNT_LABELS, value="brief", label="체험 분량").classes("w-full")
            with ui.element("div").classes("cb-kiosk-grid w-full gap-5"):
                for item in list_heritages():
                    with ui.card().classes("cb-kiosk-card w-full justify-between p-6 gap-3"):
                        ui.label(item.name).classes("cb-title text-2xl")
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
    if heritage_id.startswith(("khs:", "unesco:")):
        provider, identity = heritage_id.split(":", 1)
        with ui.column().classes("cb-shell py-10"):
            _return_button(return_to, _home_route(mode), mode=mode)
            ui.label("선택한 유산의 설명을 읽고 함께 살펴볼 유산을 찾아드려요.")
            ui.link(
                "함께 살펴볼 유산 찾기",
                with_return(
                    f"/discover/{provider}/{identity}?level={level}&"
                    + _goal_query(goal, goal_text, amount, comparison_scope),
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
            ui.label("문화유산을 찾을 수 없습니다.").classes("cb-title text-2xl")
            ui.button("처음으로", on_click=lambda: ui.navigate.to(_home_route(mode))).classes(
                _action_classes(mode)
            )
            return

        ui.label("함께 알아보면 좋은 문화유산").classes("cb-title text-3xl")
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
                        "/discover/khs/"
                        + ":".join(SEOKGURAM_CODES)
                        + f"?level={level}&"
                        + _goal_query(learning_goal.value, goal_text, amount, comparison_scope),
                        return_to,
                    ),
                )
        ui.label(f"선택한 문화유산: {selected.name}").classes("text-lg font-semibold")
        ui.label(f"학습 수준: {LEVEL_LABELS.get(level, '초급')}").classes("cb-muted")
        ui.label("학습 목표: " + GOAL_LABELS[learning_goal.value])
        ui.label("학습 분량: " + AMOUNT_LABELS[_amount(amount).value])
        if goal_text:
            ui.label("세부 목표: " + goal_text[:200])

        for candidate in candidates:
            with ui.card().classes("cb-card w-full p-6 gap-3"):
                ui.label(candidate.heritage.name).classes("cb-title text-2xl")
                ui.label(f"{candidate.heritage.country} · {candidate.heritage.period}").classes(
                    "cb-muted"
                )
                ui.label(candidate.reason).classes("text-base")
                ui.button(
                    "기본 자료 비교",
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
                left_id, right_id, learning_level, comparison_scope=comparison_scope
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
        _return_button(return_to, recommendation_url, "추천 화면으로", mode)
        with ui.column().classes("gap-1"):
            ui.label("유사점과 차이점 알아보기").classes("cb-title text-3xl")
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
                ui.label("학습 순서: " + " → ".join(result.curriculum))
                ui.label("학습 분량: " + AMOUNT_LABELS[result.amount.value])
                for notice in result.learning_notices:
                    ui.label(notice).classes("cb-muted")
            if saved_id:
                ui.label(
                    "저장 당시의 비교와 출처입니다. 자유 질문은 현재 등록 자료를 사용합니다."
                ).classes("cb-muted")
            if result.saved_id and not _is_kiosk(mode):
                ui.link(
                    "저장된 이 비교 다시 열기",
                    f"/compare/{left_id}/{right_id}?saved_id={result.saved_id}",
                ).classes("text-blue-800")
                ui.link("저장된 비교 목록", "/comparisons").classes("text-blue-800")

        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("공통점 검토 안내" if result.basis == "extracted" else "공통점").classes(
                "cb-title text-2xl"
            )
            for point in result.common_points:
                ui.label(f"• {point}").classes("text-base")
            for common in result.common_evidence:
                ui.label(common.context_note).classes("cb-muted")
                with ui.expansion("공통 후보의 양쪽 원문 근거").classes("w-full"):
                    _extracted_field_cards(
                        [common.left_evidence, common.right_evidence], learning_level
                    )

        if result.collected_sources:
            ui.label("두 유산의 이야기 읽기").classes("cb-title text-2xl")
            ui.label(
                "원문에서 찾은 설명으로 비교했어요. 설명의 뜻과 대상은 추가 확인이 필요해요."
                if result.basis == "extracted"
                else "아래 비교는 기존 검토된 데이터로 작성됐습니다."
            )
            _collected_source_cards(result.collected_sources, learning_level)
        if result.extracted_fields:
            ui.label(
                "원문을 바탕으로 살펴볼 특징"
                if learning_level is LearningLevel.ADVANCED
                else "문화유산의 핵심 특징"
            ).classes("cb-title text-2xl")
            _extracted_field_cards(result.extracted_fields, learning_level)

        ui.label(
            "원문과 별도로 보는 항목별 비교"
            if learning_level is LearningLevel.ADVANCED
            else "항목별 차이"
        ).classes("cb-title text-2xl")
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

        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("설명의 근거 확인하기").classes("cb-title text-2xl")
            if "seokguram" in (left_id, right_id):
                ui.link(
                    "석굴암 원문 읽기",
                    "/official/" + "/".join(SEOKGURAM_CODES),
                    new_tab=True,
                )
            status_label = {
                "verified": "확인됨",
                "needs_review": "추가 확인 필요",
                "insufficient_evidence": "근거 부족",
            }[result.verification_status.value]
            ui.label(status_label).classes("font-bold")
            ui.label(result.verification_note).classes("cb-muted")
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
            ui.label("궁금한 점 질문하기").classes("cb-title text-2xl")
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
                        comparison_id=result.saved_id if result.collected_sources else None,
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
                        for source in answer.sources:
                            ui.link(source.title, str(source.url), new_tab=True)

            ask_button = (
                ui.button("질문하기", on_click=submit_question)
                .props("unelevated")
                .style(f"background: {ACCENT}")
                .classes(_action_classes(mode))
            )

        with ui.card().classes("cb-card w-full p-6 gap-4"):
            ui.label("이 설명은 근거가 있을까요?").classes("cb-title text-2xl")
            if result.collected_sources:
                ui.label("이 비교에 저장된 개별 원문과 대조합니다. AI 판정은 검토 후보입니다.")
            ui.label("한 가지 사실을 입력하세요. 예: 석굴암의 재료는 화강암이다").classes(
                "cb-muted"
            )
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
                    ui.notify("주장을 2~500글자로 입력해 주세요.", color="warning")
                    return
                claim_button.disable()
                try:
                    checked = await run.io_bound(
                        verify_claim,
                        left_id,
                        right_id,
                        claim,
                        comparison_id=result.saved_id if result.collected_sources else None,
                    )
                except (ComparisonNotFoundError, ClaimTargetMismatchError, sqlite3.Error):
                    ui.notify(
                        "주장 검증의 저장 자료를 확인하지 못했습니다. 다시 시도하세요.",
                        color="negative",
                    )
                    return
                finally:
                    claim_button.enable()
                labels = {
                    "verified": "확인됨",
                    "needs_review": "추가 확인 필요",
                    "insufficient_evidence": "근거 부족",
                }
                claim_box.clear()
                with claim_box:
                    ui.label("입력한 주장: " + checked.claim)
                    ui.label(labels[checked.verification_status.value]).classes("cb-title text-xl")
                    ui.label(checked.explanation)
                    if checked.execution_trace:
                        with ui.expansion(f"주장 재검토 기록 · 추가 조회 {checked.retry_count}회"):
                            for step in checked.execution_trace:
                                ui.label(step)
                        _collected_source_cards(checked.collected_sources, learning_level)
                    if checked.unsupported_parts:
                        ui.label("개별 근거가 없는 주장 부분").classes("font-semibold")
                        for part in checked.unsupported_parts:
                            ui.label(part)
                    for entry in checked.evidence:
                        ui.label(
                            {
                                "supports": "지지 후보",
                                "contradicts": "반박 후보",
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
            ).classes(_action_classes(mode))
            ui.button(
                "처음으로",
                on_click=lambda: ui.navigate.to(_home_route(mode)),
            ).classes(_action_classes(mode))


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
            quiz = await run.io_bound(
                generate_quiz, left_id, right_id, learning_level, comparison_id=comparison_id
            )
        else:
            quiz = generate_quiz(left_id, right_id, learning_level, comparison_id=comparison_id)
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
            ui.label("배운 내용 퀴즈로 확인하기").classes("cb-title text-3xl")
            ui.label(f"{LEVEL_LABELS[quiz.level.value]} · {quiz.learning_goal}").classes(
                "text-lg font-semibold"
            )
            ui.label("5개 문항에 모두 답한 뒤 채점하세요.").classes("cb-muted text-lg")
            if quiz.basis == "extracted":
                ui.label(
                    "공식 설명을 읽고 푸는 퀴즈예요. 설명의 뜻은 원문과 함께 더 확인해 주세요."
                )

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

        result_box = ui.column().props("role=status aria-live=polite").classes("w-full gap-3")

        def submit_answers() -> None:
            answers = [radio.value for radio in radios]
            if any(answer is None for answer in answers):
                ui.notify("모든 문항에 답해 주세요.", color="warning")
                return
            try:
                result = evaluate_learning_quiz(quiz.quiz_id, [int(answer) for answer in answers])
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
                    if result.review_steps:
                        ui.label("틀린 문제 다시 살펴보기").classes("cb-title text-xl")
                        for step in result.review_steps:
                            ui.label(step).classes("text-base")
                    if result.evidence:
                        ui.label("정답의 근거 다시 읽기").classes("cb-title text-xl")
                        _extracted_field_cards(result.evidence, learning_level)
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
        ui.label("다시 보는 비교 기록").classes("cb-title text-3xl")
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
        ui.label("한국 문화유산 둘러보기").classes("cb-title text-3xl")
        ui.label(
            "국가유산청의 설명으로 우리 문화유산을 만나보세요. "
            "출처와 조회일도 함께 확인할 수 있어요."
        )
        search = ui.input(label="국가유산 이름", value=q[:100]).props("outlined maxlength=100")
        results = ui.column().classes("w-full gap-4").props("role=status aria-live=polite")

        async def submit_search() -> None:
            query = (search.value or "").strip()
            if not 1 <= len(query) <= 100:
                ui.notify("검색어를 1~100글자로 입력해 주세요.", color="warning")
                return
            search_button.disable()
            results.clear()
            try:
                response = await run.io_bound(search_official_heritages, query)
            except OfficialServiceError as exc:
                with results:
                    ui.label(str(exc)).props("role=alert")
                return
            finally:
                search_button.enable()
            with results:
                ui.label(f"총 {response.total}건 · 첫 페이지 최대 10건 표시")
                if not response.items:
                    ui.label("검색 결과가 없습니다. 다른 이름으로 검색해 주세요.")
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
) -> None:
    _base_styles()
    _header()
    learning_level = _learning_level(level)
    try:
        document = await run.io_bound(get_official_document, kind, number, region)
    except (OfficialServiceError, OfficialDocumentNotFoundError, ValueError):
        _error_page(
            "공식 자료를 불러올 수 없습니다. 조회 코드를 확인하거나 다시 시도하세요.", "web"
        )
        return
    except sqlite3.Error:
        _error_page("공식 자료를 저장할 수 없습니다. 잠시 후 다시 시도하세요.", "web")
        return
    with ui.column().classes("cb-shell gap-5 py-10"):
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
        back_search = search_level(back_search, learning_level.value)
        _return_button(back_search)
        ui.label(document.name).classes("cb-title text-3xl")
        ui.label(f"{document.designation} · {document.period} · {document.address}")
        ui.label(document.notice).props("role=status").classes("cb-muted")
        ui.label(
            f"조회 시각: {document.retrieved_at.astimezone().strftime('%Y-%m-%d %H:%M')} · "
            + ("이전 수집 자료" if document.cached else "새로 수집한 자료")
        )
        if document.stale:
            ui.label("갱신이 필요한 자료입니다.").classes("text-orange-800")
        ui.toggle(LEVEL_LABELS, value=learning_level.value).on_value_change(
            lambda e: ui.navigate.to(
                with_return(
                    f"/official/{kind}/{number}/{region}?level={e.value}&comparison_scope={comparison_scope.value}",
                    search_level(back_search, e.value),
                )
            )
        ).props('aria-label="설명 학습 수준"')
        with ui.card().classes("cb-card w-full p-6 gap-3"):
            _lesson_content(official_source(document), learning_level)
        ui.link("국가유산청 원문 보기", str(document.source_url), new_tab=True)
        with ui.card().classes("cb-card w-full p-6 gap-3"):
            ui.label("이 유산은 어디에 있을까요?").classes("cb-title text-2xl")
            ui.label("UTM-K 좌표를 조회합니다. 보호구역 경계 지도는 별도 서비스입니다.")
            location_box = ui.column().classes("w-full gap-2").props("role=status aria-live=polite")

            async def load_location() -> None:
                location_button.disable()
                location_box.clear()
                try:
                    location = await run.io_bound(get_official_location, kind, number, region)
                except OfficialDocumentNotFoundError:
                    with location_box:
                        ui.label("일치하는 공식 위치 자료가 없습니다.")
                    return
                except (OfficialServiceError, sqlite3.Error):
                    with location_box:
                        ui.label("위치정보를 불러오지 못했습니다. 잠시 후 다시 시도하세요.")
                    return
                finally:
                    location_button.enable()
                with location_box:
                    ui.label(location.location)
                    ui.label(
                        f"{location.coordinate_system} · X {location.projected_x:.3f} / "
                        f"Y {location.projected_y:.3f}"
                    )
                    ui.label(
                        "조회 시각: "
                        + location.retrieved_at.astimezone().strftime("%Y-%m-%d %H:%M")
                    )
                    if location.stale:
                        ui.label("연결 실패로 이전 위치 자료를 표시합니다. 갱신이 필요합니다.")
                    ui.link("위치 자료 출처", str(location.source_url), new_tab=True)
                    if location.latitude is not None and location.longitude is not None:
                        ui.label(
                            f"공식 자료의 위도·경도: {location.latitude:.6f}, "
                            f"{location.longitude:.6f}"
                        )
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
                "이 원문은 석굴암의 Gemini 자유 질문 근거에 포함됩니다. "
                "AI 답변은 검토가 필요합니다."
            )
            ui.link(
                "석굴암 비교 학습",
                with_return(
                    f"/explore/seokguram?level={learning_level.value}&comparison_scope={comparison_scope.value}",
                    back_search,
                ),
            )
        ui.link("공식 자료 다시 검색", f"/official?comparison_scope={comparison_scope.value}")


@ui.page("/unesco")
def unesco_page(
    q: str = "",
    level: str = "beginner",
    auto: bool = False,
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS,
) -> None:
    _base_styles()
    _header()
    with ui.column().classes("cb-shell gap-5 py-10"):
        ui.label("세계유산 둘러보기").classes("cb-title text-3xl")
        ui.label(
            "한글 별칭·국가명과 공식 영문 이름으로 검색합니다. 등재연도는 건립연도가 아닙니다."
        )
        ui.link("자료 출처와 이용 안내", UNESCO_TERMS_URL, new_tab=True)
        ui.label("유네스코 등재 정보의 출처와 자료 이용 조건을 함께 확인하세요.")
        query = (
            ui.input(
                label="유산 이름·국가·등재 ID",
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
        results = ui.column().classes("w-full gap-3").props("role=status aria-live=polite")

        async def load(refresh: bool = False) -> None:
            nonlocal suggestion_index
            button.disable()
            refresh_button.disable()
            suggestions.clear()
            results.clear()
            try:
                response = await run.io_bound(
                    search_unesco, (query.value or "")[:100], refresh=refresh
                )
                suggestion_index = await run.io_bound(get_unesco_suggestions, "", 2000)
                query.set_autocomplete([item.value for item in suggestion_index])
            except OfficialServiceError as exc:
                with results:
                    ui.label(str(exc))
                    ui.label("로컬 XML 가져오기 방법은 README의 UNESCO 연결 안내를 참고하세요.")
                return
            except sqlite3.Error:
                with results:
                    ui.label("목록을 저장하거나 불러오지 못했습니다. 다시 시도하세요.")
                return
            finally:
                button.enable()
                refresh_button.enable()
            with results:
                ui.label(f"총 {response.total}건 · 처음 20건 표시")
                ui.label("조회 시각: " + response.retrieved_at.isoformat())
                ui.link("수집한 공식 데이터 출처", response.feed_source_url, new_tab=True)
                ui.link(
                    "DataHub 데이터셋·이용 조건 (CC BY-SA 4.0)"
                    if response.source_format == "json"
                    else "XML 배포 이용 조건",
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
                        ui.label(f"등재연도 {record.inscription_year} · ID {record.id}")
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

        button = ui.button("세계유산 찾기", on_click=search_data).classes("cb-action")

        async def refresh_data() -> None:
            await load(refresh=True)

        refresh_button = ui.button("최신 목록 확인하기", on_click=refresh_data).classes("cb-action")
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
        ui.label("두 문화유산 함께 알아보기").classes("cb-title text-3xl")
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
            state = await run.io_bound(
                exploration_graph.invoke,
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
        except (HeritageNotFoundError, sqlite3.Error, ValueError):
            panel.clear()
            _error_page(
                "선택한 비교 범위에서 탐구 자료를 확인하지 못했습니다. "
                "국내 비교는 부가 기능에서 선택해 주세요.",
                mode,
            )
            return
        panel.clear()
        with panel:
            ui.label(
                "공식 설명에서 찾은 내용을 살펴봐요. 자료가 부족한 부분은 판단을 보류해요."
            ).classes("cb-muted")
            ui.label("학습 순서: " + " → ".join(state["curriculum"]))
            for notice in state["comparison"]["learning_notices"]:
                ui.label(notice).classes("cb-muted")
            with ui.expansion("자료를 찾고 확인한 과정").classes("w-full"):
                ui.label(state["verification_note"])
                for step in state["execution_trace"]:
                    ui.label(readable_trace(step))
                ui.label(f"추가 자료 확인: {state['retry_count']}회")
            _collected_source_cards(
                [CollectedSource.model_validate(s) for s in state["collected_sources"]],
                learning_level,
            )
            ui.label("두 유산의 핵심 특징").classes("cb-title text-2xl")
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
):
    _base_styles()
    _header()
    try:
        if provider == "unesco":
            target = OfficialTarget(provider=provider, record_id=identity)
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
        _error_page("공식 대상 식별자를 확인해 주세요.", "web")
        return
    with ui.column().classes("cb-shell gap-5 py-10"):
        _return_button(
            return_to,
            home_context(
                level=level,
                goal=goal,
                goal_text=goal_text,
                amount=amount,
                comparison_scope=comparison_scope,
            ),
        )
        title = ui.label("함께 살펴볼 문화유산을 찾아요").classes("cb-title text-3xl")
        ui.label(SCOPE_LABELS[comparison_scope.value]).classes("font-semibold")
        _comparison_entry(
            level=level,
            comparison_scope=comparison_scope,
            domestic_url=with_return(
                f"/discover/{provider}/{identity}?level={level}&"
                + _goal_query(goal, goal_text, amount, ComparisonScope.DOMESTIC),
                scope_return(
                    return_to
                    or home_context(level=level, goal=goal, goal_text=goal_text, amount=amount),
                    ComparisonScope.DOMESTIC,
                ),
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
            result = await run.io_bound(run_autonomous, request)
        except (ValueError, OfficialServiceError, HeritageNotFoundError, sqlite3.Error):
            panel.clear()
            with panel:
                ui.label(
                    "공식 자료를 확보하거나 탐구를 저장하지 못했습니다. 잠시 후 다시 시도하세요."
                )
                ui.link("홈 검색으로 돌아가기", "/")
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
                    "선택한 범위에서 조건에 맞는 근거를 확보하지 못해 비교를 보류했어요. "
                    "범위를 자동 변경하지 않아요."
                ).classes("cb-muted")
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
                    ui.link(
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
                ui.link(
                    "먼저 살펴본 비교 결과 보기",
                    with_return(
                        f"/compare/{comparison['left']['id']}/{comparison['right']['id']}?saved_id={comparison['saved_id']}",
                        return_to,
                    ),
                )
                if result["quiz"]:
                    ui.link(
                        "배운 내용 퀴즈 풀기",
                        with_return(
                            f"/quiz/{comparison['left']['id']}/{comparison['right']['id']}?quiz_id={result['quiz']['quiz_id']}",
                            return_to,
                        ),
                    )
                else:
                    ui.label(result["quiz_notice"])
            ui.link("홈 검색으로 돌아가기", "/")
