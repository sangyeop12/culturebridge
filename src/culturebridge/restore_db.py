"""Validate and restore to a NEW path only. Stop the server before changing DB_PATH."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def restore_database(backup: Path, output: Path):
    source = backup.resolve(strict=True)
    destination = output.resolve()
    if destination.exists() or source == destination:
        raise ValueError("복원은 새 파일 경로에만 할 수 있습니다. 기존 DB를 덮어쓰지 않습니다.")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader:
        tables = {r[0] for r in reader.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if (
            not {"heritages", "comparisons", "quiz_items"} <= tables
            or reader.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or reader.execute("PRAGMA foreign_key_check").fetchone()
        ):
            raise ValueError("CultureBridge 백업 무결성 검사를 통과하지 못했습니다.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents a concurrent restore from overwriting another file.
        with destination.open("xb"):
            pass
        with closing(sqlite3.connect(destination)) as writer, writer:
            reader.backup(writer)
    return destination


def main():
    parser = argparse.ArgumentParser(description="백업을 새 DB 파일로 복원")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(restore_database(args.backup, args.output))


if __name__ == "__main__":
    main()
