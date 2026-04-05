#!/usr/bin/env python3
"""Repair Bambuddy archive runtime fields directly in SQLite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.bambuddy.runtime_repair_core import (
    RepairValues,
    backup_database,
    repair_archive_runtime,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair Bambuddy archive runtime fields")
    parser.add_argument("--db-path", required=True, help="Path to bambuddy.db")
    parser.add_argument("--archive-id", required=True, type=int, help="Archive ID to repair")
    parser.add_argument("--started-at", help="New started_at ISO datetime")
    parser.add_argument("--completed-at", help="New completed_at ISO datetime")
    parser.add_argument("--created-at", help="New created_at ISO datetime")
    parser.add_argument("--status", help="New status value")
    parser.add_argument("--failure-reason", help="New failure_reason value")
    parser.add_argument("--audit-note", help="Append audit note to notes field")
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a backup copy of the database before applying changes.",
    )
    parser.add_argument(
        "--backup-path",
        help="Optional explicit backup path. Implies --backup when used.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the repair. Without this flag, the script runs in dry-run mode.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)

    try:
        values = RepairValues(
            started_at=args.started_at,
            completed_at=args.completed_at,
            created_at=args.created_at,
            status=args.status,
            failure_reason=args.failure_reason,
            audit_note=args.audit_note,
        )
        backup_path = None
        if args.apply and (args.backup or args.backup_path):
            backup_path = str(backup_database(db_path, Path(args.backup_path) if args.backup_path else None))

        result = repair_archive_runtime(
            db_path=db_path,
            archive_id=args.archive_id,
            values=values,
            apply=bool(args.apply),
        ).to_dict()

        if backup_path:
            result["backup_path"] = backup_path

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())