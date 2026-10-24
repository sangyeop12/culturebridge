"""Apply existing source permissions even to archived quiz snapshots and dialogue."""

from urllib.parse import urlsplit


def url_allowed(url, *, translation=False):
    from culturebridge.services.individual_source_service import INDIVIDUALS
    from culturebridge.services.source_permission_service import permission_status

    parsed = urlsplit(str(url))
    if parsed.scheme != "https":
        return False
    if parsed.hostname in {"www.khs.go.kr", "khs.go.kr", "www.heritage.go.kr", "heritage.go.kr"}:
        return True
    identities = [i for i, value in INDIVIDUALS.items() if value["url"] == str(url)]
    return bool(identities) and all(
        permission_status(i, "ai") == "approved"
        and (not translation or permission_status(i, "translation") == "approved")
        for i in identities
    )


def current_topic_messages(conversation):
    """Keep archived topics visible to the learner, outside the new AI context."""
    return conversation.messages[getattr(conversation, "topic_start", 0) :]


def conversation_ai_allowed(conversation):
    urls = [s["url"] for s in conversation.sources]
    urls += [
        c.get("url", "")
        for m in current_topic_messages(conversation)
        if m.kind != "dictionary"
        for c in m.citations
    ]
    return all(url_allowed(url) for url in urls)
