"""Bind reviewer verdicts to actual response spans and the recorded public-source snapshot.

Exact evidence provenance is checked mechanically. The semantic verdict remains the
reviewer's judgment, not a consequence of a citation existing. No API calls are made.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from culturebridge.services.agent_evaluation_service import evaluate_report


def verify_sources(report, grades, database):
    proofs = []
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        for grade in grades:
            identity = grade.get("source_id")
            row = connection.execute(
                "SELECT document_json FROM official_documents WHERE id=?", (identity,)
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT source_json FROM agent_source_cache WHERE id=?", (identity,)
                ).fetchone()
            if row is None:
                raise ValueError("Evidence source is not in the execution snapshot")
            source = json.loads(row[0])
            quote = grade.get("evidence_quote", "")
            content = source.get("content", "")
            if not quote or quote not in content:
                raise ValueError("Reviewer evidence quote is not an exact source span")
            run = next(
                r
                for r in report["runs"]
                if r["scenario"] == grade["scenario"]
                and r.get("repetition", 1) == grade.get("repetition", 1)
            )
            turn = run["turns"][grade["turn_index"]]
            proofs.append(
                {
                    "claim": grade["claim"],
                    "verdict": grade["verdict"],
                    "reviewer": grade["reviewer"],
                    "question_relevance": grade.get("question_relevance"),
                    "reason": grade["reason"],
                    "source_id": identity,
                    "source_url": source["source_url"],
                    "evidence_quote": quote,
                    "source_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "source_retrieved_at": source.get("retrieved_at"),
                    "exact_span_verified": True,
                    "source_cited": source["source_url"] in turn.get("citation_sources", []),
                }
            )
    return proofs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--grades", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    args = parser.parse_args()
    report_path = args.report.resolve()
    database = report_path.with_suffix(".db")
    if (
        report_path.parent != Path("outputs").resolve()
        or not database.is_file()
        or args.output.exists()
    ):
        parser.error("Select an outputs execution report with its DB and a NEW output file")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    grades = json.loads(args.grades.read_text(encoding="utf-8"))
    metrics = evaluate_report(
        report,
        grades=grades,
        input_rate=args.input_usd_per_million,
        output_rate=args.output_usd_per_million,
    )
    result = {
        "execution_report": str(report_path),
        "metrics": metrics,
        "claim_reviews": verify_sources(report, grades, database),
        "semantic_verdict_is_reviewer_judgment": True,
        "not_expert_or_learning_effect_approval": True,
        "price_inputs_usd_per_million": {
            "input": args.input_usd_per_million,
            "output": args.output_usd_per_million,
        },
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
