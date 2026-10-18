import json
from datetime import UTC, datetime

import httpx
import pytest

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, load_quiz_items
from culturebridge.domain.models import CollectedSource, HeritageDetail, LearningGoal, LearningLevel
from culturebridge.domain.official_models import OfficialSearchResult
from culturebridge.services import agent_discovery_service as discovery
from culturebridge.services import name_registry_service as registry
from culturebridge.services import official_page_service as pages
from culturebridge.services import unesco_service as unesco
from culturebridge.services.curriculum_service import evidence_suits_goal, plan_learning
from culturebridge.services.display_service import display_name
from culturebridge.services.dynamic_heritage_service import OfficialTarget
from culturebridge.services.extraction_service import (
    DraftField,
    extract_fields,
    validate_extraction,
)
from culturebridge.services.subject_service import (
    date_event,
    focused_text,
    is_group,
    primary_type,
    subtype,
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "general.db")
    monkeypatch.setattr(get_settings(), "gemini_enabled", False)
    initialize_database()


def source(name, content, identifier="khs:11:1:11"):
    return CollectedSource(
        id=identifier,
        heritage_id=identifier,
        title=name,
        content=content,
        organization="Official test",
        source_url="https://www.khs.go.kr/",
        feed_url="https://www.khs.go.kr/",
        retrieved_at=datetime.now(UTC),
        status="fresh",
        content_kind="listed_text" if identifier.startswith("unesco:") else "individual_text",
        scope_note="Test",
    )


@pytest.mark.parametrize(
    "name,text,kept,excluded",
    [
        (
            "경복궁",
            "경복궁은 1395년에 창건된 궁궐이다. 근정전은 1867년에 재건되었다. "
            "궁궐은 1865년에 중건되었다.",
            "1395",
            "1867",
        ),
        (
            "해인사",
            "해인사는 802년에 창건된 사찰이다. 대적광전은 1818년에 재건되었다. "
            "사찰은 불교 의례를 위한 곳이다.",
            "802",
            "1818",
        ),
        (
            "천마총",
            "천마총은 신라의 고분이다. 금관총은 1921년에 발견되었다. 이 무덤은 5세기에 조성되었다.",
            "5세기",
            "1921",
        ),
        (
            "Royal Palace",
            "Royal Palace was built in 1400. The hall was rebuilt in 1800. "
            "The palace was restored in 1900.",
            "1900",
            "1800",
        ),
        (
            "Buddhist Temple",
            "The temple was founded in 700. The gate was built in 900. "
            "The temple has a wooden layout.",
            "wooden",
            "900",
        ),
    ],
)
def test_generic_subject_filter(name, text, kept, excluded):
    focused = focused_text(source(name, text))
    assert kept in focused and excluded not in focused


def test_reconstruction_is_not_silently_promoted_to_original_construction():
    s = source("경복궁", "경복궁은 1865년에 중건되었다.")
    draft = DraftField(
        heritage_id=s.id, source_id=s.id, category="시대", value="1865년", evidence_quote=s.content
    )
    assert validate_extraction(draft, [s]) is None
    draft.value = "1865년 중건"
    assert validate_extraction(draft, [s]).date_event == "재건·복원"
    assert date_event("The palace was restored in 1900.") == "재건·복원"


@pytest.mark.parametrize(
    "name,expected",
    [("오층 건물", None), ("경복궁", "Palace"), ("천마총", "Tomb"), ("해인사", "Temple")],
)
def test_primary_type_without_false_floor_count(name, expected):
    assert primary_type(name) == expected


@pytest.mark.parametrize(
    "text",
    [
        "There are 2 components.",
        "The site has two separate components.",
        "2개의 구성 유산으로 이루어진다.",
    ],
)
def test_small_serial_properties(text):
    assert is_group("Historic buildings", text)


def test_explicit_pagoda_subtypes():
    assert subtype("삼층석탑") == "stone_pagoda"
    assert subtype("Wooden Pagoda") == "wooden_pagoda"
    assert subtype("Pagoda") is None


def test_named_components_do_not_inherit_the_parent_type_or_date():
    assert primary_type("경복궁 근정전") == "Hall"
    assert primary_type("천마총 금관") is None
    s = source(
        "경복궁", "경복궁은 1395년에 창건된 궁궐이다. 경복궁의 근정전은 1867년에 중건되었다."
    )
    assert "1867" not in focused_text(s)


def test_temple_possessions_are_not_its_own_material_and_person_date_is_not_tomb_date():
    s = source(
        "합천 해인사",
        "해인사는 802년에 창건된 절로 알려져 있다. 그 밖에 원당암다층석탑 및 석등이 있다.",
    )
    fields = {f.category: f for f in extract_fields([s], [s.id])}
    assert fields["재료"].value is None and fields["구조"].value
    s = source("경주 무열왕릉", "무열왕은 661년에 죽었다. 봉분의 가장자리에 깬돌이 있다.")
    fields = {f.category: f for f in extract_fields([s], [s.id])}
    assert fields["시대"].value is None and fields["구조"].value and fields["재료"].value


def test_component_built_by_king_is_not_the_palaces_date():
    s = source(
        "경복궁",
        "1412년 태종은 경복궁의 연못을 넓히고 경회루를 만들었다. 경복궁은 1395년에 창건되었다.",
    )
    assert "1412" not in focused_text(s) and "1395" in focused_text(s)


def test_tomb_mound_resumes_target_context_after_topography():
    s = source(
        "경주 무열왕릉", "서악동 구릉의 동사면에 위치한다. 봉분의 가장자리에는 깬돌들이 있다."
    )
    fields = {f.category: f for f in extract_fields([s], [s.id])}
    assert fields["구조"].value and fields["재료"].value


def test_goal_evidence_and_custom_activities():
    assert not evidence_suits_goal({"시대", "구조", "종교적 배경"}, {"시대", "구조"}, "religion")
    assert not evidence_suits_goal({"시대", "구조"}, {"재료", "구조"}, "compare")
    assert evidence_suits_goal({"재료", "구조"}, {"재료", "구조"}, "observe")
    steps, _ = plan_learning(
        LearningLevel.BEGINNER, LearningGoal.COMPARE, "재건 연대와 공통점, 교류를 보고 싶어요"
    )
    assert any("사건별" in s for s in steps) and any("직접 증거" in s for s in steps)


def discovery_fixture(monkeypatch, rows, searched=None):
    target = OfficialTarget(provider="unesco", record_id="100")
    selected = source(
        "Stone Pagoda", "The stone pagoda was built in 700. It is a Buddhist pagoda.", target.id
    )
    records = {"100": selected, **rows}

    def fetch(t, **kw):
        s = records[t.record_id]
        return HeritageDetail(
            id=t.id,
            name=s.title,
            country="India" if t.record_id == "100" else "Japan",
            location="Test",
            period="근거 부족",
            summary="Test",
            structure="근거 부족",
            material="근거 부족",
            religious_context="근거 부족",
            source_ids=[s.id],
        ), s

    def search(q, **kw):
        if searched is not None:
            searched.append((q, kw))
        ids = list(rows)
        return unesco.UnescoResult(
            records=[
                unesco.UnescoRecord(
                    id=i,
                    name=rows[i].title,
                    countries="Japan",
                    inscription_year="2000",
                    source_url=f"https://whc.unesco.org/en/list/{i}/",
                    description="A Buddhist stone pagoda.",
                )
                for i in ids
            ],
            total=len(ids),
            retrieved_at=datetime.now(UTC),
            cached=True,
            stale=False,
        )

    monkeypatch.setattr(discovery, "fetch_target", fetch)
    monkeypatch.setattr(discovery, "search_unesco", search)
    monkeypatch.setattr(
        discovery,
        "search_official_heritages",
        lambda *a, **kw: OfficialSearchResult(
            items=[], total=0, page=kw.get("page", 1), page_size=10
        ),
    )
    return target, search


def test_rejected_top_three_do_not_hide_the_fourth_candidate(isolated, monkeypatch):
    rows = {
        str(i): source("Unclear Stone Pagoda", "A pagoda.", f"unesco:{i}") for i in range(201, 204)
    }
    rows["204"] = source(
        "Valid Stone Pagoda", "A Buddhist stone pagoda was built in 800.", "unesco:204"
    )
    target, _ = discovery_fixture(monkeypatch, rows)
    _, candidates, _, _ = discovery.discover_candidates(target, "compare")
    assert [c.heritage.id for c in candidates] == ["unesco:204"]


def test_changed_query_retry_finds_another_candidate_once(isolated, monkeypatch):
    rows = {
        "201": source("Unclear Stone Pagoda", "A pagoda.", "unesco:201"),
        "202": source(
            "Another Stone Pagoda", "A Buddhist stone pagoda was built in 800.", "unesco:202"
        ),
    }
    target, search = discovery_fixture(monkeypatch, rows)
    calls = []

    def conditional(q, **kw):
        calls.append(q)
        result = search(q, **kw)
        result.records = [r for r in result.records if r.id == ("202" if q == "stupa" else "201")]
        return result

    monkeypatch.setattr(discovery, "search_unesco", conditional)
    _, candidates, trace, _ = discovery.discover_candidates(target, "compare")
    assert candidates[0].heritage.id == "unesco:202" and len(calls) <= 6
    assert sum("검색어 변경" in t for t in trace) == 1


def test_religion_goal_rejects_candidate_with_only_age_and_structure(isolated, monkeypatch):
    target, _ = discovery_fixture(
        monkeypatch,
        {"201": source("Stone Pagoda", "The stone pagoda was built in 800.", "unesco:201")},
    )
    _, candidates, trace, _ = discovery.discover_candidates(target, "religion")
    assert not candidates and any("학습 목표" in t for t in trace)


def test_supplement_scope_parser_and_blocked_access_cache(isolated, monkeypatch):
    html = (
        "<h1>Test Temple</h1><h2>Brief synthesis</h2><p>The Buddhist temple was built in 700. "
        "The temple has a wooden layout with a main sanctuary and a courtyard.</p>"
        "<h2>Integrity</h2><p>Not evidence</p>"
    )
    assert "Not evidence" not in pages.parse_synthesis(html, "Test Temple")
    calls = []

    def blocked(request):
        calls.append(str(request.url))
        return httpx.Response(403, text="Forbidden")

    original = httpx.Client
    monkeypatch.setattr(
        pages.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(blocked), **kw)
    )
    s = source("Test Temple", "A temple.", "unesco:999")
    assert pages.collect_supplement(s).status == "unavailable"
    assert pages.collect_supplement(s).status == "unavailable"
    assert len(calls) == 1 and calls[0] == "https://whc.unesco.org/en/list/999/"


def test_korean_names_are_id_bound_and_status_visible(isolated):
    registry.register_name(
        "unesco:999", "Example Temple", "예시 사원", ["예시절"], status="ai_candidate"
    )
    assert "AI 번역 후보" in display_name("unesco:999", "Example Temple")
    assert "확인 필요" in display_name("unesco:999", "Different official name")
    registry.register_name(
        "unesco:999", "Example Temple", "예시 사원", ["예시절"], status="reviewed"
    )
    assert "AI 번역 후보" not in display_name("unesco:999", "Example Temple")


def store_feed():
    payload = [
        {
            "id_no": 999,
            "name_en": "Example Temple",
            "states_names": ["Japan"],
            "date_inscribed": 2000,
            "short_description_en": "A Buddhist temple.",
        }
    ]
    unesco._store_feed(
        json.dumps(payload).encode(), "json", unesco.DATAHUB_URL, unesco.DATAHUB_INFO_URL
    )


def test_cached_korean_alias_search_and_autocomplete_never_call_model(isolated, monkeypatch):
    store_feed()
    registry.register_name(
        "unesco:999", "Example Temple", "예시 사원", ["예시절"], status="reviewed"
    )
    monkeypatch.setattr(
        unesco,
        "korean_search_terms",
        lambda *a: pytest.fail("Known local alias must not call model"),
    )
    assert unesco.search_unesco("예시절").records[0].name_review_status == "reviewed"
    assert unesco.get_unesco_suggestions("예시")[0].record_id == "999"


def test_unknown_korean_query_only_returns_existing_official_records(isolated, monkeypatch):
    store_feed()
    monkeypatch.setattr(
        unesco, "korean_search_terms", lambda *a: ["Example Temple", "Made Up Palace"]
    )
    result = unesco.search_unesco("미등록 한국어 이름")
    assert [r.id for r in result.records] == ["999"] and "AI" in result.notice


def test_failed_name_translation_is_cached_without_secret(isolated, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    calls = []

    def fail(**kw):
        calls.append(True)
        raise RuntimeError("private-key-error")

    monkeypatch.setattr(registry.genai, "Client", fail)
    registry.ensure_name("unesco:999", "Example Temple")
    registry.ensure_name("unesco:999", "Example Temple")
    assert len(calls) == 1
    assert "private-key-error" not in json.dumps(registry.names())


def test_actual_content_questions_and_wrong_answer_review(isolated):
    from culturebridge.services.comparison_service import create_saved_comparison
    from culturebridge.services.quiz_service import generate_quiz, grade_quiz

    sources = [
        source(
            "석굴암", "Built in 751. An artificial granite grotto. It is Buddhist.", "seokguram"
        ),
        source("호류지", "Built in 607. A wooden temple layout. It is Buddhist.", "horyuji"),
    ]
    fields = extract_fields(sources, ["seokguram", "horyuji"])
    comparison = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=fields,
    )
    quiz = generate_quiz(
        "seokguram", "horyuji", LearningLevel.BEGINNER, comparison_id=comparison.saved_id
    )
    rows = load_quiz_items(quiz.quiz_id)
    assert sum("복습 항목" in r["explanation"] for r in rows) == 5
    assert "문화유산과 설명" in rows[-1]["question"]
    assert any("석굴암" in r["question"] for r in rows)
    assert any("호류지" in r["question"] for r in rows)
    result = grade_quiz(quiz.quiz_id, [(r["correct_index"] + 1) % 4 for r in rows])
    assert len(result.review_steps) == 5 and result.score == 0


def test_negation_does_not_create_shared_material(isolated):
    from culturebridge.services.comparison_service import create_saved_comparison

    sources = [
        source("석굴암", "This grotto is not made of wood.", "seokguram"),
        source("호류지", "A wooden temple layout.", "horyuji"),
    ]
    comparison = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=extract_fields(sources, ["seokguram", "horyuji"]),
    )
    assert not any("목재" in c.statement for c in comparison.common_evidence)


def test_context_review_uses_grounded_pairs_and_keeps_review_status(isolated, monkeypatch):
    from culturebridge.domain.models import VerificationStatus
    from culturebridge.services import common_context_service as context
    from culturebridge.services.comparison_service import create_saved_comparison

    sources = [
        source("석굴암", "A Buddhist granite grotto.", "seokguram"),
        source("호류지", "A Buddhist wooden temple.", "horyuji"),
    ]
    comparison = create_saved_comparison(
        "seokguram",
        "horyuji",
        LearningLevel.BEGINNER,
        collected_sources=sources,
        extracted_fields=extract_fields(sources, ["seokguram", "horyuji"]),
    )
    pairs = comparison.common_evidence
    monkeypatch.setattr(get_settings(), "gemini_enabled", True)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(
        context,
        "_review",
        lambda pairs: context.ContextReview(
            judgments=[
                context.ContextJudgment(
                    index=i,
                    relation="shared_candidate",
                    reason="각 유산의 불교 맥락을 비교하되 직접 영향은 확인하지 않음",
                )
                for i in range(len(pairs))
            ]
        ),
    )
    reviewed = context.review_common_context(pairs)
    assert reviewed and all(
        p.method == "gemini" and p.verification_status == VerificationStatus.NEEDS_REVIEW
        for p in reviewed
    )
    monkeypatch.setattr(
        context,
        "_review",
        lambda pairs: context.ContextReview(
            judgments=[
                context.ContextJudgment(
                    index=i, relation="different_meaning", reason="같은 단어지만 다른 대상의 설명"
                )
                for i in range(len(pairs))
            ]
        ),
    )
    assert not context.review_common_context(pairs)


def test_name_import_validates_entire_input_before_changing_registry(isolated, monkeypatch):
    from culturebridge.import_names import import_names

    monkeypatch.setattr(
        "culturebridge.import_names.search_unesco",
        lambda *a: unesco.UnescoResult(
            records=[
                unesco.UnescoRecord(
                    id="999",
                    name="Example Temple",
                    countries="Japan",
                    inscription_year="2000",
                    source_url="https://whc.unesco.org/en/list/999/",
                )
            ],
            total=1,
            retrieved_at=datetime.now(UTC),
            cached=True,
            stale=False,
        ),
    )
    row = {"id": "999", "official_name": "Example Temple", "korean_name": "예시 사원"}
    with pytest.raises(ValueError):
        import_names([row, {**row, "id": "bad-id"}])
    assert "unesco:999" not in registry.names()
    assert import_names([row]) == 1 and registry.names()["unesco:999"]["status"] == "reviewed"
