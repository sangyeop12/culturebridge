"""Explicit search context, not browser history or arbitrary redirect URLs."""

from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

ROOTS = {"/", "/official", "/unesco", "/comparisons", "/kiosk"}
PARAMETERS = {"q", "scope", "page", "level", "goal", "goal_text", "amount", "auto"}


def search_return(value, fallback="/"):
    if not value or not value.startswith("/") or len(value) > 6000:
        return fallback
    decoded = unquote(value)
    if any(ord(c) < 32 for c in decoded) or "\\" in decoded or decoded.startswith("//"):
        return fallback
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.fragment or parts.path not in ROOTS:
        return fallback
    params = {k: v for k, v in parse_qsl(parts.query, keep_blank_values=True) if k in PARAMETERS}
    for key, limit in (("q", 100), ("goal_text", 200)):
        if key in params:
            params[key] = params[key][:limit]
    choices = {
        "scope": {"all", "korea", "world"},
        "level": {"beginner", "intermediate", "advanced"},
        "goal": {"observe", "compare", "religion", "verify"},
        "amount": {"brief", "standard", "deep"},
        "auto": {"0", "1", "true", "false"},
    }
    for key, allowed in choices.items():
        if key in params and params[key] not in allowed:
            params.pop(key)
    if "page" in params:
        if not params["page"].isascii() or not params["page"].isdigit():
            params.pop("page")
        else:
            params["page"] = str(max(1, min(int(params["page"]), 1000000)))
    return parts.path + ("?" + urlencode(params) if params else "")


def with_return(path, return_to):
    if not return_to:
        return path
    parts = urlsplit(path)
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "return_to"]
    params.append(("return_to", search_return(return_to)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def search_level(return_to, level):
    path = urlsplit(search_return(return_to))
    params = dict(parse_qsl(path.query, keep_blank_values=True))
    params["level"] = level
    return search_return(path.path + "?" + urlencode(params))


def home_context(
    q="", scope="all", page=1, level="beginner", goal="compare", goal_text="", amount="standard"
):
    return "/?" + urlencode(
        {
            "q": (q or "")[:100],
            "scope": scope,
            "page": page,
            "level": level,
            "goal": goal,
            "goal_text": (goal_text or "")[:200],
            "amount": amount,
            "auto": "1",
        }
    )
