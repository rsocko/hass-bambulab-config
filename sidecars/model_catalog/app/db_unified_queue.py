"""Unified production queue schema operations.

This module provides CRUD helpers for:
- queue entries
- file units under queue entries
- plate units under file units
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .db_common import connect, utc_now_iso


@dataclass(frozen=True)
class UnifiedQueueEntry:
    queue_entry_id: str
    source_kind: str
    source_ref: str | None
    title: str
    state: str
    rank: int
    started_at: str | None
    completed_at: str | None
    blocked_reason: str | None
    copies_requested: int
    copies_completed: int
    selection_mode: str
    estimated_total_minutes: int | None
    duration_bucket: str
    ams_ready_score: int
    overnight_fit_score: int
    queue_notes: str | None
    last_archive_id: str | None
    last_attempt_outcome: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UnifiedQueueFileUnit:
    queue_entry_id: str
    file_unit_id: str
    file_id: str | None
    file_name: str
    selected: bool
    estimated_minutes: int | None
    filament_requirements: dict[str, object]
    archive_link_summary: dict[str, object]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UnifiedQueuePlateUnit:
    queue_entry_id: str
    file_unit_id: str
    plate_unit_id: str
    plate_key: str
    plate_name: str | None
    preview_image_path: str | None
    selected: bool
    state: str
    completed_by_archive_id: str | None
    completion_confidence: str | None
    attempt_count: int
    last_attempt_outcome: str | None
    estimated_minutes: int | None
    created_at: str
    updated_at: str


def _entry_from_row(row) -> UnifiedQueueEntry:
    return UnifiedQueueEntry(
        queue_entry_id=str(row["queue_entry_id"]),
        source_kind=str(row["source_kind"]),
        source_ref=str(row["source_ref"] or "").strip() or None,
        title=str(row["title"]),
        state=str(row["state"]),
        rank=int(row["rank"]),
        started_at=str(row["started_at"] or "").strip() or None,
        completed_at=str(row["completed_at"] or "").strip() or None,
        blocked_reason=str(row["blocked_reason"] or "").strip() or None,
        copies_requested=int(row["copies_requested"]),
        copies_completed=int(row["copies_completed"]),
        selection_mode=str(row["selection_mode"]),
        estimated_total_minutes=int(row["estimated_total_minutes"]) if row["estimated_total_minutes"] is not None else None,
        duration_bucket=str(row["duration_bucket"]),
        ams_ready_score=int(row["ams_ready_score"]),
        overnight_fit_score=int(row["overnight_fit_score"]),
        queue_notes=str(row["queue_notes"] or "").strip() or None,
        last_archive_id=str(row["last_archive_id"] or "").strip() or None,
        last_attempt_outcome=str(row["last_attempt_outcome"] or "").strip() or None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _file_unit_from_row(row) -> UnifiedQueueFileUnit:
    return UnifiedQueueFileUnit(
        queue_entry_id=str(row["queue_entry_id"]),
        file_unit_id=str(row["file_unit_id"]),
        file_id=str(row["file_id"] or "").strip() or None,
        file_name=str(row["file_name"]),
        selected=bool(int(row["selected"])),
        estimated_minutes=int(row["estimated_minutes"]) if row["estimated_minutes"] is not None else None,
        filament_requirements=json.loads(str(row["filament_requirements_json"] or "{}")),
        archive_link_summary=json.loads(str(row["archive_link_summary_json"] or "{}")),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _plate_unit_from_row(row) -> UnifiedQueuePlateUnit:
    return UnifiedQueuePlateUnit(
        queue_entry_id=str(row["queue_entry_id"]),
        file_unit_id=str(row["file_unit_id"]),
        plate_unit_id=str(row["plate_unit_id"]),
        plate_key=str(row["plate_key"]),
        plate_name=str(row["plate_name"] or "").strip() or None,
        preview_image_path=str(row["preview_image_path"] or "").strip() or None,
        selected=bool(int(row["selected"])),
        state=str(row["state"]),
        completed_by_archive_id=str(row["completed_by_archive_id"] or "").strip() or None,
        completion_confidence=str(row["completion_confidence"] or "").strip() or None,
        attempt_count=int(row["attempt_count"]),
        last_attempt_outcome=str(row["last_attempt_outcome"] or "").strip() or None,
        estimated_minutes=int(row["estimated_minutes"]) if row["estimated_minutes"] is not None else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def create_unified_queue_entry(
    *,
    db_path: Path,
    queue_entry_id: str,
    source_kind: str,
    source_ref: str | None,
    title: str,
    state: str = "todo",
    rank: int = 0,
    started_at: str | None = None,
    completed_at: str | None = None,
    blocked_reason: str | None = None,
    copies_requested: int = 1,
    copies_completed: int = 0,
    selection_mode: str = "all_files_all_plates",
    estimated_total_minutes: int | None = None,
    duration_bucket: str = "unknown",
    ams_ready_score: int = 0,
    overnight_fit_score: int = 0,
    queue_notes: str | None = None,
    last_archive_id: str | None = None,
    last_attempt_outcome: str | None = None,
) -> UnifiedQueueEntry:
    now = utc_now_iso()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO unified_queue_entries (
                queue_entry_id,
                source_kind,
                source_ref,
                title,
                state,
                rank,
                started_at,
                completed_at,
                blocked_reason,
                copies_requested,
                copies_completed,
                selection_mode,
                estimated_total_minutes,
                duration_bucket,
                ams_ready_score,
                overnight_fit_score,
                queue_notes,
                last_archive_id,
                last_attempt_outcome,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                queue_entry_id,
                source_kind,
                source_ref,
                title,
                state,
                rank,
                started_at,
                completed_at,
                blocked_reason,
                copies_requested,
                copies_completed,
                selection_mode,
                estimated_total_minutes,
                duration_bucket,
                ams_ready_score,
                overnight_fit_score,
                queue_notes,
                last_archive_id,
                last_attempt_outcome,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    created = read_unified_queue_entry(db_path=db_path, queue_entry_id=queue_entry_id)
    if created is None:
        raise RuntimeError("Failed to read created unified queue entry")
    return created


def read_unified_queue_entry(*, db_path: Path, queue_entry_id: str) -> UnifiedQueueEntry | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM unified_queue_entries WHERE queue_entry_id = ?",
            (queue_entry_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return _entry_from_row(row)


def list_unified_queue_entries(*, db_path: Path) -> list[UnifiedQueueEntry]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT * FROM unified_queue_entries ORDER BY rank ASC, created_at ASC",
        ).fetchall()
    finally:
        connection.close()
    return [_entry_from_row(row) for row in rows]


def update_unified_queue_entry(
    *,
    db_path: Path,
    queue_entry_id: str,
    source_ref: str | None = None,
    title: str | None = None,
    state: str | None = None,
    rank: int | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    blocked_reason: str | None = None,
    copies_requested: int | None = None,
    copies_completed: int | None = None,
    selection_mode: str | None = None,
    estimated_total_minutes: int | None = None,
    duration_bucket: str | None = None,
    ams_ready_score: int | None = None,
    overnight_fit_score: int | None = None,
    queue_notes: str | None = None,
    last_archive_id: str | None = None,
    last_attempt_outcome: str | None = None,
) -> UnifiedQueueEntry | None:
    updates: list[str] = []
    params: list[object] = []

    def _set(field: str, value: object | None) -> None:
        if value is None:
            return
        updates.append(f"{field} = ?")
        params.append(value)

    _set("source_ref", source_ref)
    _set("title", title)
    _set("state", state)
    _set("rank", rank)
    _set("started_at", started_at)
    _set("completed_at", completed_at)
    _set("blocked_reason", blocked_reason)
    _set("copies_requested", copies_requested)
    _set("copies_completed", copies_completed)
    _set("selection_mode", selection_mode)
    _set("estimated_total_minutes", estimated_total_minutes)
    _set("duration_bucket", duration_bucket)
    _set("ams_ready_score", ams_ready_score)
    _set("overnight_fit_score", overnight_fit_score)
    _set("queue_notes", queue_notes)
    _set("last_archive_id", last_archive_id)
    _set("last_attempt_outcome", last_attempt_outcome)

    if not updates:
        return read_unified_queue_entry(db_path=db_path, queue_entry_id=queue_entry_id)

    updates.append("updated_at = ?")
    params.append(utc_now_iso())
    params.append(queue_entry_id)

    connection = connect(db_path)
    try:
        cursor = connection.execute(
            f"UPDATE unified_queue_entries SET {', '.join(updates)} WHERE queue_entry_id = ?",
            tuple(params),
        )
        connection.commit()
    finally:
        connection.close()
    if cursor.rowcount == 0:
        return None
    return read_unified_queue_entry(db_path=db_path, queue_entry_id=queue_entry_id)


def delete_unified_queue_entry(*, db_path: Path, queue_entry_id: str) -> bool:
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            "DELETE FROM unified_queue_entries WHERE queue_entry_id = ?",
            (queue_entry_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def create_unified_queue_file_unit(
    *,
    db_path: Path,
    queue_entry_id: str,
    file_unit_id: str,
    file_name: str,
    file_id: str | None = None,
    selected: bool = True,
    estimated_minutes: int | None = None,
    filament_requirements: dict[str, object] | None = None,
    archive_link_summary: dict[str, object] | None = None,
) -> UnifiedQueueFileUnit:
    now = utc_now_iso()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO unified_queue_file_units (
                queue_entry_id,
                file_unit_id,
                file_id,
                file_name,
                selected,
                estimated_minutes,
                filament_requirements_json,
                archive_link_summary_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                queue_entry_id,
                file_unit_id,
                file_id,
                file_name,
                1 if selected else 0,
                estimated_minutes,
                json.dumps(filament_requirements or {}, separators=(",", ":")),
                json.dumps(archive_link_summary or {}, separators=(",", ":")),
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    created = read_unified_queue_file_unit(db_path=db_path, queue_entry_id=queue_entry_id, file_unit_id=file_unit_id)
    if created is None:
        raise RuntimeError("Failed to read created unified queue file unit")
    return created


def read_unified_queue_file_unit(*, db_path: Path, queue_entry_id: str, file_unit_id: str) -> UnifiedQueueFileUnit | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT *
            FROM unified_queue_file_units
            WHERE queue_entry_id = ? AND file_unit_id = ?
            """,
            (queue_entry_id, file_unit_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return _file_unit_from_row(row)


def list_unified_queue_file_units(*, db_path: Path, queue_entry_id: str) -> list[UnifiedQueueFileUnit]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM unified_queue_file_units
            WHERE queue_entry_id = ?
            ORDER BY created_at ASC, file_unit_id ASC
            """,
            (queue_entry_id,),
        ).fetchall()
    finally:
        connection.close()
    return [_file_unit_from_row(row) for row in rows]


def update_unified_queue_file_unit(
    *,
    db_path: Path,
    queue_entry_id: str,
    file_unit_id: str,
    file_id: str | None = None,
    file_name: str | None = None,
    selected: bool | None = None,
    estimated_minutes: int | None = None,
    filament_requirements: dict[str, object] | None = None,
    archive_link_summary: dict[str, object] | None = None,
) -> UnifiedQueueFileUnit | None:
    updates: list[str] = []
    params: list[object] = []

    def _set(field: str, value: object | None) -> None:
        if value is None:
            return
        updates.append(f"{field} = ?")
        params.append(value)

    _set("file_id", file_id)
    _set("file_name", file_name)
    if selected is not None:
        _set("selected", 1 if selected else 0)
    _set("estimated_minutes", estimated_minutes)
    if filament_requirements is not None:
        _set("filament_requirements_json", json.dumps(filament_requirements, separators=(",", ":")))
    if archive_link_summary is not None:
        _set("archive_link_summary_json", json.dumps(archive_link_summary, separators=(",", ":")))

    if not updates:
        return read_unified_queue_file_unit(db_path=db_path, queue_entry_id=queue_entry_id, file_unit_id=file_unit_id)

    updates.append("updated_at = ?")
    params.append(utc_now_iso())
    params.extend((queue_entry_id, file_unit_id))

    connection = connect(db_path)
    try:
        cursor = connection.execute(
            (
                "UPDATE unified_queue_file_units "
                f"SET {', '.join(updates)} "
                "WHERE queue_entry_id = ? AND file_unit_id = ?"
            ),
            tuple(params),
        )
        connection.commit()
    finally:
        connection.close()
    if cursor.rowcount == 0:
        return None
    return read_unified_queue_file_unit(db_path=db_path, queue_entry_id=queue_entry_id, file_unit_id=file_unit_id)


def delete_unified_queue_file_unit(*, db_path: Path, queue_entry_id: str, file_unit_id: str) -> bool:
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            "DELETE FROM unified_queue_file_units WHERE queue_entry_id = ? AND file_unit_id = ?",
            (queue_entry_id, file_unit_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def create_unified_queue_plate_unit(
    *,
    db_path: Path,
    queue_entry_id: str,
    file_unit_id: str,
    plate_unit_id: str,
    plate_key: str,
    plate_name: str | None = None,
    preview_image_path: str | None = None,
    selected: bool = True,
    state: str = "pending",
    completed_by_archive_id: str | None = None,
    completion_confidence: str | None = None,
    attempt_count: int = 0,
    last_attempt_outcome: str | None = None,
    estimated_minutes: int | None = None,
) -> UnifiedQueuePlateUnit:
    now = utc_now_iso()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO unified_queue_plate_units (
                queue_entry_id,
                file_unit_id,
                plate_unit_id,
                plate_key,
                plate_name,
                preview_image_path,
                selected,
                state,
                completed_by_archive_id,
                completion_confidence,
                attempt_count,
                last_attempt_outcome,
                estimated_minutes,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                queue_entry_id,
                file_unit_id,
                plate_unit_id,
                plate_key,
                plate_name,
                preview_image_path,
                1 if selected else 0,
                state,
                completed_by_archive_id,
                completion_confidence,
                attempt_count,
                last_attempt_outcome,
                estimated_minutes,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    created = read_unified_queue_plate_unit(
        db_path=db_path,
        queue_entry_id=queue_entry_id,
        file_unit_id=file_unit_id,
        plate_unit_id=plate_unit_id,
    )
    if created is None:
        raise RuntimeError("Failed to read created unified queue plate unit")
    return created


def read_unified_queue_plate_unit(
    *,
    db_path: Path,
    queue_entry_id: str,
    file_unit_id: str,
    plate_unit_id: str,
) -> UnifiedQueuePlateUnit | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT *
            FROM unified_queue_plate_units
            WHERE queue_entry_id = ? AND file_unit_id = ? AND plate_unit_id = ?
            """,
            (queue_entry_id, file_unit_id, plate_unit_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return _plate_unit_from_row(row)


def list_unified_queue_plate_units(*, db_path: Path, queue_entry_id: str, file_unit_id: str) -> list[UnifiedQueuePlateUnit]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM unified_queue_plate_units
            WHERE queue_entry_id = ? AND file_unit_id = ?
            ORDER BY created_at ASC, plate_unit_id ASC
            """,
            (queue_entry_id, file_unit_id),
        ).fetchall()
    finally:
        connection.close()
    return [_plate_unit_from_row(row) for row in rows]


def update_unified_queue_plate_unit(
    *,
    db_path: Path,
    queue_entry_id: str,
    file_unit_id: str,
    plate_unit_id: str,
    plate_key: str | None = None,
    plate_name: str | None = None,
    preview_image_path: str | None = None,
    selected: bool | None = None,
    state: str | None = None,
    completed_by_archive_id: str | None = None,
    completion_confidence: str | None = None,
    attempt_count: int | None = None,
    last_attempt_outcome: str | None = None,
    estimated_minutes: int | None = None,
) -> UnifiedQueuePlateUnit | None:
    updates: list[str] = []
    params: list[object] = []

    def _set(field: str, value: object | None) -> None:
        if value is None:
            return
        updates.append(f"{field} = ?")
        params.append(value)

    _set("plate_key", plate_key)
    _set("plate_name", plate_name)
    _set("preview_image_path", preview_image_path)
    if selected is not None:
        _set("selected", 1 if selected else 0)
    _set("state", state)
    _set("completed_by_archive_id", completed_by_archive_id)
    _set("completion_confidence", completion_confidence)
    _set("attempt_count", attempt_count)
    _set("last_attempt_outcome", last_attempt_outcome)
    _set("estimated_minutes", estimated_minutes)

    if not updates:
        return read_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=queue_entry_id,
            file_unit_id=file_unit_id,
            plate_unit_id=plate_unit_id,
        )

    updates.append("updated_at = ?")
    params.append(utc_now_iso())
    params.extend((queue_entry_id, file_unit_id, plate_unit_id))

    connection = connect(db_path)
    try:
        cursor = connection.execute(
            (
                "UPDATE unified_queue_plate_units "
                f"SET {', '.join(updates)} "
                "WHERE queue_entry_id = ? AND file_unit_id = ? AND plate_unit_id = ?"
            ),
            tuple(params),
        )
        connection.commit()
    finally:
        connection.close()
    if cursor.rowcount == 0:
        return None
    return read_unified_queue_plate_unit(
        db_path=db_path,
        queue_entry_id=queue_entry_id,
        file_unit_id=file_unit_id,
        plate_unit_id=plate_unit_id,
    )


def delete_unified_queue_plate_unit(*, db_path: Path, queue_entry_id: str, file_unit_id: str, plate_unit_id: str) -> bool:
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            DELETE FROM unified_queue_plate_units
            WHERE queue_entry_id = ? AND file_unit_id = ? AND plate_unit_id = ?
            """,
            (queue_entry_id, file_unit_id, plate_unit_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def create_unified_queue_transition_audit(
    *,
    db_path: Path,
    queue_entry_id: str,
    from_state: str,
    to_state: str,
    actor: str | None = None,
    reason: str | None = None,
) -> int:
    """Record an immutable state transition event for queue entries."""
    now = utc_now_iso()
    payload = {
        "queue_entry_id": queue_entry_id,
        "from_state": from_state,
        "to_state": to_state,
        "actor": actor,
        "reason": reason,
        "transitioned_at": now,
    }
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_events (
                event_type,
                entity_type,
                entity_id,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "unified_queue_state_transition",
                "unified_queue_entry",
                queue_entry_id,
                json.dumps(payload, separators=(",", ":")),
                now,
            ),
        )
        event_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        connection.commit()
        return event_id
    finally:
        connection.close()


def _slugify_legacy_source_ref(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip()).strip("-").lower()
    return text or "legacy"


def _legacy_status_to_unified_state(value: object | None) -> str | None:
    status = str(value or "").strip().lower()
    if status == "queued":
        return "todo"
    if status == "done":
        return "done"
    if status in {"", "none", "null"}:
        return None
    return None


def _legacy_priority_to_int(value: object | None) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def migrate_legacy_catalog_queue_fields(*, db_path: Path, actor: str = "migration") -> dict[str, object]:
    """Migrate legacy model_catalog custom queue fields into unified queue entries.

    Source fields:
    - to_print_status
    - to_print_priority
    """
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT entity_id, field_key, field_value_json
            FROM model_catalog_custom_fields
            WHERE entity_type = 'manyfold_model'
              AND field_namespace = 'model_catalog'
              AND field_key IN ('to_print_status', 'to_print_priority')
            ORDER BY entity_id ASC
            """
        ).fetchall()

        by_model: dict[str, dict[str, object]] = {}
        for row in rows:
            entity_id = str(row["entity_id"])
            field_key = str(row["field_key"])
            try:
                value = json.loads(str(row["field_value_json"]))
            except json.JSONDecodeError:
                value = str(row["field_value_json"])
            bucket = by_model.setdefault(entity_id, {})
            bucket[field_key] = value

        existing = connection.execute(
            """
            SELECT source_ref
            FROM unified_queue_entries
            WHERE source_kind = 'catalog_model'
            """
        ).fetchall()
        existing_refs = {str(row["source_ref"] or "").strip() for row in existing}

        candidates: list[tuple[str, str, int]] = []
        skipped_none = 0
        for entity_id, fields in by_model.items():
            state = _legacy_status_to_unified_state(fields.get("to_print_status"))
            if state is None:
                skipped_none += 1
                continue
            priority = _legacy_priority_to_int(fields.get("to_print_priority"))
            candidates.append((entity_id, state, priority))

        candidates.sort(key=lambda item: (-item[2], item[0]))

        migrated_count = 0
        skipped_existing = 0
        audit_ids: list[int] = []
        now = utc_now_iso()
        for index, (source_ref, unified_state, _priority) in enumerate(candidates, start=1):
            if source_ref in existing_refs:
                skipped_existing += 1
                continue

            queue_entry_id = f"uqe-legacy-{_slugify_legacy_source_ref(source_ref)}"
            collision = connection.execute(
                "SELECT 1 FROM unified_queue_entries WHERE queue_entry_id = ?",
                (queue_entry_id,),
            ).fetchone()
            if collision is not None:
                queue_entry_id = f"{queue_entry_id}-{index}"

            title = f"Legacy Catalog: {source_ref}"
            connection.execute(
                """
                INSERT INTO unified_queue_entries (
                    queue_entry_id,
                    source_kind,
                    source_ref,
                    title,
                    state,
                    rank,
                    copies_requested,
                    copies_completed,
                    selection_mode,
                    duration_bucket,
                    ams_ready_score,
                    overnight_fit_score,
                    queue_notes,
                    created_at,
                    updated_at
                ) VALUES (?, 'catalog_model', ?, ?, ?, ?, 1, 0, 'all_files_all_plates', 'unknown', 0, 0, ?, ?, ?)
                """,
                (
                    queue_entry_id,
                    source_ref,
                    title,
                    unified_state,
                    index,
                    "Migrated from legacy model_catalog queue fields",
                    now,
                    now,
                ),
            )

            payload = {
                "queue_entry_id": queue_entry_id,
                "source_ref": source_ref,
                "from": {
                    "to_print_status": by_model.get(source_ref, {}).get("to_print_status"),
                    "to_print_priority": by_model.get(source_ref, {}).get("to_print_priority"),
                },
                "to": {
                    "state": unified_state,
                    "rank": index,
                },
                "actor": actor,
                "migrated_at": now,
            }
            connection.execute(
                """
                INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
                VALUES ('unified_queue_legacy_migration', 'unified_queue_entry', ?, ?, ?)
                """,
                (queue_entry_id, json.dumps(payload, separators=(",", ":")), now),
            )
            audit_ids.append(int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]))
            existing_refs.add(source_ref)
            migrated_count += 1

        connection.commit()
        return {
            "success": True,
            "legacy_models_detected": len(by_model),
            "candidates": len(candidates),
            "migrated": migrated_count,
            "skipped_existing": skipped_existing,
            "skipped_none": skipped_none,
            "audit_event_count": len(audit_ids),
            "audit_event_ids": audit_ids,
        }
    finally:
        connection.close()