"""Explicit session deletion and opt-in, age-based retention; shared source data is preserved."""

from culturebridge.database import transaction
from culturebridge.services.operation_service import (
    clear_operation_cache,
    deleting_session,
    session_owner,
)


def _marks(values):
    return ",".join("?" for _ in values)


def delete_records(*, owner=None, cutoff=None, apply=False):
    if owner is None and cutoff is None:
        raise ValueError("소유 세션 또는 보관 기한이 필요합니다.")
    with transaction() as connection:
        resources = connection.execute(
            "SELECT o.kind,o.id FROM resource_owners o JOIN resource_created c "
            "ON c.kind=o.kind AND c.id=o.id WHERE (? IS NULL OR o.owner=?) "
            "AND (? IS NULL OR julianday(c.created_at)<julianday(?))",
            (owner, owner, cutoff, cutoff),
        ).fetchall()
        quiz_ids = [r["id"] for r in resources if r["kind"] == "quiz"]
        comparison_ids = [r["id"] for r in resources if r["kind"] == "comparison"]
        # A newer/unrelated quiz must never lose its referenced saved comparison.
        comparison_ids = [
            identity
            for identity in comparison_ids
            if not any(
                r["quiz_id"] not in quiz_ids
                for r in connection.execute(
                    "SELECT DISTINCT quiz_id FROM quiz_items WHERE comparison_id=?", (identity,)
                )
            )
        ]
        histories = [
            r["id"]
            for r in connection.execute(
                "SELECT h.id FROM learning_history h JOIN learning_reviews r ON r.history_id=h.id "
                "WHERE (? IS NULL OR r.owner=?) "
                "AND (? IS NULL OR julianday(h.created_at)<julianday(?))",
                (owner, owner, cutoff, cutoff),
            )
        ]
        counts = {
            "comparisons": len(comparison_ids),
            "quizzes": len(quiz_ids),
            "history": len(histories),
            "applied": apply,
        }
        if not apply:
            return counts
        if histories:
            connection.execute(
                f"DELETE FROM learning_reviews WHERE history_id IN ({_marks(histories)})", histories
            )
            connection.execute(
                f"DELETE FROM learning_history WHERE id IN ({_marks(histories)})", histories
            )
        if quiz_ids:
            connection.execute(
                f"DELETE FROM quiz_items WHERE quiz_id IN ({_marks(quiz_ids)})", quiz_ids
            )
        if comparison_ids:
            connection.execute(
                f"DELETE FROM comparison_keys WHERE comparison_id IN ({_marks(comparison_ids)})",
                comparison_ids,
            )
            connection.execute(
                f"DELETE FROM comparisons WHERE id IN ({_marks(comparison_ids)})", comparison_ids
            )
        for kind, identities in [("quiz", quiz_ids), ("comparison", comparison_ids)]:
            for identity in identities:
                connection.execute(
                    "DELETE FROM resource_owners WHERE kind=? AND id=?", (kind, identity)
                )
    clear_operation_cache(owner)
    return counts


def delete_session_records():
    owner = session_owner.get()
    if not owner:
        raise ValueError("브라우저 세션을 확인할 수 없습니다.")
    with deleting_session(owner):
        return delete_records(owner=owner, apply=True)
