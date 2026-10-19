"""Create local draft requests; no external recipient, fee, or permission is accepted."""

import argparse
import json
from pathlib import Path

from culturebridge.services.permission_request_service import permission_requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--school", required=True)
    parser.add_argument("--course", required=True)
    parser.add_argument("--applicant", required=True)
    parser.add_argument("--reply-email", default="")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    # Personal sender details must stay out of the repository and pre-existing files.
    if (
        args.output.resolve().parent != Path("outputs").resolve()
        or args.output.suffix != ".json"
        or args.output.exists()
    ):
        parser.error("outputs 바로 아래에 새 JSON 파일을 지정하세요.")
    rows = permission_requests(args.school, args.course, args.applicant, args.reply_email)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "requests": rows,
                "sent": 0,
                "fees_accepted": 0,
                "next_step": "발신 메일 연결·수신 기관 연락처 확인 후 발송",
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    print(
        json.dumps({"drafts": len(rows), "sent": 0, "output": str(args.output)}, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
