import json

from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.main import app
from culturebridge.services.conversation_title_service import conversation_title


def test_title_uses_first_real_question_and_stays_stable():
    state = {
        "goal": "",
        "messages": [
            {"role": "user", "text": "안녕하세요"},
            {"role": "assistant", "text": "무엇이 궁금한가요?"},
            {"role": "user", "text": "경복궁에 대해 알고 싶어요"},
            {"role": "user", "text": "이어서 진행해 주세요"},
        ],
    }
    assert conversation_title(state) == "경복궁 알아보기"
    state["messages"].append({"role": "user", "text": "조금 더 쉽게 설명해 주세요"})
    assert conversation_title(state) == "경복궁 알아보기"


def test_empty_chat_and_long_question_have_readable_labels():
    assert conversation_title({}) == "새 대화"
    text = "다보탑과 호류지의 재료와 구조를 비교하면서 " * 5
    title = conversation_title({"messages": [{"role": "user", "text": text}]})
    assert len(title) <= 44 and title.endswith("…")


def test_old_saved_chats_get_distinct_titles_in_api_and_sidebar(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "titles.db")
    initialize_database()
    with TestClient(app) as client:
        for text in ("경복궁에 대해 알고 싶어요", "다보탑에 대해 배우고 싶어요"):
            state = client.post("/api/learning/conversations").json()
            state["messages"] = [{"role": "user", "text": text}]
            with transaction() as connection:
                connection.execute(
                    "UPDATE learning_conversations SET state_json=? WHERE id=?",
                    (json.dumps(state), state["id"]),
                )
        items = client.get("/api/learning/conversations").json()
        assert {item["title"] for item in items} == {"경복궁 알아보기", "다보탑 알아보기"}
        page = client.get(f"/learn?conversation_id={state['id']}")
        assert page.status_code == 200
        assert "경복궁 알아보기" in page.text and "다보탑 알아보기" in page.text
