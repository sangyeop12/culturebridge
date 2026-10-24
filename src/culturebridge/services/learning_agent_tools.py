"""Owned, allowlisted educational tools for the conversational planner.

The planner chooses arguments and order. Tools enforce evidence, scope and ownership;
their observations describe executed work, never hidden reasoning or mastery claims.
"""

import re
import time
from typing import Literal

from pydantic import create_model

from culturebridge.domain.models import LearningLevel

TOOLS = {
    "search": "국가유산청 대상명 검색(query)",
    "search_world": "등록 해외 유산·UNESCO 목록 검색(query)",
    "search_history": "신편 한국사 제목·공식 링크 검색(query); 본문 근거 아님",
    "read": "검색 결과의 개별 원문 읽기(source_id)",
    "define": "표준국어대사전 뜻 조회(query)",
    "discover": "알려진 유산의 비교 후보 찾기(source_id,goal,comparison_scope)",
    "compare": "알려진 두 유산 근거 비교(source_id,target_id,goal_mode,level); 퀴즈는 별도 선택",
    "quiz": "이 대화의 비교 저장본으로 확인 퀴즈 준비(comparison_id); 학습자 답을 기다림",
    "review_quiz": "이 대화에서 채점한 오답의 근거 불러오기(review_number); 다음 설명은 다시 계획",
}
NO_TARGET = "__none__"


def planning_tools(conversation):
    """Expose executable capabilities, while retaining independent runtime guards."""
    from culturebridge.domain.learning import LearningDecision

    known = {
        identity: row
        for identity, row in known_targets(conversation).items()
        if not row.get("metadata_only")
    }
    individuals = [identity for identity in known if not identity.startswith("quiz-review:")]
    comparisons = [
        a["id"]
        for a in conversation.learning_artifacts
        if a.get("kind") == "comparison" and a.get("suitable")
    ]
    enabled = {
        k: v
        for k, v in TOOLS.items()
        if k in {"search", "search_world", "search_history", "define"}
    }
    for name, condition in {
        "read": bool(known),
        "discover": bool(individuals),
        "compare": len(individuals) >= 2,
        "quiz": bool(comparisons)
        and not (conversation.active_quiz and not conversation.active_quiz.get("submitted")),
        "review_quiz": bool(conversation.active_quiz.get("history_id")),
    }.items():
        if condition:
            enabled[name] = TOOLS[name]
    actions = list(enabled) + ["ask", "references", "explain", "check", "review", "stop", "finish"]
    schema = create_model(
        "AvailableLearningDecision",
        __base__=LearningDecision,
        action=(Literal[tuple(actions)], ...),
        source_id=(Literal[tuple([NO_TARGET] + list(known))], NO_TARGET),
        target_id=(Literal[tuple([NO_TARGET] + individuals)], NO_TARGET),
        comparison_id=(Literal[tuple([NO_TARGET] + comparisons)], NO_TARGET),
    )
    constraints = {
        "readable_ids": list(known),
        "individual_ids": individuals,
        "quiz_comparison_ids": comparisons,
        "comparison_scope": conversation.comparison_scope,
        "unused_id": NO_TARGET,
        "rule": "관찰한 ID만 그대로 사용하고, 아직 없으면 먼저 검색한다.",
    }
    return enabled, constraints, schema


def arguments(decision):
    fields = {
        "search": ("query",),
        "search_world": ("query",),
        "search_history": ("query",),
        "define": ("query",),
        "read": ("source_id",),
        "discover": ("source_id", "goal_mode", "goal", "query", "comparison_scope"),
        "compare": ("source_id", "target_id", "goal_mode", "goal", "level", "comparison_scope"),
        "quiz": ("comparison_id",),
        "review_quiz": ("review_number",),
    }
    return {
        key: value
        for key in fields.get(decision.action, ())
        if (value := getattr(decision, key, "")) not in ("", 0)
    }


def action_key(decision):
    import json

    return decision.action + ":" + json.dumps(arguments(decision), sort_keys=True)


def observe(conversation, action, args, status, summary, *, reason="", planner="system"):
    entry = {
        "tool": action,
        "arguments": args,
        "status": status,
        "summary": summary,
        "reason": reason[:300],
        "planner": planner,
        "revision": conversation.revision,
    }
    conversation.tool_observations = (conversation.tool_observations + [entry])[-24:]
    return entry


def known_targets(conversation):
    rows = {row["id"]: row for row in conversation.search_results + conversation.sources}
    for artifact in conversation.learning_artifacts:
        for row in artifact.get("targets", []):
            rows[row["id"]] = row
    return rows


def target(identity):
    from culturebridge.services.dynamic_heritage_service import OfficialTarget
    from culturebridge.services.heritage_identity_service import canonical_id

    identity = canonical_id(identity)
    provider, rest = identity.split(":", 1)
    if provider == "official":
        return OfficialTarget(provider=provider, official_id=rest)
    if provider == "unesco":
        return OfficialTarget(provider=provider, record_id=rest)
    kind, number, region = rest.split(":")
    return OfficialTarget(provider=provider, kind=kind, number=number, region=region)


def requested_comparison_ids(conversation):
    """Keep explicitly named, observed targets; never infer an unknown identity."""
    from culturebridge.services.conversation_source_policy import current_topic_messages
    from culturebridge.services.display_service import short_display_name

    texts = [m.text for m in current_topic_messages(conversation) if m.role == "user"]
    texts.append(conversation.pending_request)
    for text in reversed(texts):
        if "비교" not in text:
            continue
        # Negation/correction needs semantic planning, not a positive substring constraint.
        if re.search(r"말고|제외|아닌|대신|not\b|instead\b|rather than", text, re.I):
            return []
        matches = []
        for identity, row in known_targets(conversation).items():
            name = short_display_name(row.get("name", ""))
            if len(name) >= 2 and name in text and not row.get("metadata_only"):
                matches.append(identity)
        if matches:
            return matches
    return []


def run_tool(conversation, decision, deadline):
    """Return a bounded structured observation, without running a fixed lesson pipeline."""
    if time.monotonic() >= deadline:
        return "budget", {"message": "이번 실행의 시간 범위에 도달했어요."}
    known = known_targets(conversation)
    if decision.action in {"discover", "compare"}:
        if decision.comparison_scope != conversation.comparison_scope:
            return "blocked", {
                "message": "사용자가 정한 비교 범위를 AI가 자동 변경하지 않아요.",
                "comparison_scope": conversation.comparison_scope,
            }
    if decision.action in {"discover", "compare"}:
        identities = [decision.source_id]
        if decision.action == "compare":
            identities.append(decision.target_id)
        if any(
            identity not in known or known[identity].get("metadata_only") for identity in identities
        ):
            return "blocked", {"message": "현재 검색·자료·후보에서 확인한 개별 유산 ID만 사용해요."}
    if decision.action == "compare":
        requested = requested_comparison_ids(conversation)
        if not set(requested).issubset({decision.source_id, decision.target_id}):
            return "blocked", {
                "message": (
                    "사용자가 지정한 유산을 포함해 비교해야 해요. 기준 대상을 유지해 주세요."
                ),
                "required_ids": requested,
            }
    if decision.action == "discover":
        from culturebridge.services.agent_discovery_service import discover_candidates
        from culturebridge.services.display_service import readable_reason

        detail, candidates, _, _ = discover_candidates(
            target(decision.source_id),
            decision.goal_mode + " " + (decision.goal or conversation.goal) + " " + decision.query,
            comparison_scope=decision.comparison_scope,
        )
        rows = [
            {
                "id": c.heritage.id,
                "name": c.heritage.name,
                "country": c.heritage.country,
                "metadata_only": c.heritage.id.startswith("unesco:"),
                "recommendation_reason": readable_reason(c.criteria),
            }
            for c in candidates[:3]
        ]
        conversation.learning_artifacts = (
            conversation.learning_artifacts
            + [
                {
                    "kind": "candidates",
                    "source_id": decision.source_id,
                    "targets": [{"id": detail.id, "name": detail.name}] + rows,
                }
            ]
        )[-8:]
        return ("ok" if rows else "empty"), {"candidates": rows, "target_id": detail.id}
    if decision.action == "compare":
        from culturebridge.agents.workflow import run_exploration
        from culturebridge.services.catalog_service import get_heritage
        from culturebridge.services.curriculum_service import evidence_suits_goal
        from culturebridge.services.dynamic_heritage_service import fetch_target
        from culturebridge.services.evidence_comparison_service import supported_fields

        # Resolve only tool-observed IDs; never a model-supplied URL or unobserved ID.
        for identity in (decision.source_id, decision.target_id):
            try:
                get_heritage(identity)
            except KeyError:
                fetch_target(target(identity))
        state = run_exploration(
            {
                "heritage_id": decision.source_id,
                "comparison_id": decision.target_id,
                "level": decision.level,
                "goal": decision.goal_mode,
                "goal_text": (decision.goal or conversation.goal)[:200],
                "amount": "standard",
                "comparison_scope": decision.comparison_scope,
                "generate_quiz": False,
            }
        )
        from culturebridge.domain.models import ComparisonResult

        result = ComparisonResult.model_validate(state["comparison"])
        fields = supported_fields(result)
        left = {f.category for f in fields if f.heritage_id == result.left.id}
        right = {f.category for f in fields if f.heritage_id == result.right.id}
        suitable = evidence_suits_goal(left, right, result.goal.value + " " + result.goal_text)
        artifact = {
            "kind": "comparison",
            "id": result.saved_id,
            "left_id": result.left.id,
            "right_id": result.right.id,
            "targets": [{"id": h.id, "name": h.name} for h in (result.left, result.right)],
            "suitable": suitable,
            "level": result.level.value,
            "url": f"/compare/{result.left.id}/{result.right.id}?saved_id={result.saved_id}",
        }
        conversation.learning_artifacts = (conversation.learning_artifacts + [artifact])[-8:]
        return ("ok" if suitable else "insufficient"), {
            "comparison_id": result.saved_id,
            "shared_categories": sorted(left & right),
            "missing_on_left": sorted(right - left),
            "missing_on_right": sorted(left - right),
            "goal_suitable": suitable,
            "verification_status": result.verification_status.value,
        }
    if decision.action == "quiz":
        from culturebridge.services.quiz_service import generate_quiz

        artifact = next(
            (
                a
                for a in reversed(conversation.learning_artifacts)
                if a.get("kind") == "comparison" and a["id"] == decision.comparison_id
            ),
            None,
        )
        if artifact is None or not artifact["suitable"]:
            return "blocked", {"message": "이 대화에서 목표 근거를 확보한 비교 저장본이 필요해요."}
        require_owned("comparison", artifact["id"])
        if conversation.active_quiz and not conversation.active_quiz.get("submitted"):
            return "waiting", {"message": "준비된 퀴즈에 학습자가 답할 차례예요."}
        quiz = generate_quiz(
            artifact["left_id"],
            artifact["right_id"],
            LearningLevel(artifact["level"]),
            comparison_id=artifact["id"],
            reuse=True,
        )
        conversation.active_quiz = {
            "id": quiz.quiz_id,
            "submitted": False,
            "items": [
                {
                    "question": item.question,
                    "choices": [choice.model_dump() for choice in item.choices],
                }
                for item in quiz.items
            ],
        }
        conversation.checkpoint = {}
        conversation.quiz_review = {}
        conversation.goal_status = "practising"
        return "ok", {
            "quiz_id": quiz.quiz_id,
            "questions": len(quiz.items),
            "awaiting_learner": True,
        }
    if decision.action == "review_quiz":
        from culturebridge.database import transaction
        from culturebridge.services.conversation_review_service import owned_review, seed_review

        history_id = conversation.active_quiz.get("history_id")
        if not history_id:
            return "blocked", {"message": "이 대화에서 제출한 퀴즈 기록이 필요해요."}
        with transaction() as connection:
            result, score, total = owned_review(connection, history_id)
        # Reuse the existing evidence matching without discarding this conversation's history.
        temporary = conversation.model_copy(deep=True)
        temporary.messages, temporary.topic_start = [], 0
        seed_review(temporary, history_id, result, score, total)
        if decision.review_number:
            selected = next(
                (
                    item
                    for item in temporary.quiz_review["items"]
                    if item["number"] == decision.review_number
                ),
                None,
            )
            if selected is None:
                return "blocked", {"message": "실제 오답 목록의 문항 번호만 선택할 수 있어요."}
            temporary.sources = [
                source for source in temporary.sources if source["id"] == selected["source_id"]
            ]
            temporary.quiz_review["current_number"] = selected["number"]
        conversation.quiz_review, conversation.sources = temporary.quiz_review, temporary.sources
        # The planner must first teach/ask; no answer was provided yet.
        conversation.checkpoint = {}
        conversation.goal_status = "reviewing"
        return "ok", {
            "review_sources": [
                {"id": s["id"], "concepts": [e["concept"] for e in s["excerpts"]]}
                for s in conversation.sources
            ],
            "wrong_questions": [i["number"] for i in conversation.quiz_review["items"]],
        }
    raise ValueError("지원하지 않는 학습 도구입니다.")


def submit_quiz(conversation, answers):
    from culturebridge.services.quiz_service import grade_quiz

    quiz = conversation.active_quiz
    if not quiz or quiz.get("submitted") or len(answers) != len(quiz["items"]):
        raise ValueError("현재 대화의 퀴즈 모든 문항에 답해 주세요.")
    require_owned("quiz", quiz["id"])
    result = grade_quiz(quiz["id"], answers)
    quiz.update(
        submitted=True, score=result.score, total=result.total, history_id=result.history_id
    )
    conversation.checkpoint = {}
    conversation.goal_status = "reviewing" if result.score < result.total else "exploring"
    observe(
        conversation,
        "submit_quiz",
        {"quiz_id": quiz["id"]},
        "ok",
        {"score": result.score, "total": result.total, "not_mastery": True},
        planner="learner",
    )


def require_owned(kind, identity):
    from culturebridge.database import transaction
    from culturebridge.services.operation_service import owner_key

    with transaction() as connection:
        row = connection.execute(
            "SELECT owner FROM resource_owners WHERE kind=? AND id=?", (kind, identity)
        ).fetchone()
    if row is None or row["owner"] != owner_key():
        raise ValueError("이 학습자의 저장 자료만 사용할 수 있어요.")
