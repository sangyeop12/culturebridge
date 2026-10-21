from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from culturebridge.agents import learning
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.learning import LearningDecision, LearningTurn
from culturebridge.domain.official_models import (
    OfficialDocument,
    OfficialHeritageItem,
    OfficialSearchResult,
)
from culturebridge.main import app
from culturebridge.services.learning_conversation_service import (
    ConversationConflictError,
    ConversationNotFoundError,
    create_conversation,
    get_conversation,
    request_learning_stop,
    send_learning_turn,
)
from culturebridge.services.operation_service import clear_operation_cache, session_owner

QUOTE = "이 석탑은 화강암으로 만든 탑이며 751년에 건립되었다."
IDENTITY = "khs:11:0000200000000:37"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "conversations.db")
    monkeypatch.setattr(get_settings(), "storage_secret", "learning-tests-secret-32-characters")
    monkeypatch.setattr(get_settings(), "public_mode", False)
    initialize_database()
    token = session_owner.set("learner-a")
    yield
    session_owner.reset(token)


def turn(state, text="궁금해요", **kwargs):
    return send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=state.revision, text=text, **kwargs)
    )


def script(monkeypatch, decisions):
    items = iter(decisions)
    monkeypatch.setattr(learning, "_model_decision", lambda _: next(items))


def sources(monkeypatch):
    item = OfficialHeritageItem(
        kind_code="11", asset_number="0000200000000", region_code="37", name="경주 불국사 다보탑"
    )
    monkeypatch.setattr(
        learning,
        "search_official_heritages",
        lambda *a, **kw: OfficialSearchResult(items=[item], total=1, page=1, page_size=10),
    )
    monkeypatch.setattr(
        learning,
        "get_official_document",
        lambda *a: OfficialDocument(
            **item.model_dump(),
            content=QUOTE,
            source_url="https://www.khs.go.kr/cha/SearchKindOpenapiDt.do",
            retrieved_at=datetime.now(UTC),
        ),
    )


def evidence_state():
    state = create_conversation()
    state.sources = [
        {
            "id": IDENTITY,
            "name": "다보탑",
            "url": "https://www.khs.go.kr/",
            "excerpts": [{"concept": "재료", "quote": QUOTE}],
            "reading_url": "/official/11/0000200000000/37",
            "comparison_url": "/discover/khs/11:0000200000000:37",
        }
    ]
    state.checkpoint = {"concept": "재료", "source_id": IDENTITY, "quote": QUOTE}
    with transaction() as conn:
        conn.execute(
            "UPDATE learning_conversations SET state_json=? WHERE id=?",
            (state.model_dump_json(), str(state.id)),
        )
    return state


def test_free_start_and_reconnection_without_pair_or_level(isolated):
    with TestClient(app) as client:
        state = client.post("/api/learning/conversations").json()
        request = {
            "request_id": str(uuid4()),
            "revision": 0,
            "text": "역사를 잘 모르는데 어디부터 시작할까?",
        }
        response = client.post(f"/api/learning/conversations/{state['id']}/turns", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["revision"] == 1 and len(data["messages"]) == 2
        assert data["concepts"] == {} and "제한된 안내" in data["notice"]
        assert client.get(f"/api/learning/conversations/{state['id']}").json() == data
        assert client.get("/").status_code == 200
        assert client.get(f"/learn?conversation_id={state['id']}").status_code == 200


def test_private_ownership_even_when_not_in_public_mode(isolated):
    with TestClient(app) as a, TestClient(app) as b:
        state = a.post("/api/learning/conversations").json()
        assert b.get(f"/api/learning/conversations/{state['id']}").status_code == 404
        assert b.get("/api/learning/conversations").json() == []


def test_idempotency_survives_cache_clear_and_conflicting_request_rejected(isolated):
    state = create_conversation()
    request = LearningTurn(request_id=uuid4(), revision=0, text="역사가 궁금해요")
    result = send_learning_turn(state.id, request)
    clear_operation_cache()
    assert send_learning_turn(state.id, request) == result
    with pytest.raises(ConversationConflictError):
        send_learning_turn(state.id, request.model_copy(update={"text": "다른 내용"}))
    with pytest.raises(ConversationConflictError):
        turn(state)


def test_real_graph_selects_search_read_then_check(isolated, monkeypatch):
    sources(monkeypatch)
    script(
        monkeypatch,
        [
            LearningDecision(action="search", query="불국사"),
            LearningDecision(action="read", source_id=IDENTITY),
            LearningDecision(
                action="check",
                source_id=IDENTITY,
                concept="재료",
                goal="탑의 재료를 원문으로 살펴보기",
                question="무엇으로 만들었나요?",
            ),
        ],
    )
    result = turn(create_conversation(), "불국사가 궁금해요")
    assert result.checkpoint["source_id"] == IDENTITY
    assert result.messages[-1].citations[0]["quote"] in QUOTE
    assert result.plan_history[-1]["planner"] == "ai"
    assert len(result.plan_history[-1]["tools"]) == 2


@pytest.mark.parametrize(
    "judgment,action",
    [
        ("possible_misconception", "review"),
        ("tentative_support", "check"),
    ],
)
def test_answer_reason_changes_next_learning_and_saves_tentative_evidence(
    isolated, monkeypatch, judgment, action
):
    state = evidence_state()
    script(
        monkeypatch,
        [
            LearningDecision(
                action=action,
                source_id=IDENTITY,
                concept="재료",
                assessment=judgment,
                assessment_quote=QUOTE,
                reason="설명의 재료 표현을 원문과 다시 대조하기",
            )
        ],
    )
    result = turn(state, "나무로 만들었다고 생각했어요. 모양 때문이에요.")
    record = result.concepts["재료"]
    assert record["status"] == judgment
    assert record["observations"][0]["quote"] == QUOTE
    assert result.plan_history[-1]["assessment_updated"]
    assert create_conversation().concepts == result.concepts


def test_invalid_assessment_cannot_change_profile(isolated, monkeypatch):
    state = evidence_state()
    script(
        monkeypatch,
        [
            LearningDecision(
                action="review",
                source_id=IDENTITY,
                concept="재료",
                assessment="possible_misconception",
                assessment_quote="지어낸 근거는 사용할 수 없어요.",
            )
        ],
    )
    assert turn(state, "이 탑은 나무로 만들었다고 생각해요").concepts == {}


def test_fabricated_tool_id_never_reaches_provider(isolated, monkeypatch):
    script(
        monkeypatch,
        [
            LearningDecision(action="read", source_id="khs:11:999:37"),
            LearningDecision(action="explain", source_id="khs:11:999:37"),
        ],
    )
    monkeypatch.setattr(learning, "get_official_document", lambda *a: pytest.fail("forged id"))
    result = turn(create_conversation())
    assert not result.sources and not result.messages[-1].citations
    assert "근거가 아직 없어요" in result.messages[-1].text


def test_offline_source_selection_remains_usable(isolated, monkeypatch):
    sources(monkeypatch)
    state = turn(create_conversation(), "불국사")
    assert state.search_results
    result = turn(state, text="", control="read_source", source_id=IDENTITY)
    assert result.messages[-1].citations
    with pytest.raises(ValueError):
        turn(result, text="", control="read_source", source_id="https://evil.example")


def test_control_actions_do_not_call_ai_and_disputes_are_not_erased(isolated, monkeypatch):
    state = evidence_state()
    monkeypatch.setattr(learning, "_model_decision", lambda _: pytest.fail("control called AI"))
    paused = turn(state, text="", control="stop")
    assert paused.status == "paused"
    with pytest.raises(ConversationConflictError):
        turn(paused)
    resumed = turn(paused, text="", control="resume")
    assert resumed.status == "active"
    changed = turn(resumed, text="궁궐을 알고 싶어요", control="change_topic")
    assert not changed.sources and not changed.checkpoint
    assert changed.goal == "궁궐을 알고 싶어요"


def test_repeated_tool_and_budget_are_bounded(isolated, monkeypatch):
    calls = []
    monkeypatch.setattr(
        learning, "_model_decision", lambda _: LearningDecision(action="search", query="탑")
    )
    monkeypatch.setattr(
        learning,
        "search_official_heritages",
        lambda *a, **kw: (
            calls.append(a) or OfficialSearchResult(items=[], total=0, page=1, page_size=10)
        ),
    )
    result = turn(create_conversation())
    assert len(calls) == 1
    assert not result.concepts


def test_all_new_records_deleted_with_session(isolated):
    from culturebridge.services.data_retention_service import delete_session_records

    state = turn(create_conversation())
    delete_session_records()
    with pytest.raises(ConversationNotFoundError):
        get_conversation(state.id)
    with transaction() as conn:
        for table in (
            "learning_conversations",
            "learning_turn_requests",
            "learner_profiles",
            "learning_interrupts",
        ):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_stop_during_planning_prevents_next_tool_and_discards_assessment(isolated, monkeypatch):
    state = evidence_state()

    def interrupted(_):
        request_learning_stop(state.id, state.revision)
        return LearningDecision(action="search", query="탑")

    monkeypatch.setattr(learning, "_model_decision", interrupted)
    monkeypatch.setattr(
        learning, "search_official_heritages", lambda *a, **k: pytest.fail("cancelled tool ran")
    )
    result = turn(state)
    assert result.status == "paused" and result.concepts == {}
    assert not result.messages[-1].citations
    assert result.plan_history[-1]["action"] == "stop"


def test_concurrent_duplicate_turn_executes_once(isolated, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    calls = []
    state = create_conversation()
    request = LearningTurn(request_id=uuid4(), revision=0, text="역사가 궁금해요")
    monkeypatch.setattr(
        learning,
        "_model_decision",
        lambda _: (
            calls.append(1) or LearningDecision(action="ask", question="어떤 시대가 궁금한가요?")
        ),
    )

    def send():
        marker = session_owner.set("learner-a")
        try:
            return send_learning_turn(state.id, request)
        finally:
            session_owner.reset(marker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: send(), range(2)))
    assert a == b and len(calls) == 1


def test_model_receives_distinct_prior_understanding_and_bounded_context(isolated, monkeypatch):
    import json
    from types import SimpleNamespace

    captured = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            context = json.loads(kwargs["contents"])
            captured.append(context)
            assert len(kwargs["contents"]) <= 18000
            assert kwargs["config"].max_output_tokens == 1200
            if context["concepts"]:
                decision = LearningDecision(
                    action="ask",
                    goal="건립과 재건의 사건을 대조하기",
                    question="처음 지은 때와 다시 지은 때를 구분해 볼까요?",
                )
            else:
                decision = LearningDecision(
                    action="ask",
                    goal="관심 있는 시대부터 찾아보기",
                    question="어떤 시대의 이야기가 궁금한가요?",
                )
            return SimpleNamespace(text=decision.model_dump_json())

    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only")
    monkeypatch.setattr(learning.genai, "Client", Client)
    first = turn(create_conversation(), "불국사가 궁금해요")
    with transaction() as conn:
        profile = {"시대": {"status": "tentative_support", "observations": []}}
        conn.execute(
            "INSERT OR REPLACE INTO learner_profiles VALUES(?,?)",
            ("learner-a", json.dumps(profile)),
        )
    second = turn(create_conversation(), "불국사가 궁금해요")
    assert first.goal != second.goal
    assert captured[0]["concepts"] != captured[1]["concepts"]


def test_api_validation_and_interrupt_ownership(isolated):
    with TestClient(app) as a, TestClient(app) as b:
        state = a.post("/api/learning/conversations").json()
        path = f"/api/learning/conversations/{state['id']}"
        assert b.post(path + "/interrupt", json={"revision": 0}).status_code == 404
        assert a.post(path + "/turns", json={"revision": 0, "text": "hello"}).status_code == 422
        payload = {"request_id": str(uuid4()), "revision": 0, "text": "x" * 1001}
        assert a.post(path + "/turns", json=payload).status_code == 422
        payload["text"] = "궁금해요"
        assert a.post(path + "/turns", json=payload).status_code == 200
        payload["request_id"] = str(uuid4())
        assert a.post(path + "/turns", json=payload).status_code == 409
