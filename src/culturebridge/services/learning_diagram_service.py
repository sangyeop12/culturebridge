"""Code-native reading aids, not reconstructions or provider photographs."""

from html import escape

from culturebridge.services.evidence_reading_service import observation_scope, reading_units


def shape_diagram(quote):
    shapes = {
        "여덟 모서리가 있는 모양": (
            '<polygon points="45,10 75,10 100,35 100,65 75,90 45,90 20,65 20,35"/>'
        ),
        "십자 모양": '<path d="M45 10H75V35H100V65H75V90H45V65H20V35H45Z"/>',
        "직사각형": '<rect x="15" y="25" width="90" height="50"/>',
        "네모 모양": '<rect x="25" y="15" width="70" height="70"/>',
        "둥근 봉분": '<path d="M15 80A45 45 0 0 1 105 80Z"/>',
    }
    matches = [
        (label, shapes[label])
        for axis, label in reading_units("구조", quote)
        if axis == "모양" and label in shapes
    ]
    if not matches:
        return ""
    return (
        '<div class="cb-diagrams">'
        + "".join(
            '<figure><svg viewBox="0 0 120 100" width="100" height="84" role="img" aria-label="'
            + escape(label)
            + '" fill="#eaf0e7" stroke="#245c52" stroke-width="3">'
            + shape
            + "</svg><figcaption>"
            + escape(observation_scope(label, quote))
            + " · "
            + escape(label)
            + "</figcaption></figure>"
            for label, shape in matches
        )
        + '</div><p class="cb-muted text-sm">설명에 나온 모양을 이해하기 위한 도식이에요. '
        "실제 비율·입체 모습이나 복원도가 아니에요.</p>"
    )
