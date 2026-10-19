"""Explicitly collect free, licensed supplementary records without sending permission requests."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.open_record_service import AVAILABLE_OPEN_RECORDS, fetch_open_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.suffix != ".json" or args.output.exists():
        parser.error("새 JSON 출력 파일을 지정하세요. 기존 파일은 덮어쓰지 않습니다.")
    rows, failures = [], []
    for identity in sorted(AVAILABLE_OPEN_RECORDS):
        try:
            rows.append(fetch_open_record(identity))
        except OfficialServiceError:
            failures.append(identity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "collected_at": datetime.now(UTC).isoformat(),
                "records": rows,
                "failures": failures,
                "free_only": True,
                "external_ai_called": False,
                "permission_requests_sent": 0,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    print(
        json.dumps(
            {"collected": len(rows), "failed": len(failures), "output": str(args.output)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
