from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from culturebridge.domain.models import LearningLevel
from culturebridge.services.catalog_service import recommend_related
from culturebridge.services.comparison_service import create_saved_comparison


class ExplorationState(TypedDict, total=False):
    heritage_id: str
    comparison_id: str
    level: str
    curriculum: list[str]
    candidates: list[dict]
    comparison: dict
    verification_status: str
    verification_note: str


def plan_curriculum(state: ExplorationState) -> ExplorationState:
    level = LearningLevel(state.get("level", LearningLevel.BEGINNER))
    plans = {
        LearningLevel.BEGINNER: ["형태 관찰", "재료 비교", "핵심 퀴즈"],
        LearningLevel.INTERMEDIATE: ["시대 확인", "구조 비교", "맥락 질문", "퀴즈"],
        LearningLevel.ADVANCED: ["출처 검토", "주장 분리", "비교 분석", "검증", "퀴즈"],
    }
    return {"curriculum": plans[level], "level": level.value}


def explore_history(state: ExplorationState) -> ExplorationState:
    candidates = recommend_related(state["heritage_id"])
    return {"candidates": [candidate.model_dump(mode="json") for candidate in candidates]}


def build_comparison(state: ExplorationState) -> ExplorationState:
    comparison_id = state.get("comparison_id")
    if not comparison_id:
        comparison_id = state["candidates"][0]["heritage"]["id"]
    result = create_saved_comparison(
        state["heritage_id"],
        comparison_id,
        LearningLevel(state["level"]),
    )
    return {"comparison_id": comparison_id, "comparison": result.model_dump(mode="json")}


def verify_claims(state: ExplorationState) -> ExplorationState:
    result = state["comparison"]
    return {
        "verification_status": result["verification_status"],
        "verification_note": result["verification_note"],
    }


def build_exploration_graph():
    graph = StateGraph(ExplorationState)
    graph.add_node("curriculum_agent", plan_curriculum)
    graph.add_node("history_agent", explore_history)
    graph.add_node("comparison_agent", build_comparison)
    graph.add_node("verification_agent", verify_claims)
    graph.add_edge(START, "curriculum_agent")
    graph.add_edge("curriculum_agent", "history_agent")
    graph.add_edge("history_agent", "comparison_agent")
    graph.add_edge("comparison_agent", "verification_agent")
    graph.add_edge("verification_agent", END)
    return graph.compile()


exploration_graph = build_exploration_graph()
