import json

from culturebridge.config import get_settings
from culturebridge.database import transaction
from culturebridge.services.operation_service import owner_key, session_owner


def list_learning_reviews(limit=20, offset=0):
    private = get_settings().public_mode and session_owner.get()
    with transaction() as connection:
        rows = connection.execute(
            """SELECT h.id,h.level,h.score,h.total,h.created_at,r.quiz_id,r.result_json,
            c.name AS heritage_name,
            (SELECT comparison_id FROM quiz_items WHERE quiz_id=r.quiz_id LIMIT 1) AS comparison_id
            FROM learning_history h JOIN learning_reviews r ON r.history_id=h.id
            JOIN heritages c ON c.id=h.heritage_id
            WHERE (? IS NULL OR r.owner=?) ORDER BY h.id DESC LIMIT ? OFFSET ?""",
            (owner_key() if private else None, owner_key(), limit, offset),
        ).fetchall()
    return [{**dict(row), "result": json.loads(row["result_json"])} for row in rows]
