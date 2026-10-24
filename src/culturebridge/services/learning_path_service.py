"""Interest-based ordering, not a new ability assessment or a change of course goals."""

import re

from culturebridge.services.automatic_intent_service import get_automatic_intent
from culturebridge.services.learning_intent_service import get_learning_intent


def personalized_courses(courses):
    intent = get_learning_intent()
    context = intent.planning_context()
    topics = list(context.get("interests", []))
    if context.get("goal"):
        topics.append(context["goal"])
    if intent.infer_from_dialogue:
        inferred = get_automatic_intent()
        topics.extend(item["topic"] for item in inferred.get("interests", []))
    words = set(re.findall(r"[가-힣A-Za-z]{2,}|탑|궁|릉", " ".join(topics)))
    scored = []
    for index, course in enumerate(courses):
        text = " ".join(
            str(course.get(key, ""))
            for key in (
                "title",
                "objective",
                "left_name",
                "right_name",
                "activities",
            )
        )
        score = sum(word.casefold() in text.casefold() for word in words)
        scored.append((-score, index, course))
    return [item[2] for item in sorted(scored)], any(score < 0 for score, _, _ in scored)
