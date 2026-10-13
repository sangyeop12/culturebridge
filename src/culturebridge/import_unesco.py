import argparse
from pathlib import Path

from culturebridge.database import initialize_database
from culturebridge.services.official_service import OfficialServiceError
from culturebridge.services.unesco_service import MAX_BYTES, import_unesco_xml


def main() -> int:
    parser = argparse.ArgumentParser(description="Import an official UNESCO English XML download")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        with args.path.open("rb") as handle:
            payload = handle.read(MAX_BYTES + 1)
        initialize_database()
        count = import_unesco_xml(payload)
    except (OSError, OfficialServiceError):
        print("XML import failed. Check the file and its official XML format.")
        return 1
    print(f"Imported UNESCO English XML: {count} records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
