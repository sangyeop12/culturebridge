"""Explicit live diagnostics: status and valid axes only, never secrets or invented content."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from culturebridge.database import initialize_database
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.individual_source_service import INDIVIDUALS, fetch_individual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--all", action="store_true", help="Check every registered source")
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    identities = list(INDIVIDUALS) if args.all else args.ids
    if not identities or any(identity not in INDIVIDUALS for identity in identities):
        parser.error("등록된 개별 자료 ID 또는 --all 을 지정하세요.")
    initialize_database()

    def check(identity):
        try:
            source = fetch_individual(identity, refresh=True)
            categories = [
                d.category for d in _local_extraction([source]) if validate_extraction(d, [source])
            ]
            row = {
                "id": identity,
                "status": source.status,
                "characters": len(source.content),
                "categories": categories,
                "unit": INDIVIDUALS[identity].get("unit", "building"),
                "comparison_ready": source.status in {"fresh", "cached"} and len(categories) >= 2,
            }
        except Exception as exc:
            row = {
                "id": identity,
                "status": "unavailable",
                "error_type": type(exc.__cause__ or exc).__name__,
            }
        return row

    failed = False
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for row in executor.map(check, identities):
            failed |= not row.get("comparison_ready", False)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
