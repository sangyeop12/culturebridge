import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.main import app


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "titles.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()


@pytest.mark.parametrize(
    "path,title",
    [
        ("/", "하나의 문화유산에서 세계로"),
        ("/official", "한국 문화유산 둘러보기"),
        ("/unesco", "세계유산 둘러보기"),
        ("/comparisons", "다시 보는 비교 기록"),
        ("/explore/seokguram", "함께 알아보면 좋은 문화유산"),
        ("/research/seokguram/horyuji", "두 문화유산 함께 알아보기"),
    ],
)
def test_service_facing_page_titles(isolated, path, title):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200 and title in response.text
    assert "공식 자료로 Agent 탐구" not in response.text
    assert "시대·구조·재료·종교적 배경 추출 결과" not in response.text
