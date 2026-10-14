"""Explicit non-overwriting SQLite backup; no secrets or environment files included."""

import argparse
import sqlite3
from pathlib import Path

from culturebridge.config import get_settings


def backup_database(output: Path):
    source = get_settings().db_path.resolve(strict=True)
    destination = output.resolve()
    if destination.exists() or destination == source:
        raise ValueError("기존 파일을 덮어쓰지 않습니다. 새로운 백업 경로를 지정하세요.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as reader:
        with sqlite3.connect(destination) as writer:
            reader.backup(writer)
            if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("백업 무결성 검사 실패")
    return destination


def main():
    parser = argparse.ArgumentParser(description="Create a non-overwriting SQLite backup")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(backup_database(args.output))


if __name__ == "__main__":
    main()
