"""Run an explicit live smoke check without concealing fallback as success."""

import json

from culturebridge.config import get_settings
from culturebridge.domain.models import LearningLevel
from culturebridge.services.question_service import _gemini_answer


def main() -> int:
    settings = get_settings()
    if not settings.gemini_api_key:
        print(
            json.dumps(
                {"status": "not_configured", "message": "로컬 .env에 GEMINI_API_KEY를 설정하세요."},
                ensure_ascii=False,
            )
        )
        return 2
    try:
        answer = _gemini_answer(
            "seokguram", "horyuji", "두 유산의 재료를 비교해 주세요.", LearningLevel.BEGINNER
        )
    except Exception as exc:
        # Do not print SDK exception text: it can contain request details.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1
    print(
        json.dumps(
            {
                "status": "success",
                "model": settings.gemini_model,
                "used_ai": answer.used_ai,
                "verification_status": answer.verification_status.value,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
