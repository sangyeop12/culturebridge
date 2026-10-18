"""Explicit per-purpose approvals. A desk review is not a grant of permission."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

from culturebridge.database import transaction

PURPOSES = {"storage_display", "ai", "translation", "redistribution"}


def _tables(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS source_permissions
        (id TEXT,purpose TEXT,approved INTEGER,note TEXT,PRIMARY KEY(id,purpose));
        CREATE TABLE IF NOT EXISTS source_permission_bindings
        (id TEXT,purpose TEXT,source_url TEXT NOT NULL,recorded_at TEXT NOT NULL,
         PRIMARY KEY(id,purpose));
    """)


def permission_status(identity, purpose):
    """A recorded approval applies only to the same registered source, never an alternative."""
    from culturebridge.services.individual_source_service import INDIVIDUALS
    from culturebridge.services.source_registry_service import reviews

    identity = identity.removeprefix("official:")
    if identity not in INDIVIDUALS or purpose not in PURPOSES:
        raise ValueError("등록된 자료와 처리 목적을 확인하세요.")
    if reviews().get(identity, {}).get("usage_status") == "restricted":
        return "restricted"
    with transaction() as connection:
        _tables(connection)
        row = connection.execute(
            "SELECT p.approved,b.source_url FROM source_permissions p "
            "LEFT JOIN source_permission_bindings b ON b.id=p.id AND b.purpose=p.purpose "
            "WHERE p.id=? AND p.purpose=?",
            (identity, purpose),
        ).fetchone()
    if not row:
        return "not_recorded"
    if not row["approved"]:
        return "denied"
    if row["source_url"] != INDIVIDUALS[identity]["url"]:
        return "needs_rereview"
    return "approved"


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

    for source in sources:
        identity = (source if isinstance(source, str) else source.heritage_id).removeprefix(
            "official:"
        )
        if identity not in INDIVIDUALS:
            continue
        if permission_status(identity, purpose) != "approved":
            return False
    return True


def record_permission(identity, purpose, approved, note):
    """Local administrator only; requires actual review evidence, never a public endpoint."""
    from culturebridge.services.individual_source_service import INDIVIDUALS

    if identity not in INDIVIDUALS or purpose not in PURPOSES or not note.strip():
        raise ValueError("자료·처리 목적·확인 근거를 입력하세요.")
    with transaction() as connection:
        _tables(connection)
        connection.execute(
            "INSERT OR REPLACE INTO source_permissions VALUES(?,?,?,?)",
            (identity, purpose, int(bool(approved)), note[:2000]),
        )
        connection.execute(
            "INSERT OR REPLACE INTO source_permission_bindings VALUES(?,?,?,?)",
            (identity, purpose, INDIVIDUALS[identity]["url"], datetime.now(UTC).isoformat()),
        )
