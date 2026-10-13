from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from culturebridge.domain.models import CollectedSource, LearningLevel
from culturebridge.services.catalog_service import recommend_related
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.source_collection_service import collect_official_sources


class ExplorationState(TypedDict, total=False):
    heritage_id: str
    comparison_id: str
    level: str
    curriculum: list[str]
    candidates: list[dict]
    comparison: dict
    verification_status: str
    verification_note: str
    collected_sources: list[dict]
    extracted_fields: list[dict]


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
    comparison_id = state.get("comparison_id") or candidates[0].heritage.id
    sources = collect_official_sources(state["heritage_id"], comparison_id)
    return {
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "comparison_id": comparison_id,
        "collected_sources": [source.model_dump(mode="json") for source in sources],
    }


def build_comparison(state: ExplorationState) -> ExplorationState:
    comparison_id = state.get("comparison_id")
    if not comparison_id:
        comparison_id = state["candidates"][0]["heritage"]["id"]
    sources = [CollectedSource.model_validate(s) for s in state["collected_sources"]]
    extracted = extract_fields(sources, [state["heritage_id"], comparison_id])
    result = create_saved_comparison(
        state["heritage_id"],
        comparison_id,
        LearningLevel(state["level"]),
        collected_sources=sources,
        extracted_fields=extracted,
    )
    return {
        "comparison_id": comparison_id,
        "comparison": result.model_dump(mode="json"),
        "extracted_fields": [field.model_dump(mode="json") for field in extracted],
    }


def verify_claims(state: ExplorationState) -> ExplorationState:
    result = state["comparison"]
    incomplete = any(s["status"] in {"stale", "unavailable"} for s in state["collected_sources"])
    review_extraction = any(
        f["verification_status"] != "verified" for f in state["extracted_fields"]
    )
    return {
        "verification_status": "needs_review"
        if incomplete or review_extraction
        else result["verification_status"],
        "verification_note": result["verification_note"]
        + (
            " 일부 공식 자료가 오래되었거나 수집되지 않아 추가 확인이 필요합니다."
            if incomplete
            else ""
        )
        + (
            " 추출 항목은 원문 근거를 포함하며 의미 검토가 필요합니다." if review_extraction else ""
        ),
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
