"""Aliases identify the same subject; membership never aliases a group to its child."""

from culturebridge.data.individual_sources import EXTENDED_INDIVIDUALS

ALIASES = {
    "seokguram": "khs:11:0000240000000:37",
    "horyuji": "unesco:660",
    "dayanta": "official:dayanta",
}
PARENTS = {
    "official:horyuji-pagoda": "unesco:660",
    "official:dayanta": "unesco:1442",
    "official:taj-mahal-mausoleum": "unesco:252",
    "official:grand-trianon": "unesco:83",
    **{"official:" + key: record["parent"] for key, record in EXTENDED_INDIVIDUALS.items()},
}


def canonical_id(identity):
    return ALIASES.get(identity, identity)


def identity_info(identity):
    canonical = canonical_id(identity)
    return {
        "id": identity,
        "canonical_id": canonical,
        "parent_id": PARENTS.get(canonical),
        "aliases": [old for old, new in ALIASES.items() if new == canonical],
        "note": "별칭은 같은 대상, parent_id는 포함 관계입니다. "
        "유산군을 개별 유산으로 바꾸지 않습니다.",
    }
