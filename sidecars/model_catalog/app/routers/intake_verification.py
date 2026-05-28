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
    _compile_force_include_paths,
    _compile_source_entry_exclusions,
    _coerce_bool,
    _collect_intake_source_files_in_folder,
    _configured_working_files_roots,
    _enforce_source_entries_within_intake_roots,
    _is_excluded_source_file,
    _make_intake_warning_id,
    _normalize_path_compare_key,
)
from ..services import get_all_indexed_file_hashes
from ..services.intake_service import _TERMINAL_INBOX_STATES
from ..services.shared_helpers import _local_asset_media_urls, _sha256_file, _slugify_title
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


def _parse_decision_note_payload(raw_value: Any) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    validation_actions: list[dict[str, Any]] = []

    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
    else:
        parsed = None

    if isinstance(parsed, list):
        warnings = [entry for entry in parsed if isinstance(entry, dict)]
    elif isinstance(parsed, dict):
        parsed_warnings = parsed.get("warnings")
        parsed_actions = parsed.get("validation_actions")
        if isinstance(parsed_warnings, list):
            warnings = [entry for entry in parsed_warnings if isinstance(entry, dict)]
        if isinstance(parsed_actions, list):
            validation_actions = [entry for entry in parsed_actions if isinstance(entry, dict)]

    return {
        "warnings": warnings,
        "validation_actions": validation_actions,
    }


def _normalize_validation_action(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    finding_key = str(payload.get("finding_key") or "").strip().lower()
    decision = str(payload.get("decision") or "").strip().lower()
    check_key = str(payload.get("check_key") or "").strip().lower()

    allowed_decisions = {
        "review",
        "exclude_source",
        "allow_duplicate",
        "keep_both",
        "exclude_conflict",
        "exclude_both",
    }

    if not finding_key:
        return None, "finding_key is required"
    if decision not in allowed_decisions:
        return (
            None,
            "decision must be one of: review, exclude_source, allow_duplicate, keep_both, exclude_conflict, exclude_both",
        )

    if check_key == "duplicate_scan" and decision in {"keep_both", "exclude_conflict", "exclude_both"}:
        return None, "duplicate_scan decisions must be one of: review, exclude_source, allow_duplicate"
    if check_key == "batch_duplicate_scan" and decision == "allow_duplicate":
        # Keep compatibility with older UI payloads while converging on keep_both.
        decision = "keep_both"

    if decision == "review":
        return {
            "finding_key": finding_key,
            "decision": decision,
        }, None

    normalized: dict[str, Any] = {
        "finding_key": finding_key,
        "decision": decision,
        "applied_at": _bulk_utc_now_iso(),
    }
    for optional_key in ("check_key", "source_path", "source_name", "target_path", "target_name", "note"):
        optional_value = str(payload.get(optional_key) or "").strip()
        if optional_value:
            normalized[optional_key] = optional_value
    return normalized, None



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
    # Approach B (issue #1563): callers may opt-in to include specific files
    # whose extensions are not in the supported-intake allowlist by echoing
    # the file paths (or warning_ids encoded as absolute paths) via a
    # top-level ``force_include_paths`` array on the plan request. The same
    # override can also travel as a per-entry ``force_include_paths`` list
    # inside each source entry; both are merged inside the helper.
    raw_force_includes = payload.get("force_include_paths") if isinstance(payload, dict) else None
    top_level_force_includes: set[str] = set()
    if isinstance(raw_force_includes, list):
        for item in raw_force_includes:
            raw = str(item or "").strip()
            if not raw:
                continue
            try:
                top_level_force_includes.add(str(Path(raw).expanduser().resolve(strict=False)))
            except (OSError, RuntimeError, ValueError):
                top_level_force_includes.add(raw)

    expanded_files, warnings = _expand_intake_source_entries(
        source_entries=normalized_entries,
        force_include_paths=top_level_force_includes or None,
    )
    
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
        elif isinstance(decision_note_payload, dict):
            note_warnings = decision_note_payload.get("warnings")
            if isinstance(note_warnings, list):
                warning_codes = {
                    str(warning.get("code") or "").strip().lower()
                    for warning in note_warnings
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

def _expand_intake_source_entries(
    *,
    source_entries: list[dict[str, Any]],
    force_include_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand source entries into individual files with validation."""
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    exclusion_exact_keys, exclusion_folder_prefixes = _compile_source_entry_exclusions(source_entries)
    override_paths: set[str] = set(force_include_paths or set())
    override_paths.update(_compile_force_include_paths(source_entries))

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
            # include_unsupported=True so the per-file unsupported_type warning
            # below also fires for files discovered inside folders (issue #1563).
            candidate_paths = _collect_intake_source_files_in_folder(
                source_path, recurse=recurse, include_unsupported=True
            )

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
                suffix = file_path.suffix.lower()
                # Approach B (issue #1563): honor per-file overrides supplied
                # via force_include_paths so the operator can include an
                # unsupported extension after seeing the warning, with an
                # info-level audit warning replacing the skip.
                if normalized_path in override_paths:
                    warnings.append(
                        {
                            "code": "unsupported_type_overridden",
                            "message": f"Unsupported extension included by user override: {suffix or '<none>'}",
                            "path": normalized_path,
                            "warning_id": _make_intake_warning_id(
                                "unsupported_type_overridden", normalized_path
                            ),
                            "severity": "info",
                        }
                    )
                else:
                    warnings.append(
                        {
                            "code": "unsupported_type",
                            "message": f"Unsupported extension: {suffix or '<none>'}",
                            "path": normalized_path,
                            "warning_id": _make_intake_warning_id(
                                "unsupported_type", normalized_path
                            ),
                        }
                    )
                    continue
            if not file_path.exists() or not file_path.is_file():
                warnings.append(
                    {
                        "code": "missing_source",
                        "message": f"Source file not found: {file_path}",
                        "path": normalized_path,
                        "warning_id": _make_intake_warning_id("missing_source", normalized_path),
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
                        "warning_id": _make_intake_warning_id("source_unreadable", normalized_path),
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


def _normalized_duplicate_name_tokens(filename: str) -> tuple[str, ...]:
    normalized_name = _normalized_duplicate_name(filename)
    if not normalized_name:
        return ()
    tokens = tuple(token for token in normalized_name.split(" ") if token)
    return tokens


def _parse_makerworld_download_filename(filename: str) -> tuple[str, str] | None:
    match = re.match(r"^makerworld-(\d+)-(\d+)(?:-|\.)", Path(str(filename or "")).name, re.IGNORECASE)
    if not match:
        return None
    return match.group(1), match.group(2)


def _batch_duplicate_name_similarity(
    current_filename: str,
    seen_names: list[tuple[str, str, tuple[str, ...]]],
) -> tuple[str, float] | None:
    current_name = _normalized_duplicate_name(current_filename)
    current_tokens = set(_normalized_duplicate_name_tokens(current_filename))
    current_makerworld = _parse_makerworld_download_filename(current_filename)
    if not current_name or not current_tokens:
        return None

    best_match_name = ""
    best_score = 0.0
    for prior_filename, prior_name, prior_tokens_tuple in seen_names:
        if not prior_name:
            continue
        prior_makerworld = _parse_makerworld_download_filename(prior_filename)
        if (
            current_makerworld is not None
            and prior_makerworld is not None
            and current_makerworld[0] == prior_makerworld[0]
            and current_makerworld[1] != prior_makerworld[1]
        ):
            continue
        prior_tokens = set(prior_tokens_tuple)
        if not prior_tokens:
            continue
        overlap = current_tokens.intersection(prior_tokens)
        if not overlap:
            continue
        score = len(overlap) / max(len(current_tokens), len(prior_tokens))
        if score > best_score:
            best_score = score
            best_match_name = prior_name

    if best_score < 0.5:
        return None
    return best_match_name, best_score


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

    candidate = re.sub(r"[_\-.+]+", " ", candidate)
    candidate = re.sub(r"\s*\(\d+\)$", "", candidate)
    candidate = re.sub(r"\s*(?:-|_)?copy(?:\s*\(\d+\))?$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s+", " ", candidate).strip(" -_.")
    if not candidate:
        candidate = Path(name).stem or name

    # Strip trailing slicer/tool noise tokens (e.g. "my_model_sliced_v2_plate1" → "my model")
    _NOISE_SUFFIX = re.compile(
        r"\s+(?:sliced|final|complete|remix|fixed|updated|wip|draft|test|plate\s*\d+|v\d+(?:\.\d+)*)$",
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


def _collect_self_exclude_compare_keys(
    expanded_files: list[dict[str, Any]] | None,
) -> set[str] | None:
    """Build a set of `source_path_compare_key` values for the files being
    validated so that their own `working_file_inventory` rows are not
    flagged as hash duplicates of themselves.

    Returns ``None`` (rather than an empty set) when there is nothing to
    exclude so the underlying query takes the unfiltered fast path.
    """
    if not expanded_files:
        return None
    keys: set[str] = set()
    for file_item in expanded_files:
        if not isinstance(file_item, dict):
            continue
        raw_path = str(file_item.get("path") or "").strip()
        if not raw_path:
            continue
        try:
            resolved = Path(raw_path).expanduser().resolve()
            key = _normalize_path_compare_key(str(resolved))
        except (OSError, RuntimeError):
            key = _normalize_path_compare_key(raw_path)
        if key:
            keys.add(key)
    return keys or None


def _read_indexed_filename_maps(
    db_path: Path,
    *,
    exclude_upload_id: str | None = None,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Build exact+soft filename indexes from working, queue, and catalog assets."""
    exact_map: dict[str, set[str]] = {}
    normalized_map: dict[str, set[str]] = {}
    exact_context_map: dict[str, list[dict[str, Any]]] = {}
    normalized_context_map: dict[str, list[dict[str, Any]]] = {}

    def _append_context(bucket: dict[str, list[dict[str, Any]]], key: str, context_item: dict[str, Any] | None) -> None:
        if not key or not isinstance(context_item, dict):
            return
        rows = bucket.setdefault(key, [])
        dedupe_key = (
            str(context_item.get("scope") or "").strip().lower(),
            str(context_item.get("parent_kind") or "").strip().lower(),
            str(context_item.get("parent_name") or "").strip(),
            str(context_item.get("path") or "").strip(),
            str(context_item.get("filename") or "").strip(),
        )
        for existing in rows:
            existing_key = (
                str(existing.get("scope") or "").strip().lower(),
                str(existing.get("parent_kind") or "").strip().lower(),
                str(existing.get("parent_name") or "").strip(),
                str(existing.get("path") or "").strip(),
                str(existing.get("filename") or "").strip(),
            )
            if existing_key == dedupe_key:
                return
        rows.append(context_item)

    def _add_filename(raw_name: object, context_item: dict[str, Any] | None = None) -> None:
        name = str(raw_name or "").strip().replace("\\", "/")
        if not name:
            return
        base_name = Path(name).name or name
        if not base_name:
            return
        exact_key = base_name.lower()
        exact_map.setdefault(exact_key, set()).add(base_name)
        _append_context(exact_context_map, exact_key, context_item)
        normalized_key = _normalized_duplicate_name(base_name)
        if normalized_key:
            normalized_map.setdefault(normalized_key, set()).add(base_name)
            _append_context(normalized_context_map, normalized_key, context_item)

    connection = connect(db_path)
    try:
        if exclude_upload_id:
            queue_rows = connection.execute(
                f"""
                                SELECT upload_id, source_entries_json
                FROM intake_queue_uploads
                WHERE source_entries_json IS NOT NULL
                  AND upload_id != ?
                  AND COALESCE(inbox_state, 'submitted') NOT IN ({', '.join('?' for _ in _TERMINAL_INBOX_STATES)})
                """,
                (exclude_upload_id, *_TERMINAL_INBOX_STATES),
            ).fetchall()
        else:
            queue_rows = connection.execute(
                f"""
                                SELECT upload_id, source_entries_json
                FROM intake_queue_uploads
                WHERE source_entries_json IS NOT NULL
                  AND COALESCE(inbox_state, 'submitted') NOT IN ({', '.join('?' for _ in _TERMINAL_INBOX_STATES)})
                """,
                _TERMINAL_INBOX_STATES,
            ).fetchall()

        for row in queue_rows:
            upload_id = str(row[0] or "").strip()
            payload = str(row[1] or "").strip()
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
                queued_name = entry.get("filename") or entry.get("relative_path") or entry.get("path")
                base_name = Path(str(queued_name or "")).name or str(queued_name or "").strip()
                queued_path = str(queued_name or "").strip().replace("\\", "/")
                queue_label = f"Queued intake ({upload_id[:8]})" if upload_id else "Queued intake"
                queued_context: dict[str, Any] = {
                    "scope": "indexed",
                    "parent_kind": "queue",
                    "parent_name": queue_label,
                    "path": queued_path,
                    "filename": base_name,
                    "label": f"{queue_label} -> {queued_path or base_name}",
                }
                _add_filename(queued_name, queued_context)

        try:
            asset_rows = connection.execute(
                """
                SELECT COALESCE(a.asset_filename, a.storage_path), e.model_name, a.file_size_bytes, a.preview_url,
                       a.asset_type, e.local_model_id, a.asset_id
                FROM model_catalog_assets a
                                JOIN model_catalog_entries e ON e.id = a.model_catalog_entry_id
                WHERE COALESCE(a.asset_filename, a.storage_path) IS NOT NULL
                  AND TRIM(COALESCE(a.asset_filename, a.storage_path)) != ''
                                    AND e.archived_at IS NULL
                """
            ).fetchall()
        except sqlite3.OperationalError:
            asset_rows = []
        for row in asset_rows:
            asset_path = str(row[0] or "").strip().replace("\\", "/")
            asset_name = Path(asset_path).name or asset_path
            model_name = str(row[1] or "").strip()
            asset_size = row[2] if len(row) > 2 else None
            media_urls = _local_asset_media_urls(
                model_ref=row[5] if len(row) > 5 else None,
                asset_id=row[6] if len(row) > 6 else None,
                asset_type=row[4] if len(row) > 4 else None,
                preview_url=row[3] if len(row) > 3 else None,
            )
            asset_context: dict[str, Any] = {
                "scope": "indexed",
                "parent_kind": "catalog_model",
                "parent_name": model_name,
                "path": asset_path,
                "filename": asset_name,
                "label": (f"Catalog model '{model_name}'" if model_name else "Catalog") + (f" -> {asset_path}" if asset_path else ""),
                "size_bytes": asset_size,
                "preview_url": media_urls.get("image_url"),
            }
            _add_filename(row[0], asset_context)
    finally:
        connection.close()

    return exact_map, normalized_map, exact_context_map, normalized_context_map


def _read_indexed_hash_match_contexts(
    db_path: Path,
    *,
    exclude_upload_id: str | None = None,
    max_contexts_per_hash: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Build hash match context text for duplicate findings in validation UI."""
    context_map: dict[str, list[dict[str, Any]]] = {}

    def _add_context(raw_hash: object, context_item: dict[str, Any]) -> None:
        hash_key = str(raw_hash or "").strip().lower()
        if not isinstance(context_item, dict):
            return
        label = str(context_item.get("label") or "").strip()
        if not hash_key or not label:
            return
        rows = context_map.setdefault(hash_key, [])
        dedupe_key = (
            str(context_item.get("scope") or "").strip().lower(),
            str(context_item.get("parent_kind") or "").strip().lower(),
            str(context_item.get("parent_name") or "").strip(),
            str(context_item.get("path") or "").strip(),
            str(context_item.get("filename") or "").strip(),
        )
        for existing in rows:
            existing_key = (
                str(existing.get("scope") or "").strip().lower(),
                str(existing.get("parent_kind") or "").strip().lower(),
                str(existing.get("parent_name") or "").strip(),
                str(existing.get("path") or "").strip(),
                str(existing.get("filename") or "").strip(),
            )
            if existing_key == dedupe_key:
                return
        if len(rows) >= max_contexts_per_hash:
            return
        rows.append(context_item)

    connection = connect(db_path)
    try:
        try:
            asset_rows = connection.execute(
                """
                                SELECT a.file_hash, COALESCE(a.asset_filename, a.storage_path), e.model_name, a.file_size_bytes, a.preview_url,
                                             a.asset_type, e.local_model_id, a.asset_id
                FROM model_catalog_assets a
                                JOIN model_catalog_entries e ON e.id = a.model_catalog_entry_id
                WHERE a.file_hash IS NOT NULL
                  AND TRIM(a.file_hash) != ''
                                    AND e.archived_at IS NULL
                """
            ).fetchall()
        except sqlite3.OperationalError:
            asset_rows = []
        for row in asset_rows:
            asset_path = str(row[1] or "").strip().replace("\\", "/")
            asset_name = Path(asset_path).name or asset_path
            model_name = str(row[2] or "").strip()
            asset_size = row[3] if len(row) > 3 else None
            media_urls = _local_asset_media_urls(
                model_ref=row[6] if len(row) > 6 else None,
                asset_id=row[7] if len(row) > 7 else None,
                asset_type=row[5] if len(row) > 5 else None,
                preview_url=row[4] if len(row) > 4 else None,
            )
            _add_context(
                row[0],
                {
                    "scope": "indexed",
                    "parent_kind": "catalog_model",
                    "parent_name": model_name,
                    "path": asset_path,
                    "filename": asset_name,
                    "label": (f"Catalog model '{model_name}'" if model_name else "Catalog") + (f" -> {asset_path}" if asset_path else ""),
                    "size_bytes": asset_size,
                    "preview_url": media_urls.get("image_url"),
                },
            )

        placeholders = ", ".join("?" for _ in _TERMINAL_INBOX_STATES)
        if exclude_upload_id:
            queue_rows = connection.execute(
                f"""
                SELECT upload_id, source_entries_json, file_hashes_json
                FROM intake_queue_uploads
                WHERE file_hashes_json IS NOT NULL
                  AND TRIM(file_hashes_json) != ''
                  AND upload_id != ?
                  AND COALESCE(inbox_state, 'submitted') NOT IN ({placeholders})
                """,
                (exclude_upload_id, *_TERMINAL_INBOX_STATES),
            ).fetchall()
        else:
            queue_rows = connection.execute(
                f"""
                SELECT upload_id, source_entries_json, file_hashes_json
                FROM intake_queue_uploads
                WHERE file_hashes_json IS NOT NULL
                  AND TRIM(file_hashes_json) != ''
                  AND COALESCE(inbox_state, 'submitted') NOT IN ({placeholders})
                """,
                _TERMINAL_INBOX_STATES,
            ).fetchall()
        for row in queue_rows:
            upload_id = str(row[0] or "").strip()
            source_entries_raw = str(row[1] or "[]")
            source_entries: list[dict[str, Any]] = []
            try:
                parsed_entries = json.loads(source_entries_raw)
                if isinstance(parsed_entries, list):
                    source_entries = [entry for entry in parsed_entries if isinstance(entry, dict)]
            except (json.JSONDecodeError, ValueError):
                source_entries = []

            source_labels: list[str] = []
            for entry in source_entries[:3]:
                source_path = str(entry.get("path") or "").strip().replace("\\", "/")
                entry_type = str(entry.get("type") or "source").strip().lower() or "source"
                if source_path:
                    source_labels.append(f"{entry_type}: {source_path}")
            queue_path_label = "; ".join(source_labels) if source_labels else "Queued intake batch"

            try:
                hashes = json.loads(str(row[2] or "[]"))
            except (json.JSONDecodeError, ValueError):
                hashes = []
            if not isinstance(hashes, list):
                continue
            for raw_hash in hashes:
                hash_value = str(raw_hash or "").strip().lower()
                if not hash_value:
                    continue
                _add_context(
                    hash_value,
                    {
                        "scope": "indexed",
                        "parent_kind": "queue",
                        "parent_name": f"Queued intake ({upload_id[:8]})" if upload_id else "Queued intake",
                        "path": queue_path_label,
                        "filename": "",
                        "label": f"Queued intake ({upload_id[:8]}) -> {queue_path_label}" if upload_id else f"Queued intake -> {queue_path_label}",
                    },
                )
    finally:
        connection.close()

    return context_map


def _scan_batch_duplicate_warnings(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, int, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    seen_hashes: dict[str, dict[str, str]] = {}
    seen_exact_names: set[str] = set()
    seen_normalized_names: list[tuple[str, tuple[str, ...]]] = []
    seen_exact_primary_names: dict[str, dict[str, str]] = {}
    seen_normalized_primary_names: dict[str, dict[str, str]] = {}
    duplicate_hash_count = 0
    duplicate_name_exact_count = 0
    duplicate_name_soft_count = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        file_hash = str(item.get("file_hash") or "").strip().lower()
        filename = str(item.get("filename") or Path(str(item.get("path") or "")).name).strip()
        file_path = str(item.get("path") or "").strip()
        relative_path = str(item.get("relative_path") or "").strip().replace("\\", "/")
        item_size_bytes = item.get("size_bytes")
        item_source_mtime = str((item.get("source_metadata") or {}).get("source_mtime") or "").strip() or None
        filename_key = filename.lower()
        normalized_name = _normalized_duplicate_name(filename)
        normalized_tokens = _normalized_duplicate_name_tokens(filename)
        has_hash_duplicate = False

        if file_hash:
            first_hash_match = seen_hashes.get(file_hash)
            if first_hash_match is not None:
                has_hash_duplicate = True
                duplicate_hash_count += 1
                conflict_filename = str(first_hash_match.get("filename") or "").strip()
                conflict_path = str(first_hash_match.get("path") or "").strip()
                conflict_parent = str(first_hash_match.get("parent_name") or "").strip()
                conflict_size = first_hash_match.get("size_bytes")
                conflict_mtime = first_hash_match.get("source_mtime")
                conflict_label = conflict_filename or conflict_path or "earlier file in batch"
                warnings.append(
                    {
                        "code": "batch_duplicate_hash_match",
                        "message": "Hard duplicate: hash matched another file in this batch.",
                        "sha256": file_hash,
                        "filename": filename or None,
                        "conflicts_with": [
                            {
                                "scope": "batch",
                                "parent_kind": "batch_folder",
                                "parent_name": conflict_parent,
                                "path": conflict_path,
                                "filename": conflict_filename,
                                "label": conflict_label,
                                "size_bytes": conflict_size,
                                "source_mtime": conflict_mtime,
                            }
                        ],
                    }
                )
                findings.append(
                    {
                        "filename": filename or None,
                        "path": file_path or None,
                        "relative_path": relative_path or None,
                        "violation_code": "batch_duplicate_hash_match",
                        "violation_label": "Batch hash duplicate",
                        "check_key": "batch_duplicate_scan",
                        "scope": "batch",
                        "size_bytes": item_size_bytes,
                        "source_mtime": item_source_mtime,
                        "conflicts_with": [
                            {
                                "scope": "batch",
                                "parent_kind": "batch_folder",
                                "parent_name": conflict_parent,
                                "path": conflict_path,
                                "filename": conflict_filename,
                                "label": conflict_label,
                                "size_bytes": conflict_size,
                                "source_mtime": conflict_mtime,
                            }
                        ],
                        "sha256": file_hash,
                    }
                )
            else:
                seen_hashes[file_hash] = {
                    "filename": filename,
                    "path": file_path,
                    "parent_name": Path(file_path).parent.name if file_path else "",
                    "size_bytes": item_size_bytes,
                    "source_mtime": item_source_mtime,
                }

        exact_seen = bool(filename_key and filename_key in seen_exact_names)
        similar_match = _batch_duplicate_name_similarity(filename, seen_normalized_names)
        if not has_hash_duplicate and exact_seen:
            duplicate_name_exact_count += 1
            exact_match_meta = seen_exact_primary_names.get(filename_key, {})
            conflict_name = str(exact_match_meta.get("filename") or "").strip() or "earlier file in batch"
            conflict_item = {
                "scope": "batch",
                "parent_kind": "batch_folder",
                "parent_name": str(exact_match_meta.get("parent_name") or "").strip(),
                "path": str(exact_match_meta.get("path") or "").strip(),
                "filename": conflict_name,
                "label": conflict_name,
                "size_bytes": exact_match_meta.get("size_bytes"),
                "source_mtime": exact_match_meta.get("source_mtime"),
            }
            warnings.append(
                {
                    "code": "batch_duplicate_name_exact_match",
                    "message": "Exact filename matched another file in this batch.",
                    "filename": filename,
                    "conflicts_with": [conflict_item],
                }
            )
            findings.append(
                {
                    "filename": filename or None,
                    "path": file_path or None,
                    "relative_path": relative_path or None,
                    "violation_code": "batch_duplicate_name_exact_match",
                    "violation_label": "Batch exact filename duplicate",
                    "check_key": "batch_duplicate_scan",
                    "scope": "batch",
                    "size_bytes": item_size_bytes,
                    "source_mtime": item_source_mtime,
                    "conflicts_with": [conflict_item],
                }
            )
        elif not has_hash_duplicate and similar_match is not None:
            match_name, match_score = similar_match
            duplicate_name_soft_count += 1
            soft_match_meta = seen_normalized_primary_names.get(str(match_name or ""), {})
            soft_filename = str(soft_match_meta.get("filename") or "").strip() or match_name
            match_item = {
                "scope": "batch",
                "parent_kind": "batch_folder",
                "parent_name": str(soft_match_meta.get("parent_name") or "").strip(),
                "path": str(soft_match_meta.get("path") or "").strip(),
                "filename": soft_filename,
                "label": soft_filename,
                "size_bytes": soft_match_meta.get("size_bytes"),
                "source_mtime": soft_match_meta.get("source_mtime"),
            }
            warnings.append(
                {
                    "code": "batch_duplicate_name_soft_match",
                    "message": "Soft duplicate: filename variant matched another file in this batch.",
                    "filename": filename,
                    "normalized_name": normalized_name,
                    "matched_name": match_name,
                    "match_score": round(match_score, 3),
                    "conflicts_with": [match_item],
                }
            )
            findings.append(
                {
                    "filename": filename or None,
                    "path": file_path or None,
                    "relative_path": relative_path or None,
                    "violation_code": "batch_duplicate_name_soft_match",
                    "violation_label": "Batch near-name duplicate",
                    "check_key": "batch_duplicate_scan",
                    "scope": "batch",
                    "size_bytes": item_size_bytes,
                    "source_mtime": item_source_mtime,
                    "conflicts_with": [match_item],
                    "normalized_name": normalized_name,
                    "match_score": round(match_score, 3),
                }
            )

        if filename_key:
            seen_exact_names.add(filename_key)
            seen_exact_primary_names.setdefault(
                filename_key,
                {
                    "filename": filename,
                    "path": file_path,
                    "parent_name": Path(file_path).parent.name if file_path else "",
                    "size_bytes": item_size_bytes,
                    "source_mtime": item_source_mtime,
                },
            )
        if normalized_name:
            seen_normalized_names.append((filename, normalized_name, normalized_tokens))
            seen_normalized_primary_names.setdefault(
                normalized_name,
                {
                    "filename": filename,
                    "path": file_path,
                    "parent_name": Path(file_path).parent.name if file_path else "",
                    "size_bytes": item_size_bytes,
                    "source_mtime": item_source_mtime,
                },
            )

    return warnings, duplicate_hash_count, duplicate_name_exact_count, duplicate_name_soft_count, findings


def _normalize_indexed_conflicts(conflicts: list[Any]) -> list[dict[str, Any]]:
    """Return structured conflict rows so validation UI can always render source context."""
    normalized: list[dict[str, Any]] = []
    for conflict in conflicts:
        if isinstance(conflict, dict):
            filename = str(conflict.get("filename") or "").strip()
            path_text = str(conflict.get("path") or "").strip()
            normalized.append(
                {
                    "scope": str(conflict.get("scope") or "indexed").strip() or "indexed",
                    "parent_kind": str(conflict.get("parent_kind") or "indexed_inventory").strip() or "indexed_inventory",
                    "parent_name": str(conflict.get("parent_name") or "Indexed inventory").strip() or "Indexed inventory",
                    "path": path_text,
                    "filename": filename,
                    "label": str(conflict.get("label") or filename or path_text).strip(),
                    "size_bytes": conflict.get("size_bytes"),
                    "source_mtime": conflict.get("source_mtime"),
                    "preview_url": str(conflict.get("preview_url") or "").strip() or None,
                }
            )
            continue

        conflict_name = str(conflict or "").strip()
        if not conflict_name:
            continue
        normalized.append(
            {
                "scope": "indexed",
                "parent_kind": "indexed_inventory",
                "parent_name": "Indexed inventory",
                "path": f"name-only match: {conflict_name}",
                "filename": conflict_name,
                "label": conflict_name,
            }
        )

    return normalized


def _build_validation_checks(
    *,
    warning_codes: set[str],
    expanded_files: list[dict[str, Any]],
    duplicate_hashes: list[str],
    duplicate_name_exact_count: int = 0,
    duplicate_name_soft_count: int = 0,
    batch_duplicate_hash_count: int = 0,
    batch_duplicate_name_exact_count: int = 0,
    batch_duplicate_name_soft_count: int = 0,
    duplicate_findings: list[dict[str, Any]] | None = None,
    batch_duplicate_findings: list[dict[str, Any]] | None = None,
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
            ) + (
                f" Offending files: {len(duplicate_findings or [])}."
                if duplicate_findings
                else ""
            ),
            "findings": duplicate_findings or [],
        },
        {
            "key": "batch_duplicate_scan",
            "label": "Resolved files do not duplicate each other within this batch",
            "passed": not (
                {"batch_duplicate_hash_match", "batch_duplicate_name_exact_match", "batch_duplicate_name_soft_match"}
                & warning_codes
            ),
            "detail": (
                "No duplicate hard or soft filename matches were detected within this batch."
                if not (
                    {"batch_duplicate_hash_match", "batch_duplicate_name_exact_match", "batch_duplicate_name_soft_match"}
                    & warning_codes
                )
                else (
                    "Detected "
                    + ", ".join(
                        [
                            segment
                            for segment in [
                                f"{batch_duplicate_hash_count} hard hash match(es)" if batch_duplicate_hash_count else "",
                                f"{batch_duplicate_name_exact_count} exact filename match(es)" if batch_duplicate_name_exact_count else "",
                                f"{batch_duplicate_name_soft_count} soft filename variant match(es)" if batch_duplicate_name_soft_count else "",
                            ]
                            if segment
                        ]
                    )
                    + " within this batch."
                )
            ) + (
                f" Offending files: {len(batch_duplicate_findings or [])}."
                if batch_duplicate_findings
                else ""
            ),
            "findings": batch_duplicate_findings or [],
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


# --- Sidecar metadata discovery (Phase 1: read-only enrichment) -------------
#
# When a planned group's source selection includes folders that carry sibling
# ``.modelmeta.json`` and/or ``README.md`` sidecars (e.g. Working Files
# directories), surface that metadata on the plan preview so downstream UI can
# offer to carry it forward into the new Catalog item. This stage is strictly
# additive and never mutates plan behavior -- it only attaches a
# ``detected_metadata`` payload per planned model.
#
# README routing:
#   * <= INLINE threshold chars -> render inline in the wizard
#   * >  INLINE threshold chars -> recommend attaching as a curated asset
# README content is also hard-capped at INCLUDE_MAX chars to keep the plan
# response bounded; a ``readme_truncated`` flag warns the UI when this fires.
_README_INLINE_THRESHOLD_CHARS = 1024
_README_INCLUDE_MAX_CHARS = 16 * 1024


def _discover_source_metadata(group: dict[str, Any]) -> dict[str, Any] | None:
    """Inspect a planned group's source folders for sidecar metadata.

    Returns ``None`` when no ``.modelmeta.json`` or ``README.md`` is found in
    any of the group's selected/parent folders. Otherwise returns a payload
    describing where the sidecars came from, a merged best-effort summary
    suitable for prefilling the destination form, and a confidence rating.
    """
    source_entries = group.get("source_entries") or []
    files = group.get("files") or []

    full_folder_entry_paths: list[Path] = []
    candidate_folders: list[Path] = []
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        entry_path_raw = str(entry.get("path") or "").strip()
        if not entry_path_raw:
            continue
        try:
            entry_path = Path(entry_path_raw).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if entry_type == "folder":
            full_folder_entry_paths.append(entry_path)
            candidate_folders.append(entry_path)
        elif entry_type == "file":
            candidate_folders.append(entry_path.parent)

    # Deduplicate candidates while preserving order
    seen_keys: set[str] = set()
    unique_candidates: list[Path] = []
    for folder in candidate_folders:
        key = str(folder)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_candidates.append(folder)

    # Lazy import to avoid circular module load between intake_verification
    # and working routers at import time.
    try:
        from .working import _read_folder_sidecar  # type: ignore
    except Exception:  # pragma: no cover - defensive fallback
        return None

    sidecar_hits: list[tuple[Path, dict[str, Any]]] = []
    for folder in unique_candidates:
        try:
            if not folder.is_dir():
                continue
        except OSError:
            continue
        sidecar = _read_folder_sidecar(folder)
        has_modelmeta = isinstance(sidecar.get("modelmeta"), dict)
        has_readme = isinstance(sidecar.get("readme"), str) and bool(sidecar.get("readme"))
        if has_modelmeta or has_readme:
            sidecar_hits.append((folder, sidecar))

    if not sidecar_hits:
        return None

    # Confidence:
    #   high   -- exactly one sidecar folder AND the user selected that whole
    #             folder as a source entry (no partial subselection)
    #   medium -- exactly one sidecar folder but selection is partial (file
    #             entry, or folder entry sitting below the sidecar folder)
    #   low    -- multiple distinct sidecar folders contribute to this group
    if len(sidecar_hits) == 1:
        sidecar_folder, _ = sidecar_hits[0]
        if any(sidecar_folder == fe for fe in full_folder_entry_paths):
            confidence = "high"
        else:
            confidence = "medium"
    else:
        confidence = "low"

    selected_filenames: set[str] = set()
    selected_relpaths: set[str] = set()
    for file_item in files:
        if not isinstance(file_item, dict):
            continue
        path_value = str(file_item.get("path") or "").strip()
        if path_value:
            selected_filenames.add(Path(path_value).name)
        rel_value = str(file_item.get("relative_path") or "").strip()
        if rel_value:
            selected_relpaths.add(rel_value)

    sources_payload: list[dict[str, Any]] = []
    titles: list[str] = []
    origins: list[str] = []
    primary_files: list[str] = []
    tag_seen: set[str] = set()
    tag_union: list[str] = []
    readmes: list[tuple[str, str]] = []
    thumbnail_hint: dict[str, Any] | None = None
    parse_errors: list[dict[str, str]] = []

    for sidecar_folder, sidecar in sorted(sidecar_hits, key=lambda item: str(item[0])):
        modelmeta = sidecar.get("modelmeta") if isinstance(sidecar.get("modelmeta"), dict) else None
        readme_text = sidecar.get("readme") if isinstance(sidecar.get("readme"), str) else None
        modelmeta_error = sidecar.get("modelmeta_error")
        readme_error = sidecar.get("readme_error")

        sources_payload.append(
            {
                "folder": sidecar_folder.name,
                "folder_path": str(sidecar_folder),
                "has_modelmeta": modelmeta is not None,
                "has_readme": bool(readme_text),
                "readme_bytes": len(readme_text) if readme_text else 0,
            }
        )
        if modelmeta_error:
            parse_errors.append(
                {"folder": sidecar_folder.name, "sidecar": "modelmeta", "error": str(modelmeta_error)}
            )
        if readme_error:
            parse_errors.append(
                {"folder": sidecar_folder.name, "sidecar": "readme", "error": str(readme_error)}
            )

        if modelmeta:
            display_title = str(modelmeta.get("display_title") or "").strip()
            if display_title:
                titles.append(display_title)
            origin_url = str(modelmeta.get("origin_url") or "").strip()
            if origin_url:
                origins.append(origin_url)
            primary_file = str(modelmeta.get("primary_file") or "").strip()
            if primary_file:
                primary_files.append(primary_file)
            raw_tags = modelmeta.get("tags")
            if isinstance(raw_tags, list):
                for tag in raw_tags:
                    tag_str = str(tag).strip()
                    if not tag_str:
                        continue
                    norm = tag_str.lower()
                    if norm in tag_seen:
                        continue
                    tag_seen.add(norm)
                    tag_union.append(tag_str)
            if thumbnail_hint is None:
                thumbnail_value = str(modelmeta.get("thumbnail") or "").strip()
                if thumbnail_value:
                    thumb_name = Path(thumbnail_value).name
                    thumbnail_hint = {
                        "filename": thumbnail_value,
                        "source_folder": sidecar_folder.name,
                        "in_selection": thumb_name in selected_filenames
                        or thumbnail_value in selected_relpaths,
                    }
        if readme_text:
            readmes.append((sidecar_folder.name, readme_text))

    # Concatenate READMEs across multiple sidecar folders
    if len(readmes) == 1:
        combined_readme = readmes[0][1]
    elif len(readmes) > 1:
        combined_readme = "\n\n---\n\n".join(
            f"## From `{folder_name}`\n\n{text}" for folder_name, text in readmes
        )
    else:
        combined_readme = ""

    readme_truncated = False
    if len(combined_readme) > _README_INCLUDE_MAX_CHARS:
        combined_readme = combined_readme[:_README_INCLUDE_MAX_CHARS]
        readme_truncated = True

    merged: dict[str, Any] = {}
    if titles:
        merged["display_title"] = titles[0]
    if tag_union:
        merged["tags"] = tag_union
    if origins:
        merged["origin_url"] = origins[0]
    if primary_files:
        for primary_file in primary_files:
            primary_basename = Path(primary_file).name
            if primary_file in selected_relpaths or primary_basename in selected_filenames:
                merged["primary_file"] = primary_file
                break
    if combined_readme:
        readme_route = (
            "attached" if len(combined_readme) > _README_INLINE_THRESHOLD_CHARS else "inline"
        )
        merged["readme_text"] = combined_readme
        merged["readme_truncated"] = readme_truncated
        merged["readme_route"] = readme_route

    result: dict[str, Any] = {
        "confidence": confidence,
        "sources": sources_payload,
    }
    if merged:
        result["merged"] = merged
    if thumbnail_hint:
        result["thumbnail_hint"] = thumbnail_hint
    if parse_errors:
        result["parse_errors"] = parse_errors
    return result


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
    detected_metadata = _discover_source_metadata(group)
    if detected_metadata is not None:
        summarized_group["detected_metadata"] = detected_metadata
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
    # Explicit override from UI: only custom title-basis should be treated as
    # authoritative. For derived modes (folder/first-file), compute from
    # strategy so stale client hints do not leak into model names.
    title_source = str(source_entry.get("group_title_source") or "").strip().lower().replace("_", "-")
    raw_group_title = str(source_entry.get("group_title") or "").strip()
    explicit_title = raw_group_title if (raw_group_title and title_source in {"", "custom"}) else ""

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
    entry_type = str(source_entry.get("type") or "").strip().lower()
    if title_source == "folder" and entry_type == "folder":
        return _display_title_from_path(root_path.name or str(root_path)) or "Working Group"
    return _display_title_from_path(file_path.name) or file_path.stem or file_path.name or "Working Group"
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

    # Exclude the inventory rows that correspond to the source files being
    # submitted: when a user selects a file from the Working Files root the
    # file is already in `working_file_inventory`, and without this exclusion
    # its own hash would surface as a duplicate against itself.
    submit_self_exclude_keys: set[str] = set()
    if auto_validate:
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            raw_path = str(raw_item.get("source_path") or raw_item.get("path") or "").strip()
            if not raw_path:
                continue
            try:
                resolved = Path(raw_path).expanduser().resolve()
            except (OSError, RuntimeError):
                continue
            key = _normalize_path_compare_key(str(resolved))
            if key:
                submit_self_exclude_keys.add(key)
    existing_hashes = (
        get_all_indexed_file_hashes(
            state.settings.db_path,
            exclude_source_paths=submit_self_exclude_keys or None,
        )
        if auto_validate
        else set()
    )
    batch_seen_hashes: set[str] = set()
    batch_seen_exact_names: set[str] = set()
    batch_seen_normalized_names: list[tuple[str, tuple[str, ...]]] = []

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
                filename = source_path.name.strip()
                filename_key = filename.lower()
                normalized_name = _normalized_duplicate_name(filename)
                normalized_tokens = _normalized_duplicate_name_tokens(filename)
                if file_hash and file_hash in batch_seen_hashes:
                    validation_state = "duplicate_candidate"
                    warnings.append(
                        {
                            "code": "batch_duplicate_hash_match",
                            "message": "Hard duplicate: hash matched another file in this batch",
                            "sha256": file_hash,
                            "filename": filename,
                        }
                    )
                elif filename_key and filename_key in batch_seen_exact_names:
                    validation_state = "duplicate_candidate"
                    warnings.append(
                        {
                            "code": "batch_duplicate_name_exact_match",
                            "message": "Exact filename matched another file in this batch",
                            "filename": filename,
                        }
                    )
                else:
                    similar_match = _batch_duplicate_name_similarity(filename, batch_seen_normalized_names)
                    if similar_match is not None:
                        match_name, match_score = similar_match
                        validation_state = "duplicate_candidate"
                        warnings.append(
                            {
                                "code": "batch_duplicate_name_soft_match",
                                "message": "Soft duplicate: filename variant matched another file in this batch",
                                "filename": filename,
                                "normalized_name": normalized_name,
                                "matched_name": match_name,
                                "match_score": round(match_score, 3),
                            }
                        )
                if file_hash:
                    batch_seen_hashes.add(file_hash)
                if filename_key:
                    batch_seen_exact_names.add(filename_key)
                if normalized_name:
                    batch_seen_normalized_names.append((filename, normalized_name, normalized_tokens))

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

    # Working-groups duplicate check removed in PR E.3 (table dropped).
    # Future enhancement: re-check against get_all_indexed_file_hashes if needed.
    duplicate_hashes: list[dict[str, Any]] = []
    unique_hashes: list[str] = [
        h for h in (
            str(file_item.get("file_hash") or "").strip().lower()
            for file_item in expanded_files
        ) if h
    ]

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
                   source_entries_json, file_hashes_json, uploaded_file_ids_json, error_json,
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
            "uploaded_file_ids": json.loads(str(row["uploaded_file_ids_json"] or "[]")),
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

    existing_hashes = get_all_indexed_file_hashes(
        state.settings.db_path,
        exclude_source_paths=_collect_self_exclude_compare_keys(expanded_files),
        exclude_upload_id=item_id,
    )
    indexed_hash_contexts = _read_indexed_hash_match_contexts(
        state.settings.db_path,
        exclude_upload_id=item_id,
    )
    indexed_exact_names, indexed_normalized_names, indexed_exact_contexts, indexed_normalized_contexts = _read_indexed_filename_maps(
        state.settings.db_path,
        exclude_upload_id=item_id,
    )
    file_hashes: list[str] = []
    duplicate_hashes: list[str] = []
    duplicate_name_exact_count = 0
    duplicate_name_soft_count = 0
    duplicate_findings: list[dict[str, Any]] = []
    for file_item in expanded_files:
        file_hash = str(file_item.get("file_hash") or "").strip().lower()
        file_path = str(file_item.get("path") or "").strip()
        filename = str(file_item.get("filename") or Path(str(file_item.get("path") or "")).name).strip()
        relative_path = str(file_item.get("relative_path") or "").strip().replace("\\", "/")
        filename_key = filename.lower()
        item_size_bytes = file_item.get("size_bytes")
        item_source_mtime = str((file_item.get("source_metadata") or {}).get("source_mtime") or "").strip() or None
        has_hash_duplicate = False
        has_exact_name_duplicate = False
        if not file_hash:
            pass
        else:
            file_hashes.append(file_hash)
            if file_hash in existing_hashes:
                has_hash_duplicate = True
                duplicate_hashes.append(file_hash)
                validation_state = "duplicate_candidate"
                hash_conflicts = indexed_hash_contexts.get(file_hash, [])
                warnings.append(
                    {
                        "code": "working_group_hash_match",
                        "message": "Hard duplicate: hash matched an existing indexed file.",
                        "sha256": file_hash,
                        "filename": filename,
                        "conflicts_with": hash_conflicts[:3],
                    }
                )
                duplicate_findings.append(
                    {
                        "filename": filename,
                        "path": file_path,
                        "relative_path": relative_path,
                        "violation_code": "working_group_hash_match",
                        "violation_label": "Indexed hash match",
                        "check_key": "duplicate_scan",
                        "scope": "indexed",
                        "conflicts_with": hash_conflicts[:3],
                        "sha256": file_hash,
                        "size_bytes": item_size_bytes,
                        "source_mtime": item_source_mtime,
                    }
                )

        exact_name_matches = sorted(indexed_exact_names.get(filename_key, set())) if filename_key else []
        if not has_hash_duplicate and exact_name_matches:
            has_exact_name_duplicate = True
            duplicate_name_exact_count += 1
            validation_state = "duplicate_candidate"
            exact_context_matches = indexed_exact_contexts.get(filename_key, []) if filename_key else []
            exact_conflicts = _normalize_indexed_conflicts(
                exact_context_matches[:3] if exact_context_matches else exact_name_matches[:3]
            )
            warnings.append(
                {
                    "code": "duplicate_name_exact_match",
                    "message": "Exact filename matched an existing indexed file.",
                    "filename": filename,
                    "matches": exact_name_matches[:3],
                    "conflicts_with": exact_conflicts,
                }
            )
            duplicate_findings.append(
                {
                    "filename": filename,
                    "path": file_path,
                    "relative_path": relative_path,
                    "violation_code": "duplicate_name_exact_match",
                    "violation_label": "Indexed exact filename match",
                    "check_key": "duplicate_scan",
                    "scope": "indexed",
                    "conflicts_with": exact_conflicts,
                    "size_bytes": item_size_bytes,
                    "source_mtime": item_source_mtime,
                }
            )

        normalized_name = _normalized_duplicate_name(filename)
        if normalized_name and not has_hash_duplicate and not has_exact_name_duplicate:
            soft_name_matches = [
                candidate
                for candidate in sorted(indexed_normalized_names.get(normalized_name, set()))
                if candidate.lower() != filename_key
            ]
            if soft_name_matches:
                duplicate_name_soft_count += 1
                validation_state = "duplicate_candidate"
                soft_context_matches = indexed_normalized_contexts.get(normalized_name, []) if normalized_name else []
                soft_conflicts = _normalize_indexed_conflicts(
                    soft_context_matches[:3] if soft_context_matches else soft_name_matches[:3]
                )
                warnings.append(
                    {
                        "code": "duplicate_name_soft_match",
                        "message": "Soft duplicate: filename variant matched an existing indexed file.",
                        "filename": filename,
                        "normalized_name": normalized_name,
                        "matches": soft_name_matches[:3],
                        "conflicts_with": soft_conflicts,
                    }
                )
                duplicate_findings.append(
                    {
                        "filename": filename,
                        "path": file_path,
                        "relative_path": relative_path,
                        "violation_code": "duplicate_name_soft_match",
                        "violation_label": "Indexed near-name match",
                        "check_key": "duplicate_scan",
                        "scope": "indexed",
                        "conflicts_with": soft_conflicts,
                        "normalized_name": normalized_name,
                        "size_bytes": item_size_bytes,
                        "source_mtime": item_source_mtime,
                    }
                )

    batch_duplicate_warnings, batch_duplicate_hash_count, batch_duplicate_name_exact_count, batch_duplicate_name_soft_count, batch_duplicate_findings = _scan_batch_duplicate_warnings(
        expanded_files
    )
    if batch_duplicate_warnings:
        warnings.extend(batch_duplicate_warnings)
        validation_state = "duplicate_candidate"

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
        batch_duplicate_hash_count=batch_duplicate_hash_count,
        batch_duplicate_name_exact_count=batch_duplicate_name_exact_count,
        batch_duplicate_name_soft_count=batch_duplicate_name_soft_count,
        duplicate_findings=duplicate_findings,
        batch_duplicate_findings=batch_duplicate_findings,
        source_entries=source_entries,
    )

    next_inbox_state = "validated_ready" if validation_state == "ready" else "validated_warning"
    decision_note_payload = {
        "warnings": warnings,
        "validation_actions": [],
    }
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
                json.dumps(decision_note_payload),
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


@router.post("/api/intake/items/{item_id}/validation-actions")
def set_intake_item_validation_actions(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    payload = payload or {}
    item_row = _get_intake_item_row(request.app.state.model_catalog.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    action_payload = payload.get("action") if isinstance(payload.get("action"), dict) else payload
    if not isinstance(action_payload, dict):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Provide an action object with finding_key and decision.",
            },
        )
    normalized_action, action_error = _normalize_validation_action(action_payload)
    if action_error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "invalid_payload", "message": action_error},
        )

    note_payload = _parse_decision_note_payload(item_row.get("decision_note"))
    existing_actions = [entry for entry in note_payload.get("validation_actions", []) if isinstance(entry, dict)]
    finding_key = str(normalized_action.get("finding_key") or "").strip().lower()
    existing_actions = [
        entry
        for entry in existing_actions
        if str(entry.get("finding_key") or "").strip().lower() != finding_key
    ]

    decision = str(normalized_action.get("decision") or "review").strip().lower()
    existing_actions.append(normalized_action)

    updated_note_payload = {
        "warnings": note_payload.get("warnings", []),
        "validation_actions": existing_actions,
    }

    connection = connect(request.app.state.model_catalog.settings.db_path)
    try:
        connection.execute(
            """
            UPDATE intake_queue_uploads
            SET decision_note = ?,
                updated_at = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps(updated_note_payload),
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
        event_type="intake_validation_action_set",
        payload={
            "item_id": item_id,
            "decision": decision,
            "finding_key": finding_key,
            "action_count": len(existing_actions),
        },
    )

    return {
        "success": True,
        "item_id": item_id,
        "decision_note": updated_note_payload,
        "validation_action_count": len(existing_actions),
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
    """PR E.1 removed working groups. This endpoint is permanently gone."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=410,
        content={
            "ok": False,
            "error": {
                "code": "endpoint_removed",
                "message": (
                    "Working groups were removed in PR E.1. "
                    "Use the local catalog (POST /api/local/models) to record intake instead."
                ),
            },
        },
    )
