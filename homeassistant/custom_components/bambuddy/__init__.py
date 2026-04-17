from __future__ import annotations

import base64
import binascii
import logging
from time import perf_counter
from typing import Any

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
    ARCHIVE_VIEWER_CAPTURE_UPLOAD_URL,
    ARCHIVE_VIEWER_CAPABILITIES_URL,
    ARCHIVE_VIEWER_GCODE_URL,
    DATA_MANAGER,
    DATA_RESTORE_UPLOADS,
    DATA_RESTORE_WORKFLOW,
    DOMAIN,
    PLATFORMS,
    SERVICE_APPEND_PRINT_HISTORY_EVENT,
    CONF_RUNTIME_REPAIR_BASE_URL,
    CONF_RUNTIME_REPAIR_TOKEN,
    SERVICE_DELETE_PRINT_HISTORY_PHOTO,
    SERVICE_DISMISS_PRINT_HISTORY_MEDIA_REVIEW,
    CONF_FETCH_TIMEOUT_SECONDS,
    SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE,
    SERVICE_ESTIMATE_PARTIAL_USAGE,
    SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL,
    SERVICE_GET_PRINT_HISTORY_ARCHIVE_RESTORE_WORKFLOW,
    SERVICE_QUERY_PRINT_HISTORY_BROWSER,
    SERVICE_REFRESH_PRINT_HISTORY_BROWSER,
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
    RESTORE_UPLOAD_DISCOVER_URL,
)
from .manager import PrintHistoryBrowserManager
from .print_history.query import project_archive


CONF_ENTRY_ID = "entry_id"
CONF_ARCHIVE_ID = "archive_id"
CONF_SOURCE_ARCHIVE_ID = "source_archive_id"
CONF_TARGET_ARCHIVE_ID = "target_archive_id"
CONF_PRINTER_ID = "printer_id"
CONF_UPLOAD_SESSION_ID = "upload_session_id"
CONF_RELATED_ARCHIVE_ID = "related_archive_id"
CONF_RELATION_TYPE = "relation_type"


_LOGGER = logging.getLogger(__name__)

WS_TYPE_PRINT_HISTORY_QUERY = "bambuddy/print_history_query"
WS_TYPE_PRINT_HISTORY_UPLOAD_PHOTO = "bambuddy/print_history_upload_photo"
WS_TYPE_PRINT_HISTORY_ARCHIVE_VIEWER = "bambuddy/print_history_archive_viewer"
MAX_MANUAL_PHOTO_UPLOAD_BYTES = 8 * 1024 * 1024
DATA_HTTP_VIEW_REGISTERED = f"{DOMAIN}_restore_upload_view_registered"


def _basename(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def _resolve_uploaded_photo_path(archive: dict[str, Any] | None, requested_name: str) -> str:
    if not isinstance(archive, dict):
        return ""

    requested_path = str(requested_name or "").strip()
    requested_basename = _basename(requested_path)
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

    for candidate in candidates:
        if candidate and candidate == requested_path:
            return candidate
    for candidate in candidates:
        if candidate and _basename(candidate) == requested_basename:
            return candidate
    return requested_path


def _strip_entry_id(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {CONF_ENTRY_ID, "id", "type"}}


SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): str})
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
        file_part = None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                file_part = part
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
        if file_part is None or not getattr(file_part, "filename", ""):
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

        manager.restore_uploads.cleanup_expired()
        session_id, file_path, normalized_file_name = manager.restore_uploads.prepare_session_file_path(file_part.filename)
        size_bytes = 0
        try:
            with file_path.open("wb") as handle:
                while True:
                    chunk = await file_part.read_chunk(size=64 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > manager.restore_uploads.max_upload_bytes:
                        raise HomeAssistantError(
                            f"Upload payload exceeds the configured limit of {manager.restore_uploads.max_upload_bytes} bytes"
                        )
                    handle.write(chunk)

            if size_bytes <= 0:
                raise HomeAssistantError("Upload payload is empty")

            session = manager.restore_uploads.finalize_session(
                session_id=session_id,
                entry_id=resolved_entry_id,
                source_archive_id=source_archive_id,
                printer_id=printer_id,
                file_name=normalized_file_name,
                content_type=str(file_part.headers.get("Content-Type", "application/octet-stream")),
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


class ArchiveViewerCapabilitiesView(HomeAssistantView):
    url = ARCHIVE_VIEWER_CAPABILITIES_URL
    name = "api:bambuddy:print-history:archive-viewer:capabilities"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        resolved = await _resolve_archive_viewer_request(request)
        if isinstance(resolved, web.Response):
            return resolved

        _hass, entry_id, archive_id, _manager, client = resolved
        try:
            payload = await client.async_fetch_archive_capabilities(archive_id)
        except RuntimeError as error:
            return web.json_response(
                {"success": False, "error": "capabilities_fetch_failed", "message": str(error)},
                status=502,
            )

        response_payload = dict(payload)
        response_payload[CONF_ENTRY_ID] = entry_id
        response_payload[CONF_ARCHIVE_ID] = archive_id
        return web.json_response(response_payload)


class ArchiveViewerGcodeView(HomeAssistantView):
    url = ARCHIVE_VIEWER_GCODE_URL
    name = "api:bambuddy:print-history:archive-viewer:gcode"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
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


class ArchiveViewerCaptureUploadView(HomeAssistantView):
    url = ARCHIVE_VIEWER_CAPTURE_UPLOAD_URL
    name = "api:bambuddy:print-history:archive-viewer:capture-upload"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        resolved = await _resolve_archive_viewer_request(request)
        if isinstance(resolved, web.Response):
            return resolved

        hass, entry_id, archive_id, manager, client = resolved
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response(
                {"success": False, "error": "invalid_json", "message": "Request body must be valid JSON."},
                status=400,
            )

        file_name = str((payload or {}).get("file_name", "")).strip()
        mime_type = str((payload or {}).get("mime_type", "")).strip().lower()
        content_base64 = str((payload or {}).get("content_base64", "")).strip()
        use_as_primary = bool((payload or {}).get("use_as_primary", False))

        if not file_name:
            return web.json_response(
                {"success": False, "error": "file_name_required", "message": "file_name is required."},
                status=400,
            )
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            return web.json_response(
                {
                    "success": False,
                    "error": "unsupported_mime_type",
                    "message": "Capture upload only supports PNG, JPEG, or WebP images.",
                },
                status=400,
            )

        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error):
            return web.json_response(
                {"success": False, "error": "invalid_base64", "message": "content_base64 is not valid base64."},
                status=400,
            )
        if not content:
            return web.json_response(
                {"success": False, "error": "empty_payload", "message": "Capture payload is empty."},
                status=400,
            )
        if len(content) > MAX_MANUAL_PHOTO_UPLOAD_BYTES:
            return web.json_response(
                {
                    "success": False,
                    "error": "payload_too_large",
                    "message": f"Capture payload exceeds the {MAX_MANUAL_PHOTO_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
                },
                status=400,
            )

        if not await manager.async_ensure_archive_loaded(archive_id):
            return web.json_response(
                {
                    "success": False,
                    "error": "archive_not_found",
                    "message": f"Archive {archive_id} was not found in the Bambuddy local store.",
                },
                status=404,
            )

        upload_response: dict[str, Any] | None = None
        try:
            upload_response = await client.async_upload_archive_photo(
                archive_id,
                file_name=file_name,
                mime_type=mime_type,
                content=content,
            )
            refreshed_archive = await manager.async_refresh_archive_detail(
                archive_id,
                operation="upload_archive_viewer_capture",
                extra_details={
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "byte_count": len(content),
                    "use_as_primary": use_as_primary,
                },
            )
        except RuntimeError as error:
            return web.json_response(
                {"success": False, "error": "upload_failed", "message": str(error)},
                status=502,
            )

        if refreshed_archive is None:
            return web.json_response(
                {
                    "success": False,
                    "error": "archive_refresh_failed",
                    "message": f"Archive {archive_id} could not be refreshed after upload.",
                },
                status=500,
            )

        uploaded_photo_path = _resolve_uploaded_photo_path(refreshed_archive, file_name)
        primary_photo_selection: dict[str, Any] | None = None

        if use_as_primary and uploaded_photo_path:
            try:
                primary_photo_selection = await hass.async_add_executor_job(
                    lambda: manager.store.set_primary_photo(archive_id, photo_path=uploaded_photo_path)
                )
            except ValueError as error:
                return web.json_response(
                    {"success": False, "error": "primary_photo_failed", "message": str(error)},
                    status=400,
                )
            query_changed = manager._recompute_query("upload_archive_viewer_capture_primary_photo")
            if query_changed:
                manager.browser_revision += 1
            manager.record_mutation(
                operation="upload_archive_viewer_capture_primary_photo",
                archive_id=archive_id,
                duration_ms=0.0,
                details={"photo_path": uploaded_photo_path},
            )
            manager._notify_listeners()

        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            return web.json_response(
                {
                    "success": False,
                    "error": "archive_not_found",
                    "message": f"Archive {archive_id} was not found in the Bambuddy local store.",
                },
                status=404,
            )

        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        response["upload"] = {
            "file_name": file_name,
            "mime_type": mime_type,
            "byte_count": len(content),
            "use_as_primary": use_as_primary,
        }
        response["uploaded_photo_path"] = uploaded_photo_path
        if upload_response:
            response["upload_response"] = upload_response
        if primary_photo_selection is not None:
            response["primary_photo_selection"] = primary_photo_selection
        return web.json_response(response)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if not hass.data.get(DATA_HTTP_VIEW_REGISTERED):
        hass.http.register_view(ReplacementArchiveDiscoverView())
        hass.http.register_view(ArchiveViewerCapabilitiesView())
        hass.http.register_view(ArchiveViewerGcodeView())
        hass.http.register_view(ArchiveViewerCaptureUploadView())
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

            response = manager.build_archive_detail_response(archive_id)
            if response is None:
                raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
            response[CONF_ENTRY_ID] = entry_id
            response[CONF_ARCHIVE_ID] = archive_id
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

    async def async_handle_refresh(call: ServiceCall) -> None:
        entry_id = call.data.get(CONF_ENTRY_ID)
        managers = []
        if entry_id:
            entry_data = hass.data[DOMAIN].get(entry_id)
            if entry_data is not None:
                managers.append(entry_data[DATA_MANAGER])
        else:
            managers.extend(data[DATA_MANAGER] for data in hass.data[DOMAIN].values())

        for manager in managers:
            await manager.async_request_refresh("service", delay_seconds=1.0)

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
        if attempt_reenrich and enrichment_status not in {"complete", "partial"}:
            await hass.services.async_call(
                "script",
                "reenrich_print_history_archive",
                {"archive_id": str(target_archive_id)},
                blocking=False,
            )
            target_detail = await manager.async_refresh_archive_detail(target_archive_id, operation="finish_restore_refresh_target")
            enrichment_status = _extract_enrichment_status(target_detail)

        if enrichment_status not in {"complete", "partial"}:
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