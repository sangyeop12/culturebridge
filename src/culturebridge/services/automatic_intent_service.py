"""Tentative learning topics/goals from user utterances; no identity or mastery profiling."""

import json
import re

from culturebridge.database import transaction
from culturebridge.domain.learning import LearningIntentSignal
from culturebridge.services.operation_service import owner_key


def empty_intent():
    return {
        "interests": [],
        "goal": None,
        "sequence": 0,
        "origin": "dialogue_inferred",
        "tentative": True,
        "not_an_assessment": True,
    }


def get_automatic_intent():
    with transaction() as connection:
        row = connection.execute(
            "SELECT state_json FROM inferred_learning_intents WHERE owner=?", (owner_key(),)
        ).fetchone()
    return json.loads(row[0]) if row else empty_intent()


def safe_text(text):
    # Do not retain common contact, credential, URL, or identifier-like strings as learning hints.
    return not re.search(
        r"https?://|www\.|@|AIza|sk-[A-Za-z0-9]|api[ _-]?key|비밀번호|주민등록|"
        r"\d{6,}|\d{2,4}[- ]\d{3,4}[- ]\d{4}",
        text,
        re.I,
    )


def stage_signals(conversation, signals, text, *, method="ai"):
    for signal in signals:
        if signal.quote not in text or not safe_text(text) or not safe_text(signal.topic):
            continue
        if signal.kind in {"interest", "forget_interest"} and signal.topic not in signal.quote:
            continue
        if signal.kind == "interest" and re.search(r"관심(?:이)?\s*없|싫어|제외해", signal.quote):
            continue
        if signal.kind == "forget_interest" and not re.search(
            r"없|싫|제외|빼|아니|잊|취소|말아|그만", signal.quote
        ):
            continue
        if signal.kind == "forget_goal" and not re.search(
            r"취소|목표.*(?:바꾸|아니|잊)|그만|원하지", signal.quote
        ):
            continue
        item = {**signal.model_dump(), "method": method}
        if not any(
            s["kind"] == item["kind"] and s["topic"] == item["topic"]
            for s in conversation._pending_intent_signals
        ):
            conversation._pending_intent_signals.append(item)
    conversation._pending_intent_signals = conversation._pending_intent_signals[:2]


def explicit_signals(text):
    """Only explicit phrases when AI yields no signal. Not general semantic inference."""
    if len(text) > 100 or not safe_text(text):
        return []
    clean = text.strip(" .!?？")
    denied = re.fullmatch(
        r"(?:저는\s*|나는\s*)?(.{1,40}?)(?:에(?:는)?|은|는)?\s*관심(?:이)?\s*없(?:어요|어|습니다)",
        clean,
    )
    if denied:
        return [LearningIntentSignal(kind="forget_interest", topic=denied[1], quote=clean)]
    if re.fullmatch(r"(?:이전|아까|저장한)?\s*목표(?:는|를)?\s*취소(?:할래요|해줘|해요)", clean):
        return [LearningIntentSignal(kind="forget_goal", topic="이전 학습 목표", quote=clean)]
    interest = re.fullmatch(
        r"(?:저는\s*|나는\s*)?(.{1,40}?)(?:에\s*관심(?:이)?\s*있(?:어요|어|습니다)|"
        r"(?:이|가)\s*궁금(?:해요|해|합니다))",
        clean,
    )
    if interest:
        return [LearningIntentSignal(kind="interest", topic=interest[1], quote=clean)]
    if re.fullmatch(r".{2,70}(?:배우고|알아보고|비교하고|공부하고)\s*싶(?:어요|어|습니다)", clean):
        return [LearningIntentSignal(kind="goal", topic=clean, quote=clean)]
    return []


def commit_signals(connection, conversation, request):
    from culturebridge.services.learning_intent_service import LearningIntent

    policy = connection.execute(
        "SELECT state_json FROM learning_intents WHERE owner=?", (owner_key(),)
    ).fetchone()
    enabled = LearningIntent.model_validate_json(policy[0]).infer_from_dialogue if policy else True
    if not enabled or request.control != "message" or conversation.status == "paused":
        return
    signals = conversation._pending_intent_signals
    if not signals:
        stage_signals(
            conversation, explicit_signals(request.text), request.text, method="explicit_phrase"
        )
        signals = conversation._pending_intent_signals
    if not signals:
        return
    row = connection.execute(
        "SELECT state_json FROM inferred_learning_intents WHERE owner=?", (owner_key(),)
    ).fetchone()
    state = json.loads(row[0]) if row else empty_intent()
    state["sequence"] += 1
    for signal in signals:
        if signal["kind"] == "forget_interest":
            state["interests"] = [v for v in state["interests"] if v["topic"] != signal["topic"]]
            continue
        if signal["kind"] == "forget_goal":
            state["goal"] = None
            continue
        existing = next((v for v in state["interests"] if v["topic"] == signal["topic"]), None)
        value = {
            "topic": signal["topic"],
            "quote": signal["quote"],
            "method": signal["method"],
            "last_seen": state["sequence"],
            "mentions": min(10, existing["mentions"] + 1) if existing else 1,
        }
        if signal["kind"] == "goal":
            state["goal"] = value
        else:
            state["interests"] = [
                v for v in state["interests"] if v["topic"] != signal["topic"]
            ] + [value]
            state["interests"] = state["interests"][-8:]
    connection.execute(
        "INSERT INTO inferred_learning_intents(owner,state_json) VALUES(?,?) "
        "ON CONFLICT(owner) DO UPDATE SET state_json=excluded.state_json,"
        "updated_at=CURRENT_TIMESTAMP",
        (owner_key(), json.dumps(state, ensure_ascii=False)),
    )


def clear_automatic_intent():
    """Clear guesses and disable tracking; previous dialogue and manual goals stay untouched."""
    from culturebridge.services.learning_conversation_service import learner_lock
    from culturebridge.services.learning_intent_service import LearningIntent

    with learner_lock(), transaction() as connection:
        row = connection.execute(
            "SELECT state_json FROM learning_intents WHERE owner=?", (owner_key(),)
        ).fetchone()
        intent = LearningIntent.model_validate_json(row[0]) if row else LearningIntent()
        intent.infer_from_dialogue = False
        intent.revision += 1
        connection.execute(
            "INSERT INTO learning_intents(owner,revision,state_json) VALUES(?,?,?) "
            "ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision,"
            "state_json=excluded.state_json,updated_at=CURRENT_TIMESTAMP",
            (owner_key(), intent.revision, intent.model_dump_json()),
        )
        connection.execute("DELETE FROM inferred_learning_intents WHERE owner=?", (owner_key(),))
        return intent
