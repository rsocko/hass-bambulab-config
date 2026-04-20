from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from urllib.parse import quote

import voluptuous as vol
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .api import BambuddyApiClient, BambuddyRuntimeRepairClient
from .const import (
    ARCHIVE_VIEWER_GCODE_URL,
    DATA_MANAGER,
    DATA_RESTORE_UPLOADS,
    DATA_RESTORE_WORKFLOW,
    DEFAULT_RESTORE_UPLOAD_MAX_BYTES,
    DOMAIN,
    PLATFORMS,
    SERVICE_APPEND_PRINT_HISTORY_EVENT,
    CONF_RUNTIME_REPAIR_BASE_URL,
    CONF_RUNTIME_REPAIR_TOKEN,
    SERVICE_DELETE_PRINT_HISTORY_PHOTO,
    SERVICE_DELETE_PRINT_HISTORY_ARCHIVE,
    SERVICE_DISMISS_PRINT_HISTORY_MEDIA_REVIEW,
    CONF_FETCH_TIMEOUT_SECONDS,
    SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE,
    SERVICE_ESTIMATE_PARTIAL_USAGE,
    SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL,
    SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA,
    SERVICE_GET_PRINT_HISTORY_ARCHIVE_RESTORE_WORKFLOW,
    SERVICE_REPAIR_PRINT_HISTORY_ARCHIVE_FROM_START,
    SERVICE_QUERY_PRINT_HISTORY_BROWSER,
    SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_DETAIL,
    SERVICE_REFRESH_PRINT_HISTORY_BROWSER,
    SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE,
    SERVICE_CREATE_PRINT_HISTORY_ARCHIVE_REPLACEMENT_FROM_UPLOAD,
    SERVICE_PLAN_PRINT_HISTORY_ARCHIVE_RESTORE,
    SERVICE_APPLY_PRINT_HISTORY_ARCHIVE_RESTORE,
    SERVICE_VERIFY_PRINT_HISTORY_ARCHIVE_RESTORE,
    SERVICE_FINISH_PRINT_HISTORY_ARCHIVE_RESTORE,
    SERVICE_REMOVE_PRINT_HISTORY_RESTORED_SOURCE_ARCHIVE,
    SERVICE_CLEAR_PRINT_HISTORY_ARCHIVE_RESTORE,
    SERVICE_SET_PRINT_HISTORY_MEDIA_REVIEW_STATE,
    SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO,
    SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE,
    SERVICE_SET_PRINT_HISTORY_REVIEW_STATE,
    SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE,
    SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA,
    RESTORE_UPLOAD_DISCOVER_URL,
    SOURCE_3MF_UPLOAD_URL,
)
from .manager import PrintHistoryBrowserManager
from .print_history.query import (
    ENRICHMENT_MARKER,
    RECOVERY_AUDIT_MARKER,
    SYSTEM_TAG_PREFIXES,
    SYSTEM_TAG_VALUES,
    build_enrichment_notes,
    filter_note_payload_rows,
    note_payload_rows,
    project_archive,
    split_enrichment_notes,
    system_tags,
    user_tags,
)


CONF_ENTRY_ID = "entry_id"
CONF_ARCHIVE_ID = "archive_id"
CONF_SOURCE_ARCHIVE_ID = "source_archive_id"
CONF_TARGET_ARCHIVE_ID = "target_archive_id"
CONF_PRINTER_ID = "printer_id"
CONF_UPLOAD_SESSION_ID = "upload_session_id"
CONF_RELATED_ARCHIVE_ID = "related_archive_id"
CONF_RELATION_TYPE = "relation_type"
CONF_MODE = "mode"


_LOGGER = logging.getLogger(__name__)

ENRICHMENT_METADATA_MODES = ("ALL", "ANY_MISSING_DATA", "MISSING_SPOOL", "MISSING_FILAMENT")
ENRICHMENT_SLOT_OVERRIDE_ROW_KEYS = ("slot_id", "tray", "spool_id", "filament_id")

WS_TYPE_PRINT_HISTORY_QUERY = "bambuddy/print_history_query"
WS_TYPE_PRINT_HISTORY_UPLOAD_PHOTO = "bambuddy/print_history_upload_photo"
WS_TYPE_PRINT_HISTORY_UPLOAD_SOURCE_3MF = "bambuddy/print_history_upload_source_3mf"
WS_TYPE_PRINT_HISTORY_ARCHIVE_VIEWER = "bambuddy/print_history_archive_viewer"
WS_TYPE_PRINT_HISTORY_ARCHIVE_ACTION = "bambuddy/print_history_archive_action"
MAX_MANUAL_PHOTO_UPLOAD_BYTES = 8 * 1024 * 1024
DATA_HTTP_VIEW_REGISTERED = f"{DOMAIN}_restore_upload_view_registered"


def _basename(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def _collect_archive_photo_paths(archive: dict[str, Any] | None) -> list[str]:
    if not isinstance(archive, dict):
        return []

    candidates: list[str] = []

    photo_items = archive.get("photo_items")
    if isinstance(photo_items, list):
        for item in photo_items:
            if isinstance(item, dict):
                candidates.append(str(item.get("path") or "").strip())

    photos = archive.get("photos")
    if isinstance(photos, list):
        for item in photos:
            if isinstance(item, str):
                candidates.append(item.strip())
            elif isinstance(item, dict):
                candidates.append(str(item.get("path") or item.get("photo_path") or item.get("url") or "").strip())

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _resolve_uploaded_photo_path(
    archive: dict[str, Any] | None,
    requested_name: str,
    *,
    previous_archive: dict[str, Any] | None = None,
    upload_response: dict[str, Any] | None = None,
) -> str:
    current_candidates = _collect_archive_photo_paths(archive)
    previous_candidates = set(_collect_archive_photo_paths(previous_archive))
    added_candidates = [candidate for candidate in current_candidates if candidate not in previous_candidates]
    requested_path = str(requested_name or "").strip()
    requested_basename = _basename(requested_path)

    for candidate in added_candidates:
        if requested_path and candidate == requested_path:
            return candidate
    for candidate in added_candidates:
        if requested_basename and _basename(candidate) == requested_basename:
            return candidate

    if isinstance(upload_response, dict):
        response_candidates = [
            str(upload_response.get("path") or "").strip(),
            str(upload_response.get("photo_path") or "").strip(),
            str(upload_response.get("url") or "").strip(),
            str(upload_response.get("file_path") or "").strip(),
            str(upload_response.get("filename") or upload_response.get("file_name") or "").strip(),
        ]
        for candidate in response_candidates:
            if candidate and candidate in current_candidates:
                return candidate
        response_basenames = {_basename(candidate) for candidate in response_candidates if candidate}
        for candidate in current_candidates:
            if _basename(candidate) in response_basenames:
                return candidate

    for candidate in current_candidates:
        if candidate and candidate == requested_path:
            return candidate
    for candidate in current_candidates:
        if candidate and _basename(candidate) == requested_basename:
            return candidate
    if added_candidates:
        return added_candidates[-1]
    return requested_path


def _strip_entry_id(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {CONF_ENTRY_ID, "id", "type"}}


def _normalize_3mf_filename(candidate: str, fallback: str) -> str:
    normalized = str(candidate or "").strip().replace("\\", "/")
    normalized = normalized.split("/")[-1].replace("?", "_").replace("#", "_")
    normalized = normalized or str(fallback or "archive").strip() or "archive"
    if not normalized.lower().endswith(".3mf"):
        normalized += ".3mf"
    return normalized


def _resolve_archive_model_resource(
    archive: dict[str, Any], *, preferred_resource_type: str | None = None
) -> dict[str, str]:
    archive_id = _extract_archive_id(archive.get("id")) or 0
    file_path = str(archive.get("file_path") or "").strip()
    source_path = str(archive.get("source_3mf_path") or "").strip()
    archive_name = str(archive.get("print_name") or archive.get("filename") or "").strip()

    if preferred_resource_type == "file":
        if not file_path:
            raise HomeAssistantError(f"Archive {archive_id} does not have an archived G-code file")
        return {
            "resource_type": "file",
            "filename": _normalize_3mf_filename(archive_name or _basename(file_path), f"archive-{archive_id}"),
        }

    if preferred_resource_type == "source":
        if not source_path:
            raise HomeAssistantError(f"Archive {archive_id} does not have an attached source 3MF")
        return {
            "resource_type": "source",
            "filename": _normalize_3mf_filename(_basename(source_path) or archive_name, f"archive-{archive_id}-source"),
        }

    if file_path:
        return {
            "resource_type": "file",
            "filename": _normalize_3mf_filename(archive_name or _basename(file_path), f"archive-{archive_id}"),
        }
    if source_path:
        return {
            "resource_type": "source",
            "filename": _normalize_3mf_filename(_basename(source_path) or archive_name, f"archive-{archive_id}-source"),
        }
    raise HomeAssistantError(f"Archive {archive_id} does not have an archived 3MF or attached source 3MF")


async def _build_archive_action_response(
    hass: HomeAssistant,
    manager: PrintHistoryBrowserManager,
    archive_id: int,
    *,
    entry_id: str,
    intent: str,
) -> dict[str, Any]:
    if not await manager.async_ensure_archive_loaded(archive_id):
        raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

    detail = manager.build_archive_detail_response(archive_id)
    if detail is None:
        raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
    archive = detail.get("archive") if isinstance(detail, dict) else None
    if not isinstance(archive, dict):
        raise HomeAssistantError(f"Archive {archive_id} detail payload is missing archive data")

    preferred_resource_type = None
    if intent == "download_gcode":
        preferred_resource_type = "file"
    elif intent == "download_source_3mf":
        preferred_resource_type = "source"

    resource = _resolve_archive_model_resource(archive, preferred_resource_type=preferred_resource_type)
    resource_type = resource["resource_type"]
    filename = resource["filename"]
    encoded_filename = quote(filename, safe="")
    base_url = manager.base_url.rstrip("/")

    session = aiohttp_client.async_get_clientsession(hass)
    client = BambuddyApiClient(
        session,
        manager.base_url,
        manager.api_key,
        manager.fetch_timeout_seconds,
    )

    try:
        if resource_type == "source":
            token = await client.async_create_source_slicer_token(archive_id)
            download_url = f"{base_url}/api/v1/archives/{archive_id}/source-dl/{token}/{encoded_filename}"
        else:
            token = await client.async_create_archive_slicer_token(archive_id)
            download_url = f"{base_url}/api/v1/archives/{archive_id}/dl/{token}/{encoded_filename}"
    except RuntimeError:
        token = ""
        if resource_type == "source":
            download_url = f"{base_url}/api/v1/archives/{archive_id}/source/{encoded_filename}"
        else:
            download_url = f"{base_url}/api/v1/archives/{archive_id}/file/{encoded_filename}"

    return {
        CONF_ENTRY_ID: entry_id,
        CONF_ARCHIVE_ID: archive_id,
        "intent": intent,
        "resource_type": resource_type,
        "file_name": filename,
        "download_url": download_url,
        "tokenized": bool(token),
        "archive": archive,
    }


def _parse_service_datetime(value: str, field_name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise HomeAssistantError(f"{field_name} is required")
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise HomeAssistantError(f"{field_name} must be a valid ISO datetime") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _archive_duration_for_runtime_repair(archive: dict[str, Any], explicit_duration: int | None) -> tuple[int, str]:
    if explicit_duration is not None:
        if int(explicit_duration) <= 0:
            raise HomeAssistantError("duration_seconds must be greater than zero when provided")
        return int(explicit_duration), "manual_override"

    print_time_seconds = int(archive.get("print_time_seconds") or 0)
    if print_time_seconds > 0:
        return print_time_seconds, "print_time_seconds"

    actual_time_seconds = int(archive.get("actual_time_seconds") or 0)
    if actual_time_seconds > 0:
        return actual_time_seconds, "actual_time_seconds"

    raise HomeAssistantError(
        "No usable duration was found on the archive. Provide duration_seconds explicitly."
    )


SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Optional("immediate"): bool,
    }
)
SERVICE_QUERY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Optional("status"): str,
        vol.Optional("archive_error"): str,
        vol.Optional("enrichment_status"): str,
        vol.Optional("material"): str,
        vol.Optional("duplicates"): str,
        vol.Optional("printer"): str,
        vol.Optional("date_range"): str,
        vol.Optional("start_date"): str,
        vol.Optional("end_date"): str,
        vol.Optional("designer"): str,
        vol.Optional("project"): str,
        vol.Optional("layer_height"): str,
        vol.Optional("tag"): str,
        vol.Optional("tags"): vol.Any(str, [str]),
        vol.Optional("tag_mode"): str,
        vol.Optional("tag_untagged_only"): bool,
        vol.Optional("favorites_only"): bool,
        vol.Optional("search"): str,
        vol.Optional("colors"): vol.Any(str, [str]),
        vol.Optional("selected_day"): str,
        vol.Optional("sort"): str,
        vol.Optional("activity_metric"): str,
        vol.Optional("page"): vol.Coerce(int),
        vol.Optional("page_size"): vol.Coerce(int),
        vol.Optional("include_activity_rows"): bool,
    }
)
SERVICE_DETAIL_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): str, vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int)})
SERVICE_ENRICHMENT_METADATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional(CONF_MODE, default="ALL"): vol.In(ENRICHMENT_METADATA_MODES),
    }
)
SERVICE_UPDATE_ARCHIVE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional("print_name"): str,
        vol.Optional("tags"): str,
        vol.Optional("notes"): str,
        vol.Optional("cost"): vol.Coerce(float),
        vol.Optional("status"): str,
        vol.Optional("failure_reason"): vol.Any(None, str),
        vol.Optional("project_id"): vol.Any(None, vol.Coerce(int), str),
    }
)
SERVICE_UPDATE_ENRICHMENT_METADATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional("tag_metadata"): vol.Any(dict, str),
        vol.Optional("note_metadata"): vol.Any(dict, str),
        vol.Optional("slot_overrides"): vol.Any(list, str),
    }
)
SERVICE_SET_ARCHIVE_FAVORITE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("is_favorite"): bool,
    }
)
SERVICE_APPEND_EVENT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("event_type"): str,
        vol.Required("event_source"): str,
        vol.Optional("event_time"): str,
        vol.Optional("event_status", default=""): str,
        vol.Optional("payload", default={}): vol.Any(dict, str),
        vol.Optional("derived_from", default=""): str,
        vol.Optional("event_key"): str,
    }
)
SERVICE_PRIMARY_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional("photo_path", default=""): str,
    }
)
SERVICE_DELETE_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("photo_path"): str,
    }
)
SERVICE_DELETE_ARCHIVE_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): str, vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int)})
SERVICE_MEDIA_REVIEW_STATE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("review_status"): str,
        vol.Optional("requested_at"): str,
        vol.Optional("started_at"): str,
        vol.Optional("completed_at"): str,
        vol.Optional("dismissed_at"): str,
        vol.Optional("photo_count"): vol.Coerce(int),
        vol.Optional("last_action"): str,
        vol.Optional("review_note"): str,
    }
)
SERVICE_REVIEW_STATE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("review_status"): str,
        vol.Optional("mismatch_flags", default=""): vol.Any(str, [str]),
        vol.Optional("review_note", default=""): str,
        vol.Optional("reviewed_at"): str,
    }
)
SERVICE_REPAIR_LINEAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required(CONF_RELATED_ARCHIVE_ID): vol.Coerce(int),
        vol.Required(CONF_RELATION_TYPE): str,
        vol.Optional("note", default=""): str,
        vol.Optional("created_at"): str,
    }
)
SERVICE_ESTIMATE_PARTIAL_USAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("print_status"): str,
        vol.Optional("printer_id"): vol.Coerce(int),
        vol.Optional("last_layer_num"): vol.Coerce(int),
        vol.Optional("last_progress"): vol.Coerce(float),
        vol.Optional("resolve_spoolman_matches", default=True): bool,
        vol.Optional("keep_tracking_row", default=True): bool,
    }
)
SERVICE_REPAIR_ARCHIVE_FROM_START_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
        vol.Required("started_at"): str,
        vol.Optional("duration_seconds"): vol.Coerce(int),
        vol.Optional("created_at"): str,
        vol.Optional("status"): str,
        vol.Optional("failure_reason"): vol.Any(None, str),
        vol.Optional("audit_note"): str,
        vol.Optional("dry_run", default=False): bool,
        vol.Optional("response_detail", default="full"): vol.In({"full", "summary"}),
        vol.Optional("set_status_completed", default=False): bool,
    }
)
SERVICE_GET_RESTORE_WORKFLOW_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Optional(CONF_SOURCE_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional(CONF_TARGET_ARCHIVE_ID): vol.Coerce(int),
    }
)
SERVICE_CREATE_REPLACEMENT_FROM_UPLOAD_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_SOURCE_ARCHIVE_ID): vol.Coerce(int),
        vol.Required(CONF_UPLOAD_SESSION_ID): str,
        vol.Optional(CONF_PRINTER_ID): vol.Coerce(int),
    }
)
SERVICE_RESTORE_OPERATION_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Required(CONF_SOURCE_ARCHIVE_ID): vol.Coerce(int),
        vol.Required(CONF_TARGET_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional("field_groups"): [str],
        vol.Optional("exclude_tags"): [str],
        vol.Optional("include_tags"): [str],
        vol.Optional("overrides"): dict,
        vol.Optional("run_reenrich"): bool,
        vol.Optional("audit_note"): str,
        vol.Optional("attempt_reenrich"): bool,
        vol.Optional("retain_original"): bool,
    }
)
SERVICE_CLEAR_RESTORE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Optional(CONF_SOURCE_ARCHIVE_ID): vol.Coerce(int),
        vol.Optional(CONF_TARGET_ARCHIVE_ID): vol.Coerce(int),
    }
)


def _resolve_manager(hass: HomeAssistant, entry_id: str | None = None) -> tuple[str, PrintHistoryBrowserManager]:
    all_data = hass.data.get(DOMAIN, {})
    managers = {
        candidate_entry_id: entry_data
        for candidate_entry_id, entry_data in all_data.items()
        if isinstance(entry_data, dict) and DATA_MANAGER in entry_data
    }
    if entry_id:
        entry_data = managers.get(entry_id)
        if entry_data is None:
            raise HomeAssistantError(f"Unknown Bambuddy entry_id: {entry_id}")
        return entry_id, entry_data[DATA_MANAGER]

    if not managers:
        raise HomeAssistantError("No loaded Bambuddy entries are available")

    if len(managers) > 1:
        raise HomeAssistantError("Multiple Bambuddy entries are loaded; specify entry_id")

    resolved_entry_id, entry_data = next(iter(managers.items()))
    return resolved_entry_id, entry_data[DATA_MANAGER]


def _extract_archive_id(value: Any) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _extract_uploaded_archive_id(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("id"),
        payload.get("archive_id"),
        payload.get("target_archive_id"),
    ]
    archive_payload = payload.get("archive")
    if isinstance(archive_payload, dict):
        candidates.extend(
            [
                archive_payload.get("id"),
                archive_payload.get("archive_id"),
                archive_payload.get("target_archive_id"),
            ]
        )

    for candidate in candidates:
        normalized = _extract_archive_id(candidate)
        if normalized is not None:
            return normalized
    return None


def _extract_restore_count(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return max(0, int(value))
        normalized = _extract_archive_id(value)
        if normalized is not None:
            return normalized
    return 0


def _extract_restore_workflow_state(payload: dict[str, Any], default: str) -> str:
    for key in ("workflow_state", "state", "status"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    return default


def _extract_enrichment_status(detail_response: dict[str, Any] | None) -> str:
    if isinstance(detail_response, dict) and isinstance(detail_response.get("archive"), dict):
        archive = detail_response.get("archive", {})
    elif isinstance(detail_response, dict):
        archive = detail_response
    else:
        archive = {}
    if not isinstance(archive, dict):
        return ""
    return str(archive.get("enrichment_status", "")).strip()


def _normalize_enrichment_metadata_mode(value: Any) -> str:
    normalized = str(value or "ALL").strip().upper() or "ALL"
    if normalized not in ENRICHMENT_METADATA_MODES:
        raise HomeAssistantError(
            f"mode must be one of {', '.join(ENRICHMENT_METADATA_MODES)}"
        )
    return normalized


def _parse_service_metadata_object(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    raw = str(value or "").strip()
    if not raw:
        raise HomeAssistantError(f"{field_name} must be a JSON object or mapping")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HomeAssistantError(f"{field_name} must be valid JSON") from error
    if not isinstance(parsed, dict):
        raise HomeAssistantError(f"{field_name} must be a JSON object")
    return parsed


def _normalize_system_tag_values(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_values = [str(item).strip() for item in value]
    else:
        raw_values = [item.strip() for item in str(value or "").split(",")]

    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_values:
        if not raw_tag:
            continue
        normalized = raw_tag.lower()
        is_system = normalized in SYSTEM_TAG_VALUES or any(normalized.startswith(prefix) for prefix in SYSTEM_TAG_PREFIXES)
        if not is_system:
            raise HomeAssistantError(f"Only system-managed enrichment tags are allowed here: {raw_tag}")
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(raw_tag)
    return tags


def _parse_slot_override_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") or raw.startswith("{"):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                raise HomeAssistantError("slot_overrides must be valid JSON") from error
        else:
            rows: list[dict[str, Any]] = []
            for row_index, chunk in enumerate(re.split(r"[;\r\n]+", raw)):
                normalized_chunk = chunk.strip()
                if not normalized_chunk:
                    continue
                row: dict[str, Any] = {}
                for token in re.split(r"[\s,]+", normalized_chunk):
                    if "=" not in token:
                        continue
                    key, raw_token_value = token.split("=", 1)
                    normalized_key = key.strip().lower()
                    token_value = raw_token_value.strip()
                    if not token_value:
                        continue
                    if normalized_key in {"slot", "slot_id"}:
                        row["slot_id"] = token_value
                    elif normalized_key == "tray":
                        row["tray"] = token_value
                    elif normalized_key in {"spool", "spool_id"}:
                        row["spool_id"] = token_value
                    elif normalized_key in {"filament", "filament_id"}:
                        row["filament_id"] = token_value
                if not row:
                    raise HomeAssistantError(
                        f"slot_overrides shorthand row {row_index + 1} must contain key=value pairs like SLOT=1 TRAY=B2"
                    )
                rows.append(row)
            value = rows

    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise HomeAssistantError("slot_overrides must be a JSON array")

    rows: list[dict[str, Any]] = []
    seen_slot_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise HomeAssistantError(f"slot_overrides[{index}] must be a JSON object")

        slot_id = str(item.get("slot_id", "")).strip()
        if not slot_id:
            raise HomeAssistantError(f"slot_overrides[{index}] must include slot_id")
        if slot_id in seen_slot_ids:
            raise HomeAssistantError(f"slot_overrides contains duplicate slot_id: {slot_id}")
        seen_slot_ids.add(slot_id)

        row: dict[str, Any] = {"slot_id": slot_id}

        tray_value = str(item.get("tray", "")).strip()
        if tray_value:
            row["tray"] = tray_value

        for field_name in ("spool_id", "filament_id"):
            field_value = item.get(field_name)
            if field_value in (None, "", "null", "None"):
                continue
            try:
                normalized = int(field_value)
            except (TypeError, ValueError) as error:
                raise HomeAssistantError(f"slot_overrides[{index}].{field_name} must be an integer") from error
            if normalized <= 0:
                raise HomeAssistantError(f"slot_overrides[{index}].{field_name} must be a positive integer")
            row[field_name] = normalized

        if len(row) == 1:
            raise HomeAssistantError(
                f"slot_overrides[{index}] must include at least one of tray, spool_id, or filament_id"
            )
        rows.append(row)

    return rows


def _slot_override_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("slot_overrides") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        for key in ENRICHMENT_SLOT_OVERRIDE_ROW_KEYS:
            value = item.get(key)
            if key == "slot_id":
                normalized = str(value or "").strip()
                if normalized:
                    row[key] = normalized
            elif key == "tray":
                normalized = str(value or "").strip()
                if normalized:
                    row[key] = normalized
            elif value not in (None, "", "null", "None"):
                try:
                    row[key] = int(value)
                except (TypeError, ValueError):
                    continue
        if row.get("slot_id"):
            rows.append(row)
    return rows


def _build_archive_enrichment_metadata_response(
    detail_response: dict[str, Any],
    *,
    entry_id: str,
    archive_id: int,
    mode: str,
) -> dict[str, Any]:
    archive = detail_response.get("archive", {}) if isinstance(detail_response, dict) else {}
    if not isinstance(archive, dict):
        archive = {}
    note_parts = split_enrichment_notes(str(archive.get("notes", "")))
    payload_rows = note_payload_rows(archive)
    filtered_rows = filter_note_payload_rows(payload_rows, mode)
    return {
        CONF_ENTRY_ID: entry_id,
        CONF_ARCHIVE_ID: archive_id,
        CONF_MODE: mode,
        "archive": archive,
        "tag_metadata": {
            "raw_tags": str(archive.get("tags", "")),
            "system_tags": system_tags(str(archive.get("tags", ""))),
            "user_tags": user_tags(str(archive.get("tags", ""))),
        },
        "note_metadata": {
            "marker": ENRICHMENT_MARKER,
            "recovery_marker": RECOVERY_AUDIT_MARKER,
            "system_notes": note_parts["system_notes"],
            "user_notes": note_parts["user_notes"],
            "recovery_block": note_parts["recovery_block"],
            "payload": note_parts["payload"],
            "slot_overrides": _slot_override_rows_from_payload(note_parts["payload"]),
            "payload_raw": note_parts["payload_raw"],
            "has_payload": bool(note_parts["has_payload"]),
            "payload_rows": payload_rows,
            "filtered_payload_rows": filtered_rows,
            "filtered_row_indices": [int(row.get("row_index", 0)) for row in filtered_rows],
            "payload_row_count": len(payload_rows),
            "filtered_payload_row_count": len(filtered_rows),
            "enrichment_status": str(archive.get("enrichment_status", "")),
        },
    }


async def _async_apply_archive_update(
    hass: HomeAssistant,
    manager: PrintHistoryBrowserManager,
    *,
    archive_id: int,
    update_payload: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    started = perf_counter()
    session = aiohttp_client.async_get_clientsession(hass)
    client = BambuddyApiClient(
        session,
        manager.base_url,
        manager.api_key,
        manager.fetch_timeout_seconds,
    )
    try:
        await client.async_update_archive(archive_id, update_payload)
        refreshed = await manager.async_refresh_archive_detail(
            archive_id,
            operation=operation,
            extra_details={"updated_fields": sorted(update_payload.keys())},
        )
    except RuntimeError as error:
        raise HomeAssistantError(str(error)) from error

    if refreshed is None:
        raise HomeAssistantError(f"Archive {archive_id} could not be refreshed from Bambuddy")

    manager.record_mutation(
        operation=operation,
        archive_id=archive_id,
        duration_ms=round((perf_counter() - started) * 1000, 1),
        details={"updated_fields": sorted(update_payload.keys())},
    )
    return refreshed


def _build_runtime_repair_client(
    hass: HomeAssistant,
    entry_id: str,
    manager: PrintHistoryBrowserManager,
) -> tuple[BambuddyRuntimeRepairClient | None, dict[str, Any] | None]:
    runtime_repair_base_url = str(
        manager.entry.options.get(
            CONF_RUNTIME_REPAIR_BASE_URL,
            manager.entry.data.get(CONF_RUNTIME_REPAIR_BASE_URL, ""),
        )
    ).strip().rstrip("/")
    runtime_repair_token = str(
        manager.entry.options.get(
            CONF_RUNTIME_REPAIR_TOKEN,
            manager.entry.data.get(CONF_RUNTIME_REPAIR_TOKEN, ""),
        )
    ).strip()
    timeout_seconds = int(
        manager.entry.options.get(
            CONF_FETCH_TIMEOUT_SECONDS,
            manager.entry.data.get(CONF_FETCH_TIMEOUT_SECONDS, 30),
        )
    )

    if not runtime_repair_base_url:
        return None, {
            "success": False,
            CONF_ENTRY_ID: entry_id,
            "error": "runtime_repair_base_url_not_configured",
            "message": "Bambuddy runtime repair base URL is not configured on the integration entry.",
        }
    if not runtime_repair_token:
        return None, {
            "success": False,
            CONF_ENTRY_ID: entry_id,
            "error": "runtime_repair_token_not_configured",
            "message": "Bambuddy runtime repair token is not configured on the integration entry.",
        }

    session = aiohttp_client.async_get_clientsession(hass)
    return (
        BambuddyRuntimeRepairClient(
            session,
            runtime_repair_base_url,
            runtime_repair_token,
            timeout_seconds,
        ),
        None,
    )


def _normalize_restore_request_payload(call_data: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        CONF_SOURCE_ARCHIVE_ID: int(call_data[CONF_SOURCE_ARCHIVE_ID]),
        CONF_TARGET_ARCHIVE_ID: int(call_data[CONF_TARGET_ARCHIVE_ID]),
        "dry_run": bool(dry_run),
    }
    if call_data.get("field_groups"):
        payload["field_groups"] = [str(item).strip() for item in call_data.get("field_groups", []) if str(item).strip()]
    if call_data.get("exclude_tags"):
        payload["exclude_tags"] = [str(item).strip() for item in call_data.get("exclude_tags", []) if str(item).strip()]
    if call_data.get("include_tags"):
        payload["include_tags"] = [str(item).strip() for item in call_data.get("include_tags", []) if str(item).strip()]
    if call_data.get("overrides"):
        payload["overrides"] = dict(call_data.get("overrides", {}))
    if call_data.get("run_reenrich") is not None:
        payload["run_reenrich"] = bool(call_data.get("run_reenrich"))
    return payload


def _workflow_response(entry_id: str, workflow) -> dict[str, Any]:
    response = workflow.to_response()
    response[CONF_ENTRY_ID] = entry_id
    return response


def _build_upload_diagnostics(
    *,
    request: web.Request,
    fields: dict[str, Any],
    file_name: str,
    file_content_type: str,
    byte_count: int,
    chunk_count: int,
    first_chunk_size: int,
) -> dict[str, Any]:
    return {
        "request_content_type": str(getattr(request, "headers", {}).get("Content-Type", "") or ""),
        "fields_present": sorted(str(key) for key in fields.keys()),
        "file_name": file_name,
        "file_content_type": file_content_type,
        "byte_count": byte_count,
        "chunk_count": chunk_count,
        "first_chunk_size": first_chunk_size,
    }


async def _read_uploaded_file_part(
    part: Any,
    *,
    max_upload_bytes: int = DEFAULT_RESTORE_UPLOAD_MAX_BYTES,
) -> tuple[list[bytes], int, int, int]:
    chunks: list[bytes] = []
    byte_count = 0
    chunk_count = 0
    first_chunk_size = 0

    while True:
        chunk = await part.read_chunk(size=64 * 1024)
        if not chunk:
            break
        chunk_count += 1
        if first_chunk_size <= 0:
            first_chunk_size = len(chunk)
        byte_count += len(chunk)
        if byte_count > max(1, int(max_upload_bytes)):
            raise HomeAssistantError(
                f"Upload payload exceeds the configured limit of {max(1, int(max_upload_bytes))} bytes"
            )
        chunks.append(chunk)

    return chunks, byte_count, chunk_count, first_chunk_size


class ReplacementArchiveDiscoverView(HomeAssistantView):
    url = RESTORE_UPLOAD_DISCOVER_URL
    name = "api:bambuddy:print-history:archive-repair:replacement:discover"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]

        try:
            reader = await request.multipart()
        except ValueError as error:
            return web.json_response({"success": False, "error": "invalid_multipart", "message": str(error)}, status=400)

        fields: dict[str, Any] = {}
        file_name = ""
        file_content_type = "application/octet-stream"
        file_chunks: list[bytes] = []
        file_byte_count = 0
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                file_name = str(getattr(part, "filename", "") or "").strip()
                file_content_type = str(part.headers.get("Content-Type", "application/octet-stream"))
                file_chunks, file_byte_count, _file_chunk_count, _first_chunk_size = await _read_uploaded_file_part(part)
                continue
            fields[part.name] = await part.text()

        entry_id_raw = str(fields.get(CONF_ENTRY_ID, "")).strip() or None
        source_archive_id = _extract_archive_id(fields.get(CONF_SOURCE_ARCHIVE_ID))
        printer_id = _extract_archive_id(fields.get(CONF_PRINTER_ID))

        if source_archive_id is None:
            return web.json_response(
                {"success": False, "error": "source_archive_id_required", "message": "source_archive_id is required."},
                status=400,
            )
        if printer_id is None:
            return web.json_response(
                {"success": False, "error": "printer_id_required", "message": "printer_id is required."},
                status=400,
            )
        if not file_name:
            return web.json_response(
                {"success": False, "error": "file_required", "message": "multipart field 'file' is required."},
                status=400,
            )

        try:
            resolved_entry_id, manager = _resolve_manager(hass, entry_id_raw)
            if not await manager.async_ensure_archive_loaded(source_archive_id):
                raise HomeAssistantError(f"Archive {source_archive_id} was not found in the Bambuddy local store")
        except HomeAssistantError as error:
            return web.json_response({"success": False, "error": "resolve_failed", "message": str(error)}, status=400)

        if file_byte_count > manager.restore_uploads.max_upload_bytes:
            return web.json_response(
                {
                    "success": False,
                    "error": "upload_failed",
                    "message": f"Upload payload exceeds the configured limit of {manager.restore_uploads.max_upload_bytes} bytes",
                },
                status=400,
            )

        manager.restore_uploads.cleanup_expired()
        session_id, file_path, normalized_file_name = manager.restore_uploads.prepare_session_file_path(file_name)
        size_bytes = 0
        try:
            with file_path.open("wb") as handle:
                for chunk in file_chunks:
                    size_bytes += len(chunk)
                    handle.write(chunk)

            if size_bytes <= 0:
                raise HomeAssistantError("Upload payload is empty")

            session = manager.restore_uploads.finalize_session(
                session_id=session_id,
                entry_id=resolved_entry_id,
                source_archive_id=source_archive_id,
                printer_id=printer_id,
                file_name=normalized_file_name,
                content_type=file_content_type,
                size_bytes=size_bytes,
                file_path=file_path,
            )
            workflow = manager.restore_workflow.set_upload_ready(
                entry_id=resolved_entry_id,
                source_archive_id=source_archive_id,
                upload_session_id=session.session_id,
                summary={"upload": session.to_response()},
            )
            manager.record_mutation(
                operation="stage_replacement_upload",
                archive_id=source_archive_id,
                duration_ms=0.0,
                details={
                    CONF_UPLOAD_SESSION_ID: session.session_id,
                    CONF_PRINTER_ID: printer_id,
                    "filename": session.file_name,
                    "size_bytes": session.size_bytes,
                },
            )
            manager._notify_listeners()
            return web.json_response(
                {
                    "success": True,
                    CONF_ENTRY_ID: resolved_entry_id,
                    "upload": session.to_response(),
                    "workflow": workflow.to_response(),
                }
            )
        except HomeAssistantError as error:
            manager.restore_uploads.discard_session(session_id)
            manager.restore_workflow.set_error(
                entry_id=resolved_entry_id,
                source_archive_id=source_archive_id,
                message=str(error),
            )
            manager._notify_listeners()
            return web.json_response({"success": False, "error": "upload_failed", "message": str(error)}, status=400)
        except OSError as error:
            manager.restore_uploads.discard_session(session_id)
            manager.restore_workflow.set_error(
                entry_id=resolved_entry_id,
                source_archive_id=source_archive_id,
                message=f"Unable to stage uploaded file: {error}",
            )
            manager._notify_listeners()
            return web.json_response(
                {"success": False, "error": "upload_io_failed", "message": f"Unable to stage uploaded file: {error}"},
                status=500,
            )


class ArchiveSource3mfUploadView(HomeAssistantView):
    url = SOURCE_3MF_UPLOAD_URL
    name = "api:bambuddy:print-history:archive:source-3mf:upload"
    requires_auth = True

    async def post(self, request: web.Request, archive_id: str | None = None) -> web.Response:
        hass = request.app["hass"]
        started = perf_counter()
        archive_id_value = _extract_archive_id(request.match_info.get(CONF_ARCHIVE_ID) or archive_id)
        if archive_id_value is None:
            return web.json_response(
                {"success": False, "error": "archive_id_required", "message": "archive_id must be a positive integer."},
                status=400,
            )

        try:
            reader = await request.multipart()
        except ValueError as error:
            return web.json_response({"success": False, "error": "invalid_multipart", "message": str(error)}, status=400)

        fields: dict[str, Any] = {}
        file_name = ""
        file_content_type = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
        chunks: list[bytes] = []
        byte_count = 0
        chunk_count = 0
        first_chunk_size = 0
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                file_name = str(getattr(part, "filename", "") or "").strip()
                file_content_type = str(
                    part.headers.get("Content-Type", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")
                )
                chunks, byte_count, chunk_count, first_chunk_size = await _read_uploaded_file_part(part)
                continue
            fields[part.name] = await part.text()

        entry_id_raw = str(fields.get(CONF_ENTRY_ID, "")).strip() or None
        if not file_name:
            return web.json_response(
                {"success": False, "error": "file_required", "message": "multipart field 'file' is required."},
                status=400,
            )

        if not file_name.lower().endswith(".3mf"):
            return web.json_response(
                {"success": False, "error": "invalid_file_type", "message": "File must be a .3mf file."},
                status=400,
            )

        try:
            resolved_entry_id, manager = _resolve_manager(hass, entry_id_raw)
            if not await manager.async_ensure_archive_loaded(archive_id_value):
                raise HomeAssistantError(f"Archive {archive_id_value} was not found in the Bambuddy local store")
        except HomeAssistantError as error:
            return web.json_response({"success": False, "error": "resolve_failed", "message": str(error)}, status=400)

        try:
            if byte_count > manager.restore_uploads.max_upload_bytes:
                raise HomeAssistantError(
                    f"Upload payload exceeds the configured limit of {manager.restore_uploads.max_upload_bytes} bytes"
                )
            if byte_count <= 0:
                raise HomeAssistantError("Upload payload is empty after multipart parsing")

            session = aiohttp_client.async_get_clientsession(hass)
            client = BambuddyApiClient(
                session,
                manager.base_url,
                manager.api_key,
                manager.fetch_timeout_seconds,
            )
            upload_response = await client.async_upload_archive_source_3mf(
                archive_id_value,
                file_name=file_name,
                mime_type=file_content_type,
                content=b"".join(chunks),
            )
            refreshed_archive = await manager.async_refresh_archive_detail(
                archive_id_value,
                operation="upload_archive_source_3mf",
                extra_details={
                    "file_name": file_name,
                    "byte_count": byte_count,
                    "chunk_count": chunk_count,
                },
            )
            if refreshed_archive is None:
                raise HomeAssistantError(f"Archive {archive_id_value} could not be refreshed after upload")

            response = manager.build_archive_detail_response(archive_id_value) or {"archive": refreshed_archive}
            response.update(
                {
                    "success": True,
                    CONF_ENTRY_ID: resolved_entry_id,
                    CONF_ARCHIVE_ID: archive_id_value,
                    "upload": {
                        "file_name": file_name,
                        "byte_count": byte_count,
                    },
                }
            )
            if upload_response:
                response["upload_response"] = upload_response
            return web.json_response(response)
        except HomeAssistantError as error:
            if "manager" in locals():
                manager.record_mutation(
                    operation="upload_archive_source_3mf_failed",
                    archive_id=archive_id_value,
                    duration_ms=round((perf_counter() - started) * 1000, 1),
                    details={
                        "file_name": file_name,
                        "byte_count": byte_count,
                        "chunk_count": chunk_count,
                        "message": str(error),
                    },
                )
            diagnostics = _build_upload_diagnostics(
                request=request,
                fields=fields,
                file_name=file_name,
                file_content_type=file_content_type,
                byte_count=byte_count,
                chunk_count=chunk_count,
                first_chunk_size=first_chunk_size,
            )
            _LOGGER.warning(
                "Archive source 3MF upload failed for archive %s (%s bytes, chunks=%s, first_chunk=%s, file=%s, content_type=%s): %s",
                archive_id_value,
                byte_count,
                chunk_count,
                first_chunk_size,
                file_name,
                file_content_type,
                error,
            )
            return web.json_response(
                {
                    "success": False,
                    "error": "upload_failed",
                    "message": str(error),
                    "diagnostics": diagnostics,
                },
                status=400,
            )
        except RuntimeError as error:
            if "manager" in locals():
                manager.record_mutation(
                    operation="upload_archive_source_3mf_failed",
                    archive_id=archive_id_value,
                    duration_ms=round((perf_counter() - started) * 1000, 1),
                    details={
                        "file_name": file_name,
                        "byte_count": byte_count,
                        "chunk_count": chunk_count,
                        "message": str(error),
                    },
                )
            diagnostics = _build_upload_diagnostics(
                request=request,
                fields=fields,
                file_name=file_name,
                file_content_type=file_content_type,
                byte_count=byte_count,
                chunk_count=chunk_count,
                first_chunk_size=first_chunk_size,
            )
            _LOGGER.warning(
                "Archive source 3MF upload proxy received runtime error for archive %s (%s bytes, chunks=%s, first_chunk=%s, file=%s, content_type=%s): %s",
                archive_id_value,
                byte_count,
                chunk_count,
                first_chunk_size,
                file_name,
                file_content_type,
                error,
            )
            return web.json_response(
                {
                    "success": False,
                    "error": "upload_failed",
                    "message": str(error),
                    "diagnostics": diagnostics,
                },
                status=502,
            )


async def _resolve_archive_viewer_request(
    request: web.Request,
) -> tuple[HomeAssistant, str, int, PrintHistoryBrowserManager, BambuddyApiClient] | web.Response:
    hass = request.app["hass"]
    entry_id_raw = str(request.query.get(CONF_ENTRY_ID, "")).strip() or None
    archive_id = _extract_archive_id(request.match_info.get(CONF_ARCHIVE_ID))
    if archive_id is None:
        return web.json_response(
            {"success": False, "error": "archive_id_required", "message": "archive_id must be a positive integer."},
            status=400,
        )

    try:
        resolved_entry_id, manager = _resolve_manager(hass, entry_id_raw)
    except HomeAssistantError as error:
        return web.json_response({"success": False, "error": "resolve_failed", "message": str(error)}, status=400)

    session = aiohttp_client.async_get_clientsession(hass)
    client = BambuddyApiClient(
        session,
        manager.base_url,
        manager.api_key,
        manager.fetch_timeout_seconds,
    )
    return hass, resolved_entry_id, archive_id, manager, client


class ArchiveViewerGcodeView(HomeAssistantView):
    url = ARCHIVE_VIEWER_GCODE_URL
    name = "api:bambuddy:print-history:archive-viewer:gcode"
    requires_auth = True

    async def get(self, request: web.Request, archive_id: str | None = None) -> web.Response:
        resolved = await _resolve_archive_viewer_request(request)
        if isinstance(resolved, web.Response):
            return resolved

        _hass, _entry_id, archive_id, _manager, client = resolved
        try:
            gcode = await client.async_fetch_archive_gcode(archive_id)
        except RuntimeError as error:
            return web.json_response(
                {"success": False, "error": "gcode_fetch_failed", "message": str(error)},
                status=502,
            )

        return web.Response(text=gcode, content_type="text/plain", charset="utf-8")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if not hass.data.get(DATA_HTTP_VIEW_REGISTERED):
        hass.http.register_view(ReplacementArchiveDiscoverView())
        hass.http.register_view(ArchiveSource3mfUploadView())
        hass.http.register_view(ArchiveViewerGcodeView())
        hass.data[DATA_HTTP_VIEW_REGISTERED] = True

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_PRINT_HISTORY_QUERY,
            vol.Optional(CONF_ENTRY_ID): str,
            vol.Optional("status"): str,
            vol.Optional("archive_error"): str,
            vol.Optional("enrichment_status"): str,
            vol.Optional("material"): str,
            vol.Optional("duplicates"): str,
            vol.Optional("printer"): str,
            vol.Optional("date_range"): str,
            vol.Optional("start_date"): str,
            vol.Optional("end_date"): str,
            vol.Optional("designer"): str,
            vol.Optional("project"): str,
            vol.Optional("layer_height"): str,
            vol.Optional("tag"): str,
            vol.Optional("tags"): vol.Any(str, [str]),
            vol.Optional("tag_mode"): str,
            vol.Optional("tag_untagged_only"): bool,
            vol.Optional("favorites_only"): bool,
            vol.Optional("search"): str,
            vol.Optional("colors"): vol.Any(str, [str]),
            vol.Optional("selected_day"): str,
            vol.Optional("sort"): str,
            vol.Optional("activity_metric"): str,
            vol.Optional("page"): vol.Coerce(int),
            vol.Optional("page_size"): vol.Coerce(int),
            vol.Optional("include_activity_rows"): bool,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_query(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        try:
            entry_id, manager = _resolve_manager(hass, msg.get(CONF_ENTRY_ID))
            response = manager.build_query_response(_strip_entry_id(msg), source="websocket")
            response[CONF_ENTRY_ID] = entry_id
        except HomeAssistantError as err:
            connection.send_error(msg["id"], "query_failed", str(err))
            return

        connection.send_result(msg["id"], response)

    websocket_api.async_register_command(hass, websocket_handle_query)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_PRINT_HISTORY_ARCHIVE_VIEWER,
            vol.Optional(CONF_ENTRY_ID): str,
            vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
            vol.Optional("include_gcode"): bool,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_archive_viewer(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        try:
            entry_id, manager = _resolve_manager(hass, msg.get(CONF_ENTRY_ID))
            archive_id = int(msg[CONF_ARCHIVE_ID])

            session = aiohttp_client.async_get_clientsession(hass)
            client = BambuddyApiClient(
                session,
                manager.base_url,
                manager.api_key,
                manager.fetch_timeout_seconds,
            )
            capabilities = await client.async_fetch_archive_capabilities(archive_id)
            response: dict[str, Any] = {
                CONF_ENTRY_ID: entry_id,
                CONF_ARCHIVE_ID: archive_id,
                "capabilities": capabilities,
            }

            if bool(msg.get("include_gcode", True)) and bool(capabilities.get("has_gcode")):
                response["gcode"] = await client.async_fetch_archive_gcode(archive_id)
        except HomeAssistantError as err:
            connection.send_error(msg["id"], "archive_viewer_failed", str(err))
            return
        except RuntimeError as err:
            connection.send_error(msg["id"], "archive_viewer_failed", str(err))
            return

        connection.send_result(msg["id"], response)

    websocket_api.async_register_command(hass, websocket_handle_archive_viewer)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_PRINT_HISTORY_ARCHIVE_ACTION,
            vol.Optional(CONF_ENTRY_ID): str,
            vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
            vol.Required("intent"): vol.In({"download", "download_gcode", "download_source_3mf", "open_in_slicer"}),
        }
    )
    @websocket_api.async_response
    async def websocket_handle_archive_action(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        try:
            entry_id, manager = _resolve_manager(hass, msg.get(CONF_ENTRY_ID))
            archive_id = int(msg[CONF_ARCHIVE_ID])
            response = await _build_archive_action_response(
                hass,
                manager,
                archive_id,
                entry_id=entry_id,
                intent=str(msg.get("intent") or "").strip(),
            )
        except HomeAssistantError as err:
            connection.send_error(msg["id"], "archive_action_failed", str(err))
            return
        except RuntimeError as err:
            connection.send_error(msg["id"], "archive_action_failed", str(err))
            return

        connection.send_result(msg["id"], response)

    websocket_api.async_register_command(hass, websocket_handle_archive_action)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_PRINT_HISTORY_UPLOAD_PHOTO,
            vol.Optional(CONF_ENTRY_ID): str,
            vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
            vol.Required("file_name"): str,
            vol.Required("mime_type"): str,
            vol.Required("content_base64"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_upload_photo(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        try:
            entry_id, manager = _resolve_manager(hass, msg.get(CONF_ENTRY_ID))
            archive_id = int(msg[CONF_ARCHIVE_ID])
            if not await manager.async_ensure_archive_loaded(archive_id):
                raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
            try:
                content = base64.b64decode(str(msg.get("content_base64", "")), validate=True)
            except (ValueError, binascii.Error) as error:
                raise HomeAssistantError("Upload payload is not valid base64") from error
            if not content:
                raise HomeAssistantError("Upload payload is empty")
            if len(content) > MAX_MANUAL_PHOTO_UPLOAD_BYTES:
                raise HomeAssistantError(
                    f"Upload payload exceeds the {MAX_MANUAL_PHOTO_UPLOAD_BYTES // (1024 * 1024)}MB limit"
                )

            mime_type = str(msg.get("mime_type", "")).strip().lower()
            if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise HomeAssistantError("Manual upload only supports JPEG, PNG, or WebP images")

            session = aiohttp_client.async_get_clientsession(hass)
            client = BambuddyApiClient(
                session,
                manager.base_url,
                manager.api_key,
                manager.fetch_timeout_seconds,
            )
            archive_before_upload = manager.build_archive_detail_response(archive_id)
            upload_response = await client.async_upload_archive_photo(
                archive_id,
                file_name=str(msg.get("file_name", "")),
                mime_type=mime_type,
                content=content,
            )
            refreshed_archive = await manager.async_refresh_archive_detail(
                archive_id,
                operation="upload_archive_photo",
                extra_details={
                    "file_name": str(msg.get("file_name", "")).strip(),
                    "mime_type": mime_type,
                    "byte_count": len(content),
                },
            )
            if refreshed_archive is None:
                raise HomeAssistantError(f"Archive {archive_id} could not be refreshed after upload")
            uploaded_photo_path = _resolve_uploaded_photo_path(
                refreshed_archive,
                str(msg.get("file_name", "")).strip(),
                previous_archive=archive_before_upload,
                upload_response=upload_response,
            )

            response = manager.build_archive_detail_response(archive_id)
            if response is None:
                raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
            response[CONF_ENTRY_ID] = entry_id
            response[CONF_ARCHIVE_ID] = archive_id
            response["uploaded_photo_path"] = uploaded_photo_path
            response["upload"] = {
                "file_name": str(msg.get("file_name", "")).strip(),
                "mime_type": mime_type,
                "byte_count": len(content),
            }
            if upload_response:
                response["upload_response"] = upload_response
            connection.send_result(msg["id"], response)
        except HomeAssistantError as err:
            connection.send_error(msg["id"], "upload_failed", str(err))
        except RuntimeError as err:
            connection.send_error(msg["id"], "upload_failed", str(err))

    websocket_api.async_register_command(hass, websocket_handle_upload_photo)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_PRINT_HISTORY_UPLOAD_SOURCE_3MF,
            vol.Optional(CONF_ENTRY_ID): str,
            vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int),
            vol.Required("file_name"): str,
            vol.Required("mime_type"): str,
            vol.Required("content_base64"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_upload_source_3mf(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        archive_id = 0
        file_name = str(msg.get("file_name", "")).strip()
        byte_count = 0
        try:
            entry_id, manager = _resolve_manager(hass, msg.get(CONF_ENTRY_ID))
            archive_id = int(msg[CONF_ARCHIVE_ID])
            if not await manager.async_ensure_archive_loaded(archive_id):
                raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
            try:
                content = base64.b64decode(str(msg.get("content_base64", "")), validate=True)
            except (ValueError, binascii.Error) as error:
                raise HomeAssistantError("Upload payload is not valid base64") from error

            if not content:
                raise HomeAssistantError("Upload payload is empty")
            byte_count = len(content)
            if len(content) > manager.restore_uploads.max_upload_bytes:
                raise HomeAssistantError(
                    f"Upload payload exceeds the configured limit of {manager.restore_uploads.max_upload_bytes} bytes"
                )

            if not file_name.lower().endswith(".3mf"):
                raise HomeAssistantError("Source upload only accepts .3mf files")

            mime_type = str(msg.get("mime_type", "")).strip() or "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"

            session = aiohttp_client.async_get_clientsession(hass)
            client = BambuddyApiClient(
                session,
                manager.base_url,
                manager.api_key,
                manager.fetch_timeout_seconds,
            )
            upload_response = await client.async_upload_archive_source_3mf(
                archive_id,
                file_name=file_name,
                mime_type=mime_type,
                content=content,
            )
            refreshed_archive = await manager.async_refresh_archive_detail(
                archive_id,
                operation="upload_archive_source_3mf",
                extra_details={
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "byte_count": len(content),
                },
            )
            if refreshed_archive is None:
                raise HomeAssistantError(f"Archive {archive_id} could not be refreshed after upload")

            response = manager.build_archive_detail_response(archive_id)
            if response is None:
                raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
            response[CONF_ENTRY_ID] = entry_id
            response[CONF_ARCHIVE_ID] = archive_id
            response["upload"] = {
                "file_name": file_name,
                "mime_type": mime_type,
                "byte_count": len(content),
            }
            if upload_response:
                response["upload_response"] = upload_response
            connection.send_result(msg["id"], response)
        except HomeAssistantError as err:
            if "manager" in locals():
                manager.record_mutation(
                    operation="upload_archive_source_3mf_failed",
                    archive_id=archive_id,
                    duration_ms=0.0,
                    details={
                        "file_name": file_name,
                        "byte_count": byte_count,
                        "message": str(err),
                    },
                )
            _LOGGER.warning(
                "Archive source 3MF websocket upload failed for archive %s (%s bytes, file=%s): %s",
                archive_id,
                byte_count,
                file_name,
                err,
            )
            connection.send_error(msg["id"], "upload_failed", str(err))
        except RuntimeError as err:
            if "manager" in locals():
                manager.record_mutation(
                    operation="upload_archive_source_3mf_failed",
                    archive_id=archive_id,
                    duration_ms=0.0,
                    details={
                        "file_name": file_name,
                        "byte_count": byte_count,
                        "message": str(err),
                    },
                )
            _LOGGER.warning(
                "Archive source 3MF websocket upload runtime error for archive %s (%s bytes, file=%s): %s",
                archive_id,
                byte_count,
                file_name,
                err,
            )
            connection.send_error(msg["id"], "upload_failed", str(err))

    websocket_api.async_register_command(hass, websocket_handle_upload_source_3mf)

    async def async_handle_refresh(call: ServiceCall) -> None:
        entry_id = call.data.get(CONF_ENTRY_ID)
        immediate = bool(call.data.get("immediate", False))
        managers = []
        if entry_id:
            entry_data = hass.data[DOMAIN].get(entry_id)
            if entry_data is not None:
                managers.append(entry_data[DATA_MANAGER])
        else:
            managers.extend(data[DATA_MANAGER] for data in hass.data[DOMAIN].values())

        for manager in managers:
            await manager.async_request_refresh("service", delay_seconds=0.0 if immediate else 1.0)

    async def async_handle_query(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        response = manager.build_query_response(
            {key: value for key, value in call.data.items() if key != CONF_ENTRY_ID},
            source="service",
        )
        response[CONF_ENTRY_ID] = entry_id
        return response

    async def async_handle_detail(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_get_enrichment_metadata(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        mode = _normalize_enrichment_metadata_mode(call.data.get(CONF_MODE))
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        detail_response = manager.build_archive_detail_response(archive_id)
        if detail_response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        return _build_archive_enrichment_metadata_response(
            detail_response,
            entry_id=entry_id,
            archive_id=archive_id,
            mode=mode,
        )

    async def async_handle_refresh_archive_detail(call: ServiceCall) -> None:
        _entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        refreshed = await manager.async_refresh_archive_detail(
            archive_id,
            operation="service_refresh_archive_detail",
        )
        if refreshed is None:
            raise HomeAssistantError(f"Archive {archive_id} could not be refreshed from Bambuddy")

    async def async_handle_update_archive(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        update_payload: dict[str, Any] = {}
        for field in ("print_name", "tags", "notes", "cost", "status", "failure_reason", "project_id"):
            if field not in call.data:
                continue
            value = call.data.get(field)
            if field == "project_id":
                update_payload[field] = None if value in (None, "", "__NULL__") else int(value)
            elif field == "failure_reason":
                update_payload[field] = None if value in (None, "", "__NULL__") else str(value)
            else:
                update_payload[field] = value

        if not update_payload:
            raise HomeAssistantError("At least one archive field must be provided")

        await _async_apply_archive_update(
            hass,
            manager,
            archive_id=archive_id,
            update_payload=update_payload,
            operation="update_print_history_archive",
        )

        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_update_enrichment_metadata(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        current_detail = manager.build_archive_detail_response(archive_id)
        if current_detail is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        current_archive = current_detail.get("archive", {}) if isinstance(current_detail, dict) else {}
        if not isinstance(current_archive, dict):
            current_archive = {}

        update_payload: dict[str, Any] = {}
        updated_fields: list[str] = []

        if "tag_metadata" in call.data:
            tag_metadata = _parse_service_metadata_object(call.data.get("tag_metadata"), "tag_metadata")
            if "system_tags" not in tag_metadata:
                raise HomeAssistantError("tag_metadata must include the full system_tags list")
            normalized_system_tags = _normalize_system_tag_values(tag_metadata.get("system_tags"))
            merged_tags = ",".join(user_tags(str(current_archive.get("tags", ""))) + normalized_system_tags)
            update_payload["tags"] = merged_tags
            updated_fields.append("tags")

        if "note_metadata" in call.data:
            note_metadata = _parse_service_metadata_object(call.data.get("note_metadata"), "note_metadata")
            if "payload" not in note_metadata:
                raise HomeAssistantError("note_metadata must include the full payload object")
            payload_value = note_metadata.get("payload")
            if isinstance(payload_value, str):
                try:
                    payload_value = json.loads(payload_value)
                except json.JSONDecodeError as error:
                    raise HomeAssistantError("note_metadata.payload must be valid JSON") from error
            if not isinstance(payload_value, dict):
                raise HomeAssistantError("note_metadata.payload must be a JSON object")
            recovery_block = str(note_metadata.get("recovery_block", "")).strip()
            current_note_parts = split_enrichment_notes(str(current_archive.get("notes", "")))
            slot_override_rows = _parse_slot_override_rows(note_metadata.get("slot_overrides", []))
            if slot_override_rows:
                payload_value = dict(payload_value)
                payload_value["slot_overrides"] = slot_override_rows
            elif "slot_overrides" in payload_value and not isinstance(payload_value.get("slot_overrides"), list):
                payload_value = dict(payload_value)
                payload_value.pop("slot_overrides", None)
            update_payload["notes"] = build_enrichment_notes(
                user_notes=str(current_note_parts.get("user_notes", "")),
                recovery_block=recovery_block,
                payload=payload_value,
            )
            updated_fields.append("notes")

        if "slot_overrides" in call.data:
            note_source = update_payload.get("notes", current_archive.get("notes", ""))
            current_note_parts = split_enrichment_notes(str(note_source))
            payload_value = current_note_parts.get("payload")
            if not isinstance(payload_value, dict):
                raise HomeAssistantError("slot_overrides requires an existing hidden note payload or note_metadata.payload")
            slot_override_rows = _parse_slot_override_rows(call.data.get("slot_overrides"))
            payload_value = dict(payload_value)
            if slot_override_rows:
                payload_value["slot_overrides"] = slot_override_rows
            else:
                payload_value.pop("slot_overrides", None)
            update_payload["notes"] = build_enrichment_notes(
                user_notes=str(current_note_parts.get("user_notes", "")),
                recovery_block=str(current_note_parts.get("recovery_block", "")),
                payload=payload_value,
            )
            if "notes" not in updated_fields:
                updated_fields.append("notes")

        if not update_payload:
            raise HomeAssistantError("At least one of tag_metadata, note_metadata, or slot_overrides must be provided")

        await _async_apply_archive_update(
            hass,
            manager,
            archive_id=archive_id,
            update_payload=update_payload,
            operation="update_print_history_archive_enrichment_metadata",
        )

        detail_response = manager.build_archive_detail_response(archive_id)
        if detail_response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response = _build_archive_enrichment_metadata_response(
            detail_response,
            entry_id=entry_id,
            archive_id=archive_id,
            mode="ALL",
        )
        response["updated_fields"] = updated_fields
        return response

    async def async_handle_set_archive_favorite(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        target_favorite = bool(call.data["is_favorite"])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        current_detail = manager.build_archive_detail_response(archive_id)
        if current_detail is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        current_favorite = bool(current_detail.get("archive", {}).get("is_favorite", False))

        started = perf_counter()
        if current_favorite != target_favorite:
            session = aiohttp_client.async_get_clientsession(hass)
            client = BambuddyApiClient(
                session,
                manager.base_url,
                manager.api_key,
                manager.fetch_timeout_seconds,
            )
            try:
                await client.async_toggle_archive_favorite(archive_id)
            except RuntimeError as error:
                raise HomeAssistantError(str(error)) from error

        refreshed = await manager.async_refresh_archive_detail(
            archive_id,
            operation="service_set_archive_favorite",
            extra_details={"target_favorite": target_favorite, "changed": current_favorite != target_favorite},
        )
        if refreshed is None:
            raise HomeAssistantError(f"Archive {archive_id} could not be refreshed from Bambuddy")
        if bool(refreshed.get("is_favorite", False)) != target_favorite:
            raise HomeAssistantError(
                f"Archive {archive_id} favorite state remained {bool(refreshed.get('is_favorite', False))} after requesting {target_favorite}"
            )

        manager.record_mutation(
            operation="set_print_history_archive_favorite",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={"target_favorite": target_favorite, "changed": current_favorite != target_favorite},
        )

        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_append_event(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        try:
            await manager.async_record_archive_event(
                archive_id,
                event_type=str(call.data["event_type"]),
                event_source=str(call.data["event_source"]),
                event_time=call.data.get("event_time"),
                event_status=str(call.data.get("event_status", "")),
                payload=call.data.get("payload", {}),
                derived_from=str(call.data.get("derived_from", "")),
                event_key=call.data.get("event_key"),
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_set_review_state(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        mismatch_flags = call.data.get("mismatch_flags", "")
        if isinstance(mismatch_flags, list):
            mismatch_flags = ",".join(str(item).strip() for item in mismatch_flags if str(item).strip())
        started = perf_counter()
        try:
            await hass.async_add_executor_job(
                lambda: manager.store.upsert_review_state(
                    archive_id,
                    review_status=str(call.data["review_status"]),
                    mismatch_flags=str(mismatch_flags),
                    review_note=str(call.data.get("review_note", "")),
                    reviewed_at=call.data.get("reviewed_at"),
                )
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error
        manager.record_mutation(
            operation="set_review_state",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={"review_status": str(call.data["review_status"]), "mismatch_flags": str(mismatch_flags)},
        )
        manager._notify_listeners()
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_set_primary_photo(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        started = perf_counter()
        try:
            selection = await hass.async_add_executor_job(
                lambda: manager.store.set_primary_photo(
                    archive_id,
                    photo_path=str(call.data.get("photo_path", "")),
                )
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error

        query_changed = manager._recompute_query("set_primary_photo")
        if query_changed:
            manager.browser_revision += 1
        manager.record_mutation(
            operation="set_primary_photo",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "photo_path": selection.get("photo_path", ""),
                "cleared": bool(selection.get("cleared", False)),
            },
        )
        manager._notify_listeners()
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response["primary_photo_selection"] = selection
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_delete_photo(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        photo_path = str(call.data.get("photo_path", "")).strip()
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        if not photo_path:
            raise HomeAssistantError("photo_path is required")

        started = perf_counter()
        session = aiohttp_client.async_get_clientsession(hass)
        client = BambuddyApiClient(
            session,
            manager.base_url,
            manager.api_key,
            manager.fetch_timeout_seconds,
        )
        try:
            await client.async_delete_archive_photo(archive_id, photo_path=photo_path)
            response = await manager.async_refresh_archive_detail(
                archive_id,
                operation="delete_archive_photo",
                extra_details={"photo_path": photo_path},
            )
        except RuntimeError as error:
            raise HomeAssistantError(str(error)) from error

        manager.record_mutation(
            operation="delete_archive_photo",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={"photo_path": photo_path},
        )
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_delete_archive(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        started = perf_counter()
        session = aiohttp_client.async_get_clientsession(hass)
        client = BambuddyApiClient(
            session,
            manager.base_url,
            manager.api_key,
            manager.fetch_timeout_seconds,
        )
        try:
            await client.async_delete_archive(archive_id)
            delete_result = await hass.async_add_executor_job(manager.store.delete_archive, archive_id)
        except (RuntimeError, ValueError) as error:
            raise HomeAssistantError(str(error)) from error

        manager.archives = await hass.async_add_executor_job(manager.store.load_archives)
        deleted_count = max(0, int(delete_result.get("deleted", 0)))
        manager.last_refresh_store_total_count = max(0, len(manager.archives))
        if isinstance(manager.last_refresh_archive_total_count, int):
            manager.last_refresh_archive_total_count = max(
                0,
                manager.last_refresh_archive_total_count - deleted_count,
            )
        query_changed = manager._recompute_query("delete_print_history_archive")
        if query_changed or deleted_count > 0:
            manager.browser_revision += 1
        manager.record_mutation(
            operation="delete_print_history_archive",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "deleted": deleted_count,
                "lineage_deleted": int(delete_result.get("lineage_deleted", 0)),
            },
        )
        await manager._async_sync_options()
        await manager._async_sync_media_review_helper()
        manager._notify_listeners()
        return {
            "success": True,
            CONF_ENTRY_ID: entry_id,
            CONF_ARCHIVE_ID: archive_id,
            "deleted": int(delete_result.get("deleted", 0)),
            "lineage_deleted": int(delete_result.get("lineage_deleted", 0)),
        }

    async def async_handle_set_media_review_state(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        started = perf_counter()
        try:
            media_review_state = await hass.async_add_executor_job(
                lambda: manager.store.upsert_media_review_state(
                    archive_id,
                    review_status=str(call.data["review_status"]),
                    requested_at=call.data.get("requested_at"),
                    started_at=call.data.get("started_at"),
                    completed_at=call.data.get("completed_at"),
                    dismissed_at=call.data.get("dismissed_at"),
                    photo_count=call.data.get("photo_count"),
                    last_action=call.data.get("last_action"),
                    review_note=call.data.get("review_note"),
                )
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error

        manager.record_mutation(
            operation="set_media_review_state",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "review_status": media_review_state.get("review_status", ""),
                "last_action": media_review_state.get("last_action", ""),
                "photo_count": media_review_state.get("photo_count", 0),
            },
        )
        await manager._async_sync_media_review_helper()
        manager._notify_listeners()
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_dismiss_media_review(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        started = perf_counter()
        try:
            media_review_state = await hass.async_add_executor_job(
                lambda: manager.store.upsert_media_review_state(
                    archive_id,
                    review_status="dismissed",
                    dismissed_at=call.data.get("dismissed_at"),
                    last_action="dismissed",
                    review_note=call.data.get("review_note"),
                )
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error

        manager.record_mutation(
            operation="dismiss_media_review",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "review_status": media_review_state.get("review_status", ""),
                "last_action": media_review_state.get("last_action", ""),
            },
        )
        await manager._async_sync_media_review_helper()
        manager._notify_listeners()
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_set_repair_lineage(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        related_archive_id = int(call.data[CONF_RELATED_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        if not await manager.async_ensure_archive_loaded(related_archive_id):
            raise HomeAssistantError(f"Archive {related_archive_id} was not found in the Bambuddy local store")
        started = perf_counter()
        try:
            await hass.async_add_executor_job(
                lambda: manager.store.upsert_repair_lineage(
                    archive_id,
                    related_archive_id,
                    relation_type=str(call.data[CONF_RELATION_TYPE]),
                    note=str(call.data.get("note", "")),
                    created_at=call.data.get("created_at"),
                )
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error
        await manager.async_record_archive_event(
            archive_id,
            event_type="repair_applied",
            event_source="ha_service",
            event_time=call.data.get("created_at"),
            payload={
                "related_archive_id": related_archive_id,
                "relation_type": str(call.data[CONF_RELATION_TYPE]),
            },
            notify=False,
        )
        manager.record_mutation(
            operation="set_repair_lineage",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={"related_archive_id": related_archive_id, "relation_type": str(call.data[CONF_RELATION_TYPE])},
        )
        manager._notify_listeners()
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_delete_repair_lineage(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        related_archive_id = int(call.data[CONF_RELATED_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        started = perf_counter()
        try:
            deleted = await hass.async_add_executor_job(
                manager.store.delete_repair_lineage,
                archive_id,
                related_archive_id,
                str(call.data[CONF_RELATION_TYPE]),
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error
        manager.record_mutation(
            operation="delete_repair_lineage",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "related_archive_id": related_archive_id,
                "relation_type": str(call.data[CONF_RELATION_TYPE]),
                "deleted": deleted,
            },
        )
        manager._notify_listeners()
        return {
            CONF_ENTRY_ID: entry_id,
            CONF_ARCHIVE_ID: archive_id,
            CONF_RELATED_ARCHIVE_ID: related_archive_id,
            CONF_RELATION_TYPE: str(call.data[CONF_RELATION_TYPE]),
            "deleted": deleted,
        }

    async def async_handle_estimate_partial_usage(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        client, error_response = _build_runtime_repair_client(hass, entry_id, manager)
        if error_response is not None:
            error_response["archive_id"] = int(call.data[CONF_ARCHIVE_ID])
            return error_response

        try:
            estimate = await client.async_estimate_partial_usage(
                archive_id=int(call.data[CONF_ARCHIVE_ID]),
                print_status=str(call.data["print_status"]),
                printer_id=call.data.get("printer_id"),
                last_layer_num=call.data.get("last_layer_num"),
                last_progress=call.data.get("last_progress"),
                resolve_spoolman_matches=bool(call.data.get("resolve_spoolman_matches", True)),
                keep_tracking_row=bool(call.data.get("keep_tracking_row", True)),
            )
        except RuntimeError as error:
            return {
                "success": False,
                "entry_id": entry_id,
                "archive_id": int(call.data[CONF_ARCHIVE_ID]),
                "error": "runtime_repair_request_failed",
                "message": str(error),
            }

        return {
            "success": True,
            "entry_id": entry_id,
            "archive_id": int(call.data[CONF_ARCHIVE_ID]),
            "estimate": estimate,
        }

    async def async_handle_repair_archive_from_start(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(archive_id):
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        archive = manager.build_archive_detail_response(archive_id)
        if archive is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")

        started_at = _parse_service_datetime(str(call.data["started_at"]), "started_at")
        duration_seconds, duration_source = _archive_duration_for_runtime_repair(
            archive,
            call.data.get("duration_seconds"),
        )
        completed_at = started_at + timedelta(seconds=duration_seconds)
        created_override = call.data.get("created_at")
        created_at = (
            _parse_service_datetime(str(created_override), "created_at")
            if created_override not in (None, "")
            else started_at
        )

        status = call.data.get("status")
        if not status and bool(call.data.get("set_status_completed", False)):
            status = "completed"

        payload: dict[str, Any] = {
            "archive_id": archive_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "created_at": created_at.isoformat(),
            "dry_run": bool(call.data.get("dry_run", False)),
            "response_detail": str(call.data.get("response_detail", "full")),
        }
        if status:
            payload["status"] = str(status)
        if "failure_reason" in call.data:
            payload["failure_reason"] = call.data.get("failure_reason")

        audit_note = str(call.data.get("audit_note", "")).strip()
        if audit_note:
            payload["audit_note"] = audit_note
        else:
            payload["audit_note"] = (
                f"Start-time runtime repair from HA service using {duration_source}={duration_seconds}s"
            )

        client, error_response = _build_runtime_repair_client(hass, entry_id, manager)
        computed_fields = {
            "started_at": payload["started_at"],
            "completed_at": payload["completed_at"],
            "created_at": payload["created_at"],
            "duration_seconds": duration_seconds,
            "duration_source": duration_source,
        }
        if error_response is not None:
            error_response["archive_id"] = archive_id
            error_response["computed_fields"] = computed_fields
            return error_response

        started = perf_counter()
        try:
            sidecar_response = await client.async_runtime_repair(payload)
        except RuntimeError as error:
            return {
                "success": False,
                "entry_id": entry_id,
                "archive_id": archive_id,
                "error": "runtime_repair_request_failed",
                "message": str(error),
                "computed_fields": computed_fields,
            }

        response: dict[str, Any] = {
            "success": True,
            "entry_id": entry_id,
            "archive_id": archive_id,
            "dry_run": bool(payload["dry_run"]),
            "computed_fields": computed_fields,
            "repair": sidecar_response,
        }

        if not bool(payload["dry_run"]):
            response["archive"] = await manager.async_refresh_archive_detail(
                archive_id,
                operation="repair_archive_from_start",
                extra_details={
                    "started_at": payload["started_at"],
                    "completed_at": payload["completed_at"],
                    "created_at": payload["created_at"],
                    "duration_source": duration_source,
                },
            )

        manager.record_mutation(
            operation="repair_archive_from_start_preview" if bool(payload["dry_run"]) else "repair_archive_from_start",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "duration_seconds": duration_seconds,
                "duration_source": duration_source,
                "dry_run": bool(payload["dry_run"]),
            },
        )
        return response

    async def async_handle_get_restore_workflow(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = _extract_archive_id(call.data.get(CONF_SOURCE_ARCHIVE_ID))
        target_archive_id = _extract_archive_id(call.data.get(CONF_TARGET_ARCHIVE_ID))
        workflow = manager.restore_workflow.get(
            source_archive_id=source_archive_id,
            target_archive_id=target_archive_id,
        )
        if workflow is None:
            return {
                "workflow_state": "idle",
                CONF_ENTRY_ID: entry_id,
                CONF_SOURCE_ARCHIVE_ID: source_archive_id,
                CONF_TARGET_ARCHIVE_ID: target_archive_id,
                CONF_UPLOAD_SESSION_ID: "",
                "pair_key": f"restore:{source_archive_id or 'unknown'}:{target_archive_id or 'pending'}",
            }
        response = workflow.to_response()
        response[CONF_ENTRY_ID] = entry_id
        return response

    async def async_handle_create_replacement_from_upload(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = int(call.data[CONF_SOURCE_ARCHIVE_ID])
        if not await manager.async_ensure_archive_loaded(source_archive_id):
            raise HomeAssistantError(f"Archive {source_archive_id} was not found in the Bambuddy local store")

        upload_session_id = str(call.data[CONF_UPLOAD_SESSION_ID]).strip()
        session = manager.restore_uploads.get_session(upload_session_id)
        if session is None:
            raise HomeAssistantError(f"Unknown or expired upload_session_id: {upload_session_id}")
        if session.source_archive_id != source_archive_id:
            raise HomeAssistantError("Upload session does not belong to the requested source archive")
        if session.entry_id != entry_id:
            raise HomeAssistantError("Upload session belongs to a different Bambuddy entry")

        printer_id = int(call.data.get(CONF_PRINTER_ID, session.printer_id))
        session_client = aiohttp_client.async_get_clientsession(hass)
        client = BambuddyApiClient(
            session_client,
            manager.base_url,
            manager.api_key,
            manager.fetch_timeout_seconds,
        )
        try:
            upload_response = await client.async_upload_archive_replacement(
                printer_id=printer_id,
                file_path=session.file_path,
                file_name=session.file_name,
                mime_type=session.content_type,
            )
        except RuntimeError as error:
            workflow = manager.restore_workflow.set_error(
                entry_id=entry_id,
                source_archive_id=source_archive_id,
                upload_session_id=upload_session_id,
                message=str(error),
            )
            manager.record_mutation(
                operation="create_replacement_archive_failed",
                archive_id=source_archive_id,
                duration_ms=0.0,
                details={CONF_UPLOAD_SESSION_ID: upload_session_id, "error": str(error)},
            )
            manager.browser_revision += 1
            manager._notify_listeners()
            response = workflow.to_response()
            response[CONF_ENTRY_ID] = entry_id
            response["success"] = False
            response["message"] = str(error)
            return response

        target_archive_id = _extract_uploaded_archive_id(upload_response)
        hydration_error = ""
        if target_archive_id is not None:
            try:
                raw_target_archive = await client.async_fetch_archive_detail(target_archive_id)
                projected_target_archive = project_archive(dict(raw_target_archive))
                await hass.async_add_executor_job(manager.store.upsert_archive, projected_target_archive)
                manager.archives = await hass.async_add_executor_job(manager.store.load_archives)
                manager._recompute_query("hydrate_replacement_archive")
            except Exception as error:  # pragma: no cover - best effort hydration after successful upload
                hydration_error = str(error)
                _LOGGER.warning(
                    "Bambuddy replacement archive hydration failed for %s: %s",
                    target_archive_id,
                    error,
                )
        workflow = manager.restore_workflow.set_replacement_created(
            entry_id=entry_id,
            source_archive_id=source_archive_id,
            target_archive_id=target_archive_id,
            upload_session_id=upload_session_id,
            summary={
                "upload": session.to_response(),
                "upload_response": upload_response or {},
                "hydration_error": hydration_error,
            },
        )
        manager.record_mutation(
            operation="create_replacement_archive",
            archive_id=source_archive_id,
            duration_ms=0.0,
            details={
                CONF_UPLOAD_SESSION_ID: upload_session_id,
                CONF_TARGET_ARCHIVE_ID: target_archive_id or 0,
                CONF_PRINTER_ID: printer_id,
            },
        )
        manager.restore_uploads.discard_session(upload_session_id)
        manager.browser_revision += 1
        manager._notify_listeners()

        response = workflow.to_response()
        response[CONF_ENTRY_ID] = entry_id
        response["success"] = True
        response["upload_response"] = upload_response or {}
        return response

    async def async_handle_plan_restore(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = int(call.data[CONF_SOURCE_ARCHIVE_ID])
        target_archive_id = int(call.data[CONF_TARGET_ARCHIVE_ID])
        client, error_response = _build_runtime_repair_client(hass, entry_id, manager)
        if error_response is not None:
            error_response[CONF_SOURCE_ARCHIVE_ID] = source_archive_id
            error_response[CONF_TARGET_ARCHIVE_ID] = target_archive_id
            return error_response

        payload = _normalize_restore_request_payload(call.data, dry_run=True)
        try:
            sidecar_response = await client.async_restore_from(payload)
        except RuntimeError as error:
            workflow = manager.restore_workflow.set_error(entry_id=entry_id, source_archive_id=source_archive_id, message=str(error))
            manager.browser_revision += 1
            manager._notify_listeners()
            response = _workflow_response(entry_id, workflow)
            response["success"] = False
            response["message"] = str(error)
            return response

        workflow = manager.restore_workflow.update(
            entry_id=entry_id,
            source_archive_id=source_archive_id,
            target_archive_id=target_archive_id,
            workflow_state=_extract_restore_workflow_state(sidecar_response, "plan_ready"),
            last_operation="plan",
            summary={"plan": sidecar_response},
            plan_warning_count=len(sidecar_response.get("warnings", [])) if isinstance(sidecar_response.get("warnings"), list) else 0,
            plan_updated_field_count=len(sidecar_response.get("updated_fields", [])) if isinstance(sidecar_response.get("updated_fields"), list) else 0,
        )
        manager.record_mutation(operation="plan_archive_restore", archive_id=source_archive_id, duration_ms=0.0, details={CONF_TARGET_ARCHIVE_ID: target_archive_id})
        manager.browser_revision += 1
        manager._notify_listeners()
        response = _workflow_response(entry_id, workflow)
        response["success"] = True
        response["plan"] = sidecar_response
        return response

    async def async_handle_apply_restore(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = int(call.data[CONF_SOURCE_ARCHIVE_ID])
        target_archive_id = int(call.data[CONF_TARGET_ARCHIVE_ID])
        client, error_response = _build_runtime_repair_client(hass, entry_id, manager)
        if error_response is not None:
            error_response[CONF_SOURCE_ARCHIVE_ID] = source_archive_id
            error_response[CONF_TARGET_ARCHIVE_ID] = target_archive_id
            return error_response

        payload = _normalize_restore_request_payload(call.data, dry_run=False)
        audit_note = str(call.data.get("audit_note", "")).strip()
        if audit_note:
            payload["audit_note"] = audit_note
        try:
            sidecar_response = await client.async_restore_from(payload)
        except RuntimeError as error:
            workflow = manager.restore_workflow.set_error(entry_id=entry_id, source_archive_id=source_archive_id, message=str(error))
            manager.browser_revision += 1
            manager._notify_listeners()
            response = _workflow_response(entry_id, workflow)
            response["success"] = False
            response["message"] = str(error)
            return response

        workflow = manager.restore_workflow.update(
            entry_id=entry_id,
            source_archive_id=source_archive_id,
            target_archive_id=target_archive_id,
            workflow_state=_extract_restore_workflow_state(sidecar_response, "applied_pending_verify"),
            last_operation="apply",
            summary={"apply": sidecar_response},
            plan_updated_field_count=len(sidecar_response.get("updated_fields", [])) if isinstance(sidecar_response.get("updated_fields"), list) else None,
        )
        manager.record_mutation(operation="apply_archive_restore", archive_id=source_archive_id, duration_ms=0.0, details={CONF_TARGET_ARCHIVE_ID: target_archive_id})
        manager.browser_revision += 1
        manager._notify_listeners()
        response = _workflow_response(entry_id, workflow)
        response["success"] = True
        response["apply"] = sidecar_response
        return response

    async def async_handle_verify_restore(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = int(call.data[CONF_SOURCE_ARCHIVE_ID])
        target_archive_id = int(call.data[CONF_TARGET_ARCHIVE_ID])
        client, error_response = _build_runtime_repair_client(hass, entry_id, manager)
        if error_response is not None:
            error_response[CONF_SOURCE_ARCHIVE_ID] = source_archive_id
            error_response[CONF_TARGET_ARCHIVE_ID] = target_archive_id
            return error_response

        payload = _normalize_restore_request_payload(call.data, dry_run=True)
        payload["remove_original"] = False
        try:
            sidecar_response = await client.async_restore_verify(payload)
        except RuntimeError as error:
            workflow = manager.restore_workflow.set_error(entry_id=entry_id, source_archive_id=source_archive_id, message=str(error))
            manager.browser_revision += 1
            manager._notify_listeners()
            response = _workflow_response(entry_id, workflow)
            response["success"] = False
            response["message"] = str(error)
            return response

        verified = bool(sidecar_response.get("verified", False))
        removable = bool(sidecar_response.get("removable", verified))
        blocking_count = _extract_restore_count(sidecar_response, "blocking_difference_count")
        remaining_count = _extract_restore_count(sidecar_response, "remaining_difference_count")
        workflow = manager.restore_workflow.update(
            entry_id=entry_id,
            source_archive_id=source_archive_id,
            target_archive_id=target_archive_id,
            workflow_state="remove_ready" if verified and removable else ("verified_blocked" if blocking_count else "verified_pending"),
            last_operation="verify",
            summary={"verify": sidecar_response},
            verify_remaining_difference_count=remaining_count,
            verify_blocking_difference_count=blocking_count,
            verified=verified,
            removable=removable,
        )
        manager.record_mutation(operation="verify_archive_restore", archive_id=source_archive_id, duration_ms=0.0, details={CONF_TARGET_ARCHIVE_ID: target_archive_id, "verified": verified})
        manager.browser_revision += 1
        manager._notify_listeners()
        response = _workflow_response(entry_id, workflow)
        response["success"] = True
        response["verify"] = sidecar_response
        return response

    async def async_handle_finish_restore(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = int(call.data[CONF_SOURCE_ARCHIVE_ID])
        target_archive_id = int(call.data[CONF_TARGET_ARCHIVE_ID])
        attempt_reenrich = bool(call.data.get("attempt_reenrich", True))
        retain_original = bool(call.data.get("retain_original", True))

        target_detail = await hass.async_add_executor_job(manager.store.load_archive, target_archive_id)
        if target_detail is None:
            target_detail = await manager.async_refresh_archive_detail(target_archive_id, operation="finish_restore_refresh_target")
        enrichment_status = _extract_enrichment_status(target_detail)
        if attempt_reenrich and enrichment_status not in {"complete", "near complete", "mostly complete", "partially complete"}:
            await hass.services.async_call(
                "script",
                "reenrich_print_history_archive",
                {"archive_id": str(target_archive_id)},
                blocking=False,
            )
            target_detail = await manager.async_refresh_archive_detail(target_archive_id, operation="finish_restore_refresh_target")
            enrichment_status = _extract_enrichment_status(target_detail)

        if enrichment_status not in {"complete", "near complete", "mostly complete", "partially complete"}:
            workflow = manager.restore_workflow.update(
                entry_id=entry_id,
                source_archive_id=source_archive_id,
                target_archive_id=target_archive_id,
                workflow_state="finalize_pending_reenrich",
                last_operation="finish",
                enrichment_status=enrichment_status or "missing",
                summary={"message": "Target archive enrichment is not complete. Run re-enrich before cleanup or keep the original archive."},
            )
            manager.browser_revision += 1
            manager._notify_listeners()
            response = _workflow_response(entry_id, workflow)
            response["success"] = True
            response["message"] = "Target archive enrichment is not complete. Run re-enrich before cleanup or keep the original archive."
            return response

        verify_response = await async_handle_verify_restore(
            ServiceCall(
                {
                    CONF_ENTRY_ID: entry_id,
                    CONF_SOURCE_ARCHIVE_ID: source_archive_id,
                    CONF_TARGET_ARCHIVE_ID: target_archive_id,
                    "field_groups": call.data.get("field_groups", []),
                    "exclude_tags": call.data.get("exclude_tags", []),
                    "include_tags": call.data.get("include_tags", []),
                }
            )
        )
        workflow = manager.restore_workflow.get(source_archive_id=source_archive_id)
        if workflow is None:
            raise HomeAssistantError("Restore workflow state was not found after verification")

        if workflow.verified and retain_original:
            workflow = manager.restore_workflow.update(
                entry_id=entry_id,
                source_archive_id=source_archive_id,
                target_archive_id=target_archive_id,
                workflow_state="completed_original_retained",
                last_operation="finish",
                enrichment_status=enrichment_status,
                summary={"verify": verify_response.get("verify", {}), "message": "Restore verified; original archive retained."},
                verified=True,
                removable=False,
            )
            manager.browser_revision += 1
            manager._notify_listeners()

        response = _workflow_response(entry_id, workflow)
        response["success"] = True
        response["verify"] = verify_response.get("verify", {})
        response["message"] = "Restore verified and original archive retained." if retain_original and workflow.verified else "Restore ready for original removal."
        return response

    async def async_handle_remove_restored_source(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = int(call.data[CONF_SOURCE_ARCHIVE_ID])
        target_archive_id = int(call.data[CONF_TARGET_ARCHIVE_ID])
        workflow = manager.restore_workflow.get(source_archive_id=source_archive_id, target_archive_id=target_archive_id)
        if workflow is None or workflow.workflow_state != "remove_ready":
            raise HomeAssistantError("Original removal is only allowed when the workflow state is remove_ready")

        client, error_response = _build_runtime_repair_client(hass, entry_id, manager)
        if error_response is not None:
            error_response[CONF_SOURCE_ARCHIVE_ID] = source_archive_id
            error_response[CONF_TARGET_ARCHIVE_ID] = target_archive_id
            return error_response

        payload = _normalize_restore_request_payload(call.data, dry_run=False)
        payload["remove_original"] = True
        try:
            sidecar_response = await client.async_restore_verify(payload)
        except RuntimeError as error:
            workflow = manager.restore_workflow.set_error(entry_id=entry_id, source_archive_id=source_archive_id, message=str(error))
            manager.browser_revision += 1
            manager._notify_listeners()
            response = _workflow_response(entry_id, workflow)
            response["success"] = False
            response["message"] = str(error)
            return response

        manager.restore_workflow.clear(source_archive_id=source_archive_id, target_archive_id=target_archive_id)
        manager.record_mutation(operation="remove_restored_source_archive", archive_id=source_archive_id, duration_ms=0.0, details={CONF_TARGET_ARCHIVE_ID: target_archive_id})
        manager.browser_revision += 1
        manager._notify_listeners()
        return {
            "success": True,
            CONF_ENTRY_ID: entry_id,
            CONF_SOURCE_ARCHIVE_ID: source_archive_id,
            CONF_TARGET_ARCHIVE_ID: target_archive_id,
            "removed": bool(sidecar_response.get("source_removed", True)),
            "verify": sidecar_response,
        }

    async def async_handle_clear_restore(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        source_archive_id = _extract_archive_id(call.data.get(CONF_SOURCE_ARCHIVE_ID))
        target_archive_id = _extract_archive_id(call.data.get(CONF_TARGET_ARCHIVE_ID))
        workflow = manager.restore_workflow.get(source_archive_id=source_archive_id, target_archive_id=target_archive_id)
        upload_session_id = workflow.upload_session_id if workflow is not None else ""
        if upload_session_id:
            manager.restore_uploads.discard_session(upload_session_id)
        cleared = manager.restore_workflow.clear(source_archive_id=source_archive_id, target_archive_id=target_archive_id)
        manager.browser_revision += 1
        manager._notify_listeners()
        return {
            "success": True,
            CONF_ENTRY_ID: entry_id,
            CONF_SOURCE_ARCHIVE_ID: source_archive_id,
            CONF_TARGET_ARCHIVE_ID: target_archive_id,
            "cleared": cleared,
        }

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_PRINT_HISTORY_BROWSER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_PRINT_HISTORY_BROWSER,
            async_handle_refresh,
            schema=SERVICE_REFRESH_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_QUERY_PRINT_HISTORY_BROWSER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_QUERY_PRINT_HISTORY_BROWSER,
            async_handle_query,
            schema=SERVICE_QUERY_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL,
            async_handle_detail,
            schema=SERVICE_DETAIL_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA,
            async_handle_get_enrichment_metadata,
            schema=SERVICE_ENRICHMENT_METADATA_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE,
            async_handle_update_archive,
            schema=SERVICE_UPDATE_ARCHIVE_SCHEMA,
                supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA,
            async_handle_update_enrichment_metadata,
            schema=SERVICE_UPDATE_ENRICHMENT_METADATA_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE,
            async_handle_set_archive_favorite,
            schema=SERVICE_SET_ARCHIVE_FAVORITE_SCHEMA,
                supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_DETAIL):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_DETAIL,
            async_handle_refresh_archive_detail,
            schema=SERVICE_DETAIL_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_APPEND_PRINT_HISTORY_EVENT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_APPEND_PRINT_HISTORY_EVENT,
            async_handle_append_event,
            schema=SERVICE_APPEND_EVENT_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRINT_HISTORY_REVIEW_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRINT_HISTORY_REVIEW_STATE,
            async_handle_set_review_state,
            schema=SERVICE_REVIEW_STATE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO,
            async_handle_set_primary_photo,
            schema=SERVICE_PRIMARY_PHOTO_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_PRINT_HISTORY_PHOTO):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_PRINT_HISTORY_PHOTO,
            async_handle_delete_photo,
            schema=SERVICE_DELETE_PHOTO_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_PRINT_HISTORY_ARCHIVE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_PRINT_HISTORY_ARCHIVE,
            async_handle_delete_archive,
            schema=SERVICE_DELETE_ARCHIVE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRINT_HISTORY_MEDIA_REVIEW_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRINT_HISTORY_MEDIA_REVIEW_STATE,
            async_handle_set_media_review_state,
            schema=SERVICE_MEDIA_REVIEW_STATE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DISMISS_PRINT_HISTORY_MEDIA_REVIEW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DISMISS_PRINT_HISTORY_MEDIA_REVIEW,
            async_handle_dismiss_media_review,
            schema=SERVICE_DETAIL_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE,
            async_handle_set_repair_lineage,
            schema=SERVICE_REPAIR_LINEAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE,
            async_handle_delete_repair_lineage,
            schema=SERVICE_REPAIR_LINEAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ESTIMATE_PARTIAL_USAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ESTIMATE_PARTIAL_USAGE,
            async_handle_estimate_partial_usage,
            schema=SERVICE_ESTIMATE_PARTIAL_USAGE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REPAIR_PRINT_HISTORY_ARCHIVE_FROM_START):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REPAIR_PRINT_HISTORY_ARCHIVE_FROM_START,
            async_handle_repair_archive_from_start,
            schema=SERVICE_REPAIR_ARCHIVE_FROM_START_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_GET_PRINT_HISTORY_ARCHIVE_RESTORE_WORKFLOW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PRINT_HISTORY_ARCHIVE_RESTORE_WORKFLOW,
            async_handle_get_restore_workflow,
            schema=SERVICE_GET_RESTORE_WORKFLOW_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_PRINT_HISTORY_ARCHIVE_REPLACEMENT_FROM_UPLOAD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CREATE_PRINT_HISTORY_ARCHIVE_REPLACEMENT_FROM_UPLOAD,
            async_handle_create_replacement_from_upload,
            schema=SERVICE_CREATE_REPLACEMENT_FROM_UPLOAD_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_PLAN_PRINT_HISTORY_ARCHIVE_RESTORE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PLAN_PRINT_HISTORY_ARCHIVE_RESTORE,
            async_handle_plan_restore,
            schema=SERVICE_RESTORE_OPERATION_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_PRINT_HISTORY_ARCHIVE_RESTORE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_APPLY_PRINT_HISTORY_ARCHIVE_RESTORE,
            async_handle_apply_restore,
            schema=SERVICE_RESTORE_OPERATION_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_VERIFY_PRINT_HISTORY_ARCHIVE_RESTORE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_VERIFY_PRINT_HISTORY_ARCHIVE_RESTORE,
            async_handle_verify_restore,
            schema=SERVICE_RESTORE_OPERATION_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_FINISH_PRINT_HISTORY_ARCHIVE_RESTORE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FINISH_PRINT_HISTORY_ARCHIVE_RESTORE,
            async_handle_finish_restore,
            schema=SERVICE_RESTORE_OPERATION_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REMOVE_PRINT_HISTORY_RESTORED_SOURCE_ARCHIVE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REMOVE_PRINT_HISTORY_RESTORED_SOURCE_ARCHIVE,
            async_handle_remove_restored_source,
            schema=SERVICE_RESTORE_OPERATION_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_PRINT_HISTORY_ARCHIVE_RESTORE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_PRINT_HISTORY_ARCHIVE_RESTORE,
            async_handle_clear_restore,
            schema=SERVICE_CLEAR_RESTORE_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    manager = PrintHistoryBrowserManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_MANAGER: manager,
        DATA_RESTORE_UPLOADS: manager.restore_uploads,
        DATA_RESTORE_WORKFLOW: manager.restore_workflow,
    }
    _LOGGER.info("Setting up Bambuddy entry %s", entry.entry_id)
    await manager.async_initialize()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: PrintHistoryBrowserManager = hass.data[DOMAIN][entry.entry_id][DATA_MANAGER]
        await manager.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Unloaded Bambuddy entry %s", entry.entry_id)
    return unload_ok