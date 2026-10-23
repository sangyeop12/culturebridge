"""Additive conversation contracts; existing comparison APIs stay unchanged."""

from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)


class LearningTurn(BaseModel):
    request_id: UUID
    revision: int = Field(ge=0)
    text: str = Field(default="", max_length=1000)
    control: Literal[
        "message",
        "stop",
        "resume",
        "skip",
        "change_topic",
        "correct",
        "read_source",
        "review_question",
    ] = "message"
    source_id: str = Field(default="", max_length=100)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        return value.strip()


class LearningIntentSignal(BaseModel):
    kind: Literal["interest", "goal", "forget_interest", "forget_goal"]
    topic: str = Field(min_length=1, max_length=160)
    quote: str = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def check_topic(self):
        self.topic, self.quote = self.topic.strip(), self.quote.strip()
        if (
            not self.topic
            or len(self.quote) < 2
            or (self.kind in {"interest", "forget_interest"} and len(self.topic) > 40)
        ):
            raise ValueError("invalid learning intent signal")
        return self


class LearningDecision(BaseModel):
    action: Literal[
        "ask", "search", "search_world", "references", "read", "define", "explain", "check",
        "review", "stop",
    ]
    query: str = Field(default="", max_length=80)
    source_id: str = Field(default="", max_length=100)
    goal: str = Field(default="", max_length=200)
    concept: str = Field(default="", max_length=80)
    question: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=300)
    assessment: Literal["none", "tentative_support", "possible_misconception", "unclear"] = "none"
    assessment_quote: str = Field(default="", max_length=700)
    intent_signals: list[LearningIntentSignal] = Field(default_factory=list, max_length=2)

    @field_validator("intent_signals", mode="before")
    @classmethod
    def valid_optional_signals(cls, values):
        # A malformed optional hint must not invalidate the agent's search/teaching decision.
        if not isinstance(values, list):
            return []
        accepted = []
        for value in values[:2]:
            try:
                accepted.append(LearningIntentSignal.model_validate(value))
            except ValidationError:
                continue
        return accepted


class ConversationMessage(BaseModel):
    kind: Literal["dialogue", "dictionary"] = "dialogue"
    role: Literal["user", "assistant"]
    text: str
    citations: list[dict] = Field(default_factory=list)
    suggestions: list[dict] = Field(default_factory=list)
    teaching: dict = Field(default_factory=dict)


class LearningConversation(BaseModel):
    _pending_intent_signals: list[dict] = PrivateAttr(default_factory=list)
    id: UUID
    revision: int
    status: Literal["active", "paused"] = "active"
    goal: str = ""
    concepts: dict = Field(default_factory=dict)
    plan_history: list[dict] = Field(default_factory=list)
    messages: list[ConversationMessage] = Field(default_factory=list)
    checkpoint: dict = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    search_results: list[dict] = Field(default_factory=list)
    notice: str = ""
    quiz_review: dict = Field(default_factory=dict)
