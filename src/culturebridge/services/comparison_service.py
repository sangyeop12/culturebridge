import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from culturebridge.database import transaction
from culturebridge.domain.models import (
    CollectedSource,
    ComparisonResult,
    ComparisonScope,
    ExtractedField,
    LearningAmount,
    LearningGoal,
    LearningLevel,
    SavedComparison,
    SavedComparisonSummary,
    SourceRecord,
)
from culturebridge.services.catalog_service import compare_heritages, get_sources
from culturebridge.services.curriculum_service import GOAL_LABELS, plan_learning
from culturebridge.services.evidence_comparison_service import apply_extracted_comparison
from culturebridge.services.heritage_identity_service import canonical_id
from culturebridge.services.operation_service import can_read_resource, owner_key, private_session


class ComparisonNotFoundError(KeyError):
    pass


LEARNING_VERSION = 7


def create_saved_comparison(
    left_id: str,
    right_id: str,
    level: LearningLevel,
    path: Path | None = None,
    *,
    collected_sources: list[CollectedSource] | None = None,
    extracted_fields: list[ExtractedField] | None = None,
    goal: LearningGoal = LearningGoal.COMPARE,
    goal_text: str = "",
    curriculum: list[str] | None = None,
    amount: LearningAmount = LearningAmount.STANDARD,
    comparison_scope=None,
    reuse: bool = False,
) -> ComparisonResult:
    if canonical_id(left_id) == canonical_id(right_id):
        raise ValueError("별칭이 다른 같은 유산은 비교할 수 없습니다.")
    result = compare_heritages(left_id, right_id, level)
    result.learning_version = LEARNING_VERSION
    result.comparison_scope = ComparisonScope(comparison_scope) if comparison_scope else None
    result.collected_sources = collected_sources or []
    result.extracted_fields = extracted_fields or []
    result.goal, result.goal_text = goal, goal_text
    result.amount = amount
    result.curriculum = (
        curriculum if curriculum is not None else plan_learning(level, goal, goal_text, amount)[0]
    )
    result.learning_goal = GOAL_LABELS[goal.value] + " · 기본 예제 비교"
    if extracted_fields is not None:
        result.learning_goal = GOAL_LABELS[goal.value] + " · 공식 원문 근거와 한계 확인"
        result = apply_extracted_comparison(result)
    source_records = get_sources(result.source_ids)
    if result.basis == "extracted":
        source_records = [
            SourceRecord(
                id=s.id,
                title=s.title,
                organization=s.organization,
                url=s.source_url,
                retrieved_at=s.retrieved_at.date(),
                scope_note=s.scope_note,
            )
            for s in result.collected_sources
            if s.id in result.source_ids and s.retrieved_at
        ]
    result.saved_id = str(uuid4())
    saved = SavedComparison(
        id=result.saved_id,
        created_at=datetime.now(UTC),
        comparison=result,
        sources=source_records,
    )
    with transaction(path) as connection:
        identity = result.model_dump(mode="json", exclude={"saved_id"})
        for source in identity["collected_sources"]:
            source.pop("retrieved_at", None)
            if source["status"] in {"fresh", "cached"}:
                source["status"] = "available"
        fingerprint = hashlib.sha256(
            json.dumps(
                [owner_key(), identity],
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        if reuse:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT c.content_json FROM comparison_keys k JOIN comparisons c "
                "ON c.id=k.comparison_id WHERE k.fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if existing:
                return SavedComparison.model_validate_json(existing["content_json"]).comparison
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
        connection.execute(
            "INSERT OR IGNORE INTO comparison_keys VALUES(?,?)", (fingerprint, saved.id)
        )
        connection.execute(
            "INSERT INTO resource_owners VALUES('comparison',?,?)", (saved.id, owner_key())
        )
    return result


def get_saved_comparison(record_id: str, path: Path | None = None) -> SavedComparison:
    with transaction(path) as connection:
        row = connection.execute(
            "SELECT content_json FROM comparisons WHERE id = ?", (record_id,)
        ).fetchone()
    if row is None:
        raise ComparisonNotFoundError(record_id)
    with transaction(path) as connection:
        owner = connection.execute(
            "SELECT owner FROM resource_owners WHERE kind='comparison' AND id=?", (record_id,)
        ).fetchone()
    if not can_read_resource(owner["owner"] if owner else None):
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
            WHERE (? IS NULL OR id IN (
                SELECT id FROM resource_owners WHERE kind='comparison' AND owner=?))
            AND id NOT IN (SELECT id FROM resource_owners
                WHERE kind='comparison' AND owner LIKE 'kiosk:%' AND owner!=?)
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (
                owner_key() if private_session() else None,
                owner_key(),
                owner_key(),
                limit,
                offset,
            ),
        ).fetchall()
    return [SavedComparisonSummary(**dict(row)) for row in rows]
