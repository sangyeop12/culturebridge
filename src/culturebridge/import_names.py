"""Import a team's reviewed Korean name file, validating every official ID/name first."""

import json
import sys
from pathlib import Path

from culturebridge.database import initialize_database
from culturebridge.services.name_registry_service import NameDraft, register_name
from culturebridge.services.unesco_service import search_unesco


def import_names(rows):
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError("이름 목록은 최대 2000개입니다.")
    validated = []
    for row in rows:
        identifier = str(row["id"])
        if not identifier.isdecimal() or len(identifier) > 10:
            raise ValueError("UNESCO 숫자 ID가 필요합니다.")
        result = search_unesco(identifier)
        if len(result.records) != 1 or result.records[0].name != row["official_name"]:
            raise ValueError("공식 ID와 영문명이 일치하지 않습니다.")
        draft = NameDraft(korean_name=row["korean_name"], aliases=row.get("aliases", []))
        validated.append(("unesco:" + identifier, row["official_name"], draft))
    # All validation precedes writes; an invalid file cannot partially replace the registry.
    for identifier, official_name, draft in validated:
        register_name(
            identifier, official_name, draft.korean_name, draft.aliases, status="reviewed"
        )
    return len(validated)


def main():
    initialize_database()
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python -m culturebridge.import_names 이름파일.json")
    rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    print(f"한국어 검토 이름 {import_names(rows)}개 등록")


if __name__ == "__main__":
    main()
