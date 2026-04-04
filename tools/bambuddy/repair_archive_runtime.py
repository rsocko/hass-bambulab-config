#!/usr/bin/env python3
"""Repair Bambuddy archive runtime fields directly in SQLite.

Reference-only administrative tool for restoring canonical runtime values
when the public Bambuddy archive API cannot mutate those fields.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ALLOWED_STATUS_VALUES = {
    "archived",
    "printing",
    "completed",
    "failed",
    "cancelled",
    "canceled",
}


@dataclass
class RepairValues:
    started_at: str | None
    completed_at: str | None
    created_at: str | None
    status: str | None
    failure_reason: str | None
    audit_note: str | None


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
        "--apply",
        action="store_true",
        help="Apply the repair. Without this flag, the script runs in dry-run mode.",
    )
    return parser.parse_args()


def normalize_datetime(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc

    return parsed.isoformat()


def validate_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in ALLOWED_STATUS_VALUES:
        allowed = ", ".join(sorted(ALLOWED_STATUS_VALUES))
        raise ValueError(f"Invalid status '{value}'. Allowed values: {allowed}")
    return normalized


def validate_values(values: RepairValues) -> RepairValues:
    started_at = normalize_datetime(values.started_at, "started_at")
    completed_at = normalize_datetime(values.completed_at, "completed_at")
    created_at = normalize_datetime(values.created_at, "created_at")
    status = validate_status(values.status)

    if started_at and completed_at:
        started_dt = datetime.fromisoformat(started_at)
        completed_dt = datetime.fromisoformat(completed_at)
        if completed_dt < started_dt:
            raise ValueError("completed_at cannot be earlier than started_at")

    return RepairValues(
        started_at=started_at,
        completed_at=completed_at,
        created_at=created_at,
        status=status,
        failure_reason=values.failure_reason,
        audit_note=values.audit_note,
    )


def load_archive_row(connection: sqlite3.Connection, archive_id: int) -> sqlite3.Row | None:
    query = """
    SELECT id, started_at, completed_at, created_at, status, failure_reason, notes
    FROM print_archives
    WHERE id = ?
    """
    return connection.execute(query, (archive_id,)).fetchone()


def build_audit_note(note: str) -> str:
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return f"[RUNTIME_REPAIR_V1] {timestamp} {note}"


def merge_notes(existing_notes: str | None, audit_note: str | None) -> str | None:
    if not audit_note:
        return existing_notes
    block = build_audit_note(audit_note)
    if not existing_notes:
        return block
    return f"{existing_notes}\n\n{block}"


def compute_updates(before: sqlite3.Row, values: RepairValues) -> tuple[dict[str, Any], dict[str, Any]]:
    update_fields: dict[str, Any] = {}
    after = {
        "started_at": before["started_at"],
        "completed_at": before["completed_at"],
        "created_at": before["created_at"],
        "status": before["status"],
        "failure_reason": before["failure_reason"],
        "notes": before["notes"],
    }

    for field in ("started_at", "completed_at", "created_at", "status", "failure_reason"):
        value = getattr(values, field)
        if value is not None and value != before[field]:
            update_fields[field] = value
            after[field] = value

    merged_notes = merge_notes(before["notes"], values.audit_note)
    if merged_notes != before["notes"]:
        update_fields["notes"] = merged_notes
        after["notes"] = merged_notes

    return update_fields, after


def apply_update(connection: sqlite3.Connection, archive_id: int, update_fields: dict[str, Any]) -> None:
    assignments = ", ".join(f"{field} = ?" for field in update_fields)
    values = list(update_fields.values())
    values.append(archive_id)
    connection.execute(f"UPDATE print_archives SET {assignments} WHERE id = ?", values)


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(json.dumps({"error": f"Database not found: {db_path}"}))
        return 1

    try:
        values = validate_values(
            RepairValues(
                started_at=args.started_at,
                completed_at=args.completed_at,
                created_at=args.created_at,
                status=args.status,
                failure_reason=args.failure_reason,
                audit_note=args.audit_note,
            )
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        before = load_archive_row(connection, args.archive_id)
        if before is None:
            print(json.dumps({"error": f"Archive ID {args.archive_id} not found"}))
            return 1

        update_fields, after = compute_updates(before, values)
        result = {
            "archive_id": args.archive_id,
            "applied": bool(args.apply),
            "changed": bool(update_fields),
            "before": {
                "started_at": before["started_at"],
                "completed_at": before["completed_at"],
                "created_at": before["created_at"],
                "status": before["status"],
                "failure_reason": before["failure_reason"],
                "notes": before["notes"],
            },
            "after": after,
            "updated_fields": sorted(update_fields.keys()),
        }

        if args.apply and update_fields:
            apply_update(connection, args.archive_id, update_fields)
            connection.commit()

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())