"""Summarize saved checks without contacting an API. Unreviewed claims remain unknown."""

import argparse
import json
from pathlib import Path

from culturebridge.services.agent_evaluation_service import evaluate_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--grades", type=Path, help="Independent per-claim audit JSON list")
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    grades = json.loads(args.grades.read_text(encoding="utf-8")) if args.grades else None
    print(
        json.dumps(
            evaluate_report(
                report,
                grades=grades,
                input_rate=args.input_usd_per_million,
                output_rate=args.output_usd_per_million,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
