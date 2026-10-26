"""Opt-in multi-turn live service checks, using a separate database.

No model responses, searches or source texts are replaced. Test messages and fixed
tester quiz answers are synthetic; this is not a study involving actual students.
The wrapper counts real SDK invocations and stops further calls on 429 or budget.
Output may contain public-source learning text; keep it in ignored outputs/.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from google import genai

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningTurn
from culturebridge.services.agent_evaluation_service import evaluate_report
from culturebridge.services.learning_conversation_service import (
    create_conversation,
    send_learning_turn,
)
from culturebridge.services.learning_outcome_service import outcome_summary
from culturebridge.services.operation_service import clear_operation_cache, session_owner

SCENARIOS = {
    "open_start": ["안녕하세요. 역사를 잘 모르는데 어디서부터 시작하면 좋을까요?"],
    "korean_reading": [
        "경주 불국사 다보탑을 찾아서 무엇으로 만들었는지 공식 자료로 쉽게 설명해 주세요.",
        "좀 더 쉽게 설명하고, 제가 이해했는지 확인할 질문도 해 주세요.",
    ],
    "overseas_comparison": [
        "경주 불국사 다보탑과 비교할 해외 탑을 직접 골라서 "
        "시대와 재료를 비교하고 퀴즈도 준비해 주세요.",
        "찾은 자료와 비교 후보로 계속 진행해 주세요. 대상을 직접 골라 주세요.",
        "공식 근거가 충분한 비교라면 퀴즈를 준비해 주세요. "
        "부족하면 다른 적절한 후보를 찾아 주세요.",
    ],
    "history_references": ["세종대왕의 훈민정음 창제에 관한 공식 자료를 찾아 주세요."],
    "unknown_target": [
        "실제로 없는 이름인 별빛999석탑을 찾아 설명해 주세요. 없으면 없다고 알려 주세요."
    ],
    "topic_change": [
        "경주 불국사 다보탑의 구조가 궁금해요. 공식 자료를 찾아 쉽게 설명해 주세요.",
        "다보탑 이야기는 그만하고 세종대왕의 한글 창제 자료를 찾아 주세요.",
    ],
    "comparison_rephrased": [
        "다보탑을 기준으로 해외 유산과 시대와 재료를 비교하고 퀴즈까지 준비해 주세요.",
        "기준 유산은 유지하고 적절한 후보를 직접 골라 계속 진행해 주세요.",
    ],
    "palace_comparison": [
        "경복궁과 해외 궁전을 구조와 재료로 비교하고 퀴즈도 준비해 주세요.",
        "찾은 후보 가운데 근거가 충분한 대상으로 이어가 주세요.",
    ],
    "tomb_comparison": [
        "무령왕릉과 해외 무덤을 시대와 구조로 비교하고 퀴즈도 준비해 주세요.",
        "근거가 부족하면 다른 후보를 찾아서 계속해 주세요.",
    ],
}

EXPECTATIONS = {
    "korean_reading": {
        "explanation": True,
        "source_id": "khs:11:0000200000000:37",
        "concept": "재료",
        "minimum_turns": 2,
        "checkpoint": True,
    },
    "overseas_comparison": {
        "anchor_ids": ["khs:11:0000200000000:37"],
        "categories": ["시대", "재료"],
    },
    "comparison_rephrased": {"anchor_name": "다보탑", "categories": ["시대", "재료"]},
    "palace_comparison": {"anchor_name": "경복궁", "categories": ["구조", "재료"]},
    "tomb_comparison": {"anchor_name": "무령왕릉", "categories": ["시대", "구조"]},
}


class CallBudget:
    def __init__(self, limit):
        self.limit, self.calls, self.rate_limited = limit, [], False
        self.original = genai.Client

    def client(self, **kwargs):
        budget = self
        actual = self.original(**kwargs)

        class WrappedClient:
            def __enter__(self):
                entered = actual.__enter__()

                def generate(**options):
                    if budget.rate_limited or len(budget.calls) >= budget.limit:
                        raise ValueError("live_check_call_budget")
                    schema = getattr(options.get("config"), "response_schema", None)
                    entry = {"schema": getattr(schema, "__name__", "unknown"), "status": "started"}
                    budget.calls.append(entry)
                    try:
                        response = entered.models.generate_content(**options)
                        entry["status"] = "response"
                        usage = getattr(response, "usage_metadata", None)
                        if usage is not None:
                            entry["usage"] = {
                                key: getattr(usage, key, None)
                                for key in (
                                    "prompt_token_count",
                                    "candidates_token_count",
                                    "thoughts_token_count",
                                    "cached_content_token_count",
                                    "total_token_count",
                                )
                            }
                        return response
                    except Exception as exc:
                        code = getattr(exc, "code", None)
                        entry.update(status="error", error_type=type(exc).__name__, code=code)
                        if code == 400:
                            # Request-format diagnostics only; never dump credentials or payloads.
                            entry["request_error"] = str(getattr(exc, "message", ""))[:1400]
                        budget.rate_limited = str(code) == "429"
                        if budget.rate_limited:
                            data = getattr(exc, "details", {})
                            items = (
                                data.get("error", data).get("details", [])
                                if isinstance(data, dict)
                                else []
                            )
                            entry["quota"] = [
                                {key: detail[key] for key in ("retryDelay",) if key in detail}
                                | {
                                    "limits": [
                                        {
                                            key: item[key]
                                            for key in ("quotaMetric", "quotaId", "quotaValue")
                                            if key in item
                                        }
                                        for item in detail.get("violations", [])
                                    ]
                                }
                                for detail in items
                                if isinstance(detail, dict)
                            ]
                        raise

                return SimpleNamespace(models=SimpleNamespace(generate_content=generate))

            def __exit__(self, *args):
                return actual.__exit__(*args)

        return WrappedClient()


def execute_turn(state, text, *, control="message", answers=None):
    before = state.revision
    started = time.monotonic()
    state = send_learning_turn(
        state.id,
        LearningTurn(
            request_id=uuid4(), revision=before, text=text, control=control, answers=answers or []
        ),
    )
    last = state.messages[-1]
    observations = [o for o in state.tool_observations if o["revision"] == before]
    record = {
        "input": text,
        "control": control,
        "seconds": round(time.monotonic() - started, 2),
        "revision": state.revision,
        "notice": state.notice,
        "action": state.plan_history[-1].get("action") if state.plan_history else None,
        "planner": state.plan_history[-1].get("planner") if state.plan_history else None,
        "selected_concept": state.plan_history[-1].get("concept") if state.plan_history else None,
        "teaching": last.teaching,
        "observations": observations,
        "assistant": last.text,
        "citation_count": len(last.citations),
        "citation_sources": [c.get("url") for c in last.citations],
        "citations": last.citations,
        "checkpoint": bool(state.checkpoint),
        "task_contract": state.task_contract,
        "pending_request_retained": bool(state.pending_request),
        "comparison_count": sum(a.get("kind") == "comparison" for a in state.learning_artifacts),
        "quiz_prepared": bool(state.active_quiz),
        "quiz_submitted": bool(state.active_quiz.get("submitted")),
        "quiz_review": bool(state.quiz_review),
        "concept_judgments": {k: v["status"] for k, v in state.concepts.items()},
        "outcomes": outcome_summary(state),
        "comparison_artifacts": [
            a for a in state.learning_artifacts if a.get("kind") == "comparison"
        ],
    }
    print(
        json.dumps(
            {
                k: record[k]
                for k in (
                    "revision",
                    "seconds",
                    "action",
                    "planner",
                    "citation_count",
                    "comparison_count",
                    "quiz_prepared",
                    "quiz_submitted",
                    "quiz_review",
                )
            }
            | {"tools": [o["tool"] + ":" + o["status"] for o in observations]},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return state, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", action="append", choices=SCENARIOS)
    parser.add_argument("--max-calls", type=int, default=40, choices=range(1, 61))
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 11))
    parser.add_argument("--turn-delay-seconds", type=int, default=0, choices=range(61))
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    args = parser.parse_args()
    # Reject invalid price inputs before making any paid/limited external request.
    evaluate_report(
        {}, input_rate=args.input_usd_per_million, output_rate=args.output_usd_per_million
    )
    settings = get_settings()
    if not settings.gemini_enabled or not settings.gemini_api_key:
        parser.error("Gemini is not configured; no live calls made")
    report_path = args.output.resolve()
    database_path = report_path.with_suffix(".db")
    if (
        report_path.exists()
        or database_path.exists()
        or database_path == settings.db_path.resolve()
    ):
        parser.error("Use new report/database paths, separate from learner storage")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    previous = settings.db_path
    settings.db_path = database_path
    budget = CallBudget(args.max_calls)
    report = {
        "kind": "live_models_and_sources_synthetic_learner_not_learning_effect_study",
        "started_at": datetime.now(UTC).isoformat(),
        "model": settings.gemini_model,
        "max_sdk_calls": args.max_calls,
        "turn_delay_seconds": args.turn_delay_seconds,
        "runs": [],
    }
    last_turn = None

    def checked_turn(*positional, **keywords):
        nonlocal last_turn
        if last_turn is not None and args.turn_delay_seconds:
            remaining = args.turn_delay_seconds - (time.monotonic() - last_turn)
            if remaining > 0:
                print(
                    json.dumps({"waiting_before_next_turn_seconds": round(remaining)}), flush=True
                )
                while remaining > 0:
                    time.sleep(min(remaining, 10))
                    remaining = args.turn_delay_seconds - (time.monotonic() - last_turn)
        result = execute_turn(*positional, **keywords)
        last_turn = time.monotonic()
        return result

    try:
        initialize_database()
        with patch.object(genai, "Client", budget.client):
            for repetition in range(args.repeat):
                for name in args.scenario or SCENARIOS:
                    run = {"scenario": name, "repetition": repetition + 1, "turns": []}
                    if name in EXPECTATIONS:
                        run["expectations"] = {
                            **(
                                {"comparison": True, "quiz": True, "review": True}
                                if name != "korean_reading"
                                else {}
                            ),
                            **EXPECTATIONS[name],
                        }
                    report["runs"].append(run)
                    if budget.rate_limited or len(budget.calls) >= budget.limit:
                        run["not_run"] = "provider_rate_limit_or_call_budget"
                        continue
                    token = session_owner.set(f"live-agent-check:{name}:{repetition}:{uuid4()}")
                    print(json.dumps({"scenario": name, "repetition": repetition + 1}), flush=True)
                    try:
                        state = create_conversation()
                        for text in SCENARIOS[name]:
                            if budget.rate_limited or len(budget.calls) >= budget.limit:
                                run["remaining_not_run"] = "provider_rate_limit_or_call_budget"
                                break
                            state, result = checked_turn(state, text)
                            run["turns"].append(result)
                            if state.active_quiz and not state.active_quiz.get("submitted"):
                                if budget.rate_limited or len(budget.calls) >= budget.limit:
                                    run["remaining_not_run"] = "provider_rate_limit_or_call_budget"
                                    break
                                # Fixed tester answers; no model choice or answer-key lookup.
                                answers = [i % 4 for i in range(len(state.active_quiz["items"]))]
                                state, result = checked_turn(
                                    state, "", control="submit_quiz", answers=answers
                                )
                                result["tester_answers"] = (
                                    "fixed cyclic choice indices, not real learner"
                                )
                                run["turns"].append(result)
                                if not budget.rate_limited and len(budget.calls) < budget.limit:
                                    state, result = checked_turn(
                                        state, "틀린 문항의 근거를 확인하고 다시 설명해 주세요."
                                    )
                                    run["turns"].append(result)
                                break
                    except Exception as exc:
                        run["error_type"] = type(exc).__name__
                    finally:
                        run["provider_rate_limited"] = budget.rate_limited
                        clear_operation_cache()
                        session_owner.reset(token)
                        report["sdk_calls"] = budget.calls
                        report_path.write_text(
                            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
    finally:
        report["sdk_calls"] = budget.calls
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["metrics"] = evaluate_report(
            report, input_rate=args.input_usd_per_million, output_rate=args.output_usd_per_million
        )
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        settings.db_path = previous
    print(
        json.dumps(
            {
                "report": str(report_path),
                "sdk_calls": len(budget.calls),
                "rate_limited": budget.rate_limited,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
