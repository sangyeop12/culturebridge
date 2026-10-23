"""Opt-in catalogue checks. Saves public metadata, never article text or learner data."""

import argparse
import json
from datetime import date
from pathlib import Path

import httpx

from culturebridge.services.history_search_service import search_history


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live or args.output.exists():
        parser.error("Use --live and a new output path.")
    checks = []
    for query in ("세종", "임진왜란"):
        records, notice = search_history(query)
        if not records:
            raise RuntimeError("Expected catalogue example missing")
        with httpx.Client(timeout=15) as client:
            with client.stream("GET", records[0]["reading_url"]) as response:
                response.raise_for_status()
                status = response.status_code
        checks.append({"query": query, "result_count": len(records), "notice": notice,
                       "first_title": records[0]["name"], "first_url": records[0]["reading_url"],
                       "original_link_status": status})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump({"date": date.today().isoformat(), "checks": checks,
                   "scope": "catalogue_titles_and_official_links_not_ai_teaching"},
                  output, ensure_ascii=False, indent=2)
    print("Two live catalogue searches and their first official links: passed.")


if __name__ == "__main__":
    main()
