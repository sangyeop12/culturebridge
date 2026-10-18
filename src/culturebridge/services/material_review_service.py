"""A transparent review matrix: connection evidence never becomes editorial/legal approval."""

import json
from urllib.parse import urlsplit

from culturebridge.data.material_review import POLICIES, SCOPE_NOTES
from culturebridge.data.source_audit import NAME_FINDINGS, PROVIDER_FINDINGS, REVIEW_DATE
from culturebridge.database import transaction
from culturebridge.domain.models import CollectedSource
from culturebridge.services.classroom_usage_service import classroom_usage
from culturebridge.services.display_service import display_country
from culturebridge.services.extraction_service import _local_extraction, validate_extraction
from culturebridge.services.source_registry_service import source_overview
from culturebridge.services.subject_service import focused_text, primary_type


def material_review():
    with transaction() as connection:
        cached = {
            r["id"]: r["source_json"]
            for r in connection.execute("SELECT id,source_json FROM agent_source_cache")
        }
    rows = []
    for row in source_overview():
        identity = row["id"].split(":", 1)[1]
        if identity not in SCOPE_NOTES:
            continue  # Horyuji is retained separately, not counted in the 25-target checklist.
        host = urlsplit(row["source_url"]).hostname or ""
        policy = next(
            (
                value
                for domain, value in POLICIES.items()
                if host == domain or host.endswith("." + domain)
            ),
            None,
        )
        snapshot = (
            CollectedSource.model_validate_json(cached[row["id"]]) if row["id"] in cached else None
        )
        categories = (
            sorted(
                {
                    draft.category
                    for draft in _local_extraction([snapshot])
                    if validate_extraction(draft, [snapshot])
                }
            )
            if snapshot
            else []
        )
        units = primary_type(snapshot.title, focused_text(snapshot)) if snapshot else None
        finding = next(
            (
                value
                for domain, value in PROVIDER_FINDINGS.items()
                if host == domain or host.endswith("." + domain)
            ),
            None,
        )
        usage = classroom_usage(row["source_url"], identity)
        rows.append(
            {
                **row,
                "scope_note": SCOPE_NOTES[identity],
                "scope_check": "등록 유형과 자동 추출 유형 일치·범위 의미 검토는 별도"
                if units == row["type"]
                else "원문 대조 필요",
                "categories": categories,
                "name_check": "팀 검토 기록 있음"
                if row["name_status"] == "reviewed"
                else "안내 표기·팀 검토 필요",
                "explanation_check": "한국어 풀이의 의미·수준 적합성 검토 필요",
                "desk_review": "AI 사전 점검 기록·팀 최종 승인 아님",
                "desk_review_date": REVIEW_DATE,
                "name_finding": NAME_FINDINGS[identity],
                "name_reference_url": row["source_url"],
                "policy_status": finding[0] if finding else "not_established",
                "ai_permission": "해당 출처·목적의 관리자 확인 기록 있음"
                if usage["purposes"]["ai"]["approved"]
                else "미확인 또는 불허·외부 AI 전송 허가로 간주하지 않음",
                "translation_permission": "해당 출처·목적의 관리자 확인 기록 있음"
                if usage["purposes"]["translation"]["approved"]
                else "서비스용 번역 허가 미확인 또는 불허",
                "redistribution_permission": "해당 출처·목적의 관리자 확인 기록 있음"
                if usage["purposes"]["redistribution"]["approved"]
                else "공개 재배포 허가 미확인 또는 불허",
                "policy_url": finding[1] if finding else policy[0] if policy else row["source_url"],
                "policy_note": finding[2]
                if finding
                else policy[1]
                if policy
                else "일반 재이용 조건을 확정하지 못했다. 기관 문의·개별 조건 확인 필요.",
                "policy_checked_date": REVIEW_DATE if finding or policy else None,
                "permission": "허가 완료를 뜻하지 않음",
                "classroom_usage": usage,
            }
        )
    return rows


def review_markdown():
    rows = material_review()
    lines = [
        "# 해외 문화유산 25개 자료 검토표",
        "",
        "연결·제목 대조는 기술 점검이며 한국어 의미 승인이나 재이용 허가가 아닙니다.",
        "표의 연결 상태는 현재 서버의 마지막 수집 시도 기준입니다. "
        "호류지 1개는 별도 보류 대상입니다.",
        "",
        "| 문화유산 | 국가 | 단위·유형 대조 | 한국어 이름·풀이 | 근거 항목 | 이용 조건 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        cells = [
            row["korean_name"],
            display_country(row["country"]),
            ("경내 전체" if row["unit"] == "site" else "개별 건물") + " · " + row["scope_check"],
            row["name_check"] + " / 풀이 의미 검토 필요",
            "·".join(row["categories"]) or "미수집",
            "검토 기록 있음·허가 범위 확인"
            if row["usage_status"] == "reviewed"
            else "권한 확인 필요",
        ]
        lines.append(
            "| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |"
        )
    lines += ["", "## 대상별 확인 사항", ""]
    for row in rows:
        lines += [
            "### " + row["korean_name"] + " (" + row["name"] + ")",
            "",
            "- 대상 ID: `" + row["id"] + "` / 포함 관계: `" + row["parent_id"] + "`",
            "- 공식 출처: [" + row["organization"] + "](" + row["source_url"] + ")",
            "- 한국어 이름: " + row["name_check"] + ". 공식 한국어 번역으로 인증하지 않았습니다.",
            "- 풀이: " + row["explanation_check"] + ".",
            "- 사전 표기 점검: " + row["name_finding"],
            "- 점검자·일자: AI 사전 점검 / " + row["desk_review_date"] + " / 팀 최종 승인 아님",
            "- 대상 범위: " + row["scope_note"],
            "- 연결: "
            + row["connection_status"]
            + " / 최근 성공: "
            + (row["last_success_at"] or "미기록"),
            "- 이용 조건 참고: [기관 안내](" + row["policy_url"] + ")",
            "- 권리 검토: " + row["policy_note"],
            "- 번역: " + row["translation_permission"] + " / AI: " + row["ai_permission"],
            "- 공개 재배포: " + row["redistribution_permission"],
            "- 검토 맥락: " + row["classroom_usage"]["context"],
            *[
                "- " + purpose["label"] + ": " + purpose["reason"]
                for purpose in row["classroom_usage"]["purposes"].values()
            ],
            "",
        ]
    return "\n".join(lines)


def review_json():
    return json.dumps(material_review(), ensure_ascii=False, indent=2)
