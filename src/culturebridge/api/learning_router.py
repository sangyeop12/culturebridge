"""Conversation APIs are additive and never require a pair of heritage IDs."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from culturebridge.domain.learning import LearningConversation, LearningTurn
from culturebridge.services.learning_conversation_service import (
    ConversationConflictError,
    ConversationNotFoundError,
    create_conversation,
    get_conversation,
    list_conversations,
    request_learning_stop,
    send_learning_turn,
)
from culturebridge.services.learning_intent_service import (
    LearningIntent,
    get_learning_intent,
    save_learning_intent,
)
from culturebridge.services.learning_preferences import (
    LearningPreferences,
    get_preferences,
    save_preferences,
)

router = APIRouter(prefix="/api/learning", tags=["Learning conversations"])


@router.get("/intent/automatic")
def automatic_learning_intent():
    from culturebridge.services.automatic_intent_service import get_automatic_intent

    return {**get_automatic_intent(), "enabled": get_learning_intent().infer_from_dialogue}


@router.post("/intent/automatic/reset", response_model=LearningIntent)
def reset_automatic_learning_intent():
    from culturebridge.services.automatic_intent_service import clear_automatic_intent

    return clear_automatic_intent()


@router.post("/reviews/{history_id}/conversation", response_model=LearningConversation)
def start_quiz_review_conversation(history_id: int):
    from culturebridge.services.conversation_review_service import ReviewNotFoundError

    try:
        return create_conversation(review_history_id=history_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="이 브라우저의 퀴즈 기록을 찾을 수 없어요."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/intent", response_model=LearningIntent)
def learning_intent():
    return get_learning_intent()


@router.put("/intent", response_model=LearningIntent)
def update_learning_intent(request: LearningIntent):
    try:
        return save_learning_intent(request)
    except ConversationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/preferences", response_model=LearningPreferences)
def preferences():
    return get_preferences()


@router.put("/preferences", response_model=LearningPreferences)
def update_preferences(request: LearningPreferences):
    return save_preferences(request)


@router.get("/terms")
def dictionary_term(q: str = Query(min_length=1, max_length=40)):
    from culturebridge.services.dictionary_service import lookup_term

    try:
        return lookup_term(q)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class StopRequest(BaseModel):
    revision: int = Field(ge=0)


@router.post("/conversations/{identity}/interrupt")
def interrupt_learning(identity: UUID, request: StopRequest):
    try:
        return request_learning_stop(identity, request.revision)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="이 대화를 찾을 수 없어요.") from exc
    except ConversationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/conversations", response_model=LearningConversation)
def start_conversation():
    try:
        return create_conversation()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/conversations")
def conversations():
    return list_conversations()


@router.get("/conversations/{identity}", response_model=LearningConversation)
def conversation(identity: UUID):
    try:
        return get_conversation(identity)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="이 대화를 찾을 수 없어요.") from exc


@router.post("/conversations/{identity}/turns", response_model=LearningConversation)
def learning_turn(identity: UUID, request: LearningTurn):
    try:
        return send_learning_turn(identity, request)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="이 대화를 찾을 수 없어요.") from exc
    except ConversationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
