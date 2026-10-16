"""Five guided entry points into the existing evidence/comparison/quiz workflow."""

import json
from copy import deepcopy

from culturebridge.agents.workflow import run_exploration
from culturebridge.data.learning_courses import COURSES
from culturebridge.database import transaction
from culturebridge.domain.models import ComparisonScope, LearningLevel
from culturebridge.services.comparison_scope_service import validate_pair_scope
from culturebridge.services.curriculum_service import evidence_suits_goal
from culturebridge.services.dynamic_heritage_service import OfficialTarget, fetch_target
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.operation_service import owner_key, reused_operation


class CourseNotFoundError(KeyError):
    pass


class CourseNotReadyError(ValueError):
    pass


def get_course(identity):
    if identity not in COURSES:
        raise CourseNotFoundError(identity)
    return {"id": identity, **deepcopy(COURSES[identity]), "comparison_scope": "overseas"}


def list_courses():
    return [get_course(identity) for identity in COURSES]


@reused_operation("course_start")
def start_course(identity, level=None):
    course = get_course(identity)
    level = LearningLevel(level or course["level"])
    left, left_source = fetch_target(OfficialTarget(**course["left"]))
    right, right_source = fetch_target(OfficialTarget(**course["right"]))
    validate_pair_scope(right.country, ComparisonScope.OVERSEAS)
    categories = []
    for source in (left_source, right_source):
        if source.status not in {"fresh", "cached"}:
            raise CourseNotReadyError("최신 원문을 확보하지 못해 코스 시작을 보류했어요.")
        categories.append(
            {d.category for d in _local_extraction([source]) if validate_extraction(d, [source])}
        )
    if not evidence_suits_goal(*categories, course["goal"] + " " + course["goal_text"]):
        raise CourseNotReadyError("이번 목표에 필요한 양쪽 근거가 부족해 시작을 보류했어요.")
    state = run_exploration(
        {
            "heritage_id": left.id,
            "comparison_id": right.id,
            "level": level.value,
            "goal": course["goal"],
            "goal_text": course["goal_text"],
            "amount": course["amount"],
            "comparison_scope": "overseas",
        }
    )
    saved_id = state["comparison"]["saved_id"]
    with transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO course_runs(comparison_id,course_id,owner) VALUES(?,?,?)",
            (saved_id, identity, owner_key()),
        )
    return {"course_id": identity, **state}


def course_progress(identity):
    get_course(identity)
    with transaction() as connection:
        rows = connection.execute(
            "SELECT r.comparison_id,c.content_json FROM course_runs r "
            "JOIN comparisons c ON c.id=r.comparison_id "
            "JOIN resource_owners o ON o.kind='comparison' AND o.id=c.id "
            "WHERE r.course_id=? AND r.owner=? AND o.owner=? ORDER BY r.created_at DESC LIMIT 5",
            (identity, owner_key(), owner_key()),
        ).fetchall()
        results = []
        for row in rows:
            comp = json.loads(row["content_json"])["comparison"]
            quiz = connection.execute(
                "SELECT q.quiz_id FROM quiz_items q JOIN resource_owners o "
                "ON o.kind='quiz' AND o.id=q.quiz_id "
                "WHERE q.comparison_id=? AND o.owner=? ORDER BY q.rowid DESC LIMIT 1",
                (row["comparison_id"], owner_key()),
            ).fetchone()
            review = (
                connection.execute(
                    "SELECT history_id,result_json FROM learning_reviews WHERE quiz_id=? "
                    "AND owner=? ORDER BY history_id DESC LIMIT 1",
                    (quiz["quiz_id"], owner_key()),
                ).fetchone()
                if quiz
                else None
            )
            results.append(
                {
                    "comparison_id": row["comparison_id"],
                    "left_id": comp["left"]["id"],
                    "right_id": comp["right"]["id"],
                    "level": comp["level"],
                    "quiz_id": quiz["quiz_id"] if quiz else None,
                    "history_id": review["history_id"] if review else None,
                    "status": "review_ready"
                    if review
                    else "quiz_ready"
                    if quiz
                    else "comparison_ready",
                    "result": json.loads(review["result_json"]) if review else None,
                }
            )
    return results
