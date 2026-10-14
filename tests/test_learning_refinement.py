import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, load_quiz_items, transaction
from culturebridge.domain.models import CollectedSource, LearningAmount, LearningGoal, LearningLevel
from culturebridge.main import app
from culturebridge.services import relearning_service as relearning
from culturebridge.services.comparison_service import (
    LEARNING_VERSION,
    create_saved_comparison,
    get_saved_comparison,
)
from culturebridge.services.evidence_reading_service import reading_units
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.learning_analysis_service import comparison_explanation
from culturebridge.services.lesson_service import beginner_text
from culturebridge.services.quiz_service import generate_quiz, grade_quiz


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "refinement.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    monkeypatch.setattr(get_settings(), "public_mode", False)
    monkeypatch.setattr(
        get_settings(), "storage_secret", "refinement-test-secret-at-least-32-characters"
    )
    initialize_database()
    texts = [
        (
            "seokguram",
            "석굴암",
            "석굴암은 751년에 건립되었다. 석굴암은 팔각형 전실이 있는 석굴이다. "
            "석굴암은 화강암으로 만들었다. 석굴암은 불교와 관련된다.",
        ),
        (
            "horyuji",
            "Horyuji Temple",
            "The Horyuji Temple was built in 700. The temple is inside a Buddhist temple. "
            "The temple is made of wood. The temple is a Buddhist place of worship.",
        ),
    ]
    return [
        CollectedSource(
            id="fixture:" + identity,
            heritage_id=identity,
            title=title,
            organization="Official fixture",
            source_url="https://www.khs.go.kr/" + identity,
            feed_url="https://www.khs.go.kr/",
            content=text,
            content_kind="individual_text",
            status="fresh",
            retrieved_at=datetime.now(UTC),
            scope_note="Individual fixture",
        )
        for identity, title, text in texts
    ]


def saved(sources):
    return create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=extract_fields(sources, ["seokguram", "horyuji"]),
        goal=LearningGoal.COMPARE,
        goal_text="구조와 재료",
        amount=LearningAmount.DEEP,
    )


def test_beginner_foreign_features_are_sentences_not_only_keywords():
    text = beginner_text("구조", "The palace is set over a single storey, with a balustrade.")
    assert "한 층" in text and "난간" in text and "원문에서 찾아볼 표현" not in text
    assert "나무" in beginner_text("재료", "The temple is made of wood.")


def test_negated_features_are_never_made_positive():
    assert reading_units("재료", "The pagoda is not made of wood.") == []
    assert reading_units("구조", "The hall does not have an antechamber.") == []


def test_comparison_uses_common_axis_not_absence_as_difference(sources):
    fields = extract_fields(sources, ["seokguram", "horyuji"])
    by = {(f.heritage_id, f.category): f for f in fields}
    text = comparison_explanation("시대", by["seokguram", "시대"], by["horyuji", "시대"])
    assert "751" in text and "700" in text and "51년" in text
    text = comparison_explanation("구조", by["seokguram", "구조"], by["horyuji", "구조"])
    assert "없다" not in text  # unrelated axes cannot prove architectural absence


def test_quiz_covers_both_heritages_and_keeps_choice_provenance(sources):
    comparison = saved(sources)
    quiz = generate_quiz(
        "seokguram", "horyuji", comparison.level, comparison_id=comparison.saved_id
    )
    assert len(quiz.items) == 5
    questions = " ".join(item.question for item in quiz.items)
    assert "석굴암" in questions and "호류지" in questions
    rows = load_quiz_items(quiz.quiz_id)
    result = grade_quiz(quiz.quiz_id, [(row["correct_index"] + 1) % 4 for row in rows])
    assert result.score == 0
    assert any(item.quote and "temple" in item.quote.casefold() for item in result.review_items)


def test_relearn_preserves_archive_and_goals_and_refreshes_sources(sources, monkeypatch):
    previous = saved(sources)
    before = get_saved_comparison(previous.saved_id).model_dump_json()
    calls = []

    def collect(*args, **kwargs):
        calls.append(kwargs)
        return sources

    monkeypatch.setattr(relearning, "collect_official_sources", collect)
    updated = relearning.relearn_saved_comparison(previous.saved_id)
    assert calls == [{"refresh": True}]
    assert updated.saved_id != previous.saved_id and updated.learning_version == LEARNING_VERSION
    assert (updated.goal, updated.goal_text, updated.amount) == (
        previous.goal,
        previous.goal_text,
        previous.amount,
    )
    assert get_saved_comparison(previous.saved_id).model_dump_json() == before


def test_legacy_snapshot_defaults_to_version_zero_and_offers_relearning(sources):
    previous = saved(sources)
    with transaction() as conn:
        row = conn.execute(
            "SELECT content_json FROM comparisons WHERE id=?", (previous.saved_id,)
        ).fetchone()
        content = json.loads(row["content_json"])
        content["comparison"].pop("learning_version")
        conn.execute(
            "UPDATE comparisons SET content_json=? WHERE id=?",
            (json.dumps(content), previous.saved_id),
        )
    assert get_saved_comparison(previous.saved_id).comparison.learning_version == 0
    page = TestClient(app).get(f"/compare/seokguram/horyuji?saved_id={previous.saved_id}")
    assert "이전 방식" in page.text and "최신 근거로 다시 탐구하기" in page.text


def test_relearning_api_obeys_session_ownership(sources, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_mode", True)
    with TestClient(app) as first, TestClient(app) as other:
        old = first.post(
            "/api/comparisons", json={"left_id": "seokguram", "right_id": "horyuji"}
        ).json()
        assert other.post("/api/comparisons/" + old["saved_id"] + "/relearn").status_code == 404


def test_old_quiz_advises_relearning_without_overwriting_it(sources):
    previous = saved(sources)
    quiz = generate_quiz("seokguram", "horyuji", previous.level, comparison_id=previous.saved_id)
    with transaction() as conn:
        row = conn.execute(
            "SELECT content_json FROM comparisons WHERE id=?", (previous.saved_id,)
        ).fetchone()
        content = json.loads(row["content_json"])
        content["comparison"]["learning_version"] = 0
        conn.execute(
            "UPDATE comparisons SET content_json=? WHERE id=?",
            (json.dumps(content), previous.saved_id),
        )
    with TestClient(app) as client:
        page = client.get(f"/quiz/seokguram/horyuji?quiz_id={quiz.quiz_id}")
    assert "이전 방식의 저장본" in page.text
    assert len(load_quiz_items(quiz.quiz_id)) == 5


def test_ai_quiz_cannot_ignore_one_supported_heritage(sources):
    from culturebridge.services.display_service import display_name
    from culturebridge.services.quiz_draft_service import QuizDraft, QuizDraftItem, validate_draft

    comparison = saved(sources)
    fields = comparison.extracted_fields
    names = {h.id: display_name(h.id, h.name) for h in (comparison.left, comparison.right)}
    indices = [
        next(i for i, f in enumerate(fields) if f.heritage_id == identity and f.category == "시대")
        for identity in ("seokguram", "horyuji")
    ]

    def draft(selection):
        return QuizDraft(
            items=[
                QuizDraftItem(
                    question=names[fields[index].heritage_id] + f"의 시대 원문은? {position}",
                    choices=[fields[index].evidence_quote, "조선 시대", "근대", "자료 없음"],
                    correct_index=0,
                    evidence_index=index,
                )
                for position, index in enumerate(selection)
            ]
        )

    with pytest.raises(ValueError, match="Both heritage"):
        validate_draft(draft([indices[0]] * 5), comparison, comparison.level, fields, ["시대"])
    assert (
        len(
            validate_draft(
                draft([indices[0], indices[1], indices[0], indices[1], indices[0]]),
                comparison,
                comparison.level,
                fields,
                ["시대"],
            )
        )
        == 5
    )


@pytest.mark.parametrize(
    "identity,expected", [("taj-mahal-mausoleum", "Tomb"), ("grand-trianon", "Palace")]
)
def test_individual_allowlist_has_explicit_subject_selectors(identity, expected):
    from culturebridge.services.dynamic_heritage_service import OfficialTarget
    from culturebridge.services.individual_source_service import INDIVIDUALS, Paragraphs

    record = INDIVIDUALS[identity]
    parser = Paragraphs()
    parser.feed(
        "<p>Contact and tickets</p><p>" + record["starts"][0] + " official introduction.</p>"
    )
    selected = [p for p in parser.rows if p.startswith(record["starts"])]
    assert len(selected) == 1 and record["type"] == expected
    assert OfficialTarget(provider="official", official_id=identity).id == "official:" + identity


def test_ai_answer_schema_cannot_invent_a_new_correct_fact(sources):
    from culturebridge.services.quiz_draft_service import _schema, allowed_answers

    comparison = saved(sources)
    fields = comparison.extracted_fields
    schema = _schema(fields, comparison.level)
    choices = schema["properties"]["items"]["items"]["properties"]["correct_answer"]["enum"]
    assert choices and all(len(choice) <= 120 for choice in choices)
    assert all(any(choice in allowed_answers(field) for field in fields) for choice in choices)
    assert "자료에 없는 역사적 사실" not in choices
