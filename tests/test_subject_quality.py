from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.domain.models import CollectedSource
from culturebridge.services.display_service import (
    display_country,
    display_name,
    learning_title,
    readable_reason,
)
from culturebridge.services.extraction_service import (
    DraftField,
    extract_fields,
    validate_extraction,
)
from culturebridge.services.subject_service import focused_text, is_group, primary_type


@pytest.fixture
def tower(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "quality.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()
    return CollectedSource(
        id="khs:11:20:37",
        heritage_id="khs:11:20:37",
        title="경주 불국사 다보탑",
        organization="국가유산청",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="individual_text",
        scope_note="Test",
        content="불국사는 751년에 창건된 사찰이다. 석굴암은 석굴이다.\n"
        "다보탑과 석가탑은 대표적인 석탑이다.\n"
        "다보탑은 팔각형 기단과 난간이 있다.\n"
        "탑이 건립된 시기는 751년으로 추측된다.\n"
        "탑은 부처의 설법과 법화경의 내용을 표현했다.",
    )


def test_tower_subject_does_not_inherit_parent_temple_and_neighbor_cave(tower):
    text = focused_text(tower)
    assert "사찰" not in text and "석굴" not in text
    assert primary_type(tower.title, text) == "Pagoda"
    fields = {f.category: f for f in extract_fields([tower], [tower.id])}
    assert "추측" in fields["시대"].value
    assert fields["재료"].value == "석재"
    assert "법화경" in fields["종교적 배경"].evidence_quote


def test_background_date_and_unqualified_estimate_are_rejected(tower):
    draft = DraftField(
        heritage_id=tower.id,
        source_id=tower.id,
        category="시대",
        value="751년",
        evidence_quote="불국사는 751년에 창건된 사찰이다.",
    )
    assert validate_extraction(draft, [tower]) is None
    draft.evidence_quote = "탑이 건립된 시기는 751년으로 추측된다."
    assert validate_extraction(draft, [tower]) is None
    draft.value = "751년으로 추측"
    assert validate_extraction(draft, [tower]) is not None


def test_stone_is_not_promoted_to_granite_and_style_is_not_material(tower):
    draft = DraftField(
        heritage_id=tower.id,
        source_id=tower.id,
        category="재료",
        value="화강암",
        evidence_quote="다보탑과 석가탑은 대표적인 석탑이다.",
    )
    assert validate_extraction(draft, [tower]) is None
    tower.content += "\n다보탑은 목조건축의 복잡한 구조를 표현했다."
    draft.value = "목재"
    draft.evidence_quote = "다보탑은 목조건축의 복잡한 구조를 표현했다."
    assert validate_extraction(draft, [tower]) is None


@pytest.mark.parametrize(
    "name",
    [
        "Silk Roads: the Routes Network of Chang'an-Tianshan Corridor",
        "Gyeongju Historic Areas",
        "Complex of Monuments and Landscapes",
    ],
)
def test_large_ensembles_are_not_individual_towers(name):
    assert is_group(name)
    assert not is_group("서울 원각사지 십층석탑")


def test_korean_bilingual_names_do_not_change_official_names():
    original = "Rangiri Dambulla Cave Temple"
    assert display_name("unesco:561", original) == "랑기리 담불라 석굴 사원(" + original + ")"
    assert original == "Rangiri Dambulla Cave Temple"
    assert "확인 필요" in display_name("unesco:99999", "Unmapped site")
    assert display_country("China; Kyrgyzstan; Kazakhstan") == "중국 · 키르기스스탄 · 카자흐스탄"
    assert learning_title("다보탑").startswith("다보탑과")
    reason = readable_reason(["같은 핵심 유형: Pagoda", "Buddhist, Grotto, Temple"])
    assert "Buddhist" not in reason and "불교" in reason and "판단하지" in reason


def test_learning_page_uses_bilingual_cards_and_simple_labels(tower, monkeypatch):
    from nicegui import Client

    from culturebridge.main import app
    from culturebridge.ui import pages

    async def connected(*args, **kwargs):
        pass

    monkeypatch.setattr(Client, "connected", connected)
    result = {
        "target": {"id": tower.id, "name": tower.title},
        "used_ai_planner": False,
        "verification_note": "길고 기술적인 원문 검증 설명",
        "execution_trace": [],
        "candidates": [
            {
                "heritage": {
                    "id": "unesco:561",
                    "name": "Rangiri Dambulla Cave Temple",
                    "country": "Sri Lanka",
                },
                "criteria": ["Buddhist, Grotto, Temple"],
                "reason": "technical",
            }
        ],
        "comparison": None,
        "quiz": None,
    }
    monkeypatch.setattr(pages, "run_autonomous", lambda *args: result)
    with TestClient(app) as client:
        response = client.get("/discover/khs/11:20:37")
    assert response.status_code == 200
    assert "랑기리 담불라 석굴 사원" in response.text
    assert "이 유산과 비교하기" in response.text and "자료를 찾고 비교한 과정" in response.text
    assert "원문 키워드 기반 대체 검색 계획" not in response.text


def test_discovery_excludes_serial_heritage_and_candidate_without_direct_evidence(
    tower, monkeypatch
):
    from culturebridge.domain.models import HeritageDetail
    from culturebridge.domain.official_models import OfficialSearchResult
    from culturebridge.services import agent_discovery_service as discovery
    from culturebridge.services.dynamic_heritage_service import OfficialTarget
    from culturebridge.services.unesco_service import UnescoRecord, UnescoResult

    target = OfficialTarget(provider="khs", kind="11", number="20", region="37")
    records = [
        UnescoRecord(
            id=id,
            name=name,
            countries="China",
            inscription_year="2000",
            source_url=f"https://whc.unesco.org/en/list/{id}/",
            description=description,
        )
        for id, name, description in [
            ("1442", "Silk Roads: Routes Network", "Buddhist pagodas, temples and caves."),
            (
                "200",
                "Stone Pagoda",
                "Built in the 8th century. A stone pagoda with a Buddhist statue.",
            ),
            ("201", "Unclear Pagoda", "A Buddhist shrine."),
        ]
    ]
    fetched = []

    def fetch(t):
        fetched.append(t.id)
        source = (
            tower
            if t.provider == "khs"
            else tower.model_copy(
                update={
                    "id": t.id,
                    "heritage_id": t.id,
                    "title": next(r.name for r in records if r.id == t.record_id),
                    "content": next(r.description for r in records if r.id == t.record_id),
                    "content_kind": "listed_text",
                }
            )
        )
        detail = HeritageDetail(
            id=t.id,
            name=source.title,
            country="대한민국" if t.provider == "khs" else "China",
            period="근거 부족",
            location="Test",
            summary="Test",
            material="근거 부족",
            structure="근거 부족",
            religious_context="근거 부족",
            source_ids=[t.id],
        )
        return detail, source

    monkeypatch.setattr(discovery, "fetch_target", fetch)
    monkeypatch.setattr(
        discovery,
        "search_unesco",
        lambda *a, **kw: UnescoResult(
            records=records, total=3, retrieved_at=datetime.now(UTC), cached=True, stale=False
        ),
    )
    monkeypatch.setattr(
        discovery,
        "search_official_heritages",
        lambda *a, **kw: OfficialSearchResult(items=[], total=0, page=1, page_size=5),
    )
    _, candidates, trace, _ = discovery.discover_candidates(target)
    assert [c.heritage.id for c in candidates] == ["unesco:200"]
    assert "unesco:1442" not in fetched
    assert any("근거 부족" in step for step in trace)
