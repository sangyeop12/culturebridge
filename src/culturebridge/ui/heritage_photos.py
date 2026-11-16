"""Locally served, reviewed public-domain photographs; never agent evidence."""

from pathlib import Path

from nicegui import ui

PHOTO_DIR = Path(__file__).resolve().parents[1] / "data" / "photos"
PHOTOS = {
    "khs:11:0000200000000:37": {
        "file": "dabotap.jpg",
        "name": "경주 불국사 다보탑",
        "alt": "계단과 난간, 여러 모양의 몸체가 보이는 다보탑의 실제 사진",
        "author": "Bernard Gagnon",
        "year": "2022",
        "license": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "source": "https://commons.wikimedia.org/wiki/File:Dabotap_Pagoda_01.jpg",
        "sha256": "bd21d337db7cb2b2cb6bc2623b6b4b4e65844eba5ffc64b513ebdc9adeac699e",
    },
    "official:toji-pagoda": {
        "file": "toji-pagoda.jpg",
        "name": "도지 오층탑",
        "alt": "연못과 나무 뒤로 다섯 층의 지붕이 보이는 도지 오층탑의 실제 사진",
        "author": "Wicki",
        "year": "2008",
        "license": "Public domain",
        "license_url": "https://commons.wikimedia.org/wiki/File:Pagoda_w_Toji.JPG#Licensing",
        "source": "https://commons.wikimedia.org/wiki/File:Pagoda_w_Toji.JPG",
        "sha256": "3a2b2286f2f28244fb6c2a8ce069b12da46fa61090f078445a56e53d76fcb0bc",
    },
}


def photo_gallery(identities):
    photos = [PHOTOS[i] for i in dict.fromkeys(identities) if i in PHOTOS]
    if not photos:
        return False
    ui.label("사진으로 함께 살펴봐요").classes("cb-title text-xl")
    with ui.element("div").classes("cb-photo-grid w-full"):
        for photo in photos:
            with ui.element("figure").classes("cb-photo-card"):
                image = (
                    ui.image(str(PHOTO_DIR / photo["file"]))
                    .props("fit=contain loading=lazy role=img")
                    .classes("cb-heritage-photo")
                )
                image._props["alt"] = photo["alt"]
                image._props["aria-label"] = photo["alt"]
                with ui.element("figcaption").classes("cb-photo-caption"):
                    ui.label(photo["name"]).classes("font-semibold")
                    ui.label(f"사진: {photo['author']} · {photo['year']}년 촬영")
                    with ui.row().classes("gap-3"):
                        ui.link("사진 출처", photo["source"], new_tab=True)
                        ui.link(photo["license"], photo["license_url"], new_tab=True)
    ui.label(
        "사진에서 탑의 모양을 찾아보세요. 촬영 시점과 지금의 모습은 다를 수 있어요. "
        "만들어진 시기와 재료는 공식 설명과 함께 살펴봐요."
    ).classes("cb-muted text-sm")
    return True
