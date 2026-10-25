import json
import sys
from datetime import UTC, datetime

import pytest

from culturebridge.config import get_settings
from culturebridge.data.assessment_benchmark import CASES
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.models import CollectedSource
from culturebridge.domain.official_models import OfficialDocument
from scripts import check_assessment_quality as quality
from scripts import review_heritage_content as review


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "outputs"
    folder.mkdir()
    path = folder / "isolated.db"
    monkeypatch.setattr(get_settings(), "db_path", path)
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "synthetic-test-only")
    initialize_database()
    source = CollectedSource(
        id="official:edinburgh-great-hall",
        heritage_id="official:edinburgh-great-hall",
        title="Synthetic Hall",
        organization="Synthetic fixture",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        scope_note="Test-only fixture",
        content="Its wooden roof is one of the most superb in Britain.",
    )
    with transaction() as connection:
        connection.execute(
            "INSERT INTO agent_source_cache VALUES(?,?,?)",
            (source.id, source.model_dump_json(), source.retrieved_at.isoformat()),
        )
    monkeypatch.setattr(quality, "CASES", CASES[:1])
    return path


def test_offline_assessment_review_makes_no_model_calls(audit_db, monkeypatch):
    report_path = audit_db.parent / "offline.json"
    monkeypatch.setattr(sys, "argv", ["check", "--db", str(audit_db), "--output", str(report_path)])
    monkeypatch.setattr(
        quality, "assessment_decision", lambda _: pytest.fail("Unexpected model call")
    )
    quality.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["calls"] == 0 and report["gold_agreement_rate"] is None
    assert all(row["source_matches_case"] for row in report["rows"])
    assert report["human_participants"] == 0 and not report["educational_effect_established"]


@pytest.mark.parametrize("permitted,expected_calls", [(True, 1), (False, 0)])
def test_live_assessment_stops_at_quota_or_source_policy(
    audit_db, monkeypatch, permitted, expected_calls
):
    report_path = audit_db.parent / "live.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check",
            "--db",
            str(audit_db),
            "--output",
            str(report_path),
            "--live",
            "--max-calls",
            "2",
        ],
    )
    monkeypatch.setattr(quality, "url_allowed", lambda _: permitted)
    calls = []

    class QuotaError(Exception):
        code = 429

    def unavailable(_):
        calls.append(1)
        raise QuotaError()

    monkeypatch.setattr(quality, "assessment_decision", unavailable)
    quality.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["calls"] == len(calls) == expected_calls
    assert report["completed"] == 0 and report["gold_agreement_rate"] is None


def test_missing_source_does_not_crash_or_count_as_preserved(audit_db, monkeypatch):
    report_path = audit_db.parent / "missing.json"
    monkeypatch.setattr(
        sys, "argv", ["review", "--db", str(audit_db), "--output", str(report_path)]
    )
    monkeypatch.setattr(
        review, "material_review", lambda: [{"id": "missing", "source_url": "https://example.org/"}]
    )
    review.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["reading_count"] == 0 and not report["all_originals_preserved"]
    assert report["source_unavailable_count"] == 1


def test_national_source_snapshot_and_variant_are_supported(audit_db, monkeypatch):
    case = next(case for case in CASES if case["id"] == "khs-pagoda-structure")
    monkeypatch.setattr(quality, "CASES", [case])
    document = OfficialDocument(
        kind_code="11",
        asset_number="0000200000000",
        region_code="37",
        name="다보탑",
        content="십(十)자 모양 평면의 기단에는 사방에 돌계단을 마련하고, "
        "8각형의 탑신과 그 주위로는 네모난 난간을 돌렸다.",
        source_url="https://www.khs.go.kr/cha/SearchKindOpenapiDt.do",
        retrieved_at=datetime.now(UTC),
    )
    with transaction() as connection:
        connection.execute(
            "INSERT INTO official_documents VALUES(?,?,?,?)",
            (case["source_id"], document.model_dump_json(), "", document.retrieved_at.isoformat()),
        )
    report_path = audit_db.parent / "national.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["check", "--db", str(audit_db), "--output", str(report_path), "--variant", "2"],
    )
    monkeypatch.setattr(
        quality, "assessment_decision", lambda _: pytest.fail("Unexpected live call")
    )
    quality.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["calls"] == 0 and report["ready_cases"] == 1
    assert report["source_policy_blocked_cases"] == 0
    assert len(report["rows"]) == 1
    assert report["rows"][0]["variant"] == 2
    assert report["rows"][0]["source_id"] == case["source_id"]
    assert report["rows"][0]["source_matches_case"]


def test_offline_readiness_distinguishes_permission_from_text_match(audit_db, monkeypatch):
    report_path = audit_db.parent / "permission.json"
    monkeypatch.setattr(quality, "url_allowed", lambda _: False)
    monkeypatch.setattr(sys, "argv", ["check", "--db", str(audit_db), "--output", str(report_path)])
    quality.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ready_cases"] == 0 and report["source_policy_blocked_cases"] == 2
    assert all(
        row["source_matches_case"] and not row["source_ai_allowed"] for row in report["rows"]
    )
