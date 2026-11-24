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
        "submit_quiz",
        "resume",
        "skip",
        "change_topic",
        "correct",
        "read_source",
        "review_question",
    ] = "message"
    source_id: str = Field(default="", max_length=100)
    answers: list[int] = Field(default_factory=list, max_length=5)

    @field_validator("answers")
    @classmethod
    def valid_answers(cls, values):
        if any(value < 0 or value > 3 for value in values):
            raise ValueError("선택지 번호를 확인해 주세요.")
        return values

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
        "ask",
        "search",
        "search_world",
        "search_history",
        "references",
        "read",
        "define",
        "explain",
        "check",
        "review",
        "stop",
        "discover",
        "compare",
        "quiz",
        "review_quiz",
        "finish",
    ]
    query: str = Field(default="", max_length=80)
    source_id: str = Field(default="", max_length=100)
    goal: str = Field(default="", max_length=200)
    concept: str = Field(default="", max_length=80)
    question: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=300)
    target_id: str = Field(default="", max_length=100)
    comparison_id: str = Field(default="", max_length=100)
    review_number: int = Field(default=0, ge=0, le=5)
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    goal_mode: Literal["observe", "compare", "religion", "verify"] = "compare"
    comparison_scope: Literal["overseas", "domestic"] = "overseas"
    activity: Literal[
        "auto", "explain", "scaffold", "remediate", "contrast", "alternate_question", "deepen"
    ] = "auto"
    plan: list[Literal["search", "read", "explain", "compare", "quiz", "review"]] = Field(
        default_factory=list, max_length=8
    )
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
    topic_start: int = Field(default=0, ge=0)
    checkpoint: dict = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    search_results: list[dict] = Field(default_factory=list)
    notice: str = ""
    quiz_review: dict = Field(default_factory=dict)
    learning_plan: list[str] = Field(default_factory=list)
    goal_status: Literal["exploring", "practising", "reviewing", "summarized"] = "exploring"
    comparison_scope: Literal["overseas", "domestic"] = "overseas"
    tool_observations: list[dict] = Field(default_factory=list)
    pending_request: str = Field(default="", max_length=1000)
    learning_artifacts: list[dict] = Field(default_factory=list)
    active_quiz: dict = Field(default_factory=dict)
    task_contract: dict = Field(default_factory=dict)
