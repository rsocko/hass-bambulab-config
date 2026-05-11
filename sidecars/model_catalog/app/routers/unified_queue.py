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
from pathlib import Path
import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, Response

from ..db import (
    ReorderMove,
    connect,
    create_unified_queue_match_suggestion,
    create_unified_queue_transition_audit,
    create_unified_queue_entry,
    create_unified_queue_file_unit,
    create_unified_queue_plate_unit,
    delete_unified_queue_entry,
    list_unified_queue_entries,
    list_unified_queue_file_units,
    list_unified_queue_match_suggestions,
    read_unified_queue_match_suggestion,
    read_unified_queue_planner_preference,
    read_unified_queue_entry,
    reorder_unified_queue_entries,
    update_unified_queue_match_suggestion,
    update_unified_queue_entry,
    upsert_unified_queue_planner_preference,
    create_planner_operation_audit,
    list_planner_operation_audits,
    create_planner_operation_snapshots,
    read_planner_operation_snapshots,
    utc_now_iso,
)
from ..geometry_3mf import extract_3mf_plates_metadata
from ..services.model_detail_service import build_model_detail_response
from ..state import AppState

router = APIRouter(tags=["unified-queue"])

VALID_SOURCE_KINDS = {"catalog_model", "working_group", "working_file", "idea"}
VALID_STATES = {"backlog", "preparing", "ready", "in_progress", "blocked", "done"}
VALID_DURATION_BUCKETS = {"quick", "medium", "overnight", "marathon", "unknown"}
VALID_SELECTION_MODES = {"all_files_all_plates", "selected_files", "selected_plates"}
STATE_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"preparing", "ready", "in_progress"},
    "preparing": {"ready", "in_progress", "blocked"},
    "ready": {"in_progress", "blocked"},
    "in_progress": {"blocked", "done"},
    "blocked": {"preparing", "ready", "in_progress", "done"},
    "done": set(),
}

_DURATION_BUCKET_ALIASES = {
    "0-2h": "quick",
    "2-4h": "medium",
    "4-8h": "overnight",
    "8h+": "marathon",
}

PLANNER_STRATEGY_PRESETS: dict[str, dict[str, Any]] = {
    "aggressive": {
        "ams_fit": 60,
        "overnight_fit": 10,
        "duration": {
            "quick": 30,
            "medium": 20,
            "overnight": 10,
            "marathon": 0,
            "unknown": 0,
        },
    },
    "balanced": {
        "ams_fit": 35,
        "overnight_fit": 35,
        "duration": {
            "quick": 30,
            "medium": 20,
            "overnight": 10,
            "marathon": 0,
            "unknown": 0,
        },
    },
    "lazy": {
        "ams_fit": 20,
        "overnight_fit": 60,
        "duration": {
            "quick": 10,
            "medium": 15,
            "overnight": 25,
            "marathon": 0,
            "unknown": 0,
        },
    },
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


def _next_append_rank(*, db_path: Path) -> int:
    entries = list_unified_queue_entries(db_path=db_path)
    if not entries:
        return 0
    return max(int(entry.rank) for entry in entries) + 1


def _normalize_plate_specs(raw_plates: object) -> tuple[list[dict[str, str]], int]:
    normalized: list[dict[str, str]] = []
    duplicate_skips = 0
    seen_ids: set[str] = set()

    if isinstance(raw_plates, list):
        for idx, raw_plate in enumerate(raw_plates):
            if not isinstance(raw_plate, dict):
                continue
            plate_key = str(raw_plate.get("id") or raw_plate.get("plate_id") or "").strip() or str(idx + 1)
            plate_name = str(raw_plate.get("name") or raw_plate.get("plate_name") or "").strip() or f"Plate {idx + 1}"
            if plate_key in seen_ids:
                duplicate_skips += 1
                continue
            seen_ids.add(plate_key)
            normalized.append({"plate_key": plate_key, "plate_name": plate_name})

    if normalized:
        return normalized, duplicate_skips

    return ([{"plate_key": "default", "plate_name": "Default Plate"}], duplicate_skips)


def _extract_catalog_file_plates(
    *,
    request: Request,
    model_ref: str,
    file_id: str,
    file_name: str,
    file_type: str | None,
) -> list[dict[str, str]]:
    is_3mf = file_name.lower().endswith(".3mf") or "3mf" in str(file_type or "").lower()
    if not is_3mf:
        return [{"plate_key": "default", "plate_name": "Default Plate"}]

    try:
        from . import models as models_router

        payload = models_router.get_3mf_plates_endpoint(request=request, model_ref=model_ref, file_id=file_id)
        if isinstance(payload, JSONResponse):
            return [{"plate_key": "default", "plate_name": "Default Plate"}]
        raw_plates = payload.get("plates")
        if isinstance(raw_plates, list) and raw_plates:
            return raw_plates
        return [{"plate_key": "default", "plate_name": "Default Plate"}]
    except Exception:
        return [{"plate_key": "default", "plate_name": "Default Plate"}]


def _extract_working_file_plates(file_path: Path) -> list[dict[str, str]]:
    if file_path.suffix.lower() != ".3mf":
        return [{"plate_key": "default", "plate_name": "Default Plate"}]

    try:
        package_bytes = file_path.read_bytes()
    except Exception:
        return [{"plate_key": "default", "plate_name": "Default Plate"}]

    try:
        metadata = extract_3mf_plates_metadata(package_bytes)
    except Exception:
        return [{"plate_key": "default", "plate_name": "Default Plate"}]

    raw_plates = metadata.get("plates")
    if isinstance(raw_plates, list) and raw_plates:
        return raw_plates
    return [{"plate_key": "default", "plate_name": "Default Plate"}]


def _resolve_catalog_quick_add_specs(
    *,
    state: AppState,
    request: Request,
    source_ref: str,
) -> tuple[list[dict[str, Any]], int, int, str | None]:
    client = request.app.state.manyfold_client
    detail = build_model_detail_response(state, client, source_ref, request=request)
    if detail.get("success") is not True:
        return [], 0, 0, "catalog model not found"

    model_payload = detail.get("model") if isinstance(detail.get("model"), dict) else {}
    files = model_payload.get("files") if isinstance(model_payload.get("files"), list) else []
    if not files:
        return [], 0, 0, "catalog model has no files"

    specs: list[dict[str, Any]] = []
    duplicate_file_skips = 0
    duplicate_plate_skips = 0
    seen_files: set[str] = set()

    for index, file_obj in enumerate(files):
        if not isinstance(file_obj, dict):
            continue
        file_id = str(file_obj.get("id") or file_obj.get("file_id") or "").strip() or f"catalog-file-{index + 1}"
        file_name = str(file_obj.get("filename") or file_obj.get("name") or "").strip() or file_id
        dedupe_key = file_id.lower()
        if dedupe_key in seen_files:
            duplicate_file_skips += 1
            continue
        seen_files.add(dedupe_key)

        raw_plates = _extract_catalog_file_plates(
            request=request,
            model_ref=source_ref,
            file_id=file_id,
            file_name=file_name,
            file_type=str(file_obj.get("file_type") or file_obj.get("content_type") or file_obj.get("asset_type") or ""),
        )
        plates, plate_dupes = _normalize_plate_specs(raw_plates)
        duplicate_plate_skips += plate_dupes
        specs.append({"file_id": file_id, "file_name": file_name, "plates": plates})

    if not specs:
        return [], duplicate_file_skips, duplicate_plate_skips, "catalog model has no queueable files"

    return specs, duplicate_file_skips, duplicate_plate_skips, None


def _resolve_working_group_quick_add_specs(
    *,
    state: AppState,
    source_ref: str,
) -> tuple[list[dict[str, Any]], int, int, str | None]:
    connection = connect(state.settings.db_path)
    try:
        group_row = None
        if source_ref.isdigit():
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (int(source_ref),)).fetchone()
        if group_row is None:
            group_row = connection.execute("SELECT * FROM working_groups WHERE slug = ?", (source_ref,)).fetchone()
        if group_row is None:
            return [], 0, 0, "working group not found"

        item_rows = connection.execute(
            "SELECT id, file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC",
            (int(group_row["id"]),),
        ).fetchall()
    finally:
        connection.close()

    if not item_rows:
        return [], 0, 0, "working group has no files"

    specs: list[dict[str, Any]] = []
    duplicate_file_skips = 0
    duplicate_plate_skips = 0
    seen_paths: set[str] = set()

    for row in item_rows:
        file_path = Path(str(row["file_path"] or "")).expanduser()
        dedupe_key = str(file_path).replace("\\", "/").lower()
        if dedupe_key in seen_paths:
            duplicate_file_skips += 1
            continue
        seen_paths.add(dedupe_key)

        file_name = file_path.name or f"working-item-{int(row['id'])}"
        file_id = f"working-item-{int(row['id'])}"
        raw_plates = _extract_working_file_plates(file_path)
        plates, plate_dupes = _normalize_plate_specs(raw_plates)
        duplicate_plate_skips += plate_dupes
        specs.append({"file_id": file_id, "file_name": file_name, "plates": plates})

    if not specs:
        return [], duplicate_file_skips, duplicate_plate_skips, "working group has no queueable files"

    return specs, duplicate_file_skips, duplicate_plate_skips, None


def _create_quick_add_units(*, state: AppState, queue_entry_id: str, specs: list[dict[str, Any]]) -> tuple[int, int]:
    file_units_created = 0
    plate_units_created = 0

    for file_index, file_spec in enumerate(specs):
        file_unit_id = f"qfu-{file_index + 1:03d}"
        created_file = create_unified_queue_file_unit(
            db_path=state.settings.db_path,
            queue_entry_id=queue_entry_id,
            file_unit_id=file_unit_id,
            file_id=str(file_spec.get("file_id") or "").strip() or None,
            file_name=str(file_spec.get("file_name") or "").strip() or file_unit_id,
            selected=True,
        )
        file_units_created += 1

        plates = file_spec.get("plates") if isinstance(file_spec.get("plates"), list) else []
        for plate_index, plate in enumerate(plates):
            if not isinstance(plate, dict):
                continue
            plate_key = str(plate.get("plate_key") or "").strip() or f"plate-{plate_index + 1}"
            plate_name = str(plate.get("plate_name") or "").strip() or f"Plate {plate_index + 1}"
            plate_unit_id = f"qpu-{file_index + 1:03d}-{plate_index + 1:03d}"
            create_unified_queue_plate_unit(
                db_path=state.settings.db_path,
                queue_entry_id=queue_entry_id,
                file_unit_id=created_file.file_unit_id,
                plate_unit_id=plate_unit_id,
                plate_key=plate_key,
                plate_name=plate_name,
                selected=True,
                state="pending",
            )
            plate_units_created += 1

    return file_units_created, plate_units_created


def _normalize_tag_values(value: object) -> set[str]:
    values: set[str] = set()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized:
            values.add(normalized)
        return values
    if isinstance(value, list):
        for item in value:
            values.update(_normalize_tag_values(item))
        return values
    if isinstance(value, dict):
        for item in value.values():
            values.update(_normalize_tag_values(item))
        return values
    return values


def _filename_stem(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[0]
    cleaned = "".join(ch if ch.isalnum() else " " for ch in normalized)
    return " ".join(cleaned.split())


def _entry_estimated_minutes(entry: Any, file_units: list[Any]) -> int | None:
    if entry.estimated_total_minutes is not None:
        return int(entry.estimated_total_minutes)
    minute_values = [int(unit.estimated_minutes) for unit in file_units if unit.estimated_minutes is not None]
    if minute_values:
        return sum(minute_values)
    return None


def _score_archive_match_candidate(
    *,
    archive_model_id: str | None,
    archive_filename: str | None,
    archive_filament_tags: set[str],
    archive_estimated_minutes: int | None,
    entry: Any,
    file_units: list[Any],
) -> dict[str, Any]:
    entry_model_id = str(entry.source_ref or "").strip().lower()
    entry_tags: set[str] = set()
    entry_filenames: set[str] = set()
    for unit in file_units:
        entry_tags.update(_normalize_tag_values(unit.filament_requirements))
        stem = _filename_stem(unit.file_name)
        if stem:
            entry_filenames.add(stem)

    archive_filename_stem = _filename_stem(archive_filename)
    high_match = bool(
        archive_model_id
        and entry_model_id
        and archive_model_id == entry_model_id
        and archive_filament_tags
        and archive_filament_tags.issubset(entry_tags)
    )

    filename_match = bool(archive_filename_stem and archive_filename_stem in entry_filenames)
    tag_subset_match = bool(archive_filament_tags and archive_filament_tags.issubset(entry_tags))

    entry_minutes = _entry_estimated_minutes(entry, file_units)
    time_match = False
    if archive_estimated_minutes is not None and entry_minutes is not None and archive_estimated_minutes > 0:
        delta = abs(entry_minutes - archive_estimated_minutes)
        time_match = delta <= (archive_estimated_minutes * 0.15)

    if high_match:
        return {
            "confidence": "high",
            "score": 1.0,
            "match_method": "model_id_and_filament_tags",
            "reasons": ["exact model_id + all filament tags match"],
        }
    if filename_match or tag_subset_match:
        reasons: list[str] = []
        if filename_match:
            reasons.append("filename match")
        if tag_subset_match:
            reasons.append("tag subset match")
        score = 0.75 if (filename_match and tag_subset_match) else 0.7
        return {
            "confidence": "medium",
            "score": score,
            "match_method": "filename_or_tag_subset",
            "reasons": reasons,
        }
    if time_match:
        return {
            "confidence": "low",
            "score": 0.4,
            "match_method": "estimated_time_within_15_percent",
            "reasons": ["print time estimate within +/-15%"],
        }
    return {
        "confidence": "unmatched",
        "score": 0.0,
        "match_method": "none",
        "reasons": ["no criteria met"],
    }


def _rank_archive_match_candidates(
    *,
    db_path: Path,
    archive_model_id: str | None,
    archive_filename: str | None,
    archive_filament_tags: set[str],
    archive_estimated_minutes: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    candidates: list[dict[str, Any]] = []
    entries = list_unified_queue_entries(db_path=db_path)
    for entry in entries:
        file_units = list_unified_queue_file_units(db_path=db_path, queue_entry_id=entry.queue_entry_id)
        score_data = _score_archive_match_candidate(
            archive_model_id=archive_model_id,
            archive_filename=archive_filename,
            archive_filament_tags=archive_filament_tags,
            archive_estimated_minutes=archive_estimated_minutes,
            entry=entry,
            file_units=file_units,
        )
        candidates.append(
            {
                "queue_entry_id": entry.queue_entry_id,
                "source_kind": entry.source_kind,
                "source_ref": entry.source_ref,
                "confidence": score_data["confidence"],
                "confidence_score": score_data["score"],
                "match_method": score_data["match_method"],
                "reasons": score_data["reasons"],
            }
        )

    confidence_rank = {"high": 3, "medium": 2, "low": 1, "unmatched": 0}
    ordered = sorted(
        candidates,
        key=lambda item: (
            confidence_rank.get(str(item["confidence"]), 0),
            float(item["confidence_score"]),
            str(item["queue_entry_id"]),
        ),
        reverse=True,
    )
    best = ordered[0] if ordered else None
    return ordered, best


def _match_suggestion_to_response(suggestion: Any) -> dict[str, Any]:
    payload = asdict(suggestion)
    payload["matched"] = payload.get("status") in {"auto_completed", "suggested", "remapped"}
    payload["unmatched"] = payload.get("status") == "unmatched"
    return payload


def _extract_required_tray_uuids(file_units: list[Any]) -> set[str]:
    required: set[str] = set()

    def _walk(value: object) -> None:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized:
                required.add(normalized)
            return
        if isinstance(value, list):
            for item in value:
                _walk(item)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                key_name = str(key).strip().lower()
                if key_name in {"tray_uuid", "tray_uuids", "ams_tray_uuid", "ams_tray_uuids", "uuid", "uuids"}:
                    _walk(item)
            return

    for file_unit in file_units:
        _walk(file_unit.filament_requirements)
    return required


def _duration_bucket_for_minutes(estimated_minutes: int | None) -> str:
    if estimated_minutes is None or estimated_minutes <= 0:
        return "unknown"
    if estimated_minutes <= 120:
        return "quick"
    if estimated_minutes <= 240:
        return "medium"
    if estimated_minutes <= 480:
        return "overnight"
    return "marathon"


def _duration_bucket_score(duration_bucket: str) -> int:
    weights = {
        "quick": 40,
        "medium": 30,
        "overnight": 20,
        "marathon": 10,
        "unknown": 0,
    }
    return int(weights.get(duration_bucket, 0))


def _normalize_planner_strategy(value: object | None) -> str:
    strategy = str(value or "").strip().lower() or "balanced"
    if strategy not in PLANNER_STRATEGY_PRESETS:
        raise ValueError("strategy must be one of ['aggressive', 'balanced', 'lazy']")
    return strategy


def _normalize_planner_weights(strategy: str, custom_weights: object | None) -> dict[str, Any]:
    base = {
        "ams_fit": int(PLANNER_STRATEGY_PRESETS[strategy]["ams_fit"]),
        "overnight_fit": int(PLANNER_STRATEGY_PRESETS[strategy]["overnight_fit"]),
        "duration": dict(PLANNER_STRATEGY_PRESETS[strategy]["duration"]),
    }
    if custom_weights is None:
        return base
    if not isinstance(custom_weights, dict):
        raise ValueError("custom_weights must be an object")

    if "ams_fit" in custom_weights:
        base["ams_fit"] = _coerce_int(custom_weights.get("ams_fit"), field="custom_weights.ams_fit", minimum=0)
    if "overnight_fit" in custom_weights:
        base["overnight_fit"] = _coerce_int(
            custom_weights.get("overnight_fit"),
            field="custom_weights.overnight_fit",
            minimum=0,
        )
    if "duration" in custom_weights:
        duration_obj = custom_weights.get("duration")
        if not isinstance(duration_obj, dict):
            raise ValueError("custom_weights.duration must be an object")
        for bucket in ["quick", "medium", "overnight", "marathon", "unknown"]:
            if bucket in duration_obj:
                base["duration"][bucket] = _coerce_int(
                    duration_obj.get(bucket),
                    field=f"custom_weights.duration.{bucket}",
                    minimum=0,
                )
    return base


def _duration_bucket_score_for_weights(duration_bucket: str, weights: dict[str, Any]) -> int:
    duration_weights = weights.get("duration") if isinstance(weights.get("duration"), dict) else {}
    return int(duration_weights.get(duration_bucket, duration_weights.get("unknown", 0)))


def _parse_selected_files_payload(raw_selected_files: object) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(raw_selected_files, list) or not raw_selected_files:
        return [], "selected_files must be a non-empty array"

    parsed: list[dict[str, Any]] = []
    seen_file_ids: set[str] = set()
    for file_index, raw_file in enumerate(raw_selected_files):
        if not isinstance(raw_file, dict):
            return [], f"selected_files[{file_index}] must be an object"

        file_id = str(raw_file.get("file_id") or raw_file.get("id") or "").strip()
        if not file_id:
            return [], f"selected_files[{file_index}].file_id is required"
        if file_id in seen_file_ids:
            return [], f"selected_files contains duplicate file_id '{file_id}'"
        seen_file_ids.add(file_id)

        selected_raw = raw_file.get("selected")
        if selected_raw is None:
            selected = True
        else:
            try:
                selected = bool(_coerce_bool(selected_raw, field=f"selected_files[{file_index}].selected"))
            except ValueError as exc:
                return [], str(exc)

        file_name = str(raw_file.get("file_name") or raw_file.get("name") or "").strip() or None

        selected_plate_keys: set[str] = set()
        if isinstance(raw_file.get("plate_ids"), list):
            for plate_index, plate_id in enumerate(raw_file.get("plate_ids") or []):
                plate_key = str(plate_id or "").strip()
                if not plate_key:
                    return [], f"selected_files[{file_index}].plate_ids[{plate_index}] must be a non-empty string"
                selected_plate_keys.add(plate_key)
        elif isinstance(raw_file.get("plates"), list):
            for plate_index, raw_plate in enumerate(raw_file.get("plates") or []):
                if not isinstance(raw_plate, dict):
                    return [], f"selected_files[{file_index}].plates[{plate_index}] must be an object"
                plate_key = str(raw_plate.get("plate_key") or raw_plate.get("plate_id") or raw_plate.get("id") or "").strip()
                if not plate_key:
                    return [], f"selected_files[{file_index}].plates[{plate_index}] must include plate id"
                plate_selected_raw = raw_plate.get("selected")
                if plate_selected_raw is None:
                    plate_selected = True
                else:
                    try:
                        plate_selected = bool(
                            _coerce_bool(
                                plate_selected_raw,
                                field=f"selected_files[{file_index}].plates[{plate_index}].selected",
                            )
                        )
                    except ValueError as exc:
                        return [], str(exc)
                if plate_selected:
                    selected_plate_keys.add(plate_key)

        parsed.append(
            {
                "file_id": file_id,
                "file_name": file_name,
                "selected": selected,
                "selected_plate_keys": selected_plate_keys,
            }
        )

    return parsed, None


def _apply_advanced_selection_to_specs(
    *,
    specs: list[dict[str, Any]],
    selected_files_payload: list[dict[str, Any]],
    selection_mode: str,
) -> tuple[list[dict[str, Any]], str | None]:
    spec_by_file_id: dict[str, dict[str, Any]] = {}
    for spec in specs:
        file_id = str(spec.get("file_id") or "").strip()
        if file_id:
            spec_by_file_id[file_id] = spec

    selected_output: list[dict[str, Any]] = []
    total_selected_plates = 0
    total_selected_files = 0

    for payload_file in selected_files_payload:
        if not payload_file.get("selected"):
            continue

        file_id = str(payload_file.get("file_id") or "").strip()
        spec = spec_by_file_id.get(file_id)
        if spec is None:
            return [], f"selected file_id '{file_id}' is not valid for source"

        total_selected_files += 1
        source_plates = spec.get("plates") if isinstance(spec.get("plates"), list) else []
        selected_plate_keys = payload_file.get("selected_plate_keys") or set()

        if selection_mode == "selected_plates":
            if not isinstance(selected_plate_keys, set) or not selected_plate_keys:
                continue
            filtered_plates = [
                plate for plate in source_plates if str(plate.get("plate_key") or "").strip() in selected_plate_keys
            ]
            if len(filtered_plates) != len(selected_plate_keys):
                available = {str(plate.get("plate_key") or "").strip() for plate in source_plates}
                invalid = sorted([plate_key for plate_key in selected_plate_keys if plate_key not in available])
                return [], f"selected plate ids {invalid} are not valid for file_id '{file_id}'"
            total_selected_plates += len(filtered_plates)
        else:
            filtered_plates = source_plates
            total_selected_plates += len(filtered_plates)

        if not filtered_plates:
            continue

        selected_output.append(
            {
                "file_id": file_id,
                "file_name": payload_file.get("file_name") or spec.get("file_name"),
                "plates": filtered_plates,
            }
        )

    if total_selected_files == 0:
        return [], "At least one file must be selected"
    if total_selected_plates == 0:
        return [], "At least one plate must be selected"
    if not selected_output:
        return [], "Selected files/plates produced no queueable units"

    return selected_output, None


@router.post("/api/unified-queue/entries")
def create_entry(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> Any:
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    source_ref = str(body.get("source_ref") or body.get("source_id") or "").strip() or None
    title = str(body.get("title") or "").strip()
    try:
        source_kind = _validate_source_kind(body.get("source_kind"))
        entry_state = _validate_state(body.get("state")) or "preparing"
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

    quick_add_specs: list[dict[str, Any]] = []
    advanced_add_specs: list[dict[str, Any]] = []
    duplicate_file_skips = 0
    duplicate_plate_skips = 0

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
        entry_state = requested_state or "preparing"

        copies_requested = _coerce_int(body.get("copies", 1), field="copies", minimum=1)
        duration_bucket = _validate_duration_bucket(body.get("duration_bucket")) or "unknown"

        rank = _coerce_optional_int(body.get("rank"), field="rank", minimum=0)
        if rank is None:
            rank = _next_append_rank(db_path=state.settings.db_path)

        ams_fit = _coerce_bool(body.get("ams_fit"), field="ams_fit")
        overnight_fit = _coerce_bool(body.get("overnight_fit"), field="overnight_fit")
        ams_ready_score = 100 if ams_fit is True else 0
        overnight_fit_score = 100 if overnight_fit is True else 0

        quick_add = _coerce_bool(body.get("quick_add"), field="quick_add") is True
        selected_files_payload_raw = body.get("selected_files")
        advanced_add = isinstance(selected_files_payload_raw, list)
        if quick_add and advanced_add:
            return _error_response(
                status_code=400,
                error="validation_error",
                message="quick_add and selected_files cannot be used together",
            )

        selection_mode = _validate_selection_mode(body.get("selection_mode"))
        if advanced_add and selection_mode is None:
            selection_mode = "selected_plates"
        elif selection_mode is None:
            selection_mode = "all_files_all_plates"

        if quick_add:
            if source_kind == "catalog_model":
                quick_add_specs, duplicate_file_skips, duplicate_plate_skips, quick_add_error = (
                    _resolve_catalog_quick_add_specs(
                        state=state,
                        request=request,
                        source_ref=source_ref or "",
                    )
                )
            elif source_kind == "working_group":
                quick_add_specs, duplicate_file_skips, duplicate_plate_skips, quick_add_error = (
                    _resolve_working_group_quick_add_specs(
                        state=state,
                        source_ref=source_ref or "",
                    )
                )
            else:
                return _error_response(
                    status_code=400,
                    error="validation_error",
                    message="quick_add is only supported for source_kind catalog_model and working_group",
                )

            if quick_add_error:
                return _error_response(
                    status_code=404,
                    error="not_found",
                    message=quick_add_error,
                )
        elif advanced_add:
            if source_kind == "catalog_model":
                source_specs, _dupe_files, _dupe_plates, source_error = _resolve_catalog_quick_add_specs(
                    state=state,
                    request=request,
                    source_ref=source_ref or "",
                )
            elif source_kind == "working_group":
                source_specs, _dupe_files, _dupe_plates, source_error = _resolve_working_group_quick_add_specs(
                    state=state,
                    source_ref=source_ref or "",
                )
            else:
                return _error_response(
                    status_code=400,
                    error="validation_error",
                    message="advanced selected_files is only supported for source_kind catalog_model and working_group",
                )

            if source_error:
                return _error_response(
                    status_code=404,
                    error="not_found",
                    message=source_error,
                )

            if selection_mode not in {"selected_files", "selected_plates"}:
                return _error_response(
                    status_code=400,
                    error="validation_error",
                    message="selection_mode must be selected_files or selected_plates when selected_files is provided",
                )

            selected_files_payload, selected_files_error = _parse_selected_files_payload(selected_files_payload_raw)
            if selected_files_error:
                return _error_response(status_code=400, error="validation_error", message=selected_files_error)

            advanced_add_specs, advanced_error = _apply_advanced_selection_to_specs(
                specs=source_specs,
                selected_files_payload=selected_files_payload,
                selection_mode=selection_mode,
            )
            if advanced_error:
                return _error_response(status_code=400, error="validation_error", message=advanced_error)

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
            selection_mode=selection_mode,
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

    if quick_add_specs:
        try:
            file_units_created, plate_units_created = _create_quick_add_units(
                state=state,
                queue_entry_id=created.queue_entry_id,
                specs=quick_add_specs,
            )
        except Exception as exc:
            delete_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=created.queue_entry_id)
            return _error_response(
                status_code=500,
                error="internal_error",
                message=f"failed to create quick-add file/plate units: {exc}",
            )
    elif advanced_add_specs:
        try:
            file_units_created, plate_units_created = _create_quick_add_units(
                state=state,
                queue_entry_id=created.queue_entry_id,
                specs=advanced_add_specs,
            )
        except Exception as exc:
            delete_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=created.queue_entry_id)
            return _error_response(
                status_code=500,
                error="internal_error",
                message=f"failed to create advanced-add file/plate units: {exc}",
            )
    else:
        file_units_created = 0
        plate_units_created = 0

    location = f"/api/unified-queue/entries/{created.queue_entry_id}"
    payload = {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "entry": _entry_to_response(created),
    }
    if quick_add_specs:
        payload["quick_add"] = {
            "enabled": True,
            "selection_mode": "all_files_all_plates",
            "file_units_created": file_units_created,
            "plate_units_created": plate_units_created,
            "duplicate_file_skips": duplicate_file_skips,
            "duplicate_plate_skips": duplicate_plate_skips,
        }
    if advanced_add_specs:
        payload["advanced_add"] = {
            "enabled": True,
            "selection_mode": created.selection_mode,
            "file_units_created": file_units_created,
            "plate_units_created": plate_units_created,
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


@router.patch("/api/v1/queues/{printer_id}/reorder")
def reorder_queue_entries_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Batch reorder queue entries by setting new ranks.

    Conflict resolution strategy (gap-fill):
    1. Apply all requested rank values in a single transaction.
    2. Re-normalize ALL entry ranks sequentially (0, 1, 2, ...) ordered by
       (rank ASC, created_at ASC). This closes any gaps or collisions.
    3. Entries not in the request may have their rank adjusted as a side effect
       of normalization — this is expected and keeps the rank space dense.

    The printer_id path parameter is accepted for v1 compat but is not used for scoping
    (the unified queue is global, not per-printer).
    """
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    raw_moves = body.get("moves")
    if not isinstance(raw_moves, list):
        return _error_response(
            status_code=400,
            error="validation_error",
            message="'moves' must be an array of {id, new_rank} objects",
        )
    if len(raw_moves) == 0:
        return _error_response(
            status_code=400,
            error="validation_error",
            message="'moves' must contain at least one entry",
        )

    # Validate and coerce each move
    seen_ids: set[str] = set()
    parsed_moves: list[tuple[str, int]] = []
    for i, move in enumerate(raw_moves):
        if not isinstance(move, dict):
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"moves[{i}] must be an object with 'id' and 'new_rank'",
            )
        entry_id = str(move.get("id") or "").strip()
        if not entry_id:
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"moves[{i}].id is required and must be a non-empty string",
            )
        if entry_id in seen_ids:
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"moves[{i}].id '{entry_id}' appears more than once — duplicate IDs are not allowed",
            )
        seen_ids.add(entry_id)
        try:
            new_rank = _coerce_int(move.get("new_rank"), field=f"moves[{i}].new_rank", minimum=0)
        except ValueError as exc:
            return _error_response(status_code=400, error="validation_error", message=str(exc))
        parsed_moves.append((entry_id, new_rank))

    # Capture pre-reorder ranks for audit
    pre_reorder: dict[str, int] = {}
    for entry_id, _ in parsed_moves:
        entry = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=entry_id)
        if entry is not None:
            pre_reorder[entry_id] = entry.rank

    try:
        changed_moves, missing_ids = reorder_unified_queue_entries(
            db_path=state.settings.db_path,
            moves=parsed_moves,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if missing_ids:
        return _error_response(
            status_code=404,
            error="not_found",
            message=f"One or more entry IDs not found: {missing_ids}",
            extra={"missing_ids": missing_ids},
        )

    # Write audit events for each explicitly requested entry whose rank changed
    actor = request.headers.get("x-actor") or "api"
    for entry_id, new_rank_requested in parsed_moves:
        old_rank = pre_reorder.get(entry_id)
        final_entry = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=entry_id)
        final_rank = final_entry.rank if final_entry is not None else new_rank_requested
        if old_rank is not None and old_rank != final_rank:
            try:
                create_unified_queue_transition_audit(
                    db_path=state.settings.db_path,
                    queue_entry_id=entry_id,
                    from_state=f"rank:{old_rank}",
                    to_state=f"rank:{final_rank}",
                    actor=actor,
                    reason=f"reorder via v1 PATCH /reorder (requested new_rank={new_rank_requested})",
                )
            except Exception:
                pass  # audit failure must not block reorder response

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "moved_count": len(parsed_moves),
        "normalization_adjustments": len(changed_moves),
        "moves": [
            {"queue_entry_id": m.queue_entry_id, "old_rank": m.old_rank, "new_rank": m.new_rank}
            for m in changed_moves
        ],
    }


@router.post("/api/v1/queues/{printer_id}/archive-match")
def match_archive_to_queue_entry_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Match an archive payload to the best queue entry using confidence tiers.

    Confidence order:
    - high: exact model_id + all filament tags match
    - medium: filename match OR tag subset match
    - low: estimated print time within +/-15%
    - unmatched: no criteria met
    """
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    archive_id = str(body.get("archive_id") or "").strip() or None
    archive_model_id = str(body.get("model_id") or "").strip().lower() or None
    archive_filename = str(body.get("filename") or "").strip() or None
    archive_filament_tags = _normalize_tag_values(body.get("filament_tags"))
    try:
        archive_estimated_minutes = _coerce_optional_int(
            body.get("estimated_minutes"),
            field="estimated_minutes",
            minimum=0,
        )
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    try:
        ordered, best = _rank_archive_match_candidates(
            db_path=state.settings.db_path,
            archive_model_id=archive_model_id,
            archive_filename=archive_filename,
            archive_filament_tags=archive_filament_tags,
            archive_estimated_minutes=archive_estimated_minutes,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    matched = bool(best and best.get("confidence") != "unmatched")
    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "archive_id": archive_id,
        "matched": matched,
        "unmatched": not matched,
        "best_match": best,
        "candidates": ordered,
    }


@router.post("/api/v1/queues/{printer_id}/archive-completion")
def process_archive_completion_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Apply completion rules from an archive payload and record suggestion audit.

    Rules:
    - high: auto-complete queue entry
    - medium: store suggested record for manual review
    - low/unmatched: store unmatched archive record
    """
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    archive_id = str(body.get("archive_id") or "").strip()
    if not archive_id:
        return _error_response(status_code=400, error="validation_error", message="archive_id is required")

    archive_model_id = str(body.get("model_id") or "").strip().lower() or None
    archive_filename = str(body.get("filename") or "").strip() or None
    archive_filament_tags = _normalize_tag_values(body.get("filament_tags"))
    try:
        archive_estimated_minutes = _coerce_optional_int(
            body.get("estimated_minutes"),
            field="estimated_minutes",
            minimum=0,
        )
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    try:
        ordered, best = _rank_archive_match_candidates(
            db_path=state.settings.db_path,
            archive_model_id=archive_model_id,
            archive_filename=archive_filename,
            archive_filament_tags=archive_filament_tags,
            archive_estimated_minutes=archive_estimated_minutes,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    confidence = str((best or {}).get("confidence") or "unmatched")
    queue_entry_id = str((best or {}).get("queue_entry_id") or "").strip() or None
    suggestion_id = f"uqs-{uuid.uuid4().hex[:12]}"

    status = "unmatched"
    if confidence == "high":
        status = "auto_completed"
    elif confidence == "medium":
        status = "suggested"

    archive_payload = {
        "archive_id": archive_id,
        "model_id": archive_model_id,
        "filename": archive_filename,
        "filament_tags": sorted(list(archive_filament_tags)),
        "estimated_minutes": archive_estimated_minutes,
    }

    try:
        suggestion = create_unified_queue_match_suggestion(
            db_path=state.settings.db_path,
            suggestion_id=suggestion_id,
            printer_id=printer_id,
            archive_id=archive_id,
            queue_entry_id=queue_entry_id,
            confidence=confidence,
            confidence_score=float((best or {}).get("confidence_score") or 0.0),
            match_method=str((best or {}).get("match_method") or "").strip() or None,
            reasons=[str(item) for item in ((best or {}).get("reasons") or [])],
            archive_payload=archive_payload,
            status=status,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    auto_completed = False
    if status == "auto_completed" and queue_entry_id is not None:
        existing = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
        if existing is not None:
            try:
                update_unified_queue_entry(
                    db_path=state.settings.db_path,
                    queue_entry_id=queue_entry_id,
                    state="done",
                    completed_at=utc_now_iso(),
                    last_archive_id=archive_id,
                    last_attempt_outcome="success",
                )
                auto_completed = True
            except Exception as exc:
                return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "archive_id": archive_id,
        "action": status,
        "auto_completed": auto_completed,
        "best_match": best,
        "candidates": ordered,
        "suggestion": _match_suggestion_to_response(suggestion),
    }


@router.get("/api/v1/queues/{printer_id}/suggestions")
def list_queue_suggestions_v1(
    printer_id: str,
    request: Request,
    status: str | None = None,
) -> Any:
    state: AppState = request.app.state.model_catalog
    status_value = str(status or "").strip().lower() or None
    if status_value not in {None, "suggested", "auto_completed", "unmatched", "rejected", "remapped"}:
        return _error_response(
            status_code=400,
            error="validation_error",
            message="status must be one of suggested, auto_completed, unmatched, rejected, remapped",
        )

    try:
        suggestions = list_unified_queue_match_suggestions(
            db_path=state.settings.db_path,
            printer_id=printer_id,
            status=status_value,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "status": status_value,
        "suggestions": [_match_suggestion_to_response(item) for item in suggestions],
    }


@router.post("/api/v1/queues/{printer_id}/suggestions/{suggestion_id}/reject")
def reject_queue_suggestion_v1(
    printer_id: str,
    suggestion_id: str,
    request: Request,
) -> Any:
    state: AppState = request.app.state.model_catalog
    try:
        existing = read_unified_queue_match_suggestion(db_path=state.settings.db_path, suggestion_id=suggestion_id)
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if existing is None or existing.printer_id != printer_id:
        return _error_response(status_code=404, error="not_found", message="suggestion not found")

    try:
        updated = update_unified_queue_match_suggestion(
            db_path=state.settings.db_path,
            suggestion_id=suggestion_id,
            status="rejected",
            reviewed=True,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if updated is None:
        return _error_response(status_code=404, error="not_found", message="suggestion not found")

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "suggestion": _match_suggestion_to_response(updated),
    }


@router.post("/api/v1/queues/{printer_id}/suggestions/{suggestion_id}/remap")
def remap_queue_suggestion_v1(
    printer_id: str,
    suggestion_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    queue_entry_id = str(body.get("queue_entry_id") or "").strip()
    if not queue_entry_id:
        return _error_response(status_code=400, error="validation_error", message="queue_entry_id is required")

    try:
        existing = read_unified_queue_match_suggestion(db_path=state.settings.db_path, suggestion_id=suggestion_id)
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if existing is None or existing.printer_id != printer_id:
        return _error_response(status_code=404, error="not_found", message="suggestion not found")

    target = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    if target is None:
        return _error_response(status_code=404, error="not_found", message="target queue entry not found")

    try:
        update_unified_queue_entry(
            db_path=state.settings.db_path,
            queue_entry_id=queue_entry_id,
            state="done",
            completed_at=utc_now_iso(),
            last_archive_id=existing.archive_id,
            last_attempt_outcome="success",
        )
        updated = update_unified_queue_match_suggestion(
            db_path=state.settings.db_path,
            suggestion_id=suggestion_id,
            status="remapped",
            remapped_queue_entry_id=queue_entry_id,
            reviewed=True,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    if updated is None:
        return _error_response(status_code=404, error="not_found", message="suggestion not found")

    remapped_entry = read_unified_queue_entry(db_path=state.settings.db_path, queue_entry_id=queue_entry_id)
    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "suggestion": _match_suggestion_to_response(updated),
        "remapped_entry": _entry_to_response(remapped_entry) if remapped_entry is not None else None,
    }


def _compute_planner_scores_immutable(
    db_path: str,
    strategy: str,
    weights: dict[str, Any],
    ams_tray_uuids: object | None = None,
) -> tuple[bool, set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute planner scores for all queue entries WITHOUT persisting to DB.

    Returns: (ams_state_known, available_uuids, scored, ranked)
    - scored: list of score dicts with current_rank field
    - ranked: sorted list by planner score (what /plan compares against)
    """
    ams_state_known = True
    if ams_tray_uuids is None:
        ams_state_known = False
        available_uuids: set[str] = set()
    elif isinstance(ams_tray_uuids, list):
        available_uuids = {
            str(item).strip().lower()
            for item in ams_tray_uuids
            if str(item).strip()
        }
    else:
        raise ValueError("ams_tray_uuids must be an array of strings or null")

    entries = list_unified_queue_entries(db_path=db_path)
    scored: list[dict[str, Any]] = []
    for entry in entries:
        file_units = list_unified_queue_file_units(db_path=db_path, queue_entry_id=entry.queue_entry_id)
        estimated_minutes = _entry_estimated_minutes(entry, file_units)
        required_uuids = _extract_required_tray_uuids(file_units)

        if not ams_state_known:
            ams_fit = False
            ams_ready_score = 0
            ams_reason = "ams_state_unknown"
        elif not required_uuids:
            ams_fit = True
            ams_ready_score = 100
            ams_reason = "no_required_tray_uuids"
        else:
            ams_fit = required_uuids.issubset(available_uuids)
            ams_ready_score = 100 if ams_fit else 0
            ams_reason = "required_trays_available" if ams_fit else "missing_required_trays"

        overnight_fit = bool(estimated_minutes is not None and estimated_minutes <= 480)
        overnight_fit_score = 100 if overnight_fit else 0
        duration_bucket = _duration_bucket_for_minutes(estimated_minutes)
        duration_score = _duration_bucket_score_for_weights(duration_bucket, weights)
        planner_score = int(
            (weights.get("ams_fit", 0) if ams_fit else 0)
            + (weights.get("overnight_fit", 0) if overnight_fit else 0)
            + duration_score
        )

        scored.append(
            {
                "queue_entry_id": entry.queue_entry_id,
                "current_rank": entry.rank,
                "source_kind": entry.source_kind,
                "source_ref": entry.source_ref,
                "estimated_minutes": estimated_minutes,
                "required_tray_uuids": sorted(list(required_uuids)),
                "ams": {
                    "state_known": ams_state_known,
                    "fit": ams_fit,
                    "score": ams_ready_score,
                    "reason": ams_reason,
                },
                "overnight": {
                    "fit": overnight_fit,
                    "score": overnight_fit_score,
                    "window_hours": 8,
                },
                "duration": {
                    "bucket": duration_bucket,
                    "score": duration_score,
                },
                "planner_score": planner_score,
            }
        )

    ranked = sorted(
        scored,
        key=lambda item: (
            int(item["planner_score"]),
            int(item["ams"]["score"]),
            int(item["overnight"]["score"]),
            -_duration_bucket_weight(str(item["duration"]["bucket"])),
            str(item["queue_entry_id"]),
        ),
        reverse=True,
    )

    return ams_state_known, available_uuids, scored, ranked


@router.post("/api/v1/queues/{printer_id}/planner/score")
def planner_score_queue_entries_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Compute and persist planner scores for queue entries.

    Scoring dimensions:
    - AMS fit (binary): required tray UUIDs available now
    - Overnight fit (binary): estimated duration <= 8h
    - Duration bucket: quick/medium/overnight/marathon/unknown
    """
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    try:
        requested_strategy = _normalize_planner_strategy(body.get("strategy")) if "strategy" in body else None
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    persisted_pref = read_unified_queue_planner_preference(db_path=state.settings.db_path, printer_id=printer_id)
    active_strategy = requested_strategy or (persisted_pref.strategy if persisted_pref is not None else "balanced")

    # Weight resolution rules:
    # 1) custom_weights in request -> apply to active strategy
    # 2) explicit strategy in request (without custom_weights) -> strategy preset defaults
    # 3) no explicit strategy -> use persisted weights (or preset defaults when no persisted preference)
    if "custom_weights" in body:
        weights_source: object | None = body.get("custom_weights")
    elif requested_strategy is not None:
        weights_source = None
    else:
        weights_source = persisted_pref.weights if persisted_pref else None

    try:
        active_weights = _normalize_planner_weights(active_strategy, weights_source)
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    if requested_strategy is not None or "custom_weights" in body:
        try:
            upsert_unified_queue_planner_preference(
                db_path=state.settings.db_path,
                printer_id=printer_id,
                strategy=active_strategy,
                weights=active_weights,
            )
        except Exception as exc:
            return _error_response(status_code=500, error="internal_error", message=str(exc))

    ams_payload = body.get("ams_tray_uuids")
    ams_state_known = True
    if ams_payload is None:
        ams_state_known = False
        available_uuids: set[str] = set()
    elif isinstance(ams_payload, list):
        available_uuids = {
            str(item).strip().lower()
            for item in ams_payload
            if str(item).strip()
        }
    else:
        return _error_response(status_code=400, error="validation_error", message="ams_tray_uuids must be an array of strings")

    try:
        entries = list_unified_queue_entries(db_path=state.settings.db_path)
        scored: list[dict[str, Any]] = []
        for entry in entries:
            file_units = list_unified_queue_file_units(db_path=state.settings.db_path, queue_entry_id=entry.queue_entry_id)
            estimated_minutes = _entry_estimated_minutes(entry, file_units)
            required_uuids = _extract_required_tray_uuids(file_units)

            if not ams_state_known:
                ams_fit = False
                ams_ready_score = 0
                ams_reason = "ams_state_unknown"
            elif not required_uuids:
                ams_fit = True
                ams_ready_score = 100
                ams_reason = "no_required_tray_uuids"
            else:
                ams_fit = required_uuids.issubset(available_uuids)
                ams_ready_score = 100 if ams_fit else 0
                ams_reason = "required_trays_available" if ams_fit else "missing_required_trays"

            overnight_fit = bool(estimated_minutes is not None and estimated_minutes <= 480)
            overnight_fit_score = 100 if overnight_fit else 0
            duration_bucket = _duration_bucket_for_minutes(estimated_minutes)
            duration_score = _duration_bucket_score_for_weights(duration_bucket, active_weights)
            planner_score = int(
                (active_weights.get("ams_fit", 0) if ams_fit else 0)
                + (active_weights.get("overnight_fit", 0) if overnight_fit else 0)
                + duration_score
            )

            update_unified_queue_entry(
                db_path=state.settings.db_path,
                queue_entry_id=entry.queue_entry_id,
                ams_ready_score=ams_ready_score,
                overnight_fit_score=overnight_fit_score,
                duration_bucket=duration_bucket,
            )

            scored.append(
                {
                    "queue_entry_id": entry.queue_entry_id,
                    "source_kind": entry.source_kind,
                    "source_ref": entry.source_ref,
                    "estimated_minutes": estimated_minutes,
                    "required_tray_uuids": sorted(list(required_uuids)),
                    "ams": {
                        "state_known": ams_state_known,
                        "fit": ams_fit,
                        "score": ams_ready_score,
                        "reason": ams_reason,
                    },
                    "overnight": {
                        "fit": overnight_fit,
                        "score": overnight_fit_score,
                        "window_hours": 8,
                    },
                    "duration": {
                        "bucket": duration_bucket,
                        "score": duration_score,
                    },
                    "planner_score": planner_score,
                }
            )

        ranked = sorted(
            scored,
            key=lambda item: (
                int(item["planner_score"]),
                int(item["ams"]["score"]),
                int(item["overnight"]["score"]),
                -_duration_bucket_weight(str(item["duration"]["bucket"])),
                str(item["queue_entry_id"]),
            ),
            reverse=True,
        )

        for rank, row in enumerate(ranked):
            update_unified_queue_entry(
                db_path=state.settings.db_path,
                queue_entry_id=str(row["queue_entry_id"]),
                rank=rank,
            )
            row["recommended_rank"] = rank

    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "planner": {
            "ams_state_known": ams_state_known,
            "available_tray_uuids": sorted(list(available_uuids)),
            "entry_count": len(ranked),
            "strategy": active_strategy,
            "weights": active_weights,
        },
        "entries": ranked,
    }


@router.get("/api/v1/queues/{printer_id}/planner/strategy")
def get_planner_strategy_v1(
    printer_id: str,
    request: Request,
) -> Any:
    state: AppState = request.app.state.model_catalog
    try:
        saved = read_unified_queue_planner_preference(db_path=state.settings.db_path, printer_id=printer_id)
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    strategy = saved.strategy if saved is not None else "balanced"
    try:
        weights = _normalize_planner_weights(strategy, saved.weights if saved is not None else None)
    except ValueError as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "strategy": strategy,
        "weights": weights,
        "presets": PLANNER_STRATEGY_PRESETS,
        "persisted": saved is not None,
    }


@router.put("/api/v1/queues/{printer_id}/planner/strategy")
def set_planner_strategy_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    try:
        strategy = _normalize_planner_strategy(body.get("strategy"))
        weights = _normalize_planner_weights(strategy, body.get("custom_weights"))
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    try:
        saved = upsert_unified_queue_planner_preference(
            db_path=state.settings.db_path,
            printer_id=printer_id,
            strategy=strategy,
            weights=weights,
        )
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "strategy": saved.strategy,
        "weights": saved.weights,
        "presets": PLANNER_STRATEGY_PRESETS,
        "updated_at": saved.updated_at,
    }


@router.post("/api/v1/queues/{printer_id}/plan")
def plan_queue_reorder_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Generate optimal rank deltas using planner strategy without persisting.

    Returns delta (before/after) showing which entries would move and why.
    Does NOT persist changes until /apply called.
    """
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    try:
        requested_strategy = _normalize_planner_strategy(body.get("strategy")) if "strategy" in body else None
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    persisted_pref = read_unified_queue_planner_preference(db_path=state.settings.db_path, printer_id=printer_id)
    active_strategy = requested_strategy or (persisted_pref.strategy if persisted_pref is not None else "balanced")

    if "custom_weights" in body:
        weights_source: object | None = body.get("custom_weights")
    elif requested_strategy is not None:
        weights_source = None
    else:
        weights_source = persisted_pref.weights if persisted_pref else None

    try:
        active_weights = _normalize_planner_weights(active_strategy, weights_source)
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    try:
        ams_payload = body.get("ams_tray_uuids")
        ams_state_known, available_uuids, scored, ranked = _compute_planner_scores_immutable(
            db_path=state.settings.db_path,
            strategy=active_strategy,
            weights=active_weights,
            ams_tray_uuids=ams_payload,
        )
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    moves: list[dict[str, Any]] = []
    optimal_rank_map: dict[str, int] = {entry["queue_entry_id"]: idx for idx, entry in enumerate(ranked)}

    for entry in scored:
        entry_id = entry["queue_entry_id"]
        current_rank = entry["current_rank"]
        optimal_rank = optimal_rank_map.get(entry_id)

        if optimal_rank is not None and current_rank != optimal_rank:
            reason = ""
            if entry["ams"]["fit"] and entry["ams"]["score"] > 0:
                reason = "ams_ready"
            elif entry["overnight"]["fit"] and entry["overnight"]["score"] > 0:
                reason = "overnight_fit"
            elif entry["duration"]["score"] > 0:
                reason = f"duration_{entry['duration']['bucket']}"
            else:
                reason = "planner_score"

            moves.append(
                {
                    "id": entry_id,
                    "from_rank": current_rank,
                    "to_rank": optimal_rank,
                    "reason": reason,
                }
            )

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "strategy": active_strategy,
        "moves": moves,
        "move_count": len(moves),
        "ams_state_known": ams_state_known,
        "available_tray_uuids": sorted(list(available_uuids)),
    }


@router.post("/api/v1/queues/{printer_id}/plan/apply")
def apply_planner_delta_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Apply a planner delta, updating all ranks atomically and recording to audit log.

    Accepts optional delta from /plan endpoint to re-apply or accepts moves array directly.
    Records all changes in audit trail for undo support.
    """
    state: AppState = request.app.state.model_catalog
    if not isinstance(body, dict):
        return _error_response(status_code=400, error="invalid_payload", message="Request body must be a JSON object")

    try:
        requested_strategy = _normalize_planner_strategy(body.get("strategy")) if "strategy" in body else None
    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))

    # Fetch persisted preference or use defaults
    persisted_pref = read_unified_queue_planner_preference(db_path=state.settings.db_path, printer_id=printer_id)
    active_strategy = requested_strategy or (persisted_pref.strategy if persisted_pref is not None else "balanced")

    try:
        # Get current state before applying
        current_entries = list_unified_queue_entries(db_path=state.settings.db_path)
        current_rank_map = {entry.queue_entry_id: entry.rank for entry in current_entries}

        # Get delta from body or compute fresh delta
        if "moves" in body:
            moves = body.get("moves", [])
            if not isinstance(moves, list):
                return _error_response(status_code=400, error="validation_error", message="moves must be an array")
            delta = moves
        else:
            # Compute fresh delta using same strategy logic as /plan
            if "custom_weights" in body:
                weights_source: object | None = body.get("custom_weights")
            elif requested_strategy is not None:
                weights_source = None
            else:
                weights_source = persisted_pref.weights if persisted_pref else None

            active_weights = _normalize_planner_weights(active_strategy, weights_source)
            ams_payload = body.get("ams_tray_uuids")
            _, _, _, ranked = _compute_planner_scores_immutable(
                db_path=state.settings.db_path,
                strategy=active_strategy,
                weights=active_weights,
                ams_tray_uuids=ams_payload,
            )

            optimal_rank_map = {entry["queue_entry_id"]: idx for idx, entry in enumerate(ranked)}
            delta = []
            for entry in current_entries:
                optimal_rank = optimal_rank_map.get(entry.queue_entry_id)
                if optimal_rank is not None and entry.rank != optimal_rank:
                    delta.append({
                        "id": entry.queue_entry_id,
                        "from_rank": entry.rank,
                        "to_rank": optimal_rank,
                    })

        # Extract moved entry IDs
        moved_entry_ids = [str(move.get("id", "")) for move in delta if "id" in move]

        # Apply moves atomically
        rank_moves = []
        snapshots_data = []
        for move in delta:
            entry_id = str(move.get("id", "")).strip()
            to_rank = move.get("to_rank")
            if entry_id and to_rank is not None:
                rank_before = current_rank_map.get(entry_id, -1)
                rank_moves.append((entry_id, to_rank))
                snapshots_data.append((entry_id, rank_before, to_rank))

        if not rank_moves:
            return {
                "success": True,
                "contract": "unified-queue.v1",
                "printer_id": printer_id,
                "message": "no moves to apply",
                "audit_id": None,
            }

        changed_moves, missing_ids = reorder_unified_queue_entries(db_path=state.settings.db_path, moves=rank_moves)
        if missing_ids:
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"entries not found: {missing_ids}",
            )

        # Record in audit log
        audit = create_planner_operation_audit(
            db_path=state.settings.db_path,
            printer_id=printer_id,
            operation="apply",
            strategy=active_strategy,
            delta=delta,
            moved_entry_ids=moved_entry_ids,
            created_by=None,  # Could derive from request context
        )

        # Record rank snapshots
        create_planner_operation_snapshots(
            db_path=state.settings.db_path,
            audit_id=audit.id,
            snapshots=snapshots_data,
        )

    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "strategy": active_strategy,
        "applied_moves": len(delta),
        "audit_id": audit.id,
        "undo_available": True,
    }


@router.post("/api/v1/queues/{printer_id}/plan/undo")
def undo_planner_operation_v1(
    printer_id: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
) -> Any:
    """Undo the most recent planner operation by reverting to previous rank state.

    Restores ranks to their state before the most recent /apply call.
    Records undo as a separate audit entry for full history tracking.
    """
    state: AppState = request.app.state.model_catalog

    try:
        # Get most recent apply operation
        audits = list_planner_operation_audits(db_path=state.settings.db_path, printer_id=printer_id, limit=1)
        if not audits:
            return _error_response(
                status_code=404,
                error="not_found",
                message="no planner operations to undo",
            )

        last_audit = audits[0]
        if last_audit.operation != "apply":
            return _error_response(
                status_code=400,
                error="invalid_operation",
                message="can only undo recent apply operations",
            )

        # Get snapshots to restore previous ranks
        snapshots = read_planner_operation_snapshots(db_path=state.settings.db_path, audit_id=last_audit.id)
        if not snapshots:
            return _error_response(
                status_code=400,
                error="invalid_state",
                message="audit has no rank snapshots",
            )

        # Build undo moves (reverse the before/after)
        undo_moves = [(snap.queue_entry_id, snap.rank_before) for snap in snapshots]
        undo_delta = [
            {
                "id": snap.queue_entry_id,
                "from_rank": snap.rank_after,
                "to_rank": snap.rank_before,
                "reason": "undo",
            }
            for snap in snapshots
        ]

        # Apply undo moves
        changed_moves, missing_ids = reorder_unified_queue_entries(db_path=state.settings.db_path, moves=undo_moves)
        if missing_ids:
            return _error_response(
                status_code=400,
                error="validation_error",
                message=f"entries not found for undo: {missing_ids}",
            )

        # Record undo in audit log
        moved_entry_ids = [str(snap.queue_entry_id) for snap in snapshots]
        undo_audit = create_planner_operation_audit(
            db_path=state.settings.db_path,
            printer_id=printer_id,
            operation="undo",
            strategy=last_audit.strategy,
            delta=undo_delta,
            moved_entry_ids=moved_entry_ids,
            created_by=None,
        )

        # Record undo snapshots (for potential redo)
        undo_snapshots_data = [
            (snap.queue_entry_id, snap.rank_after, snap.rank_before)
            for snap in snapshots
        ]
        create_planner_operation_snapshots(
            db_path=state.settings.db_path,
            audit_id=undo_audit.id,
            snapshots=undo_snapshots_data,
        )

    except ValueError as exc:
        return _error_response(status_code=400, error="validation_error", message=str(exc))
    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "undone_moves": len(undo_delta),
        "restored_audit_id": last_audit.id,
        "undo_audit_id": undo_audit.id,
    }


@router.get("/api/v1/queues/{printer_id}/plan/history")
def list_planner_history_v1(
    printer_id: str,
    request: Request,
    limit: int = 5,
) -> Any:
    """List recent planner operations (apply/undo) with full audit trail."""
    state: AppState = request.app.state.model_catalog

    try:
        if limit < 1 or limit > 20:
            return _error_response(
                status_code=400,
                error="validation_error",
                message="limit must be between 1 and 20",
            )

        audits = list_planner_operation_audits(db_path=state.settings.db_path, printer_id=printer_id, limit=limit)
        history = []
        for audit in audits:
            snapshots = read_planner_operation_snapshots(db_path=state.settings.db_path, audit_id=audit.id)
            history.append({
                "id": audit.id,
                "operation": audit.operation,
                "strategy": audit.strategy,
                "moved_entry_count": len(audit.moved_entry_ids),
                "snapshots_count": len(snapshots),
                "created_at": audit.created_at,
                "created_by": audit.created_by,
            })

    except Exception as exc:
        return _error_response(status_code=500, error="internal_error", message=str(exc))

    return {
        "success": True,
        "contract": "unified-queue.v1",
        "printer_id": printer_id,
        "history": history,
        "history_count": len(history),
    }

