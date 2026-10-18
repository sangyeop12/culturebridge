"""Repeatable desk review and live base-example audit, never a human trial.

Uses a new isolated database. Only source caches are read from the service DB;
learner records, permissions and keys are never copied into the output report.
"""

import argparse
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction


def prepare_database(destination, source):
    destination = destination.resolve()
    if destination.parent != Path("outputs").resolve() or destination.exists():
        raise ValueError("Choose a NEW audit DB directly inside outputs.")
    destination.parent.mkdir(exist_ok=True)
    settings = get_settings()
    settings.db_path = destination
    initialize_database()
    # Read only public source caches, not user data or permission grants.
    if source.exists():
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
            with transaction() as target:
                for table in ("official_documents", "unesco_feeds", "agent_source_cache"):
                    rows = original.execute(f"SELECT * FROM {table}").fetchall()
                    if rows:
                        placeholders = ",".join("?" for _ in rows[0])
                        target.executemany(
                            f"INSERT OR IGNORE INTO {table} VALUES({placeholders})", rows
                        )


def live_base_example():
    """Real service calls, no mocks; individual-source permission gates stay enabled."""
    from culturebridge.agents.workflow import run_exploration
    from culturebridge.domain.models import LearningLevel
    from culturebridge.services.question_service import answer_question
    from culturebridge.services.quiz_service import grade_quiz, load_quiz

    settings = get_settings()
    if not settings.gemini_api_key:
        return {"status": "not_configured"}
    settings.gemini_enabled = True
    state = run_exploration(
        {
            "heritage_id": "seokguram",
            "comparison_id": "horyuji",
            "level": "beginner",
            "goal": "compare",
            "goal_text": "재료와 구조",
            "amount": "standard",
            "comparison_scope": "overseas",
        }
    )
    comp = state["comparison"]
    answer = answer_question(
        "seokguram",
        "horyuji",
        "두 유산은 어떤 재료로 만들었나요?",
        LearningLevel.BEGINNER,
        comparison_id=comp["saved_id"],
        use_ai=True,
    )
    result = {
        "status": "completed_with_checks",
        "pair": ["seokguram", "horyuji"],
        "sources": [{"id": s["id"], "status": s["status"]} for s in state["collected_sources"]],
        "field_methods": sorted({f["method"] for f in state["extracted_fields"] if f.get("value")}),
        "question_used_ai": answer.used_ai,
        "question_citations": len(answer.citations),
        "question_status": answer.verification_status.value,
        "trace": state["execution_trace"],
        "quiz_available": bool(state.get("quiz")),
        "full_ai_success": False,
    }
    if state.get("quiz"):
        quiz = load_quiz(state["quiz"]["quiz_id"], "seokguram", "horyuji")
        correct = [item.correct_index for item in quiz.items]
        wrong = grade_quiz(quiz.quiz_id, [(i + 1) % 4 for i in correct])
        result.update(
            quiz_generation=quiz.generation_note,
            questions=len(quiz.items),
            all_wrong_score=wrong.score,
            review_items=len(wrong.review_items),
        )
        result["full_ai_success"] = (
            result["field_methods"] == ["gemini"]
            and answer.used_ai
            and "Gemini" in quiz.generation_note
            and "규칙" not in quiz.generation_note
            and len(quiz.items) == 5
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Uses configured Gemini quota")
    parser.add_argument("--refresh-materials", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Report already exists; select a new filename.")
    settings = get_settings()
    prepare_database(args.db, settings.db_path)
    from culturebridge.audit_learning import audit_courses
    from culturebridge.services.material_review_service import material_review
    from culturebridge.services.operation_service import session_owner

    token = session_owner.set("readiness-audit-not-a-person")
    try:
        settings.gemini_enabled = False
        if args.refresh_materials:
            from culturebridge.data.material_review import SCOPE_NOTES
            from culturebridge.services.individual_source_service import fetch_individual

            def fetch(identity):
                try:
                    return {
                        "id": identity,
                        "status": fetch_individual(identity, refresh=True).status,
                    }
                except Exception as exc:
                    return {
                        "id": identity,
                        "status": "unavailable",
                        "error_type": type(exc).__name__,
                    }

            with ThreadPoolExecutor(max_workers=4) as pool:
                connections = list(pool.map(fetch, SCOPE_NOTES))
        else:
            connections = []
        review = material_review()
        result = {
            "human_participants": 0,
            "human_approval": False,
            "materials": review,
            "simulated_classroom": audit_courses(),
            "connections": connections,
        }
        if args.live:
            try:
                result["live_base_example"] = live_base_example()
            except Exception as exc:
                # Never log SDK request contents or exception messages.
                result["live_base_example"] = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "full_ai_success": False,
                }
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    "materials": len(review),
                    "simulated": [r["status"] for r in result["simulated_classroom"]["scenarios"]],
                    "live": result.get("live_base_example"),
                },
                ensure_ascii=False,
            )
        )
    finally:
        session_owner.reset(token)


if __name__ == "__main__":
    main()
