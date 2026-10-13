"""Read-only version and dependency-lock verification; never prints API keys."""

import json
import platform
import sqlite3
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from culturebridge.config import get_settings


def environment_report(lock_path: Path | None = None):
    lock_path = lock_path or Path(__file__).resolve().parents[2] / "requirements-lock.txt"
    mismatches = []
    pinned = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = "missing"
        pinned[name] = installed
        if installed != expected:
            mismatches.append(f"{name}: expected {expected}, installed {installed}")
    if sys.version_info[:2] not in {(3, 12), (3, 13)}:
        mismatches.append("Supported Python versions are 3.12 and 3.13")
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "sqlite": sqlite3.sqlite_version,
        "gemini_model": get_settings().gemini_model,
        "packages": pinned,
        "mismatches": mismatches,
        "status": "ok" if not mismatches else "mismatch",
    }


def main():
    report = environment_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
