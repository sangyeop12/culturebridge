"""Owned, revisioned conversations. No external text or model output is trusted as a command."""

import hashlib
import json
import threading
from contextlib import contextmanager
from uuid import uuid4

from culturebridge.database import transaction
from culturebridge.domain.learning import LearningConversation, LearningTurn
from culturebridge.services.operation_service import owner_key, reused_operation


class ConversationNotFoundError(KeyError):
    pass


class ConversationConflictError(ValueError):
    pass


_guard = threading.Lock()
_locks = {}


@contextmanager
def learner_lock():
    from culturebridge.config import get_settings

    key = (str(get_settings().db_path.resolve()), owner_key())
    with _guard:
        entry = _locks.setdefault(key, [threading.RLock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _guard:
            entry[1] -= 1
            if not entry[1]:
                del _locks[key]


def create_conversation(*, review_history_id=None):
    with learner_lock(), transaction() as connection:
        review = None
        if review_history_id is not None:
            from culturebridge.services.conversation_review_service import owned_review

            review = owned_review(connection, review_history_id)
            linked = connection.execute(
                "SELECT c.state_json FROM learning_review_links r JOIN learning_conversations c "
                "ON c.id=r.conversation_id WHERE r.history_id=? AND r.owner=? AND c.owner=?",
                (review_history_id, owner_key(), owner_key()),
            ).fetchone()
            if linked:
                previous = LearningConversation.model_validate_json(linked[0])
                if previous.revision < 200:
                    return previous
                connection.execute(
                    "DELETE FROM learning_review_links WHERE history_id=? AND owner=?",
                    (review_history_id, owner_key()),
                )
        count = connection.execute(
            "SELECT count(*) FROM learning_conversations WHERE owner=?", (owner_key(),)
        ).fetchone()[0]
        if count >= 100:
            raise ValueError("대화가 많이 쌓였어요. 기존 대화를 이어가거나 기록을 정리해 주세요.")
        profile = connection.execute(
            "SELECT state_json FROM learner_profiles WHERE owner=?", (owner_key(),)
        ).fetchone()
        state = LearningConversation(
            id=uuid4(), revision=0, concepts=json.loads(profile[0]) if profile else {}
        )
        if review is not None:
            from culturebridge.services.conversation_review_service import seed_review

            seed_review(state, review_history_id, *review)
        connection.execute(
            "INSERT INTO learning_conversations(id,owner,state_json) VALUES(?,?,?)",
            (str(state.id), owner_key(), state.model_dump_json()),
        )
        if review is not None:
            connection.execute(
                "INSERT INTO learning_review_links VALUES(?,?,?)",
                (review_history_id, str(state.id), owner_key()),
            )
        return state


def get_conversation(identity):
    with transaction() as connection:
        row = connection.execute(
            "SELECT state_json FROM learning_conversations WHERE id=? AND owner=?",
            (str(identity), owner_key()),
        ).fetchone()
    if not row:
        raise ConversationNotFoundError(identity)
    return LearningConversation.model_validate_json(row[0])


def list_conversations():
    with transaction() as connection:
        rows = connection.execute(
            "SELECT id,revision,state_json FROM learning_conversations WHERE owner=? "
            "ORDER BY updated_at DESC,rowid DESC LIMIT 30",
            (owner_key(),),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "revision": r["revision"],
            "goal": json.loads(r["state_json"]).get("goal") or "이어서 이야기하기",
        }
        for r in rows
    ]


def request_learning_stop(identity, revision):
    """Cooperative cancellation: no learner lock, so an in-flight request can see it."""
    with transaction() as connection:
        row = connection.execute(
            "SELECT revision FROM learning_conversations WHERE id=? AND owner=?",
            (str(identity), owner_key()),
        ).fetchone()
        if not row:
            raise ConversationNotFoundError(identity)
        if row[0] != revision:
            raise ConversationConflictError("대화가 바뀌었어요. 최신 내용을 불러와 주세요.")
        connection.execute(
            "INSERT OR REPLACE INTO learning_interrupts VALUES(?,?)", (str(identity), revision)
        )
    return {"stop_requested": True}


def learning_stop_requested(state):
    with transaction() as connection:
        row = connection.execute(
            "SELECT i.revision FROM learning_interrupts i JOIN learning_conversations c "
            "ON c.id=i.conversation_id WHERE c.id=? AND c.owner=?",
            (str(state.id), owner_key()),
        ).fetchone()
    return row is not None and row[0] == state.revision


@reused_operation("learning_conversation")
def send_learning_turn(identity, request: LearningTurn):
    from culturebridge.agents.learning import run_learning_turn

    payload_hash = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    with learner_lock():
        state = get_conversation(identity)
        with transaction() as connection:
            previous = connection.execute(
                "SELECT payload_hash,response_json FROM learning_turn_requests "
                "WHERE conversation_id=? AND request_id=?",
                (str(identity), str(request.request_id)),
            ).fetchone()
        if previous:
            if previous[0] != payload_hash:
                raise ConversationConflictError("같은 요청 번호에 다른 내용을 보낼 수 없어요.")
            return LearningConversation.model_validate_json(previous[1])
        if state.revision != request.revision:
            raise ConversationConflictError("다른 창에서 대화가 바뀌었어요. 새로 불러와 주세요.")
        if state.revision >= 200:
            raise ValueError("이 대화는 충분히 길어졌어요. 새 대화에서 이어가 주세요.")
        if request.control in {"message", "correct"} and not request.text:
            raise ValueError("이야기하고 싶은 내용을 입력해 주세요.")
        if request.control == "read_source" and request.source_id not in {
            r["id"] for r in state.search_results
        }:
            raise ValueError("이 대화의 공식 검색 결과에서 선택해 주세요.")
        if request.control == "review_question" and request.source_id not in {
            str(i["number"]) for i in state.quiz_review.get("items", [])
        }:
            raise ValueError("이 복습 대화의 문항을 선택해 주세요.")
        if state.status == "paused" and request.control not in {"resume", "change_topic", "stop"}:
            raise ConversationConflictError("대화가 중단돼 있어요. 이어서 학습을 선택해 주세요.")
        with transaction() as connection:
            profile = connection.execute(
                "SELECT state_json FROM learner_profiles WHERE owner=?", (owner_key(),)
            ).fetchone()
        if profile:
            state.concepts = json.loads(profile[0])
        result = run_learning_turn(state, request)
        result.revision = state.revision + 1
        removed = max(0, len(result.messages) - 40)
        result.topic_start = max(0, result.topic_start - removed)
        result.messages = result.messages[-40:]
        result.plan_history = result.plan_history[-30:]
        with transaction() as connection:
            stopped = connection.execute(
                "SELECT revision FROM learning_interrupts WHERE conversation_id=?",
                (str(identity),),
            ).fetchone()
            if stopped and stopped[0] == state.revision:
                result.status = "paused"
                result.concepts, result.checkpoint = state.concepts, state.checkpoint
                result.goal = state.goal
                result.messages[-1].text = "중단했어요. 원할 때 이어서 학습할 수 있어요."
                result.messages[-1].citations = []
                result.messages[-1].suggestions = []
                result.messages[-1].teaching = {}
                result.plan_history.append({"action": "stop", "reason": "사용자의 중단 요청"})
                connection.execute(
                    "DELETE FROM learning_interrupts WHERE conversation_id=?", (str(identity),)
                )
            cursor = connection.execute(
                "UPDATE learning_conversations SET revision=?,state_json=?,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner=? AND revision=?",
                (
                    result.revision,
                    result.model_dump_json(),
                    str(identity),
                    owner_key(),
                    state.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConversationConflictError("대화가 변경됐어요. 다시 불러와 주세요.")
            if state.quiz_review and not result.quiz_review:
                connection.execute(
                    "DELETE FROM learning_review_links WHERE conversation_id=? AND owner=?",
                    (str(identity), owner_key()),
                )
            from culturebridge.services.automatic_intent_service import commit_signals

            commit_signals(connection, result, request)
            result._pending_intent_signals = []
            connection.execute(
                "INSERT INTO learning_turn_requests VALUES(?,?,?,?)",
                (str(identity), str(request.request_id), payload_hash, result.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO learner_profiles VALUES(?,?) ON CONFLICT(owner) "
                "DO UPDATE SET state_json=excluded.state_json",
                (owner_key(), json.dumps(result.concepts, ensure_ascii=False)),
            )
        return result
