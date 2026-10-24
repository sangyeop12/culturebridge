"""Source-derived regressions from the 25-source desk review; no actual pupil outcomes."""

from uuid import uuid4

import pytest

from culturebridge.domain.learning import LearningConversation
from culturebridge.services.adaptive_learning_service import activity_question
from culturebridge.services.classroom_quiz_service import content_question
from culturebridge.services.date_reading_service import read_period
from culturebridge.services.evidence_reading_service import observation_scope, reading_units
from culturebridge.services.learning_agent_tools import planning_tools
from culturebridge.services.learning_outcome_service import update_contract
from culturebridge.services.lesson_service import beginner_text


@pytest.mark.parametrize(
    "learner_text,subject",
    [
        ("다보탑과 해외 탑을 시대와 재료로 비교해 줘", "다보탑"),
        ("석굴암을 기준으로 해외 석굴과 구조를 비교해 줘", "석굴암"),
        ("경복궁과 비교할 해외 궁전을 골라 줘", "경복궁"),
        ("무령왕릉과 다른 나라의 무덤을 비교해 줘", "무령왕릉"),
        ("다보탑 말고 경복궁과 해외 궁전을 비교해 줘", "경복궁"),
    ],
)
def test_planner_cannot_offer_comparison_before_anchor_search(learner_text, subject):
    state = LearningConversation(id=uuid4(), revision=0)
    update_contract(state, learner_text)
    state.search_results = [
        {"id": "official:a", "name": "해외 유산 A"},
        {"id": "official:b", "name": "해외 유산 B"},
    ]
    enabled, constraints, _ = planning_tools(state)
    assert "compare" not in enabled and "discover" not in enabled
    assert constraints["subject_to_find"] == subject
    state.search_results.append({"id": "official:anchor", "name": subject})
    enabled, constraints, _ = planning_tools(state)
    assert "compare" in enabled and "discover" in enabled
    assert constraints["required_anchor_ids"] == ["official:anchor"]


def test_pronoun_uses_unique_read_source_not_literal_search_anchor():
    state = LearningConversation(id=uuid4(), revision=0, sources=[{"id": "x", "name": "경복궁"}])
    update_contract(state, "이 유산과 해외 궁전을 구조로 비교해 줘")
    assert state.task_contract["subject"] == "경복궁"


def test_start_completion_and_current_building_are_distinguished():
    assert "공사를 시작한" in beginner_text("시대", "Construction began in 1023.")
    assert "공사를 마친" in beginner_text("시대", "The hall was completed in 1511.")
    text = beginner_text("시대", "현재의 탑은 1644년 지어진 것입니다.")
    assert "현재 남아 있는" in text and "처음" not in text
    assert "현재 남아 있는" not in beginner_text(
        "시대", "At present, records say it was built in 700."
    )


def test_starting_year_and_multi_stage_precision_are_preserved():
    quote = "The fort was rebuilt from 1565 and later decorated in marble."
    assert read_period(quote).text == "1565년부터"
    assert "1565년부터예요" in beginner_text("시대", quote)
    text = beginner_text(
        "시대", "It was built in several stages, about 5000 years ago and 2500 BC."
    )
    assert "여러 단계" in text and "한 해" in text
    assert read_period("It was built in several stages, about 5000 years ago and 2500 BC.") is None


def test_dome_is_not_automatically_a_roof_and_octagon_is_room_scoped():
    quote = "The stupa has a hemispherical dome."
    labels = {label for _, label in reading_units("구조", quote)}
    assert "둥근 돔" in labels and "둥글게 덮은 지붕" not in labels
    assert observation_scope("공을 반으로 자른 모양", quote) == "돔의 모양"
    text = beginner_text("구조", "Step inside the grand octagonal chamber.")
    assert "방의 모양" in text


def test_beginner_questions_are_direct_and_remediation_is_short():
    assert content_question("층수") == "몇 층으로 설명되어 있나요?"
    assert "재료" in content_question("재료") and "표현은" not in content_question("재료")
    text = activity_question("재료", {"mode": "scaffold"}, quote="The roof is made of wood.")
    assert "무엇으로 만들었나요" in text and "The roof is made of wood." in text
