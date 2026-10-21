import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import LearningDecision, LearningTurn
from culturebridge.domain.models import ExtractedField, QuizAttemptResult, QuizReviewItem
from culturebridge.main import app
from culturebridge.services.conversation_review_service import ReviewNotFoundError
from culturebridge.services.data_retention_service import delete_records
from culturebridge.services.learning_conversation_service import (
    ConversationConflictError,
    create_conversation,
    get_conversation,
    send_learning_turn,
)
from culturebridge.services.learning_history_service import list_learning_reviews
from culturebridge.services.operation_service import owner_key, session_owner

QUOTE = "석굴암은 화강암으로 만든 인공 석굴이다."
URL = "https://www.khs.go.kr/cha/SearchKindOpenapiDt.do"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "review.db")
    monkeypatch.setattr(get_settings(), "public_mode", False)
    initialize_database()
    marker = session_owner.set("review-a")
    yield
    session_owner.reset(marker)


def graded(*, owner=None, grounded=True, score=0):
    with transaction() as connection:
        identity = connection.execute(
            "INSERT INTO learning_history(session_id,heritage_id,level,score,total) "
            "VALUES('test-review','seokguram','beginner',?,2)",
            (score,),
        ).lastrowid
        field = ExtractedField(
            heritage_id="seokguram",
            category="재료",
            value="화강암",
            evidence_quote=QUOTE,
            source_url=URL,
            verification_status="verified",
            note="단위 검사",
        )
        result = QuizAttemptResult(
            history_id=identity,
            quiz_id="test-review",
            score=score,
            total=2,
            explanations=["해설"],
            review_items=[
                QuizReviewItem(
                    number=n,
                    question="석굴암의 재료를 설명해 볼까요?",
                    selected="목재",
                    correct_answer="화강암",
                    activity="원문의 재료 표현을 찾아보세요.",
                    quote=QUOTE if grounded else "",
                    source_url=URL if grounded else None,
                )
                for n in range(1, 3 - score)
            ],
            evidence=[field] if grounded else [],
        )
        connection.execute(
            "INSERT INTO learning_reviews VALUES(?,?,?,?)",
            (identity, result.quiz_id, result.model_dump_json(), owner or owner_key()),
        )
    return identity


def turn(state, **kwargs):
    return send_learning_turn(
        state.id,
        LearningTurn(
            request_id=uuid4(),
            revision=state.revision,
            **kwargs,
        ),
    )


def test_import_owned_record_without_model_or_automatic_assessment(isolated, monkeypatch):
    monkeypatch.setattr(learning, "_model_decision", lambda _: pytest.fail("creation called AI"))
    history_id = graded()
    state = create_conversation(review_history_id=history_id)
    assert state.quiz_review["history_id"] == history_id
    assert state.checkpoint["quote"] == QUOTE and state.checkpoint["concept"] == "재료"
    assert state.messages[-1].citations[0]["url"] == URL
    assert state.concepts == {} and state.revision == 0
    assert create_conversation(review_history_id=history_id).id == state.id
    with transaction() as connection:
        assert connection.execute("SELECT count(*) FROM learning_conversations").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM learner_profiles").fetchone()[0] == 0
        state.revision = 200
        connection.execute(
            "UPDATE learning_conversations SET revision=200,state_json=? WHERE id=?",
            (state.model_dump_json(), str(state.id)),
        )
    assert create_conversation(review_history_id=history_id).id != state.id


def test_shared_local_record_is_not_importable_by_other_owner(isolated):
    history_id = graded()
    marker = session_owner.set("review-b")
    try:
        assert list_learning_reviews()[0]["can_conversation_review"] is False
        with pytest.raises(ReviewNotFoundError):
            create_conversation(review_history_id=history_id)
    finally:
        session_owner.reset(marker)


@pytest.mark.parametrize("mode", ["missing", "mismatched_quote", "insufficient", "ambiguous"])
def test_no_grounded_checkpoint_for_missing_or_ambiguous_evidence(isolated, mode):
    identity = graded(grounded=mode != "missing")
    if mode != "missing":
        with transaction() as connection:
            data = json.loads(
                connection.execute(
                    "SELECT result_json FROM learning_reviews WHERE history_id=?",
                    (identity,),
                ).fetchone()[0]
            )
            if mode == "mismatched_quote":
                data["evidence"][0]["evidence_quote"] = "다른 유산의 근거"
            elif mode == "insufficient":
                data["evidence"][0]["verification_status"] = "insufficient_evidence"
            else:
                data["evidence"].append({**data["evidence"][0], "category": "구조"})
            connection.execute(
                "UPDATE learning_reviews SET result_json=? WHERE history_id=?",
                (json.dumps(data), identity),
            )
    state = create_conversation(review_history_id=identity)
    assert not state.checkpoint and not state.sources and not state.concepts
    assert "근거가 부족" in state.messages[-1].text


def test_perfect_score_does_not_imply_mastery(isolated):
    state = create_conversation(review_history_id=graded(score=2))
    assert state.concepts == {} and state.checkpoint == {}
    assert "모든 문항" in state.messages[-1].text


def test_switch_question_is_owned_revisioned_and_does_not_assess(isolated, monkeypatch):
    monkeypatch.setattr(learning, "_model_decision", lambda _: pytest.fail("selection called AI"))
    state = create_conversation(review_history_id=graded())
    state = turn(state, control="review_question", source_id="2")
    assert state.checkpoint["question_number"] == 2 and state.concepts == {}
    with pytest.raises(ValueError):
        turn(state, control="review_question", source_id="99")
    paused = turn(state, control="stop")
    with pytest.raises(ConversationConflictError):
        turn(paused, control="review_question", source_id="1")


def test_explanation_assessment_links_back_to_question_only_after_answer(isolated, monkeypatch):
    identity = graded()
    state = create_conversation(review_history_id=identity)
    source_id = state.checkpoint["source_id"]
    monkeypatch.setattr(
        learning,
        "_model_decision",
        lambda _: LearningDecision(
            action="review",
            source_id=source_id,
            concept="재료",
            assessment="tentative_support",
            assessment_quote=QUOTE,
            reason="사용자가 재료와 원문 표현을 연결했는지 잠정 검토",
        ),
    )
    state = turn(state, text="원문에 화강암으로 만들었다고 해서 화강암이라고 생각했어요.")
    observation = state.concepts["재료"]["observations"][-1]
    assert observation["history_id"] == identity and observation["question_number"] == 1
    assert observation["judgment"] == "tentative_support"
    assert state.messages[-1].citations[0]["quote"] == QUOTE


def test_change_topic_detaches_review_but_retains_previous_dialogue(isolated):
    identity = graded()
    original = create_conversation(review_history_id=identity)
    changed = turn(original, control="change_topic", text="새 주제로")
    assert not changed.quiz_review and not changed.checkpoint and not changed.sources
    assert QUOTE in changed.messages[1].text
    restarted = create_conversation(review_history_id=identity)
    assert restarted.id != original.id
    assert get_conversation(original.id).goal == "새 주제로"


def test_deletion_cascades_links_and_does_not_remove_other_owners(isolated):
    identity = graded()
    state = create_conversation(review_history_id=identity)
    marker = session_owner.set("review-b")
    other = create_conversation(review_history_id=graded())
    session_owner.reset(marker)
    delete_records(owner="review-a", apply=True)
    with transaction() as connection:
        assert connection.execute("SELECT count(*) FROM learning_review_links").fetchone()[0] == 1
    marker = session_owner.set("review-b")
    assert get_conversation(other.id).quiz_review
    session_owner.reset(marker)
    assert state.id != other.id


def test_api_and_ui_provide_explicit_start_not_get_side_effect(isolated):
    with TestClient(app) as a:
        # Establish an anonymous session without accessing real user records.
        first = a.post("/api/learning/conversations").json()
        with transaction() as connection:
            owner = connection.execute(
                "SELECT owner FROM learning_conversations WHERE id=?", (first["id"],)
            ).fetchone()[0]
        identity = graded(owner=owner)
        path = f"/api/learning/reviews/{identity}/conversation"
        assert a.get(path).status_code in {404, 405}
        with transaction() as connection:
            assert (
                connection.execute("SELECT count(*) FROM learning_conversations").fetchone()[0] == 1
            )
        cookies = dict(a.cookies)
        a.cookies.clear()
        assert a.post(path).status_code == 404
        assert "대화로 다시 익히기" not in a.get("/learning-history").text
        a.cookies.clear()
        a.cookies.update(cookies)
        created = a.post(path)
        assert created.status_code == 200
        assert a.post(path).json()["id"] == created.json()["id"]
        history = a.get("/learning-history").text
        assert "대화로 다시 익히기" in history
        assert "모든 문항을 맞혔어요" not in history
        page = a.get("/learn?conversation_id=" + created.json()["id"])
        assert page.status_code == 200 and "다른 문항 다시 살펴보기" in page.text
        assert "공식 원문" in page.text
