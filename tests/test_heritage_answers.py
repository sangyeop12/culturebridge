"""A heritage question must produce an in-service answer, not a history link list."""

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
    create_conversation,
    send_learning_turn,
)
from culturebridge.services.learning_subject_service import heritage_subject, overview_excerpt

QUOTE = "경복궁은 조선 왕조의 궁궐이다. 조선 태조 때 처음 세웠으며 왕이 정사를 돌보던 곳이다."
ITEM = OfficialHeritageItem(
    kind_code="13", asset_number="0000117000000", region_code="11", name="서울 경복궁"
)


@pytest.fixture(autouse=True)
def sources(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "answers.db")
    initialize_database()
    monkeypatch.setattr(
        learning,
        "search_official_heritages",
        lambda *a, **kw: OfficialSearchResult(items=[ITEM], total=1, page=1, page_size=10),
    )
    monkeypatch.setattr(
        learning,
        "get_official_document",
        lambda *a: OfficialDocument(
            **ITEM.model_dump(),
            content=QUOTE,
            source_url="https://www.khs.go.kr/",
            retrieved_at=datetime.now(UTC),
        ),
    )


@pytest.mark.parametrize("text", ["경복궁에 대해 알고 싶어요", "경복궁에 대해 배우고 싶어요"])
def test_failed_gemini_still_reads_and_answers_from_actual_source(monkeypatch, text):
    calls = []

    class QuotaError(Exception):
        code = 429

    def unavailable(_):
        calls.append(1)
        raise QuotaError()

    monkeypatch.setattr(learning, "_model_decision", unavailable)
    state = create_conversation()
    result = send_learning_turn(state.id, LearningTurn(request_id=uuid4(), revision=0, text=text))
    assert calls == [1]  # No further model calls after the provider limit.
    assert [o["tool"] for o in result.tool_observations] == ["search", "read"]
    assert QUOTE in result.messages[-1].text
    assert result.messages[-1].citations[0]["quote"] == QUOTE
    assert result.messages[-1].teaching["method"] == "local_guide"
    assert any(s["url"].startswith("/discover/khs/") for s in result.messages[-1].suggestions)
    assert "요청 한도" in result.notice
    assert result.plan_history[-1]["planner_error"]["code"] == 429
    assert "신편 한국사" not in result.messages[-1].text
    assert "AI 연결이 복구되면" not in result.messages[-1].text
    assert result.pending_request == text


def test_model_history_misroute_is_corrected_before_tool_execution(monkeypatch):
    choices = iter(
        [
            LearningDecision(action="search_history", query="경복궁"),
            LearningDecision(action="read", source_id=ITEM.record_id),
        ]
    )
    monkeypatch.setattr(learning, "_model_decision", lambda _: next(choices))
    state = create_conversation()
    result = send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=0, text="경복궁에 대해 알고 싶어요")
    )
    assert [o["tool"] for o in result.tool_observations] == ["search", "read"]
    assert QUOTE in result.messages[-1].text
    assert result.plan_history[-1]["action"] == "explain"


@pytest.mark.parametrize("text", ["역사에 대해 알고 싶어요", "세종대왕에 대해 알고 싶어요"])
def test_broad_history_and_people_are_not_classified_as_heritages(text):
    assert heritage_subject(text) == ""


def test_overview_never_cuts_qualification_from_long_sentence():
    assert overview_excerpt("가" * 710 + " 추정된다고 한다.") == ""
    assert overview_excerpt(QUOTE) == QUOTE


def test_overview_uses_paragraph_about_named_object():
    palace = "불국사는 통일신라 시대 사찰로 여러 건물이 있다."
    tower = "다보탑은 불국사 뜰에 있는 석탑으로 석가탑과 마주 보고 있다."
    assert overview_excerpt(palace + "\n" + tower, "경주 불국사 다보탑") == tower
    assert overview_excerpt(palace, "경주 불국사 다보탑") == ""


def test_tower_answer_uses_tower_paragraph_not_temple_background(monkeypatch):
    tower_item = ITEM.model_copy(update={"name": "경주 불국사 다보탑"})
    palace = "불국사는 통일신라 시대 사찰로 여러 건물이 있다."
    tower = "다보탑은 불국사 뜰에 있는 석탑으로 석가탑과 마주 보고 있다."
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    monkeypatch.setattr(
        learning,
        "search_official_heritages",
        lambda *a, **kw: OfficialSearchResult(items=[tower_item], total=1, page=1, page_size=10),
    )
    monkeypatch.setattr(
        learning,
        "get_official_document",
        lambda *a: OfficialDocument(
            **tower_item.model_dump(),
            content=palace + "\n" + tower,
            source_url="https://www.khs.go.kr/",
            retrieved_at=datetime.now(UTC),
        ),
    )
    state = create_conversation()
    result = send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=0, text="다보탑에 대해 알려주세요")
    )
    assert result.messages[-1].citations[0]["quote"] == tower
    assert palace not in result.messages[-1].text

    result.sources[0]["excerpts"][0]["quote"] = palace
    with transaction() as connection:
        connection.execute(
            "UPDATE learning_conversations SET state_json=? WHERE id=?",
            (result.model_dump_json(), str(result.id)),
        )
    resumed = send_learning_turn(
        result.id,
        LearningTurn(request_id=uuid4(), revision=result.revision, text="이어서 진행해 주세요"),
    )
    assert resumed.messages[-1].citations[0]["quote"] == tower


def test_palace_is_found_after_first_ten_component_results(monkeypatch):
    children = [
        ITEM.model_copy(update={"name": f"경복궁 구성 건물 {i}", "asset_number": str(i)})
        for i in range(1, 13)
    ]
    pages = []

    def search(query, *, page_size):
        pages.append(page_size)
        return OfficialSearchResult(items=children + [ITEM], total=13, page=1, page_size=page_size)

    monkeypatch.setattr(learning, "search_official_heritages", search)
    monkeypatch.setattr(learning, "_model_decision", lambda _: (_ for _ in ()).throw(ValueError()))
    state = create_conversation()
    result = send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=0, text="경복궁에 대해 알고 싶어요")
    )
    assert pages == [50]
    assert result.sources[0]["name"] == ITEM.name
    assert result.messages[-1].citations[0]["source_id"] == ITEM.record_id


def test_chat_displays_answer_provenance_and_internal_learning_actions(monkeypatch):
    monkeypatch.setattr(learning, "_model_decision", lambda _: (_ for _ in ()).throw(ValueError()))
    with TestClient(app) as client:
        state = client.post("/api/learning/conversations").json()
        result = client.post(
            f"/api/learning/conversations/{state['id']}/turns",
            json={"request_id": str(uuid4()), "revision": 0, "text": "경복궁에 대해 알고 싶어요"},
        )
        assert result.status_code == 200
        page = client.get(f"/learn?conversation_id={state['id']}")
        assert QUOTE in page.text
        assert "공식 자료 기본 설명 · Gemini 설명 미사용" in page.text
        assert "다른 나라 유산과 비교하기" in page.text
        assert "/discover/khs/13:0000117000000:11" in page.text


def test_continue_repairs_old_link_only_palace_conversation(monkeypatch):
    state = create_conversation()
    state.pending_request = "경복궁에 대해 알고 싶어요"
    state.search_results = [
        {
            "id": "nikh:old",
            "name": "경복궁 관련 사건",
            "metadata_only": True,
            "catalogue": "history",
            "reading_url": "https://db.history.go.kr/",
        }
    ]
    with transaction() as connection:
        connection.execute(
            "UPDATE learning_conversations SET state_json=? WHERE id=?",
            (state.model_dump_json(), str(state.id)),
        )
    monkeypatch.setattr(learning, "_model_decision", lambda _: (_ for _ in ()).throw(ValueError()))
    result = send_learning_turn(
        state.id, LearningTurn(request_id=uuid4(), revision=0, text="이어서 진행해 주세요")
    )
    assert [o["tool"] for o in result.tool_observations] == ["search", "read"]
    assert QUOTE in result.messages[-1].text
