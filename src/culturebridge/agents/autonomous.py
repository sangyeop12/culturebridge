from pydantic import BaseModel, Field

from culturebridge.agents.workflow import exploration_graph
from culturebridge.domain.models import (
    CollectedSource,
    ComparisonResult,
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
from culturebridge.services.dynamic_heritage_service import OfficialTarget


class AutonomousRequest(BaseModel):
    target: OfficialTarget
    level: LearningLevel = LearningLevel.BEGINNER
    goal: LearningGoal = LearningGoal.COMPARE
    goal_text: str = Field(default="", max_length=200)
    amount: LearningAmount = LearningAmount.STANDARD


class AutonomousResult(BaseModel):
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
        request.target, request.goal.value + " " + request.goal_text
    )
    result = {
        "target": detail.model_dump(mode="json"),
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "execution_trace": trace,
        "used_ai_planner": used_ai,
        "comparison": None,
        "quiz": None,
        "verification_status": "insufficient_evidence",
        "verification_note": "공식 자료에서 적합한 비교 후보를 확보하지 못해 판단을 보류했습니다.",
    }
    if not candidates:
        return result
    state = exploration_graph.invoke(
        {
            "heritage_id": detail.id,
            "comparison_id": candidates[0].heritage.id,
            "level": request.level.value,
            "goal": request.goal.value,
            "goal_text": request.goal_text,
            "amount": request.amount.value,
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
