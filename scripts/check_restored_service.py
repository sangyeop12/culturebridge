"""Read a backup and its isolated restoration; never replace the running service DB."""

import argparse
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from culturebridge.config import get_settings


def counts(path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                for name in names if name.replace('_', '').isalnum()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--restored", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    if args.restored.resolve() == settings.db_path.resolve() or args.output.exists():
        parser.error("Use an isolated restored DB and a new report path")
    before, after = counts(args.backup), counts(args.restored)
    assert before == after, "Restored table counts differ"
    settings.db_path = args.restored
    settings.gemini_enabled = settings.maintenance_enabled = settings.retention_enabled = False
    settings.individual_sources_enabled = False
    from culturebridge.main import app

    with TestClient(app) as client:
        routes = {path: client.get(path).status_code for path in (
            "/api/health", "/", "/learn", "/settings", "/courses", "/learning-history"
        )}
    assert all(value == 200 for value in routes.values()), routes
    report = {"integrity": "ok", "foreign_keys": "ok", "table_counts_equal": True,
              "tables_checked": len(before), "routes": routes, "production_replaced": False}
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
