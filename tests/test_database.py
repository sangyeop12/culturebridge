import sqlite3
from pathlib import Path

from culturebridge.database import connect, initialize_database


def test_database_schema_and_seed(tmp_path: Path) -> None:
    database = tmp_path / "culturebridge-test.db"
    initialize_database(database)
    with connect(database) as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        heritage_count = connection.execute("SELECT COUNT(*) FROM heritages").fetchone()[0]

    assert {
        "heritages",
        "sources",
        "comparisons",
        "quiz_items",
        "learning_history",
    }.issubset(tables)
    assert heritage_count == 3


def test_database_seed_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "culturebridge-test.db"
    initialize_database(database)
    initialize_database(database)
    with connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM heritages").fetchone()[0] == 3


def test_legacy_quiz_table_is_migrated(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE quiz_items (
                id TEXT PRIMARY KEY,
                quiz_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                question TEXT NOT NULL,
                choices_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                explanation TEXT NOT NULL
            )
            """
        )

    initialize_database(database)
    with connect(database) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(quiz_items)")}
    assert {"heritage_id", "level"}.issubset(columns)
