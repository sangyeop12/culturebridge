"""Opt-in scheduled backups; destructive retention needs a verified backup first."""

import argparse
import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from culturebridge.backup_db import backup_database
from culturebridge.config import get_settings
from culturebridge.services.data_retention_service import delete_records


def maintain(*, apply=False):
    settings = get_settings()
    cutoff = (datetime.now(UTC) - timedelta(days=settings.record_retention_days)).isoformat()
    report = {"retention": delete_records(cutoff=cutoff), "backup": None, "pruned_backups": 0}
    if not apply:
        return report
    directory = settings.backup_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    filename = (
        "culturebridge-auto-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid4().hex
        + ".db"
    )
    backup = backup_database(directory / filename)
    report["backup"] = backup.name
    if settings.retention_enabled:
        report["retention"] = delete_records(cutoff=cutoff, apply=True)
    # Only files made by this command in this exact directory; never recurse or follow symlinks.
    backups = sorted(
        (
            path
            for path in directory.iterdir()
            if re.fullmatch(r"culturebridge-auto-\d{8}T\d{6}-[a-f0-9]{32}\.db", path.name)
            and path.is_file()
            and not path.is_symlink()
        ),
        key=lambda path: (path == backup, path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for path in backups[settings.backup_keep :]:
        path.unlink()
        report["pruned_backups"] += 1
    return report


async def maintenance_loop():
    while True:
        try:
            await asyncio.to_thread(maintain, apply=True)
        except Exception as exc:
            logging.getLogger(__name__).error(
                "Scheduled maintenance failed: %s", type(exc).__name__
            )
        await asyncio.sleep(get_settings().maintenance_interval_hours * 3600)


def main():
    parser = argparse.ArgumentParser(description="백업·보관 정책 점검 (기본은 변경 없는 미리보기)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="백업 생성·백업 보관 수 적용; 기록 삭제는 별도 retention_enabled 설정 필요",
    )
    args = parser.parse_args()
    print(json.dumps(maintain(apply=args.apply), ensure_ascii=False))


if __name__ == "__main__":
    main()
