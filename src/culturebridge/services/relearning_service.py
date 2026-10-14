"""Recollect and re-extract into a new snapshot; never mutate archived learning."""

from culturebridge.services.comparison_service import create_saved_comparison, get_saved_comparison
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.operation_service import reused_operation
from culturebridge.services.source_collection_service import collect_official_sources


@reused_operation("relearn")
def relearn_saved_comparison(record_id):
    previous = get_saved_comparison(record_id).comparison
    sources = collect_official_sources(previous.left.id, previous.right.id, refresh=True)
    fields = extract_fields(sources, [previous.left.id, previous.right.id])
    return create_saved_comparison(
        previous.left.id,
        previous.right.id,
        previous.level,
        collected_sources=sources,
        extracted_fields=fields,
        goal=previous.goal,
        goal_text=previous.goal_text,
        amount=previous.amount,
        comparison_scope=previous.comparison_scope,
        reuse=False,
    )
