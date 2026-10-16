"""Private, snapshot-based reports. Raw provider text and unsubmitted quiz answers are omitted."""

import html
import json
from datetime import UTC, datetime, timedelta, timezone

from culturebridge.database import transaction
from culturebridge.services.comparison_service import ComparisonNotFoundError, get_saved_comparison
from culturebridge.services.curriculum_service import GOAL_LABELS
from culturebridge.services.display_service import display_name
from culturebridge.services.evidence_comparison_service import supported_fields
from culturebridge.services.evidence_reading_service import reading_units
from culturebridge.services.lesson_service import beginner_text
from culturebridge.services.operation_service import owner_key


class LearningReportNotFoundError(KeyError):
    pass


# Current classroom records use KST; no platform-specific tzdata dependency is needed.
KST = timezone(timedelta(hours=9), "KST")


def _summary(field):
    if field is None:
        return "근거 부족 · 판단 보류"
    if field.category == "시대":
        summary = beginner_text(field.category, field.evidence_quote)
        if summary.startswith(("원문에 나온 시기는 ", "원문에는 ")):
            return summary
        return "연대·사건은 서비스에서 원문과 대조하세요. 자동 요약은 보류했습니다."
    units = reading_units(field.category, field.evidence_quote)
    return (
        "원문에서 찾은 표현: " + " · ".join(label for _, label in units)
        if units
        else ("이 항목은 서비스에서 원문과 함께 확인하세요. 지원 표현으로 요약하지 않았습니다.")
    )


def learning_report(record_id, history_id=None):
    # Export is always session-bound, including local/development mode.
    with transaction() as connection:
        owner = connection.execute(
            "SELECT owner FROM resource_owners WHERE kind='comparison' AND id=?", (record_id,)
        ).fetchone()
        if not owner or owner["owner"] != owner_key():
            raise ComparisonNotFoundError(record_id)
    saved = get_saved_comparison(record_id)
    comparison = saved.comparison
    fields = {(field.heritage_id, field.category): field for field in supported_fields(comparison)}
    with transaction() as connection:
        attempt = connection.execute(
            "SELECT DISTINCT r.history_id,r.result_json,h.created_at FROM learning_reviews r "
            "JOIN learning_history h ON h.id=r.history_id JOIN quiz_items q ON q.quiz_id=r.quiz_id "
            "JOIN resource_owners o ON o.kind='quiz' AND o.id=q.quiz_id "
            "WHERE q.comparison_id=? AND r.owner=? AND o.owner=? "
            "AND (? IS NULL OR r.history_id=?) ORDER BY r.history_id DESC LIMIT 1",
            (record_id, owner_key(), owner_key(), history_id, history_id),
        ).fetchone()
    if history_id is not None and not attempt:
        raise LearningReportNotFoundError(history_id)
    assessment = None
    if attempt:
        result = json.loads(attempt["result_json"])
        assessment = {
            "history_id": attempt["history_id"],
            "submitted_at": datetime.fromisoformat(attempt["created_at"])
            .replace(tzinfo=UTC)
            .astimezone(KST)
            .isoformat(),
            "score": int(result["score"]),
            "total": int(result["total"]),
            "review_activities": [
                {"number": item["number"], "activity": item["activity"]}
                for item in result.get("review_items", [])
            ],
        }
    return {
        "title": "CultureBridge 문화유산 비교 학습지",
        "comparison_id": saved.id,
        "saved_at": saved.created_at.astimezone(KST).isoformat(),
        "exported_at": datetime.now(KST).isoformat(),
        "learning_version": comparison.learning_version,
        "level": comparison.level.value,
        "level_label": {"beginner": "초급", "intermediate": "중급", "advanced": "고급"}[
            comparison.level.value
        ],
        "goal": GOAL_LABELS[comparison.goal.value],
        "goal_text": comparison.goal_text,
        "curriculum": comparison.curriculum,
        "left": display_name(comparison.left.id, comparison.left.name),
        "right": display_name(comparison.right.id, comparison.right.name),
        "basis": comparison.basis,
        "verification_status": comparison.verification_status.value,
        "common_points": comparison.common_points,
        "comparison": [
            {
                "category": point.category,
                "left": _summary(fields.get((comparison.left.id, point.category))),
                "right": _summary(fields.get((comparison.right.id, point.category))),
                "analysis": point.explanation,
            }
            for point in comparison.differences
        ],
        "sources": [
            {
                "title": source.title,
                "organization": source.organization,
                "url": str(source.url),
                "retrieved_at": source.retrieved_at.isoformat(),
            }
            for source in saved.sources
        ],
        "assessment": assessment,
        "notices": comparison.learning_notices
        + [
            "저장 당시의 자료를 바탕으로 한 학습용 검토 후보이며 역사적 의미 검증 완료가 아닙니다.",
            "원문 전체·직접 인용·퀴즈 문항 본문·선택지·정답은 내보내기에 포함하지 않습니다.",
            "출처 표시가 재배포 허가를 뜻하지 않습니다. 기관별 이용 조건을 확인하세요.",
            "파일에는 학습 목표·점수 등이 포함될 수 있습니다. 공유 전에 내용을 확인하세요.",
        ],
    }


def report_markdown(report):
    def text(value):
        return html.escape(str(value)).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

    lines = [
        "# " + text(report["title"]),
        "",
        text(report["left"]) + " ↔ " + text(report["right"]),
        "",
        "- 수준: " + text(report["level_label"]),
        "- 학습 목표: " + text(report["goal"]),
        "- 세부 목표: " + text(report["goal_text"] or "없음"),
        "- 저장 시각: " + text(report["saved_at"]),
        "- 비교 ID: " + text(report["comparison_id"]),
        "",
        "## 학습 순서",
        "",
    ]
    lines += [str(index) + ". " + text(step) for index, step in enumerate(report["curriculum"], 1)]
    lines += ["", "## 공통점과 항목별 비교", ""] + [
        "- " + text(point) for point in report["common_points"]
    ]
    for row in report["comparison"]:
        lines += [
            "",
            "### " + text(row["category"]),
            "- 왼쪽: " + text(row["left"]),
            "- 오른쪽: " + text(row["right"]),
            "- 비교 기준: " + text(row["analysis"]),
        ]
    lines += ["", "## 퀴즈와 복습", ""]
    assessment = report["assessment"]
    if assessment:
        lines += [f"점수: {assessment['score']} / {assessment['total']}"]
        lines += [
            f"- {item['number']}번 보충 활동: " + text(item["activity"])
            for item in assessment["review_activities"]
        ]
    else:
        lines += [
            "이 비교에 연결된 현재 세션의 제출 결과가 없습니다. 정답을 미리 제공하지 않습니다."
        ]
    lines += [
        "",
        "## 내가 정리한 내용",
        "",
        "- 공통점: ",
        "- 차이점: ",
        "- 더 확인할 점: ",
        "",
        "## 공식 출처",
        "",
    ]
    lines += [
        "- "
        + text(source["organization"])
        + " / "
        + text(source["title"])
        + " / "
        + text(source["url"])
        + " / 조회: "
        + text(source["retrieved_at"])
        for source in report["sources"]
    ]
    lines += ["", "## 안내", ""] + ["- " + text(note) for note in report["notices"]]
    return "\n".join(lines)


def report_html(report):
    def escape(value):
        return html.escape(str(value), quote=True)

    def paragraphs(values):
        return "".join("<li>" + escape(value) + "</li>" for value in values)

    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + escape(row[key]) + "</td>" for key in ("category", "left", "right", "analysis")
        )
        + "</tr>"
        for row in report["comparison"]
    )
    sources = "".join(
        "<li>"
        + escape(source["organization"])
        + " · "
        + escape(source["title"])
        + ' · <a href="'
        + escape(source["url"])
        + '">'
        + escape(source["url"])
        + "</a>"
        + " · "
        + escape(source["retrieved_at"])
        + "</li>"
        for source in report["sources"]
    )
    assessment = report["assessment"]
    quiz = (
        (
            f"<p>점수: {assessment['score']} / {assessment['total']}</p><ul>"
            + paragraphs(
                [
                    str(item["number"]) + "번: " + item["activity"]
                    for item in assessment["review_activities"]
                ]
            )
            + "</ul>"
        )
        if assessment
        else "<p>제출된 퀴즈 결과 없음 · 정답을 미리 제공하지 않습니다.</p>"
    )
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>CultureBridge 학습 결과</title><style>"
        'body{font-family:Arial,"Malgun Gothic",sans-serif;line-height:1.7;color:#203631;'
        "max-width:1100px;margin:32px auto;padding:0 20px}h1,h2{color:#193e3a}"
        "table{border-collapse:collapse;width:100%;table-layout:fixed}"
        "td,th{border:1px solid #bbb;padding:10px;vertical-align:top;overflow-wrap:anywhere}"
        "a{overflow-wrap:anywhere} .writing{min-height:80px;border-bottom:1px solid #bbb}"
        "@media print{.toolbar{display:none}body{margin:0;max-width:none;font-size:10pt}"
        "tr{break-inside:avoid}h2{break-after:avoid}}@page{size:A4;margin:16mm}"
        '</style></head><body><div class="toolbar"><button onclick="window.print()">'
        "인쇄 / PDF로 저장</button><p>브라우저의 인쇄 기능에서 "
        "PDF 저장을 선택할 수 있어요.</p></div>"
        "<h1>"
        + escape(report["title"])
        + "</h1><p>"
        + escape(report["left"])
        + " ↔ "
        + escape(report["right"])
        + "</p><p>수준: "
        + escape(report["level_label"])
        + " · 목표: "
        + escape(report["goal"])
        + "</p>"
        "<p>세부 목표: " + escape(report["goal_text"] or "없음") + "</p>"
        "<p>저장 시각: "
        + escape(report["saved_at"])
        + " · 학습 구성 버전: "
        + str(report["learning_version"])
        + "</p><h2>학습 순서</h2><ol>"
        + paragraphs(report["curriculum"])
        + "</ol><h2>공통점 검토</h2><ul>"
        + paragraphs(report["common_points"])
        + "</ul>"
        "<h2>항목별 비교</h2><table><thead><tr><th>항목</th><th>왼쪽 유산</th>"
        "<th>오른쪽 유산</th><th>비교 기준</th></tr></thead><tbody>" + rows + "</tbody></table>"
        "<h2>퀴즈와 복습</h2>" + quiz + "<h2>내가 정리한 내용</h2>"
        '<p class="writing">공통점:</p><p class="writing">차이점:</p>'
        '<p class="writing">더 확인할 점:</p><h2>공식 출처</h2><ul>' + sources + "</ul>"
        "<h2>안내</h2><ul>" + paragraphs(report["notices"]) + "</ul></body></html>"
    )
