"""Generate a metadata-only checklist without overwriting an existing document."""

import argparse
from pathlib import Path

from culturebridge.database import initialize_database
from culturebridge.services.material_review_service import review_json, review_markdown


def main():
    parser = argparse.ArgumentParser(description="25개 공식 자료 검토표 생성 (AI 호출 없음)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    initialize_database()
    text = review_json() if args.output.suffix == ".json" else review_markdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print(args.output)


if __name__ == "__main__":
    main()
