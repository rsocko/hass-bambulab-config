"""
Intake queue upload management endpoints.

Handles:
    state: AppState = request.app.state.model_catalog
    request_started = time.perf_counter()
- Queue lifecycle (create, list, delete, status transitions)
- Browser-based file upload staging
- Server filesystem browsing for source selection
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from sqlite3 import connect
from typing import Any

from starlette.datastructures import UploadFile

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..settings import Settings
from ..state import AppState



from .._helpers import (
    SUPPORTED_INTAKE_FILE_EXTENSIONS,
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    LOCAL_IMPORT_IMAGE_EXTENSIONS,
    LOCAL_IMPORT_DOCUMENT_EXTENSIONS,
    _bulk_timestamp_iso,
    _bulk_utc_now_iso,
    _compile_source_entry_exclusions,
    _coerce_bool,
    _collect_intake_source_files_in_folder,
    _configured_intake_browse_roots,
    _configured_intake_source_roots,
    _enforce_source_entries_within_intake_roots,
    _is_excluded_source_file,
    _is_path_within_roots,
)

router = APIRouter(tags=["intake"])


# ==================== CONSTANTS ====================

BROWSER_INTAKE_UPLOAD_STORAGE_DIR = "intake_browser_uploads"

# Valid state transitions for intake queue uploads
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"uploading", "failed"},
    "uploading": {"uploaded_unverified", "failed"},
    "uploaded_unverified": {"verified", "failed"},
    "verified": {"cleanup_pending", "failed"},
    "cleanup_pending": {"cleanup_done", "cleanup_failed", "failed"},
    "cleanup_done": {"failed"},
    "cleanup_failed": {"cleanup_pending", "failed"},
    "failed": set(),
}

_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

_INTAKE_PREVIEW_MAX_BYTES = 5 * 1024 * 1024  # 5 MB for direct image previews
_INTAKE_PREVIEW_MAX_3MF_BYTES = 200 * 1024 * 1024  # cap package reads for thumbnail extraction
_INTAKE_UPLOAD_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


# ==================== HELPER FUNCTIONS ====================

def _browser_intake_upload_storage_root(settings: Settings) -> Path:
    return (settings.db_path.parent / BROWSER_INTAKE_UPLOAD_STORAGE_DIR).resolve()


def _sanitize_filesystem_segment(segment: str, *, fallback: str = "item") -> str:
    value = re.sub(r"[<>:\\|?*\x00-\x1f]", "_", str(segment or "").strip())
    value = value.rstrip(" .")
    if not value:
        value = fallback
    device_name = value.split(".", 1)[0].upper()
    if device_name in _WINDOWS_RESERVED_NAMES:
        value = f"{value}_"
    return value


def _sanitize_browser_upload_relative_path(relative_path: str | None, fallback_name: str) -> Path:
    raw_value = str(relative_path or "").strip().replace("\\", "/")
    fallback_raw = Path(fallback_name or "upload.bin").name or "upload.bin"
    fallback = Path(_sanitize_filesystem_segment(fallback_raw, fallback="upload.bin"))
    if not raw_value:
        return fallback

    candidate = PurePosixPath(raw_value)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        return fallback

    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts:
        return fallback

    normalized_parts = [_sanitize_filesystem_segment(part, fallback="item") for part in parts]

    sanitized = Path(*normalized_parts)
    if sanitized.name in {"", ".", ".."}:
        return fallback
    return sanitized


def _expand_server_archive_source_entries(
    settings: Settings,
    source_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand server-side ZIP source entries into staged file entries.

    Browser ZIP files are expanded client-side before upload. This helper brings
    server-browse ZIP selections to the same contract by expanding each archive
    into staged member-file entries consumed by existing intake validation and
    publish flows.
    """
    expanded_entries: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for entry in source_entries:
        if not isinstance(entry, dict):
            continue

        entry_type = str(entry.get("type") or "").strip().lower()
        source_type = str(entry.get("source_type") or "").strip().lower()
        entry_path_raw = str(entry.get("path") or "").strip()

        if entry_type != "file" or not entry_path_raw or source_type == "browser_upload":
            expanded_entries.append(entry)
            continue

        entry_path = Path(entry_path_raw).expanduser().resolve()
        if entry_path.suffix.lower() != ".zip":
            expanded_entries.append(entry)
            continue
        if not entry_path.exists() or not entry_path.is_file():
            expanded_entries.append(entry)
            continue

        archive_root_name = _sanitize_filesystem_segment(entry_path.stem or entry_path.name, fallback="archive")
        archive_upload_id = str(uuid.uuid4())
        archive_stage_root = (_browser_intake_upload_storage_root(settings) / archive_upload_id).resolve()
        archive_stage_root.mkdir(parents=True, exist_ok=True)

        archive_member_count = 0
        archive_member_files = 0
        try:
            with zipfile.ZipFile(entry_path) as archive:
                for zip_info in archive.infolist():
                    archive_member_count += 1
                    if zip_info.is_dir():
                        continue

                    normalized_relative = _sanitize_browser_upload_relative_path(zip_info.filename, fallback_name=Path(zip_info.filename).name or "file.bin")
                    member_relative = Path(archive_root_name) / normalized_relative
                    stage_path = (archive_stage_root / member_relative).resolve()
                    if not stage_path.is_relative_to(archive_stage_root):
                        continue

                    stage_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(zip_info, "r") as src, stage_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

                    stat_result = stage_path.stat()
                    from .._helpers import _bulk_path_source_metadata
                    staged_metadata = _bulk_path_source_metadata(stage_path, stat_result)

                    expanded_entry = {
                        "type": "file",
                        "path": str(stage_path),
                        "recurse": False,
                        "excluded_items": [],
                        "source_mtime": staged_metadata["source_mtime"],
                        "source_ctime": staged_metadata["source_ctime"],
                        "source_birthtime": staged_metadata.get("source_birthtime"),
                        "source_size_bytes": int(stat_result.st_size),
                        "source_type": "server_archive_upload",
                        "upload_id": archive_upload_id,
                        "original_filename": entry_path.name,
                        "relative_path": str(member_relative).replace("\\", "/"),
                    }

                    for carry_key in (
                        "grouping_strategy",
                        "preserve_folder_structure",
                        "group_title_source",
                        "group_title",
                    ):
                        carry_value = entry.get(carry_key)
                        if carry_value not in {None, ""}:
                            expanded_entry[carry_key] = carry_value

                    expanded_entries.append(expanded_entry)
                    archive_member_files += 1
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            warnings.append(
                {
                    "code": "archive_expand_failed",
                    "message": f"Could not expand archive: {entry_path.name}",
                    "path": str(entry_path),
                    "detail": str(error),
                }
            )
            shutil.rmtree(archive_stage_root, ignore_errors=True)
            expanded_entries.append(entry)
            continue

        if archive_member_files <= 0:
            warnings.append(
                {
                    "code": "archive_empty",
                    "message": f"Archive has no files to import: {entry_path.name}",
                    "path": str(entry_path),
                }
            )
            shutil.rmtree(archive_stage_root, ignore_errors=True)
            expanded_entries.append(entry)
            continue

        warnings.append(
            {
                "code": "archive_expanded",
                "message": f"Expanded archive {entry_path.name} into {archive_member_files} file(s).",
                "path": str(entry_path),
                "member_count": archive_member_count,
                "expanded_file_count": archive_member_files,
            }
        )

    return expanded_entries, warnings


def _browser_upload_stage_directories(settings: Settings, source_entries: list[dict[str, Any]]) -> list[Path]:
    storage_root = _browser_intake_upload_storage_root(settings)
    directories: set[Path] = set()
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        source_type = str(entry.get("source_type") or "").strip().lower()
        if source_type not in {"browser_upload", "server_archive_upload"}:
            continue

        upload_id = str(entry.get("upload_id") or "").strip()
        if upload_id:
            directories.add((storage_root / upload_id).resolve())
            continue

        entry_path_raw = str(entry.get("path") or "").strip()
        if not entry_path_raw:
            continue
        entry_path = Path(entry_path_raw).expanduser().resolve()
        if not entry_path.is_relative_to(storage_root):
            continue
        relative_path = entry_path.relative_to(storage_root)
        if relative_path.parts:
            directories.add((storage_root / relative_path.parts[0]).resolve())

    return sorted(directories)


def _source_intake_storage_root(settings: Settings) -> Path:
    db_path_text = str(settings.db_path)
    if db_path_text == ":memory:":
        return Path(tempfile.gettempdir()) / "model_catalog_source_intake"
    return Path(settings.db_path).resolve().parent / ".source_intake"


def _makerworld_stage_directories(settings: Settings, source_entries: list[dict[str, Any]]) -> list[Path]:
    storage_root = _source_intake_storage_root(settings).resolve()
    directories: set[Path] = set()
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        source_type = str(entry.get("source_type") or "").strip().lower()
        if source_type != "makerworld_download":
            continue

        record_id = str(entry.get("source_record_id") or "").strip()
        if record_id:
            candidate = (storage_root / record_id).resolve()
            if candidate.is_relative_to(storage_root):
                directories.add(candidate)
            continue

        entry_path_raw = str(entry.get("path") or "").strip()
        if not entry_path_raw:
            continue
        entry_path = Path(entry_path_raw).expanduser().resolve()
        if not entry_path.is_relative_to(storage_root):
            continue
        relative_path = entry_path.relative_to(storage_root)
        if relative_path.parts:
            directories.add((storage_root / relative_path.parts[0]).resolve())

    return sorted(directories)


def _intake_browse_allowlist_roots(settings: Settings) -> list[Path]:
    allowlist_raw = os.environ.get("BAMBULAB_INTAKE_ALLOWLIST", "/models,/storage")
    env_roots = [
        Path(p.strip()).expanduser().resolve()
        for p in allowlist_raw.split(",")
        if p.strip()
    ]
    # Keep legacy env allowlist support, but mirror the wizard browse contract
    # (intake roots + working-files root) so preview authorization matches.
    return sorted({*env_roots, *_configured_intake_browse_roots(settings)})


def _image_mime_for_suffix(path: Path) -> str:
    guessed, _encoding = mimetypes.guess_type(str(path))
    if guessed and guessed.startswith("image/"):
        return guessed
    suffix = str(path.suffix or "").lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def _normalize_intake_cleanup_policy(value: object | None) -> str:
    cleanup_policy = str(value or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        return "keep"
    return cleanup_policy


def _normalize_browser_intake_cleanup_policy(value: object | None) -> str:
    _ = value
    # Browser uploads are always ephemeral staging files that should be
    # removed after successful materialization into local/working storage.
    return "delete_on_verified"


def _normalize_terminal_actor(actor: object | None, *, fallback: str = "sidecar_api") -> str:
    value = str(actor or "").strip()
    return value or fallback


def _split_terminal_result_ids(value: object | None) -> list[str]:
    return [
        segment.strip()
        for segment in str(value or "").split(",")
        if segment and segment.strip()
    ]


def _normalize_terminal_result(terminal_action: object | None, terminal_result_id: object | None) -> dict[str, Any]:
    action = str(terminal_action or "").strip().lower()
    raw_value = str(terminal_result_id or "").strip()
    payload: Any = None
    if raw_value[:1] in {"{", "["}:
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            payload = None

    result: dict[str, Any] = {
        "kind": "none",
        "primary_result_id": None,
        "local_model_ids": [],
        "group_results": [],
        "raw": terminal_result_id,
    }

    if action == "published_by_destination" and isinstance(payload, dict):
        local_model_ids = [
            str(value).strip()
            for value in (payload.get("curated_model_ids") or payload.get("curated") or [])
            if str(value).strip()
        ]
        group_results: list[dict[str, Any]] = []
        for item in payload.get("group_results") or []:
            if not isinstance(item, dict):
                continue
            destination = str(item.get("destination") or "").strip().lower()
            match_mode = str(item.get("match_mode") or "").strip().lower()
            result_id = str(
                item.get("result_id")
                or item.get("local_model_id")
                or ""
            ).strip()
            outcome_action = str(item.get("action") or "").strip().lower()
            if not outcome_action and destination == "curated":
                outcome_action = "published_to_catalog"
            group_results.append(
                {
                    "destination": destination,
                    "match_mode": match_mode,
                    "result_id": result_id,
                    "action": outcome_action,
                }
            )

        primary_result_id = local_model_ids[0] if local_model_ids else None
        result.update(
            {
                "kind": "destination_publish",
                "primary_result_id": primary_result_id,
                "local_model_ids": local_model_ids,
                "group_results": group_results,
            }
        )
        return result

    if action == "published_to_catalog":
        local_model_ids = _split_terminal_result_ids(raw_value)
        result.update(
            {
                "kind": "curated_models",
                "primary_result_id": local_model_ids[0] if local_model_ids else None,
                "local_model_ids": local_model_ids,
            }
        )
        return result

    return result


def _derive_terminal_display_action(terminal_action: object | None, terminal_result_id: object | None) -> str:
    action = str(terminal_action or "").strip().lower()
    if action != "published_by_destination":
        return action

    normalized_result = _normalize_terminal_result(action, terminal_result_id)
    local_model_ids = normalized_result.get("local_model_ids") or []

    if local_model_ids:
        return "published_to_catalog"

    return "completed"


def _stable_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _payload_signature(value: Any) -> str:
    return hashlib.sha256(_stable_json_dumps(value).encode("utf-8")).hexdigest()


def _content_signature(value: bytes | str) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).hexdigest()


def _duration_ms(start_time: float) -> int:
    return max(0, int((time.perf_counter() - start_time) * 1000))


def _normalize_upload_telemetry(telemetry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not telemetry:
        return None

    transport_mode = str(telemetry.get("transport_mode") or "").strip() or None
    payload_bytes_raw = telemetry.get("payload_bytes_raw")
    payload_bytes_encoded = telemetry.get("payload_bytes_encoded")
    upload_duration_ms = telemetry.get("upload_duration_ms")
    staging_write_duration_ms = telemetry.get("staging_write_duration_ms")
    warnings_count = telemetry.get("warnings_count")

    normalized = {
        "transport_mode": transport_mode,
        "payload_bytes_raw": int(payload_bytes_raw) if payload_bytes_raw is not None else None,
        "payload_bytes_encoded": int(payload_bytes_encoded) if payload_bytes_encoded is not None else None,
        "upload_duration_ms": int(upload_duration_ms) if upload_duration_ms is not None else None,
        "staging_write_duration_ms": int(staging_write_duration_ms) if staging_write_duration_ms is not None else None,
        "warnings_count": int(warnings_count) if warnings_count is not None else None,
    }
    if all(value is None for value in normalized.values()):
        return None
    return normalized


def _idempotency_expires_at(now_iso: str) -> str:
    now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    expires_dt = now_dt + timedelta(seconds=_INTAKE_UPLOAD_IDEMPOTENCY_TTL_SECONDS)
    return expires_dt.isoformat().replace("+00:00", "Z")


def _normalize_server_selection_signature(selections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in selections:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        if entry_type not in {"file", "folder"}:
            continue
        entry_path = str(entry.get("path") or "").strip()
        if not entry_path:
            continue
        try:
            normalized_path = str(Path(entry_path).expanduser().resolve())
        except (OSError, RuntimeError):
            normalized_path = entry_path
        normalized.append(
            {
                "type": entry_type,
                "path": normalized_path,
                "recurse": _coerce_bool(entry.get("recurse", True)) if entry_type == "folder" else False,
            }
        )
    return normalized


def _response_with_idempotency(response_payload: dict[str, Any], *, key: str | None, replayed: bool) -> dict[str, Any]:
    idempotency_key = str(key or "").strip()
    if not idempotency_key:
        return response_payload
    payload = dict(response_payload)
    payload["replayed"] = replayed
    payload["idempotency"] = {"key": idempotency_key, "replayed": replayed}
    return payload


def _idempotency_conflict_response(*, key: str, upload_id: str | None = None) -> JSONResponse:
    payload: dict[str, Any] = {
        "success": False,
        "error": "idempotency_conflict",
        "message": "This idempotency_key was already used with a different payload.",
        "idempotency": {"key": key, "replayed": False},
    }
    if upload_id:
        payload["upload_id"] = upload_id
    return JSONResponse(status_code=409, content=payload)


def _maybe_replay_idempotent_upload(*, db_path: Path, key: str | None, signature: str | None) -> JSONResponse | None:
    idempotency_key = str(key or "").strip()
    payload_signature = str(signature or "").strip()
    if not idempotency_key or not payload_signature:
        return None

    now_iso = _bulk_utc_now_iso()
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "DELETE FROM intake_upload_idempotency WHERE expires_at <= ?",
            (now_iso,),
        )
        row = connection.execute(
            """
            SELECT payload_signature, upload_id, response_json
            FROM intake_upload_idempotency
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        connection.commit()
    finally:
        connection.close()

    if row is None:
        return None

    existing_upload_id = str(row["upload_id"] or "").strip() or None
    if str(row["payload_signature"] or "") != payload_signature:
        return _idempotency_conflict_response(key=idempotency_key, upload_id=existing_upload_id)

    try:
        payload = json.loads(str(row["response_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if existing_upload_id and not payload.get("upload_id"):
        payload["upload_id"] = existing_upload_id
    return JSONResponse(content=_response_with_idempotency(payload, key=idempotency_key, replayed=True))


def _store_idempotent_upload_response(
    *,
    db_path: Path,
    key: str | None,
    signature: str | None,
    upload_id: str,
    response_payload: dict[str, Any],
) -> None:
    idempotency_key = str(key or "").strip()
    payload_signature = str(signature or "").strip()
    if not idempotency_key or not payload_signature:
        return

    now_iso = _bulk_utc_now_iso()
    connection = connect(db_path)
    try:
        connection.execute(
            "DELETE FROM intake_upload_idempotency WHERE expires_at <= ?",
            (now_iso,),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO intake_upload_idempotency (
                idempotency_key, payload_signature, upload_id, response_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                idempotency_key,
                payload_signature,
                upload_id,
                _stable_json_dumps(response_payload),
                now_iso,
                _idempotency_expires_at(now_iso),
            ),
        )
        connection.commit()
    finally:
        connection.close()


class IntakeSourceValidationError(ValueError):
    def __init__(self, *, error: str, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.detail = detail


def _validate_intake_source_entries(source_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source_entries, list) or len(source_entries) == 0:
        raise IntakeSourceValidationError(
            error="invalid_payload",
            message="source_entries must be a non-empty list of {type, path, recurse?, excluded_items?}",
        )

    validated_entries: list[dict[str, Any]] = []
    for entry in source_entries:
        if not isinstance(entry, dict):
            raise IntakeSourceValidationError(
                error="invalid_source_entry",
                message="Each source_entry must be an object",
            )

        entry_type = str(entry.get("type") or "").strip().lower()
        entry_path = str(entry.get("path") or "").strip()
        excluded_items = entry.get("excluded_items") or []
        
        # Validate excluded_items format
        if not isinstance(excluded_items, list):
            raise IntakeSourceValidationError(
                error="invalid_excluded_items",
                message="source_entry.excluded_items must be a list of strings",
            )
        for item in excluded_items:
            if not isinstance(item, str):
                raise IntakeSourceValidationError(
                    error="invalid_excluded_items",
                    message="Each item in excluded_items must be a string",
                )
        
        if entry_type not in {"file", "folder"}:
            raise IntakeSourceValidationError(
                error="invalid_source_type",
                message=f"source_entry.type must be 'file' or 'folder', got '{entry_type}'",
            )
        if not entry_path:
            raise IntakeSourceValidationError(
                error="invalid_source_path",
                message="source_entry.path is required",
            )

        resolved_path = Path(entry_path).expanduser().resolve()
        if not resolved_path.exists():
            raise IntakeSourceValidationError(
                error="source_not_found",
                message=f"source_entry.path does not exist: {entry_path}",
            )
        if entry_type == "file" and not resolved_path.is_file():
            raise IntakeSourceValidationError(
                error="source_is_not_file",
                message=f"source_entry marked as 'file' but path is not a file: {entry_path}",
            )
        if entry_type == "folder" and not resolved_path.is_dir():
            raise IntakeSourceValidationError(
                error="source_is_not_folder",
                message=f"source_entry marked as 'folder' but path is not a directory: {entry_path}",
            )
        if entry_type == "file" and resolved_path.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
            raise IntakeSourceValidationError(
                error="unsupported_file_type",
                message=f"Unsupported file type for intake: {resolved_path.name}",
            )

        try:
            stat_result = resolved_path.stat()
            
            browser_mtime_ms = entry.get("file_last_modified_ms")
            if browser_mtime_ms is not None and isinstance(browser_mtime_ms, (int, float)):
                entry_source_metadata = {
                    "source_mtime": _bulk_timestamp_iso(float(browser_mtime_ms) / 1000.0),
                    "source_ctime": _bulk_timestamp_iso(stat_result.st_ctime),
                }
                birthtime = getattr(stat_result, "st_birthtime", None)
                if birthtime is not None:
                    entry_source_metadata["source_birthtime"] = _bulk_timestamp_iso(birthtime)
            else:
                from .._helpers import _bulk_path_source_metadata
                entry_source_metadata = _bulk_path_source_metadata(resolved_path, stat_result)
        except (OSError, PermissionError) as error:
            raise IntakeSourceValidationError(
                error="source_stat_error",
                message=f"source_entry.path metadata could not be read: {entry_path}",
                detail=str(error),
            ) from error

        validated_entry = {
            "type": entry_type,
            "path": str(resolved_path),
            "recurse": _coerce_bool(entry.get("recurse", True)) if entry_type == "folder" else False,
            "excluded_items": excluded_items,  # NEW: Include excluded_items in validated entry
            "source_mtime": entry_source_metadata["source_mtime"],
            "source_ctime": entry_source_metadata["source_ctime"],
            "source_birthtime": entry_source_metadata.get("source_birthtime"),
            "source_size_bytes": int(stat_result.st_size) if entry_type == "file" else None,
        }
        for extra_key in (
            "source_type",
            "source_record_id",
            "original_filename",
            "relative_path",
            "upload_id",
            "grouping_strategy",
            "preserve_folder_structure",
            "group_title_source",
            "group_title",
        ):
            extra_value = entry.get(extra_key)
            if extra_value not in {None, ""}:
                validated_entry[extra_key] = extra_value
        validated_entries.append(validated_entry)

    return validated_entries


def _create_intake_queue_upload_record(
    *,
    db_path: Path,
    validated_entries: list[dict[str, Any]],
    cleanup_policy: str,
    telemetry: dict[str, Any] | None = None,
) -> tuple[str, str]:
    upload_id = str(uuid.uuid4())
    now_iso = _bulk_utc_now_iso()
    normalized_telemetry = _normalize_upload_telemetry(telemetry)

    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at, transport_mode,
                payload_bytes_raw, payload_bytes_encoded, upload_duration_ms,
                staging_write_duration_ms, warnings_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                "queued",
                json.dumps(validated_entries),
                "unverified",
                cleanup_policy,
                now_iso,
                now_iso,
                normalized_telemetry.get("transport_mode") if normalized_telemetry else None,
                normalized_telemetry.get("payload_bytes_raw") if normalized_telemetry else None,
                normalized_telemetry.get("payload_bytes_encoded") if normalized_telemetry else None,
                normalized_telemetry.get("upload_duration_ms") if normalized_telemetry else None,
                normalized_telemetry.get("staging_write_duration_ms") if normalized_telemetry else None,
                normalized_telemetry.get("warnings_count") if normalized_telemetry else None,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return upload_id, now_iso


def _transition_queue_status(
    db_path: Path,
    upload_id: str,
    new_status: str,
    event_type: str = "status_change",
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Transition an intake queue upload to a new status with audit logging.
    
    Returns (success: bool, error_message: str | None)
    """
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id, status, upload_id FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not row:
            return False, f"Upload not found: {upload_id}"
        
        current_status = row["status"]
        
        if new_status not in VALID_STATUS_TRANSITIONS.get(current_status, set()):
            return False, f"Invalid transition from {current_status} to {new_status}"
        
        now_iso = _bulk_utc_now_iso()
        timestamp_field = None
        if new_status == "uploading":
            timestamp_field = "uploaded_at"
        elif new_status == "verified":
            timestamp_field = "verified_at"
        elif new_status in ("cleanup_done", "cleanup_failed"):
            timestamp_field = "cleanup_done_at"
        
        update_clause = "status = ?, updated_at = ?"
        params: list[Any] = [new_status, now_iso]
        
        if timestamp_field:
            update_clause += f", {timestamp_field} = ?"
            params.append(now_iso)

        if new_status == "verified":
            update_clause += ", verification_status = ?"
            params.append("pass")
        
        if error_message and new_status == "failed":
            error_payload = {"error": error_message}
            update_clause += ", error_json = ?"
            params.append(json.dumps(error_payload))
        
        params.append(upload_id)
        
        connection.execute(
            f"UPDATE intake_queue_uploads SET {update_clause} WHERE upload_id = ?",
            params,
        )
        
        event_payload = {
            "upload_id": upload_id,
            "from_status": current_status,
            "to_status": new_status,
            "transition_at": now_iso,
        }
        if error_message:
            event_payload["error"] = error_message
        if metadata:
            event_payload["metadata"] = metadata
        
        connection.execute(
            """
            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                "intake_queue_upload",
                upload_id,
                json.dumps(event_payload),
                now_iso,
            ),
        )
        
        connection.commit()
        return True, None
        
    except Exception as e:
        return False, f"State transition error: {str(e)}"
    finally:
        connection.close()


def _expand_source_entries_to_files(source_entries: list[dict[str, Any]]) -> list[Path]:
    files: list[Path] = []
    exclusion_exact_keys, exclusion_folder_prefixes = _compile_source_entry_exclusions(source_entries)
    for entry in source_entries:
        entry_type = str(entry.get("type") or "").strip().lower()
        resolved = Path(str(entry.get("path") or "").strip()).expanduser().resolve()
        if entry_type == "file":
            if (
                resolved.exists()
                and resolved.is_file()
                and not _is_excluded_source_file(
                    file_path=resolved,
                    exclusion_exact_keys=exclusion_exact_keys,
                    exclusion_folder_prefixes=exclusion_folder_prefixes,
                )
            ):
                files.append(resolved)
            continue
        if entry_type != "folder" or not resolved.exists() or not resolved.is_dir():
            continue
        recurse = _coerce_bool(entry.get("recurse", True))
        for folder_file in _collect_intake_source_files_in_folder(resolved, recurse=recurse):
            if _is_excluded_source_file(
                file_path=folder_file,
                exclusion_exact_keys=exclusion_exact_keys,
                exclusion_folder_prefixes=exclusion_folder_prefixes,
            ):
                continue
            files.append(folder_file)
    return files


def _record_queue_event(*, request: Request, upload_id: str, event_type: str, payload: dict[str, Any]) -> None:
    connection = connect(request.app.state.model_catalog.settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                "intake_queue_upload",
                upload_id,
                json.dumps(payload),
                _bulk_utc_now_iso(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


# ==================== ENDPOINTS ====================

@router.post("/api/intake/uploads")
def intake_queue_post_upload(request: Request, payload: dict[str, Any]) -> Any:
    """
    Add a new upload to the intake queue.
    
    Source contract supports:
    - explicit file uploads: { type: "file", path: "/path/to/file.3mf" }
    - folder entries: { type: "folder", path: "/path/to/folder", recurse: true }
    - mixed batches: array of above mixed together
    
    Returns upload_id for tracking, plus queue status lifecycle.
    """
    state: AppState = request.app.state.model_catalog
    request_started = time.perf_counter()
    
    source_entries = payload.get("source_entries") or []
    cleanup_policy = _normalize_intake_cleanup_policy(payload.get("cleanup_policy"))
    idempotency_key = str(payload.get("idempotency_key") or "").strip() or None

    # Strict allowlist enforcement: server-mode source entries must resolve
    # within the intake roots configured for the active DB profile (prod/test).
    # Browser-staged entries are exempt (they live in sidecar staging).
    rejection_message = _enforce_source_entries_within_intake_roots(
        state.settings,
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

    try:
        validated_entries = _validate_intake_source_entries(source_entries)
    except IntakeSourceValidationError as error:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": error.error,
                "message": error.message,
                **({"detail": error.detail} if error.detail else {}),
            },
        )

    # NEW: Consolidate overlapping selections
    from ..services.intake_consolidation import _consolidate_overlapping_selections
    consolidated_entries = _consolidate_overlapping_selections(validated_entries)
    
    request_signature = _payload_signature(
        {
            "route": "intake_queue_post_upload",
            "cleanup_policy": cleanup_policy,
            "source_entries": consolidated_entries,
        }
    )
    replay_response = _maybe_replay_idempotent_upload(
        db_path=state.settings.db_path,
        key=idempotency_key,
        signature=request_signature,
    )
    if replay_response is not None:
        return replay_response

    expanded_entries, archive_warnings = _expand_server_archive_source_entries(
        state.settings,
        consolidated_entries,
    )

    upload_id, now_iso = _create_intake_queue_upload_record(
        db_path=state.settings.db_path,
        validated_entries=expanded_entries,
        cleanup_policy=cleanup_policy,
        telemetry={
            "warnings_count": len(archive_warnings),
            "upload_duration_ms": _duration_ms(request_started),
        },
    )

    response_payload = {
        "success": True,
        "upload_id": upload_id,
        "status": "queued",
        "verification_status": "unverified",
        "cleanup_policy": cleanup_policy,
        "source_entry_count": len(expanded_entries),
        "warnings": archive_warnings,
        "created_at": now_iso,
    }
    response_payload = _response_with_idempotency(response_payload, key=idempotency_key, replayed=False)
    _store_idempotent_upload_response(
        db_path=state.settings.db_path,
        key=idempotency_key,
        signature=request_signature,
        upload_id=upload_id,
        response_payload=response_payload,
    )

    return response_payload




@router.post(
    "/api/intake/uploads/v2/browser-multipart",
    summary="Create intake upload from multipart browser files",
    description=(
        "Stages browser-uploaded files from multipart form-data and creates a standard intake queue "
        "upload without using the v1 base64 transport. The multipart manifest preserves relative paths, "
        "grouping hints, and optional server selections while reusing the existing queue semantics."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["manifest"],
                        "properties": {
                            "manifest": {
                                "type": "string",
                                "description": "JSON manifest describing cleanup policy, optional server selections, and per-file metadata.",
                                "example": json.dumps(
                                    {
                                        "cleanup_policy": "delete_on_verified",
                                        "grouping_strategy": "by-folder",
                                        "preserve_folder_structure": True,
                                        "browser_files": [
                                            {
                                                "filename": "widget.3mf",
                                                "relative_path": "Batch A/widget.3mf",
                                            },
                                            {
                                                "filename": "preview.jpg",
                                                "relative_path": "Batch A/preview.jpg",
                                            },
                                        ],
                                    }
                                ),
                            },
                            "files[]": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary",
                                },
                                "description": "Repeated multipart file parts, one for each uploaded file.",
                            },
                        },
                    },
                    "examples": {
                        "nested-batch": {
                            "summary": "Nested browser upload with per-file relative paths",
                            "value": {
                                "manifest": json.dumps(
                                    {
                                        "cleanup_policy": "delete_on_verified",
                                        "grouping_strategy": "by-folder",
                                        "preserve_folder_structure": True,
                                        "browser_files": [
                                            {
                                                "filename": "base.3mf",
                                                "relative_path": "TopA/base.3mf",
                                            },
                                            {
                                                "filename": "tall.3mf",
                                                "relative_path": "TopA/variants/tall.3mf",
                                            },
                                        ],
                                    }
                                ),
                                "files[]": ["<binary>", "<binary>"],
                            },
                        }
                    },
                }
            },
        }
    },
)
async def intake_queue_post_browser_upload_v2(request: Request) -> Any:
    state: AppState = request.app.state.model_catalog
    request_started = time.perf_counter()

    try:
        form = await request.form()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Multipart upload must be valid form-data.",
            },
        )

    manifest_raw = form.get("manifest")
    if manifest_raw is None or isinstance(manifest_raw, UploadFile):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_manifest",
                "message": "Multipart upload requires a JSON manifest form field.",
            },
        )

    try:
        payload = json.loads(str(manifest_raw))
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_manifest",
                "message": "Multipart upload manifest must be valid JSON.",
            },
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_manifest",
                "message": "Multipart upload manifest must be a JSON object.",
            },
        )

    browser_files_meta = payload.get("browser_files")
    if browser_files_meta is None:
        browser_files_meta = payload.get("files_meta") or []
    if browser_files_meta and not isinstance(browser_files_meta, list):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_manifest",
                "message": "browser_files or files_meta must be a list when provided.",
            },
        )

    parsed_selections = payload.get("server_selections") or []
    if parsed_selections and not isinstance(parsed_selections, list):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_server_selections",
                "message": "server_selections must be a list.",
            },
        )

    cleanup_policy = _normalize_browser_intake_cleanup_policy(payload.get("cleanup_policy"))
    idempotency_key = str(payload.get("idempotency_key") or "").strip() or None
    warnings: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = [entry for entry in parsed_selections if isinstance(entry, dict)]
    idempotency_browser_files: list[dict[str, Any]] = []
    payload_bytes_raw = 0
    staging_write_duration_ms = 0

    upload_files: list[UploadFile] = []
    seen_upload_ids: set[int] = set()
    for field_name in ("files[]", "files"):
        for item in form.getlist(field_name):
            if not isinstance(item, UploadFile):
                continue
            marker = id(item)
            if marker in seen_upload_ids:
                continue
            seen_upload_ids.add(marker)
            upload_files.append(item)

    if browser_files_meta and len(browser_files_meta) != len(upload_files):
        for upload in upload_files:
            await upload.close()
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_manifest_file_mapping",
                "message": "browser_files/files_meta must include exactly one entry per uploaded multipart file.",
            },
        )

    if not upload_files and not source_entries:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_browser_files",
                "message": "Select at least one browser file or server selection before submitting.",
            },
        )

    staged_upload_id = str(uuid.uuid4()) if upload_files else None
    staged_root = (_browser_intake_upload_storage_root(state.settings) / staged_upload_id) if staged_upload_id else None
    if staged_root is not None:
        staged_root.mkdir(parents=True, exist_ok=True)

    default_grouping_strategy = str(payload.get("grouping_strategy") or "").strip() or None
    default_group_title_source = payload.get("group_title_source")
    default_group_title = payload.get("group_title")
    default_preserve_folder_structure = payload.get("preserve_folder_structure")

    try:
        for index, upload in enumerate(upload_files):
            file_meta = browser_files_meta[index] if browser_files_meta else {}
            if file_meta and not isinstance(file_meta, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_manifest_file_mapping",
                        "message": "Each browser_files/files_meta entry must be an object.",
                    },
                )

            filename = Path(str((file_meta or {}).get("filename") or upload.filename or "")).name or f"upload-{index + 1}.bin"
            relative_path = _sanitize_browser_upload_relative_path(
                str((file_meta or {}).get("relative_path") or upload.filename or filename),
                filename,
            )
            if relative_path.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
                warnings.append(
                    {
                        "code": "unsupported_file_type",
                        "message": f"Skipped unsupported browser upload: {filename}",
                        "filename": filename,
                    }
                )
                continue

            assert staged_root is not None
            destination = (staged_root / relative_path).resolve()
            if not destination.is_relative_to(staged_root.resolve()):
                warnings.append(
                    {
                        "code": "invalid_relative_path",
                        "message": f"Skipped browser upload with unsafe path: {filename}",
                        "filename": filename,
                    }
                )
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            bytes_written = 0
            content_hasher = hashlib.sha256()
            with destination.open("wb") as handle:
                file_write_started = time.perf_counter()
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    content_hasher.update(chunk)
                    bytes_written += len(chunk)
                staging_write_duration_ms += _duration_ms(file_write_started)

            if bytes_written <= 0:
                destination.unlink(missing_ok=True)
                warnings.append(
                    {
                        "code": "empty_upload",
                        "message": f"Skipped empty browser upload: {filename}",
                        "filename": filename,
                    }
                )
                continue

            grouping_strategy = str((file_meta or {}).get("grouping_strategy") or default_grouping_strategy or "").strip() or None
            preserve_folder_structure = (file_meta or {}).get("preserve_folder_structure")
            if preserve_folder_structure is None:
                preserve_folder_structure = default_preserve_folder_structure

            source_entries.append(
                {
                    "type": "file",
                    "path": str(destination),
                    "source_type": "browser_upload",
                    "original_filename": filename,
                    "relative_path": str(relative_path).replace("\\", "/"),
                    "upload_id": staged_upload_id,
                    "file_last_modified_ms": (file_meta or {}).get("file_last_modified_ms"),
                    "grouping_strategy": grouping_strategy,
                    "preserve_folder_structure": preserve_folder_structure,
                    "group_title_source": (file_meta or {}).get("group_title_source", default_group_title_source),
                    "group_title": (file_meta or {}).get("group_title", default_group_title),
                }
            )
            idempotency_browser_files.append(
                {
                    "filename": filename,
                    "upload_filename": str(upload.filename or "").strip() or filename,
                    "relative_path": str(relative_path).replace("\\", "/"),
                    "content_sha256": content_hasher.hexdigest(),
                    "size_bytes": bytes_written,
                    "file_last_modified_ms": (file_meta or {}).get("file_last_modified_ms"),
                    "grouping_strategy": grouping_strategy,
                    "preserve_folder_structure": preserve_folder_structure,
                    "group_title_source": (file_meta or {}).get("group_title_source", default_group_title_source),
                    "group_title": (file_meta or {}).get("group_title", default_group_title),
                }
            )
            payload_bytes_raw += bytes_written
    finally:
        for upload in upload_files:
            await upload.close()

    if not source_entries:
        if staged_root is not None:
            shutil.rmtree(staged_root, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_supported_sources",
                "message": "No supported intake sources remained after browser upload filtering.",
                "warnings": warnings,
            },
        )

    try:
        validated_entries = _validate_intake_source_entries(source_entries)
    except IntakeSourceValidationError as error:
        if staged_root is not None:
            shutil.rmtree(staged_root, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": error.error,
                "message": error.message,
                **({"detail": error.detail} if error.detail else {}),
                "warnings": warnings,
            },
        )

    request_signature = _payload_signature(
        {
            "route": "intake_queue_post_browser_upload_v2",
            "cleanup_policy": cleanup_policy,
            "server_selections": _normalize_server_selection_signature([entry for entry in parsed_selections if isinstance(entry, dict)]),
            "browser_files": idempotency_browser_files,
        }
    )
    replay_response = _maybe_replay_idempotent_upload(
        db_path=state.settings.db_path,
        key=idempotency_key,
        signature=request_signature,
    )
    if replay_response is not None:
        if staged_root is not None:
            shutil.rmtree(staged_root, ignore_errors=True)
        return replay_response

    validated_entries, archive_warnings = _expand_server_archive_source_entries(
        state.settings,
        validated_entries,
    )
    if archive_warnings:
        warnings.extend(archive_warnings)

    upload_id, now_iso = _create_intake_queue_upload_record(
        db_path=state.settings.db_path,
        validated_entries=validated_entries,
        cleanup_policy=cleanup_policy,
        telemetry={
            "transport_mode": "v2_multipart",
            "payload_bytes_raw": payload_bytes_raw,
            "upload_duration_ms": _duration_ms(request_started),
            "staging_write_duration_ms": staging_write_duration_ms,
            "warnings_count": len(warnings),
        },
    )

    response_payload = {
        "success": True,
        "contract": "intake-upload-v2-multipart",
        "upload_id": upload_id,
        "status": "queued",
        "verification_status": "unverified",
        "cleanup_policy": cleanup_policy,
        "source_entry_count": len(validated_entries),
        "browser_file_count": len([entry for entry in validated_entries if entry.get("source_type") == "browser_upload"]),
        "warnings": warnings,
        "created_at": now_iso,
    }
    response_payload = _response_with_idempotency(response_payload, key=idempotency_key, replayed=False)
    _store_idempotent_upload_response(
        db_path=state.settings.db_path,
        key=idempotency_key,
        signature=request_signature,
        upload_id=upload_id,
        response_payload=response_payload,
    )

    return response_payload


@router.post("/api/intake/uploads/browser")
async def intake_queue_post_browser_upload(request: Request) -> Any:
    state: AppState = request.app.state.model_catalog
    request_started = time.perf_counter()
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Browser upload payload must be valid JSON.",
            },
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Browser upload payload must be a JSON object.",
            },
        )

    browser_files = payload.get("browser_files") or []
    cleanup_policy = _normalize_browser_intake_cleanup_policy(payload.get("cleanup_policy"))
    idempotency_key = str(payload.get("idempotency_key") or "").strip() or None
    warnings: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []
    idempotency_browser_files: list[dict[str, Any]] = []
    payload_bytes_raw = 0
    payload_bytes_encoded = 0
    staging_write_duration_ms = 0

    parsed_selections = payload.get("server_selections") or []
    if parsed_selections and not isinstance(parsed_selections, list):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_server_selections",
                "message": "server_selections must be a list.",
            },
        )
    source_entries.extend([entry for entry in parsed_selections if isinstance(entry, dict)])

    if not browser_files and not source_entries:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_browser_files",
                "message": "Select at least one browser file or server selection before submitting.",
            },
        )

    staged_upload_id = str(uuid.uuid4())
    staged_root = _browser_intake_upload_storage_root(state.settings) / staged_upload_id
    staged_root.mkdir(parents=True, exist_ok=True)

    for index, upload in enumerate(browser_files):
        if not isinstance(upload, dict):
            warnings.append(
                {
                    "code": "invalid_browser_file",
                    "message": "Skipped malformed browser upload entry.",
                }
            )
            continue

        filename = Path(str(upload.get("filename") or "")).name or f"upload-{index + 1}.bin"
        relative_path = _sanitize_browser_upload_relative_path(
            str(upload.get("relative_path") or ""),
            filename,
        )
        if relative_path.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
            warnings.append(
                {
                    "code": "unsupported_file_type",
                    "message": f"Skipped unsupported browser upload: {filename}",
                    "filename": filename,
                }
            )
            continue

        destination = (staged_root / relative_path).resolve()
        if not destination.is_relative_to(staged_root.resolve()):
            warnings.append(
                {
                    "code": "invalid_relative_path",
                    "message": f"Skipped browser upload with unsafe path: {filename}",
                    "filename": filename,
                }
            )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded_content = str(upload.get("content_base64") or "").strip()
        if not encoded_content:
            warnings.append(
                {
                    "code": "empty_upload",
                    "message": f"Skipped empty browser upload: {filename}",
                    "filename": filename,
                }
            )
            continue

        try:
            file_bytes = base64.b64decode(encoded_content, validate=True)
        except (binascii.Error, ValueError):
            warnings.append(
                {
                    "code": "invalid_base64",
                    "message": f"Skipped browser upload with invalid base64 content: {filename}",
                    "filename": filename,
                }
            )
            continue
        if not file_bytes:
            warnings.append(
                {
                    "code": "empty_upload",
                    "message": f"Skipped empty browser upload: {filename}",
                    "filename": filename,
                }
            )
            continue

        write_started = time.perf_counter()
        destination.write_bytes(file_bytes)
        staging_write_duration_ms += _duration_ms(write_started)
        payload_bytes_raw += len(file_bytes)
        payload_bytes_encoded += len(encoded_content.encode("utf-8"))
        idempotency_browser_files.append(
            {
                "filename": filename,
                "relative_path": str(relative_path).replace("\\", "/"),
                "content_sha256": _content_signature(file_bytes),
                "size_bytes": len(file_bytes),
                "file_last_modified_ms": upload.get("file_last_modified_ms"),
                "grouping_strategy": str(upload.get("grouping_strategy") or "").strip() or None,
                "preserve_folder_structure": upload.get("preserve_folder_structure"),
                "group_title_source": upload.get("group_title_source"),
                "group_title": upload.get("group_title"),
            }
        )
        source_entries.append(
            {
                "type": "file",
                "path": str(destination),
                "source_type": "browser_upload",
                "original_filename": filename,
                "relative_path": str(relative_path).replace("\\", "/"),
                "upload_id": staged_upload_id,
                "file_last_modified_ms": upload.get("file_last_modified_ms"),
                "grouping_strategy": str(upload.get("grouping_strategy") or "").strip() or None,
                "preserve_folder_structure": upload.get("preserve_folder_structure"),
                "group_title_source": upload.get("group_title_source"),
                "group_title": upload.get("group_title"),
            }
        )

    if not source_entries:
        shutil.rmtree(staged_root, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_supported_sources",
                "message": "No supported intake sources remained after browser upload filtering.",
                "warnings": warnings,
            },
        )

    try:
        validated_entries = _validate_intake_source_entries(source_entries)
    except IntakeSourceValidationError as error:
        shutil.rmtree(staged_root, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": error.error,
                "message": error.message,
                **({"detail": error.detail} if error.detail else {}),
                "warnings": warnings,
            },
        )

    request_signature = _payload_signature(
        {
            "route": "intake_queue_post_browser_upload",
            "cleanup_policy": cleanup_policy,
            "server_selections": _normalize_server_selection_signature([entry for entry in parsed_selections if isinstance(entry, dict)]),
            "browser_files": idempotency_browser_files,
        }
    )
    replay_response = _maybe_replay_idempotent_upload(
        db_path=state.settings.db_path,
        key=idempotency_key,
        signature=request_signature,
    )
    if replay_response is not None:
        shutil.rmtree(staged_root, ignore_errors=True)
        return replay_response

    validated_entries, archive_warnings = _expand_server_archive_source_entries(
        state.settings,
        validated_entries,
    )
    if archive_warnings:
        warnings.extend(archive_warnings)

    upload_id, now_iso = _create_intake_queue_upload_record(
        db_path=state.settings.db_path,
        validated_entries=validated_entries,
        cleanup_policy=cleanup_policy,
        telemetry={
            "transport_mode": "v1_base64",
            "payload_bytes_raw": payload_bytes_raw,
            "payload_bytes_encoded": payload_bytes_encoded,
            "upload_duration_ms": _duration_ms(request_started),
            "staging_write_duration_ms": staging_write_duration_ms,
            "warnings_count": len(warnings),
        },
    )

    response_payload = {
        "success": True,
        "upload_id": upload_id,
        "status": "queued",
        "verification_status": "unverified",
        "cleanup_policy": cleanup_policy,
        "source_entry_count": len(validated_entries),
        "browser_file_count": len([entry for entry in validated_entries if entry.get("source_type") == "browser_upload"]),
        "warnings": warnings,
        "created_at": now_iso,
    }
    response_payload = _response_with_idempotency(response_payload, key=idempotency_key, replayed=False)
    _store_idempotent_upload_response(
        db_path=state.settings.db_path,
        key=idempotency_key,
        signature=request_signature,
        upload_id=upload_id,
        response_payload=response_payload,
    )

    return response_payload


@router.get("/api/intake/uploads")
def intake_queue_get_uploads(request: Request, status: str | None = None, limit: int | None = None) -> Any:
    """
    List intake queue uploads with optional status filter.
    
    Status values: queued, uploading, uploaded_unverified, verified, 
                   cleanup_pending, cleanup_done, cleanup_failed, failed
    """
    state: AppState = request.app.state.model_catalog
    
    limit_int = min(int(limit or 50), 1000)
    status_filter = str(status or "").strip().lower() if status else None
    valid_statuses = {
        "queued", "uploading", "uploaded_unverified", "verified",
        "cleanup_pending", "cleanup_done", "cleanup_failed", "failed"
    }
    if status_filter and status_filter not in valid_statuses:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_status",
                "message": f"status must be one of: {', '.join(sorted(valid_statuses))}",
            },
        )
    
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        if status_filter:
            rows = connection.execute(
                """
                SELECT id, upload_id, status, verification_status, cleanup_policy,
                      created_at, updated_at, uploaded_at, verified_at, cleanup_done_at,
                      transport_mode, payload_bytes_raw, payload_bytes_encoded,
                      upload_duration_ms, staging_write_duration_ms, warnings_count,
                       (SELECT COUNT(*) FROM json_each(source_entries_json)) as source_entry_count,
                       (SELECT COUNT(*) FROM json_each(file_hashes_json)) as file_count
                FROM intake_queue_uploads
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status_filter, limit_int),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, upload_id, status, verification_status, cleanup_policy,
                      created_at, updated_at, uploaded_at, verified_at, cleanup_done_at,
                      transport_mode, payload_bytes_raw, payload_bytes_encoded,
                      upload_duration_ms, staging_write_duration_ms, warnings_count,
                       (SELECT COUNT(*) FROM json_each(source_entries_json)) as source_entry_count,
                       (SELECT COUNT(*) FROM json_each(file_hashes_json)) as file_count
                FROM intake_queue_uploads
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit_int,),
            ).fetchall()
        
        uploads = []
        for row in rows:
            uploads.append({
                "id": row["id"],
                "upload_id": row["upload_id"],
                "status": row["status"],
                "verification_status": row["verification_status"],
                "cleanup_policy": row["cleanup_policy"],
                "source_entry_count": row["source_entry_count"],
                "file_count": row["file_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "uploaded_at": row["uploaded_at"],
                "verified_at": row["verified_at"],
                "cleanup_done_at": row["cleanup_done_at"],
                "upload_telemetry": _normalize_upload_telemetry(
                    {
                        "transport_mode": row["transport_mode"],
                        "payload_bytes_raw": row["payload_bytes_raw"],
                        "payload_bytes_encoded": row["payload_bytes_encoded"],
                        "upload_duration_ms": row["upload_duration_ms"],
                        "staging_write_duration_ms": row["staging_write_duration_ms"],
                        "warnings_count": row["warnings_count"],
                    }
                ),
            })
    finally:
        connection.close()
    
    return {
        "success": True,
        "status_filter": status_filter,
        "upload_count": len(uploads),
        "uploads": uploads,
    }


@router.delete("/api/intake/uploads/{upload_id}")
def intake_queue_delete_upload(request: Request, upload_id: str) -> Any:
    """
    Delete an upload from the intake queue.
    
    Only allows deletion of queued uploads (not uploading/verified).
    """
    state: AppState = request.app.state.model_catalog
    
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id, status, source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not row:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "upload_not_found",
                    "message": f"No upload found with id: {upload_id}",
                },
            )
        
        current_status = row["status"]
        deletable_statuses = {"queued", "failed", "submitted", "validated_ready", "validated_warning", "deferred"}
        if current_status not in deletable_statuses:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "cannot_delete_status",
                    "message": f"Cannot delete upload with status '{current_status}'. Only non-terminal uploads can be deleted.",
                },
            )
        
        connection.execute(
            "DELETE FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        )
        connection.commit()
    finally:
        connection.close()

    source_entries = json.loads(str(row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list):
        source_entries = []
    for stage_dir in _browser_upload_stage_directories(state.settings, source_entries):
        shutil.rmtree(stage_dir, ignore_errors=True)
    for stage_dir in _makerworld_stage_directories(state.settings, source_entries):
        shutil.rmtree(stage_dir, ignore_errors=True)
    
    return {
        "success": True,
        "upload_id": upload_id,
        "deleted": True,
    }


@router.put("/api/intake/uploads/{upload_id}/status")
def intake_queue_update_status(request: Request, upload_id: str, payload: dict[str, Any]) -> Any:
    """
    Update the status of an intake queue upload.
    
    Transitions through the state machine with audit logging:
    - queued → uploading
    - uploading → uploaded_unverified
    - uploaded_unverified → verified
    - verified → cleanup_pending
    - cleanup_pending → cleanup_done or cleanup_failed
    - (any) → failed (on error)
    
    Payload: { "status": "new_status", "error": "optional error message" }
    """
    state: AppState = request.app.state.model_catalog
    
    new_status = str(payload.get("status") or "").strip().lower()
    error_message = str(payload.get("error") or "").strip() or None
    metadata = payload.get("metadata")
    
    if not new_status:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_status",
                "message": "Payload must include 'status' field",
            },
        )
    
    valid_statuses = {
        "queued", "uploading", "uploaded_unverified", "verified",
        "cleanup_pending", "cleanup_done", "cleanup_failed", "failed"
    }
    if new_status not in valid_statuses:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_status",
                "message": f"status must be one of: {', '.join(sorted(valid_statuses))}",
            },
        )
    
    success, error = _transition_queue_status(
        db_path=state.settings.db_path,
        upload_id=upload_id,
        new_status=new_status,
        event_type="manual_status_transition",
        error_message=error_message,
        metadata=metadata,
    )
    
    if not success:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": error,
            },
        )
    
    return {
        "success": True,
        "upload_id": upload_id,
        "new_status": new_status,
        "updated_at": _bulk_utc_now_iso(),
    }


@router.get("/api/intake/browse")
def intake_browse_folder(request: Request, path: str | None = None) -> Any:
    """
    Browse server filesystem for file/folder selection with allowlist validation.
    
    Returns folder structure for UI-based source selection. Respects:
    - Allowlist paths from settings (BAMBULAB_INTAKE_ALLOWLIST env var)
    - Returns file/folder metadata for UI tree rendering
    """
    state: AppState = request.app.state.model_catalog

    allowlist_paths = _intake_browse_allowlist_roots(state.settings)
    
    browse_path = None
    archive_path: Path | None = None
    archive_inner_path = ""
    archive_virtual_mode = False
    if not path or path.strip() == "/":
        return {
            "success": True,
            "path": "/",
            "is_root": True,
            "type": "virtual_root",
            "entries": [
                {
                    "path": str(allowed_root),
                    "name": allowed_root.name or str(allowed_root),
                    "type": "folder",
                    "accessible": allowed_root.exists(),
                    "has_children": allowed_root.is_dir() if allowed_root.exists() else False,
                }
                for allowed_root in allowlist_paths
            ],
        }
    else:
        raw_path = str(path).strip()
        if "::" in raw_path:
            archive_raw, inner_raw = raw_path.split("::", 1)
            archive_path = Path(archive_raw).expanduser().resolve()
            browse_path = archive_path
            archive_inner_path = str(inner_raw or "").replace("\\", "/").strip("/")
            archive_virtual_mode = True
        else:
            browse_path = Path(raw_path).expanduser().resolve()
            if browse_path.suffix.lower() == ".zip":
                archive_path = browse_path
                archive_inner_path = ""
                archive_virtual_mode = True
    
    if browse_path is not None:
        is_allowed = any(
            browse_path == allowed or browse_path.is_relative_to(allowed)
            for allowed in allowlist_paths
        )
        if not is_allowed:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "path_not_allowed",
                    "message": f"Path '{path}' is not in allowlist. Allowed: {', '.join(str(p) for p in allowlist_paths)}",
                },
            )
    
    if browse_path is None or not browse_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": f"Path does not exist: {path}",
            },
        )
    
    if archive_virtual_mode:
        if archive_path is None or not archive_path.exists() or not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "not_a_directory",
                    "message": f"Path is not a directory: {path}",
                },
            )

        entries: list[dict[str, Any]] = []
        folder_names: set[str] = set()
        file_entries: dict[str, dict[str, Any]] = {}
        prefix = archive_inner_path + "/" if archive_inner_path else ""

        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    normalized = str(info.filename or "").replace("\\", "/").lstrip("/")
                    if not normalized:
                        continue
                    if prefix and not normalized.startswith(prefix):
                        continue

                    relative = normalized[len(prefix):] if prefix else normalized
                    if not relative:
                        continue
                    parts = [part for part in relative.split("/") if part not in {"", ".", ".."}]
                    if not parts:
                        continue

                    if len(parts) > 1:
                        folder_names.add(parts[0])
                        continue

                    leaf_name = parts[0]
                    child_inner = f"{archive_inner_path}/{leaf_name}" if archive_inner_path else leaf_name
                    virtual_child_path = f"{archive_path}::{child_inner}"
                    file_entries[leaf_name] = {
                        "path": virtual_child_path,
                        "name": leaf_name,
                        "type": "file",
                        "size_bytes": int(info.file_size),
                        "has_children": False,
                        "extension": Path(leaf_name).suffix.lower(),
                        "virtual_archive": True,
                        "selectable": False,
                    }
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "archive_browse_failed",
                    "message": f"Could not browse archive: {archive_path.name}",
                    "detail": str(error),
                },
            )

        for folder_name in sorted(folder_names):
            child_inner = f"{archive_inner_path}/{folder_name}" if archive_inner_path else folder_name
            virtual_child_path = f"{archive_path}::{child_inner}"
            entries.append(
                {
                    "path": virtual_child_path,
                    "name": folder_name,
                    "type": "folder",
                    "size_bytes": None,
                    "has_children": True,
                    "virtual_archive": True,
                    "selectable": False,
                }
            )

        for file_name in sorted(file_entries.keys()):
            entries.append(file_entries[file_name])

        if archive_inner_path:
            parent_inner = archive_inner_path.rsplit("/", 1)[0] if "/" in archive_inner_path else ""
            parent_path = f"{archive_path}::{parent_inner}" if parent_inner else str(archive_path)
        else:
            parent_path = str(archive_path.parent)

        display_path = f"{archive_path}::{archive_inner_path}" if archive_inner_path else str(archive_path)
        return {
            "success": True,
            "path": display_path,
            "name": archive_path.name if not archive_inner_path else Path(archive_inner_path).name,
            "type": "folder",
            "parent_path": parent_path,
            "is_root": False,
            "entry_count": len(entries),
            "entries": entries,
            "virtual_archive": True,
            "archive_source_path": str(archive_path),
        }

    if not browse_path.is_dir():
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "not_a_directory",
                "message": f"Path is not a directory: {path}",
            },
        )
    
    entries = []
    
    try:
        for item in sorted(browse_path.iterdir()):
            if item.name.startswith("."):
                continue
            
            try:
                is_dir = item.is_dir()
                size_bytes = None
                if not is_dir:
                    try:
                        size_bytes = item.stat().st_size
                    except (OSError, PermissionError):
                        pass
                
                entry = {
                    "path": str(item),
                    "name": item.name,
                    "type": "folder" if is_dir else "file",
                    "size_bytes": size_bytes,
                    "has_children": is_dir,
                }
                
                if not is_dir:
                    entry["extension"] = item.suffix.lower()
                
                entries.append(entry)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError) as e:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "permission_denied",
                "message": f"Cannot access directory: {str(e)}",
            },
        )
    
    parent_path = None
    if browse_path != browse_path.parent:
        parent_candidate = browse_path.parent
        is_parent_allowed = any(
            parent_candidate == allowed or parent_candidate.is_relative_to(allowed)
            for allowed in allowlist_paths
        )
        if is_parent_allowed:
            parent_path = str(parent_candidate)
    
    return {
        "success": True,
        "path": str(browse_path),
        "name": browse_path.name or str(browse_path),
        "type": "folder",
        "parent_path": parent_path,
        "is_root": False,
        "entry_count": len(entries),
        "entries": entries,
    }


@router.get("/api/intake/preview")
def intake_preview_file(request: Request, path: str | None = None) -> Any:
    """Return a preview image for allowlisted intake source files."""
    state: AppState = request.app.state.model_catalog

    path_value = str(path or "").strip()
    if not path_value:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_path",
                "message": "Query parameter 'path' is required.",
            },
        )

    try:
        resolved_path = Path(path_value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_path",
                "message": "Could not resolve preview path.",
            },
        )

    allowlisted_roots = _intake_browse_allowlist_roots(state.settings)
    if not _is_path_within_roots(resolved_path, allowlisted_roots):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "path_not_allowed",
                "message": "Preview path is outside allowed intake roots.",
            },
        )

    if not resolved_path.exists() or not resolved_path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Preview file not found.",
            },
        )

    suffix = str(resolved_path.suffix or "").lower()

    if suffix in LOCAL_IMPORT_IMAGE_EXTENSIONS:
        file_size = resolved_path.stat().st_size
        if file_size > _INTAKE_PREVIEW_MAX_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": "preview_too_large",
                    "message": "Image preview exceeds max size (5 MB).",
                },
            )

        try:
            content = resolved_path.read_bytes()
        except (OSError, PermissionError):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "preview_read_failed",
                    "message": "Could not read preview file.",
                },
            )

        return Response(
            content=content,
            media_type=_image_mime_for_suffix(resolved_path),
            headers={"Cache-Control": "public, max-age=300"},
        )

    if suffix == ".3mf":
        from ..geometry_3mf import extract_3mf_thumbnail

        file_size = resolved_path.stat().st_size
        if file_size > _INTAKE_PREVIEW_MAX_3MF_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": "model_file_too_large",
                    "message": "3MF file exceeds max size for preview extraction.",
                },
            )

        try:
            thumbnail_bytes = extract_3mf_thumbnail(resolved_path.read_bytes())
        except (OSError, PermissionError):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "preview_read_failed",
                    "message": "Could not read model file for preview extraction.",
                },
            )

        if thumbnail_bytes is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "thumbnail_not_found",
                    "message": "No embedded thumbnail found in 3MF file.",
                },
            )

        mime_type = "image/png"
        if thumbnail_bytes[:3] == b"\xff\xd8\xff":
            mime_type = "image/jpeg"

        return Response(
            content=thumbnail_bytes,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=300"},
        )

    return JSONResponse(
        status_code=415,
        content={
            "success": False,
            "error": "preview_unsupported_type",
            "message": "Preview is supported for images and .3mf files only.",
        },
    )
