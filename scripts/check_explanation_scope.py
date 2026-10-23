"""Opt-in, four-call maximum review of dated and religious KHS excerpts."""
import argparse
import json
import time
from pathlib import Path

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.learning_preferences import LearningPreferences
from culturebridge.services.lesson_service import official_source
from culturebridge.services.official_service import get_official_document
from culturebridge.services.personalized_explanation_service import explain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--category", choices=["시대", "종교적 배경"], action="append")
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".db").exists():
        parser.error("Choose new report and DB paths")
    settings = get_settings()
    if not settings.gemini_enabled or not settings.gemini_api_key:
        parser.error("Gemini is not configured")
    settings.db_path = args.output.with_suffix(".db")
    initialize_database()
    doc = get_official_document("11", "0000200000000", "37")
    source = official_source(doc)
    fields = [f for f in _local_extraction([source]) if validate_extraction(f, [source])]
    rows = []
    for category in args.category or ("시대", "종교적 배경"):
        field = next(f for f in fields if f.category == category)
        text, metadata = explain(
            category, field.evidence_quote, LearningPreferences(explanation_depth="easy"),
            {"mode": "explain"}, time.monotonic() + 35,
        )
        rows.append({"category": category, "original": field.evidence_quote,
                     "explanation": text, "metadata": metadata,
                     "check_passed": metadata["method"] == "gemini_grounded_rewrite"})
        if metadata.get("failure_kind") == "provider_rate_limit":
            break
    args.output.write_text(json.dumps({"max_model_calls": 4, "cases": rows,
        "source_url": str(doc.source_url), "expert_approval": False}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps({"cases": [{"category": r["category"], "passed": r["check_passed"],
                                 "method": r["metadata"]["method"]} for r in rows]}))


if __name__ == "__main__":
    main()
