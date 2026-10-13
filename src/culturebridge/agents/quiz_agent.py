from culturebridge.domain.models import LearningLevel
from culturebridge.services.evidence_quiz_service import EvidenceQuizError
from culturebridge.services.quiz_service import generate_quiz, grade_quiz


def create_learning_quiz(state):
    try:
        quiz = generate_quiz(
            state["heritage_id"],
            state["comparison_id"],
            LearningLevel(state["level"]),
            comparison_id=state["comparison"]["saved_id"],
        )
        return {
            "quiz": quiz.model_dump(mode="json"),
            "quiz_notice": "공식 근거 퀴즈가 준비됐습니다.",
            "execution_trace": state.get("execution_trace", []) + ["quiz_agent: 5문항 생성"],
        }
    except EvidenceQuizError:
        return {
            "quiz": None,
            "quiz_notice": "유효한 원문 근거가 없어 퀴즈 생성을 보류했습니다.",
            "execution_trace": state.get("execution_trace", [])
            + ["quiz_agent: 근거 부족으로 보류"],
        }


def evaluate_learning_quiz(quiz_id, answers):
    return grade_quiz(quiz_id, answers)
