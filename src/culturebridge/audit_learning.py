"""Explicit AI-off simulated learner walkthrough, not an educational outcome study."""

import argparse
import json
from pathlib import Path

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.models import CollectedSource
from culturebridge.services.course_service import course_progress, list_courses, start_course
from culturebridge.services.learning_report_service import (
    learning_report,
    report_html,
    report_markdown,
)
from culturebridge.services.lesson_service import explain_source
from culturebridge.services.operation_service import session_owner
from culturebridge.services.question_service import answer_question
from culturebridge.services.quiz_service import grade_quiz, load_quiz


def audit_courses():
    """Caller must select an isolated DB. These are controlled synthetic answer scenarios."""
    if get_settings().gemini_enabled:
        raise ValueError("권한 미확인 원문을 외부 AI에 전송하지 않도록 AI를 비활성화하세요.")
    token = session_owner.set("simulated-classroom-audit")
    rows = []
    try:
        for course in list_courses():
            for level in ("beginner", "intermediate", "advanced"):
                try:
                    state = start_course(course["id"], level)
                    comp = state["comparison"]
                    quiz = load_quiz(
                        state["quiz"]["quiz_id"], comp["left"]["id"], comp["right"]["id"]
                    )
                    expected = [item.correct_index for item in quiz.items]
                    correct = grade_quiz(quiz.quiz_id, expected)
                    wrong = grade_quiz(quiz.quiz_id, [(answer + 1) % 4 for answer in expected])
                    exported = learning_report(comp["saved_id"], wrong.history_id)
                    originals = [
                        CollectedSource.model_validate(s) for s in comp["collected_sources"]
                    ]
                    readings = [explain_source(source, level) for source in originals]
                    html = report_html(exported)
                    markdown = report_markdown(exported)
                    question = answer_question(
                        comp["left"]["id"],
                        comp["right"]["id"],
                        "두 유산의 재료와 구조를 설명해 주세요.",
                        readings[0].level,
                        comparison_id=comp["saved_id"],
                        use_ai=False,
                    )
                    rows.append(
                        {
                            "course": course["id"],
                            "level": level,
                            "questions": len(quiz.items),
                            "distinct_questions": len({item.question for item in quiz.items}),
                            "max_choice_length": max(
                                len(c.text) for item in quiz.items for c in item.choices
                            ),
                            "content_questions": sum(
                                "복습 항목:" in item.explanation for item in quiz.items
                            ),
                            "all_correct_score": correct.score,
                            "all_wrong_score": wrong.score,
                            "wrong_review_items": len(wrong.review_items),
                            "exported_score": exported["assessment"]["score"],
                            "export_has_no_answers": "correct_answer" not in json.dumps(exported),
                            "print_ready": "window.print()" in html
                            and "## 퀴즈와 복습" in markdown,
                            "original_preserved": all(
                                r.original_text == s.content
                                for r, s in zip(readings, originals, strict=True)
                            ),
                            "question_grounded": bool(question.source_ids) and not question.used_ai,
                            "progress": course_progress(course["id"])[0]["status"],
                            "status": "completed",
                        }
                    )
                except Exception as exc:
                    rows.append(
                        {
                            "course": course["id"],
                            "level": level,
                            "status": "held",
                            "error": type(exc).__name__,
                        }
                    )
    finally:
        session_owner.reset(token)
    for row in rows:
        if row["status"] == "completed" and not (
            row["questions"] == row["distinct_questions"] == row["content_questions"] == 5
            and row["all_correct_score"] == 5
            and row["all_wrong_score"] == 0
            and row["wrong_review_items"] == 5
            and row["exported_score"] == 0
            and row["export_has_no_answers"]
            and row["print_ready"]
            and row["original_preserved"]
            and row["question_grounded"]
        ):
            row["status"] = "quality_issue"
    return {
        "method": "AI-off simulated learner; deliberately correct/wrong answers",
        "human_participants": 0,
        "educational_effectiveness_validated": False,
        "ai_permission_granted": False,
        "scenarios": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="격리 DB에서 5코스×3수준 모의 학습 점검")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.db_path.resolve().parent != Path("outputs").resolve():
        parser.error(
            "CULTUREBRIDGE_DB_PATH를 outputs 아래 점검 DB로 지정하세요. "
            "실제 학습 DB는 사용하지 않습니다."
        )
    settings.gemini_enabled = False
    initialize_database()
    result = audit_courses()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))
    return int(any(row["status"] != "completed" for row in result["scenarios"]))


if __name__ == "__main__":
    raise SystemExit(main())
