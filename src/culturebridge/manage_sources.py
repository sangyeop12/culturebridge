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
        "--purpose", choices=["ai", "translation", "redistribution"], required=True
    )
    permission.add_argument("--status", choices=["approved", "denied"], required=True)
    permission.add_argument("--note", required=True, help="허가 문서·정책 등 실제 확인 근거")
    args = parser.parse_args()
    initialize_database()
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
        from culturebridge.services.source_permission_service import record_permission

        record_permission(
            args.id.removeprefix("official:"), args.purpose, args.status == "approved", args.note
        )
    print(json.dumps(source_overview(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
