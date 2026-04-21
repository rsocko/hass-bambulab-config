from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import ArchiveMetadataCorrectionRequest, ArchiveMetadataCorrectionResponse
from tools.bambuddy.runtime_repair_core import ensure_database_exists, normalize_datetime, validate_status


AUDIT_MARKER = "[ARCHIVE_METADATA_CORRECTION_V1]"
REVISION_FIELDS = ("started_at", "completed_at", "created_at", "status", "failure_reason", "notes")
EDITABLE_FIELDS = ("started_at", "completed_at", "created_at", "status", "failure_reason")


@dataclass(slots=True)
class MetadataRow:
    archive_id: int
    started_at: str | None
    completed_at: str | None
    created_at: str | None
    status: str | None
    failure_reason: str | None
    notes: str | None

    def snapshot(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "notes": self.notes,
        }


def _load_row(connection: sqlite3.Connection, archive_id: int) -> MetadataRow:
    row = connection.execute(
        """
        SELECT id, started_at, completed_at, created_at, status, failure_reason, notes
        FROM archives
        WHERE id = ?
        """,
        (archive_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Archive {archive_id} was not found")
    return MetadataRow(
        archive_id=int(row[0]),
        started_at=row[1],
        completed_at=row[2],
        created_at=row[3],
        status=row[4],
        failure_reason=row[5],
        notes=row[6],
    )


def compute_archive_metadata_revision(snapshot: dict[str, Any]) -> str:
    payload = {field: snapshot.get(field) for field in REVISION_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    normalized = normalize_datetime(value)
    if not normalized:
        return None
    return datetime.fromisoformat(normalized)


def _duration_seconds(started_at: str | None, completed_at: str | None) -> int | None:
    start_value = _parse_iso(started_at)
    end_value = _parse_iso(completed_at)
    if start_value is None or end_value is None:
        return None
    delta = int((end_value - start_value).total_seconds())
    return delta if delta >= 0 else None


def _iso_day(value: str | None) -> str:
    normalized = str(value or "").strip()
    return normalized[:10] if len(normalized) >= 10 else normalized


def _append_audit_note(existing_notes: str | None, *, reason: str, before: dict[str, Any], after: dict[str, Any], request_id: str, trigger_source: str) -> str:
    payload = {
        "request_id": request_id,
        "trigger_source": trigger_source,
        "reason": reason,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "before": {field: before.get(field) for field in EDITABLE_FIELDS},
        "after": {field: after.get(field) for field in EDITABLE_FIELDS},
    }
    note_block = AUDIT_MARKER + "\n" + json.dumps(payload, sort_keys=True, ensure_ascii=True)
    base_notes = str(existing_notes or "").rstrip()
    return note_block if not base_notes else base_notes + "\n\n" + note_block


def _build_warnings(before: dict[str, Any], after: dict[str, Any], updated_fields: list[str]) -> list[str]:
    warnings: list[str] = []
    if not updated_fields:
        warnings.append("No editable fields changed; nothing will be written.")
        return warnings
    if "created_at" in updated_fields:
        warnings.append("Changing created_at can move this archive to a different day bucket in browser views and statistics.")
    if "started_at" in updated_fields or "completed_at" in updated_fields:
        warnings.append("Changing started_at or completed_at updates the effective runtime used by print-history views.")
    if "status" in updated_fields or "failure_reason" in updated_fields:
        warnings.append("Changing status or failure_reason changes failure analytics and status-based filters.")
    if before.get("status") != after.get("status") and str(after.get("status") or "").strip().lower() == "failed" and not str(after.get("failure_reason") or "").strip():
        warnings.append("Failed status is set without a failure_reason.")
    return warnings


def _build_derived_impacts(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_duration = _duration_seconds(before.get("started_at"), before.get("completed_at"))
    after_duration = _duration_seconds(after.get("started_at"), after.get("completed_at"))
    before_day = _iso_day(before.get("created_at"))
    after_day = _iso_day(after.get("created_at"))
    return {
        "duration_seconds_before": before_duration,
        "duration_seconds_after": after_duration,
        "duration_seconds_changed": before_duration != after_duration,
        "created_day_before": before_day,
        "created_day_after": after_day,
        "created_day_changed": before_day != after_day,
        "status_changed": before.get("status") != after.get("status"),
        "failure_reason_changed": before.get("failure_reason") != after.get("failure_reason"),
    }


def correct_archive_metadata(db_path: Path, request: ArchiveMetadataCorrectionRequest) -> ArchiveMetadataCorrectionResponse:
    ensure_database_exists(db_path)
    request_id = str(request.request_id or uuid4()).strip()
    requested_at = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(db_path)
    try:
        row = _load_row(connection, int(request.archive_id))
        before = row.snapshot()
        current_revision = compute_archive_metadata_revision(before)
        expected_revision = str(request.expected_archive_revision or "").strip()
        if expected_revision and expected_revision != current_revision:
            raise ValueError("Archive metadata changed since this correction form was opened. Refresh metadata and preview again.")

        requested_fields = request.fields.model_dump(exclude_unset=True)
        after = dict(before)
        updated_fields: list[str] = []
        for field_name in EDITABLE_FIELDS:
            if field_name not in requested_fields:
                continue
            raw_value = requested_fields.get(field_name)
            if field_name in {"started_at", "completed_at", "created_at"}:
                normalized_value = normalize_datetime(raw_value)
                if not normalized_value:
                    raise ValueError(f"{field_name} must be a valid ISO datetime")
            elif field_name == "status":
                normalized_value = validate_status(raw_value)
                if not normalized_value:
                    raise ValueError("status must be one of printing, completed, failed, or cancelled")
            else:
                normalized_value = str(raw_value or "").strip() or None
            if after.get(field_name) != normalized_value:
                after[field_name] = normalized_value
                updated_fields.append(field_name)

        warnings = _build_warnings(before, after, updated_fields)
        derived_impacts = _build_derived_impacts(before, after)
        correction_id = request_id
        archive_revision = compute_archive_metadata_revision({**after, "notes": before.get("notes")})
        applied_at: str | None = None

        if not request.dry_run and updated_fields:
            after_notes = _append_audit_note(
                before.get("notes"),
                reason=request.reason,
                before=before,
                after=after,
                request_id=request_id,
                trigger_source=request.trigger_source,
            )
            assignments = [f"{field_name} = ?" for field_name in updated_fields]
            values = [after[field_name] for field_name in updated_fields]
            assignments.append("notes = ?")
            values.append(after_notes)
            values.append(int(request.archive_id))
            connection.execute(f"UPDATE archives SET {', '.join(assignments)} WHERE id = ?", values)
            connection.commit()
            after["notes"] = after_notes
            applied_at = datetime.now(timezone.utc).isoformat()
            archive_revision = compute_archive_metadata_revision(after)

        return ArchiveMetadataCorrectionResponse(
            archive_id=int(request.archive_id),
            applied=not request.dry_run and bool(updated_fields),
            changed=bool(updated_fields),
            correction_id=correction_id,
            request_id=request_id,
            requested_at=requested_at,
            applied_at=applied_at,
            before={field: before.get(field) for field in EDITABLE_FIELDS},
            after={field: after.get(field) for field in EDITABLE_FIELDS},
            updated_fields=updated_fields,
            warnings=warnings,
            derived_impacts=derived_impacts,
            archive_revision=archive_revision,
        )
    finally:
        connection.close()