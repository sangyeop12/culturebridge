"""Small presentation helpers; operational timestamps stay out of lesson content."""

from datetime import UTC, datetime, timedelta, timezone

from culturebridge.database import transaction
from culturebridge.services.operation_service import owner_key


def learning_day(value):
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(timezone(timedelta(hours=9))).strftime("%m월 %d일 학습")
    except (ValueError, TypeError):
        return "지난 학습"


def owns_comparison(identity):
    with transaction() as connection:
        row = connection.execute(
            "SELECT owner FROM resource_owners WHERE kind='comparison' AND id=?", (identity,)
        ).fetchone()
    return bool(row and row["owner"] == owner_key())


def lesson_activity(identity):
    from culturebridge.data.learning_courses import COURSES

    with transaction() as connection:
        row = connection.execute(
            "SELECT course_id FROM course_runs WHERE comparison_id=? AND owner=?",
            (identity, owner_key()),
        ).fetchone()
        note = connection.execute(
            "SELECT content FROM learning_notes WHERE comparison_id=? AND owner=?",
            (identity, owner_key()),
        ).fetchone()
    course = COURSES.get(row["course_id"], {}) if row else {}
    return {
        "title": course.get("title", "내가 정리한 배움"),
        "activities": course.get("activities", []),
        "reflection": course.get("reflection", "같은 점과 다른 점, 더 확인할 점을 적어 보세요."),
        "note": note["content"] if note else "",
    }


def save_learning_note(identity, content):
    if not owns_comparison(identity):
        raise ValueError("내 학습 기록에만 정리를 저장할 수 있어요.")
    if len(content) > 3000:
        raise ValueError("정리한 내용은 3,000자 이내로 입력해 주세요.")
    with transaction() as connection:
        connection.execute(
            "INSERT INTO learning_notes VALUES(?,?,?) ON CONFLICT(comparison_id,owner) "
            "DO UPDATE SET content=excluded.content",
            (identity, owner_key(), content),
        )
