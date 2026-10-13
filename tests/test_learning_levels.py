from itertools import permutations

import pytest

from culturebridge.config import get_settings
from culturebridge.database import connect, load_quiz_items
from culturebridge.domain.models import LearningLevel
from culturebridge.services.catalog_service import compare_heritages, get_heritage
from culturebridge.services.quiz_service import generate_quiz, grade_quiz


@pytest.fixture(autouse=True)
def isolated_quiz_database(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "levels.db")


@pytest.mark.parametrize("level", list(LearningLevel))
@pytest.mark.parametrize(
    "left_id,right_id", list(permutations(["seokguram", "horyuji", "dayanta"], 2))
)
def test_all_pairs_and_levels_have_gradeable_unique_choices(left_id, right_id, level):
    quiz = generate_quiz(left_id, right_id, level)
    assert quiz.level is level
    assert quiz.learning_goal
    assert len(quiz.items) == 5
    for item in quiz.items:
        assert len(item.choices) == 4
        assert len({choice.text for choice in item.choices}) == 4
        assert "correct_index" not in item.model_dump()
        assert "explanation" not in item.model_dump()
    correct = [item.correct_index for item in quiz.items]
    assert len(set(correct)) > 1
    result = grade_quiz(quiz.quiz_id, correct)
    assert result.score == result.total == 5
    wrong = grade_quiz(quiz.quiz_id, [(answer + 1) % 4 for answer in correct])
    assert wrong.score == 0
    with connect() as connection:
        stored = connection.execute(
            "SELECT level FROM learning_history WHERE session_id = ?", (quiz.quiz_id,)
        ).fetchall()
    assert all(row["level"] == level.value for row in stored)


def test_levels_change_all_explanations_and_question_sets():
    comparisons = [compare_heritages("seokguram", "horyuji", level) for level in LearningLevel]
    for category in range(4):
        assert len({result.differences[category].explanation for result in comparisons}) == 3
        assert len({result.differences[category].left for result in comparisons}) == 1
        assert len({result.differences[category].right for result in comparisons}) == 1
    quizzes = [generate_quiz("seokguram", "horyuji", level) for level in LearningLevel]
    assert len({tuple(item.question for item in quiz.items) for quiz in quizzes}) == 3
    for quiz in quizzes:
        rows = load_quiz_items(quiz.quiz_id)
        assert [row["correct_index"] for row in rows] == [item.correct_index for item in quiz.items]


def test_answers_match_facts_and_evidence_rubric():
    left = get_heritage("seokguram")
    right = get_heritage("horyuji")
    quizzes = [generate_quiz(left.id, right.id, level) for level in LearningLevel]
    answers = [[item.choices[item.correct_index].text for item in quiz.items] for quiz in quizzes]
    assert answers[0][:3] == [left.country, right.material, left.name]
    assert left.period in answers[1][0] and right.period in answers[1][0]
    assert left.material in answers[1][1] and left.structure in answers[1][1]
    assert answers[2][2] == "근거 부족"
    assert answers[2][4] == "추가 확인 필요"
    assert "독립된 근거" in answers[2][1]
