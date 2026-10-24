"""Opt-in real-model planning probes, isolated from learner records.

Synthetic observations test planning only, not historical truth or learning effect.
Run with --live to use the configured Gemini account (normal API usage applies).
Never print the API key, raw provider errors, or real learner conversations.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from culturebridge.agents.learning import _model_decision
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningTurn
from culturebridge.services.learning_agent_tools import observe
from culturebridge.services.learning_conversation_service import create_conversation
from culturebridge.services.operation_service import clear_operation_cache, session_owner


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use configured Gemini account")
    parser.add_argument(
        "--case",
        action="append",
        choices=["empty_search", "assessment_progression", "quiz_selection"],
        help="Run selected scenarios only",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Actual API calls require --live")
    settings = get_settings()
    if not settings.gemini_enabled or not settings.gemini_api_key:
        print(json.dumps({"status": "unavailable", "reason": "AI is not configured"}))
        return
    previous_db = settings.db_path
    token = session_owner.set("synthetic-agent-planning-probe")
    try:
        with tempfile.TemporaryDirectory(prefix="culturebridge-agent-") as directory:
            settings.db_path = Path(directory) / "probe.db"
            initialize_database()
            for scenario in ("empty_search", "assessment_progression", "quiz_selection"):
                if args.case and scenario not in args.case:
                    continue
                conversation = create_conversation()
                conversation.goal = "문화유산의 재료 차이 이해하기"
                feedback = {}
                message = "해외 목탑을 찾아 비교해 주세요."
                if scenario == "empty_search":
                    observe(
                        conversation,
                        "search_world",
                        {"query": "wooden pagoda"},
                        "empty",
                        {"results": []},
                        planner="ai",
                    )
                elif scenario == "assessment_progression":
                    message = (
                        "화강암이라는 원문을 보고 돌로 만들었다고 설명했어요. "
                        "이어서 적절한 다른 재료의 사례를 골라 찾아 비교해 주세요."
                    )
                    conversation.sources = [
                        {
                            "id": "khs:11:0000200000000:37",
                            "name": "합성 학습 자료",
                            "url": "https://www.khs.go.kr/",
                            "reading_url": "/official",
                            "excerpts": [
                                {"concept": "재료", "quote": "이 탑은 화강암으로 만들었다."}
                            ],
                        }
                    ]
                    feedback = {
                        "judgment": "tentative_support",
                        "recorded": True,
                        "not_mastery": True,
                        "reason": "합성 평가 결과: 근거와 설명 일치",
                    }
                else:
                    message = "방금 비교한 내용으로 퀴즈를 풀고 싶어요."
                    conversation.learning_artifacts = [
                        {
                            "kind": "comparison",
                            "id": "synthetic-owned-comparison",
                            "left_id": "seokguram",
                            "right_id": "horyuji",
                            "suitable": True,
                            "level": "beginner",
                        }
                    ]
                    observe(
                        conversation,
                        "compare",
                        {},
                        "ok",
                        {
                            "comparison_id": "synthetic-owned-comparison",
                            "goal_suitable": True,
                            "shared_categories": ["재료", "시대"],
                        },
                        planner="ai",
                    )
                state = {
                    "conversation": conversation,
                    "seen": [],
                    "assessment_checked": True,
                    "understanding_feedback": feedback,
                    "request": LearningTurn(request_id=uuid4(), revision=0, text=message),
                    "deadline": time.monotonic() + settings.learning_turn_seconds,
                }
                try:
                    decision = _model_decision(state)
                    checks = {
                        "empty_search": decision.action in {"search", "search_world"}
                        and bool(decision.query.strip())
                        and decision.query != "wooden pagoda",
                        "assessment_progression": (
                            decision.action in {"search", "search_world"}
                            and bool(decision.query.strip())
                            or decision.action == "discover"
                            and decision.source_id in {s["id"] for s in conversation.sources}
                            and decision.comparison_scope == conversation.comparison_scope
                        )
                        and decision.assessment == "none",
                        "quiz_selection": decision.action == "quiz"
                        and decision.comparison_id == "synthetic-owned-comparison",
                    }
                    print(
                        json.dumps(
                            {
                                "scenario": scenario,
                                "status": "observed",
                                "action": decision.action,
                                "query": decision.query,
                                "source_id": decision.source_id,
                                "question": decision.question,
                                "reason": decision.reason,
                                "contract_met": checks[scenario],
                            },
                            ensure_ascii=False,
                        )
                    )
                except Exception as exc:
                    print(
                        json.dumps(
                            {
                                "scenario": scenario,
                                "status": "unavailable",
                                "error_type": type(exc).__name__,
                            }
                        )
                    )
    finally:
        settings.db_path = previous_db
        clear_operation_cache()
        session_owner.reset(token)


if __name__ == "__main__":
    run()
