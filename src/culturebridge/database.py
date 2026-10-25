import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from culturebridge.config import get_settings
from culturebridge.data.catalog import HERITAGES, SOURCES
from culturebridge.services.operation_service import can_read_resource, owner_key

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS learner_profiles (
    owner TEXT PRIMARY KEY, state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_preferences (
    owner TEXT PRIMARY KEY, state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_intents (
    owner TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0, state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS inferred_learning_intents (
    owner TEXT PRIMARY KEY, state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_conversations (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS learning_conversation_owner ON learning_conversations(owner);
CREATE TABLE IF NOT EXISTS learning_turn_requests (
    conversation_id TEXT NOT NULL REFERENCES learning_conversations(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, response_json TEXT NOT NULL,
    PRIMARY KEY(conversation_id, request_id)
);
CREATE TABLE IF NOT EXISTS learning_interrupts (
    conversation_id TEXT PRIMARY KEY REFERENCES learning_conversations(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS resource_owners (
    kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
CREATE TABLE IF NOT EXISTS comparison_keys (
    fingerprint TEXT PRIMARY KEY, comparison_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resource_created (
    kind TEXT NOT NULL, id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(kind,id)
);
CREATE TRIGGER IF NOT EXISTS resource_creation_time AFTER INSERT ON resource_owners
BEGIN
    INSERT OR IGNORE INTO resource_created(kind,id) VALUES(NEW.kind,NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS resource_deletion_time AFTER DELETE ON resource_owners
BEGIN
    DELETE FROM resource_created WHERE kind=OLD.kind AND id=OLD.id;
END;
CREATE TABLE IF NOT EXISTS learning_reviews (
    history_id INTEGER PRIMARY KEY REFERENCES learning_history(id),
    quiz_id TEXT NOT NULL, result_json TEXT NOT NULL, owner TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_review_links (
    history_id INTEGER PRIMARY KEY REFERENCES learning_history(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL UNIQUE REFERENCES learning_conversations(id) ON DELETE CASCADE,
    owner TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heritages (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    period TEXT NOT NULL,
    location TEXT NOT NULL,
    summary TEXT NOT NULL,
    structure TEXT NOT NULL,
    material TEXT NOT NULL,
    religious_context TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    heritage_id TEXT NOT NULL REFERENCES heritages(id),
    title TEXT NOT NULL,
    organization TEXT NOT NULL,
    url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    license_note TEXT
);

CREATE TABLE IF NOT EXISTS dynamic_heritages (
    id TEXT PRIMARY KEY REFERENCES heritages(id),
    detail_json TEXT NOT NULL,
    source_json TEXT NOT NULL,
    target_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comparisons (
    id TEXT PRIMARY KEY,
    left_id TEXT NOT NULL REFERENCES heritages(id),
    right_id TEXT NOT NULL REFERENCES heritages(id),
    level TEXT NOT NULL,
    content_json TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS course_runs (
    comparison_id TEXT PRIMARY KEY REFERENCES comparisons(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL, owner TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_notes (
    comparison_id TEXT NOT NULL REFERENCES comparisons(id) ON DELETE CASCADE,
    owner TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(comparison_id,owner)
);
CREATE TABLE IF NOT EXISTS quiz_metadata (
    quiz_id TEXT PRIMARY KEY, generation_note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS official_documents (
    id TEXT PRIMARY KEY,
    document_json TEXT NOT NULL,
    raw_xml TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS official_location_feeds (
    kind_code TEXT PRIMARY KEY,
    raw_xml TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unesco_feeds (
    language TEXT PRIMARY KEY,
    raw_xml TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_source_cache (
    id TEXT PRIMARY KEY,
    source_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS official_search_terms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quiz_items (
    id TEXT PRIMARY KEY,
    quiz_id TEXT NOT NULL,
    heritage_id TEXT NOT NULL REFERENCES heritages(id),
    level TEXT NOT NULL,
    position INTEGER NOT NULL,
    question TEXT NOT NULL,
    choices_json TEXT NOT NULL,
    correct_index INTEGER NOT NULL CHECK(correct_index BETWEEN 0 AND 3),
    explanation TEXT NOT NULL,
    UNIQUE(quiz_id, position)
);

CREATE TABLE IF NOT EXISTS learning_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    heritage_id TEXT NOT NULL REFERENCES heritages(id),
    level TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def database_path() -> Path:
    return get_settings().db_path


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def transaction(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(path: Path | None = None) -> Path:
    target = path or database_path()
    with transaction(target) as connection:
        connection.executescript(SCHEMA)
        # Legacy resources start their retention clock on migration, never at an invented past date.
        connection.execute(
            "INSERT OR IGNORE INTO resource_created(kind,id) SELECT kind,id FROM resource_owners"
        )
        _migrate_quiz_items(connection)
        unesco_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(unesco_feeds)")
        }
        for column, default in (
            ("format", "xml"),
            ("source_url", "https://whc.unesco.org/en/list/xml"),
            ("license_url", "https://whc.unesco.org/en/syndication"),
        ):
            if column not in unesco_columns:
                connection.execute(
                    f"ALTER TABLE unesco_feeds ADD {column} TEXT DEFAULT '{default}' NOT NULL"
                )
        source_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sources)")}
        for column in ("summary", "scope_note"):
            if column not in source_columns:
                connection.execute(
                    f"ALTER TABLE sources ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )
        for heritage in HERITAGES.values():
            connection.execute(
                """
                INSERT INTO heritages (
                    id, name, country, period, location, summary,
                    structure, material, religious_context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    country = excluded.country,
                    period = excluded.period,
                    location = excluded.location,
                    summary = excluded.summary,
                    structure = excluded.structure,
                    material = excluded.material,
                    religious_context = excluded.religious_context
                """,
                (
                    heritage.id,
                    heritage.name,
                    heritage.country,
                    heritage.period,
                    heritage.location,
                    heritage.summary,
                    heritage.structure,
                    heritage.material,
                    heritage.religious_context,
                ),
            )
            for source_id in heritage.source_ids:
                source = SOURCES[source_id]
                connection.execute(
                    """
                    INSERT INTO sources (
                        id, heritage_id, title, organization, url, retrieved_at, license_note,
                        summary, scope_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        heritage_id = excluded.heritage_id,
                        title = excluded.title,
                        organization = excluded.organization,
                        url = excluded.url,
                        retrieved_at = excluded.retrieved_at,
                        license_note = excluded.license_note,
                        summary = excluded.summary,
                        scope_note = excluded.scope_note
                    """,
                    (
                        source.id,
                        heritage.id,
                        source.title,
                        source.organization,
                        str(source.url),
                        source.retrieved_at.isoformat(),
                        source.license_note,
                        source.summary,
                        source.scope_note,
                    ),
                )
    return target


def _migrate_quiz_items(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(quiz_items)")}
    if "comparison_id" not in columns:
        connection.execute(
            "ALTER TABLE quiz_items ADD COLUMN comparison_id TEXT REFERENCES comparisons(id)"
        )
    if "evidence_json" not in columns:
        connection.execute(
            "ALTER TABLE quiz_items ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "heritage_id" not in columns:
        connection.execute(
            "ALTER TABLE quiz_items ADD COLUMN heritage_id TEXT NOT NULL DEFAULT 'seokguram'"
        )
    if "level" not in columns:
        connection.execute(
            "ALTER TABLE quiz_items ADD COLUMN level TEXT NOT NULL DEFAULT 'beginner'"
        )


def save_quiz_items(
    quiz_id: str,
    heritage_id: str,
    level: str,
    items: list[tuple[str, str, list[str], int, str]],
    path: Path | None = None,
    *,
    comparison_id: str | None = None,
    evidence: list[dict] | None = None,
) -> None:
    with transaction(path) as connection:
        for position, (item_id, question, choices, correct_index, explanation) in enumerate(items):
            connection.execute(
                """
                INSERT INTO quiz_items (
                    id, quiz_id, heritage_id, level, position,
                    question, choices_json, correct_index, explanation, comparison_id, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    quiz_id,
                    heritage_id,
                    level,
                    position,
                    question,
                    json.dumps(choices, ensure_ascii=False),
                    correct_index,
                    explanation,
                    comparison_id,
                    json.dumps(evidence or [], ensure_ascii=False),
                ),
            )
        connection.execute("INSERT INTO resource_owners VALUES('quiz',?,?)", (quiz_id, owner_key()))


def load_quiz_items(quiz_id: str, path: Path | None = None) -> list[sqlite3.Row]:
    with connect(path) as connection:
        owner = connection.execute(
            "SELECT owner FROM resource_owners WHERE kind='quiz' AND id=?", (quiz_id,)
        ).fetchone()
        if not can_read_resource(owner["owner"] if owner else None):
            return []
        return list(
            connection.execute(
                """
                SELECT id, heritage_id, level, question, choices_json, correct_index, explanation,
                    comparison_id, evidence_json
                FROM quiz_items
                WHERE quiz_id = ?
                ORDER BY position
                """,
                (quiz_id,),
            )
        )


def save_learning_result(
    session_id: str,
    heritage_id: str,
    level: str,
    score: int,
    total: int,
    path: Path | None = None,
) -> int:
    with transaction(path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO learning_history (session_id, heritage_id, level, score, total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, heritage_id, level, score, total),
        )
        return cursor.lastrowid
