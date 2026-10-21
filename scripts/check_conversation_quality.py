"""Opt-in live Gemini review. Uses a separate DB; never prints credentials.

Run manually, not from pytest. Maximum twelve model calls: two planning cases,
three assessment cases (at most two calls each), and two explanations with separate
semantic checks. No retries/purchases.
"""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from culturebridge.agents.learning import _assessment, _model_decision
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.learning import LearningConversation, LearningTurn
from culturebridge.services.learning_preferences import LearningPreferences
from culturebridge.services.lesson_service import official_source
from culturebridge.services.official_service import get_official_document
from culturebridge.services.operation_service import session_owner
from culturebridge.services.personalized_explanation_service import explain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    settings.db_path = args.output.with_suffix(".db")
    if settings.db_path.resolve() == Path("data/culturebridge.db").resolve():
        raise ValueError("Use an isolated database")
    if not settings.gemini_enabled or not settings.gemini_api_key:
        raise ValueError("Gemini key/enabled flag not configured; no calls made")
    initialize_database()
    token = session_owner.set("live-conversation-quality-review")
    report = {
        "model": settings.gemini_model,
        "max_model_calls": 12,
        "kind": "bounded_AI_review_not_student_or_expert_validation",
        "cases": [],
    }
    try:
        document = get_official_document("11", "0000200000000", "37")
        source = official_source(document)
        from culturebridge.services.extraction_service import _local_extraction, validate_extraction

        fields = [f for f in _local_extraction([source]) if validate_extraction(f, [source])]
        field = next(
            f
            for f in fields
            if "10.29m" in f.evidence_quote
            and "10.75m" in f.evidence_quote
            and len(f.evidence_quote) <= 700
        )
        quote = field.evidence_quote
        record = {
            "id": document.record_id,
            "name": document.name,
            "url": str(document.source_url),
            "reading_url": "/official/11/0000200000000/37",
            "excerpts": [{"concept": "구조", "quote": quote}],
        }
        report["official_evidence"] = {
            "quote": quote,
            "url": str(document.source_url),
            "cached": document.cached,
            "stale": document.stale,
        }
        cases = [
            (
                "interest_goal",
                "궁궐에 관심이 있어요. 건물의 배치가 왜 다른지 비교해서 배우고 싶어요.",
                None,
            ),
            ("no_unfounded_interest", "안녕하세요. 아직 어떤 역사를 배울지 모르겠어요.", None),
            (
                "supported_explanation",
                "다보탑과 석가탑의 높이는 비슷해요. "
                "원문에서 두 높이를 적고 비슷하다고 했기 때문이에요.",
                "tentative_support",
            ),
            (
                "misconception",
                "다보탑과 석가탑의 높이는 같아요. "
                "원문에 두 탑의 높이가 완전히 같다고 나와 있기 때문이에요.",
                "possible_misconception",
            ),
            ("no_reason_yet", "아직 잘 모르겠어요. 더 쉽게 설명해 주세요.", "unclear"),
        ]
        rate_limited = False
        for name, text, expected in cases:
            if rate_limited:
                report["cases"].append(
                    {"case": name, "check_passed": False, "not_run": "provider_rate_limit"}
                )
                continue
            conversation = LearningConversation(id=uuid4(), revision=0)
            if expected:
                conversation.sources = [record]
                conversation.checkpoint = {
                    "concept": "구조",
                    "source_id": record["id"],
                    "quote": quote,
                    "question": "두 탑의 높이를 원문에 근거해 설명해 볼까요?",
                }
            state = {
                "conversation": conversation,
                "request": LearningTurn(request_id=uuid4(), revision=0, text=text),
                "seen": [],
                "deadline": time.monotonic() + 30,
                "steps": 0,
                "assessed": False,
            }
            result = {"case": name, "input": text, "expected_assessment": expected}
            try:
                decision = _model_decision(state)
                result["decision"] = decision.model_dump()
                result["assessment_accepted"] = _assessment(state, decision)
                if expected:
                    result["check_passed"] = (
                        decision.assessment == expected and result["assessment_accepted"]
                    )
                    if name == "no_reason_yet":
                        result["check_passed"] = decision.assessment in {"none", "unclear"}
                elif name == "no_unfounded_interest":
                    result["check_passed"] = not decision.intent_signals
                else:
                    result["check_passed"] = any(
                        s.kind == "interest" for s in decision.intent_signals
                    ) and any(s.kind == "goal" for s in decision.intent_signals)
            except Exception as exc:
                result.update(
                    error_type=type(exc).__name__,
                    error_code=getattr(exc, "code", None),
                    check_passed=False,
                )
                rate_limited = getattr(exc, "code", None) == 429
            report["cases"].append(result)
            print(name, "PASS" if result["check_passed"] else "NEEDS_REVIEW", flush=True)
        for tone, depth in [("friendly", "easy"), ("polite", "detailed")]:
            if rate_limited:
                report["cases"].append(
                    {
                        "case": f"explanation_{tone}_{depth}",
                        "check_passed": False,
                        "not_run": "provider_rate_limit",
                    }
                )
                continue
            text, metadata = explain(
                "구조",
                quote,
                LearningPreferences(tone=tone, explanation_depth=depth),
                {"mode": "explain"},
                time.monotonic() + 30,
            )
            success = metadata["method"] == "gemini_grounded_rewrite"
            report["cases"].append(
                {
                    "case": f"explanation_{tone}_{depth}",
                    "text": text,
                    "metadata": metadata,
                    "check_passed": success,
                }
            )
            print(f"explanation_{tone}_{depth}", "PASS" if success else "FALLBACK", flush=True)
    finally:
        session_owner.reset(token)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report", args.output)


if __name__ == "__main__":
    main()
