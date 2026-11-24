"""Learner-controlled task constraints and conservative learning-outcome observations."""

import re


def update_contract(conversation, text):
    """Capture an explicit comparison anchor before search, not from a model's goal."""
    match = re.search(
        r"^(.{2,70}?)(?:(?:과|와)\s*(?:비교할|해외|국내|다른\s*나라)|[을를]\s*기준으로)",
        text.strip(),
    )
    if "비교" not in text or not match:
        return
    subject = match[1].strip()
    if subject.replace(" ", "") in {"이유산", "이문화유산", "그유산", "선택한유산"}:
        if conversation.task_contract.get("subject"):
            subject = conversation.task_contract["subject"]
        elif len(conversation.sources) == 1:
            subject = conversation.sources[0]["name"]
        else:
            return  # No unique antecedent: do not invent a named anchor from a pronoun.
    if re.search(r"말고|아닌|제외|대신", subject):
        subject = re.split(r"말고|아닌|대신", subject)[-1].strip()
        if not subject or "제외" in subject:
            conversation.task_contract = {}
            return
    categories = [c for c in ("시대", "구조", "재료", "종교적 배경") if c in text]
    if "종교" in text and "종교적 배경" not in categories:
        categories.append("종교적 배경")
    conversation.task_contract = {
        "request": text[:1000],
        "subject": subject,
        "categories": categories,
        "quiz_requested": "퀴즈" in text and not re.search(r"퀴즈\s*(?:없이|말고|빼고)", text),
    }


def anchored_ids(conversation, known):
    from culturebridge.services.display_service import short_display_name

    subject = conversation.task_contract.get("subject", "")
    if not subject:
        return []
    normalized = re.sub(r"\s+", "", subject).casefold()
    return [
        identity
        for identity, row in known.items()
        if not row.get("metadata_only")
        and re.sub(r"\s+", "", short_display_name(row.get("name", "")))
        .casefold()
        .endswith(normalized)
    ]


def outcome_summary(conversation):
    """Activity completion is not mastery; compare observations only within one source/concept."""
    contract = conversation.task_contract
    required = set(contract.get("categories", []))
    comparisons = [a for a in conversation.learning_artifacts if a.get("kind") == "comparison"]
    suitable = [
        a
        for a in comparisons
        if a.get("suitable")
        and required <= set(a.get("shared_categories", []))
        and (not contract.get("subject") or a.get("contract_subject") == contract["subject"])
    ]
    evidence = []
    for concept, record in conversation.concepts.items():
        by_source = {}
        for item in record.get("observations", []):
            if item.get("topic_start") != conversation.topic_start:
                continue
            if item.get("disputed_by_learner") or len(item.get("quote", "").strip()) < 10:
                continue
            by_source.setdefault(item.get("source_id"), []).append(item)
        for source_id, observations in by_source.items():
            if not source_id:
                continue
            latest = observations[-1]
            improved = latest.get("judgment") == "tentative_support" and any(
                o.get("judgment") in {"possible_misconception", "unclear"}
                and o.get("revision", -1) < latest.get("revision", -1)
                for o in observations[:-1]
            )
            evidence.append(
                {
                    "concept": concept,
                    "source_id": source_id,
                    "latest_judgment": latest.get("judgment"),
                    "explanation_improved_observation": improved,
                    "after_quiz_review": bool(latest.get("history_id")),
                }
            )
    quiz = conversation.active_quiz
    quiz_matches_goal = not contract or quiz.get("comparison_id") in {
        a["id"] for a in suitable if a.get("id")
    }
    activities_complete = bool(suitable) and (
        not contract.get("quiz_requested") or bool(quiz.get("submitted") and quiz_matches_goal)
    )
    return {
        "comparison_goal_met": bool(suitable) if contract else None,
        "requested_activities_complete": activities_complete if contract else None,
        "quiz_submitted": bool(quiz.get("submitted") and quiz_matches_goal),
        "quiz_score": quiz.get("score") if quiz.get("submitted") else None,
        "quiz_total": quiz.get("total") if quiz.get("submitted") else None,
        "explanation_observations": evidence,
        "mastery_established": False,
        "educational_effect_established": False,
        "notice": "활동 완료나 한 번의 답변만으로 이해·학습 효과를 확정하지 않아요.",
    }
