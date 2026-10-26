"""Opt-in live source API checks in a fresh DB. No Gemini calls or key output."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.main import app
from culturebridge.services.history_search_service import search_history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    database = output.with_suffix(".db")
    if output.parent != Path("outputs").resolve() or output.exists() or database.exists():
        parser.error("Use new report and DB paths directly inside outputs")
    settings = get_settings()
    original = settings.model_copy(deep=True)
    settings.db_path = database
    settings.gemini_enabled = False
    settings.maintenance_enabled = False
    rows = []
    detail = "/api/official/heritages/11/0000200000000/37"
    checks = [
        ("khs_search", "/api/official/heritages", {"q": "다보탑"}, "items"),
        ("khs_detail", detail, {}, "content"),
        ("khs_detail_cache", detail, {}, "content"),
        ("khs_location", detail + "/location", {}, "projected_x"),
        ("unesco_datahub", "/api/unesco/heritages", {"q": "호류지"}, "records"),
        ("unesco_cache", "/api/unesco/heritages", {"q": "호류지"}, "records"),
        ("unesco_autocomplete", "/api/unesco/suggestions", {"q": "호류지"}, None),
    ]
    try:
        with TestClient(app) as client:
            for name, path, params, required in checks:
                started = time.monotonic()
                row = {"check": name, "passed": False}
                try:
                    response = client.get(path, params=params)
                    row["http_status"] = response.status_code
                    payload = response.json()
                    valid = bool(payload.get(required)) if required else bool(payload)
                    if isinstance(payload, dict):
                        row.update({k: payload[k] for k in ("cached", "stale") if k in payload})
                        for key in ("source_url", "feed_source_url", "coordinate_system"):
                            if key in payload:
                                row[key] = payload[key]
                        if required in {"items", "records"}:
                            row["result_count"] = len(payload.get(required, []))
                    row["passed"] = response.status_code == 200 and valid and not row.get("stale")
                    if name.endswith("_cache"):
                        row["passed"] = row["passed"] and row.get("cached") is True
                except Exception as exc:
                    row["error_type"] = type(exc).__name__
                row["seconds"] = round(time.monotonic() - started, 3)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
            for query in ("세종", "임진왜란"):
                started = time.monotonic()
                row = {"check": "history_" + query, "passed": False}
                try:
                    records, _ = search_history(query)
                    row.update(passed=bool(records), result_count=len(records))
                except Exception as exc:
                    row["error_type"] = type(exc).__name__
                row["seconds"] = round(time.monotonic() - started, 3)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        settings.db_path = original.db_path
        settings.gemini_enabled = original.gemini_enabled
        settings.maintenance_enabled = original.maintenance_enabled
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "checks": rows,
                    "dictionary": "deferred_by_user",
                    "gemini_calls": 0,
                },
                stream,
                ensure_ascii=False,
                indent=2,
            )
    return int(any(not row["passed"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
