"""Offline coverage of reading, constrained repair, administration, and safe retention."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from culturebridge import maintenance
from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.models import CollectedSource, LearningGoal, LearningLevel
from culturebridge.restore_db import restore_database
from culturebridge.services import korean_lesson_service as korean
from culturebridge.services import quiz_draft_service as quiz_draft
from culturebridge.services.comparison_service import create_saved_comparison
from culturebridge.services.data_retention_service import delete_records, delete_session_records
from culturebridge.services.display_service import korean_name
from culturebridge.services.evidence_comparison_service import supported_fields
from culturebridge.services.evidence_reading_service import reading_units
from culturebridge.services.extraction_service import extract_fields
from culturebridge.services.individual_source_service import fetch_individual, search_individuals
from culturebridge.services.lesson_service import beginner_text, explain_source
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.operation_service import (
    OperationBusyError,
    deleting_session,
    reused_operation,
    session_owner,
)
from culturebridge.services.quiz_service import generate_quiz, grade_quiz
from culturebridge.services.source_registry_service import (
    record_attempt,
    save_review,
    source_overview,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    settings = get_settings()
    for key, value in {
        "db_path": tmp_path / "test.db",
        "backup_dir": tmp_path / "backups",
        "gemini_enabled": False,
        "maintenance_enabled": False,
        "retention_enabled": False,
        "public_mode": False,
        "quiz_repair_attempts": 1,
        "backup_keep": 2,
    }.items():
        monkeypatch.setattr(settings, key, value)
    initialize_database()
    token = session_owner.set(None)
    yield
    session_owner.reset(token)


def source(identity="seokguram"):
    return CollectedSource(
        id=identity,
        heritage_id=identity,
        title="Synthetic Hall",
        organization="Fixture",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        content_kind="individual_text",
        status="fresh",
        content="The hall was completed in 1511. The hall has a wooden roof. "
        "The hall is a Buddhist building.",
        scope_note="Synthetic, not heritage facts",
    )


def comparison():
    sources = [source(), source("horyuji")]
    return create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=extract_fields(sources, ["seokguram", "horyuji"]),
        goal=LearningGoal.OBSERVE,
    )


def test_expanded_reading_and_intermediate_axes_preserve_original():
    assert ("재료", "사암") in reading_units("재료", "The fort is made of sandstone.")
    assert ("재료", "석회암") in reading_units("재료", "The walls are limestone.")
    assert ("모양", "공을 반으로 자른 모양") in reading_units("구조", "A hemispherical dome.")
    assert "기원전 3세기" in beginner_text("시대", "Built in the 3rd century BCE.")
    assert "1511년" in beginner_text("시대", "The hall was completed in 1511.")
    original = source()
    lesson = explain_source(original, "intermediate")
    assert lesson.original_text == original.content
    assert any("읽는 기준" in item.text for item in lesson.sections)
    assert not explain_source(original, "advanced").sections


def valid_korean(lesson):
    texts = {
        "시대": "1511년에 완공되었다는 설명을 읽어 보세요.",
        "구조": "이 자료는 건물 자체를 설명하고 있어요.",
        "재료": "나무 재료를 사용했다는 설명이 나와요.",
        "종교적 배경": "이 자료에는 불교와 관련된 설명이 나와요.",
    }
    return korean.KoreanDraft(
        sections=[
            korean.KoreanSection(
                category=section.category,
                text=texts[section.category],
                evidence_quote=section.evidence_quote,
            )
            for section in lesson.sections
            if section.evidence_quote
        ]
    )


def test_korean_draft_cache_and_advanced_bypass(monkeypatch):
    assert korean.source_numbers("King James IV completed it in 1511.") == {"4", "1511"}
    assert korean.source_numbers("I read the description.") == set()
    original = source()
    lesson = explain_source(original)
    draft = valid_korean(lesson)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=draft.model_dump_json())

    monkeypatch.setattr(korean.genai, "Client", Client)
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "offline-fixture")
    korean.korean_lesson(original, cache_only=True)
    assert not calls
    result = korean.korean_lesson(original)
    assert "풀이 초안" in result.notice
    assert result.original_text == original.content
    korean.korean_lesson(original)
    assert len(calls) == 1
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    cached = korean.korean_lesson(original, cache_only=True)
    assert "풀이 초안" in cached.notice
    assert cached.sections == result.sections
    assert len(calls) == 1
    assert korean.korean_lesson(original, "advanced").original_text == original.content
    assert len(calls) == 1


@pytest.mark.parametrize("defect", ["quote", "number", "feature", "missing"])
def test_korean_draft_rejects_unsupported_changes(defect):
    lesson = explain_source(source())
    draft = valid_korean(lesson)
    if defect == "quote":
        draft.sections[0].evidence_quote += " fabricated"
    elif defect == "number":
        draft.sections[0].text += " 9999년"
    elif defect == "feature":
        next(
            s for s in draft.sections if s.category == "재료"
        ).text = "이 건물은 화강암 재료로 만들었어요."
    else:
        draft.sections.pop()
    with pytest.raises(ValueError):
        korean.validate_korean_draft(draft, lesson)


def make_quiz_draft(comp):
    fields = supported_fields(comp)
    indices = [
        next(
            i for i, f in enumerate(fields) if f.heritage_id == identity and f.category == category
        )
        for identity, category in [
            ("seokguram", "재료"),
            ("seokguram", "구조"),
            ("horyuji", "재료"),
            ("horyuji", "구조"),
            ("seokguram", "재료"),
        ]
    ]
    items = []
    for number, index in enumerate(indices):
        field = fields[index]
        name = comp.left.name if field.heritage_id == comp.left.id else comp.right.name
        items.append(
            quiz_draft.QuizDraftItem(
                question=f"{name}의 {field.category} 근거 후보를 고르세요. ({number + 1})",
                choices=[
                    field.value,
                    "명백한 시험 오답A",
                    "명백한 시험 오답B",
                    "명백한 시험 오답C",
                ],
                correct_index=0,
                evidence_index=index,
            )
        )
    return fields, quiz_draft.QuizDraft(items=items)


def test_quiz_repairs_bad_item_once_and_preserves_good_items(monkeypatch):
    comp = comparison()
    fields, good = make_quiz_draft(comp)
    bad = good.model_copy(deep=True)
    bad.items[1].choices[0] = "근거 없는 정답"
    calls = []

    def generate(*args):
        calls.append(args)
        return bad if len(calls) == 1 else good.model_copy(deep=True)

    monkeypatch.setattr(quiz_draft, "_generate", generate)
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "offline-fixture")
    rows, notice = quiz_draft.try_draft_quiz(comp, comp.level, fields, ["구조", "재료"])
    assert rows and len(rows) == 5 and "부분 수정" in notice
    assert len(calls) == 2 and calls[1][-1]["fixed_indices"] == [0, 2, 3, 4]


def test_source_review_updates_search_and_restriction_blocks_collection():
    save_review("sanchi-great-stupa", "산치 대탑", ["새로운 산치 별칭"], name_status="reviewed")
    assert search_individuals("새로운 산치 별칭")[0].id == "official:sanchi-great-stupa"
    assert korean_name("official:sanchi-great-stupa", "Great Stupa of Sanchi") == "산치 대탑"
    record_attempt("sanchi-great-stupa", "fresh")
    record_attempt("sanchi-great-stupa", "unavailable", "HTTP_503")
    row = next(r for r in source_overview() if r["id"] == "official:sanchi-great-stupa")
    assert row["last_success_at"] and row["error_code"] == "HTTP_503"
    save_review("sanchi-great-stupa", "산치 대탑", usage_status="restricted")
    assert search_individuals("산치") == []
    with pytest.raises(OfficialServiceError):
        fetch_individual("sanchi-great-stupa")


def add_learning(owner):
    token = session_owner.set(owner)
    try:
        comp = comparison()
        quiz = generate_quiz("seokguram", "horyuji", comp.level, comparison_id=comp.saved_id)
        grade_quiz(quiz.quiz_id, [0] * 5)
        return comp.saved_id, quiz.quiz_id
    finally:
        session_owner.reset(token)


def test_session_deletion_preserves_other_owner_and_shared_sources():
    left = add_learning("owner-a")
    right = add_learning("owner-b")
    token = session_owner.set("owner-a")
    try:
        result = delete_session_records()
        assert result["comparisons"] == result["quizzes"] == result["history"] == 1
    finally:
        session_owner.reset(token)
    with transaction() as connection:
        assert not connection.execute(
            "SELECT id FROM comparisons WHERE id=?", (left[0],)
        ).fetchone()
        assert connection.execute("SELECT id FROM comparisons WHERE id=?", (right[0],)).fetchone()
        assert connection.execute("SELECT COUNT(*) FROM heritages").fetchone()[0] >= 3
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_deletion_blocks_new_learning_jobs():
    token = session_owner.set("owner-a")

    @reused_operation("deletion-guard-test")
    def job():
        return "completed"

    try:
        with deleting_session("owner-a"):
            with pytest.raises(OperationBusyError):
                job()
        assert job() == "completed"
    finally:
        session_owner.reset(token)


def test_retention_is_opt_in_backup_first_and_restore_is_non_overwriting(tmp_path, monkeypatch):
    old = add_learning("old-owner")
    new = add_learning("new-owner")
    with transaction() as connection:
        connection.execute(
            "UPDATE resource_created SET created_at='2000-01-01' WHERE id IN (?,?)", old
        )
        connection.execute(
            "UPDATE learning_history SET created_at='2000-01-01' WHERE id IN "
            "(SELECT history_id FROM learning_reviews WHERE owner='old-owner')"
        )
    assert maintenance.maintain()["retention"]["comparisons"] == 1
    assert not get_settings().backup_dir.exists()
    maintenance.maintain(apply=True)
    assert delete_records(owner="old-owner")["comparisons"] == 1
    monkeypatch.setattr(get_settings(), "retention_enabled", True)
    report = maintenance.maintain(apply=True)
    assert report["retention"]["comparisons"] == 1
    assert delete_records(owner="new-owner")["comparisons"] == 1
    backup = get_settings().backup_dir / report["backup"]
    restored = restore_database(backup, tmp_path / "restored.db")
    assert restored.is_file()
    with pytest.raises(ValueError):
        restore_database(backup, restored)
    assert delete_records(owner="new-owner")["comparisons"] == 1 and new[0]


def test_backup_failure_prevents_retention(monkeypatch):
    add_learning("owner-a")
    monkeypatch.setattr(get_settings(), "retention_enabled", True)

    def fail(*args):
        raise ValueError("Fixture backup failure")

    monkeypatch.setattr(maintenance, "backup_database", fail)
    with pytest.raises(ValueError):
        maintenance.maintain(apply=True)
    assert delete_records(owner="owner-a")["comparisons"] == 1


def test_public_catalogue_policy_and_delete_confirmation():
    from culturebridge.main import app

    with TestClient(app) as client:
        response = client.get("/api/sources")
        assert response.status_code == 200 and len(response.json()) == 26
        assert client.get("/sources").status_code == 200
        assert client.get("/data-policy").status_code == 200
        assert (
            client.post("/api/learning-data/delete", json={"confirmation": "wrong"}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/learning-data/delete", json={"confirmation": "이 세션의 학습 기록 삭제"}
            ).status_code
            == 200
        )
        assert client.post("/api/sources/review", json={}).status_code in {404, 405}
        assert "offline-fixture" not in json.dumps(response.json())


@pytest.mark.parametrize(
    "quote,text",
    [
        ("The roof is not made of wood.", "나무 재료로 만들었다는 설명이에요."),
        ("The hall was rebuilt in 1511.", "1511년에 처음 만든 건물이라는 설명이에요."),
        ("The hall was built around 1511.", "1511년에 만든 건물이라는 설명이에요."),
        ("The stupa was built in the 3rd century BCE.", "3세기에 만든 건물이라는 설명이에요."),
    ],
)
def test_korean_draft_preserves_qualifiers(quote, text):
    lesson = explain_source(source())
    section = lesson.sections[0]
    section.category = "시대"
    section.evidence_quote = quote
    lesson.sections = [section]
    draft = korean.KoreanDraft(
        sections=[
            korean.KoreanSection(
                category="시대",
                text=text,
                evidence_quote=quote,
            )
        ]
    )
    with pytest.raises(ValueError):
        korean.validate_korean_draft(draft, lesson)


def test_backup_pruning_only_removes_its_own_old_backups():
    directory = get_settings().backup_dir
    directory.mkdir()
    untouched = directory / "manual-backup.db"
    untouched.write_bytes(b"manual fixture")
    for _ in range(3):
        latest = maintenance.maintain(apply=True)
    assert len(list(directory.glob("culturebridge-auto-*.db"))) == 2
    assert (directory / latest["backup"]).exists()
    assert untouched.read_bytes() == b"manual fixture"


def test_quiz_repair_is_bounded_and_never_retries_quota(monkeypatch):
    from google.genai.errors import ClientError

    comp = comparison()
    fields, bad = make_quiz_draft(comp)
    bad.items[1].choices[0] = "근거 없는 정답"
    calls = []

    def invalid(*args):
        calls.append(args)
        return bad

    monkeypatch.setattr(quiz_draft, "_generate", invalid)
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "offline-fixture")
    assert quiz_draft.try_draft_quiz(comp, comp.level, fields, ["구조", "재료"])[0] is None
    assert len(calls) == 2
    calls.clear()

    def quota(*args):
        calls.append(args)
        raise ClientError(429, {"error": {"message": "private fixture"}})

    monkeypatch.setattr(quiz_draft, "_generate", quota)
    assert "429" in quiz_draft.try_draft_quiz(comp, comp.level, fields, ["구조", "재료"])[1]
    assert len(calls) == 1
