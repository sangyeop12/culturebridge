"""One information architecture for every learning screen."""

import asyncio
import logging
import sqlite3
from contextvars import copy_context
from functools import partial

from nicegui import ui

from culturebridge.services.learning_conversation_service import (
    ConversationNotFoundError,
    delete_conversation,
    list_conversation_page,
)

logger = logging.getLogger(__name__)
THREAD_PAGE_SIZE = 20

PRIMARY = (
    ("새 대화", "/learn", "conversation"),
    ("자료 찾기", "/library", "heritage"),
    ("학습 코스", "/courses", "courses"),
    ("나의 학습", "/learning-history", "history"),
)


def section_for(path):
    if path == "/":
        return "home"
    if path.startswith("/learn") and not path.startswith("/learning-history"):
        return "conversation"
    if path.startswith("/courses"):
        return "courses"
    if path in {"/learning-history", "/comparisons", "/data-policy"}:
        return "history"
    if path == "/install":
        return "guide"
    if path == "/settings":
        return "settings"
    return "heritage"


def primary_navigation(path):
    active = section_for(path)
    icons = {
        "conversation": "edit_square",
        "heritage": "search",
        "courses": "auto_stories",
        "history": "history",
    }
    with ui.element("nav").classes("cb-nav").props('aria-label="주요 메뉴"'):
        for title, route, section in PRIMARY:
            with ui.link(target=route) as link:
                ui.icon(icons[section], size="19px").props("aria-hidden=true")
                ui.label(title)
            if section == active or (section == "conversation" and active == "home"):
                link.props('aria-current="page"')


def workspace_navigation(path):
    """One owner-scoped thread list shared by all ordinary pages."""
    request = ui.context.client.request
    selected = request.query_params.get("conversation_id", "") if request else ""
    owner_context = copy_context()
    with (
        ui.left_drawer(value=None, top_corner=True, bottom_corner=True)
        .props("breakpoint=900 width=264 bordered")
        .classes("cb-sidebar") as drawer
    ):
        with ui.link(target="/").classes("cb-brand").props('aria-label="CultureBridge 처음으로"'):
            ui.icon("account_balance", size="23px").classes("cb-brand-mark").props(
                "aria-hidden=true"
            )
            ui.label("CultureBridge")
        primary_navigation(path)
        with ui.column().classes("cb-thread-section w-full gap-0"):
            ui.label("최근 대화").classes("cb-sidebar-label").props("id=conversation-heading")
            _conversation_list(selected, owner_context)
        with ui.column().classes("cb-thread-list w-full gap-1").props("id=conversation-list"):
            ui.label("최근 대화").classes("cb-sidebar-label")
            thread_items = ui.column().classes("cb-thread-items w-full gap-1")
            shown = 0

            def confirm_delete(item):
                with ui.dialog() as dialog, ui.card():
                    ui.label("이 대화를 삭제할까요?")
                    ui.label(item["title"]).classes("cb-muted")
                    with ui.row():
                        ui.button("취소", on_click=dialog.close).props("flat")

                        def remove():
                            try:
                                delete_conversation(item["id"])
                            except ConversationNotFoundError:
                                ui.notify("이미 삭제된 대화예요.", color="warning")
                            dialog.close()
                            if str(item["id"]) == selected:
                                ui.navigate.to("/learn")
                            else:
                                render_threads(shown)

                        ui.button("삭제", on_click=remove).props("color=negative")
                dialog.open()

            def render_threads(count):
                nonlocal shown
                items = list_conversations(limit=count)
                shown = len(items)
                thread_items.clear()
                with thread_items:
                    for item in items:
                        with ui.row().classes("cb-thread-row w-full items-center no-wrap"):
                            with ui.link(target=f"/learn?conversation_id={item['id']}").classes(
                                "cb-thread-link"
                            ) as link:
                                ui.label(item["title"]).classes("cb-thread-title")
                                if item.get("preview") and item["preview"] != item["title"]:
                                    ui.label(item["preview"]).classes("cb-thread-preview")
                            if str(item["id"]) == selected:
                                link.props('aria-current="page"')
                            with (
                                ui.button(icon="more_vert")
                                .props('flat round dense aria-label="대화 메뉴"')
                                .classes("cb-thread-menu")
                            ):
                                with ui.menu():
                                    ui.menu_item(
                                        "삭제", on_click=lambda _, row=item: confirm_delete(row)
                                    )
                more.set_visibility(len(items) == count)

            more = (
                ui.button("더보기", icon="expand_more", on_click=lambda: render_threads(shown + 20))
                .props("flat no-caps")
                .classes("cb-thread-more")
            )
            render_threads(20)
            if not shown:
                ui.label("첫 질문을 남겨 보세요.").classes("cb-thread-empty")
        with ui.column().classes("cb-sidebar-bottom w-full gap-1"):
            with ui.expansion("도움말과 이용 안내", icon="help_outline").classes("w-full"):
                ui.link("공식 자료 안내", "/sources")
                ui.link("기록 보관·삭제", "/data-policy")
                ui.link("홈 화면에 추가하기", "/install")
                ui.link("박물관 체험 모드", "/kiosk")
                ui.link(
                    "UI 참고 · Codex Desktop",
                    "https://github.com/dfones288/codex-desktop",
                    new_tab=True,
                )
            with ui.link(target="/settings").classes("cb-sidebar-settings") as settings:
                ui.icon("tune", size="19px").props("aria-hidden=true")
                ui.label("학습 설정")
            if path == "/settings":
                settings.props('aria-current="page"')
    return drawer


def _conversation_list(selected, owner_context):
    with (
        ui.column()
        .classes("cb-thread-list w-full gap-1")
        .props(
            "id=conversation-list role=region aria-labelledby=conversation-heading tabindex=0"
        ) as scroller
    ):
        thread_items = ui.column().classes("cb-thread-items w-full gap-1")
        empty = ui.label("첫 질문을 남겨 보세요.").classes("cb-thread-empty")
        shown_ids = set()
        cursor = None
        has_more = True
        loading = False
        retry = False

        def size_batch(batch):
            count = len(batch.default_slot.children)
            if count:
                batch.style(f"--cb-thread-count: {count}")
            else:
                batch.delete()

        def confirm_delete(item, row, batch):
            with ui.dialog() as dialog, ui.card():
                ui.label("이 대화를 삭제할까요?")
                ui.label(item["title"]).classes("cb-muted")
                with ui.row():
                    ui.button("취소", on_click=dialog.close).props("flat")

                    def remove():
                        try:
                            owner_context.copy().run(delete_conversation, item["id"])
                        except ConversationNotFoundError:
                            ui.notify("이미 삭제된 대화예요.", color="warning")
                        dialog.close()
                        if item["id"] == selected:
                            ui.navigate.to("/learn")
                            return
                        shown_ids.discard(item["id"])
                        row.delete()
                        size_batch(batch)
                        empty.set_visibility(not shown_ids and not has_more)

                    ui.button("삭제", on_click=remove).props("color=negative")
            dialog.open()

        def append_threads(items):
            new_items = [item for item in items if item["id"] not in shown_ids]
            if not new_items:
                return
            with thread_items, ui.column().classes("cb-thread-batch w-full gap-1") as batch:
                for item in new_items:
                    with ui.row().classes("cb-thread-row w-full items-center no-wrap") as row:
                        shown_ids.add(item["id"])
                        link = ui.link(
                            item["title"], f"/learn?conversation_id={item['id']}"
                        ).classes("cb-thread-link")
                        if item["id"] == selected:
                            link.props('aria-current="page"')
                        with (
                            ui.button(icon="more_vert")
                            .props('flat round dense aria-label="대화 메뉴"')
                            .classes("cb-thread-menu")
                        ):
                            with ui.menu():
                                ui.menu_item(
                                    "삭제",
                                    on_click=partial(confirm_delete, item, row, batch),
                                )
                size_batch(batch)

        def show_page(items, next_cursor):
            nonlocal cursor, has_more, retry
            append_threads(items)
            cursor = next_cursor
            has_more = cursor is not None
            retry = False
            status.set_text("")
            more.set_text("더보기")
            more.classes(add="cb-thread-auto")
            more.set_visibility(has_more)
            empty.set_visibility(not shown_ids and not has_more)

        def show_error():
            nonlocal retry
            retry = True
            status.set_text("이전 대화를 불러오지 못했어요.")
            more.set_text("다시 시도")
            more.classes(remove="cb-thread-auto")
            empty.set_visibility(False)

        async def load_more(automatic=False):
            nonlocal loading
            if loading or not has_more or (automatic and retry):
                return
            loading = True
            more.disable()
            status.set_text("이전 대화를 불러오는 중…")
            try:
                items, next_cursor = await asyncio.to_thread(
                    owner_context.copy().run,
                    list_conversation_page,
                    page_size=THREAD_PAGE_SIZE,
                    before=cursor,
                )
                show_page(items, next_cursor)
            except sqlite3.Error:
                logger.exception("Failed to load older conversations")
                show_error()
            finally:
                loading = False
                more.enable()

        async def load_on_scroll():
            await load_more(automatic=True)

        status = ui.label().classes("cb-thread-status").props("role=status aria-live=polite")
        more = (
            ui.button("더보기", icon="expand_more", on_click=lambda: load_more())
            .props("flat no-caps")
            .classes("cb-thread-more cb-thread-auto")
        )
        scroller.on(
            "scroll",
            load_on_scroll,
            throttle=0.25,
            js_handler="""(event) => {
                const list = event.currentTarget;
                const more = list.querySelector('.cb-thread-auto:not([disabled])');
                if (more?.getClientRects().length &&
                    list.scrollHeight - list.scrollTop - list.clientHeight <= 160) {
                    emit();
                }
            }""",
        )
        try:
            show_page(*list_conversation_page(page_size=THREAD_PAGE_SIZE))
        except sqlite3.Error:
            logger.exception("Failed to load recent conversations")
            show_error()
