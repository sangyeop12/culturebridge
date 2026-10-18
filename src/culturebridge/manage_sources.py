"""Administrator-only local command. No public mutation endpoint or arbitrary fetch URL."""

import argparse
import json

from culturebridge.database import initialize_database
from culturebridge.services.source_registry_service import save_review, source_overview


def main():
    parser = argparse.ArgumentParser(description="공식 자료 목록·검토 상태 관리")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    review = sub.add_parser("review")
    review.add_argument("id")
    review.add_argument("--korean-name", required=True)
    review.add_argument("--alias", action="append", default=[])
    review.add_argument("--name-status", choices=["guidance", "reviewed"], default="guidance")
    review.add_argument(
        "--usage-status", choices=["pending", "reviewed", "restricted"], default="pending"
    )
    review.add_argument("--note", default="")
    permission = sub.add_parser("permission", help="확인된 처리 목적별 이용 근거 기록")
    permission.add_argument("id")
    permission.add_argument(
        "--purpose",
        choices=["storage_display", "ai", "translation", "redistribution"],
        required=True,
    )
    permission.add_argument("--status", choices=["approved", "denied"], required=True)
    permission.add_argument("--note", required=True, help="허가 문서·정책 등 실제 확인 근거")
    permission.add_argument(
        "--confirm-evidence",
        action="store_true",
        help="실제 출처·처리 목적의 허용 근거를 확인했을 때만 지정",
    )
    sub.add_parser("permissions", help="25개 자료의 네 목적별 확인 상태 출력 (원문·AI 호출 없음)")
    args = parser.parse_args()
    initialize_database()
    if args.command == "permissions":
        from culturebridge.services.material_review_service import material_review

        print(
            json.dumps(
                [
                    {"id": row["id"], "name": row["korean_name"], "usage": row["classroom_usage"]}
                    for row in material_review()
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.command == "review":
        save_review(
            args.id.removeprefix("official:"),
            args.korean_name,
            args.alias,
            name_status=args.name_status,
            usage_status=args.usage_status,
            note=args.note,
        )
    elif args.command == "permission":
        if args.status == "approved" and not args.confirm_evidence:
            parser.error("승인은 실제 허용 근거 확인 후 --confirm-evidence가 필요합니다.")
        from culturebridge.services.source_permission_service import record_permission

        record_permission(
            args.id.removeprefix("official:"), args.purpose, args.status == "approved", args.note
        )
    print(json.dumps(source_overview(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
