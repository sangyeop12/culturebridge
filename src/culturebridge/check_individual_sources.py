"""Explicit live diagnostics: status and valid axes only, never secrets or invented content."""

import argparse
import json

from culturebridge.database import initialize_database
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.individual_source_service import INDIVIDUALS, fetch_individual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+", choices=list(INDIVIDUALS))
    args = parser.parse_args()
    initialize_database()
    failed = False
    for identity in args.ids:
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
            }
            failed |= source.status not in {"fresh", "cached"}
        except Exception as exc:
            row = {
                "id": identity,
                "status": "unavailable",
                "error_type": type(exc.__cause__ or exc).__name__,
            }
            failed = True
        print(json.dumps(row, ensure_ascii=False))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
