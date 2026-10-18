"""Purpose-specific classroom assessment, distinct from permission and enforcement."""

from urllib.parse import urlsplit

from culturebridge.data.source_audit import PROVIDER_FINDINGS

PURPOSE_LABELS = {
    "storage_display": "서버 저장·화면 표시",
    "translation": "한국어 번역·쉬운 설명 가공",
    "ai": "외부 AI 전송",
    "redistribution": "학습 결과 다운로드·재배포",
}


def classroom_usage(source_url, identity=None):
    host = (urlsplit(str(source_url)).hostname or "").removeprefix("www.")
    match = next(
        (
            (domain, value)
            for domain, value in PROVIDER_FINDINGS.items()
            if host == domain or host.endswith("." + domain)
        ),
        None,
    )
    domain, finding = match if match else (host, None)
    educational_exception = domain in {"sainte-chapelle.fr", "abbaye-mont-saint-michel.fr"}
    purposes = {}
    for key, label in PURPOSE_LABELS.items():
        status = "not_established"
        reason = "이 용도를 허용하는 서비스 적용 근거가 아직 확인되지 않았어요."
        if educational_exception and key in {"storage_display", "redistribution"}:
            status = "educational_exception_review"
            reason = (
                "교육 목적 예외가 명시돼 있어요. "
                "개별 사이트·우리 수업의 적용 범위는 확인이 필요해요."
            )
        elif finding and finding[0] == "permission_required":
            status = "permission_required"
            reason = "약관에 허가 조건이 있어요. 교육 목적만으로 이 용도의 허가를 추정하지 않아요."
        purposes[key] = {"label": label, "status": status, "reason": reason, "approved": False}
        if identity:
            from culturebridge.services.source_permission_service import permission_status

            recorded = permission_status(identity, key)
            purposes[key]["recorded_status"] = recorded
            if recorded == "approved":
                purposes[key].update(
                    status="recorded_approval",
                    approved=True,
                    reason=(
                        "이 출처·목적의 관리자 확인 근거가 기록돼 있어요. 다른 용도는 별도예요."
                    ),
                )
            elif recorded in {"denied", "restricted", "needs_rereview"}:
                purposes[key].update(
                    status=recorded,
                    reason={
                        "denied": "이 목적은 불허로 기록돼 있어요.",
                        "restricted": "관리자가 이용 제한으로 표시한 출처예요.",
                        "needs_rereview": "출처 변경 또는 이전 승인 기록의 범위 재확인이 필요해요.",
                    }[recorded],
                )
    return {
        "context": "비상업 개인·수업 프로젝트 / 팀원·교수님 시연",
        "policy_checked_date": "2026-10-19",
        "policy_url": finding[1] if finding else None,
        "purposes": purposes,
        "review_note": "조건 확인 기록이며 권리자 허가·법률 판단·서비스 차단 설정이 아니에요.",
        "commercial_release_assessed": False,
    }
