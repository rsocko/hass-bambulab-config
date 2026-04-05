"""Shared repair logic for Bambuddy archive runtime correction."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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

RUNTIME_FIELDS = (
    "started_at",
    "completed_at",
    "created_at",
    "status",
    "failure_reason",
)


@dataclass
class RepairValues:
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    status: str | None = None
    failure_reason: str | None = None
    audit_note: str | None = None


@dataclass
class RepairResult:
    archive_id: int
    applied: bool
    changed: bool
    before: dict[str, Any]
    after: dict[str, Any]
    updated_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    normalized = RepairValues(
        started_at=normalize_datetime(values.started_at, "started_at"),
        completed_at=normalize_datetime(values.completed_at, "completed_at"),
        created_at=normalize_datetime(values.created_at, "created_at"),
        status=validate_status(values.status),
        failure_reason=values.failure_reason,
        audit_note=values.audit_note,
    )

    if normalized.started_at and normalized.completed_at:
        started_dt = datetime.fromisoformat(normalized.started_at)
        completed_dt = datetime.fromisoformat(normalized.completed_at)
        if completed_dt < started_dt:
            raise ValueError("completed_at cannot be earlier than started_at")

    return normalized


def ensure_database_exists(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")


def build_audit_note(note: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"[RUNTIME_REPAIR_V1] {timestamp} {note}"


def merge_notes(existing_notes: str | None, audit_note: str | None) -> str | None:
    if not audit_note:
        return existing_notes

    block = build_audit_note(audit_note)
    if not existing_notes:
        return block
    return f"{existing_notes}\n\n{block}"


def load_archive_row(connection: sqlite3.Connection, archive_id: int) -> sqlite3.Row | None:
    query = """
    SELECT id, started_at, completed_at, created_at, status, failure_reason, notes
    FROM print_archives
    WHERE id = ?
    """
    return connection.execute(query, (archive_id,)).fetchone()


def _row_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "status": row["status"],
        "failure_reason": row["failure_reason"],
        "notes": row["notes"],
    }


def compute_updates(before: sqlite3.Row, values: RepairValues) -> tuple[dict[str, Any], dict[str, Any]]:
    update_fields: dict[str, Any] = {}
    after = _row_snapshot(before)

    for field in RUNTIME_FIELDS:
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


def backup_database(db_path: Path, backup_path: Path | None = None) -> Path:
    backup_target = backup_path or db_path.with_name(
        f"{db_path.stem}.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}{db_path.suffix}"
    )

    source = sqlite3.connect(db_path)
    destination = sqlite3.connect(backup_target)
    try:
        source.backup(destination)
    finally:
        source.close()
        destination.close()

    return backup_target


def repair_archive_runtime(
    db_path: Path,
    archive_id: int,
    values: RepairValues,
    apply: bool = False,
) -> RepairResult:
    ensure_database_exists(db_path)
    validated_values = validate_values(values)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        before = load_archive_row(connection, archive_id)
        if before is None:
            raise ValueError(f"Archive ID {archive_id} not found")

        update_fields, after = compute_updates(before, validated_values)
        if apply and update_fields:
            apply_update(connection, archive_id, update_fields)
            connection.commit()

        return RepairResult(
            archive_id=archive_id,
            applied=apply,
            changed=bool(update_fields),
            before=_row_snapshot(before),
            after=after,
            updated_fields=sorted(update_fields.keys()),
        )
    finally:
        connection.close()


def result_to_json(result: RepairResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)