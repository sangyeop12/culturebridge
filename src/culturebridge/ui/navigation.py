"""One information architecture for every learning screen; routes remain unchanged."""

from nicegui import ui

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
    from culturebridge.services.learning_conversation_service import (
        ConversationNotFoundError,
        delete_conversation,
        list_conversations,
    )

    request = ui.context.client.request
    selected = request.query_params.get("conversation_id", "") if request else ""
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
                            link = ui.link(
                                item["title"], f"/learn?conversation_id={item['id']}"
                            ).classes("cb-thread-link")
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
