import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.models import LearningLevel
from culturebridge.main import app
from culturebridge.services import individual_source_service as individual
from culturebridge.services import question_service
from culturebridge.services.operation_service import reused_operation


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "hardening.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    monkeypatch.setattr(get_settings(), "storage_secret", "test-session-secret-32-characters-long")
    initialize_database()


def test_basic_comparison_preserves_goal_and_refresh_reuses_record(isolated):
    with TestClient(app) as client:
        url = "/compare/seokguram/horyuji?goal=religion&goal_text=불교&amount=deep&level=advanced"
        assert client.get(url).status_code == client.get(url).status_code == 200
    with transaction() as conn:
        rows = conn.execute("SELECT content_json FROM comparisons").fetchall()
    assert len(rows) == 1
    saved = json.loads(rows[0]["content_json"])["comparison"]
    assert (saved["goal"], saved["goal_text"], saved["amount"]) == ("religion", "불교", "deep")
    assert saved["curriculum"]


def test_public_sessions_cannot_read_or_grade_other_sessions(isolated, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_mode", True)
    with TestClient(app) as first, TestClient(app) as second:
        saved = first.post(
            "/api/comparisons", json={"left_id": "seokguram", "right_id": "horyuji"}
        ).json()
        quiz = first.post(
            "/api/quizzes", json={"left_id": "seokguram", "right_id": "horyuji"}
        ).json()
        assert len(first.get("/api/comparisons").json()) == 1
        assert second.get("/api/comparisons").json() == []
        assert second.get("/api/comparisons/" + saved["saved_id"]).status_code == 404
        assert (
            second.post(
                "/api/quiz-attempts", json={"quiz_id": quiz["quiz_id"], "answers": [0] * 5}
            ).status_code
            == 404
        )
        assert (
            first.post(
                "/api/quiz-attempts", json={"quiz_id": quiz["quiz_id"], "answers": [0] * 5}
            ).status_code
            == 200
        )
        assert len(first.get("/api/learning-history").json()) == 1
        assert second.get("/api/learning-history").json() == []


def test_repeated_quiz_and_grade_reuse_and_keep_review(isolated):
    with TestClient(app) as client:
        payload = {"left_id": "seokguram", "right_id": "horyuji"}
        first = client.post("/api/quizzes", json=payload).json()
        assert client.post("/api/quizzes", json=payload).json()["quiz_id"] == first["quiz_id"]
        attempt = {"quiz_id": first["quiz_id"], "answers": [0] * 5}
        assert client.post("/api/quiz-attempts", json=attempt).status_code == 200
        assert client.post("/api/quiz-attempts", json=attempt).status_code == 200
        reviews = client.get("/api/learning-history").json()
        assert len(reviews) == 1 and reviews[0]["result"]["review_steps"]
        assert client.get("/learning-history").status_code == 200


def test_identical_concurrent_operation_runs_once(isolated):
    calls = []

    @reused_operation("concurrency-test")
    def work(value):
        calls.append(value)
        return {"saved_id": "ok", "value": value}

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(work, [1, 1]))
    assert len(calls) == 1 and results[0] == results[1]


def test_individual_adapter_uses_subject_paragraph_only(isolated, monkeypatch):
    html = (
        "<p>The temple was built in 600.</p>"
        "<p>The Five-storied Pagoda is a Buddhist wooden pagoda.</p>"
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        individual.httpx,
        "Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html))
        ),
    )
    source = individual.fetch_individual("horyuji-pagoda")
    assert "temple was built" not in source.content
    assert source.content_kind == "individual_text" and source.status == "fresh"


def test_question_rejects_invented_quote_and_accepts_bounded_context(isolated, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only-key")

    class Model:
        def __init__(self, **kw):
            self.models = self

        def close(self):
            pass

        def generate_content(self, **kw):
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "citations": [
                            {
                                "sentence": "Unsupported",
                                "source_id": "src-seokguram-unesco",
                                "quote": "Invented quote never in the source",
                            }
                        ]
                    }
                )
            )

    monkeypatch.setattr(question_service.genai, "Client", Model)
    answer = question_service.answer_question(
        "seokguram", "horyuji", "재료는?", LearningLevel.BEGINNER, use_ai=True
    )
    assert not answer.used_ai and not answer.citations


def test_backup_is_valid_and_does_not_overwrite(isolated, tmp_path):
    from culturebridge.backup_db import backup_database

    target = tmp_path / "backup.db"
    assert backup_database(target) == target
    with pytest.raises(ValueError):
        backup_database(target)


def test_public_request_limit_returns_retry_after(isolated, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_mode", True)
    monkeypatch.setattr(get_settings(), "requests_per_minute", 1)
    with TestClient(app) as client:
        assert client.post("/api/comparisons", json={}).status_code == 422
        blocked = client.post("/api/comparisons", json={})
        assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"


def test_same_subject_alias_is_not_a_comparison():
    from culturebridge.domain.models import ComparisonRequest
    from culturebridge.services.heritage_identity_service import identity_info

    with pytest.raises(ValueError):
        ComparisonRequest(left_id="seokguram", right_id="khs:11:0000240000000:37")
    assert identity_info("official:horyuji-pagoda")["parent_id"] == "unesco:660"
    assert identity_info("horyuji")["canonical_id"] != "official:horyuji-pagoda"


def test_individual_candidate_connects_comparison_and_quiz(isolated, monkeypatch):
    from datetime import UTC, datetime

    from culturebridge.agents.autonomous import AutonomousRequest, run_autonomous
    from culturebridge.domain.models import CollectedSource
    from culturebridge.domain.official_models import OfficialDocument
    from culturebridge.services import agent_discovery_service as discovery
    from culturebridge.services import dynamic_heritage_service as dynamic
    from culturebridge.services.dynamic_heritage_service import OfficialTarget
    from culturebridge.services.unesco_service import UnescoResult

    monkeypatch.setattr(get_settings(), "individual_sources_enabled", True)
    monkeypatch.setattr(
        dynamic,
        "get_official_document",
        lambda *a, **kw: OfficialDocument(
            kind_code="11",
            asset_number="20",
            region_code="37",
            name="다보탑",
            content="다보탑은 751년에 건립한 석탑이다. 다보탑은 불교 경전 법화경을 표현했다.",
            source_url="https://www.khs.go.kr/",
            retrieved_at=datetime.now(UTC),
        ),
    )
    monkeypatch.setattr(
        discovery,
        "search_unesco",
        lambda *a, **kw: UnescoResult(
            records=[],
            total=0,
            retrieved_at=datetime.now(UTC),
            cached=True,
            stale=False,
        ),
    )
    monkeypatch.setattr(
        individual,
        "fetch_individual",
        lambda identity, refresh=False: CollectedSource(
            id="official:" + identity,
            heritage_id="official:" + identity,
            title=individual.INDIVIDUALS[identity]["name"],
            organization="Official temple",
            source_url=individual.INDIVIDUALS[identity]["url"],
            feed_url=individual.INDIVIDUALS[identity]["url"],
            retrieved_at=datetime.now(UTC),
            content="The Five-storied Pagoda is a Buddhist wooden pagoda. It was built in 700.",
            status="fresh",
            content_kind="individual_text",
            scope_note="Individual pagoda test fixture",
        ),
    )
    result = run_autonomous(
        AutonomousRequest(
            target=OfficialTarget(provider="khs", kind="11", number="20", region="37")
        )
    )
    assert result["candidates"][0]["heritage"]["id"] == "official:horyuji-pagoda"
    assert result["comparison"] and result["quiz"]
    assert len(result["quiz"]["items"]) == 5
    assert result["comparison"]["comparison_scope"] == "overseas"


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("reset", ["manual", "timeout"])
def test_kiosk_reset_preserves_personal_session_and_isolates_records(
    isolated, monkeypatch, public, reset
):
    monkeypatch.setattr(get_settings(), "public_mode", public)
    with TestClient(app) as client:
        saved = client.post(
            "/api/comparisons", json={"left_id": "seokguram", "right_id": "horyuji"}
        ).json()
        personal_cookie = client.cookies.get("cb_session")
        assert client.get("/kiosk").status_code == 200
        kiosk_cookie = client.cookies.get("cb_kiosk_session")
        assert kiosk_cookie and kiosk_cookie != personal_cookie
        payload = {"left_id": "seokguram", "right_id": "horyuji"}
        kiosk_saved = client.post("/api/comparisons?mode=kiosk", json=payload).json()
        kiosk_id = kiosk_saved["saved_id"]
        assert kiosk_id != saved["saved_id"]
        kiosk_quiz = client.post("/api/quizzes?mode=kiosk", json=payload).json()
        assert (
            client.post(
                "/api/quiz-attempts?mode=kiosk",
                json={"quiz_id": kiosk_quiz["quiz_id"], "answers": [0] * 5},
            ).status_code
            == 200
        )
        assert len(client.get("/api/learning-history?mode=kiosk").json()) == 1
        assert client.get("/api/learning-history").json() == []
        assert client.get(f"/api/comparisons/{kiosk_id}?mode=kiosk").status_code == 200
        assert client.get(f"/api/comparisons/{kiosk_id}").status_code == 404
        assert [r["id"] for r in client.get("/api/comparisons").json()] == [saved["saved_id"]]
        assert client.get(f"/kiosk?reset={reset}").status_code == 200
        assert client.cookies.get("cb_session") == personal_cookie
        assert client.cookies.get("cb_kiosk_session") != kiosk_cookie
        assert client.get("/api/comparisons/" + saved["saved_id"]).status_code == 200
        assert client.get(f"/api/comparisons/{kiosk_id}?mode=kiosk").status_code == 404
        assert client.get("/api/comparisons?mode=kiosk").json() == []
        assert client.get("/api/learning-history?mode=kiosk").json() == []
        assert (
            client.post(
                "/api/quiz-attempts?mode=kiosk",
                json={"quiz_id": kiosk_quiz["quiz_id"], "answers": [0] * 5},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/quiz-attempts", json={"quiz_id": kiosk_quiz["quiz_id"], "answers": [0] * 5}
            ).status_code
            == 404
        )
        with transaction() as conn:
            assert conn.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0] == 2


def test_ui_workers_keep_anonymous_owner(monkeypatch):
    import asyncio

    from culturebridge.services.operation_service import owner_key, session_owner
    from culturebridge.ui import pages

    async def executor(callback, *args):
        return await asyncio.to_thread(callback, *args)

    monkeypatch.setattr(pages.run, "io_bound", executor)
    token = session_owner.set("worker-session-test")
    try:
        assert asyncio.run(pages._io_bound(owner_key)) == "worker-session-test"
    finally:
        session_owner.reset(token)


def test_page_title_and_symbol_are_not_structure_evidence():
    from datetime import UTC, datetime

    from culturebridge.domain.models import CollectedSource
    from culturebridge.services.extraction_service import _local_extraction

    source = CollectedSource(
        id="official:dayanta",
        heritage_id="official:dayanta",
        title="Giant Wild Goose Pagoda",
        organization="City government",
        source_url=individual.INDIVIDUALS["dayanta"]["url"],
        feed_url=individual.INDIVIDUALS["dayanta"]["url"],
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        content="The Giant Wild Goose Pagoda (The Great Temple of Benevolence and Kindness)\n"
        "The Giant Wild Goose Pagoda is esteemed as the symbol of the city. "
        "It was situated inside the Buddhist temple.",
        scope_note="Individual subject",
    )
    fields = {field.category: field for field in _local_extraction([source])}
    assert "inside" in fields["구조"].evidence_quote
    assert "symbol" not in fields["구조"].evidence_quote


@pytest.mark.parametrize(
    "axes,expected", [(["종교적 배경"], {"종교적 배경"}), (["invented-axis"], set())]
)
def test_free_goal_semantics_are_bounded_to_supported_axes(isolated, monkeypatch, axes, expected):
    from culturebridge.services import goal_interpretation_service as intent
    from culturebridge.services.agent_discovery_service import required_categories

    intent._interpret.cache_clear()
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-only-key")

    class Model:
        def __init__(self, **kw):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kw):
            return SimpleNamespace(text=json.dumps({"categories": axes}, ensure_ascii=False))

    monkeypatch.setattr(intent.genai, "Client", Model)
    assert required_categories("compare 옛사람들이 이 장소를 소중히 여긴 이유") == expected
    intent._interpret.cache_clear()


def test_negated_material_is_not_promoted_to_a_positive_fact():
    from datetime import UTC, datetime

    from culturebridge.domain.models import CollectedSource
    from culturebridge.services.extraction_service import DraftField, validate_extraction

    source = CollectedSource(
        id="official:test",
        heritage_id="official:test",
        title="Wooden Pagoda",
        organization="Official site",
        source_url="https://www.horyuji.or.jp/",
        feed_url="https://www.horyuji.or.jp/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        content="The wooden pagoda is not made of granite.",
        scope_note="Subject",
    )
    assert (
        validate_extraction(
            DraftField(
                heritage_id=source.heritage_id,
                category="재료",
                value="granite",
                source_id=source.id,
                evidence_quote=source.content,
            ),
            [source],
        )
        is None
    )
