"""Learner-confirmed planning hints, never evidence of understanding or historical facts."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from culturebridge.database import transaction
from culturebridge.services.learning_conversation_service import (
    ConversationConflictError,
    learner_lock,
)
from culturebridge.services.operation_service import owner_key


class LearningIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(default=0, ge=0)
    interests: list[str] = Field(default_factory=list, max_length=8)
    goal: str = Field(default="", max_length=300)
    experience: str = Field(default="", max_length=300)
    use_for_planning: bool = False
    infer_from_dialogue: bool = True

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values):
        unique = []
        for value in values:
            value = value.strip()
            if not 1 <= len(value) <= 40:
                raise ValueError("관심사는 항목마다 1~40자로 적어주세요.")
            if value not in unique:
                unique.append(value)
        return unique

    @field_validator("goal", "experience")
    @classmethod
    def clean_text(cls, value):
        return value.strip()

    def planning_context(self):
        if not self.use_for_planning:
            return {}
        return {
            "interests": self.interests,
            "goal": self.goal,
            "experience": self.experience,
            "origin": "learner_confirmed",
            "not_an_assessment": True,
        }


def get_learning_intent():
    with transaction() as connection:
        row = connection.execute(
            "SELECT state_json FROM learning_intents WHERE owner=?", (owner_key(),)
        ).fetchone()
    return LearningIntent.model_validate_json(row[0]) if row else LearningIntent()


def save_learning_intent(intent: LearningIntent):
    with learner_lock(), transaction() as connection:
        row = connection.execute(
            "SELECT revision FROM learning_intents WHERE owner=?", (owner_key(),)
        ).fetchone()
        current = row[0] if row else 0
        if current != intent.revision:
            raise ConversationConflictError(
                "다른 화면에서 관심사가 바뀌었어요. 다시 불러와 주세요."
            )
        saved = intent.model_copy(update={"revision": current + 1})
        connection.execute(
            "INSERT INTO learning_intents(owner,revision,state_json) VALUES(?,?,?) "
            "ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision,"
            "state_json=excluded.state_json,updated_at=CURRENT_TIMESTAMP",
            (owner_key(), saved.revision, saved.model_dump_json()),
        )
    return saved
