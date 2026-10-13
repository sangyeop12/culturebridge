from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from culturebridge.database import transaction
from culturebridge.domain.models import (
    ComparisonResult,
    LearningLevel,
    SavedComparison,
    SavedComparisonSummary,
)
from culturebridge.services.catalog_service import compare_heritages, get_sources


class ComparisonNotFoundError(KeyError):
    pass


def create_saved_comparison(
    left_id: str,
    right_id: str,
    level: LearningLevel,
    path: Path | None = None,
) -> ComparisonResult:
    result = compare_heritages(left_id, right_id, level)
    result.saved_id = str(uuid4())
    saved = SavedComparison(
        id=result.saved_id,
        created_at=datetime.now(UTC),
        comparison=result,
        sources=get_sources(result.source_ids),
    )
    with transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO comparisons
                (id, left_id, right_id, level, content_json, verification_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                saved.id,
                left_id,
                right_id,
                level.value,
                saved.model_dump_json(),
                result.verification_status.value,
                saved.created_at.isoformat(),
            ),
        )
    return result


def get_saved_comparison(record_id: str, path: Path | None = None) -> SavedComparison:
    with transaction(path) as connection:
        row = connection.execute(
            "SELECT content_json FROM comparisons WHERE id = ?", (record_id,)
        ).fetchone()
    if row is None:
        raise ComparisonNotFoundError(record_id)
    return SavedComparison.model_validate_json(row["content_json"])


def list_saved_comparisons(
    limit: int = 20, offset: int = 0, path: Path | None = None
) -> list[SavedComparisonSummary]:
    with transaction(path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at,
                json_extract(content_json, '$.comparison.left.name') AS left_name,
                json_extract(content_json, '$.comparison.right.name') AS right_name,
                level
            FROM comparisons
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [SavedComparisonSummary(**dict(row)) for row in rows]
