"""Suggestions are navigation aids, not invented heritage search results."""

from difflib import get_close_matches

from culturebridge.services.display_service import KOREAN_NAMES
from culturebridge.services.home_search_service import get_home_suggestions


def suggested_search_terms(query):
    term = query.strip()
    known = list(KOREAN_NAMES.values())
    known.extend(item.value for item in get_home_suggestions(limit=6000))
    return [
        candidate
        for candidate in get_close_matches(term, list(dict.fromkeys(known)), n=3, cutoff=0.4)
        if candidate != term
    ]
