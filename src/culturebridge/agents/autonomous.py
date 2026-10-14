from pydantic import BaseModel, Field

from culturebridge.agents.workflow import exploration_graph
from culturebridge.domain.models import (
    CollectedSource,
    ComparisonResult,
    ComparisonScope,
    ExtractedField,
    HeritageDetail,
    LearningAmount,
    LearningGoal,
    LearningLevel,
    QuizPreview,
    RelatedHeritage,
    VerificationStatus,
)
from culturebridge.services.agent_discovery_service import discover_candidates
from culturebridge.services.comparison_scope_service import SCOPE_LABELS
from culturebridge.services.curriculum_service import required_categories
from culturebridge.services.dynamic_heritage_service import OfficialTarget, dynamic_source
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.official_page_service import cached_supplement


class AutonomousRequest(BaseModel):
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS
    target: OfficialTarget
    level: LearningLevel = LearningLevel.BEGINNER
    goal: LearningGoal = LearningGoal.COMPARE
    goal_text: str = Field(default="", max_length=200)
    amount: LearningAmount = LearningAmount.STANDARD


class AutonomousResult(BaseModel):
    comparison_scope: ComparisonScope = ComparisonScope.OVERSEAS
    target: HeritageDetail
    candidates: list[RelatedHeritage]
    execution_trace: list[str]
    used_ai_planner: bool
    comparison: ComparisonResult | None = None
    quiz: QuizPreview | None = None
    verification_status: VerificationStatus
    verification_note: str
    quiz_notice: str = ""
    collected_sources: list[CollectedSource] = Field(default_factory=list)
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    retry_count: int = 0
    curriculum: list[str] = Field(default_factory=list)


def run_autonomous(request: AutonomousRequest):
    detail, candidates, trace, used_ai = discover_candidates(
        request.target,
        request.goal.value + " " + request.goal_text,
        comparison_scope=request.comparison_scope,
    )
    result = {
        "comparison_scope": request.comparison_scope.value,
        "target": detail.model_dump(mode="json"),
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "execution_trace": trace,
        "used_ai_planner": used_ai,
        "comparison": None,
        "quiz": None,
        "verification_status": "insufficient_evidence",
        "verification_note": SCOPE_LABELS[request.comparison_scope.value]
        + " 범위에서 적합한 근거를 확보하지 못해 보류했습니다. 다른 범위로 자동 전환하지 않습니다.",
    }
    if not candidates:
        return result
    selected_source = dynamic_source(detail.id)
    evidence = _local_extraction([selected_source]) if selected_source else []
    selected_sources = [selected_source] if selected_source else []
    extra = cached_supplement(detail.id)
    if extra:
        selected_sources.append(extra)
        evidence.extend(_local_extraction([extra]))
    supported = {d.category for d in evidence if validate_extraction(d, selected_sources)}
    if (
        len(supported) < 2
        or not required_categories(request.goal.value + " " + request.goal_text) <= supported
    ):
        result["verification_note"] = (
            "비교 후보는 찾았지만 선택 유산 자체의 근거가 부족해 자동 비교를 보류했습니다."
        )
        result["execution_trace"].append(
            "verification_agent: 선택 대상의 직접 근거 부족·자동 선택 보류"
        )
        return result
    state = exploration_graph.invoke(
        {
            "heritage_id": detail.id,
            "comparison_id": candidates[0].heritage.id,
            "level": request.level.value,
            "goal": request.goal.value,
            "goal_text": request.goal_text,
            "amount": request.amount.value,
            "comparison_scope": request.comparison_scope.value,
        }
    )
    result.update(
        {
            key: state[key]
            for key in (
                "comparison",
                "quiz",
                "quiz_notice",
                "verification_status",
                "verification_note",
                "collected_sources",
                "extracted_fields",
                "retry_count",
                "curriculum",
            )
        }
    )
    result["execution_trace"] = trace + state["execution_trace"]
    return result
