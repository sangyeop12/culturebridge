from datetime import date

from culturebridge.domain.models import HeritageDetail, SourceRecord, VerificationStatus

SOURCES = {
    "src-seokguram-unesco": SourceRecord(
        id="src-seokguram-unesco",
        title="Seokguram Grotto and Bulguksa Temple",
        organization="UNESCO World Heritage Centre",
        url="https://whc.unesco.org/en/list/736/",
        retrieved_at=date(2026, 10, 13),
        license_note="영문 설명의 한국어 요약·CC BY-SA 3.0 IGO",
        summary="8세기 신라의 화강암 인공 석굴로 전실·통로·원형 주실로 구성된다.",
        scope_note="Brief synthesis를 요약했다. 불국사와 함께 등재된 자료다.",
    ),
    "src-seokguram-khs": SourceRecord(
        id="src-seokguram-khs",
        title="석굴암",
        organization="국가유산청 국가유산포털",
        url="https://www.heritage.go.kr/heri/html/HtmlPage.do?pageNo=2_1_1_0&pg=%2Funesco%2FHeritage%2FHeritage_01.jsp",
        retrieved_at=date(2026, 10, 13),
        license_note="페이지의 공공저작물 이용 조건을 확인한 뒤 재사용",
    ),
    "src-horyuji-unesco": SourceRecord(
        id="src-horyuji-unesco",
        title="Buddhist Monuments in the Horyu-ji Area",
        organization="UNESCO World Heritage Centre",
        url="https://whc.unesco.org/en/list/660/",
        retrieved_at=date(2026, 10, 13),
        license_note="CC BY-SA 3.0 IGO 표시 조건 확인",
        summary="나라현의 초기 목조 건축군과 중국 불교 건축·배치의 일본 내 수용을 설명한다.",
        scope_note="소개와 Brief Synthesis를 요약했다. 모든 건물의 연대가 같다는 뜻은 아니다.",
    ),
    "src-dayanta-unesco": SourceRecord(
        id="src-dayanta-unesco",
        title="Silk Roads: the Routes Network of Chang'an-Tianshan Corridor",
        organization="UNESCO World Heritage Centre",
        url="https://whc.unesco.org/en/list/1442/",
        retrieved_at=date(2026, 10, 13),
        license_note="페이지별 이용 조건 확인",
        summary="중국·카자흐스탄·키르기스스탄을 잇는 실크로드 회랑의 교역과 문화 교류를 설명한다.",
        scope_note="회랑 전체의 설명이다. 대안탑의 개별 재료·연대는 추가 자료 대조가 필요하다.",
    ),
}


HERITAGES = {
    "seokguram": HeritageDetail(
        id="seokguram",
        name="석굴암",
        country="대한민국",
        period="통일신라 8세기",
        location="경상북도 경주시",
        summary="화강암 부재를 조립해 조성한 인공 석굴 사원이다.",
        structure="전실·통로·원형 주실로 이어지는 인공 석굴",
        material="화강암",
        religious_context="불교 예배 공간과 조각 프로그램",
        source_ids=["src-seokguram-khs", "src-seokguram-unesco"],
    ),
    "horyuji": HeritageDetail(
        id="horyuji",
        name="호류지 불교 건축물",
        country="일본",
        period="7세기 후반~8세기 초",
        location="나라현 이카루가",
        summary="일본 초기 불교 건축의 전개를 보여 주는 목조 건축군이다.",
        structure="기둥과 보, 공포, 기와지붕으로 구성된 사찰 건축군",
        material="목재",
        religious_context="일본에 수용된 불교와 사찰 배치의 전개",
        source_ids=["src-horyuji-unesco"],
    ),
    "dayanta": HeritageDetail(
        verification_status=VerificationStatus.NEEDS_REVIEW,
        id="dayanta",
        name="대안탑",
        country="중국",
        period="당대 7세기",
        location="산시성 시안",
        summary="실크로드 교류와 불교 경전 전래의 맥락에서 살펴볼 수 있는 전탑이다.",
        structure="층을 쌓아 올린 누각식 전탑",
        material="벽돌",
        religious_context="불교 경전과 동서 문화 교류의 역사",
        source_ids=["src-dayanta-unesco"],
    ),
}
