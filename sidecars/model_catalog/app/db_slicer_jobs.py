"""Slicer job CRUD operations (Workstream B / Slice 2).

Provides persistence for ``model_catalog_print_history_jobs`` rows that
represent operator-initiated slicer workflows.  Each function opens and
closes its own connection following the project convention in
``db_common.py``.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db_common import connect, utc_now_iso


# ---------------------------------------------------------------------------
# Domain dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlicerJob:
    """Read-only projection of a ``model_catalog_print_history_jobs`` row."""

    id: int
    job_id: str
    workflow_kind: str
    source_kind: str
    source_ref: str | None
    local_model_id: str | None
    working_file_path: str | None
    archive_intent: str
    status: str
    requested_print_started_at: str | None
    requested_print_completed_at: str | None
    requested_print_timezone: str | None
    date_override_strategy: str
    target_archive_id: int | None
    created_archive_id: int | None
    selected_file_path: str | None
    selected_plate_key: str | None
    selected_plate_index: int | None
    source_file_name: str | None
    source_sha256: str | None
    sliced_output_path: str | None
    sliced_output_sha256: str | None
    worker_provider: str | None
    worker_job_id: str | None
    attach_source_after_create: bool
    validation_warnings: list[Any]
    overrides: dict[str, Any]
    commit_request: dict[str, Any]
    result_summary: dict[str, Any]
    last_error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


# ---------------------------------------------------------------------------
# Status lifecycle
# ---------------------------------------------------------------------------

VALID_STATUSES: set[str] = {
    "draft",
    "pending_validation",
    "validated",
    "slicing",
    "sliced",
    "committing",
    "committed",
    "failed",
    "cancelled",
}

VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_validation", "cancelled", "failed"},
    "pending_validation": {"validated", "draft", "failed"},
    "validated": {"slicing", "draft", "cancelled", "failed"},
    "slicing": {"sliced", "failed"},
    "sliced": {"committing", "cancelled", "failed"},
    "committing": {"committed", "failed"},
    "committed": set(),
    "failed": {"draft"},
    "cancelled": {"draft"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_job_id() -> str:
    """Generate a short unique job identifier."""
    return uuid.uuid4().hex[:12]


def _row_to_slicer_job(row: Any) -> SlicerJob:
    """Convert a sqlite3.Row to a SlicerJob dataclass."""
    return SlicerJob(
        id=int(row["id"]),
        job_id=str(row["job_id"]),
        workflow_kind=str(row["workflow_kind"]),
        source_kind=str(row["source_kind"]),
        source_ref=row["source_ref"],
        local_model_id=row["local_model_id"],
        working_file_path=row["working_file_path"],
        archive_intent=str(row["archive_intent"]),
        status=str(row["status"]),
        requested_print_started_at=row["requested_print_started_at"],
        requested_print_completed_at=row["requested_print_completed_at"],
        requested_print_timezone=row["requested_print_timezone"],
        date_override_strategy=str(row["date_override_strategy"]),
        target_archive_id=int(row["target_archive_id"]) if row["target_archive_id"] is not None else None,
        created_archive_id=int(row["created_archive_id"]) if row["created_archive_id"] is not None else None,
        selected_file_path=row["selected_file_path"],
        selected_plate_key=row["selected_plate_key"],
        selected_plate_index=int(row["selected_plate_index"]) if row["selected_plate_index"] is not None else None,
        source_file_name=row["source_file_name"],
        source_sha256=row["source_sha256"],
        sliced_output_path=row["sliced_output_path"],
        sliced_output_sha256=row["sliced_output_sha256"],
        worker_provider=row["worker_provider"],
        worker_job_id=row["worker_job_id"],
        attach_source_after_create=bool(row["attach_source_after_create"]),
        validation_warnings=json.loads(row["validation_warnings_json"] or "[]"),
        overrides=json.loads(row["overrides_json"] or "{}"),
        commit_request=json.loads(row["commit_request_json"] or "{}"),
        result_summary=json.loads(row["result_summary_json"] or "{}"),
        last_error=row["last_error"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=row["completed_at"],
    )


def _slicer_job_to_dict(job: SlicerJob) -> dict[str, Any]:
    """Serialize a SlicerJob to a JSON-safe dict."""
    return {
        "id": job.id,
        "job_id": job.job_id,
        "workflow_kind": job.workflow_kind,
        "source_kind": job.source_kind,
        "source_ref": job.source_ref,
        "local_model_id": job.local_model_id,
        "working_file_path": job.working_file_path,
        "archive_intent": job.archive_intent,
        "status": job.status,
        "requested_print_started_at": job.requested_print_started_at,
        "requested_print_completed_at": job.requested_print_completed_at,
        "requested_print_timezone": job.requested_print_timezone,
        "date_override_strategy": job.date_override_strategy,
        "target_archive_id": job.target_archive_id,
        "created_archive_id": job.created_archive_id,
        "selected_file_path": job.selected_file_path,
        "selected_plate_key": job.selected_plate_key,
        "selected_plate_index": job.selected_plate_index,
        "source_file_name": job.source_file_name,
        "source_sha256": job.source_sha256,
        "sliced_output_path": job.sliced_output_path,
        "sliced_output_sha256": job.sliced_output_sha256,
        "worker_provider": job.worker_provider,
        "worker_job_id": job.worker_job_id,
        "attach_source_after_create": job.attach_source_after_create,
        "validation_warnings": job.validation_warnings,
        "overrides": job.overrides,
        "commit_request": job.commit_request,
        "result_summary": job.result_summary,
        "last_error": job.last_error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def create_slicer_job(
    *,
    db_path: Path,
    source_kind: str,
    archive_intent: str,
    workflow_kind: str = "historical_backfill",
    source_ref: str | None = None,
    local_model_id: str | None = None,
    working_file_path: str | None = None,
    requested_print_started_at: str | None = None,
    requested_print_completed_at: str | None = None,
    requested_print_timezone: str | None = None,
    date_override_strategy: str = "operator_supplied",
    selected_file_path: str | None = None,
    selected_plate_key: str | None = None,
    selected_plate_index: int | None = None,
    source_file_name: str | None = None,
    attach_source_after_create: bool = False,
    overrides: dict[str, Any] | None = None,
) -> SlicerJob:
    """Create a new slicer job in ``draft`` status."""
    job_id = _generate_job_id()
    now = utc_now_iso()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_print_history_jobs (
                job_id, workflow_kind, source_kind, source_ref,
                local_model_id, working_file_path, archive_intent,
                status,
                requested_print_started_at, requested_print_completed_at,
                requested_print_timezone, date_override_strategy,
                selected_file_path, selected_plate_key, selected_plate_index,
                source_file_name,
                attach_source_after_create,
                overrides_json,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                'draft',
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?,
                ?,
                ?,
                ?, ?
            )
            """,
            (
                job_id,
                workflow_kind,
                source_kind,
                source_ref,
                local_model_id,
                working_file_path,
                archive_intent,
                requested_print_started_at,
                requested_print_completed_at,
                requested_print_timezone,
                date_override_strategy,
                selected_file_path,
                selected_plate_key,
                selected_plate_index,
                source_file_name,
                1 if attach_source_after_create else 0,
                json.dumps(overrides or {}),
                now,
                now,
            ),
        )
        connection.commit()
        job = read_slicer_job(db_path=db_path, job_id=job_id)
        if job is None:
            raise RuntimeError(f"Failed to read created slicer job {job_id}")
        return job
    finally:
        connection.close()


def read_slicer_job(*, db_path: Path, job_id: str) -> SlicerJob | None:
    """Read a single slicer job by its unique ``job_id``."""
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM model_catalog_print_history_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        return _row_to_slicer_job(row)
    finally:
        connection.close()


def list_slicer_jobs(
    *,
    db_path: Path,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    source_kind: str | None = None,
) -> tuple[list[SlicerJob], int]:
    """List slicer jobs with pagination and optional filters.

    Returns ``(jobs, total_count)``.
    """
    connection = connect(db_path)
    try:
        where_clauses: list[str] = []
        params: list[Any] = []

        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if source_kind:
            where_clauses.append("source_kind = ?")
            params.append(source_kind)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_row = connection.execute(
            f"SELECT COUNT(*) AS cnt FROM model_catalog_print_history_jobs{where_sql}",
            params,
        ).fetchone()
        total = int(count_row["cnt"] if count_row else 0)

        rows = connection.execute(
            f"""
            SELECT * FROM model_catalog_print_history_jobs{where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        return [_row_to_slicer_job(r) for r in rows], total
    finally:
        connection.close()


def update_slicer_job(
    *,
    db_path: Path,
    job_id: str,
    source_ref: str | None = None,
    local_model_id: str | None = None,
    working_file_path: str | None = None,
    requested_print_started_at: str | None = None,
    requested_print_completed_at: str | None = None,
    requested_print_timezone: str | None = None,
    date_override_strategy: str | None = None,
    selected_file_path: str | None = None,
    selected_plate_key: str | None = None,
    selected_plate_index: int | None = None,
    source_file_name: str | None = None,
    attach_source_after_create: bool | None = None,
    overrides: dict[str, Any] | None = None,
) -> SlicerJob | None:
    """Update mutable fields on a draft slicer job.

    Only jobs in ``draft`` status can be updated through this function.
    Returns ``None`` if the job does not exist.
    Raises ``ValueError`` if the job is not in ``draft`` status.
    """
    existing = read_slicer_job(db_path=db_path, job_id=job_id)
    if existing is None:
        return None
    if existing.status != "draft":
        raise ValueError(f"Cannot update job {job_id}: status is '{existing.status}', expected 'draft'")

    sets: list[str] = []
    params: list[Any] = []

    _UNSET = object()
    field_map: list[tuple[str, Any]] = [
        ("source_ref", source_ref),
        ("local_model_id", local_model_id),
        ("working_file_path", working_file_path),
        ("requested_print_started_at", requested_print_started_at),
        ("requested_print_completed_at", requested_print_completed_at),
        ("requested_print_timezone", requested_print_timezone),
        ("date_override_strategy", date_override_strategy),
        ("selected_file_path", selected_file_path),
        ("selected_plate_key", selected_plate_key),
        ("selected_plate_index", selected_plate_index),
        ("source_file_name", source_file_name),
    ]
    for col, val in field_map:
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)

    if attach_source_after_create is not None:
        sets.append("attach_source_after_create = ?")
        params.append(1 if attach_source_after_create else 0)

    if overrides is not None:
        sets.append("overrides_json = ?")
        params.append(json.dumps(overrides))

    if not sets:
        return existing

    sets.append("updated_at = ?")
    params.append(utc_now_iso())
    params.append(job_id)

    connection = connect(db_path)
    try:
        connection.execute(
            f"UPDATE model_catalog_print_history_jobs SET {', '.join(sets)} WHERE job_id = ?",
            params,
        )
        connection.commit()
    finally:
        connection.close()

    return read_slicer_job(db_path=db_path, job_id=job_id)


def transition_slicer_job(
    *,
    db_path: Path,
    job_id: str,
    new_status: str,
    last_error: str | None = None,
    validation_warnings: list[Any] | None = None,
    worker_provider: str | None = None,
    worker_job_id: str | None = None,
    sliced_output_path: str | None = None,
    sliced_output_sha256: str | None = None,
    source_sha256: str | None = None,
    created_archive_id: int | None = None,
    commit_request: dict[str, Any] | None = None,
    result_summary: dict[str, Any] | None = None,
) -> SlicerJob:
    """Transition a slicer job to a new status with optional payload.

    Validates the transition against ``VALID_STATUS_TRANSITIONS``.
    Raises ``ValueError`` on invalid transitions or missing jobs.
    """
    existing = read_slicer_job(db_path=db_path, job_id=job_id)
    if existing is None:
        raise ValueError(f"Slicer job not found: {job_id}")

    allowed = VALID_STATUS_TRANSITIONS.get(existing.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {existing.status!r} → {new_status!r} "
            f"(allowed: {sorted(allowed)})"
        )

    sets: list[str] = ["status = ?", "updated_at = ?"]
    now = utc_now_iso()
    params: list[Any] = [new_status, now]

    if last_error is not None:
        sets.append("last_error = ?")
        params.append(last_error)
    elif new_status not in ("failed",):
        # Clear error on non-failure transitions
        sets.append("last_error = NULL")

    if validation_warnings is not None:
        sets.append("validation_warnings_json = ?")
        params.append(json.dumps(validation_warnings))

    if worker_provider is not None:
        sets.append("worker_provider = ?")
        params.append(worker_provider)

    if worker_job_id is not None:
        sets.append("worker_job_id = ?")
        params.append(worker_job_id)

    if sliced_output_path is not None:
        sets.append("sliced_output_path = ?")
        params.append(sliced_output_path)

    if sliced_output_sha256 is not None:
        sets.append("sliced_output_sha256 = ?")
        params.append(sliced_output_sha256)

    if source_sha256 is not None:
        sets.append("source_sha256 = ?")
        params.append(source_sha256)

    if created_archive_id is not None:
        sets.append("created_archive_id = ?")
        params.append(created_archive_id)

    if commit_request is not None:
        sets.append("commit_request_json = ?")
        params.append(json.dumps(commit_request))

    if result_summary is not None:
        sets.append("result_summary_json = ?")
        params.append(json.dumps(result_summary))

    # Set completed_at on terminal statuses
    if new_status in ("committed", "failed", "cancelled"):
        sets.append("completed_at = ?")
        params.append(now)

    params.append(job_id)

    connection = connect(db_path)
    try:
        connection.execute(
            f"UPDATE model_catalog_print_history_jobs SET {', '.join(sets)} WHERE job_id = ?",
            params,
        )
        connection.commit()
    finally:
        connection.close()

    result = read_slicer_job(db_path=db_path, job_id=job_id)
    if result is None:
        raise RuntimeError(f"Failed to read slicer job after transition: {job_id}")
    return result


def delete_slicer_job(*, db_path: Path, job_id: str) -> bool:
    """Delete a slicer job.  Only draft/cancelled/failed jobs can be deleted.

    Returns ``True`` if a row was removed, ``False`` if the job was not found.
    Raises ``ValueError`` if the job exists but is in a non-deletable status.
    """
    existing = read_slicer_job(db_path=db_path, job_id=job_id)
    if existing is None:
        return False
    if existing.status not in ("draft", "cancelled", "failed"):
        raise ValueError(
            f"Cannot delete job {job_id}: status is '{existing.status}' "
            f"(only draft/cancelled/failed jobs can be deleted)"
        )
    connection = connect(db_path)
    try:
        connection.execute(
            "DELETE FROM model_catalog_print_history_jobs WHERE job_id = ?",
            (job_id,),
        )
        connection.commit()
        return True
    finally:
        connection.close()
