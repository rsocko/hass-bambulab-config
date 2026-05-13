"""
Intake verification workflow endpoints.

Handles:
- Intake item submission and workflow (submit, validate, defer, reject, group)
- Item lifecycle in working groups
- Validation state tracking
- Action eligibility enforcement
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..state import AppState
from .._helpers import (
    LOCAL_IMPORT_IMAGE_EXTENSIONS,
    _bulk_path_source_metadata,
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_utc_now_iso,
    _compile_source_entry_exclusions,
    _coerce_bool,
    _collect_intake_source_files_in_folder,
    _configured_working_files_roots,
    _enforce_source_entries_within_intake_roots,
    _is_excluded_source_file,
    _normalize_path_compare_key,
)
from ..services import get_all_indexed_file_hashes
from ..services.shared_helpers import _serialize_working_group, _sha256_file, _slugify_title
from ..services.intake_consolidation import _consolidate_overlapping_selections
from ..services.intake_eligibility_service import ActionEligibility
from ..services.intake_grouping import _prefilter_excluded_items

from .intake_queue import (
    _expand_source_entries_to_files,
    _record_queue_event,
    _browser_upload_stage_directories,
    _derive_terminal_display_action,
    _normalize_terminal_actor,
    _normalize_terminal_result,
    SUPPORTED_INTAKE_FILE_EXTENSIONS,
)

router = APIRouter(tags=["intake"])


def _canonical_source_entries(source_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _consolidate_overlapping_selections(
        [entry for entry in source_entries if isinstance(entry, dict)]
    )


# ==================== HELPER FUNCTIONS ====================

def _get_intake_item_row(db_path: Path, item_id: str) -> dict[str, Any] | None:
    """Fetch a single intake item row from database."""
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                                 source_entries_json, file_hashes_json, error_json, decision_note,
                                     terminal_action, terminal_result_id, terminal_at, terminal_actor,
                                     created_at, updated_at
            FROM intake_queue_uploads
            WHERE upload_id = ?
            """,
            (item_id,),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        connection.close()


def _build_intake_item_response(item_row: dict[str, Any]) -> dict[str, Any]:
    """Build a response payload for an intake item with eligibility information."""
    current_state = str(item_row.get("inbox_state") or "submitted").strip().lower()
    eligibility = ActionEligibility.build_allowed_actions_payload(current_state)
    terminal_action = item_row.get("terminal_action")
    terminal_result_id = item_row.get("terminal_result_id")

    return {
        "item_id": item_row["upload_id"],
        "status": item_row["status"],
        "state": current_state,
        "verification_status": item_row["verification_status"],
        "cleanup_policy": item_row["cleanup_policy"],
        "is_terminal": eligibility["is_terminal"],
        "is_active_queue": eligibility["is_active_queue"],
        "allowed_actions": eligibility["allowed_actions"],
        "state_display_name": eligibility["state_display_name"],
        "terminal_action": terminal_action,
        "terminal_display_action": _derive_terminal_display_action(terminal_action, terminal_result_id),
        "terminal_result_id": terminal_result_id,
        "terminal_result": _normalize_terminal_result(terminal_action, terminal_result_id),
        "terminal_at": item_row.get("terminal_at"),
        "terminal_actor": _normalize_terminal_actor(item_row.get("terminal_actor"), fallback="queue_processed"),
        "created_at": item_row["created_at"],
        "updated_at": item_row["updated_at"],
    }



@router.post("/api/intake/plan")
def plan_intake_groups(request: Request, payload: dict[str, Any] | None = None) -> Any:
    payload = payload or {}
    upload_id = str(payload.get("upload_id") or "").strip()
    source_entries = payload.get("source_entries")

    if upload_id:
        item_row = _get_intake_item_row(request.app.state.model_catalog.settings.db_path, upload_id)
        if item_row is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "item_not_found",
                    "message": f"No intake item found: {upload_id}",
                },
            )
        source_entries = json.loads(str(item_row.get("source_entries_json") or "[]"))

    if not isinstance(source_entries, list) or not source_entries:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Provide upload_id or a non-empty source_entries array.",
            },
        )

    # Strict allowlist enforcement: every server-mode source entry must resolve
    # within the intake roots configured for the active DB profile (prod/test).
    # This is the deterministic guard that prevents cross-profile path leakage
    # even if a stale browser cache or buggy client sends the wrong root.
    rejection_message = _enforce_source_entries_within_intake_roots(
        request.app.state.model_catalog.settings,
        source_entries,
    )
    if rejection_message is not None:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "path_not_allowed",
                "message": rejection_message,
            },
        )

    normalized_entries = _canonical_source_entries(source_entries)
    expanded_files, warnings = _expand_intake_source_entries(source_entries=normalized_entries)
    
    # Extract excluded_items from source entries and filter out excluded files
    excluded_items = []
    for entry in normalized_entries:
        if isinstance(entry, dict) and entry.get("excluded_items"):
            excluded_list = entry.get("excluded_items")
            if isinstance(excluded_list, list):
                excluded_items.extend(excluded_list)
    
    if excluded_items:
        expanded_files = _prefilter_excluded_items(expanded_files, excluded_items)
    
    plan = _plan_intake_groups(source_entries=normalized_entries, expanded_files=expanded_files)
    return {
        "success": True,
        "contract": "intake-plan.v1alpha1",
        "upload_id": upload_id or None,
        "warnings": warnings,
        "planned_models": plan.get("planned_models", []),
        "summary": plan.get("summary", {}),
    }

def _check_action_eligibility(item_row: dict[str, Any], action: str, override: bool = False) -> tuple[bool, str | None]:
    """
    Check if an action is eligible for the current item state.
    
    Returns (is_eligible: bool, reason_code: str | None).
    """
    current_state = str(item_row.get("inbox_state") or "submitted").strip().lower()
    warning_codes: set[str] = set()
    decision_note_raw = item_row.get("decision_note")
    if isinstance(decision_note_raw, str) and decision_note_raw.strip():
        try:
            decision_note_payload = json.loads(decision_note_raw)
        except json.JSONDecodeError:
            decision_note_payload = None
        if isinstance(decision_note_payload, list):
            warning_codes = {
                str(warning.get("code") or "").strip().lower()
                for warning in decision_note_payload
                if isinstance(warning, dict) and str(warning.get("code") or "").strip()
            }
    
    # Check basic eligibility
    is_eligible, reason = ActionEligibility.validate_action_eligibility(current_state, action)
    if not is_eligible:
        return False, reason
    
    # Check override requirement for warning state
    if action in {ActionEligibility.GROUP_NEW, ActionEligibility.GROUP_EXISTING}:
        source_warning_codes = {"missing_source", "source_unreadable", "unsupported_type"}
        if current_state == "validated_warning" and warning_codes and warning_codes.issubset(source_warning_codes):
            return True, None
        is_valid_override, override_reason = ActionEligibility.validate_override_for_warning_state(
            current_state, action, override
        )
        if not is_valid_override:
            return False, override_reason
    
    return True, None

def _expand_intake_source_entries(*, source_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand source entries into individual files with validation."""
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    exclusion_exact_keys, exclusion_folder_prefixes = _compile_source_entry_exclusions(source_entries)

    for entry in source_entries:
        entry_type = str(entry.get("type") or "").strip().lower()
        source_path_raw = str(entry.get("path") or "").strip()
        if entry_type not in {"file", "folder"} or not source_path_raw:
            continue

        source_path = Path(source_path_raw).expanduser().resolve()
        if entry_type == "file":
            candidate_paths = [source_path]
        else:
            recurse = _coerce_bool(entry.get("recurse", True))
            candidate_paths = _collect_intake_source_files_in_folder(source_path, recurse=recurse)

        # Track how many files this specific entry contributes so we can emit a
        # diagnostic warning when an explicit folder/file selection yields zero
        # eligible files. Without this, the wizard's "Choose Destination" step
        # silently dead-ends with "No planned groups available yet" and the
        # operator has no clue why their selection produced no models.
        entry_expanded_before = len(expanded)
        entry_warnings_before = len(warnings)

        for file_path in sorted(candidate_paths):
            normalized_path = str(file_path.resolve())
            if normalized_path in seen_paths:
                continue
            if _is_excluded_source_file(
                file_path=file_path,
                exclusion_exact_keys=exclusion_exact_keys,
                exclusion_folder_prefixes=exclusion_folder_prefixes,
            ):
                continue
            if file_path.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
                warnings.append(
                    {
                        "code": "unsupported_type",
                        "message": f"Unsupported extension: {file_path.suffix.lower() or '<none>'}",
                        "path": normalized_path,
                    }
                )
                continue
            if not file_path.exists() or not file_path.is_file():
                warnings.append(
                    {
                        "code": "missing_source",
                        "message": f"Source file not found: {file_path}",
                        "path": normalized_path,
                    }
                )
                continue

            try:
                stat_result = file_path.stat()
                file_hash = _sha256_file(file_path).lower()
            except (OSError, PermissionError) as exc:
                warnings.append(
                    {
                        "code": "source_unreadable",
                        "message": f"Could not read source file: {file_path} ({exc})",
                        "path": normalized_path,
                    }
                )
                continue

            # Compute relative path for folder structure preservation
            relative_path: str = file_path.name
            if entry_type == "folder":
                try:
                    relative_path = str(file_path.relative_to(source_path))
                except ValueError:
                    relative_path = file_path.name
            
            source_metadata = _bulk_path_source_metadata(file_path, stat_result)
            if entry_type == "file":
                for key in ("source_mtime", "source_ctime", "source_birthtime"):
                    override_value = str(entry.get(key) or "").strip()
                    if override_value:
                        source_metadata[key] = override_value

            expanded.append(
                {
                    "path": normalized_path,
                    "relative_path": relative_path,
                    "filename": file_path.name,
                    "entry_type": entry_type,
                    "source_entry": entry,
                    "source_metadata": source_metadata,
                    "file_hash": file_hash,
                    "size_bytes": int(stat_result.st_size),
                }
            )
            seen_paths.add(normalized_path)

        # Diagnostic: if this entry contributed zero files AND produced no
        # per-file warning of its own (unsupported_type / missing_source /
        # source_unreadable), surface a "no_eligible_files" warning so the
        # wizard's destination step can explain the empty plan instead of
        # silently dead-ending.
        if (
            len(expanded) == entry_expanded_before
            and len(warnings) == entry_warnings_before
        ):
            if entry_type == "folder":
                message = (
                    f"Folder contains no eligible model files: {source_path_raw}"
                )
            else:
                message = (
                    f"Source contains no eligible model files: {source_path_raw}"
                )
            warnings.append(
                {
                    "code": "no_eligible_files",
                    "message": message,
                    "path": str(source_path),
                }
            )

    return expanded, warnings


def _source_timestamp_summary(files: list[dict[str, Any]]) -> dict[str, Any]:
    mtimes = [
        str((item.get("source_metadata") or {}).get("source_mtime") or "").strip()
        for item in files
        if isinstance(item, dict)
    ]
    ctimes = [
        str((item.get("source_metadata") or {}).get("source_ctime") or "").strip()
        for item in files
        if isinstance(item, dict)
    ]
    birthtimes = [
        str((item.get("source_metadata") or {}).get("source_birthtime") or "").strip()
        for item in files
        if isinstance(item, dict)
    ]
    mtimes = sorted([value for value in mtimes if value])
    ctimes = sorted([value for value in ctimes if value])
    birthtimes = sorted([value for value in birthtimes if value])

    summary: dict[str, Any] = {
        "file_count": len(files),
        "earliest_source_mtime": mtimes[0] if mtimes else None,
        "latest_source_mtime": mtimes[-1] if mtimes else None,
        "earliest_source_ctime": ctimes[0] if ctimes else None,
        "latest_source_ctime": ctimes[-1] if ctimes else None,
    }
    if birthtimes:
        summary["earliest_source_birthtime"] = birthtimes[0]
        summary["latest_source_birthtime"] = birthtimes[-1]
    return summary


def _read_existing_working_hashes(db_path: Path) -> set[str]:
    """Get all file hashes from existing working items."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hash FROM working_items WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''"
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    finally:
        connection.close()


def _normalized_duplicate_name(filename: str) -> str:
    """Normalize filename variants so re-download copies map to a common key."""
    stem = Path(str(filename or "")).stem.strip().lower()
    if not stem:
        return ""

    candidate = re.sub(r"[_\-.]+", " ", stem)
    candidate = re.sub(r"\s+", " ", candidate).strip()

    copy_suffix_patterns = (
        r"\s*\(\d+\)$",  # common browser suffix: "model (2)"
        r"\s*(?:-|_)?copy(?:\s*\(\d+\))?$",  # copy, copy (2), -copy
    )
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        for pattern in copy_suffix_patterns:
            candidate = re.sub(pattern, "", candidate).strip()

    return re.sub(r"\s+", " ", candidate).strip()


_DISPLAY_TITLE_STRIPPABLE_SUFFIXES = {
    ".3mf",
    ".stl",
    ".step",
    ".stp",
    ".obj",
    ".amf",
    ".ply",
    ".gcode",
    ".bgcode",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
}


def _display_title_from_path(path_value: str | None) -> str:
    """Derive a user-facing title from a filename or folder name."""
    normalized = str(path_value or "").replace("\\", "/").strip()
    if not normalized:
        return ""

    name = Path(normalized).name.strip()
    if not name:
        return ""

    candidate = name
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        suffix = Path(candidate).suffix.lower()
        if suffix not in _DISPLAY_TITLE_STRIPPABLE_SUFFIXES:
            break
        candidate = Path(candidate).stem

    candidate = re.sub(r"[_\-.]+", " ", candidate)
    candidate = re.sub(r"\s*\(\d+\)$", "", candidate)
    candidate = re.sub(r"\s*(?:-|_)?copy(?:\s*\(\d+\))?$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s+", " ", candidate).strip(" -_.")
    if not candidate:
        candidate = Path(name).stem or name

    # Strip trailing slicer/tool noise tokens (e.g. "my_model_sliced_v2_plate1" → "my model")
    _NOISE_SUFFIX = re.compile(
        r"\s+(?:sliced|final|remix|fixed|updated|wip|draft|test|plate\s*\d+|v\d+(?:\.\d+)*)$",
        re.IGNORECASE,
    )
    while True:
        stripped = _NOISE_SUFFIX.sub("", candidate).strip(" -_.")
        if not stripped or stripped == candidate:
            break
        candidate = stripped

    letters_only = re.sub(r"[^A-Za-z]+", "", candidate)
    if letters_only and (letters_only == letters_only.lower() or letters_only == letters_only.upper()):
        words: list[str] = []
        for part in candidate.split(" "):
            if re.fullmatch(r"\d+d", part, flags=re.IGNORECASE):
                words.append(f"{part[:-1]}D")
            else:
                words.append(part.capitalize())
        candidate = " ".join(words)

    return candidate.strip()


def _read_indexed_filename_maps(
    db_path: Path,
    *,
    exclude_upload_id: str | None = None,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Build exact+soft filename indexes from working, queue, and catalog assets."""
    exact_map: dict[str, set[str]] = {}
    normalized_map: dict[str, set[str]] = {}

    def _add_filename(raw_name: object) -> None:
        name = str(raw_name or "").strip().replace("\\", "/")
        if not name:
            return
        base_name = Path(name).name or name
        if not base_name:
            return
        exact_key = base_name.lower()
        exact_map.setdefault(exact_key, set()).add(base_name)
        normalized_key = _normalized_duplicate_name(base_name)
        if normalized_key:
            normalized_map.setdefault(normalized_key, set()).add(base_name)

    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_path FROM working_items WHERE file_path IS NOT NULL AND TRIM(file_path) != ''"
        ).fetchall()
        for row in rows:
            _add_filename(row[0])

        if exclude_upload_id:
            queue_rows = connection.execute(
                """
                SELECT source_entries_json
                FROM intake_queue_uploads
                WHERE source_entries_json IS NOT NULL
                  AND upload_id != ?
                """,
                (exclude_upload_id,),
            ).fetchall()
        else:
            queue_rows = connection.execute(
                "SELECT source_entries_json FROM intake_queue_uploads WHERE source_entries_json IS NOT NULL"
            ).fetchall()

        for row in queue_rows:
            payload = str(row[0] or "").strip()
            if not payload:
                continue
            try:
                entries = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_type = str(entry.get("type") or "").strip().lower()
                if entry_type == "folder":
                    continue
                _add_filename(entry.get("filename") or entry.get("relative_path") or entry.get("path"))

        try:
            asset_rows = connection.execute(
                "SELECT asset_filename FROM model_catalog_assets WHERE asset_filename IS NOT NULL AND TRIM(asset_filename) != ''"
            ).fetchall()
        except sqlite3.OperationalError:
            asset_rows = []
        for row in asset_rows:
            _add_filename(row[0])
    finally:
        connection.close()

    return exact_map, normalized_map


def _build_validation_checks(
    *,
    warning_codes: set[str],
    expanded_files: list[dict[str, Any]],
    duplicate_hashes: list[str],
    duplicate_name_exact_count: int = 0,
    duplicate_name_soft_count: int = 0,
    source_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    resolved_count = len(expanded_files)
    duplicate_count = len(duplicate_hashes)
    
    # Extract excluded items from all source entries
    excluded_files_count = 0
    excluded_folders_count = 0
    if source_entries:
        all_excluded_items: set[str] = set()
        for entry in source_entries:
            if not isinstance(entry, dict):
                continue
            excluded_items = entry.get("excluded_items") or []
            if isinstance(excluded_items, list):
                all_excluded_items.update(excluded_items)
        
        # Count files vs folders (folders typically end with / or are detected as dir paths)
        # For simplicity, count total excluded items and note that some may be folders
        total_excluded = len(all_excluded_items)
        if total_excluded > 0:
            # Estimate: assume folders are roughly 20% of exclusions (can be refined)
            # In practice, we count items; the UI can distinguish if needed
            excluded_files_count = total_excluded
    
    checks: list[dict[str, Any]] = [
        {
            "key": "source_access",
            "label": "Selected sources are present and readable",
            "passed": not ({"missing_source", "source_unreadable"} & warning_codes),
            "detail": (
                f"Resolved {resolved_count} file(s) for validation."
                if not ({"missing_source", "source_unreadable"} & warning_codes)
                else "One or more selected source files are missing or unreadable."
            ),
        },
        {
            "key": "supported_types",
            "label": "Resolved files use supported model or image types",
            "passed": "unsupported_type" not in warning_codes,
            "detail": (
                "All resolved files use supported extensions."
                if "unsupported_type" not in warning_codes
                else "One or more selected files use unsupported extensions."
            ),
        },
        {
            "key": "duplicate_scan",
            "label": "Resolved files do not match existing indexed files (hard/soft)",
            "passed": not (
                {"working_group_hash_match", "duplicate_name_exact_match", "duplicate_name_soft_match"}
                & warning_codes
            ),
            "detail": (
                "No duplicate hard or soft filename matches were detected."
                if not (
                    {"working_group_hash_match", "duplicate_name_exact_match", "duplicate_name_soft_match"}
                    & warning_codes
                )
                else (
                    "Detected "
                    + ", ".join(
                        [
                            segment
                            for segment in [
                                f"{duplicate_count} hard hash match(es)" if duplicate_count else "",
                                f"{duplicate_name_exact_count} exact filename match(es)" if duplicate_name_exact_count else "",
                                f"{duplicate_name_soft_count} soft filename variant match(es)" if duplicate_name_soft_count else "",
                            ]
                            if segment
                        ]
                    )
                    + " in indexed inventory."
                )
            ),
        },
        {
            "key": "commit_ready",
            "label": "Resolved plan contains at least one file to commit",
            "passed": bool(expanded_files) and "needs_manual_grouping" not in warning_codes,
            "detail": (
                f"Prepared upload contains {resolved_count} resolved file(s)."
                if expanded_files and "needs_manual_grouping" not in warning_codes
                else "No files were resolved from the selected sources."
            ),
        },
        {
            "key": "excluded_items_summary",
            "label": "Exclusion summary",
            "passed": True,  # Informational only - never blocks commit
            "detail": (
                f"{excluded_files_count} items excluded from selected sources. Proceeding with {resolved_count} remaining items for import."
                if excluded_files_count > 0
                else "No items excluded."
            ),
            # Issue #1347: surface the count so the wizard chip shows "N excluded"
            # instead of a misleading generic "pass" badge.
            "excluded_count": excluded_files_count,
        },
    ]
    
    return checks


def _intake_item_state_from_upload_status(status: str) -> str:
    """Map queue status to inbox state."""
    normalized = str(status or "").strip().lower()
    if normalized == "queued":
        return "submitted"
    if normalized in {"uploading", "uploaded_unverified"}:
        return "processing"
    if normalized == "verified":
        return "validated_ready"
    if normalized == "cleanup_pending":
        return "grouping"
    if normalized == "cleanup_done":
        return "grouped"
    if normalized == "cleanup_failed":
        return "validated_warning"
    if normalized == "failed":
        return "rejected"
    return "submitted"


def _existing_working_slugs(connection: Any) -> set[str]:
    """Get all existing working group slugs."""
    rows = connection.execute("SELECT slug FROM working_groups").fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _unique_slug(connection: Any, title: str) -> str:
    """Generate a unique slug for a new working group."""
    base = _slugify_title(title)
    existing = _existing_working_slugs(connection)
    if base not in existing:
        return base
    counter = 2
    while True:
        candidate = f"{base}-{counter}"
        if candidate not in existing:
            return candidate
        counter += 1
def _default_group_title(source_entries: list[dict[str, Any]], expanded_files: list[dict[str, Any]]) -> str:
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        hinted_title = str(entry.get("group_title") or "").strip()
        if hinted_title:
            return hinted_title

    first_entry = source_entries[0] if source_entries else {}
    first_entry_path = Path(str(first_entry.get("path") or "")) if isinstance(first_entry, dict) else Path()
    title_source = str(first_entry.get("group_title_source") or "").strip().lower().replace("_", "-") if isinstance(first_entry, dict) else ""

    if title_source == "folder" and str(first_entry.get("type") or "") == "folder":
        return _display_title_from_path(first_entry_path.name or str(first_entry_path)) or "Working Group"

    if title_source == "first-file":
        return _display_title_from_path(str(expanded_files[0].get("filename") or expanded_files[0].get("path") or "")) or "Working Group"

    if str(first_entry.get("type") or "") == "folder":
        return _display_title_from_path(first_entry_path.name or str(first_entry_path)) or "Working Group"

    return _display_title_from_path(str(expanded_files[0].get("filename") or expanded_files[0].get("path") or "")) or "Working Group"


def _normalize_grouping_strategy(value: object | None) -> str:
    """Normalize grouping strategy value."""
    normalized = str(value or "").strip().lower()
    if normalized == "by-file":
        normalized = "flat"
    if normalized in {"by-folder", "by-root", "flat", "none"}:
        return normalized
    return "none"


def _classify_intake_file_kind(file_item: dict[str, Any]) -> str:
    suffix = Path(str(file_item.get("filename") or file_item.get("path") or "")).suffix.lower()
    if suffix in SUPPORTED_WORKING_FILE_EXTENSIONS:
        return "model"
    if suffix in LOCAL_IMPORT_IMAGE_EXTENSIONS:
        return "media"
    return "supporting"


def _is_printable_intake_file(file_item: dict[str, Any]) -> bool:
    return _classify_intake_file_kind(file_item) == "model"


def _common_prefix_length(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    count = 0
    for left_part, right_part in zip(left, right):
        if left_part != right_part:
            break
        count += 1
    return count

def _relative_parts_for_matching(file_item: dict[str, Any]) -> tuple[str, ...]:
    relative_path = str(file_item.get("relative_path") or file_item.get("filename") or "").replace("\\", "/")
    if not relative_path:
        return ()
    return tuple(part.lower() for part in Path(relative_path).parts if str(part).strip())


def _normalize_effective_grouping_strategy(
    *,
    entry_type: str,
    requested_strategy: object | None,
    batch_files: list[dict[str, Any]],
) -> str:
    strategy = _normalize_grouping_strategy(requested_strategy)
    if strategy == "flat" and not any(_is_printable_intake_file(file_item) for file_item in batch_files):
        return "none"
    return strategy


def _find_flat_group_anchor(
    *,
    file_item: dict[str, Any],
    printable_group_keys: list[str],
    printable_files_by_key: dict[str, dict[str, Any]],
) -> str | None:
    file_parts = _relative_parts_for_matching(file_item)
    file_parent_parts = file_parts[:-1]
    best_key: str | None = None
    best_score: tuple[int, int, int] | None = None
    for group_key in printable_group_keys:
        printable_file = printable_files_by_key[group_key]
        printable_parts = _relative_parts_for_matching(printable_file)
        printable_parent_parts = printable_parts[:-1]
        prefix_score = _common_prefix_length(file_parent_parts, printable_parent_parts)
        same_parent_score = 1 if file_parent_parts == printable_parent_parts else 0
        depth_delta = abs(len(file_parent_parts) - len(printable_parent_parts))
        candidate_score = (same_parent_score, prefix_score, -depth_delta)
        if best_score is None or candidate_score > best_score:
            best_key = group_key
            best_score = candidate_score
    return best_key


def _plan_flat_file_groups(
    *,
    batch_files: list[dict[str, Any]],
    source_entry: dict[str, Any],
    root_path: Path,
) -> dict[str, dict[str, Any]]:
    printable_files = [file_item for file_item in batch_files if _is_printable_intake_file(file_item)]
    if not printable_files:
        first_file = Path(str(batch_files[0]["path"])).resolve()
        return {
            "__single__": {
                "title": _compute_group_title(
                    group_key="__single__",
                    root_path=root_path,
                    file_path=first_file,
                    strategy="none",
                    source_entry=source_entry,
                ),
                "files": list(batch_files),
                "strategy": "none",
                "source_entry": source_entry,
                "root_path": str(root_path),
                "preserve_folder_structure": _coerce_bool(source_entry.get("preserve_folder_structure", True)),
                "group_title": str(source_entry.get("group_title") or "").strip(),
            }
        }

    groups_by_key: dict[str, dict[str, Any]] = {}
    printable_files_by_key: dict[str, dict[str, Any]] = {}
    for file_item in printable_files:
        file_source_entry = file_item.get("source_entry") if isinstance(file_item.get("source_entry"), dict) else source_entry
        file_path = Path(str(file_item["path"])).resolve()
        relative_path = str(file_item.get("relative_path") or file_item.get("filename") or "").replace("\\", "/")
        group_key = relative_path or str(file_path)
        printable_files_by_key[group_key] = file_item
        groups_by_key[group_key] = {
            "title": _compute_group_title(
                group_key=group_key,
                root_path=root_path,
                file_path=file_path,
                strategy="flat",
                source_entry=file_source_entry,
            ),
            "files": [file_item],
            "strategy": "flat",
            "source_entry": file_source_entry,
            "root_path": str(root_path),
            "preserve_folder_structure": _coerce_bool(file_source_entry.get("preserve_folder_structure", True)),
            "group_title": str(file_source_entry.get("group_title") or "").strip(),
        }

    printable_group_keys = list(groups_by_key.keys())
    for file_item in batch_files:
        if _is_printable_intake_file(file_item):
            continue
        anchor_key = _find_flat_group_anchor(
            file_item=file_item,
            printable_group_keys=printable_group_keys,
            printable_files_by_key=printable_files_by_key,
        )
        if anchor_key is None:
            anchor_key = printable_group_keys[0]
        groups_by_key[anchor_key]["files"].append(file_item)

    return groups_by_key


def _merge_planned_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    # Issue #1341: 'none' (a.k.a. "Group with the batch") means every selection
    # in the batch that picks this strategy collapses into a single planned
    # model -- regardless of whether the user customized per-entry titles. The
    # merged title prefers the first non-empty explicit group_title we
    # encounter; if none of the merged entries set one, we keep the existing
    # default title that was already populated on the first group.
    for group in groups:
        explicit_title = str(group.get("group_title") or "").strip()
        effective_strategy = str(group.get("strategy") or "none").strip() or "none"
        if effective_strategy == "none":
            merge_key = "none::__batch__"
        else:
            merge_key = str(group.get("plan_group_id") or uuid.uuid4())
        existing = merged_by_key.get(merge_key)
        if existing is None:
            next_group = dict(group)
            next_group["files"] = list(group.get("files") or [])
            next_group["source_entries"] = list(group.get("source_entries") or [])
            merged_by_key[merge_key] = next_group
            ordered_keys.append(merge_key)
            continue
        existing["files"].extend(group.get("files") or [])
        existing["source_entries"].extend(group.get("source_entries") or [])
        existing["preserve_folder_structure"] = bool(existing.get("preserve_folder_structure")) or bool(group.get("preserve_folder_structure"))
        # Upgrade the merged group's title if a later 'none' entry carries an
        # explicit user-set group_title and the existing merged group still
        # holds only a derived/default title.
        if effective_strategy == "none" and explicit_title:
            existing_explicit_title = str(existing.get("group_title") or "").strip()
            if not existing_explicit_title:
                existing["group_title"] = explicit_title
                existing["title"] = explicit_title
    return [merged_by_key[key] for key in ordered_keys]


def _summarize_planned_group(group: dict[str, Any]) -> dict[str, Any]:
    files = sorted(
        list(group.get("files") or []),
        key=lambda item: str(item.get("relative_path") or item.get("filename") or item.get("path") or "").lower(),
    )
    model_files = 0
    media_files = 0
    supporting_files = 0
    summarized_files: list[dict[str, Any]] = []
    for file_item in files:
        file_kind = _classify_intake_file_kind(file_item)
        if file_kind == "model":
            model_files += 1
        elif file_kind == "media":
            media_files += 1
        else:
            supporting_files += 1
        summarized_files.append(
            {
                "path": str(file_item.get("path") or ""),
                "relative_path": str(file_item.get("relative_path") or file_item.get("filename") or ""),
                "filename": str(file_item.get("filename") or Path(str(file_item.get("path") or "")).name),
                "kind": file_kind,
                "size_bytes": int(file_item.get("size_bytes") or 0),
                "source_entry_type": str((file_item.get("source_entry") or {}).get("type") or file_item.get("entry_type") or ""),
                "source_entry_path": str((file_item.get("source_entry") or {}).get("path") or ""),
            }
        )
    summarized_group = dict(group)
    summarized_group["files"] = summarized_files
    summarized_group["file_count"] = len(summarized_files)
    summarized_group["model_file_count"] = model_files
    summarized_group["media_file_count"] = media_files
    summarized_group["supporting_file_count"] = supporting_files
    summarized_group["source_entry_count"] = len(group.get("source_entries") or [])
    return summarized_group


def _plan_intake_groups(
    *,
    source_entries: list[dict[str, Any]],
    expanded_files: list[dict[str, Any]],
) -> dict[str, Any]:
    file_entries = [entry for entry in source_entries if isinstance(entry, dict) and str(entry.get("type") or "").strip().lower() == "file"]
    folder_entries = [entry for entry in source_entries if isinstance(entry, dict) and str(entry.get("type") or "").strip().lower() == "folder"]
    planned_groups: list[dict[str, Any]] = []

    if file_entries:
        file_batch_files = [file_item for file_item in expanded_files if str((file_item.get("source_entry") or {}).get("type") or "").strip().lower() == "file"]
        if file_batch_files:
            representative_entry = dict(file_entries[0])
            effective_strategy = _normalize_effective_grouping_strategy(
                entry_type="file",
                requested_strategy=representative_entry.get("grouping_strategy"),
                batch_files=file_batch_files,
            )
            root_path = Path(str(file_batch_files[0].get("path") or representative_entry.get("path") or "")).resolve().parent
            grouped = _plan_flat_file_groups(
                batch_files=file_batch_files,
                source_entry=representative_entry,
                root_path=root_path,
            ) if effective_strategy == "flat" else _group_files_by_strategy(
                expanded_files=file_batch_files,
                source_entries=file_entries,
                strategy=effective_strategy,
            )
            for group_key, group in grouped.items():
                planned_groups.append(
                    {
                        "plan_group_id": f"files::{group_key}",
                        "title": str(group.get("title") or _default_group_title(file_entries, file_batch_files)),
                        "strategy": effective_strategy,
                        "preserve_folder_structure": _coerce_bool(representative_entry.get("preserve_folder_structure", True)),
                        "group_title": str(representative_entry.get("group_title") or "").strip(),
                        "source_entries": list(file_entries),
                        "files": list(group.get("files") or []),
                    }
                )

    for entry in folder_entries:
        entry_files = [file_item for file_item in expanded_files if file_item.get("source_entry") is entry]
        if not entry_files:
            continue
        effective_strategy = _normalize_effective_grouping_strategy(
            entry_type="folder",
            requested_strategy=entry.get("grouping_strategy"),
            batch_files=entry_files,
        )
        entry_root = Path(str(entry.get("path") or entry_files[0].get("path") or "")).resolve()
        grouped = _plan_flat_file_groups(
            batch_files=entry_files,
            source_entry=entry,
            root_path=entry_root,
        ) if effective_strategy == "flat" else _group_files_by_strategy(
            expanded_files=entry_files,
            source_entries=[entry],
            strategy=effective_strategy,
        )
        for group_key, group in grouped.items():
            planned_groups.append(
                {
                    "plan_group_id": f"folder::{entry_root}::{group_key}",
                    "title": str(group.get("title") or _default_group_title([entry], entry_files)),
                    "strategy": effective_strategy,
                    "preserve_folder_structure": _coerce_bool(entry.get("preserve_folder_structure", True)),
                    "group_title": str(entry.get("group_title") or "").strip(),
                    "source_entries": [entry],
                    "files": list(group.get("files") or []),
                }
            )

    merged_groups = _merge_planned_groups(planned_groups)
    summarized_groups = [_summarize_planned_group(group) for group in merged_groups]
    strategies = sorted({str(group.get("strategy") or "none") for group in summarized_groups})
    preserve_values = {bool(group.get("preserve_folder_structure", True)) for group in summarized_groups}
    return {
        "groups": merged_groups,
        "planned_models": summarized_groups,
        "summary": {
            "planned_model_count": len(summarized_groups),
            "source_entry_count": len([entry for entry in source_entries if isinstance(entry, dict)]),
            "file_count": sum(int(group.get("file_count") or 0) for group in summarized_groups),
            "model_file_count": sum(int(group.get("model_file_count") or 0) for group in summarized_groups),
            "media_file_count": sum(int(group.get("media_file_count") or 0) for group in summarized_groups),
            "supporting_file_count": sum(int(group.get("supporting_file_count") or 0) for group in summarized_groups),
            "grouping_strategy": strategies[0] if len(strategies) == 1 else "mixed",
            "preserve_folder_structure": next(iter(preserve_values)) if len(preserve_values) == 1 else None,
            "mixed_grouping": len(strategies) > 1,
        },
    }


def _compute_group_key(
    *, 
    file_path: Path,
    root_path: Path,
    strategy: str,
    source_entry: dict[str, Any]
) -> str:
    """
    Compute the group key for a file based on grouping strategy.
    
    by-folder: file's parent folder relative to root
    by-root: unique key per selected root path
    flat: unique per file
    none: "__single__" (all files → same group)
    """
    if strategy == "by-root":
        return f"__root__::{str(root_path)}"
    if strategy == "flat":
        return str(file_path.resolve())
    if strategy == "by-folder":
        try:
            relative_parent = file_path.parent.relative_to(root_path)
            return str(relative_parent) if str(relative_parent) != "." else "__root_folder__"
        except ValueError:
            return "__root_folder__"
    # "none" or unknown
    return "__single__"


def _compute_group_title(
    *,
    group_key: str,
    root_path: Path,
    file_path: Path,
    strategy: str,
    source_entry: dict[str, Any]
) -> str:
    """
    Compute group title based on grouping strategy and group key.
    """
    # Explicit override from UI: keep exact title for single-group strategy,
    # and suffix grouped strategies so each model/group remains distinct.
    explicit_title = str(source_entry.get("group_title") or "").strip()

    def _strategy_suffix() -> str:
        if strategy == "by-root":
            if group_key.startswith("__root__::"):
                return _display_title_from_path(Path(group_key.split("::", 1)[1]).name or root_path.name or "Root") or "Root"
            return _display_title_from_path(root_path.name or str(root_path)) or "Root"
        if strategy == "flat":
            return _display_title_from_path(file_path.name) or file_path.stem or file_path.name
        if strategy == "by-folder":
            if group_key == "__root_folder__":
                return _display_title_from_path(root_path.name or "Root") or "Root"
            return _display_title_from_path(Path(str(group_key).replace("\\", "/")).name or str(group_key)) or str(group_key).replace("\\", "/")
        return ""

    if explicit_title:
        if strategy == "flat":
            # Each file is its own group in flat mode; the explicit title IS the
            # full model name — no suffix needed.
            return explicit_title
        if strategy == "none":
            return explicit_title
        suffix = _strategy_suffix()
        return f"{explicit_title} - {suffix}" if suffix else explicit_title

    if strategy == "by-root":
        return _display_title_from_path(root_path.name or str(root_path)) or "Working Group"
    if strategy == "flat":
        return _display_title_from_path(file_path.name) or file_path.stem or file_path.name
    if strategy == "by-folder":
        if group_key == "__root_folder__":
            root_title = _display_title_from_path(root_path.name or "Root") or "Root"
            return f"{root_title} Root"
        parent = Path(group_key)
        return _display_title_from_path(parent.name or group_key) or parent.name or group_key
    # "none"
    title_source = str(source_entry.get("group_title_source") or "").strip().lower().replace("_", "-")
    entry_type = str(source_entry.get("type") or "").strip().lower()
    if title_source == "folder" and entry_type == "folder":
        return _display_title_from_path(root_path.name or str(root_path)) or "Working Group"
    return _display_title_from_path(file_path.name) or file_path.stem or file_path.name or "Working Group"
    
    if strategy == "by-root":
        return root_path.name or str(root_path)
    if strategy == "flat":
        return file_path.stem or file_path.name
    if strategy == "by-folder":
        if group_key == "__root_folder__":
            return f"{root_path.name} Root"
        parent = Path(group_key)
        return parent.name or group_key
    # "none"
    return "Working Group"

    title_source = str(source_entry.get("group_title_source") or "").strip().lower().replace("_", "-")
    entry_type = str(source_entry.get("type") or "").strip().lower()
    if title_source == "folder" and entry_type == "folder":
        return f"{root_path.name} Root"
def _group_files_by_strategy(
    *,
    expanded_files: list[dict[str, Any]],
    source_entries: list[dict[str, Any]],
    strategy: str
) -> dict[str, dict[str, Any]]:
    """
    Group expanded files into proposals based on strategy.
    
    Returns dict[group_key] = {
        "title": str,
        "files": [expanded_file_items],
        "strategy": str,
        "source_entry": dict
    }
    """
    groups_by_key: dict[str, dict[str, Any]] = {}

    source_roots: dict[str, Path] = {}
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        entry_path_raw = str(entry.get("path") or "").strip()
        if entry_path_raw:
            source_roots[entry_path_raw] = Path(entry_path_raw).expanduser().resolve()

    if strategy == "flat":
        representative_entry = next((entry for entry in source_entries if isinstance(entry, dict)), {})
        representative_root = next(
            iter(source_roots.values()),
            Path(str(expanded_files[0]["path"])).resolve().parent if expanded_files else Path(),
        )
        return _plan_flat_file_groups(
            batch_files=expanded_files,
            source_entry=representative_entry,
            root_path=representative_root,
        )

    for file_item in expanded_files:
        source_entry = file_item.get("source_entry", {})
        source_path_raw = str(source_entry.get("path") or "").strip()
        root_path = source_roots.get(source_path_raw, Path(file_item["path"]).parent)

        file_path = Path(file_item["path"]).resolve()
        relative_path_raw = str(file_item.get("relative_path") or source_entry.get("relative_path") or "").strip().replace("\\", "/")
        relative_path = Path(relative_path_raw) if relative_path_raw else None

        if relative_path is not None and str(source_entry.get("source_type") or "").strip().lower() == "browser_upload":
            if strategy == "by-folder":
                rel_parent = relative_path.parent
                group_key = "__root_folder__" if str(rel_parent) in {"", "."} else str(rel_parent).replace("\\", "/")
            elif strategy == "by-root":
                parts = [part for part in relative_path.parts if str(part).strip()]
                group_key = parts[0] if parts else "__root__"
            else:
                group_key = "__single__"
        else:
            group_key = _compute_group_key(
                file_path=file_path,
                root_path=root_path,
                strategy=strategy,
                source_entry=source_entry,
            )
        group_title = _compute_group_title(
            group_key=group_key,
            root_path=root_path,
            file_path=file_path,
            strategy=strategy,
            source_entry=source_entry,
        )

        if group_key not in groups_by_key:
            groups_by_key[group_key] = {
                "title": group_title,
                "files": [],
                "strategy": strategy,
                "source_entry": source_entry,
                "root_path": str(root_path),
                "preserve_folder_structure": _coerce_bool(source_entry.get("preserve_folder_structure", True)),
                "group_title": str(source_entry.get("group_title") or "").strip(),
            }

        groups_by_key[group_key]["files"].append(file_item)

    return groups_by_key


def _move_files_to_working_group(
    *, 
    expanded_files: list[dict[str, Any]], 
    working_group_id: int,
    working_group_slug: str | None,
    settings: Any,
    preserve_folder_structure: bool = True
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """
    Move files from their source locations to the working files folder.
    
    Args:
        expanded_files: List of file items from _expand_intake_source_entries
        working_group_id: Working group database ID
        working_group_slug: Working group slug for folder naming
        settings: Application settings
        preserve_folder_structure: If True, recreate folder hierarchy using relative_path.
                                   If False, flatten all files into group_folder.
    
    Returns:
        (moved_files, errors) where:
        - moved_files: List of (source_path, destination_path) tuples for successfully moved files
        - errors: List of error dicts with 'path' and 'message' keys
    """
    moved_files: list[tuple[str, str]] = []
    errors: list[dict[str, Any]] = []
    
    # Get working files root directory
    working_files_roots = _configured_working_files_roots(settings)
    if not working_files_roots:
        errors.append({
            "code": "no_working_files_root",
            "message": "No working files root configured in settings"
        })
        return moved_files, errors
    
    working_files_root = working_files_roots[0]
    folder_name = str(working_group_slug or "").strip() or str(working_group_id)
    group_folder = working_files_root / folder_name
    
    # Create group folder if it doesn't exist
    try:
        group_folder.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as exc:
        errors.append({
            "code": "mkdir_failed",
            "message": f"Failed to create working group folder: {exc}"
        })
        return moved_files, errors
    
    # Move each file to the group folder
    reserved_paths: set[str] = set()
    for file_item in expanded_files:
        source_path_str = str(file_item.get("path") or "").strip()
        if not source_path_str:
            continue
        
        source_path = Path(source_path_str).resolve()
        
        # Verify source exists
        if not source_path.exists() or not source_path.is_file():
            errors.append({
                "code": "source_missing",
                "path": source_path_str,
                "message": f"Source file not found: {source_path_str}"
            })
            continue
        
        # Determine destination path based on preserve_folder_structure
        if preserve_folder_structure:
            # Use relative_path if available (from by-folder grouping metadata)
            relative_path_raw = file_item.get("relative_path")
            if relative_path_raw:
                dest_rel = Path(relative_path_raw)
                dest_path = group_folder / dest_rel
                # Create parent directories as needed
                try:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                except (OSError, PermissionError) as exc:
                    errors.append({
                        "code": "mkdir_failed",
                        "path": source_path_str,
                        "message": f"Failed to create folder structure: {exc}"
                    })
                    continue
            else:
                # Fallback: use filename only
                dest_path = group_folder / source_path.name
        else:
            # Flatten: use filename only
            dest_path = group_folder / source_path.name
        
        dest_key = _normalize_path_compare_key(str(dest_path.resolve()))
        
        # If file already exists, append a counter
        if dest_path.exists() or dest_key in reserved_paths:
            stem = source_path.stem
            suffix = source_path.suffix
            counter = 2
            while True:
                next_dest_name = f"{stem}-{counter}{suffix}"
                next_dest_path = dest_path.parent / next_dest_name
                next_key = _normalize_path_compare_key(str(next_dest_path.resolve()))
                if not next_dest_path.exists() and next_key not in reserved_paths:
                    dest_path = next_dest_path
                    break
                counter += 1
        
        reserved_paths.add(_normalize_path_compare_key(str(dest_path.resolve())))
        
        # Move the file
        try:
            shutil.move(str(source_path), str(dest_path))
            moved_files.append((source_path_str, str(dest_path.resolve())))
        except (OSError, PermissionError, shutil.Error) as exc:
            errors.append({
                "code": "move_failed",
                "path": source_path_str,
                "message": f"Failed to move file: {exc}"
            })
    
    return moved_files, errors


# ==================== ENDPOINTS ====================

@router.post("/api/intake/submit")
def intake_submit(request: Request, payload: dict[str, Any]) -> Any:
    """
    Submit one or more intake items into inbox workflow.

    Payload:
      items: [{ source_path, source_type? }]
      auto_validate: bool (default true)
      cleanup_policy: keep|delete_on_verified|replace_with_stub
    """
    state: AppState = request.app.state.model_catalog
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "invalid_payload", "message": "items must be a non-empty list"},
        )

    auto_validate = _coerce_bool(payload.get("auto_validate", True))
    cleanup_policy = str(payload.get("cleanup_policy") or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        cleanup_policy = "keep"

    now_iso = _bulk_utc_now_iso()
    created_items: list[dict[str, Any]] = []
    pending_events: list[dict[str, Any]] = []
    existing_hashes = get_all_indexed_file_hashes(state.settings.db_path) if auto_validate else set()

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            source_path_text = str(raw_item.get("source_path") or raw_item.get("path") or "").strip()
            source_type = str(raw_item.get("source_type") or "filesystem_action").strip().lower() or "filesystem_action"
            if not source_path_text:
                continue

            source_path = Path(source_path_text).expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                created_items.append(
                    {
                        "item_id": None,
                        "source_path": source_path_text,
                        "state": "validated_warning",
                        "validation": {
                            "validation_state": "missing_source",
                            "warnings": [{"code": "missing_source", "message": "Source file not found"}],
                        },
                    }
                )
                continue

            suffix = source_path.suffix.lower()
            if suffix not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
                created_items.append(
                    {
                        "item_id": None,
                        "source_path": str(source_path),
                        "state": "validated_warning",
                        "validation": {
                            "validation_state": "unsupported_type",
                            "warnings": [{"code": "unsupported_type", "message": f"Unsupported extension: {suffix}"}],
                        },
                    }
                )
                continue

            stat_result = source_path.stat()
            file_hash = None
            validation_state = "ready"
            warnings: list[dict[str, Any]] = []
            if auto_validate:
                try:
                    file_hash = _sha256_file(source_path).lower()
                except (OSError, PermissionError):
                    validation_state = "missing_source"
                    warnings.append({"code": "hash_failed", "message": "Could not compute file hash"})
                if file_hash and file_hash in existing_hashes:
                    validation_state = "duplicate_candidate"
                    warnings.append({"code": "working_group_hash_match", "message": "Hash matched an existing working item"})

            upload_id = str(uuid.uuid4())
            source_entries_json = json.dumps(
                [
                    {
                        "type": "file",
                        "path": str(source_path),
                        "source_type": source_type,
                        "source_size_bytes": int(stat_result.st_size),
                    }
                ]
            )
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, source_entries_json, file_hashes_json,
                    verification_status, cleanup_policy, created_at, updated_at,
                    inbox_state, decision_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    "queued",
                    source_entries_json,
                    json.dumps([file_hash] if file_hash else []),
                    "pass" if validation_state == "ready" else "unverified",
                    cleanup_policy,
                    now_iso,
                    now_iso,
                    _intake_item_state_from_upload_status("verified" if validation_state == "ready" else "cleanup_failed"),
                    None,
                ),
            )

            if auto_validate:
                pending_events.append(
                    {
                        "upload_id": upload_id,
                        "event_type": "intake_item_validated",
                        "payload": {
                            "upload_id": upload_id,
                            "validation_state": validation_state,
                            "warnings": warnings,
                            "source_path": str(source_path),
                        },
                    }
                )

            created_items.append(
                {
                    "item_id": upload_id,
                    "source_path": str(source_path),
                    "state": "validated_ready" if validation_state == "ready" else "validated_warning",
                    "validation": {
                        "validation_state": validation_state,
                        "warnings": warnings,
                    },
                }
            )

        connection.commit()
    finally:
        connection.close()

    for event in pending_events:
        _record_queue_event(
            request=request,
            upload_id=str(event["upload_id"]),
            event_type=str(event["event_type"]),
            payload=dict(event["payload"]),
        )

    return {
        "success": True,
        "created_count": len([item for item in created_items if item.get("item_id")]),
        "items": created_items,
    }


@router.get("/api/intake/items")
def list_intake_items(request: Request, limit: int | None = None, offset: int | None = None, state_filter: str | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    limit_value = max(1, min(int(limit or 100), 1000))
    offset_value = max(0, int(offset or 0))

    where_clauses = ["1=1"]
    params: list[Any] = []
    if state_filter and state_filter.strip():
        where_clauses.append("inbox_state = ?")
        params.append(state_filter.strip())
    where_sql = " AND ".join(where_clauses)

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS cnt FROM intake_queue_uploads WHERE {where_sql}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                   source_entries_json, file_hashes_json, error_json,
                 created_at, updated_at, uploaded_at, verified_at, cleanup_done_at, decision_note,
                  terminal_action, terminal_result_id, terminal_at, terminal_actor
            FROM intake_queue_uploads
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit_value, offset_value],
        ).fetchall()
    finally:
        connection.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        source_entries = json.loads(str(row["source_entries_json"] or "[]"))
        source_entry = source_entries[0] if isinstance(source_entries, list) and source_entries else {}
        normalized_state = str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or ""))
        terminal_action = row["terminal_action"]
        terminal_result_id = row["terminal_result_id"]
        items.append(
            {
                "item_id": row["upload_id"],
                "status": row["status"],
                "state": normalized_state,
                "verification_status": row["verification_status"],
                "cleanup_policy": row["cleanup_policy"],
                "source_entry": source_entry,
                "file_hashes": json.loads(str(row["file_hashes_json"] or "[]")),
                "error": json.loads(str(row["error_json"] or "null")),
                "decision_note": row["decision_note"],
                "terminal_action": terminal_action,
                "terminal_display_action": _derive_terminal_display_action(terminal_action, terminal_result_id),
                "terminal_result_id": terminal_result_id,
                "terminal_result": _normalize_terminal_result(terminal_action, terminal_result_id),
                "terminal_at": row["terminal_at"],
                "terminal_actor": _normalize_terminal_actor(row["terminal_actor"], fallback="queue_processed"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "uploaded_at": row["uploaded_at"],
                "verified_at": row["verified_at"],
                "cleanup_done_at": row["cleanup_done_at"],
            }
        )

    return {
        "success": True,
        "pagination": {
            "limit": limit_value,
            "offset": offset_value,
            "total": int(total_row["cnt"] if total_row else 0),
        },
        "items": items,
    }


@router.post("/api/intake/preview-batch")
def preview_intake_batch(request: Request, payload: dict[str, Any] | None = None) -> Any:
    """
    Preview what will happen if source entries are expanded and grouped.
    
    Shows:
    - Total files that will be imported
    - Warnings about missing sources, duplicates, etc.
    - Impact of grouping strategy
    - Whether files are already in working groups (duplicates)
    """
    payload = payload or {}
    source_entries = payload.get("source_entries") or []
    if not isinstance(source_entries, list):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "source_entries must be a list",
            },
        )

    canonical_entries = _canonical_source_entries(source_entries)
    state: AppState = request.app.state.model_catalog
    
    # Expand files from source entries (same logic as validate)
    expanded_files, expansion_warnings = _expand_intake_source_entries(
        source_entries=canonical_entries
    )

    # Check for duplicates in existing working groups
    existing_hashes = _read_existing_working_hashes(state.settings.db_path)
    duplicate_hashes: list[dict[str, Any]] = []
    unique_hashes: list[str] = []
    
    for file_item in expanded_files:
        file_hash = str(file_item.get("file_hash") or "").strip().lower()
        if not file_hash:
            continue
        if file_hash in existing_hashes:
            duplicate_hashes.append({
                "filename": str(file_item.get("filename", "")).strip(),
                "file_path": str(file_item.get("path", "")).strip(),
                "file_hash": file_hash,
                "status": "already_in_working_group",
            })
        else:
            unique_hashes.append(file_hash)

    # Analyze grouping impact
    source_entry_count = len(canonical_entries)
    folder_entries = sum(1 for e in canonical_entries if e.get("type") == "folder")
    file_entries = source_entry_count - folder_entries

    return {
        "success": True,
        "contract": "intake-preview-batch.v1alpha1",
        "source_entries": {
            "total": source_entry_count,
            "files": file_entries,
            "folders": folder_entries,
        },
        "files": {
            "expanded_total": len(expanded_files),
            "unique_hashes": len(unique_hashes),
            "duplicate_hashes": len(duplicate_hashes),
            "duplicate_details": duplicate_hashes,
        },
        "warnings": expansion_warnings,
        "grouping_impact": {
            "recommended_strategy": "group_by_root" if folder_entries > 0 else "single_group",
            "strategy_explanation": (
                "Group by root: Creates one working group per top-level source path. "
                "Single group: All files in one working group."
            ),
            "file_count_by_strategy": {
                "single_group": len(expanded_files),
                "group_by_root": source_entry_count,
                "group_by_folder": len(set(str(Path(f["path"]).parent) for f in expanded_files)),
            },
        },
        "can_publish_directly": (
            len(expanded_files) > 0 and 
            len(duplicate_hashes) == 0 and 
            len([w for w in expansion_warnings if w.get("code") in {"missing_source", "source_unreadable"}]) == 0
        ),
        "next_actions": [
            "queue" if not expanded_files else "preview_or_queue",
            "execute_now" if len(expanded_files) > 0 and len(duplicate_hashes) == 0 else None,
        ],
    }


@router.get("/api/intake/items/{item_id}")
def get_intake_item(request: Request, item_id: str) -> Any:
    """Get a single intake item with full details and action eligibility."""
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                   source_entries_json, file_hashes_json, manyfold_file_ids_json, error_json,
                   created_at, updated_at, uploaded_at, verified_at, cleanup_done_at, decision_note
            FROM intake_queue_uploads
            WHERE upload_id = ?
            """,
            (item_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    current_state = str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or ""))
    eligibility = ActionEligibility.build_allowed_actions_payload(current_state)
    source_entries = json.loads(str(row["source_entries_json"] or "[]"))

    return {
        "success": True,
        "item": {
            "item_id": row["upload_id"],
            "status": row["status"],
            "state": current_state,
            "verification_status": row["verification_status"],
            "cleanup_policy": row["cleanup_policy"],
            "source_entries": source_entries,
            "file_hashes": json.loads(str(row["file_hashes_json"] or "[]")),
            "manyfold_file_ids": json.loads(str(row["manyfold_file_ids_json"] or "[]")),
            "error": json.loads(str(row["error_json"] or "null")),
            "decision_note": row["decision_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "uploaded_at": row["uploaded_at"],
            "verified_at": row["verified_at"],
            "cleanup_done_at": row["cleanup_done_at"],
            # Action eligibility
            "is_terminal": eligibility["is_terminal"],
            "is_active_queue": eligibility["is_active_queue"],
            "allowed_actions": eligibility["allowed_actions"],
            "state_display_name": eligibility["state_display_name"],
        },
    }


@router.post("/api/intake/items/{item_id}/validate")
def validate_intake_item(request: Request, item_id: str) -> Any:
    """
    Validate an intake item (run quality checks and resolve files).
    
    Allowed states: submitted, validated_ready, validated_warning, deferred.
    Returns HTTP 409 if state is terminal.
    """
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
            (item_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    row = dict(row)

    # Check action eligibility
    is_eligible, reason_code = _check_action_eligibility(row, ActionEligibility.VALIDATE)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot validate item in state '{row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": row.get("inbox_state"),
                **_build_intake_item_response(row),
            },
        )

    source_entries = _canonical_source_entries(json.loads(str(row["source_entries_json"] or "[]")))
    warnings: list[dict[str, Any]] = []
    validation_state = "ready"

    expanded_files, expansion_warnings = _expand_intake_source_entries(
        source_entries=source_entries
    )
    warnings.extend(expansion_warnings)
    warning_codes = {str(warning.get("code") or "").strip().lower() for warning in expansion_warnings if isinstance(warning, dict)}
    if "missing_source" in warning_codes or "source_unreadable" in warning_codes:
        validation_state = "missing_source"
    elif "unsupported_type" in warning_codes and not expanded_files:
        validation_state = "unsupported_type"
    elif expansion_warnings:
        validation_state = "source_warning"

    existing_hashes = get_all_indexed_file_hashes(state.settings.db_path)
    indexed_exact_names, indexed_normalized_names = _read_indexed_filename_maps(
        state.settings.db_path,
        exclude_upload_id=item_id,
    )
    file_hashes: list[str] = []
    duplicate_hashes: list[str] = []
    duplicate_name_exact_count = 0
    duplicate_name_soft_count = 0
    for file_item in expanded_files:
        file_hash = str(file_item.get("file_hash") or "").strip().lower()
        filename = str(file_item.get("filename") or Path(str(file_item.get("path") or "")).name).strip()
        filename_key = filename.lower()
        if not file_hash:
            pass
        else:
            file_hashes.append(file_hash)
            if file_hash in existing_hashes:
                duplicate_hashes.append(file_hash)
                validation_state = "duplicate_candidate"
                warnings.append(
                    {
                        "code": "working_group_hash_match",
                        "message": "Hard duplicate: hash matched an existing indexed file.",
                        "sha256": file_hash,
                    }
                )

        exact_name_matches = sorted(indexed_exact_names.get(filename_key, set())) if filename_key else []
        if exact_name_matches:
            duplicate_name_exact_count += 1
            validation_state = "duplicate_candidate"
            warnings.append(
                {
                    "code": "duplicate_name_exact_match",
                    "message": "Exact filename matched an existing indexed file.",
                    "filename": filename,
                    "matches": exact_name_matches[:3],
                }
            )

        normalized_name = _normalized_duplicate_name(filename)
        if normalized_name:
            soft_name_matches = [
                candidate
                for candidate in sorted(indexed_normalized_names.get(normalized_name, set()))
                if candidate.lower() != filename_key
            ]
            if soft_name_matches:
                duplicate_name_soft_count += 1
                validation_state = "duplicate_candidate"
                warnings.append(
                    {
                        "code": "duplicate_name_soft_match",
                        "message": "Soft duplicate: filename variant matched an existing indexed file.",
                        "filename": filename,
                        "normalized_name": normalized_name,
                        "matches": soft_name_matches[:3],
                    }
                )

    if not expanded_files and validation_state == "ready":
        validation_state = "needs_manual_grouping"
        warnings.append({"code": "needs_manual_grouping", "message": "No files resolved from source entries."})

    warning_codes = {
        str(warning.get("code") or "").strip().lower()
        for warning in warnings
        if isinstance(warning, dict) and str(warning.get("code") or "").strip()
    }
    validation_checks = _build_validation_checks(
        warning_codes=warning_codes,
        expanded_files=expanded_files,
        duplicate_hashes=duplicate_hashes,
        duplicate_name_exact_count=duplicate_name_exact_count,
        duplicate_name_soft_count=duplicate_name_soft_count,
        source_entries=source_entries,
    )

    next_inbox_state = "validated_ready" if validation_state == "ready" else "validated_warning"
    connection = connect(state.settings.db_path)
    try:
        connection.execute(
            """
            UPDATE intake_queue_uploads
            SET file_hashes_json = ?,
                verification_status = ?,
                inbox_state = ?,
                decision_note = ?,
                updated_at = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps(file_hashes),
                "pass" if validation_state == "ready" else "unverified",
                next_inbox_state,
                json.dumps(warnings) if warnings else None,
                _bulk_utc_now_iso(),
                item_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    _record_queue_event(
        request=request,
        upload_id=item_id,
        event_type="intake_item_validated",
        payload={
            "validation_state": validation_state,
            "warnings": warnings,
            "file_hash_count": len(file_hashes),
        },
    )

    # Fetch updated row to build response with eligibility
    updated_row = _get_intake_item_row(state.settings.db_path, item_id)

    return {
        "success": True,
        "item_id": item_id,
        "state": next_inbox_state,
        "validation": {
            "validation_state": validation_state,
            "warnings": warnings,
            "file_hash_count": len(file_hashes),
            "checks": validation_checks,
        },
        **_build_intake_item_response(updated_row),
    }


@router.post("/api/intake/items/{item_id}/defer")
def defer_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Defer an intake item (park for later review).
    
    Allowed states: submitted, validated_ready, validated_warning.
    Terminal states: returns 409 Conflict.
    """
    payload = payload or {}
    note = str(payload.get("note") or "Deferred by operator").strip() or "Deferred by operator"
    state: AppState = request.app.state.model_catalog

    # Fetch current item
    item_row = _get_intake_item_row(state.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    # Check action eligibility
    is_eligible, reason_code = _check_action_eligibility(item_row, ActionEligibility.DEFER)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot defer item in state '{item_row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": item_row.get("inbox_state"),
                **_build_intake_item_response(item_row),
            },
        )

    # Update database
    connection = connect(state.settings.db_path)
    try:
        now_iso = _bulk_utc_now_iso()
        connection.execute(
            "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
            ("deferred", note, now_iso, item_id),
        )
        connection.commit()
    finally:
        connection.close()

    # Log event
    _record_queue_event(
        request=request,
        upload_id=item_id,
        event_type="intake_item_deferred",
        payload={"note": note},
    )

    # Refresh and return updated item
    updated_row = _get_intake_item_row(state.settings.db_path, item_id)
    return {
        "success": True,
        **_build_intake_item_response(updated_row),
        "decision_note": note,
    }


@router.post("/api/intake/items/{item_id}/reject")
def reject_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Reject an intake item (terminal state).
    
    Allowed states: submitted, validated_ready, validated_warning, deferred.
    Creates a terminal state; no further intake actions allowed.
    """
    payload = payload or {}
    note = str(payload.get("note") or "Rejected by operator").strip() or "Rejected by operator"
    state: AppState = request.app.state.model_catalog

    # Fetch current item
    item_row = _get_intake_item_row(state.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    # Check action eligibility
    is_eligible, reason_code = _check_action_eligibility(item_row, ActionEligibility.REJECT)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot reject item in state '{item_row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": item_row.get("inbox_state"),
                **_build_intake_item_response(item_row),
            },
        )

    # Update database (set to terminal state)
    connection = connect(state.settings.db_path)
    try:
        now_iso = _bulk_utc_now_iso()
        connection.execute(
            """
            UPDATE intake_queue_uploads 
            SET inbox_state = ?, decision_note = ?, updated_at = ?,
                terminal_action = 'rejected', terminal_at = ?
            WHERE upload_id = ?
            """,
            ("rejected", note, now_iso, now_iso, item_id),
        )
        connection.commit()
    finally:
        connection.close()

    # Log event
    _record_queue_event(
        request=request,
        upload_id=item_id,
        event_type="intake_item_rejected",
        payload={"note": note},
    )

    # Refresh and return updated item
    updated_row = _get_intake_item_row(state.settings.db_path, item_id)
    return {
        "success": True,
        **_build_intake_item_response(updated_row),
        "decision_note": note,
        "terminal": True,
    }


@router.post("/api/intake/items/{item_id}/group")
def group_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Group an intake item into working group(s) (terminal state).
    
    Supports multi-group decomposition based on grouping_strategy:
    - none: all files in one group
    - by-folder: one group per unique folder (respects folder hierarchy)
    - by-root: one group per root selection
    - flat: one group per file (not recommended)
    
    Also supports folder structure preservation via preserve_folder_structure flag.
    
    Allowed states: validated_ready (always), validated_warning (with override=true).
    Terminal states: returns 409 Conflict.
    """
    state: AppState = request.app.state.model_catalog
    payload = payload or {}
    action = str(payload.get("action") or "create_working_group").strip().lower()
    if action not in {"create_working_group", "attach_existing_working_group"}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_action",
                "message": "action must be create_working_group or attach_existing_working_group",
            },
        )

    # Fetch current item
    item_row = _get_intake_item_row(state.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    # Map action to eligibility constant
    eligibility_action = ActionEligibility.GROUP_NEW if action == "create_working_group" else ActionEligibility.GROUP_EXISTING
    
    # Check action eligibility (includes override requirement for warning states)
    override = _coerce_bool(payload.get("override", False))
    is_eligible, reason_code = _check_action_eligibility(item_row, eligibility_action, override=override)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot group item in state '{item_row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": item_row.get("inbox_state"),
                **_build_intake_item_response(item_row),
            },
        )

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    response_payload: dict[str, Any] | None = None
    event_payload: dict[str, Any] | None = None
    try:
        source_entries = _canonical_source_entries(json.loads(str(item_row.get("source_entries_json") or "[]")))
        expanded_files, expansion_warnings = _expand_intake_source_entries(
            source_entries=source_entries
        )
        if not expanded_files:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_files",
                    "message": "Intake item has no resolved files to group",
                    "warnings": expansion_warnings,
                },
            )

        # Extract excluded_items from payload and filter out excluded files
        excluded_items = payload.get("excluded_items", [])
        if excluded_items and isinstance(excluded_items, list):
            expanded_files = _prefilter_excluded_items(expanded_files, excluded_items)

        plan = _plan_intake_groups(source_entries=source_entries, expanded_files=expanded_files)
        plan_summary = dict(plan.get("summary") or {})

        if action == "create_working_group":
            planned_models = list(plan.get("groups") or [])
        else:
            planned_models = [{
                "title": "Existing",
                "files": expanded_files,
                "strategy": "none",
                "preserve_folder_structure": True,
                "source_entries": list(source_entries),
            }]

        now_iso = _bulk_utc_now_iso()
        created_groups: list[dict[str, Any]] = []
        total_added_items = 0
        total_duplicate_items = 0
        
        for group_info in planned_models:
            group_files = group_info.get("files", [])
            if not group_files:
                continue
            group_strategy = str(group_info.get("strategy") or "none").strip() or "none"
            group_preserve_folder_structure = _coerce_bool(group_info.get("preserve_folder_structure", True))
            
            if action == "create_working_group":
                # Create new working group
                title = str(payload.get("title") or "").strip() or group_info.get("title") or _default_group_title(source_entries, group_files)
                stage = str(payload.get("stage") or "draft").strip() or "draft"
                folder_hint = str(payload.get("folder_hint") or Path(str(group_files[0]["path"])).parent).strip() or None
                notes = str(payload.get("notes") or "Imported from intake workflow").strip() or None
                slug = _unique_slug(connection, title)
                group_timestamp_summary = _source_timestamp_summary(group_files)
                connection.execute(
                    """
                    INSERT INTO working_groups (
                        slug, title, stage, notes, primary_file_path, folder_hint,
                        related_manyfold_model_id, created_at, updated_at,
                        discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        title,
                        stage,
                        notes,
                        None,
                        folder_hint,
                        None,
                        now_iso,
                        now_iso,
                        folder_hint,
                        group_strategy,
                        now_iso,
                        json.dumps({
                            "source": "intake",
                            "upload_id": item_id,
                            "imported_at": now_iso,
                            "source_timestamp_summary": group_timestamp_summary,
                            "grouping_strategy": group_strategy,
                            "preserve_folder_structure": group_preserve_folder_structure,
                        }),
                    ),
                )
                group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
                group_slug = slug
            else:
                # Attach to existing group
                group_id = int(payload.get("working_group_id") or 0)
                if group_id <= 0:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "error": "invalid_payload",
                            "message": "working_group_id is required for attach_existing_working_group",
                        },
                    )
                existing_group = connection.execute("SELECT id, slug FROM working_groups WHERE id = ?", (group_id,)).fetchone()
                if existing_group is None:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "success": False,
                            "error": "working_group_not_found",
                            "message": f"Working group not found: {group_id}",
                        },
                    )
                group_slug = str(existing_group["slug"] or "").strip() or None

            # Move files to working files folder
            moved_files, move_errors = _move_files_to_working_group(
                expanded_files=group_files,
                working_group_id=group_id,
                working_group_slug=group_slug,
                settings=state.settings,
                preserve_folder_structure=group_preserve_folder_structure
            )
            
            # Build a map of source -> destination paths
            source_to_dest = dict(moved_files)
            
            # Record move errors in expansion_warnings
            for error in move_errors:
                expansion_warnings.append(error)

            added_items = 0
            duplicate_items = 0
            primary_file_path: str | None = None
            for index, file_item in enumerate(group_files):
                original_path = str(file_item["path"])
                # Use the moved path if available, otherwise use original path
                file_path = source_to_dest.get(original_path, original_path)
                file_hash = str(file_item.get("file_hash") or "").strip().lower() or None
                existing_item = connection.execute(
                    "SELECT id FROM working_items WHERE working_group_id = ? AND file_path = ?",
                    (group_id, file_path),
                ).fetchone()
                if existing_item is not None:
                    duplicate_items += 1
                    continue
                if file_hash:
                    existing_hash_match = connection.execute(
                        "SELECT id FROM working_items WHERE file_hash = ?",
                        (file_hash,),
                    ).fetchone()
                    if existing_hash_match is not None:
                        duplicate_items += 1
                        continue
                item_role = "primary" if index == 0 and action == "create_working_group" else "supporting"
                if item_role == "primary" and primary_file_path is None:
                    primary_file_path = file_path
                connection.execute(
                    """
                    INSERT INTO working_items (
                        working_group_id, file_path, item_role, created_at, updated_at,
                        file_hash, file_size, source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        file_path,
                        item_role,
                        now_iso,
                        now_iso,
                        file_hash,
                        int(file_item.get("size_bytes") or 0) or None,
                        json.dumps(file_item.get("source_metadata") or {}),
                    ),
                )
                added_items += 1

            if action == "create_working_group" and primary_file_path:
                connection.execute(
                    "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                    (primary_file_path, now_iso, group_id),
                )

            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            serialized_group = _serialize_working_group(connection, group_row, state.settings)
            created_groups.append({
                "working_group_id": group_id,
                "group": serialized_group,
                "added_items": added_items,
                "duplicate_items": duplicate_items,
            })
            total_added_items += added_items
            total_duplicate_items += duplicate_items

        # Set to terminal state with metadata
        terminal_action = "grouped_new" if action == "create_working_group" else "grouped_existing"
        group_ids_str = ",".join(str(g["working_group_id"]) for g in created_groups)
        connection.execute(
            """
            UPDATE intake_queue_uploads 
            SET inbox_state = ?, decision_note = ?, updated_at = ?,
                terminal_action = ?, terminal_at = ?, terminal_actor = ?,
                terminal_result_id = ?
            WHERE upload_id = ?
            """,
            (
                terminal_action,
                f"Grouped to working_group_id(s)={group_ids_str}",
                now_iso,
                terminal_action,
                now_iso,
                "queue_processed",
                group_ids_str,
                item_id,
            ),
        )
        connection.commit()

        event_payload = {
            "upload_id": item_id,
            "action": action,
            "grouping_strategy": plan_summary.get("grouping_strategy", "none"),
            "preserve_folder_structure": plan_summary.get("preserve_folder_structure"),
            "created_groups": [
                {
                    "working_group_id": g["working_group_id"],
                    "added_items": g["added_items"],
                    "duplicate_items": g["duplicate_items"],
                } for g in created_groups
            ],
            "total_added_items": total_added_items,
            "total_duplicate_items": total_duplicate_items,
            "warnings": expansion_warnings,
        }
        response_payload = {
            "success": True,
            "item_id": item_id,
            "state": terminal_action,
            "terminal": True,
            "working_group_id": created_groups[0]["working_group_id"] if created_groups else None,
            "grouping_strategy": plan_summary.get("grouping_strategy", "none"),
            "preserve_folder_structure": plan_summary.get("preserve_folder_structure"),
            "plan_summary": plan_summary,
            "created_groups": created_groups,
            "total_added_items": total_added_items,
            "total_duplicate_items": total_duplicate_items,
            "added_items": created_groups[0]["added_items"] if len(created_groups) == 1 else total_added_items,
            "duplicate_items": created_groups[0]["duplicate_items"] if len(created_groups) == 1 else total_duplicate_items,
            "group": created_groups[0]["group"] if created_groups else None,
            "warnings": expansion_warnings,
        }

        # Browser uploads stage into GUID directories; remove staging after files
        # are successfully moved and grouped.
        for stage_dir in _browser_upload_stage_directories(state.settings, source_entries):
            shutil.rmtree(stage_dir, ignore_errors=True)
    finally:
        connection.close()

    if event_payload is not None:
        _record_queue_event(
            request=request,
            upload_id=item_id,
            event_type="intake_item_grouped",
            payload=event_payload,
        )
    return response_payload
