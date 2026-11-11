from culturebridge.domain.learning import ConversationMessage
from culturebridge.services.learning_preferences import LearningPreferences
from culturebridge.ui.learning_chat import message_body

FOOTER = (
    "\n\n현재 자료와 요청은 유지했어요. "
    "AI 연결이 복구되면 ‘이어서 진행해 주세요’로 계속할 수 있어요."
)


def test_legacy_retry_footer_is_hidden_without_rewriting_saved_answer():
    message = ConversationMessage(role="assistant", text="경복궁의 공식 설명입니다." + FOOTER)
    before = message.model_dump_json()
    assert message_body(message, LearningPreferences()) == "경복궁의 공식 설명입니다."
    assert message.model_dump_json() == before


def test_learner_text_and_source_quotations_are_preserved():
    learner = ConversationMessage(role="user", text="이 말은 왜 나오나요?" + FOOTER)
    assert message_body(learner, LearningPreferences()) == learner.text
    quotation = ConversationMessage(
        role="assistant", text="인용문:" + FOOTER, citations=[{"quote": FOOTER.strip()}]
    )
    assert message_body(quotation, LearningPreferences()) == quotation.text
