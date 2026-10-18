"""Dated desk review. These findings are not legal advice, permission, or human approval."""

REVIEW_DATE = "2026-10-17"

# A policy being found is never a licence to translate, send to AI, or republish.
PROVIDER_FINDINGS = {
    "japan.travel": (
        "permission_required",
        "https://www.japan.travel/en/terms-of-use/",
        "복제·저장·번역·변형 등에 권리자의 명시적 허가를 요구한다.",
    ),
    "chateauversailles.fr": (
        "permission_required",
        "https://en.chateauversailles.fr/legal-information",
        "개인적·사적인 정보 이용 외 복제·이용을 제한한다. 링크 조건도 확인해야 한다.",
    ),
    "nijo-jocastle.city.kyoto.lg.jp": (
        "exception_scope",
        "https://nijo-jocastle.city.kyoto.lg.jp/site_policy/",
        "사적 복제·인용 등 법률상 허용 범위 외 무단 복제·전용을 제한한다.",
    ),
    "edinburghcastle.scot": (
        "exception_scope",
        "https://www.edinburghcastle.scot/terms-and-conditions/",
        "개인적 발췌와 출처 표시 조건이 있으며 변형·상업 이용은 별도 조건을 확인한다.",
    ),
    "hrp.org.uk": (
        "exception_scope",
        "https://www.hrp.org.uk/terms-of-use/",
        "개인적 발췌·저자 표시를 허용하나 변형을 제한하고 상업 이용은 라이선스를 요구한다.",
    ),
    "english-heritage.org.uk": (
        "exception_scope",
        "https://www.english-heritage.org.uk/about/our-policies-and-reports/terms-and-conditions/",
        "개인 이용을 넘는 복제·공유·다른 저작물 편입의 허가를 확인해야 한다.",
    ),
    "sainte-chapelle.fr": (
        "exception_scope",
        "https://www.monuments-nationaux.fr/mentions-legales",
        "CMN은 개인·교육·과학·정보 목적의 예외를 명시한다. 개별 사이트·변형 적용은 미확정이다.",
    ),
    "abbaye-mont-saint-michel.fr": (
        "exception_scope",
        "https://www.monuments-nationaux.fr/mentions-legales",
        "CMN의 교육적 이용 예외와 저자 표시·무변형 조건을 실제 공개 서비스와 대조해야 한다.",
    ),
    "incredibleindia.gov.in": (
        "permission_required",
        "https://www.incredibleindia.gov.in/en/terms-of-use",
        "법률상 허용 또는 서면 허가 없는 복제·게시·전송·수정·파생물 작성을 제한한다.",
    ),
    "agra.nic.in": (
        "permission_required",
        "https://agra.nic.in/website-policies/",
        "이메일로 적절한 허가를 받은 뒤 정확한 재현·출처 표시를 요구한다. 제3자 자료는 별도다.",
    ),
    "tajmahal.gov.in": (
        "not_established",
        "https://tajmahal.gov.in/disclaimer.aspx",
        "면책 안내는 확인했으나 번역·AI 전송·공개 재배포 허가 조항을 확인하지 못했다.",
    ),
    "mptourism.com": (
        "not_established",
        "https://www.mptourism.com/disclaimer.php",
        "면책 안내와 권리 유보를 확인했다. 공개 재사용·AI 처리 허용 범위는 미확정이다.",
    ),
    "en.xa.gov.cn": (
        "not_established",
        "https://en.xa.gov.cn/ContactUs/1.html",
        "기관 문의 경로이다. 일반 콘텐츠 이용허락 정책으로 간주하지 않는다.",
    ),
    "durhamcathedral.co.uk": (
        "not_established",
        "https://www.durhamcathedral.co.uk/legal/terms-and-conditions",
        "행사·박물관 약관은 본문 재이용 허가가 아니다. 대성당 본문 권한은 별도 문의가 필요하다.",
    ),
    "english.visitbeijing.com.cn": (
        "not_established",
        "https://www.visitbeijing.com.cn/service-agreement",
        "중문 본 사이트는 원출처·비상업 목적 등 조건을 제시한다. "
        "영문·제3자 기사 적용은 미확정이다.",
    ),
}

# The names identify the intended subject; an institution's Korean article is not
# proof that our component-specific label is its official registered Korean title.
NAME_FINDINGS = {
    "dayanta": "Giant Wild Goose Pagoda와 대안탑을 대응시킨 안내명이다.",
    "taj-mahal-mausoleum": "Taj Mahal의 tomb/mausoleum만 가리키도록 묘당을 덧붙인 안내명이다.",
    "grand-trianon": "Grand Trianon을 음역하고 palace를 궁전으로 풀이한 안내명이다.",
    "st-margarets-chapel": "St Margaret's Chapel의 성인명 음역·예배당 표기이다.",
    "humayun-tomb": "Humayun's Tomb의 인명 음역과 묘 표기이다. 휴마윤 등 별칭을 유지한다.",
    "agra-fort": "Agra Fort의 안내명이며 경내 전체를 가리킨다.",
    "sanchi-great-stupa": "Great Stupa의 안내명이다. 산치 전체가 아닌 제1탑을 구분한다.",
    "edinburgh-great-hall": "Great Hall을 대연회장으로 풀이하며 성 전체와 구분한다.",
    "toji-pagoda": "JNTO 한국어의 도지·오층탑 표현을 대조했다. 사찰 전체의 명칭과 구분한다.",
    "todaiji-hall": "JNTO 한국어의 도다이지·다이부쓰덴 불전을 대조했다. 불상과 구분한다.",
    "kiyomizu-hall": "JNTO 한국어의 기요미즈데라·본당을 대응시켰다. 청수사를 별칭으로 유지한다.",
    "himeji-castle": "JNTO 한국어의 히메지성 표기를 대조했다. 천수만을 뜻하지 않는다.",
    "ninomaru-palace": "Ninomaru Palace의 안내명이다. 니조성 전체와 구분한다.",
    "byodoin-phoenix-hall": "JNTO 한국어의 뵤도인·봉황당을 대응시킨 안내명이다.",
    "yakushiji-temple": "JNTO 한국어의 야쿠시지 사원 표기를 대조했다. 약사사를 별칭으로 유지한다.",
    "kinkakuji-pavilion": (
        "JNTO의 킨카쿠지·금빛 누각 설명과 대응한다. 금각사·긴카쿠지를 함께 검색한다."
    ),
    "petit-trianon": "Petit Trianon의 음역 안내명이다. 그랑 트리아농과 구분한다.",
    "versailles-palace": "Palace of Versailles의 안내명이며 영지 전체와 구분한다.",
    "versailles-royal-chapel": "Royal Chapel의 예배당 안내명이다. palace와 분리한다.",
    "sainte-chapelle": (
        "Sainte-Chapelle의 안내명이다. chapel의 정확한 풀이로 왕실 예배당도 병기한다."
    ),
    "mont-saint-michel-abbey": "Abbey를 수도원으로 풀이했다. 섬·만 전체의 등재명과 구분한다.",
    "white-tower": "White Tower의 음역이며 런던탑 전체와 구분한다.",
    "stonehenge": "Stonehenge의 안내명이다. Avebury 등 다른 등재 구성 유산을 포함하지 않는다.",
    "durham-cathedral": "Durham Cathedral의 대성당 안내명이며 Durham Castle과 구분한다.",
    "heaven-prayer-hall": (
        "Hall of Prayer for Good Harvests를 기년전과 대응시켰다. 천단 전체와 구분한다."
    ),
}
