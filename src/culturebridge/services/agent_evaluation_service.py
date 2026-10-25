"""Offline aggregate metrics. Unexecuted checks and unreviewed claims are unknown, not passes."""

import math
from statistics import mean


def matches_anchor(artifact, expected):
    anchors = set(expected.get("anchor_ids", []))
    if anchors:
        return bool(anchors & {artifact.get("left_id"), artifact.get("right_id")})
    name = expected.get("anchor_name")
    if name:
        return any(
            t.get("name", "").replace(" ", "").endswith(name.replace(" ", ""))
            for t in artifact.get("targets", [])
        )
    return True


def fraction(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def review_explained(turn):
    teaching = turn.get("teaching", {})
    return (
        turn.get("quiz_review", False)
        and teaching.get("source_id", "").startswith("quiz-review:")
        and teaching.get("method") in {"gemini_grounded_rewrite", "local_guide"}
        and turn.get("citation_count", 0) > 0
    )


def evaluate_report(report, *, grades=None, input_rate=None, output_rate=None):
    """Rates are optional USD per million tokens, provided explicitly, never guessed."""
    for rate in (input_rate, output_rate):
        if rate is not None and (not math.isfinite(rate) or rate < 0):
            raise ValueError("Token prices must be finite and non-negative")
    runs = report.get("runs", [])
    executed = [r for r in runs if r.get("turns")]
    classified, recovered, failed = [], 0, 0
    by_scenario = {}
    drifts, comparisons = 0, 0
    explanation_drifts, explanations = 0, 0
    teaching_modes = {}
    generation_failures = {}
    basic_after_failure = 0
    durations = []
    review_loaded_runs, review_explained_runs = 0, 0
    for run in executed:
        expected = run.get("expectations", {})
        observations = [o for t in run["turns"] for o in t.get("observations", [])]
        had_failure = any(
            o.get("status") in {"error", "empty", "insufficient"} for o in observations
        )
        if had_failure:
            failed += 1
            # Same-tool recovery is not proof that the whole user goal was recovered.
            recovered += any(
                any(
                    later.get("tool") == item.get("tool") and later.get("status") == "ok"
                    for later in observations[index + 1 :]
                )
                for index, item in enumerate(observations)
                if item.get("status") in {"error", "empty", "insufficient"}
            )
        artifacts = [a for t in run["turns"] for a in t.get("comparison_artifacts", [])]
        unique = {a["id"]: a for a in artifacts}
        for artifact in unique.values():
            anchors = set(expected.get("anchor_ids", []))
            if anchors or expected.get("anchor_name"):
                comparisons += 1
                drifts += not matches_anchor(artifact, expected)
        final = run["turns"][-1]
        review_loaded_runs += any(t.get("quiz_review", False) for t in run["turns"])
        review_explained_runs += any(review_explained(t) for t in run["turns"])
        success_checks = []
        if expected.get("explanation"):
            relevant = [t for t in run["turns"] if t.get("selected_concept")]
            for turn in relevant:
                explanations += 1
                teaching = turn.get("teaching", {})
                explanation_drifts += teaching.get("source_id") != expected.get(
                    "source_id"
                ) or turn.get("selected_concept") != expected.get("concept")
            success = (
                len(run["turns"]) >= expected.get("minimum_turns", 1)
                and bool(relevant)
                and final.get("selected_concept") == expected.get("concept")
                and final.get("teaching", {}).get("source_id") == expected.get("source_id")
                and all(
                    t.get("teaching", {}).get("source_id") == expected.get("source_id")
                    and t.get("selected_concept") == expected.get("concept")
                    and t.get("citation_count", 0) > 0
                    for t in relevant
                )
                and (not expected.get("checkpoint") or final.get("checkpoint", False))
            )
            success_checks.append(bool(success))
        if expected.get("comparison"):
            success = any(
                a.get("suitable")
                and matches_anchor(a, expected)
                and set(expected.get("categories", [])) <= set(a.get("shared_categories", []))
                for a in unique.values()
            )
            outcome = final.get("outcomes", {})
            success = success and (
                not expected.get("quiz")
                or outcome.get("quiz_submitted", final.get("quiz_submitted", False))
            )
            all_correct = (outcome.get("quiz_total", 0) or 0) > 0 and (
                outcome.get("quiz_score") == outcome.get("quiz_total")
            )
            success = success and (
                not expected.get("review")
                or all_correct
                or any(review_explained(t) for t in run["turns"])
            )
            success_checks.append(bool(success))
        if success_checks:
            complete = all(success_checks)
            classified.append(complete)
            by_scenario.setdefault(run.get("scenario", "unknown"), []).append(complete)
        for turn in run["turns"]:
            teaching = turn.get("teaching", {})
            method = teaching.get("method")
            if method:
                teaching_modes[method] = teaching_modes.get(method, 0) + 1
            failure = teaching.get("failure_kind")
            if failure:
                generation_failures[failure] = generation_failures.get(failure, 0) + 1
                basic_after_failure += method == "local_guide"
            if isinstance(turn.get("seconds"), (int, float)):
                durations.append(turn["seconds"])
    calls = report.get("sdk_calls", [])
    with_usage = [c for c in calls if isinstance(c.get("usage"), dict)]
    metered = [
        c
        for c in with_usage
        if all(
            isinstance(c["usage"].get(key), int) and c["usage"][key] >= 0
            for key in ("prompt_token_count", "candidates_token_count")
        )
    ]
    prompt = sum(c["usage"].get("prompt_token_count", 0) or 0 for c in with_usage)
    output = sum(
        (c["usage"].get("candidates_token_count", 0) or 0)
        + (c["usage"].get("thoughts_token_count", 0) or 0)
        for c in with_usage
    )
    usage_complete = (
        bool(calls)
        and len(with_usage) == len(calls)
        and all(
            isinstance(c["usage"].get(key), int) and c["usage"][key] >= 0
            for c in with_usage
            for key in ("prompt_token_count", "candidates_token_count")
        )
    )
    cost = (
        (prompt * input_rate + output * output_rate) / 1_000_000
        if usage_complete and input_rate is not None and output_rate is not None
        else None
    )
    # A human/independent audit must supply per-claim grades. Citations alone are not correctness.
    grade_rows = grades or []
    if not isinstance(grade_rows, list):
        raise ValueError("Claim grades must be a JSON list")
    seen_grades = set()
    for grade in grade_rows:
        run = next(
            (
                r
                for r in runs
                if r.get("scenario") == grade.get("scenario")
                and r.get("repetition", 1) == grade.get("repetition", 1)
            ),
            None,
        )
        index = grade.get("turn_index")
        claim = grade.get("claim", "")
        key = (grade.get("scenario"), grade.get("repetition", 1), index, claim)
        if (
            not run
            or not isinstance(index, int)
            or index < 0
            or index >= len(run.get("turns", []))
            or not claim
            or claim not in run["turns"][index].get("assistant", "")
            or not grade.get("reviewer")
            or not grade.get("reason")
            or grade.get("verdict") not in {"supported", "unsupported", "uncertain"}
            or grade.get("question_relevance") not in {None, "direct", "partial", "off_topic"}
            or key in seen_grades
        ):
            raise ValueError("Claim grade must identify a unique actual response span and reviewer")
        seen_grades.add(key)
    supported = sum(g.get("verdict") == "supported" for g in grade_rows)
    unsupported = sum(g.get("verdict") == "unsupported" for g in grade_rows)
    ordered = sorted(durations)
    return {
        "planned_runs": len(runs),
        "executed_runs": len(executed),
        "not_executed_runs": len(runs) - len(executed),
        "task_success": fraction(sum(classified), len(classified)),
        "unclassified_executed_runs": len(executed) - len(classified),
        "interrupted_runs": sum(
            bool(
                r.get("remaining_not_run")
                or r.get("error_type")
                or r.get("provider_rate_limited")
                or (
                    executed
                    and r is executed[-1]
                    and report.get("sdk_calls")
                    and str(report["sdk_calls"][-1].get("code")) == "429"
                    and r.get("turns", [{}])[-1].get("planner") == "limited_fallback"
                )
            )
            for r in runs
        ),
        "review_source_loaded_runs": review_loaded_runs,
        "review_explained_runs": review_explained_runs,
        "per_scenario_success": {k: fraction(sum(v), len(v)) for k, v in by_scenario.items()},
        "goal_drift": fraction(drifts, comparisons),
        "explanation_goal_drift": fraction(explanation_drifts, explanations),
        "explanation_methods": teaching_modes,
        "generation_failures_by_kind": generation_failures,
        "basic_guide_after_generation_failure": basic_after_failure,
        "same_tool_recovery": fraction(recovered, failed),
        "unsupported_claims": fraction(unsupported, supported + unsupported),
        "claim_metric_scope": "Reviewed claims only; not an estimate of all factual claims.",
        "reviewed_claim_relevance": {
            label: sum(g.get("question_relevance") == label for g in grade_rows)
            for label in ("direct", "partial", "off_topic")
        },
        "uncertain_reviewed_claims": sum(
            g.get("verdict") not in {"supported", "unsupported"} for g in grade_rows
        ),
        "unreviewed_claims": None,
        "latency_seconds": {
            "count": len(ordered),
            "mean": mean(ordered) if ordered else None,
            "p95": ordered[math.ceil(len(ordered) * 0.95) - 1] if ordered else None,
        },
        "sdk_calls": len(calls),
        "usage_recorded_calls": len(with_usage),
        "sdk_response_success": fraction(
            sum(c.get("status") == "response" for c in calls), len(calls)
        ),
        "observed_usage_only": {
            "fully_metered_calls": len(metered),
            "prompt_tokens": sum(c["usage"]["prompt_token_count"] for c in metered)
            if metered
            else None,
            "output_and_thinking_tokens": sum(
                c["usage"]["candidates_token_count"] + (c["usage"].get("thoughts_token_count") or 0)
                for c in metered
            )
            if metered
            else None,
            "cached_input_tokens": sum(
                c["usage"].get("cached_content_token_count", 0) or 0 for c in with_usage
            )
            if with_usage
            else None,
            "cost_estimate_usd_without_cache_discount": (
                (prompt * input_rate + output * output_rate) / 1_000_000
                if metered
                and len(metered) == len(with_usage)
                and input_rate is not None
                and output_rate is not None
                else None
            ),
            "scope": "Calls with usage only; not a complete run cost or actual invoice.",
        },
        "prompt_tokens": prompt if usage_complete else None,
        "output_and_thinking_tokens": output if usage_complete else None,
        "estimated_token_cost_usd": cost,
        "cost_is_complete": cost is not None,
        "cost_note": "Explicit token-rate estimate only; not invoice, cache/tool fees, or taxes.",
        "educational_effect_established": False,
    }
