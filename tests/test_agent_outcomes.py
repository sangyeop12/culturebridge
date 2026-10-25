"""Deterministic checks of protection/measurement, not real-model or learning-effect results."""

import time
from uuid import uuid4

import pytest

from culturebridge.domain.learning import LearningConversation, LearningDecision
from culturebridge.services.agent_evaluation_service import evaluate_report
from culturebridge.services.learning_agent_tools import run_tool
from culturebridge.services.learning_outcome_service import (
    anchored_ids,
    outcome_summary,
    update_contract,
)


def conversation():
    return LearningConversation(id=uuid4(), revision=0)


@pytest.mark.parametrize("subject", ["다보탑", "석굴암", "경복궁", "무령왕릉"])
def test_anchor_survives_continuation_and_unknown_subject_blocks_comparison(subject):
    state = conversation()
    update_contract(state, f"{subject}과 해외 유산을 시대와 재료로 비교하고 퀴즈도 준비해 주세요")
    update_contract(state, "찾은 후보로 계속 진행해 주세요")
    assert state.task_contract["subject"] == subject
    assert state.task_contract["categories"] == ["시대", "재료"]
    state.search_results = [
        {"id": "official:a", "name": "외국 유산 A"},
        {"id": "official:b", "name": "외국 유산 B"},
    ]
    decision = LearningDecision(action="compare", source_id="official:a", target_id="official:b")
    status, observation = run_tool(state, decision, time.monotonic() + 5)
    assert status == "blocked" and observation["search_subject"] == subject
    state.search_results.append({"id": "official:anchor", "name": f"경주 {subject}"})
    assert anchored_ids(state, {r["id"]: r for r in state.search_results}) == ["official:anchor"]
    status, observation = run_tool(state, decision, time.monotonic() + 5)
    assert status == "blocked" and observation["required_anchor_ids"] == ["official:anchor"]


def test_old_serialized_conversation_and_explicit_new_subject():
    state = LearningConversation.model_validate({"id": str(uuid4()), "revision": 0})
    assert state.task_contract == {}
    update_contract(state, "다보탑과 해외 탑을 재료로 비교해 줘")
    update_contract(state, "경복궁과 해외 궁전을 구조로 비교해 줘")
    assert state.task_contract["subject"] == "경복궁"
    assert state.task_contract["categories"] == ["구조"]
    update_contract(state, "경복궁 말고 석굴암과 해외 유산을 재료로 비교해 줘")
    assert state.task_contract["subject"] == "석굴암"
    update_contract(state, "다보탑을 기준으로 해외 유산과 재료를 비교하고 퀴즈 없이 설명해 줘")
    assert state.task_contract["subject"] == "다보탑"
    assert not state.task_contract["quiz_requested"]


def test_activity_is_not_comprehension_and_missing_goal_evidence_is_not_complete():
    state = conversation()
    update_contract(state, "다보탑과 해외 탑을 시대와 재료로 비교해 줘")
    state.learning_artifacts = [
        {
            "kind": "comparison",
            "suitable": True,
            "contract_subject": "다보탑",
            "shared_categories": ["시대"],
        }
    ]
    result = outcome_summary(state)
    assert result["comparison_goal_met"] is False
    assert not result["mastery_established"] and not result["educational_effect_established"]
    state.learning_artifacts[0]["shared_categories"].append("재료")
    assert outcome_summary(state)["comparison_goal_met"] is True
    state.task_contract["quiz_requested"] = True
    state.learning_artifacts[0]["id"] = "current-comparison"
    state.active_quiz = {"submitted": True, "comparison_id": "old-comparison"}
    assert not outcome_summary(state)["requested_activities_complete"]
    state.active_quiz["comparison_id"] = "current-comparison"
    assert outcome_summary(state)["requested_activities_complete"]


def test_finish_does_not_mark_unfinished_request_as_complete():
    from culturebridge.agents.learning import respond
    from culturebridge.domain.learning import LearningTurn

    state = conversation()
    update_contract(state, "다보탑과 해외 탑을 재료로 비교하고 퀴즈도 준비해 주세요")
    result = respond(
        {
            "conversation": state,
            "decision": LearningDecision(action="finish"),
            "request": LearningTurn(request_id=uuid4(), revision=0, text="이어서 해줘"),
            "seen": [],
        }
    )["conversation"]
    assert result.goal_status == "exploring"
    assert "전체 목표를 완료한 것은 아니에요" in result.messages[-1].text


def test_explanation_change_requires_same_source_later_evidence_and_ignores_dispute():
    state = conversation()
    base = {
        "source_id": "a",
        "topic_start": 0,
        "quote": "공식 자료의 원문에서 인용한 충분히 긴 문장입니다.",
    }
    state.concepts = {
        "재료": {
            "observations": [
                {**base, "judgment": "possible_misconception", "revision": 1},
                {**base, "source_id": "b", "judgment": "tentative_support", "revision": 2},
            ]
        }
    }
    assert not any(
        o["explanation_improved_observation"]
        for o in outcome_summary(state)["explanation_observations"]
    )
    state.concepts["재료"]["observations"].append(
        {**base, "judgment": "tentative_support", "revision": 3, "history_id": "quiz-1"}
    )
    rows = outcome_summary(state)["explanation_observations"]
    assert rows[0]["explanation_improved_observation"] and rows[0]["after_quiz_review"]
    state.concepts["재료"]["observations"][-1]["disputed_by_learner"] = True
    assert not outcome_summary(state)["explanation_observations"][0][
        "explanation_improved_observation"
    ]


def sample_report():
    artifact = {
        "id": "c",
        "left_id": "anchor",
        "right_id": "foreign",
        "suitable": True,
        "shared_categories": ["시대", "재료"],
    }
    return {
        "runs": [
            {
                "scenario": "comparison",
                "repetition": 1,
                "expectations": {
                    "comparison": True,
                    "quiz": True,
                    "anchor_ids": ["anchor"],
                    "categories": ["종교적 배경"],
                },
                "turns": [
                    {
                        "seconds": 2,
                        "assistant": "검토할 문장입니다.",
                        "observations": [
                            {"tool": "search", "status": "empty"},
                            {"tool": "read", "status": "ok"},
                        ],
                        "comparison_artifacts": [artifact],
                        "quiz_submitted": True,
                    }
                ],
            }
        ],
        "sdk_calls": [],
    }


def test_metrics_use_actual_outcomes_not_tool_or_citation_counts():
    report = sample_report()
    report["runs"][0]["expectations"]["categories"] = ["시대", "재료"]
    report["runs"].append({"scenario": "skipped", "not_run": "quota", "turns": []})
    metrics = evaluate_report(report)
    assert metrics["task_success"]["rate"] == 1
    assert metrics["same_tool_recovery"]["rate"] == 0  # An unrelated read isn't search recovery.
    assert metrics["not_executed_runs"] == 1
    assert metrics["unsupported_claims"]["rate"] is None
    assert metrics["estimated_token_cost_usd"] is None
    report["runs"][0]["turns"][0]["comparison_artifacts"][0]["left_id"] = "wrong"
    metrics = evaluate_report(report)
    assert metrics["task_success"]["rate"] == 0 and metrics["goal_drift"]["rate"] == 1


def test_cost_requires_rates_and_complete_usage_including_thinking():
    report = sample_report()
    report["sdk_calls"] = [
        {
            "usage": {
                "prompt_token_count": 1000,
                "candidates_token_count": 200,
                "thoughts_token_count": 300,
            }
        }
    ]
    assert evaluate_report(report)["estimated_token_cost_usd"] is None
    metrics = evaluate_report(report, input_rate=1, output_rate=2)
    assert metrics["estimated_token_cost_usd"] == 0.002
    report["sdk_calls"].append({"status": "error"})
    assert evaluate_report(report, input_rate=1, output_rate=2)["estimated_token_cost_usd"] is None
    with pytest.raises(ValueError):
        evaluate_report(report, input_rate=float("nan"))


def test_claim_audit_requires_real_response_span_and_does_not_imply_global_accuracy():
    report = sample_report()
    grade = {
        "scenario": "comparison",
        "turn_index": 0,
        "claim": "검토할 문장입니다.",
        "reviewer": "independent-test-reviewer",
        "reason": "Synthetic test only",
        "verdict": "unsupported",
    }
    assert evaluate_report(report, grades=[grade])["unsupported_claims"]["rate"] == 1
    with pytest.raises(ValueError):
        evaluate_report(report, grades=[{**grade, "claim": "보고서에 없는 문장"}])
    with pytest.raises(ValueError):
        evaluate_report(report, grades=[grade, grade])


def test_no_executions_produce_unknown_rates_not_perfect_scores():
    metrics = evaluate_report({"runs": [{"not_run": "quota", "turns": []}]})
    assert metrics["task_success"]["rate"] is None
    assert metrics["goal_drift"]["rate"] is None
    assert metrics["latency_seconds"]["p95"] is None


def test_partial_live_explanation_is_not_a_completed_multi_turn_goal():
    turn = {
        "selected_concept": "재료",
        "citation_count": 1,
        "checkpoint": True,
        "teaching": {
            "method": "local_guide",
            "source_id": "a",
            "failure_kind": "provider_rate_limit",
        },
    }
    report = {
        "runs": [
            {
                "scenario": "reading",
                "expectations": {
                    "explanation": True,
                    "source_id": "a",
                    "concept": "재료",
                    "minimum_turns": 2,
                    "checkpoint": True,
                },
                "turns": [turn],
            }
        ],
        "sdk_calls": [
            {
                "status": "response",
                "usage": {"prompt_token_count": 100, "candidates_token_count": 20},
            },
            {"status": "error", "code": 429},
        ],
    }
    metrics = evaluate_report(report, input_rate=1, output_rate=2)
    assert metrics["task_success"]["rate"] == 0
    assert metrics["explanation_goal_drift"]["rate"] == 0
    assert metrics["explanation_methods"] == {"local_guide": 1}
    assert metrics["generation_failures_by_kind"] == {"provider_rate_limit": 1}
    assert metrics["basic_guide_after_generation_failure"] == 1
    assert metrics["estimated_token_cost_usd"] is None
    assert metrics["observed_usage_only"]["prompt_tokens"] == 100
    assert metrics["sdk_response_success"]["rate"] == 0.5
    report["runs"][0]["turns"].append({"action": "ask"})
    assert evaluate_report(report)["task_success"]["rate"] == 0


def test_claim_provenance_uses_actual_cached_snapshot(tmp_path):
    import json
    import sqlite3

    from scripts.review_agent_evidence import verify_sources

    path = tmp_path / "snapshot.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE official_documents(id TEXT,document_json TEXT)")
        connection.execute("CREATE TABLE agent_source_cache(id TEXT,source_json TEXT)")
        connection.execute(
            "INSERT INTO official_documents VALUES(?,?)",
            (
                "a",
                json.dumps(
                    {"content": "The roof is made of wood.", "source_url": "https://www.khs.go.kr/"}
                ),
            ),
        )
    report = sample_report()
    report["runs"][0]["turns"][0]["citation_sources"] = ["https://www.khs.go.kr/"]
    grade = {
        "scenario": "comparison",
        "turn_index": 0,
        "claim": "검토할 문장입니다.",
        "verdict": "supported",
        "reviewer": "fixture reviewer",
        "reason": "test",
        "source_id": "a",
        "evidence_quote": "made of wood",
    }
    result = verify_sources(report, [grade], path)
    assert result[0]["exact_span_verified"] and result[0]["source_cited"]
    assert len(result[0]["source_sha256"]) == 64
    with pytest.raises(ValueError):
        verify_sources(report, [{**grade, "evidence_quote": "made of gold"}], path)
    with pytest.raises(ValueError):
        verify_sources(report, [{**grade, "source_id": "unknown"}], path)


def test_multi_component_request_is_counted_once_and_requires_all_components():
    report = sample_report()
    expected = report["runs"][0]["expectations"]
    expected.update(explanation=True, source_id="anchor", concept="재료", minimum_turns=1)
    report["runs"][0]["turns"][0].update(
        selected_concept="재료", teaching={"source_id": "anchor"}, citation_count=1
    )
    metrics = evaluate_report(report)
    assert metrics["task_success"]["denominator"] == 1
    assert metrics["task_success"]["rate"] == 0  # Required religion evidence is missing.
    assert metrics["unclassified_executed_runs"] == 0


def review_report():
    report = sample_report()
    report["runs"][0]["expectations"].update(categories=["시대", "재료"], review=True)
    report["runs"][0]["turns"][0].update(quiz_review=True, planner="limited_fallback")
    return report


def test_loading_review_sources_is_not_completed_review_feedback():
    metrics = evaluate_report(review_report())
    assert metrics["task_success"]["rate"] == 0
    assert metrics["review_source_loaded_runs"] == 1
    assert metrics["review_explained_runs"] == 0


def test_grounded_review_feedback_can_complete_the_activity():
    report = review_report()
    report["runs"][0]["turns"][0].update(
        teaching={"source_id": "quiz-review:1:1", "method": "gemini_grounded_rewrite"},
        citation_count=1,
    )
    assert evaluate_report(report)["task_success"]["rate"] == 1


def test_no_wrong_answers_do_not_require_remediation():
    report = review_report()
    report["runs"][0]["turns"][0]["outcomes"] = {
        "quiz_submitted": True,
        "quiz_score": 5,
        "quiz_total": 5,
    }
    metrics = evaluate_report(report)
    assert metrics["task_success"]["rate"] == 1
    assert metrics["review_explained_runs"] == 0


def test_quota_interruption_is_reported_even_after_quiz_submission():
    report = review_report()
    report["runs"][0]["provider_rate_limited"] = True
    assert evaluate_report(report)["interrupted_runs"] == 1
    del report["runs"][0]["provider_rate_limited"]
    report["sdk_calls"] = [{"status": "error", "code": 429}]
    assert evaluate_report(report)["interrupted_runs"] == 1  # Older saved reports lack the flag.
