from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.database import initialize_database, transaction
from culturebridge.domain.models import LearningLevel
from culturebridge.main import app
from culturebridge.services import official_service as service
from culturebridge.services import question_service

LIST_XML = """<result><totalCnt>1</totalCnt><item>
<ccbaKdcd>11</ccbaKdcd><ccbaAsno>0000240000000</ccbaAsno><ccbaCtcd>37</ccbaCtcd>
<ccbaMnm1>경주 석굴암 석굴</ccbaMnm1><ccmaName>국보</ccmaName><ccbaCncl>N</ccbaCncl>
</item></result>"""
DETAIL_XML = """<result>
<ccbaKdcd>11</ccbaKdcd><ccbaAsno>0000240000000</ccbaAsno><ccbaCtcd>37</ccbaCtcd>
<item><ccbaMnm1>경주 석굴암 석굴</ccbaMnm1><ccceName>통일신라시대</ccceName>
<content><![CDATA[<p>공식 자료 테스트 설명</p><br>화강암 시험 본문]]></content></item></result>"""


@pytest.fixture(autouse=True)
def isolated_official_database(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "official.db")
    initialize_database()


@pytest.fixture
def upstream(monkeypatch):
    original_client = httpx.Client

    def install(handler):
        monkeypatch.setattr(
            service.httpx,
            "Client",
            lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return install


def test_search_sends_expected_query_and_keeps_leading_zeroes(upstream):
    def handler(request):
        assert request.url.params["ccbaMnm1"] == "석굴암"
        assert request.url.params["pageIndex"] == "2"
        assert request.url.params["pageUnit"] == "5"
        assert "serviceKey" not in request.url.params
        return httpx.Response(200, text=LIST_XML)

    upstream(handler)
    result = service.search_official_heritages(" 석굴암 ", page=2, page_size=5)
    assert result.total == 1
    assert result.items[0].asset_number == "0000240000000"


def test_detail_stores_raw_xml_and_reuses_cache(upstream):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=DETAIL_XML)

    upstream(handler)
    first = service.get_official_document(*service.SEOKGURAM_CODES)
    second = service.get_official_document(*service.SEOKGURAM_CODES)
    assert not first.cached and second.cached
    assert first.retrieved_at == second.retrieved_at
    assert len(calls) == 1
    assert "<p>" not in first.content and "공식 자료 테스트 설명" in first.content
    with transaction() as connection:
        row = connection.execute("SELECT raw_xml FROM official_documents").fetchone()
    assert row["raw_xml"] == DETAIL_XML


def test_expired_cache_is_labelled_stale_on_upstream_failure(upstream):
    upstream(lambda request: httpx.Response(200, text=DETAIL_XML))
    document = service.get_official_document(*service.SEOKGURAM_CODES)
    document.retrieved_at = datetime.now(UTC) - timedelta(days=2)
    with transaction() as connection:
        connection.execute(
            "UPDATE official_documents SET document_json = ?", (document.model_dump_json(),)
        )
    upstream(lambda request: httpx.Response(503))
    cached = service.get_official_document(*service.SEOKGURAM_CODES)
    assert cached.stale and cached.cached
    assert "연결 실패" in cached.notice


@pytest.mark.parametrize(
    "payload",
    ["<html>failure</html>", "<result>", '<!DOCTYPE r [<!ENTITY x "bad">]><result>&x;</result>'],
)
def test_invalid_and_entity_xml_are_rejected(upstream, payload):
    upstream(lambda request: httpx.Response(200, text=payload))
    with pytest.raises(service.OfficialServiceError):
        service.search_official_heritages("석굴암")


def test_wrong_heritage_is_not_cached(upstream):
    payload = DETAIL_XML.replace("<ccbaCtcd>37", "<ccbaCtcd>11")
    upstream(lambda request: httpx.Response(200, text=payload))
    with pytest.raises(service.OfficialServiceError):
        service.get_official_document(*service.SEOKGURAM_CODES)
    assert service.get_cached_document(*service.SEOKGURAM_CODES) is None


def test_official_api_errors_and_validation(upstream):
    upstream(lambda request: httpx.Response(503))
    client = TestClient(app)
    assert client.get("/api/official/heritages?q=석굴암").status_code == 502
    assert client.get("/api/official/heritages?q=석굴암&page_size=51").status_code == 422
    assert client.get("/api/official/heritages/abc/0000240000000/37").status_code == 422
    upstream(lambda request: httpx.Response(200, text="<result></result>"))
    assert client.get("/api/official/heritages/11/0000240000000/37").status_code == 404


def test_gemini_receives_collected_source_text_and_url(upstream, monkeypatch):
    upstream(lambda request: httpx.Response(200, text=DETAIL_XML))
    document = service.get_official_document(*service.SEOKGURAM_CODES)
    captured = {}

    class FakeGemini:
        def __init__(self, **kwargs):
            self.models = self

        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="근거를 검토해야 하는 초안")

        def close(self):
            pass

    monkeypatch.setattr(question_service.genai, "Client", FakeGemini)
    answer = question_service._gemini_answer(
        "seokguram", "horyuji", "본문 설명을 알려 주세요", LearningLevel.BEGINNER
    )
    assert "공식 자료 테스트 설명" in captured["contents"]
    assert str(document.source_url) in captured["contents"]
    assert document.record_id in answer.source_ids
    assert answer.verification_status.value == "needs_review"
    assert answer.sources[-1].url == document.source_url
