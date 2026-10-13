from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.models import CollectedSource, LearningLevel
from culturebridge.domain.official_models import OfficialDocument
from culturebridge.services.lesson_service import beginner_text, explain_source, official_source


@pytest.fixture
def document(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "lesson.db")
    initialize_database()
    return OfficialDocument(
        kind_code="11",
        asset_number="20",
        region_code="37",
        name="경주 불국사 다보탑",
        content="불국사는 751년에 창건된 사찰이다.\n다보탑은 팔각형 기단과 난간이 있는 석탑이다.\n"
        "다보탑이 건립된 시기는 751년으로 추측된다.\n탑은 법화경의 내용을 표현했다.",
        source_url="https://www.khs.go.kr/cha/SearchKindOpenapiDt.do",
        retrieved_at=datetime.now(UTC),
        cached=True,
    )


def test_three_levels_have_different_bodies_and_preserve_original(document):
    source = official_source(document)
    before = source.model_dump_json()
    beginner = explain_source(source, LearningLevel.BEGINNER)
    intermediate = explain_source(source, LearningLevel.INTERMEDIATE)
    advanced = explain_source(source, LearningLevel.ADVANCED)
    assert beginner.sections[0].text != intermediate.sections[0].text
    assert "추정·전승" in beginner.sections[0].text
    assert "아랫부분" in beginner.sections[1].text
    assert intermediate.sections[0].heading == "시대"
    assert "추측" in intermediate.sections[0].text
    assert advanced.original_text == document.content and not advanced.sections
    assert beginner.original_text == intermediate.original_text == advanced.original_text
    assert source.model_dump_json() == before


def test_missing_fields_stay_missing(document):
    document.content = "다보탑은 팔각형 기단이 있는 탑이다."
    lesson = explain_source(official_source(document))
    assert "직접 근거" in lesson.sections[0].text
    assert "직접 근거" in lesson.sections[2].text
    assert "화강암" not in " ".join(s.text for s in lesson.sections)


def test_stale_text_not_promoted_to_learning_summary(document):
    document.stale = True
    lesson = explain_source(official_source(document))
    assert not lesson.sections and "보류" in lesson.notice
    assert lesson.original_text == document.content


def test_rebuilding_and_negation_are_retained():
    text = beginner_text("시대", "궁궐은 1867년에 재건되었으며 창건 연대가 아니다.")
    assert "재건·복원" in text and "부정" in text


def test_foreign_source_reading_guide_is_not_called_official_translation():
    source = CollectedSource(
        id="unesco:999",
        heritage_id="unesco:999",
        title="Example Temple",
        organization="UNESCO",
        source_url="https://whc.unesco.org/en/list/999/",
        feed_url="https://data.unesco.org/",
        content="Built in the 8th century. A Buddhist wooden temple layout.",
        content_kind="listed_text",
        status="fresh",
        retrieved_at=datetime.now(UTC),
        scope_note="Test",
    )
    lesson = explain_source(source)
    assert "전체 번역문이 아닙니다" in lesson.notice
    assert "8세기" in lesson.sections[0].text
    assert "나무" in lesson.sections[2].text
    assert "원문 표현 해설" in explain_source(source, "intermediate").sections[2].text
    assert explain_source(source, "advanced").original_text == source.content


@pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
def test_lesson_api_and_ui_use_requested_level(document, monkeypatch, level):
    from culturebridge.api import router
    from culturebridge.main import app
    from culturebridge.ui import pages

    monkeypatch.setattr(router, "get_official_document", lambda *a: document)
    monkeypatch.setattr(pages, "get_official_document", lambda *a: document)
    with TestClient(app) as client:
        response = client.get("/api/official/heritages/11/20/37/lesson", params={"level": level})
        page = client.get("/official/11/20/37", params={"level": level})
        raw = client.get("/api/official/heritages/11/20/37")
    assert response.status_code == page.status_code == raw.status_code == 200
    assert response.json()["level"] == level
    assert response.json()["original_text"] == raw.json()["content"] == document.content
    assert "설명 학습 수준" in page.text
    assert ("공식 원문 전체 보기" in page.text) == (level != "advanced")


def test_lesson_api_rejects_unknown_level(document, monkeypatch):
    from culturebridge.main import app

    with TestClient(app) as client:
        assert client.get("/api/official/heritages/11/20/37/lesson?level=expert").status_code == 422
