"""Official-cache comprehension benchmark. Offline by default; no student-effect claims."""

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from culturebridge.config import get_settings
from culturebridge.data.assessment_benchmark import CASES
from culturebridge.domain.learning import LearningConversation, LearningTurn
from culturebridge.domain.models import CollectedSource
from culturebridge.services.conversation_source_policy import url_allowed
from culturebridge.services.lesson_service import explain_source
from culturebridge.services.understanding_assessment_service import assessment_decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", action="append", choices=[case["id"] for case in CASES])
    parser.add_argument("--max-calls", type=int, default=20, choices=range(1, 41))
    args = parser.parse_args()
    if (
        args.db.resolve().parent != Path("outputs").resolve()
        or not args.db.is_file()
        or args.output.exists()
    ):
        parser.error("Select an isolated outputs DB and a new output report")
    settings = get_settings()
    if args.live and not (settings.gemini_enabled and settings.gemini_api_key):
        parser.error("Gemini is not configured")
    previous = settings.db_path
    settings.db_path = args.db
    report = {
        "kind": "AI_authored_gold_cases_not_expert_or_student_validation",
        "human_participants": 0,
        "educational_effect_established": False,
        "live_requested": args.live,
        "calls": 0,
        "rate_limited": False,
        "rows": [],
    }
    try:
        with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            cached = dict(connection.execute("SELECT id,source_json FROM agent_source_cache"))
        for case in CASES:
            if args.case and case["id"] not in args.case:
                continue
            raw = cached.get("official:" + case["source"])
            source = CollectedSource.model_validate_json(raw) if raw else None
            section = (
                next(
                    (s for s in explain_source(source).sections if s.category == case["concept"]),
                    None,
                )
                if source
                else None
            )
            quote = section.evidence_quote if section else ""
            consistent = bool(re.search(case["quote_pattern"], quote, re.I | re.S))
            for index, (answer, expected) in enumerate(case["answers"]):
                row = {
                    "case": case["id"],
                    "variant": index,
                    "expected": expected,
                    "question": case["question"],
                    "learner_answer": answer,
                    "source_quote": quote,
                    "source_id": source.heritage_id if source else None,
                    "source_url": str(source.source_url) if source else None,
                    "source_retrieved_at": source.retrieved_at.isoformat() if source else None,
                    "source_matches_case": consistent,
                    "status": "ready_not_executed" if consistent else "source_review_needed",
                }
                report["rows"].append(row)
                if not consistent or not args.live:
                    continue
                if report["rate_limited"] or report["calls"] >= args.max_calls:
                    row["status"] = "not_run_limit"
                    continue
                if not url_allowed(str(source.source_url)):
                    row["status"] = "not_run_source_policy"
                    continue
                state = LearningConversation(id=uuid4(), revision=0)
                state.checkpoint = {
                    "question": case["question"],
                    "quote": quote,
                    "concept": case["concept"],
                    "source_id": source.heritage_id,
                }
                started = time.monotonic()
                report["calls"] += 1
                try:
                    decision = assessment_decision(
                        {
                            "conversation": state,
                            "deadline": started + 20,
                            "request": LearningTurn(request_id=uuid4(), revision=0, text=answer),
                        }
                    )
                    actual = decision.assessment if decision else "none"
                    row.update(status="executed", actual=actual, matches_gold=actual == expected)
                except Exception as exc:
                    report["rate_limited"] = str(getattr(exc, "code", "")) == "429"
                    row.update(status="error", error_type=type(exc).__name__)
                row["seconds"] = round(time.monotonic() - started, 3)
        completed = [r for r in report["rows"] if r["status"] == "executed"]
        report["completed"] = len(completed)
        report["matches_gold"] = sum(r["matches_gold"] for r in completed)
        report["gold_agreement_rate"] = (
            report["matches_gold"] / len(completed) if completed else None
        )
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "live_requested",
                        "calls",
                        "rate_limited",
                        "completed",
                        "gold_agreement_rate",
                    )
                },
                ensure_ascii=False,
            )
        )
    finally:
        settings.db_path = previous


if __name__ == "__main__":
    main()
