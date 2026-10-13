from culturebridge.domain.models import LearningLevel, VerificationStatus
from culturebridge.services.question_service import answer_question


def test_grounded_material_answer_is_verified() -> None:
    result = answer_question(
        "seokguram",
        "horyuji",
        "두 문화유산의 재료는 어떻게 다른가요?",
        LearningLevel.BEGINNER,
        use_ai=False,
    )
    assert result.verification_status is VerificationStatus.VERIFIED
    assert "화강암" in result.answer
    assert "목재" in result.answer
    assert result.used_ai is False


def test_unsupported_question_does_not_guess() -> None:
    result = answer_question(
        "seokguram",
        "horyuji",
        "두 유산을 만든 장인들이 서로 만났나요?",
        LearningLevel.ADVANCED,
        use_ai=False,
    )
    assert result.verification_status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert "단정적으로 답하기 어렵습니다" in result.answer


def test_source_question_lists_source_organizations() -> None:
    result = answer_question(
        "seokguram",
        "horyuji",
        "어떤 출처를 사용했나요?",
        LearningLevel.INTERMEDIATE,
        use_ai=False,
    )
    assert "국가유산청" in result.answer
    assert "UNESCO" in result.answer
