"""One information architecture for every learning screen; routes remain unchanged."""

from nicegui import ui

PRIMARY = (
    ("홈", "/", "home"),
    ("대화 학습", "/learn", "conversation"),
    ("문화유산 탐구", "/official", "heritage"),
    ("추천 학습 코스", "/courses", "courses"),
    ("나의 학습", "/learning-history", "history"),
)


def section_for(path):
    if path == "/":
        return "home"
    if path == "/history-search" or (
        path.startswith("/learn") and not path.startswith("/learning-history")
    ):
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
    with ui.element("nav").classes("cb-nav").props('aria-label="주요 메뉴"'):
        for title, route, section in PRIMARY:
            link = ui.link(title, route)
            if section == active:
                link.props('aria-current="page"')


def secondary_navigation(path):
    section = section_for(path)
    groups = {
        "heritage": (
            ("한국 문화유산", "/official"),
            ("세계유산", "/unesco"),
            ("비교할 유산 찾기", "/#heritage-search"),
            ("공식 자료 안내", "/sources"),
        ),
        "history": (
            ("관심사와 학습 목표", "/learning-history#learning-profile"),
            ("퀴즈와 복습", "/learning-history"),
            ("비교 기록", "/comparisons"),
            ("기록 보관·삭제", "/data-policy"),
        ),
        "conversation": (
            ("대화 학습", "/learn"),
            ("인물·사건 자료 찾기", "/history-search"),
            ("학습 기록", "/learning-history"),
            ("설정", "/settings"),
        ),
        "courses": (("코스 둘러보기", "/courses"), ("학습 기록", "/learning-history")),
        "guide": (("홈 화면에 추가하기", "/install"), ("자료 이용 안내", "/sources")),
        "settings": (("설정", "/settings"), ("나의 학습", "/learning-history")),
    }
    if section == "home":
        return
    label = next(
        (title for title, _, key in PRIMARY if key == section),
        "설정" if section == "settings" else "이용 안내",
    )
    with ui.element("div").classes("cb-context-wrap"):
        with ui.element("nav").classes("cb-breadcrumb").props('aria-label="현재 위치"'):
            ui.link("홈", "/")
            ui.icon("chevron_right", size="16px").props("aria-hidden=true")
            ui.label(label)
        with ui.element("nav").classes("cb-subnav").props('aria-label="관련 화면"'):
            for title, route in groups[section]:
                link = ui.link(title, route)
                if path == route or (
                    route in {"/official", "/sources", "/courses"} and path.startswith(route + "/")
                ):
                    link.props('aria-current="page"')


def site_footer():
    with ui.element("footer").classes("cb-site-footer") as footer:
        with ui.row().classes("items-center justify-between w-full gap-4 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("CultureBridge").classes("cb-footer-brand")
                ui.label("질문을 나누고, 공식 자료로 확인하고, 나만의 배움으로 이어가요.")
            with ui.row().classes("gap-5 flex-wrap"):
                ui.link("설정", "/settings")
                ui.link("공식 자료 안내", "/sources")
                ui.link("학습 기록 안내", "/data-policy")
                ui.link("홈 화면에 추가하기", "/install")
    return footer
