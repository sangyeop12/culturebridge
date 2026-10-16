"""Read-only public source catalogue; changes require a local administrator CLI."""

import json
from datetime import UTC, datetime

from culturebridge.database import transaction


def _tables(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS source_reviews (
            id TEXT PRIMARY KEY, korean_name TEXT NOT NULL, aliases_json TEXT NOT NULL,
            name_status TEXT NOT NULL, usage_status TEXT NOT NULL, note TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_attempts (
            id TEXT PRIMARY KEY, status TEXT NOT NULL, error_code TEXT NOT NULL,
            attempted_at TEXT NOT NULL, last_success_at TEXT);
    """)


def reviews():
    with transaction() as connection:
        _tables(connection)
        return {row["id"]: dict(row) for row in connection.execute("SELECT * FROM source_reviews")}


def save_review(
    identity, korean_name, aliases=(), *, name_status="guidance", usage_status="pending", note=""
):
    from culturebridge.services.individual_source_service import INDIVIDUALS
    from culturebridge.services.name_registry_service import NameDraft

    if identity not in INDIVIDUALS:
        raise ValueError("등록된 개별 유산 ID가 필요합니다.")
    draft = NameDraft(korean_name=korean_name, aliases=list(aliases))
    if (
        name_status not in {"guidance", "reviewed"}
        or usage_status not in {"pending", "reviewed", "restricted"}
        or len(note) > 2000
    ):
        raise ValueError("검토 상태와 메모를 확인하세요.")
    with transaction() as connection:
        _tables(connection)
        connection.execute(
            "INSERT OR REPLACE INTO source_reviews VALUES(?,?,?,?,?,?,?)",
            (
                identity,
                draft.korean_name,
                json.dumps(draft.aliases, ensure_ascii=False),
                name_status,
                usage_status,
                note,
                datetime.now(UTC).isoformat(),
            ),
        )


def record_attempt(identity, status, error_code=""):
    now = datetime.now(UTC).isoformat()
    success = now if status == "fresh" else None
    with transaction() as connection:
        _tables(connection)
        connection.execute(
            "INSERT INTO source_attempts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status,error_code=excluded.error_code,attempted_at=excluded.attempted_at,"
            "last_success_at=COALESCE(excluded.last_success_at,source_attempts.last_success_at)",
            (identity, status, error_code, now, success),
        )


def source_overview():
    from culturebridge.services.individual_source_service import INDIVIDUALS

    reviewed = reviews()
    with transaction() as connection:
        attempts = {
            row["id"]: dict(row) for row in connection.execute("SELECT * FROM source_attempts")
        }
        cached = {
            row["id"]: row["retrieved_at"]
            for row in connection.execute("SELECT id,retrieved_at FROM agent_source_cache")
        }
    rows = []
    for identity, source in INDIVIDUALS.items():
        review = reviewed.get(identity, {})
        attempt = attempts.get(identity, {})
        rows.append(
            {
                "id": "official:" + identity,
                "name": source["name"],
                "korean_name": review.get("korean_name", source["korean"]),
                "country": source["country"],
                "type": source["type"],
                "unit": source.get("unit", "building"),
                "source_url": source["url"],
                "organization": source["organization"],
                "parent_id": source["parent"],
                "aliases": list(source.get("aliases", ()))
                + json.loads(review.get("aliases_json", "[]")),
                "name_status": review.get("name_status", "guidance"),
                "usage_status": review.get("usage_status", "pending"),
                "note": review.get("note", ""),
                "reviewed_at": review.get("updated_at"),
                "connection_status": attempt.get("status", "not_checked"),
                "error_code": attempt.get("error_code", ""),
                "attempted_at": attempt.get("attempted_at"),
                "last_success_at": attempt.get("last_success_at"),
                "cached_at": cached.get("official:" + identity),
            }
        )
    return rows
