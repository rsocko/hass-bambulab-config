"""Unified production queue entry endpoints.

Issue #1406 scope:
- create_entry
- get_entry
- list_entries (filters + pagination)
- update_entry
- delete_entry
"""

from __future__ import annotations

from dataclasses import asdict
import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, Response

from ..db import (
    create_unified_queue_transition_audit,
    create_unified_queue_entry,
    delete_unified_queue_entry,
    list_unified_queue_entries,
    read_unified_queue_entry,
    update_unified_queue_entry,
)
from ..state import AppState

router = APIRouter(tags=["unified-queue"])

VALID_SOURCE_KINDS = {"catalog_model", "working_group", "working_file", "idea"}
VALID_STATES = {"idea", "todo", "ready", "started", "blocked", "done"}
VALID_DURATION_BUCKETS = {"quick", "medium", "overnight", "marathon", "unknown"}
VALID_SELECTION_MODES = {"all_files_all_plates", "selected_files", "selected_plates"}
STATE_TRANSITIONS: dict[str, set[str]] = {
    "idea": {"todo"},
    "todo": {"ready"},
    "ready": {"started"},
    "started": {"blocked", "done"},
    "blocked": {"ready", "done"},
    "done": set(),
}

_DURATION_BUCKET_ALIASES = {
    "0-2h": "quick",
    "2-4h": "medium",
    "4-8h": "overnight",
    "8h+": "marathon",
}


def _error_response(*, status_code: int, error: str, message: str, extra: dict[str, Any] | None = None) -> JSONResponse:
    payload: dict[str, Any] = {
        "success": False,
        "error": error,
        "message": message,
    }
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _coerce_int(value: object, *, field: str, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return parsed


def _coerce_optional_int(value: object | None, *, field: str, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _coerce_int(value, field=field, minimum=minimum)


def _normalize_duration_bucket(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    normalized = _DURATION_BUCKET_ALIASES.get(normalized, normalized)
    return normalized


def _entry_to_response(entry: Any) -> dict[str, Any]:
    payload = asdict(entry)
    payload["source_id"] = payload.get("source_ref")
    payload["copies"] = payload.get("copies_requested")
    return payload


def _coerce_bool(value: object | None, *, field: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in {0, 1}:
            return bool(value)
        raise ValueError(f"{field} must be a boolean")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{field} must be a boolean")


def _validate_state_transition(*, from_state: str, to_state: str) -> tuple[bool, list[str]]:
    allowed = sorted(STATE_TRANSITIONS.get(from_state, set()))
    return to_state in set(allowed), allowed


def _validate_source_kind(value: object) -> str:
    source_kind = str(value or "").strip().lower()
    if source_kind not in VALID_SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {sorted(VALID_SOURCE_KINDS)}")
    return source_kind


def _validate_state(value: object | None) -> str | None:
    if value is None:
        return None
    state = str(value).strip().lower()
    if state not in VALID_STATES:
        raise ValueError(f"state must be one of {sorted(VALID_STATES)}")
    return state


def _validate_selection_mode(value: object | None) -> str | None:
    if value is None:
        return None
    selection_mode = str(value).strip().lower()
    if selection_mode not in VALID_SELECTION_MODES:
        raise ValueError(f"selection_mode must be one of {sorted(VALID_SELECTION_MODES)}")
    return selection_mode


def _validate_duration_bucket(value: object | None) -> str | None:
    if value is None:
        return None
    duration_bucket = _normalize_duration_bucket(str(value))
    if duration_bucket is None:
        return None
    if duration_bucket not in VALID_DURATION_BUCKETS:
        raise ValueError(f"duration_bucket must be one of {sorted(VALID_DURATION_BUCKETS)}")
    return duration_bucket


def _validate_attempt_outcome(value: object | None) -> str | None:
    if value is None:
        return None
    outcome = str(value).strip().lower()
    if not outcome:
        return None
    if outcome not in {"success", "failed", "aborted", "unknown"}:
        raise ValueError("last_attempt_outcome must be one of ['aborted', 'failed', 'success', 'unknown']")
    return outcome


def _parse_csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    values = [item.strip().lower() for item in str(value).split(",")]
    return [item for item in values if item]


def _parse_sort(sort: str | None, order: str | None) -> tuple[str, str] | None:
    if not sort:
        return ("rank", "asc")

    candidate = str(sort).strip().lower()
    direction = str(order or "").strip().lower() or None
    field = candidate

    if ":" in candidate:
        field, suffix = candidate.split(":", 1)
        if suffix in {"asc", "desc"}:
            direction = suffix
    elif candidate.startswith("-"):
        field = candidate[1:]
        direction = direction or "desc"

    if field not in {"rank", "created_at", "duration_bucket"}:
        return None

    resolved_direction = direction or "asc"
    if resolved_direction not in {"asc", "desc"}:
        return None
    return (field, resolved_direction)


def _duration_bucket_weight(bucket: str) -> int:
    mapping = {
        "quick": 1,
        "medium": 2,
        "overnight": 3,
        "marathon": 4,
        "unknown": 5,
    }
    return mapping.get(str(bucket or "unknown").strip().lower(), 5)


def _sort_entries(entries: list[Any], field: str, direction: str) -> list[Any]:
    reverse = direction == "desc"
    if field == "rank":
        return sorted(entries, key=lambda entry: (int(entry.rank), str(entry.created_at)), reverse=reverse)
    if field == "created_at":
        return sorted(entries, key=lambda entry: str(entry.created_at), reverse=reverse)
    if field == "duration_bucket":
        return sorted(
            entries,
            key=lambda entry: (_duration_bucket_weight(str(entry.duration_bucket)), int(entry.rank), str(entry.created_at)),
            reverse=reverse,
        )
    return entries


@router.post("/api/unified-queue/entries")
def create_entry(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    source_ref = str(body.get("source_ref") or body.get("source_id") or "").strip() or None
    title = str(body.get("title") or "").strip()
    try:
        source_kind = _validate_source_kind(body.get("source_kind"))
        entry_state = _validate_state(body.get("state")) or "todo"
        selection_mode = _validate_selection_mode(body.get("selection_mode")) or "all_files_all_plates"
        duration_bucket = _validate_duration_bucket(body.get("duration_bucket")) or "unknown"
        rank = _coerce_optional_int(body.get("rank"), field="rank", minimum=0) or 0
        copies = body.get("copies_requested", body.get("copies", 1))
        copies_requested = _coerce_int(copies, field="copies_requested", minimum=1)
        copies_completed = _coerce_optional_int(body.get("copies_completed"), field="copies_completed", minimum=0) or 0
        estimated_total_minutes = _coerce_optional_int(
            body.get("estimated_total_minutes"), field="estimated_total_minutes", minimum=0
        )
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    if source_kind != "idea" and not source_ref:
        return _error_response(
            status_code=400,
            error="validation_error",
            message="source_ref (or source_id) is required unless source_kind is 'idea'",
        )
    if not title:
        if source_ref:
            title = f"{source_kind.replace('_', ' ').title()}: {source_ref}"
        else:
            title = "Queue Entry"

    queue_entry_id = str(body.get("queue_entry_id") or "").strip() or f"uqe-{uuid.uuid4().hex[:12]}"

    try:
        created = create_unified_queue_entry(
            db_path=state.settings.db_path,
            queue_entry_id=queue_entry_id,
            source_kind=source_kind,
            source_ref=source_ref,
            title=title,
            state=entry_state,
            rank=rank,
            started_at=str(body.get("started_at") or "").strip() or None,
            completed_at=str(body.get("completed_at") or "").strip() or None,
            blocked_reason=str(body.get("blocked_reason") or "").strip() or None,
            copies_requested=copies_requested,
            copies_completed=copies_completed,
            selection_mode=selection_mode,
            estimated_total_minutes=estimated_total_minutes,
            duration_bucket=duration_bucket,
            ams_ready_score=_coerce_optional_int(body.get("ams_ready_score"), field="ams_ready_score", minimum=0) or 0,
            overnight_fit_score=_coerce_optional_int(body.get("overnight_fit_score"), field="overnight_fit_score", minimum=0)
            or 0,
            queue_notes=str(body.get("queue_notes") or "").strip() or None,
            last_archive_id=str(body.get("last_archive_id") or "").strip() or None,
            last_attempt_outcome=_validate_attempt_outcome(body.get("last_attempt_outcome")),
        )
    except sqlite3.IntegrityError as exc:
        return _error_response(status_code=400, error="integrity_error", message=str(exc))
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {"success": True, "entry": _entry_to_response(created)}


@router.get("/api/unified-queue/entries/{queue_entry_id}")
def get_entry(queue_entry_id: str, request: Request) -> Any:
    state: AppState = request.app.state.model_catalog
    try:
        entry = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if entry is None:
        return _error_response(
            status_code=404,
            error="not_found",
            message="Queue entry not found",
            extra={"queue_entry_id": queue_entry_id},
        )
    return {"success": True, "entry": _entry_to_response(entry)}


@router.get("/api/unified-queue/entries")
def list_entries(
    request: Request,
    source_kind: str | None = None,
    source_ref: str | None = None,
    state: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    state_obj: AppState = request.app.state.model_catalog
    try:
        if source_kind:
            _validate_source_kind(source_kind)
        if state:
            _validate_state(state)
        if limit < 1 or limit > 200:
            return _error_response(status_code=400, error="validation_error", message="limit must be between 1 and 200")
        if offset < 0:
            return _error_response(status_code=400, error="validation_error", message="offset must be >= 0")

        entries = list_unified_queue_entries(db_path=state_obj.settings.db_path)
        filtered = entries
        if source_kind:
            source_kind_norm = source_kind.strip().lower()
            filtered = [entry for entry in filtered if entry.source_kind == source_kind_norm]
        if source_ref:
            source_ref_norm = source_ref.strip().lower()
            filtered = [entry for entry in filtered if (entry.source_ref or "").lower() == source_ref_norm]
        if state:
            state_norm = state.strip().lower()
            filtered = [entry for entry in filtered if entry.state == state_norm]
        if q:
            query = q.strip().lower()
            filtered = [
                entry
                for entry in filtered
                if query in entry.title.lower() or query in (entry.source_ref or "").lower()
            ]

        total = len(filtered)
        items = filtered[offset: offset + limit]
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "entries": [_entry_to_response(item) for item in items],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "total": total,
            "has_more": (offset + len(items)) < total,
        },
        "filters": {
            "source_kind": source_kind,
            "source_ref": source_ref,
            "state": state,
            "q": q,
        },
    }


@router.get("/api/v1/queues/{printer_id}/entries")
def list_queue_entries_v1(
    printer_id: str,
    request: Request,
    state: str | None = None,
    source_kind: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Compatibility endpoint for queue entry listing with filters and pagination."""
    state_obj: AppState = request.app.state.model_catalog
    state_filters = _parse_csv_values(state)
    source_kind_filters = _parse_csv_values(source_kind)
    sort_spec = _parse_sort(sort, order)

    try:
        if limit < 1 or limit > 200:
            return _error_response(status_code=400, error="validation_error", message="limit must be between 1 and 200")
        if offset < 0:
            return _error_response(status_code=400, error="validation_error", message="offset must be >= 0")
        if sort_spec is None:
            return _error_response(
                status_code=400,
                error="validation_error",
                message="sort must be one of rank, created_at, duration_bucket with optional :asc or :desc",
            )

        invalid_states = [candidate for candidate in state_filters if candidate not in VALID_STATES]
        if invalid_states:
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"invalid state filters: {invalid_states}",
            )

        invalid_sources = [candidate for candidate in source_kind_filters if candidate not in VALID_SOURCE_KINDS]
        if invalid_sources:
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"invalid source_kind filters: {invalid_sources}",
            )

        entries = list_unified_queue_entries(db_path=state_obj.settings.db_path)
        filtered = entries
        if state_filters:
            allowed_states = set(state_filters)
            filtered = [entry for entry in filtered if entry.state in allowed_states]
        if source_kind_filters:
            allowed_sources = set(source_kind_filters)
            filtered = [entry for entry in filtered if entry.source_kind in allowed_sources]

        sort_field, sort_direction = sort_spec
        ordered = _sort_entries(filtered, sort_field, sort_direction)

        total = len(ordered)
        paged = ordered[offset: offset + limit]
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "entries": [_entry_to_response(entry) for entry in paged],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(paged),
            "total": total,
            "has_more": (offset + len(paged)) < total,
        },
        "filters": {
            "state": state_filters,
            "source_kind": source_kind_filters,
        },
        "sort": {
            "field": sort_field,
            "direction": sort_direction,
        },
    }


@router.post("/api/v1/queues/{printer_id}/add")
def add_queue_entry_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Add endpoint for v1 queue contract backed by unified queue storage."""
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    legacy_fields = [
        field_name
        for field_name in ["queue_status", "queue_priority", "print_file", "print_settings"]
        if field_name in body
    ]
    if legacy_fields:
        return _error_response(
            status_code=400,
            error="validation_error",
            message=(
                "legacy queue fields are not supported in unified queue add endpoint; "
                "use state, rank, and queue_notes"
            ),
            extra={"unsupported_fields": legacy_fields},
        )

    try:
        source_kind = _validate_source_kind(body.get("source_kind") or "catalog_model")
        source_ref = str(body.get("source_id") or body.get("source_ref") or "").strip() or None
        if source_kind != "idea" and not source_ref:
            return _error_response(
                status_code=400,
                error="validation_error",
                message="source_id is required unless source_kind is 'idea'",
            )

        requested_state = _validate_state(body.get("state"))
        entry_state = requested_state or "todo"

        copies_requested = _coerce_int(body.get("copies", 1), field="copies", minimum=1)
        duration_bucket = _validate_duration_bucket(body.get("duration_bucket")) or "unknown"

        rank = _coerce_optional_int(body.get("rank"), field="rank", minimum=0) or 0

        ams_fit = _coerce_bool(body.get("ams_fit"), field="ams_fit")
        overnight_fit = _coerce_bool(body.get("overnight_fit"), field="overnight_fit")
        ams_ready_score = 100 if ams_fit is True else 0
        overnight_fit_score = 100 if overnight_fit is True else 0

        queue_notes = str(body.get("queue_notes") or "").strip() or None

        title = str(body.get("title") or "").strip()
        if not title:
            if source_ref:
                title = f"{source_kind.replace('_', ' ').title()}: {source_ref}"
            else:
                title = "Queue Entry"

        queue_entry_id = str(body.get("queue_entry_id") or "").strip() or f"uqe-{uuid.uuid4().hex[:12]}"

        created = create_unified_queue_entry(
            db_path=state.settings.db_path,
            queue_entry_id=queue_entry_id,
            source_kind=source_kind,
            source_ref=source_ref,
            title=title,
            state=entry_state,
            rank=rank,
            copies_requested=copies_requested,
            duration_bucket=duration_bucket,
            selection_mode="all_files_all_plates",
            ams_ready_score=ams_ready_score,
            overnight_fit_score=overnight_fit_score,
            queue_notes=queue_notes,
        )
    except sqlite3.IntegrityError as exc:
        return _error_response(status_code=400, error="integrity_error", message=str(exc))
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    location = f"/api/unified-queue/entries/{created.queue_entry_id}"
    payload = {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "entry": _entry_to_response(created),
    }
    return JSONResponse(status_code=201, content=payload, headers={"Location": location})


@router.patch("/api/unified-queue/entries/{queue_entry_id}")
def update_entry(
    queue_entry_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    try:
        updates: dict[str, Any] = {}
        if "source_ref" in body or "source_id" in body:
            updates["source_ref"] = str(body.get("source_ref") or body.get("source_id") or "").strip() or None
        if "title" in body:
            title = str(body.get("title") or "").strip()
            if not title:
                return _error_response(status_code=400, error="validation_error", message="title cannot be empty")
            updates["title"] = title
        if "state" in body:
            updates["state"] = _validate_state(body.get("state"))
        if "rank" in body:
            updates["rank"] = _coerce_optional_int(body.get("rank"), field="rank", minimum=0)
        if "copies_requested" in body or "copies" in body:
            copies = body.get("copies_requested", body.get("copies"))
            updates["copies_requested"] = _coerce_int(copies, field="copies_requested", minimum=1)
        if "copies_completed" in body:
            updates["copies_completed"] = _coerce_optional_int(body.get("copies_completed"), field="copies_completed", minimum=0)
        if "selection_mode" in body:
            updates["selection_mode"] = _validate_selection_mode(body.get("selection_mode"))
        if "duration_bucket" in body:
            updates["duration_bucket"] = _validate_duration_bucket(body.get("duration_bucket"))
        if "estimated_total_minutes" in body:
            updates["estimated_total_minutes"] = _coerce_optional_int(
                body.get("estimated_total_minutes"), field="estimated_total_minutes", minimum=0
            )
        if "ams_ready_score" in body:
            updates["ams_ready_score"] = _coerce_optional_int(body.get("ams_ready_score"), field="ams_ready_score", minimum=0)
        if "overnight_fit_score" in body:
            updates["overnight_fit_score"] = _coerce_optional_int(
                body.get("overnight_fit_score"), field="overnight_fit_score", minimum=0
            )
        if "started_at" in body:
            updates["started_at"] = str(body.get("started_at") or "").strip() or None
        if "completed_at" in body:
            updates["completed_at"] = str(body.get("completed_at") or "").strip() or None
        if "blocked_reason" in body:
            updates["blocked_reason"] = str(body.get("blocked_reason") or "").strip() or None
        if "queue_notes" in body:
            updates["queue_notes"] = str(body.get("queue_notes") or "").strip() or None
        if "last_archive_id" in body:
            updates["last_archive_id"] = str(body.get("last_archive_id") or "").strip() or None
        if "last_attempt_outcome" in body:
            updates["last_attempt_outcome"] = _validate_attempt_outcome(body.get("last_attempt_outcome"))
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    if not updates:
        return _error_response(status_code=400, error="validation_error", message="No supported fields provided")

    existing = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    if existing is None:
        return _error_response(
            status_code=404,
            error="not_found",
            message="Queue entry not found",
            extra={"queue_entry_id": queue_entry_id},
        )

    next_state = updates.get("state")
    transitioning = bool(isinstance(next_state, str) and next_state != existing.state)
    if transitioning:
        allowed, allowed_targets = _validate_state_transition(from_state=existing.state, to_state=next_state)
        if not allowed:
            return _error_response(
                status_code=400,
                error="invalid_transition",
                message=(
                    f"Invalid state transition '{existing.state}' -> '{next_state}'. "
                    f"Allowed targets: {allowed_targets}"
                ),
                extra={
                    "from_state": existing.state,
                    "to_state": next_state,
                    "allowed_targets": allowed_targets,
                },
            )

    try:
        updated = update_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id, **updates)
        if transitioning and updated is not None:
            actor = request.headers.get("x-actor") or "api"
            reason = str(body.get("blocked_reason") or body.get("queue_notes") or "").strip() or None
            create_unified_queue_transition_audit(
                db_path=state.settings.db_path,
                queue_entry_id=queue_entry_id,
                from_state=existing.state,
                to_state=next_state,
                actor=actor,
                reason=reason,
            )
    except sqlite3.IntegrityError as exc:
        return _error_response(status_code=400, error="integrity_error", message=str(exc))
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if updated is None:
        return _error_response(
            status_code=404,
            error="not_found",
            message="Queue entry not found",
            extra={"queue_entry_id": queue_entry_id},
        )
    return {"success": True, "entry": _entry_to_response(updated)}


@router.delete("/api/unified-queue/entries/{queue_entry_id}")
def delete_entry(queue_entry_id: str, request: Request) -> Any:
    state: AppState = request.app.state.model_catalog
    try:
        deleted = delete_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if not deleted:
        return _error_response(
            status_code=404,
            error="not_found",
            message="Queue entry not found",
            extra={"queue_entry_id": queue_entry_id},
        )
    return {"success": True, "queue_entry_id": queue_entry_id, "deleted": True}


@router.delete("/api/v1/queues/{printer_id}/entries/{queue_entry_id}")
def delete_queue_entry_v1(
    printer_id: str,
    queue_entry_id: str,
    request: Request,
) -> Any:
    """v1 compat: delete a queue entry by ID. Returns 204 No Content on success."""
    state: AppState = request.app.state.model_catalog

    existing = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    if existing is None:
        return _error_response(
            status_code=404,
            error="not_found",
            message="Queue entry not found",
            extra={"queue_entry_id": queue_entry_id, "printer_id": printer_id},
        )

    try:
        deleted = delete_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if not deleted:
        return _error_response(
            status_code=404,
            error="not_found",
            message="Queue entry not found",
            extra={"queue_entry_id": queue_entry_id, "printer_id": printer_id},
        )

    actor = request.headers.get("x-actor") or "api"
    try:
        create_unified_queue_transition_audit(
            db_path=state.settings.db_path,
            queue_entry_id=queue_entry_id,
            from_state=existing.state,
            to_state="deleted",
            actor=actor,
            reason="entry deleted via v1 DELETE endpoint",
        )
    except Exception:
        pass  # audit failure must not block successful delete response

    return Response(status_code=204)


