"""Explicit per-purpose approvals. A desk review is not a grant of permission."""

from urllib.parse import urlsplit

from culturebridge.database import transaction


def policy_url(url):
    from culturebridge.data.source_audit import PROVIDER_FINDINGS

    host = (urlsplit(str(url)).hostname or "").removeprefix("www.")
    return next(
        (
            value[1]
            for domain, value in PROVIDER_FINDINGS.items()
            if value[0] != "not_established" and (host == domain or host.endswith("." + domain))
        ),
        None,
    )


def external_ai_allowed(sources, purpose="ai"):
    from culturebridge.services.individual_source_service import INDIVIDUALS
    from culturebridge.services.source_registry_service import reviews

    for source in sources:
        identity = (source if isinstance(source, str) else source.heritage_id).removeprefix(
            "official:"
        )
        if identity not in INDIVIDUALS:
            continue
        if reviews().get(identity, {}).get("usage_status") == "restricted":
            return False
        with transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_permissions "
                "(id TEXT,purpose TEXT,approved INTEGER,note TEXT,PRIMARY KEY(id,purpose))"
            )
            row = connection.execute(
                "SELECT approved FROM source_permissions WHERE id=? AND purpose=?",
                (identity, purpose),
            ).fetchone()
        if not row or not row["approved"]:
            return False
    return True


def record_permission(identity, purpose, approved, note):
    """Local administrator only; requires actual review evidence, never a public endpoint."""
    from culturebridge.services.individual_source_service import INDIVIDUALS

    if (
        identity not in INDIVIDUALS
        or purpose not in {"ai", "translation", "redistribution"}
        or not note.strip()
    ):
        raise ValueError("자료·처리 목적·확인 근거를 입력하세요.")
    with transaction() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS source_permissions "
            "(id TEXT,purpose TEXT,approved INTEGER,note TEXT,PRIMARY KEY(id,purpose))"
        )
        connection.execute(
            "INSERT OR REPLACE INTO source_permissions VALUES(?,?,?,?)",
            (identity, purpose, int(bool(approved)), note[:2000]),
        )
