"""Original vector illustrations, not photographs or historical reconstructions."""

from html import escape

MOTIFS = {
    "pagoda": (
        "탑",
        '<path fill="#bdad8e" d="M115 221h130v15H115zM130 201h100v20H130z"/>'
        '<path fill="#d9c9a8" d="M151 90h58v111h-58z"/>'
        '<path fill="#506a60" d="m180 65-52 35h104zm0 40-62 35h124zm0 43-74 36h148z"/>'
        '<path stroke="#7c5b42" stroke-width="3" d="M180 36v34"/>'
        '<g fill="none" stroke="#7c5b42" stroke-width="3">'
        '<ellipse cx="180" cy="48" rx="7" ry="2"/>'
        '<ellipse cx="180" cy="57" rx="9" ry="2"/></g>'
        '<path fill="#9c614b" d="M172 183h16v18h-16z"/>',
    ),
    "hall": (
        "큰 건물",
        '<path fill="#b09a76" d="M80 220h200v13H80z"/>'
        '<path fill="#dfcdae" d="M100 151h160v69H100z"/>'
        '<path fill="#405d53" d="M180 83c-20 36-65 61-112 65v12h224v-12c-47-4-92-29-112-65z"/>'
        '<path fill="#a15f47" d="M110 160h9v60h-9zm55 0h9v60h-9zm76 0h9v60h-9z"/>'
        '<path fill="#6d5943" d="M129 174h25v46h-25zm58 0h38v46h-38z"/>',
    ),
    "palace": (
        "궁전",
        '<path fill="#b09a76" d="M70 224h220v12H70z"/>'
        '<path fill="#dbc8a7" d="M83 146h194v78H83zM148 123h64v101h-64z"/>'
        '<path fill="#54695e" d="m180 78-54 45h108zM75 137h210v12H75z"/>'
        '<g fill="#79634b"><path d="M103 165h20v35h-20zm134 0h20v35h-20z"/>'
        '<path d="M166 224v-53a14 14 0 0 1 28 0v53z"/></g>'
        '<path stroke="#f4e8cf" stroke-width="6" d="M139 151v69m82-69v69"/>',
    ),
    "tomb": (
        "무덤과 묘당",
        '<path fill="#bfc8a9" d="M64 224a90 90 0 0 1 180 0z"/>'
        '<path fill="#d9c9ae" d="M160 150h111v74H160z"/>'
        '<path fill="#607667" d="M155 150c5-20 18-35 60-64 42 29 55 44 60 64z"/>'
        '<path stroke="#816346" stroke-width="4" d="M215 73v15"/>'
        '<path fill="#78654e" d="M202 224v-39a13 13 0 0 1 26 0v39z"/>'
        '<path fill="#b2a183" d="M149 224h132v12H149z"/>',
    ),
    "church": (
        "성당과 예배당",
        '<path fill="#d7c6a5" d="M109 119h35v108h-35zm34 29h110v79H143z"/>'
        '<path fill="#53695e" d="m126 56-25 63h50zm71 43-62 49h124z"/>'
        '<path fill="#a77d57" d="M180 227v-44a17 17 0 0 1 34 0v44z"/>'
        '<path fill="#8caaac" '
        'd="M119 148v-14a7 7 0 0 1 14 0v14zM187 151v-17a10 10 0 0 1 20 0v17z"/>'
        '<path stroke="#856844" stroke-width="4" d="M126 40v18m-8-11h16"/>'
        '<path fill="#ae9a79" d="M98 227h167v10H98z"/>',
    ),
}

COURSE_ART = {
    "pagoda-materials": "pagoda",
    "halls-and-roofs": "hall",
    "palace-spaces": "palace",
    "tombs-and-materials": "tomb",
    "churches-and-evidence": "church",
}


def heritage_art(kind="hall", *, panoramic=False):
    """Only fixed, locally authored SVG markup; never insert source/provider HTML."""
    name, drawing = MOTIFS.get(kind, MOTIFS["hall"])
    if panoramic:
        body = (
            '<circle cx="595" cy="65" r="33" fill="#e3bc77"/>'
            '<path d="M0 190 130 104 270 191 410 120 610 216 760 140 900 215v105H0z" '
            'fill="#c7d0bd"/>'
            '<path d="M0 242 155 172 300 234 470 181 680 250 820 191 900 224v96H0z" '
            'fill="#aabca8"/>'
            '<g transform="translate(55 39) scale(1.05)">' + MOTIFS["pagoda"][1] + "</g>"
            '<g transform="translate(370 55)">' + MOTIFS["hall"][1] + "</g>"
            '<g transform="translate(650 65) scale(.88)">' + MOTIFS["church"][1] + "</g>"
            '<path d="M0 296h900" stroke="#7d937e" stroke-width="2"/>'
        )
        viewbox, label = "0 0 900 320", "산과 탑, 큰 건물, 성당을 표현한 창작 삽화"
    else:
        body = (
            '<circle cx="265" cy="68" r="27" fill="#e8c786"/>'
            '<path d="M0 220 90 153 180 202 290 145 360 202v58H0z" fill="#d8dfcb"/>'
            + drawing
            + '<path d="M35 237h290" stroke="#a59a7d" stroke-width="2"/>'
        )
        viewbox, label = "0 0 360 260", name + " 유형을 표현한 창작 삽화"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
        f'role="img" aria-label="{escape(label, quote=True)}" class="cb-heritage-art">'
        '<rect width="100%" height="100%" fill="#f1eadb"/>' + body + "</svg>"
    )


def course_art(identity):
    return heritage_art(COURSE_ART.get(identity, "hall"))


def museum_scene():
    """A locally authored illustrated exhibition, not a reconstruction of a real place."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 470" '
        'role="img" aria-label="탑과 궁전, 성당을 둘러보는 상상의 역사 전시관">'
        '<rect width="720" height="470" rx="36" fill="#e6f2ef"/>'
        '<circle cx="590" cy="92" r="61" fill="#ffcd78"/>'
        '<path d="M0 344Q180 226 358 337T720 292V470H0Z" fill="#c5e0d7"/>'
        '<path d="M0 438Q350 265 720 409" fill="none" stroke="#fff6e8" stroke-width="50"/>'
        '<rect x="40" y="99" width="190" height="240" rx="90" fill="#fff5e3"/>'
        '<rect x="265" y="50" width="190" height="240" rx="90" fill="#eee6fb"/>'
        '<rect x="490" y="126" width="190" height="240" rx="90" fill="#ffe3d1"/>'
        '<g transform="translate(15 143) scale(.67)">' + MOTIFS["pagoda"][1] + "</g>"
        '<g transform="translate(240 93) scale(.67)">' + MOTIFS["palace"][1] + "</g>"
        '<g transform="translate(465 169) scale(.67)">' + MOTIFS["church"][1] + "</g>"
        '<g fill="#fff" stroke="#2a685d" stroke-width="3">'
        '<circle cx="135" cy="341" r="18"/><circle cx="360" cy="292" r="18"/>'
        '<circle cx="585" cy="368" r="18"/></g>'
        '<g fill="#2a685d" font-family="sans-serif" font-size="18" text-anchor="middle">'
        '<text x="135" y="347">1</text><text x="360" y="298">2</text>'
        '<text x="585" y="374">3</text></g>'
        '<path d="m54 59 4 12 12 4-12 4-4 12-4-12-12-4 12-4Z" fill="#447a6d"/>'
        '<path d="m481 48 4 12 12 4-12 4-4 12-4-12-12-4 12-4Z" fill="#9076b6"/>'
        '<circle cx="326" cy="401" r="21" fill="#efae86"/>'
        '<path d="M301 445v-16a25 25 0 0 1 50 0v16" fill="#356d67"/>'
        '<circle cx="379" cy="408" r="17" fill="#e9b88f"/>'
        '<path d="M359 449v-15a20 20 0 0 1 40 0v15" fill="#a58bc5"/>'
        "</svg>"
    )
