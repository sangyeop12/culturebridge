from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from culturebridge.agents.quiz_agent import create_learning_quiz
from culturebridge.domain.models import (
    CollectedSource,
    ExtractedField,
    LearningAmount,
    LearningGoal,
    LearningLevel,
)
from culturebridge.services.catalog_service import recommend_related
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.curriculum_service import plan_learning
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.research_retry_service import retry_missing_sources
from culturebridge.services.source_collection_service import collect_official_sources


class ExplorationState(TypedDict, total=False):
    heritage_id: str
    comparison_id: str
    level: str
    goal: str
    goal_text: str
    amount: str
    curriculum: list[str]
    focus_categories: list[str]
    candidates: list[dict]
    comparison: dict
    verification_status: str
    verification_note: str
    collected_sources: list[dict]
    extracted_fields: list[dict]
    missing_heritages: list[str]
    retry_count: int
    execution_trace: list[str]
    quiz: dict | None
    quiz_notice: str


def plan_curriculum(state):
    level, goal = (
        LearningLevel(state.get("level", "beginner")),
        LearningGoal(state.get("goal", "compare")),
    )
    amount = LearningAmount(state.get("amount", "standard"))
    steps, focus = plan_learning(level, goal, state.get("goal_text", ""), amount)
    return {
        "level": level.value,
        "goal": goal.value,
        "amount": amount.value,
        "curriculum": steps,
        "focus_categories": focus,
        "retry_count": 0,
        "execution_trace": ["curriculum_agent: 수준·목표별 학습 계획"],
    }


def explore_history(state):
    candidates = recommend_related(state["heritage_id"], LearningGoal(state["goal"]))
    comparison_id = state.get("comparison_id") or candidates[0].heritage.id
    sources = collect_official_sources(state["heritage_id"], comparison_id)
    return {
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "comparison_id": comparison_id,
        "collected_sources": [s.model_dump(mode="json") for s in sources],
        "execution_trace": state["execution_trace"] + ["history_agent: 적합성 추천·공식 자료 수집"],
    }


def extract_evidence(state):
    sources = [CollectedSource.model_validate(s) for s in state["collected_sources"]]
    fields = extract_fields(sources, [state["heritage_id"], state["comparison_id"]])
    return {
        "extracted_fields": [f.model_dump(mode="json") for f in fields],
        "execution_trace": state["execution_trace"] + ["comparison_tool: 4개 항목 추출"],
    }


def verify_claims(state):
    fields = [ExtractedField.model_validate(f) for f in state["extracted_fields"]]
    missing = sorted(
        {f.heritage_id for f in fields if f.category in state["focus_categories"] and not f.value}
    )
    old_sources = any(s["status"] in {"stale", "unavailable"} for s in state["collected_sources"])
    note = "인용·출처 연결을 검사했습니다. 추출 후보의 의미 검토는 별도로 필요합니다."
    if missing or old_sources:
        note += " 목표 항목의 근거가 부족하거나 수집되지 않은 자료가 있습니다."
    return {
        "missing_heritages": missing,
        "verification_status": "needs_review",
        "verification_note": note,
        "execution_trace": state["execution_trace"] + ["verification_agent: 근거·범위 점검"],
    }


def select_verification_path(state):
    old_sources = any(s["status"] in {"stale", "unavailable"} for s in state["collected_sources"])
    return (
        "retry"
        if (state["missing_heritages"] or old_sources) and state["retry_count"] < 1
        else "finish"
    )


def retry_research(state):
    sources = retry_missing_sources(
        state["heritage_id"],
        state["comparison_id"],
        [CollectedSource.model_validate(s) for s in state["collected_sources"]],
        state["missing_heritages"],
    )
    return {
        "collected_sources": [s.model_dump(mode="json") for s in sources],
        "retry_count": state["retry_count"] + 1,
        "execution_trace": state["execution_trace"]
        + ["research_retry_tool: 공식 출처 재조회·추가 출처 1회"],
    }


def build_comparison(state):
    result = create_saved_comparison(
        state["heritage_id"],
        state["comparison_id"],
        LearningLevel(state["level"]),
        collected_sources=[CollectedSource.model_validate(s) for s in state["collected_sources"]],
        extracted_fields=[ExtractedField.model_validate(f) for f in state["extracted_fields"]],
        goal=LearningGoal(state["goal"]),
        goal_text=state.get("goal_text", ""),
        curriculum=state["curriculum"],
        amount=LearningAmount(state["amount"]),
    )
    return {
        "comparison": result.model_dump(mode="json"),
        "verification_status": result.verification_status.value,
        "verification_note": state["verification_note"]
        + (
            " 재검색 후에도 부족한 항목은 판단을 보류했습니다."
            if state["missing_heritages"]
            else ""
        ),
        "execution_trace": state["execution_trace"] + ["comparison_tool: 근거별 비교·공통점·저장"],
    }


def build_exploration_graph():
    graph = StateGraph(ExplorationState)
    for name, node in [
        ("curriculum_agent", plan_curriculum),
        ("history_agent", explore_history),
        ("extract_tool", extract_evidence),
        ("verification_agent", verify_claims),
        ("retry_tool", retry_research),
        ("compare_tool", build_comparison),
        ("quiz_agent", create_learning_quiz),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "curriculum_agent")
    graph.add_edge("curriculum_agent", "history_agent")
    graph.add_edge("history_agent", "extract_tool")
    graph.add_edge("extract_tool", "verification_agent")
    graph.add_conditional_edges(
        "verification_agent",
        select_verification_path,
        {"retry": "retry_tool", "finish": "compare_tool"},
    )
    graph.add_edge("retry_tool", "extract_tool")
    graph.add_edge("compare_tool", "quiz_agent")
    graph.add_edge("quiz_agent", END)
    return graph.compile()


exploration_graph = build_exploration_graph()
