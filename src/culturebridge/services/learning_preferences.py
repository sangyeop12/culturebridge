"""Presentation preferences never enter the planner or understanding assessment."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from culturebridge.database import transaction
from culturebridge.services.operation_service import owner_key


class LearningPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tone: Literal["friendly", "polite", "concise", "custom"] = "friendly"
    custom_style: str = Field(default="", max_length=120)
    explanation_depth: Literal["auto", "easy", "detailed"] = "auto"


def get_preferences():
    with transaction() as connection:
        row = connection.execute(
            "SELECT state_json FROM learning_preferences WHERE owner=?", (owner_key(),)
        ).fetchone()
    return LearningPreferences.model_validate_json(row[0]) if row else LearningPreferences()


def save_preferences(preferences: LearningPreferences):
    with transaction() as connection:
        connection.execute(
            "INSERT INTO learning_preferences(owner,state_json) VALUES(?,?) "
            "ON CONFLICT(owner) DO UPDATE SET state_json=excluded.state_json,"
            "updated_at=CURRENT_TIMESTAMP",
            (owner_key(), preferences.model_dump_json()),
        )
    return preferences


def present_message(message, preferences):
    """Change only known guidance phrases. Every quotation remains byte-for-byte intact."""
    if message.role != "assistant" or message.kind == "dictionary":
        return message.text
    tone = preferences.tone
    if tone == "custom":
        tone = "polite" if "존댓말" in preferences.custom_style else "friendly"
        if "간결" in preferences.custom_style:
            tone = "concise"
    # Do not transform historical facts, unknown generated wording, or quoted text.
    replacements = {
        "polite": {
            "어떤 이야기가 궁금한가요?": "어떤 이야기가 궁금하신가요?",
            "지금 궁금한 점을 들려주세요.": "지금 궁금하신 점을 말씀해 주세요.",
            "이어서 살펴볼게요.": "이어서 살펴보겠습니다.",
            "새 주제로 시작할게요.": "새 주제로 시작하겠습니다.",
            "여기서 멈출게요. 기록은 남겨 두었어요.": (
                "여기서 멈추겠습니다. 기록은 남겨 두었습니다."
            ),
        },
        "concise": {"이어서 살펴볼게요. ": "", "새 주제로 시작할게요. ": ""},
    }.get(tone, {})
    # Protect both the full official-original section and every citation occurrence.
    prefix, separator, original = message.text.partition("공식 원문:")
    protected = [c.get("quote", "") for c in message.citations if c.get("quote")]
    for old, new in replacements.items():
        if not any(old in quote for quote in protected):
            prefix = prefix.replace(old, new)
    return prefix + separator + original
