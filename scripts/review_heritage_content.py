"""Read-only content desk review against an explicitly selected audit source cache."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource, LearningLevel
from culturebridge.services.date_reading_service import read_period
from culturebridge.services.lesson_service import explain_source
from culturebridge.services.material_review_service import material_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.db.resolve().parent != Path("outputs").resolve() or not args.db.is_file():
        parser.error("Select an existing isolated DB inside outputs.")
    if args.output.exists():
        parser.error("Choose a new output report.")
    settings = get_settings()
    settings.db_path = args.db
    settings.gemini_enabled = False
    with transaction() as connection:
        cache = {
            row["id"]: row["source_json"]
            for row in connection.execute("SELECT id,source_json FROM agent_source_cache")
        }
    result = []
    for row in material_review():
        if row["id"] not in cache:
            result.append(
                {
                    "id": row["id"],
                    "source_url": row["source_url"],
                    "review_status": "source_not_cached",
                    "human_approved": False,
                    "original_preserved": False,
                    "readings_generated": 0,
                }
            )
            continue
        source = CollectedSource.model_validate_json(cache[row["id"]])
        lessons = [explain_source(source, level) for level in LearningLevel]
        sections = lessons[0].sections
        result.append(
            {
                "id": row["id"],
                "korean_name": row["korean_name"],
                "official_name": row["name"],
                "source_url": row["source_url"],
                "unit": row["unit"],
                "scope_note": row["scope_note"],
                "name_finding": row["name_finding"],
                "name_status": row["name_status"],
                "human_approved": False,
                "review_status": "generated"
                if source.status in {"fresh", "cached"}
                else "source_not_current",
                "readings_generated": len(lessons),
                "original_preserved": all(
                    lesson.original_text == source.content for lesson in lessons
                ),
                "missing_categories": [
                    category
                    for category in ("시대", "구조", "재료", "종교적 배경")
                    if not any(s.category == category and s.evidence_quote for s in sections)
                ],
                "period_reading": next(
                    (
                        period.text
                        for section in sections
                        if section.category == "시대"
                        and (period := read_period(section.evidence_quote))
                    ),
                    None,
                ),
                "beginner_sections": [
                    {
                        "category": section.category,
                        "guide": section.text,
                        "evidence_quote": section.evidence_quote,
                        "check_question": section.check_question,
                    }
                    for section in sections
                ],
            }
        )
    report = {
        "date": datetime.now(timezone(timedelta(hours=9))).date().isoformat(),
        "reviewer": "AI desk review",
        "human_approved": False,
        "permission_granted": False,
        "sources": result,
        "source_count": len(result),
        "reading_count": sum(row["readings_generated"] for row in result),
        "source_unavailable_count": sum(r["review_status"] != "generated" for r in result),
        "all_originals_preserved": all(row["original_preserved"] for row in result),
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "source_count",
                    "reading_count",
                    "all_originals_preserved",
                    "human_approved",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
