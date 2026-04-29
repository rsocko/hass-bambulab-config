from __future__ import annotations

import asyncio
import base64
import importlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
HOMEASSISTANT_ROOT = REPO_ROOT / "homeassistant"


def test_archive_photo_upload_backend_normalizes_transport_errors() -> None:
    api_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "api.py").read_text("utf-8")
    init_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "__init__.py").read_text("utf-8")
    const_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "const.py").read_text("utf-8")
    sensor_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "sensor.py").read_text("utf-8")

    assert "from uuid import uuid4" in api_content
    assert "except (ClientError, asyncio.TimeoutError, OSError) as error:" in api_content
    assert "Bambuddy photo upload request failed:" in api_content
    assert "Unhandled error during Bambuddy archive photo upload" in init_content
    assert 'connection.send_error(msg["id"], "upload_failed", message)' in init_content
    assert 'ENTITY_TEMP_STORAGE = "bambuddy_print_history_temp_storage"' in const_content
    assert 'name="Bambuddy Print History Temp Storage"' in sensor_content


def test_archive_pick_image_view_is_browser_loadable_without_auth() -> None:
    init_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "__init__.py").read_text("utf-8")

    assert 'class ArchivePickImageView(HomeAssistantView):' in init_content
    assert 'name = "api:bambuddy:print-history:archive:pick-image"' in init_content
    assert 'requires_auth = False' in init_content


def test_print_history_api_docs_landing_is_registered() -> None:
    init_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "__init__.py").read_text("utf-8")
    const_content = (HOMEASSISTANT_ROOT / "custom_components" / "bambuddy" / "const.py").read_text("utf-8")

    assert 'PRINT_HISTORY_API_DOCS_URL = "/api/bambuddy/print-history/docs"' in const_content
    assert 'class PrintHistoryApiDocsView(HomeAssistantView):' in init_content
    assert 'name = "api:bambuddy:print-history:docs"' in init_content
    assert 'requires_auth = True' in init_content
    assert 'hass.http.register_view(PrintHistoryApiDocsView())' in init_content


def _install_homeassistant_stubs() -> None:
    voluptuous_module = ModuleType("voluptuous")
    aiohttp_module = ModuleType("aiohttp")
    homeassistant_module = ModuleType("homeassistant")
    components_module = ModuleType("homeassistant.components")
    http_module = ModuleType("homeassistant.components.http")
    websocket_api_module = ModuleType("homeassistant.components.websocket_api")
    config_entries_module = ModuleType("homeassistant.config_entries")
    const_module = ModuleType("homeassistant.const")
    core_module = ModuleType("homeassistant.core")
    exceptions_module = ModuleType("homeassistant.exceptions")
    helpers_module = ModuleType("homeassistant.helpers")
    aiohttp_client_module = ModuleType("homeassistant.helpers.aiohttp_client")
    helpers_event_module = ModuleType("homeassistant.helpers.event")
    util_module = ModuleType("homeassistant.util")
    util_dt_module = ModuleType("homeassistant.util.dt")

    class ConfigEntry:
        def __init__(self, entry_id: str = "entry-1", data: dict | None = None, options: dict | None = None) -> None:
            self.entry_id = entry_id
            self.data = data or {}
            self.options = options or {}

        def add_update_listener(self, listener):
            return listener

        def async_on_unload(self, callback):
            return callback

    class Platform:
        SENSOR = "sensor"

    class HomeAssistant:
        pass

    class ServiceCall:
        def __init__(self, data=None) -> None:
            self.data = data or {}

    class SupportsResponse:
        ONLY = "only"
        OPTIONAL = "optional"

    class Event:
        def __init__(self, data=None) -> None:
            self.data = data or {}

    class HomeAssistantError(Exception):
        pass

    class ClientError(Exception):
        pass

    class ClientResponseError(Exception):
        def __init__(self, status: int = 0) -> None:
            self.status = status
            super().__init__(status)

    class ClientSession:
        pass

    class ClientTimeout:
        def __init__(self, total=None) -> None:
            self.total = total

    class FormData:
        def __init__(self) -> None:
            self.fields = []

        def add_field(self, *args, **kwargs) -> None:
            self.fields.append((args, kwargs))

    class HomeAssistantView:
        url = ""
        name = ""
        requires_auth = True

    class _WebNamespace:
        class Request:
            pass

        class Response:
            def __init__(self, text=None, content_type=None, charset=None, status=200):
                self.text = text
                self.content_type = content_type
                self.charset = charset
                self.status = status

        @staticmethod
        def json_response(payload, status=200):
            return {"payload": payload, "status": status}

    class ActiveConnection:
        def __init__(self) -> None:
            self.errors: list[tuple[int, str, str]] = []
            self.results: list[tuple[int, dict]] = []

        def send_error(self, message_id: int, code: str, message: str) -> None:
            self.errors.append((message_id, code, message))

        def send_result(self, message_id: int, result: dict) -> None:
            self.results.append((message_id, result))

    voluptuous_module.Schema = lambda value: value
    voluptuous_module.Required = lambda key, default=None: key
    voluptuous_module.Optional = lambda key, default=None: key
    voluptuous_module.Any = lambda *validators: validators
    voluptuous_module.Coerce = lambda type_: type_
    voluptuous_module.In = lambda values: values

    aiohttp_module.ClientError = ClientError
    aiohttp_module.ClientResponseError = ClientResponseError
    aiohttp_module.ClientSession = ClientSession
    aiohttp_module.ClientTimeout = ClientTimeout
    aiohttp_module.FormData = FormData
    aiohttp_module.web = _WebNamespace

    config_entries_module.ConfigEntry = ConfigEntry
    const_module.Platform = Platform
    core_module.HomeAssistant = HomeAssistant
    core_module.ServiceCall = ServiceCall
    core_module.ServiceResponse = dict
    core_module.SupportsResponse = SupportsResponse
    core_module.Event = Event
    core_module.callback = lambda func: func
    exceptions_module.HomeAssistantError = HomeAssistantError
    aiohttp_client_module.async_get_clientsession = lambda hass: object()
    helpers_event_module.async_track_state_change_event = lambda *args, **kwargs: (lambda: None)
    helpers_event_module.async_track_time_interval = lambda *args, **kwargs: (lambda: None)
    util_dt_module.DEFAULT_TIME_ZONE = timezone.utc
    util_dt_module.utcnow = lambda: datetime(2026, 4, 10, tzinfo=timezone.utc)
    websocket_api_module.ActiveConnection = ActiveConnection
    websocket_api_module.websocket_command = lambda _schema: (lambda func: func)
    websocket_api_module.async_response = lambda func: func
    websocket_api_module.async_register_command = lambda hass, handler: getattr(hass, "websocket_handlers", []).append(handler)
    helpers_module.aiohttp_client = aiohttp_client_module
    util_module.dt = util_dt_module
    http_module.HomeAssistantView = HomeAssistantView

    homeassistant_module.components = components_module
    homeassistant_module.config_entries = config_entries_module
    homeassistant_module.const = const_module
    homeassistant_module.core = core_module
    homeassistant_module.helpers = helpers_module
    homeassistant_module.util = util_module
    components_module.websocket_api = websocket_api_module
    components_module.http = http_module

    sys.modules["voluptuous"] = voluptuous_module
    sys.modules["aiohttp"] = aiohttp_module
    sys.modules["homeassistant"] = homeassistant_module
    sys.modules["homeassistant.components"] = components_module
    sys.modules["homeassistant.components.http"] = http_module
    sys.modules["homeassistant.components.websocket_api"] = websocket_api_module
    sys.modules["homeassistant.config_entries"] = config_entries_module
    sys.modules["homeassistant.const"] = const_module
    sys.modules["homeassistant.core"] = core_module
    sys.modules["homeassistant.exceptions"] = exceptions_module
    sys.modules["homeassistant.helpers"] = helpers_module
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_module
    sys.modules["homeassistant.helpers.event"] = helpers_event_module
    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = util_dt_module


def _purge_component_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "custom_components.bambuddy" or module_name.startswith("custom_components.bambuddy."):
            sys.modules.pop(module_name, None)


def _import_component_modules():
    _install_homeassistant_stubs()
    _purge_component_modules()

    const_module = importlib.import_module("custom_components.bambuddy.const")
    query_module = importlib.import_module("custom_components.bambuddy.print_history.query")
    manager_module = importlib.import_module("custom_components.bambuddy.manager")
    init_module = importlib.import_module("custom_components.bambuddy.__init__")
    return const_module, query_module, manager_module, init_module


class FakeState:
    def __init__(self, state: str) -> None:
        self.state = state


class FakeStates:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = {key: FakeState(value) for key, value in mapping.items()}

    def get(self, entity_id: str):
        return self._mapping.get(entity_id)


class FakeServices:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], dict[str, object]] = {}
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._handlers

    def async_register(self, domain: str, service: str, handler, schema=None, supports_response=None) -> None:
        self._handlers[(domain, service)] = {
            "handler": handler,
            "schema": schema,
            "supports_response": supports_response,
        }

    async def async_call(self, domain: str, service: str, data=None, blocking=False) -> None:
        self.calls.append((domain, service, data or {}))

    def handler(self, domain: str, service: str):
        return self._handlers[(domain, service)]["handler"]


class FakeBus:
    def async_listen(self, *_args, **_kwargs):
        return lambda: None


class FakeHttp:
    def __init__(self) -> None:
        self.views: list[object] = []

    def register_view(self, view) -> None:
        self.views.append(view)


class FakeApiClient:
    archives: list[dict] = []
    printers: list[dict] = []
    projects: list[dict] = []
    archive_stats: dict[str, object] = {}
    failure_analysis: dict[str, object] = {}
    last_fetch_archives_kwargs: dict[str, object] = {}
    uploaded_photos: list[dict[str, object]] = []
    uploaded_source_3mfs: list[dict[str, object]] = []
    timelapse_info_requests: list[int] = []
    timelapse_thumbnail_requests: list[dict[str, int]] = []
    processed_timelapses: list[dict[str, object]] = []
    uploaded_replacements: list[dict[str, object]] = []
    deleted_archives: list[int] = []
    updated_archives: list[dict[str, object]] = []
    toggled_favorites: list[int] = []
    archive_slicer_tokens: list[int] = []
    source_slicer_tokens: list[int] = []
    related_requests: list[dict[str, object]] = []
    compare_requests: list[list[int]] = []

    def __init__(self, _session, _base_url: str, _api_key: str, _timeout_seconds: int) -> None:
        pass

    async def async_fetch_archives(
        self,
        *,
        limit: int,
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict[str, object]]:
        type(self).last_fetch_archives_kwargs = {
            "limit": limit,
            "date_from": date_from,
            "date_to": date_to,
        }
        return [dict(item) for item in self.archives[:limit]]

    async def async_fetch_printers(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.printers]

    async def async_fetch_archive_detail(self, archive_id: int) -> dict[str, object]:
        for item in self.archives:
            if int(item.get("id", 0)) == int(archive_id):
                return dict(item)
        raise RuntimeError("Bambuddy returned HTTP 404")

    async def async_fetch_archive_similar(self, archive_id: int, *, limit: int = 10) -> list[dict[str, object]]:
        normalized_archive_id = int(archive_id)
        type(self).related_requests.append({"archive_id": normalized_archive_id, "limit": int(limit)})
        candidates: list[dict[str, object]] = []
        for item in self.archives:
            candidate_id = int(item.get("id", 0))
            if candidate_id == normalized_archive_id:
                continue
            match_score = 100 if item.get("print_name") == "Hueforge Batman" else 50
            candidates.append(
                {
                    "archive": dict(item),
                    "match_reason": "Same print name" if match_score >= 100 else "Same filament type",
                    "match_score": match_score,
                }
            )
        return candidates[: max(1, int(limit))]

    async def async_compare_archives(self, archive_ids: list[int]) -> dict[str, object]:
        normalized_ids = [int(value) for value in archive_ids]
        type(self).compare_requests.append(list(normalized_ids))
        archives = [dict(item) for item in self.archives if int(item.get("id", 0)) in normalized_ids]
        archives.sort(key=lambda item: normalized_ids.index(int(item.get("id", 0))))
        statuses = [str(item.get("status") or "") for item in archives]
        return {
            "archives": archives,
            "comparison": [
                {
                    "field": "status",
                    "label": "Status",
                    "values": statuses,
                    "has_difference": len(set(statuses)) > 1,
                },
                {
                    "field": "layer_height",
                    "label": "Layer Height",
                    "values": [item.get("layer_height") for item in archives],
                    "unit": "mm",
                    "has_difference": len({item.get("layer_height") for item in archives}) > 1,
                },
            ],
            "differences": [
                {"field": "status", "label": "Status"},
            ],
            "success_correlation": {
                "has_both_outcomes": "completed" in statuses and "failed" in statuses,
                "successful_count": sum(1 for status in statuses if status == "completed"),
                "failed_count": sum(1 for status in statuses if status == "failed"),
                "insights": [
                    {"label": "Status", "insight": "One archive completed while another failed."}
                ],
                "message": "Need both successful and failed prints to analyze correlation.",
            },
        }

    async def async_fetch_archive_capabilities(self, archive_id: int) -> dict[str, object]:
        archive = await self.async_fetch_archive_detail(archive_id)
        return {
            "has_model": bool(archive.get("file_path") or archive.get("source_3mf_path")),
            "has_gcode": True,
            "has_source": bool(archive.get("source_3mf_path")),
            "build_volume": {"x": 256, "y": 256, "z": 256},
            "filament_colors": ["#112233", "#FFFFFF"],
        }

    async def async_fetch_archive_gcode(self, archive_id: int) -> str:
        await self.async_fetch_archive_detail(archive_id)
        return "G0 X0 Y0 Z0.2\nG1 X42 Y42 E10"

    async def async_fetch_archive_timelapse_info(self, archive_id: int) -> dict[str, object]:
        archive = await self.async_fetch_archive_detail(archive_id)
        if not archive.get("timelapse_path"):
            raise RuntimeError("Bambuddy returned HTTP 404")
        normalized_archive_id = int(archive_id)
        type(self).timelapse_info_requests.append(normalized_archive_id)
        return {
            "duration": 84.5,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "h264",
            "bitrate": 6400000,
        }

    async def async_fetch_archive_timelapse_thumbnails(
        self,
        archive_id: int,
        *,
        count: int = 10,
        width: int = 160,
    ) -> dict[str, object]:
        archive = await self.async_fetch_archive_detail(archive_id)
        if not archive.get("timelapse_path"):
            raise RuntimeError("Bambuddy returned HTTP 404")
        request = {"archive_id": int(archive_id), "count": int(count), "width": int(width)}
        type(self).timelapse_thumbnail_requests.append(request)
        return {
            "thumbnails": ["thumb-a", "thumb-b", "thumb-c"],
            "timestamps": [0.0, 42.25, 84.5],
        }

    async def async_process_archive_timelapse(
        self,
        archive_id: int,
        *,
        trim_start: float = 0,
        trim_end: float | None = None,
        speed: float = 1.0,
        save_mode: str = "replace",
        output_filename: str | None = None,
        audio_file_name: str | None = None,
        audio_mime_type: str | None = None,
        audio_content: bytes | None = None,
    ) -> dict[str, object]:
        archive = await self.async_fetch_archive_detail(archive_id)
        if not archive.get("timelapse_path"):
            raise RuntimeError("Bambuddy returned HTTP 404")
        normalized_archive_id = int(archive_id)
        record = {
            "archive_id": normalized_archive_id,
            "trim_start": trim_start,
            "trim_end": trim_end,
            "speed": speed,
            "save_mode": save_mode,
            "output_filename": output_filename,
            "audio_file_name": audio_file_name,
            "audio_mime_type": audio_mime_type,
            "audio_byte_count": len(audio_content or b""),
        }
        type(self).processed_timelapses.append(record)
        return {
            "status": "completed",
            "output_path": str(archive.get("timelapse_path") or ""),
            "message": "Timelapse replaced successfully" if save_mode == "replace" else "Saved as new timelapse",
        }

    async def async_upload_archive_timelapse(
        self,
        archive_id: int,
        *,
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, object]:
        normalized_archive_id = int(archive_id)
        record = {
            "archive_id": normalized_archive_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "byte_count": len(content),
        }
        type(self).uploaded_photos.append(record)
        for index, item in enumerate(type(self).archives):
            if int(item.get("id", 0)) != normalized_archive_id:
                continue
            updated = dict(item)
            updated["timelapse_path"] = f"archive_timelapses/{normalized_archive_id}/{file_name}"
            type(self).archives[index] = updated
            break
        return {"status": "attached", "filename": file_name}

    async def async_fetch_projects(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.projects]

    async def async_fetch_archive_stats(self) -> dict[str, object]:
        return dict(self.archive_stats)

    async def async_fetch_failure_analysis(
        self,
        *,
        days: int | None = None,
        date_from: str = "",
        date_to: str = "",
        printer_id: int | None = None,
        project_id: int | None = None,
    ) -> dict[str, object]:
        payload = dict(self.failure_analysis)
        payload["requested_days"] = days
        payload["requested_date_from"] = date_from
        payload["requested_date_to"] = date_to
        payload["requested_printer_id"] = printer_id
        payload["requested_project_id"] = project_id
        return payload

    async def async_upload_archive_photo(
        self,
        archive_id: int,
        *,
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, object]:
        record = {
            "archive_id": archive_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "byte_count": len(content),
        }
        type(self).uploaded_photos.append(record)
        return record

    async def async_upload_archive_source_3mf(
        self,
        archive_id: int,
        *,
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, object]:
        normalized_archive_id = int(archive_id)
        record = {
            "archive_id": normalized_archive_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "byte_count": len(content),
        }
        type(self).uploaded_source_3mfs.append(record)
        for index, item in enumerate(type(self).archives):
            if int(item.get("id", 0)) != normalized_archive_id:
                continue
            updated = dict(item)
            updated["source_3mf_path"] = f"archive_sources/{normalized_archive_id}/{file_name}"
            type(self).archives[index] = updated
            break
        return record

    async def async_create_archive_slicer_token(self, archive_id: int) -> str:
        normalized_archive_id = int(archive_id)
        type(self).archive_slicer_tokens.append(normalized_archive_id)
        return f"archive-{normalized_archive_id}-token"

    async def async_create_source_slicer_token(self, archive_id: int) -> str:
        normalized_archive_id = int(archive_id)
        type(self).source_slicer_tokens.append(normalized_archive_id)
        return f"source-{normalized_archive_id}-token"

    async def async_upload_archive_replacement(
        self,
        *,
        printer_id: int,
        file_path: Path,
        file_name: str,
        mime_type: str,
    ) -> dict[str, object]:
        record = {
            "id": 232,
            "archive_id": 232,
            "printer_id": printer_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "file_path": str(file_path),
        }
        type(self).uploaded_replacements.append(record)
        return record

    async def async_delete_archive(self, archive_id: int) -> None:
        type(self).deleted_archives.append(int(archive_id))

    async def async_update_archive(self, archive_id: int, payload: dict[str, object]) -> dict[str, object]:
        normalized_archive_id = int(archive_id)
        for index, item in enumerate(type(self).archives):
            if int(item.get("id", 0)) != normalized_archive_id:
                continue
            updated = dict(item)
            for key, value in payload.items():
                updated[key] = value
            if payload.get("project_id") is None:
                updated["project_name"] = ""
            type(self).archives[index] = updated
            type(self).updated_archives.append({"archive_id": normalized_archive_id, "payload": dict(payload)})
            return dict(updated)
        raise RuntimeError("Bambuddy returned HTTP 404")

    async def async_toggle_archive_favorite(self, archive_id: int) -> dict[str, object]:
        normalized_archive_id = int(archive_id)
        for index, item in enumerate(type(self).archives):
            if int(item.get("id", 0)) != normalized_archive_id:
                continue
            updated = dict(item)
            updated["is_favorite"] = not bool(updated.get("is_favorite", False))
            type(self).archives[index] = updated
            type(self).toggled_favorites.append(normalized_archive_id)
            return dict(updated)
        raise RuntimeError("Bambuddy returned HTTP 404")


class FakeRuntimeRepairClient:
    metadata_correction_calls: list[dict[str, object]] = []
    restore_from_calls: list[dict[str, object]] = []
    restore_verify_calls: list[dict[str, object]] = []
    storage_scan_calls: list[dict[str, object]] = []
    storage_scan_batch_calls: list[dict[str, object]] = []

    def __init__(self, _session, _base_url: str, _token: str, _timeout_seconds: int) -> None:
        pass

    async def async_estimate_partial_usage(self, **kwargs) -> dict[str, object]:
        return {
            "archive_id": kwargs["archive_id"],
            "print_status": kwargs["print_status"],
            "calculation": {"method": "gcode_layer", "confidence": "high"},
            "totals": {"estimated_used_g_total": 12.5, "matched_slots": 1, "unmatched_slots": 0},
            "per_slot": [{"slot_id": 0, "estimated_used_g": 12.5, "spoolman_spool_id": 123}],
            "dedupe": {"dedupe_key": "101:failed:4:42.5", "already_consumed": False, "consumed_by": None},
        }

    async def async_metadata_correction(self, payload: dict[str, object]) -> dict[str, object]:
        type(self).metadata_correction_calls.append(dict(payload))
        fields = dict(payload.get("fields", {}))
        after = {
            "started_at": fields.get("started_at", "2026-04-10T00:00:00+00:00"),
            "completed_at": fields.get("completed_at", "2026-04-10T04:00:00+00:00"),
            "created_at": fields.get("created_at", "2026-04-10T00:00:00+00:00"),
            "status": fields.get("status", "completed"),
            "failure_reason": fields.get("failure_reason"),
            "filament_used_grams": fields.get("filament_used_grams", 42.5),
            "cost": fields.get("cost", 2.35),
            "quantity": fields.get("quantity", 1),
            "external_url": fields.get("external_url"),
        }
        return {
            "archive_id": int(payload["archive_id"]),
            "applied": not bool(payload.get("dry_run")),
            "changed": True,
            "correction_id": str(payload.get("request_id") or "corr-101"),
            "request_id": str(payload.get("request_id") or "corr-101"),
            "requested_at": "2026-04-19T10:00:00Z",
            "applied_at": None if payload.get("dry_run") else "2026-04-19T10:00:01Z",
            "before": {
                "started_at": "2026-04-10T00:00:00+00:00",
                "completed_at": "2026-04-10T04:00:00+00:00",
                "created_at": "2026-04-10T00:00:00+00:00",
                "status": "completed",
                "failure_reason": None,
                "filament_used_grams": 42.5,
                "cost": 2.35,
                "quantity": 1,
                "external_url": None,
            },
            "after": after,
            "updated_fields": sorted(list(fields.keys())),
            "warnings": ["Changing started_at or completed_at updates the effective runtime used by print-history views."],
            "derived_impacts": {
                "duration_seconds_before": 14400,
                "duration_seconds_after": 14400,
                "duration_seconds_changed": False,
                "created_day_before": "2026-04-10",
                "created_day_after": str(after["created_at"])[:10],
                "created_day_changed": str(after["created_at"])[:10] != "2026-04-10",
                "status_changed": after["status"] != "completed",
                "failure_reason_changed": after["failure_reason"] is not None,
                "filament_used_grams_before": 42.5,
                "filament_used_grams_after": after["filament_used_grams"],
                "filament_used_grams_changed": after["filament_used_grams"] != 42.5,
                "cost_before": 2.35,
                "cost_after": after["cost"],
                "cost_changed": after["cost"] != 2.35,
                "quantity_before": 1,
                "quantity_after": after["quantity"],
                "quantity_changed": after["quantity"] != 1,
                "external_url_before": None,
                "external_url_after": after["external_url"],
                "external_url_changed": bool(after["external_url"]),
            },
            "archive_revision": "rev-1",
        }

    async def async_restore_from(self, payload: dict[str, object]) -> dict[str, object]:
        type(self).restore_from_calls.append(dict(payload))
        if payload.get("dry_run"):
            return {
                "workflow_state": "plan_ready",
                "warnings": ["target parser-derived fields preserved"],
                "updated_fields": ["started_at", "completed_at", "tags"],
            }
        return {
            "workflow_state": "applied_pending_verify",
            "updated_fields": ["started_at", "completed_at", "tags"],
            "applied": True,
        }

    async def async_restore_verify(self, payload: dict[str, object]) -> dict[str, object]:
        type(self).restore_verify_calls.append(dict(payload))
        if payload.get("remove_original"):
            return {
                "verified": True,
                "removable": True,
                "source_removed": True,
                "blocking_difference_count": 0,
                "remaining_difference_count": 0,
            }
        return {
            "verified": True,
            "removable": True,
            "blocking_difference_count": 0,
            "remaining_difference_count": 0,
        }

    async def async_scan_archive_storage(self, payload: dict[str, object]) -> dict[str, object]:
        type(self).storage_scan_calls.append(dict(payload))
        archive_id = int(payload["archive_id"])
        return {
            "archive_id": archive_id,
            "computed_at": "2026-04-18T19:30:00Z",
            "scan_status": "complete",
            "metrics": {
                "archive_3mf_bytes": 98304,
                "thumbnail_bytes": 4096,
                "source_3mf_bytes": 32768,
                "timelapse_bytes": 5242880,
                "f3d_bytes": 0,
                "photo_bytes": 204800,
                "photo_count": 2,
                "other_bytes": 1024,
                "other_file_count": 1,
                "files_missing_count": 0,
                "total_bytes": 5583872,
            },
        }

    async def async_scan_archive_storage_batch(self, payload: dict[str, object]) -> dict[str, object]:
        type(self).storage_scan_batch_calls.append(dict(payload))
        archive_ids = [int(value) for value in payload.get("archive_ids", [])]
        return {
            "completed_count": len(archive_ids),
            "failed_count": 0,
            "errors": [],
            "results": [
                {
                    "archive_id": archive_id,
                    "computed_at": "2026-04-18T19:35:00Z",
                    "scan_status": "complete",
                    "metrics": {
                        "archive_3mf_bytes": 1000 + archive_id,
                        "thumbnail_bytes": 100,
                        "source_3mf_bytes": 200,
                        "timelapse_bytes": 300,
                        "f3d_bytes": 0,
                        "photo_bytes": 400,
                        "photo_count": 1,
                        "other_bytes": 50,
                        "other_file_count": 1,
                        "files_missing_count": 0,
                        "total_bytes": 2050 + archive_id,
                    },
                }
                for archive_id in archive_ids
            ],
        }


class FakeConfig:
    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, *parts: str) -> str:
        return str(self._root.joinpath(*parts))


class FakeHass:
    def __init__(self, root: Path, states: dict[str, str]) -> None:
        self.config = FakeConfig(root)
        self.states = FakeStates(states)
        self.services = FakeServices()
        self.bus = FakeBus()
        self.http = FakeHttp()
        self.data: dict[str, object] = {}
        self.websocket_handlers: list[object] = []

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        return coro


class FakeTimerHandle:
    def __init__(self, callback) -> None:
        self._callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self._callback()


class FakeLoop:
    def __init__(self) -> None:
        self.handles: list[FakeTimerHandle] = []

    def call_later(self, _delay: float, callback):
        handle = FakeTimerHandle(callback)
        self.handles.append(handle)
        return handle


class FakeMultipartPart:
    def __init__(self, name: str, *, filename: str | None = None, text: str = "", content: bytes = b"", content_type: str = "application/octet-stream") -> None:
        self.name = name
        self.filename = filename
        self._text = text
        self._content = content
        self._read = False
        self.headers = {"Content-Type": content_type}

    async def text(self) -> str:
        return self._text

    async def read_chunk(self, size: int = 64 * 1024) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._content[:size]

    def discard_unread(self) -> None:
        if self._read:
            return
        self._read = True
        self._content = b""


class FakeMultipartReader:
    def __init__(self, parts: list[FakeMultipartPart]) -> None:
        self._parts = list(parts)
        self._index = 0
        self._last_part: FakeMultipartPart | None = None

    async def next(self):
        if self._last_part is not None:
            self._last_part.discard_unread()
        if self._index >= len(self._parts):
            return None
        part = self._parts[self._index]
        self._index += 1
        self._last_part = part
        return part


class FakeMultipartRequest:
    def __init__(self, hass: FakeHass, archive_id: int, parts: list[FakeMultipartPart], headers: dict[str, str] | None = None) -> None:
        self.app = {"hass": hass}
        self.headers = headers or {"Content-Type": "multipart/form-data; boundary=fake-boundary"}
        self.match_info = {"archive_id": str(archive_id)}
        self._reader = FakeMultipartReader(parts)

    async def multipart(self):
        return self._reader


class FakeQueryRequest:
    def __init__(self, hass: FakeHass, archive_id: int, query: dict[str, object] | None = None) -> None:
        self.app = {"hass": hass}
        self.headers = {}
        self.match_info = {"archive_id": str(archive_id)}
        self.query = query or {}


def _default_state_map() -> dict[str, str]:
    return {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_text.print_history_filter_start_date": "",
        "input_text.print_history_filter_end_date": "",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_activity_metric": "Print Count",
        "input_select.print_history_sort": "Date (Newest)",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
        "input_number.print_history_max_archives": "500",
        "input_number.print_history_related_candidate_limit": "10",
        "input_boolean.bambuddy_integration_enabled": "on",
        "input_boolean.bambuddy_history_sync_enabled": "on",
    }


def _projected_archives(project_archive) -> list[dict]:
    raw = [
        {
            "id": 101,
            "printer_id": 1,
            "print_name": "Hueforge Batman",
            "content_hash": "hash-101-aabbccdd",
            "actual_time_seconds": 14400,
            "print_time_seconds": 15000,
            "filament_used_grams": 42.5,
            "filament_type": "PLA",
            "filament_color": "#112233,#ffffff",
            "status": "completed",
            "started_at": "2026-04-08T10:00:00Z",
            "completed_at": "2026-04-08T14:00:00Z",
            "created_at": "2026-04-08T09:58:00Z",
            "cost": 2.35,
            "duplicate_count": 2,
            "duplicate_sequence": 0,
            "original_archive_id": 101,
            "object_count": 2,
            "layer_height": 0.16,
            "designer": "Jane",
            "is_favorite": True,
            "tags": "display,hueforge,s:123",
            "notes": "User note\n\n+>{\"s\":\"c\",\"F\":[{\"n\":\"Blue PLA\",\"h\":\"#112233\"}]}",
            "file_path": "archives/101/model.3mf",
            "file_size": 98304,
            "photos": [
                "finish-overview.webp",
                {"path": "topdown-closeup.jpg", "role": "finish"},
                {"url": "detail-angle.png"},
            ],
            "thumbnail_path": "/api/v1/archives/101/thumbnail",
            "project_name": "Wall Art",
            "extra_data": {
                "filament_slots": [
                    {"tray": "A1", "name": "Blue PLA", "color": "#112233", "used_grams": 21.2},
                    {"tray": "A2", "name": "White PLA", "color": "#FFFFFF", "used_grams": 21.3},
                ]
            },
        },
        {
            "id": 202,
            "printer_id": 2,
            "print_name": "Fixture Test",
            "content_hash": "hash-202-zzxxyyww",
            "actual_time_seconds": 3600,
            "print_time_seconds": 3700,
            "filament_used_grams": 15.0,
            "filament_type": "PETG",
            "filament_color": "#445566",
            "status": "failed",
            "started_at": "2026-03-15T08:00:00Z",
            "completed_at": "2026-03-15T09:00:00Z",
            "created_at": "2026-03-15T07:55:00Z",
            "cost": 0.75,
            "duplicate_count": 2,
            "duplicate_sequence": 1,
            "original_archive_id": 101,
            "object_count": 1,
            "layer_height": 0.20,
            "designer": "Alex",
            "is_favorite": False,
            "tags": "qa",
            "notes": "Failed print",
            "failure_reason": "Layer shift",
            "project_name": "",
            "source_3mf_path": "archive_sources/202/source.3mf",
            "extra_data": {
                "no_3mf_available": True,
                "filament_slots": [{"tray": "B1", "color": "#445566", "used_grams": 15.0}],
            },
        },
    ]
    return [project_archive(item) for item in raw]


def test_variant3_manager_build_query_response_includes_store_annotations(tmp_path: Path) -> None:
    const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()

    response = manager.build_query_response({"page": 1, "page_size": 10})

    assert response["archive_count"] >= 2
    assert response["archives"][0]["id"] == 101
    assert "duplicate_count" in response["archives"][0]
    assert response["query"]["filtered_count"] >= 2

def test_variant3_manager_build_archive_detail_response_summarizes_spool_usage_events(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))

    manager.store.append_archive_event(
        101,
        event_type="spool_usage_recorded",
        event_source="spoolman_sync",
        event_time="2026-04-08T12:15:00Z",
        event_status="recorded",
        payload={
            "tray_name": "AMS 1 Tray 1",
            "spool_id": 501,
            "used_grams": "21.2",
            "message": "Spool usage was recorded successfully for this tray.",
        },
    )
    manager.store.append_archive_event(
        101,
        event_type="spool_usage_recording_failed",
        event_source="spoolman_sync",
        event_time="2026-04-08T12:16:00Z",
        event_status="failed",
        payload={
            "tray_name": "AMS 1 Tray 2",
            "reason_code": "missing_tray_uuid",
            "message": "Tray UUID was missing, so automatic spool usage recording was skipped for this tray.",
        },
    )

    detail = manager.build_archive_detail_response(101)

    assert detail is not None
    assert detail["event_timeline"][0]["label"] == "Spool usage recorded"
    assert detail["event_timeline"][0]["color_key"] == "spoolman"
    assert detail["event_timeline"][1]["label"] == "Spool usage recording failed"
    assert detail["event_timeline"][1]["color_key"] == "failure"
    assert detail["spool_usage_recording"]["status"] == "partial"
    assert detail["spool_usage_recording"]["label"] == "Partial"
    assert detail["spool_usage_recording"]["recorded_count"] == 1
    assert detail["spool_usage_recording"]["failed_count"] == 1
    assert detail["spool_usage_recording"]["recorded_spool_ids"] == [501]
    assert detail["spool_usage_recording"]["failed_trays"] == ["AMS 1 Tray 2"]
    assert detail["spool_usage_recording"]["reason_code"] == "missing_tray_uuid"


def test_variant3_manager_build_archive_detail_response_marks_review_only_spool_usage(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))

    manager.store.append_archive_event(
        101,
        event_type="spool_usage_review_estimated",
        event_source="spoolman_sync",
        event_time="2026-04-08T12:30:00Z",
        event_status="review_only",
        payload={
            "outcome": "failed",
            "matched_slots": 1,
            "unmatched_slots": 1,
            "message": "Review-only partial usage estimate captured. No Spoolman decrement was applied.",
        },
    )

    detail = manager.build_archive_detail_response(101)

    assert detail is not None
    assert detail["event_timeline"][0]["label"] == "Spool usage review estimate"
    assert detail["event_timeline"][0]["color_key"] == "neutral"
    assert detail["spool_usage_recording"]["status"] == "review_only"
    assert detail["spool_usage_recording"]["label"] == "Review Only"
    assert detail["spool_usage_recording"]["review_only_count"] == 1


def test_variant3_manager_build_query_response_includes_runtime_annotations(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.store.upsert_review_state(
        101,
        review_status="needs_review",
        mismatch_flags="color_mismatch",
        review_note="Check tray mapping",
        reviewed_at="2026-04-09T12:00:00Z",
    )
    manager.store.upsert_repair_lineage(
        101,
        202,
        relation_type="reprint_of",
        note="Retried after failure",
        created_at="2026-04-09T12:05:00Z",
    )
    manager.archives = manager.store.load_archives()
    manager._recompute_query()

    response = manager.build_query_response({"page": 1, "page_size": 10})

    assert response["archive_count"] == 2
    assert response["archives"][0]["id"] == 101
    assert response["archives"][0]["duplicate_count"] == 2
    assert response["review_state_by_archive"]["101"]["review_status"] == "needs_review"
    assert response["repair_lineage_by_archive"]["101"][0]["relation_type"] == "reprint_of"
    assert response["sync_metadata_by_archive"]["101"]["payload_hash"]
    assert response["store"]["archive_count"] == 2
    assert response["query"]["page_info"] == "1 of 1"
    assert manager.query_stats["count"] == 1
    assert manager.query_stats["last_matching_archive_count"] == 2
    assert manager.query_stats["last_metric_archive_count"] == 2
    assert manager.query_stats["last_metric_aggregate_ms"] >= 0.0
    assert manager.query_stats["last_page_item_count"] == 2
    assert manager.diagnostics()["recent_operations"][0]["type"] == "query"


def test_variant3_manager_build_query_response_filters_duplicates(tmp_path: Path) -> None:
    const_module, query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_select.print_history_filter_duplicates"] = "Dupes Only"
    hass = FakeHass(tmp_path, state_map)
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()

    response = manager.build_query_response({"duplicates": "Dupes Only"})

    assert [archive["id"] for archive in response["archives"]] == [202]
    assert "duplicates" in response["query"]["active_filters"]


def test_variant3_async_setup_registers_services_and_mutations_work(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.last_refresh_store_total_count = len(manager.archives)
    manager.last_refresh_archive_total_count = len(manager.archives)
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    registered = set(hass.services._handlers)
    assert (const_module.DOMAIN, const_module.SERVICE_REFRESH_PRINT_HISTORY_BROWSER) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_QUERY_PRINT_HISTORY_BROWSER) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_FAILURE_ANALYSIS) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_TEMP_STORAGE_SUMMARY) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS_BATCH) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_APPEND_PRINT_HISTORY_EVENT) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REVIEW_STATE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_ARCHIVE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_ESTIMATE_PARTIAL_USAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_CORRECT_PRINT_HISTORY_ARCHIVE_METADATA) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_RESTORE_WORKFLOW) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_CREATE_PRINT_HISTORY_ARCHIVE_REPLACEMENT_FROM_UPLOAD) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_PLAN_PRINT_HISTORY_ARCHIVE_RESTORE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_APPLY_PRINT_HISTORY_ARCHIVE_RESTORE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_VERIFY_PRINT_HISTORY_ARCHIVE_RESTORE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_FINISH_PRINT_HISTORY_ARCHIVE_RESTORE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_REMOVE_PRINT_HISTORY_RESTORED_SOURCE_ARCHIVE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_CLEAR_PRINT_HISTORY_ARCHIVE_RESTORE) in registered
    view_urls = {getattr(view, "url", "") for view in hass.http.views}
    assert const_module.RESTORE_UPLOAD_DISCOVER_URL in view_urls
    assert const_module.ARCHIVE_VIEWER_GCODE_URL in view_urls
    assert const_module.SOURCE_3MF_UPLOAD_URL in view_urls
    websocket_handler_names = {getattr(handler, "__name__", "") for handler in hass.websocket_handlers}
    assert "websocket_handle_archive_action" in websocket_handler_names
    assert "websocket_handle_archive_related" in websocket_handler_names
    assert "websocket_handle_archive_compare" in websocket_handler_names
    assert "websocket_handle_failure_analysis" in websocket_handler_names

    original_runtime_repair_client = init_module.BambuddyRuntimeRepairClient
    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyRuntimeRepairClient = FakeRuntimeRepairClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.deleted_archives = []
    FakeApiClient.updated_archives = []
    FakeApiClient.toggled_favorites = []
    FakeApiClient.archive_slicer_tokens = []
    FakeApiClient.source_slicer_tokens = []
    FakeApiClient.failure_analysis = {
        "period_days": 30,
        "total_prints": 10,
        "failed_prints": 2,
        "failure_rate": 20.0,
        "failures_by_reason": {"Spaghetti Detection": 2},
        "failures_by_filament": {"PLA": 2},
        "failures_by_printer": {"Printer 1": 2},
        "failures_by_hour": {0: 0, 1: 0},
        "recent_failures": [],
        "trend": [],
    }
    FakeApiClient.uploaded_source_3mfs = []
    FakeRuntimeRepairClient.metadata_correction_calls = []
    FakeRuntimeRepairClient.storage_scan_calls = []
    FakeRuntimeRepairClient.storage_scan_batch_calls = []

    try:
        query_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_QUERY_PRINT_HISTORY_BROWSER)(
                SimpleNamespace(data={"page": 1, "page_size": 10})
            )
        )
        activity_query_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_QUERY_PRINT_HISTORY_BROWSER)(
                SimpleNamespace(data={"include_activity_rows": True, "selected_day": ""})
            )
        )
        detail_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL)(
                SimpleNamespace(data={"archive_id": 101})
            )
        )
        failure_analysis_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_GET_FAILURE_ANALYSIS)(
                SimpleNamespace(data={"days": 14, "printer_id": 22, "project_id": 7})
            )
        )
        storage_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS)(
                SimpleNamespace(data={"archive_id": 101})
            )
        )
        temp_storage_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_TEMP_STORAGE_SUMMARY)(
                SimpleNamespace(data={})
            )
        )
        storage_refresh_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS)(
                SimpleNamespace(data={"archive_id": 101})
            )
        )
        storage_batch_refresh_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS_BATCH)(
                SimpleNamespace(data={"archive_ids": [101, 202]})
            )
        )
        enrichment_metadata_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA)(
                SimpleNamespace(data={"archive_id": 101, "mode": "MISSING_SPOOL"})
            )
        )
        update_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE)(
                SimpleNamespace(data={"archive_id": 101, "tags": "display,verified"})
            )
        )
        update_enrichment_metadata_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "tag_metadata": {
                            "system_tags": ["s:999", "f:555"],
                        },
                        "note_metadata": {
                            "payload": {
                                "s": "m",
                                "F": [
                                    {
                                        "n": "Blue PLA",
                                        "w": 42.5,
                                        "t": "A1",
                                        "s": 999,
                                        "f": 555,
                                        "h": "#112233",
                                    }
                                ],
                            },
                            "recovery_block": "[RECOVERY_AUDIT_V1]\nupdated by test",
                        },
                        "slot_overrides": "SLOT=0 TRAY=A1 SPOOL=999 FILAMENT=555",
                    }
                )
            )
        )
        favorite_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE)(
                SimpleNamespace(data={"archive_id": 202, "is_favorite": True})
            )
        )
        primary_photo_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "photo_path": "topdown-closeup.jpg",
                    }
                )
            )
        )
        append_event_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_APPEND_PRINT_HISTORY_EVENT)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "event_type": "objects_skipped",
                        "event_source": "ha_script",
                        "event_time": "2026-04-10T00:02:00Z",
                        "event_status": "printing",
                        "payload": {
                            "requested_skip_ids": [7],
                            "skip_overlay_state": {
                                "overlay_version": "v1",
                                "requested_skip_ids": [7],
                                "skipped_ids": [7],
                                "pick_image_path": "/api/image_proxy/image.3d_printer_pick_image",
                            },
                        },
                    }
                )
            )
        )
        review_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REVIEW_STATE)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "review_status": "reviewed",
                        "mismatch_flags": ["color_mismatch"],
                        "review_note": "Verified",
                        "reviewed_at": "2026-04-10T00:00:00Z",
                    }
                )
            )
        )
        lineage_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "related_archive_id": 202,
                        "relation_type": "derived_from",
                        "note": "Source failure",
                        "created_at": "2026-04-10T00:05:00Z",
                    }
                )
            )
        )
        delete_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "related_archive_id": 202,
                        "relation_type": "derived_from",
                    }
                )
            )
        )
        delete_archive_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_ARCHIVE)(
                SimpleNamespace(data={"archive_id": 202})
            )
        )
        estimate_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_ESTIMATE_PARTIAL_USAGE)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "print_status": "failed",
                        "printer_id": 1,
                        "last_layer_num": 4,
                        "last_progress": 42.5,
                    }
                )
            )
        )
        metadata_correction_preview_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_CORRECT_PRINT_HISTORY_ARCHIVE_METADATA)(
                SimpleNamespace(
                    data={
                        "archive_id": 101,
                        "created_at": "2026-04-11T00:00:00+00:00",
                        "filament_used_grams": 48.75,
                        "cost": 2.6,
                        "quantity": 2,
                        "external_url": "https://printables.com/model/12345",
                        "reason": "Correct archive day and advanced metadata",
                        "dry_run": True,
                        "request_id": "corr-preview-101",
                    }
                )
            )
        )
    finally:
        init_module.BambuddyRuntimeRepairClient = original_runtime_repair_client
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    assert query_response["entry_id"] == "entry-1"
    assert query_response["archives"][0]["id"] == 101
    assert query_response["archives"][0]["effective_duration_seconds"] == 14400
    assert query_response["archives"][0]["primary_photo_path"] == ""
    assert len(activity_query_response["activity_rows"]) == 2
    assert activity_query_response["activity_rows"][0]["effective_duration_seconds"] == 14400
    assert activity_query_response["activity_rows"][0]["enrichment_status"] == "partially complete"
    assert activity_query_response["activity_rows"][0]["project_name"] == "Wall Art"
    assert activity_query_response["activity_rows"][0]["duplicate_count"] == 2
    assert activity_query_response["activity_rows"][0]["primary_photo_path"] == ""
    assert detail_response["archive_id"] == 101
    assert detail_response["archive"]["print_name"] == "Hueforge Batman"
    assert detail_response["archive"]["effective_duration_seconds"] == 14400
    assert detail_response["archive"]["primary_photo_path"] == ""
    assert failure_analysis_response["failure_rate"] == 20.0
    assert failure_analysis_response["requested_days"] == 14
    assert failure_analysis_response["requested_printer_id"] == 22
    assert failure_analysis_response["requested_project_id"] == 7
    assert storage_response["success"] is True
    assert storage_response["source"] == "sidecar"
    assert storage_response["storage_metrics"]["metrics"]["total_bytes"] == 5583872
    assert temp_storage_response["success"] is True
    assert temp_storage_response["temp_storage"]["total_bytes"] >= 0
    temp_categories = {item["category"] for item in temp_storage_response["temp_storage"]["categories"]}
    assert "snapshot_cache" in temp_categories
    assert "restore_upload_staging" in temp_categories
    assert storage_refresh_response["success"] is True
    assert storage_refresh_response["refreshed"] is True
    assert storage_refresh_response["storage_metrics"]["metrics"]["photo_count"] == 2
    assert storage_batch_refresh_response["success"] is True
    assert storage_batch_refresh_response["completed_count"] == 2
    assert len(storage_batch_refresh_response["results"]) == 2
    assert enrichment_metadata_response["tag_metadata"]["system_tags"] == ["s:123"]
    assert enrichment_metadata_response["tag_metadata"]["user_tags"] == ["display", "hueforge"]
    assert enrichment_metadata_response["mode"] == "MISSING_SPOOL"
    assert enrichment_metadata_response["note_metadata"]["filtered_payload_row_count"] == 1
    assert enrichment_metadata_response["note_metadata"]["filtered_payload_rows"][0]["spool_id"] is None
    assert update_response["archive"]["tags"] == "display,verified"
    assert update_enrichment_metadata_response["tag_metadata"]["system_tags"] == ["s:999", "f:555"]
    assert update_enrichment_metadata_response["tag_metadata"]["user_tags"] == ["display", "verified"]
    assert update_enrichment_metadata_response["note_metadata"]["payload"]["F"][0]["s"] == 999
    assert update_enrichment_metadata_response["note_metadata"]["payload"]["F"][0]["f"] == 555
    assert update_enrichment_metadata_response["note_metadata"]["slot_overrides"] == [
        {"slot_id": "0", "tray": "A1", "spool_id": 999, "filament_id": 555}
    ]
    assert "[RECOVERY_AUDIT_V1]" in update_enrichment_metadata_response["note_metadata"]["system_notes"]
    assert update_enrichment_metadata_response["archive"]["notes"].startswith("User note")
    assert favorite_response["archive"]["is_favorite"] is True
    assert primary_photo_response["primary_photo_selection"]["photo_path"] == "topdown-closeup.jpg"
    assert primary_photo_response["archive"]["primary_photo_path"] == "topdown-closeup.jpg"
    assert append_event_response["event_timeline"][0]["type"] == "objects_skipped"
    assert append_event_response["event_timeline"][0]["label"] == "Objects skipped"
    assert append_event_response["skip_overlay_state"]["requested_skip_ids"] == [7]
    assert append_event_response["skip_overlay_state"]["pick_image_path"] == "/api/bambuddy/print-history/archive/101/pick-image?plate=0"
    assert review_response["review_state"]["review_status"] == "reviewed"
    assert review_response["review_state"]["mismatch_flags"] == "color_mismatch"
    assert lineage_response["repair_lineage"][0]["relation_type"] == "derived_from"
    assert delete_response["deleted"] == 1
    assert delete_archive_response["deleted"] == 1
    assert FakeApiClient.deleted_archives == [202]
    assert FakeApiClient.updated_archives == [
        {"archive_id": 101, "payload": {"tags": "display,verified"}},
        {
            "archive_id": 101,
            "payload": {
                "tags": "display,verified,s:999,f:555",
                "notes": "User note\n\n[RECOVERY_AUDIT_V1]\nupdated by test\n\n+>{\"F\":[{\"f\":555,\"h\":\"#112233\",\"n\":\"Blue PLA\",\"s\":999,\"t\":\"A1\",\"w\":42.5}],\"s\":\"m\",\"slot_overrides\":[{\"filament_id\":555,\"slot_id\":\"0\",\"spool_id\":999,\"tray\":\"A1\"}]}",
            },
        },
    ]
    assert FakeApiClient.toggled_favorites == [202]
    assert manager.store.load_archive(202) is None
    assert manager.last_refresh_store_total_count == 1
    assert manager.last_refresh_archive_total_count == 1
    assert estimate_response["success"] is True
    assert estimate_response["estimate"]["totals"]["estimated_used_g_total"] == 12.5
    assert estimate_response["estimate"]["dedupe"]["dedupe_key"] == "101:failed:4:42.5"
    assert metadata_correction_preview_response["success"] is True
    assert metadata_correction_preview_response["dry_run"] is True
    assert metadata_correction_preview_response["correction"]["updated_fields"] == [
        "cost",
        "created_at",
        "external_url",
        "filament_used_grams",
        "quantity",
    ]
    assert manager.store.load_metadata_correction_audit(101)[0]["status"] == "preview"
    assert FakeRuntimeRepairClient.metadata_correction_calls == [
        {
            "archive_id": 101,
            "fields": {
                "created_at": "2026-04-11T00:00:00+00:00",
                "filament_used_grams": 48.75,
                "cost": 2.6,
                "quantity": 2,
                "external_url": "https://printables.com/model/12345",
            },
            "reason": "Correct archive day and advanced metadata",
            "dry_run": True,
            "trigger_source": "home_assistant_archive_actions",
            "request_id": "corr-preview-101",
        }
    ]
    assert FakeRuntimeRepairClient.storage_scan_calls == [
        {"archive_id": 101, "force": False, "include_other_files": True, "include_extension_breakdown": False},
        {"archive_id": 101, "force": True, "include_other_files": True, "include_extension_breakdown": False},
    ]
    assert FakeRuntimeRepairClient.storage_scan_batch_calls == [
        {"archive_ids": [101, 202], "force": True, "include_other_files": True, "include_extension_breakdown": False}
    ]
    assert manager.store.load_archive_storage_metrics(101)["metrics"]["total_bytes"] == 2151
    assert manager.store.load_archive_storage_metrics(202) is None
    assert manager.query_stats["count"] == 2
    assert manager.query_stats["last_source"] == "service"
    assert manager.result.page_items[0]["primary_photo_path"] == "topdown-closeup.jpg"
    assert manager.mutation_stats["count"] == 18


def test_variant3_manual_photo_upload_refreshes_storage_metrics(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    original_runtime_repair_client = init_module.BambuddyRuntimeRepairClient
    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    FakeRuntimeRepairClient.storage_scan_calls = []
    FakeApiClient.archives = manager.archives
    init_module.BambuddyRuntimeRepairClient = FakeRuntimeRepairClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient

    try:
        asyncio.run(init_module.async_setup(hass, {}))
        connection = sys.modules["homeassistant.components.websocket_api"].ActiveConnection()
        payload = base64.b64encode(b"fake-image-bytes").decode("ascii")
        asyncio.run(
            next(handler for handler in hass.websocket_handlers if getattr(handler, "__name__", "") == "websocket_handle_upload_photo")(
                hass,
                connection,
                {
                    "id": 9,
                    "type": "bambuddy/print_history_upload_photo",
                    "archive_id": 101,
                    "file_name": "manual-upload.jpg",
                    "mime_type": "image/jpeg",
                    "content_base64": payload,
                },
            )
        )
    finally:
        init_module.BambuddyRuntimeRepairClient = original_runtime_repair_client
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    assert connection.results
    result = connection.results[0][1]
    assert result["archive_id"] == 101
    assert connection.errors == []


def test_variant3_archive_viewer_proxy_view_returns_gcode(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    gcode_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.ARCHIVE_VIEWER_GCODE_URL)

    original_api_client = init_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives

    try:
        gcode_response = asyncio.run(
            gcode_view.get(
                SimpleNamespace(
                    app={"hass": hass},
                    query={},
                    match_info={"archive_id": "101"},
                )
            )
        )
    finally:
        init_module.BambuddyApiClient = original_api_client

    assert gcode_response.status == 200
    assert gcode_response.content_type == "text/plain"
    assert "G1 X42 Y42 E10" in gcode_response.text


def test_variant3_archive_action_websocket_returns_tokenized_download_urls(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    action_handler = next(handler for handler in hass.websocket_handlers if getattr(handler, "__name__", "") == "websocket_handle_archive_action")
    connection = sys.modules["homeassistant.components.websocket_api"].ActiveConnection()

    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.archive_slicer_tokens = []
    FakeApiClient.source_slicer_tokens = []

    try:
        asyncio.run(
            action_handler(
                hass,
                connection,
                {"id": 1, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_ACTION, "archive_id": 101, "intent": "download_gcode"},
            )
        )
        asyncio.run(
            action_handler(
                hass,
                connection,
                {"id": 2, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_ACTION, "archive_id": 202, "intent": "open_in_slicer"},
            )
        )
        asyncio.run(
            action_handler(
                hass,
                connection,
                {"id": 3, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_ACTION, "archive_id": 202, "intent": "download_source_3mf"},
            )
        )
    finally:
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    assert not connection.errors
    first_result = connection.results[0][1]
    second_result = connection.results[1][1]
    third_result = connection.results[2][1]
    assert first_result["resource_type"] == "file"
    assert "/api/v1/archives/101/dl/archive-101-token/" in first_result["download_url"]
    assert second_result["resource_type"] == "source"
    assert "/api/v1/archives/202/source-dl/source-202-token/" in second_result["download_url"]
    assert third_result["resource_type"] == "source"
    assert "/api/v1/archives/202/source-dl/source-202-token/" in third_result["download_url"]
    assert FakeApiClient.archive_slicer_tokens == [101]
    assert FakeApiClient.source_slicer_tokens == [202, 202]


def test_variant3_archive_related_and_compare_websockets_return_normalized_payloads(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[1]["print_name"] = "Hueforge Batman"
    manager.archives[1]["status"] = "failed"
    manager.archives.extend(
        [
            {
                **manager.archives[1],
                "id": 404,
                "print_name": "Zulu Fixture",
                "status": "completed",
                "created_at": "2026-04-19T07:55:00Z",
            },
            {
                **manager.archives[1],
                "id": 303,
                "print_name": "Alpha Fixture",
                "status": "completed",
                "created_at": "2026-01-03T07:55:00Z",
            },
        ]
    )
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    related_handler = next(
        handler for handler in hass.websocket_handlers if getattr(handler, "__name__", "") == "websocket_handle_archive_related"
    )
    duplicates_handler = next(
        handler for handler in hass.websocket_handlers if getattr(handler, "__name__", "") == "websocket_handle_archive_duplicates"
    )
    compare_handler = next(
        handler for handler in hass.websocket_handlers if getattr(handler, "__name__", "") == "websocket_handle_archive_compare"
    )
    connection = sys.modules["homeassistant.components.websocket_api"].ActiveConnection()

    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.related_requests = []
    FakeApiClient.compare_requests = []

    try:
        asyncio.run(
            related_handler(
                hass,
                connection,
                {"id": 1, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_RELATED, "archive_id": 101, "limit": 4},
            )
        )
        asyncio.run(
            compare_handler(
                hass,
                connection,
                {"id": 2, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_COMPARE, "archive_ids": [101, 202]},
            )
        )
        asyncio.run(
            duplicates_handler(
                hass,
                connection,
                {"id": 3, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_DUPLICATES, "archive_id": 101},
            )
        )
        asyncio.run(
            duplicates_handler(
                hass,
                connection,
                {"id": 4, "type": init_module.WS_TYPE_PRINT_HISTORY_ARCHIVE_DUPLICATES, "archive_id": 202},
            )
        )
    finally:
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    assert not connection.errors
    related_result = connection.results[0][1]
    compare_result = connection.results[1][1]
    source_duplicates_result = connection.results[2][1]
    child_duplicates_result = connection.results[3][1]
    assert related_result["archive_id"] == 101
    assert related_result["limit"] == 4
    assert related_result["candidates"][0]["archive_id"] == 202
    assert related_result["candidates"][0]["confidence_bucket"] == "high"
    assert related_result["candidates"][0]["match_type"] == "same_name"
    assert related_result["candidates"][0]["archive"]["print_name"] == "Hueforge Batman"
    assert related_result["candidates"][1]["archive_id"] == 303
    assert related_result["candidates"][2]["archive_id"] == 404
    assert compare_result["archive_ids"] == [101, 202]
    assert compare_result["comparison"][0]["field"] == "status"
    assert compare_result["comparison"][-1]["field"] == "content_hash"
    assert compare_result["comparison"][-1]["label"] == "File Content Hash"
    assert compare_result["comparison"][-1]["has_difference"] is True
    assert compare_result["differences"][0]["field"] == "status"
    assert compare_result["differences"][-1]["field"] == "content_hash"
    assert compare_result["success_correlation"]["has_both_outcomes"] is True
    assert source_duplicates_result["archive_id"] == 101
    assert source_duplicates_result["family_anchor_id"] == 101
    assert source_duplicates_result["source"]["archive_id"] == 101
    assert sorted(member["archive_id"] for member in source_duplicates_result["duplicates"]) == [202, 303, 404]
    assert child_duplicates_result["archive_id"] == 202
    assert child_duplicates_result["family_anchor_id"] == 101
    assert child_duplicates_result["source"]["archive_id"] == 101
    assert child_duplicates_result["duplicates"][0]["archive_id"] == 202
    assert child_duplicates_result["duplicates"][0]["is_current"] is True
    assert FakeApiClient.related_requests == [{"archive_id": 101, "limit": 4}]
    assert FakeApiClient.compare_requests == [[101, 202]]


def test_variant3_source_3mf_upload_view_refreshes_archive_detail(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    upload_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.SOURCE_3MF_UPLOAD_URL)

    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.uploaded_source_3mfs = []

    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart("entry_id", text="entry-1"),
            FakeMultipartPart(
                "file",
                filename="source-model.3mf",
                content=b"fake-3mf-bytes",
                content_type="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            ),
        ],
    )

    try:
        response = asyncio.run(upload_view.post(request))
    finally:
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    payload = response["payload"]
    assert response["status"] == 200
    assert payload["success"] is True
    assert payload["archive"]["source_3mf_path"] == "archive_sources/101/source-model.3mf"
    assert manager.store.load_archive(101)["source_3mf_path"] == "archive_sources/101/source-model.3mf"
    assert FakeApiClient.uploaded_source_3mfs == [
        {
            "archive_id": 101,
            "file_name": "source-model.3mf",
            "mime_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            "byte_count": 14,
        }
    ]


def test_variant3_source_3mf_upload_view_returns_diagnostics_for_empty_payload(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    upload_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.SOURCE_3MF_UPLOAD_URL)
    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart("entry_id", text="entry-1"),
            FakeMultipartPart(
                "file",
                filename="empty-source.3mf",
                content=b"",
                content_type="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            ),
        ],
        headers={"Content-Type": "multipart/form-data; boundary=diagnostic-boundary"},
    )

    response = asyncio.run(upload_view.post(request))

    payload = response["payload"]
    assert response["status"] == 400
    assert payload["success"] is False
    assert payload["message"] == "Upload payload is empty after multipart parsing"
    assert payload["diagnostics"] == {
        "request_content_type": "multipart/form-data; boundary=diagnostic-boundary",
        "fields_present": ["entry_id"],
        "file_name": "empty-source.3mf",
        "file_content_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        "byte_count": 0,
        "chunk_count": 0,
        "first_chunk_size": 0,
    }


def test_variant3_source_3mf_upload_view_reads_file_before_advancing_multipart_reader(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    upload_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.SOURCE_3MF_UPLOAD_URL)

    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.uploaded_source_3mfs = []

    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart(
                "file",
                filename="source-first.3mf",
                content=b"file-before-entry-id",
                content_type="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            ),
            FakeMultipartPart("entry_id", text="entry-1"),
        ],
    )

    try:
        response = asyncio.run(upload_view.post(request))
    finally:
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    payload = response["payload"]
    assert response["status"] == 200
    assert payload["success"] is True
    assert payload["archive"]["source_3mf_path"] == "archive_sources/101/source-first.3mf"
    assert FakeApiClient.uploaded_source_3mfs[-1]["byte_count"] == len(b"file-before-entry-id")


def test_variant3_source_3mf_upload_websocket_refreshes_archive_detail(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    upload_handler = next(
        handler for handler in hass.websocket_handlers if getattr(handler, "__name__", "") == "websocket_handle_upload_source_3mf"
    )
    connection = sys.modules["homeassistant.components.websocket_api"].ActiveConnection()

    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.uploaded_source_3mfs = []

    try:
        asyncio.run(
            upload_handler(
                hass,
                connection,
                {
                    "id": 1,
                    "type": init_module.WS_TYPE_PRINT_HISTORY_UPLOAD_SOURCE_3MF,
                    "archive_id": 101,
                    "file_name": "source-model.3mf",
                    "mime_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
                    "content_base64": base64.b64encode(b"fake-3mf-bytes").decode("ascii"),
                },
            )
        )
    finally:
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    assert not connection.errors
    result = connection.results[0][1]
    assert result["archive"]["source_3mf_path"] == "archive_sources/101/source-model.3mf"
    assert manager.store.load_archive(101)["source_3mf_path"] == "archive_sources/101/source-model.3mf"
    assert FakeApiClient.uploaded_source_3mfs == [
        {
            "archive_id": 101,
            "file_name": "source-model.3mf",
            "mime_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            "byte_count": 14,
        }
    ]


def test_variant3_timelapse_info_view_returns_metadata(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    info_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.TIMELAPSE_INFO_URL)
    request = FakeQueryRequest(hass, 101)

    original_api_client = init_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.timelapse_info_requests = []

    try:
        response = asyncio.run(info_view.get(request))
    finally:
        init_module.BambuddyApiClient = original_api_client

    payload = response["payload"]
    assert response["status"] == 200
    assert payload["success"] is True
    assert payload["archive_id"] == 101
    assert payload["duration"] == 84.5
    assert payload["width"] == 1920
    assert FakeApiClient.timelapse_info_requests == [101]


def test_variant3_timelapse_thumbnails_view_forwards_query_params(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    thumbnails_view = next(
        view for view in hass.http.views if getattr(view, "url", "") == const_module.TIMELAPSE_THUMBNAILS_URL
    )
    request = FakeQueryRequest(hass, 101, {"count": "15", "width": "240"})

    original_api_client = init_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.timelapse_thumbnail_requests = []

    try:
        response = asyncio.run(thumbnails_view.get(request))
    finally:
        init_module.BambuddyApiClient = original_api_client

    payload = response["payload"]
    assert response["status"] == 200
    assert payload["success"] is True
    assert payload["thumbnails"] == ["thumb-a", "thumb-b", "thumb-c"]
    assert payload["timestamps"] == [0.0, 42.25, 84.5]
    assert FakeApiClient.timelapse_thumbnail_requests == [{"archive_id": 101, "count": 15, "width": 240}]


def test_variant3_timelapse_process_view_refreshes_archive_detail(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    process_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.TIMELAPSE_PROCESS_URL)
    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart("entry_id", text="entry-1"),
            FakeMultipartPart("trim_start", text="5"),
            FakeMultipartPart("trim_end", text="30"),
            FakeMultipartPart("speed", text="1.5"),
            FakeMultipartPart("save_mode", text="replace"),
            FakeMultipartPart(
                "audio",
                filename="soundtrack.mp3",
                content=b"fake-audio-bytes",
                content_type="audio/mpeg",
            ),
        ],
    )

    original_runtime_repair_client = init_module.BambuddyRuntimeRepairClient
    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyRuntimeRepairClient = FakeRuntimeRepairClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.processed_timelapses = []
    FakeRuntimeRepairClient.storage_scan_calls = []

    try:
        response = asyncio.run(process_view.post(request))
    finally:
        init_module.BambuddyRuntimeRepairClient = original_runtime_repair_client
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    payload = response["payload"]
    assert response["status"] == 200
    assert payload["success"] is True
    assert payload["process"]["status"] == "completed"
    assert payload["process"]["message"] == "Timelapse replaced successfully"
    assert payload["process"]["output_path"] == "archive_timelapses/101/print-101.mp4"
    assert payload["storage_metrics"]["metrics"]["timelapse_bytes"] == 5242880
    assert payload["archive"]["storage_metrics"]["metrics"]["timelapse_bytes"] == 5242880
    assert FakeRuntimeRepairClient.storage_scan_calls == [
        {"archive_id": 101, "force": True, "include_other_files": True, "include_extension_breakdown": False}
    ]
    assert FakeApiClient.processed_timelapses == [
        {
            "archive_id": 101,
            "trim_start": 5.0,
            "trim_end": 30.0,
            "speed": 1.5,
            "save_mode": "replace",
            "output_filename": None,
            "audio_file_name": "soundtrack.mp3",
            "audio_mime_type": "audio/mpeg",
            "audio_byte_count": 16,
        }
    ]


def test_variant3_timelapse_upload_view_refreshes_nested_storage_metrics(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    upload_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.TIMELAPSE_UPLOAD_URL)
    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart("entry_id", text="entry-1"),
            FakeMultipartPart(
                "file",
                filename="replacement.mp4",
                content=b"replacement-video-bytes",
                content_type="video/mp4",
            ),
        ],
    )

    original_runtime_repair_client = init_module.BambuddyRuntimeRepairClient
    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyRuntimeRepairClient = FakeRuntimeRepairClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.uploaded_photos = []
    FakeRuntimeRepairClient.storage_scan_calls = []

    try:
        response = asyncio.run(upload_view.post(request))
    finally:
        init_module.BambuddyRuntimeRepairClient = original_runtime_repair_client
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    payload = response["payload"]
    assert response["status"] == 200
    assert payload["success"] is True
    assert payload["upload"]["file_name"] == "replacement.mp4"
    assert payload["storage_metrics"]["metrics"]["timelapse_bytes"] == 5242880
    assert payload["archive"]["storage_metrics"]["metrics"]["timelapse_bytes"] == 5242880
    assert payload["archive"]["timelapse_path"] == "archive_timelapses/101/replacement.mp4"
    assert FakeRuntimeRepairClient.storage_scan_calls == [
        {"archive_id": 101, "force": True, "include_other_files": True, "include_extension_breakdown": False}
    ]


def test_variant3_timelapse_process_view_rejects_save_as_new_mode(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    process_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.TIMELAPSE_PROCESS_URL)
    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart("entry_id", text="entry-1"),
            FakeMultipartPart("trim_start", text="5"),
            FakeMultipartPart("trim_end", text="30"),
            FakeMultipartPart("speed", text="1.5"),
            FakeMultipartPart("save_mode", text="new"),
            FakeMultipartPart("output_filename", text="should-not-be-used.mp4"),
        ],
    )

    original_api_client = init_module.BambuddyApiClient
    original_manager_api_client = manager_module.BambuddyApiClient
    init_module.BambuddyApiClient = FakeApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    FakeApiClient.archives = manager.archives
    FakeApiClient.processed_timelapses = []

    try:
        response = asyncio.run(process_view.post(request))
    finally:
        init_module.BambuddyApiClient = original_api_client
        manager_module.BambuddyApiClient = original_manager_api_client

    payload = response["payload"]
    assert response["status"] == 400
    assert payload["success"] is False
    assert payload["error"] == "invalid_payload"
    assert "Only save_mode='replace' is supported" in payload["message"]
    assert FakeApiClient.processed_timelapses == []


def test_variant3_timelapse_upload_view_requires_delete_before_reupload(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.archives[0]["timelapse_path"] = "archive_timelapses/101/print-101.mp4"
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    upload_view = next(view for view in hass.http.views if getattr(view, "url", "") == const_module.TIMELAPSE_UPLOAD_URL)
    request = FakeMultipartRequest(
        hass,
        101,
        [
            FakeMultipartPart("entry_id", text="entry-1"),
            FakeMultipartPart(
                "file",
                filename="replacement.mp4",
                content=b"replacement-video-bytes",
                content_type="video/mp4",
            ),
        ],
    )

    response = asyncio.run(upload_view.post(request))

    payload = response["payload"]
    assert response["status"] == 400
    assert payload["success"] is False
    assert payload["error"] == "resolve_failed"
    assert payload["message"] == (
        "This archive already has an attached timelapse. Delete the existing timelapse first before uploading a new file."
    )


def test_variant3_restore_workflow_services_manage_upload_plan_verify_and_clear(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    replacement_file = tmp_path / "replacement.gcode.3mf"
    replacement_file.write_bytes(b"replacement-bytes")
    upload_session = manager.restore_uploads.finalize_session(
        session_id="session-1",
        entry_id=entry.entry_id,
        source_archive_id=101,
        printer_id=1,
        file_name="replacement.gcode.3mf",
        content_type="application/octet-stream",
        size_bytes=replacement_file.stat().st_size,
        file_path=replacement_file,
    )
    manager.restore_workflow.set_upload_ready(
        entry_id=entry.entry_id,
        source_archive_id=101,
        upload_session_id=upload_session.session_id,
        summary={"upload": upload_session.to_response()},
    )

    original_runtime_repair_client = init_module.BambuddyRuntimeRepairClient
    original_api_client = init_module.BambuddyApiClient
    FakeRuntimeRepairClient.restore_from_calls = []
    FakeRuntimeRepairClient.restore_verify_calls = []
    FakeApiClient.uploaded_replacements = []
    FakeApiClient.archives = _projected_archives(query_module.project_archive) + [
        query_module.project_archive(
            {
                "id": 232,
                "printer_id": 1,
                "print_name": "Replacement Archive",
                "actual_time_seconds": 15000,
                "print_time_seconds": 15000,
                "filament_used_grams": 42.5,
                "filament_type": "PLA",
                "filament_color": "#112233,#ffffff",
                "status": "completed",
                "started_at": "2026-04-08T10:00:00Z",
                "completed_at": "2026-04-08T14:10:00Z",
                "created_at": "2026-04-08T09:58:00Z",
                "cost": 2.40,
                "duplicate_count": 1,
                "duplicate_sequence": 0,
                "original_archive_id": 232,
                "object_count": 2,
                "layer_height": 0.16,
                "designer": "Jane",
                "is_favorite": False,
                "tags": "replacement",
                "notes": "+>{\"s\":\"c\"}",
                "thumbnail_path": "/api/v1/archives/232/thumbnail",
                "extra_data": {"filament_slots": []},
                "enrichment_status": "complete",
            }
        )
    ]
    FakeApiClient.printers = [{"id": 1, "name": "P1S"}]
    FakeApiClient.projects = []
    FakeApiClient.archive_stats = {"total_prints": 3}
    init_module.BambuddyRuntimeRepairClient = FakeRuntimeRepairClient
    init_module.BambuddyApiClient = FakeApiClient

    try:
        asyncio.run(init_module.async_setup(hass, {}))
        create_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_CREATE_PRINT_HISTORY_ARCHIVE_REPLACEMENT_FROM_UPLOAD)(
                SimpleNamespace(data={"source_archive_id": 101, "upload_session_id": "session-1"})
            )
        )
        plan_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_PLAN_PRINT_HISTORY_ARCHIVE_RESTORE)(
                SimpleNamespace(data={"source_archive_id": 101, "target_archive_id": 232})
            )
        )
        apply_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_APPLY_PRINT_HISTORY_ARCHIVE_RESTORE)(
                SimpleNamespace(data={"source_archive_id": 101, "target_archive_id": 232})
            )
        )
        verify_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_VERIFY_PRINT_HISTORY_ARCHIVE_RESTORE)(
                SimpleNamespace(data={"source_archive_id": 101, "target_archive_id": 232})
            )
        )
        finish_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_FINISH_PRINT_HISTORY_ARCHIVE_RESTORE)(
                SimpleNamespace(data={"source_archive_id": 101, "target_archive_id": 232, "retain_original": True})
            )
        )
        clear_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_CLEAR_PRINT_HISTORY_ARCHIVE_RESTORE)(
                SimpleNamespace(data={"source_archive_id": 101, "target_archive_id": 232})
            )
        )
    finally:
        init_module.BambuddyRuntimeRepairClient = original_runtime_repair_client
        init_module.BambuddyApiClient = original_api_client

    assert create_response["success"] is True
    assert create_response["target_archive_id"] == 232
    assert FakeApiClient.uploaded_replacements[0]["printer_id"] == 1
    assert plan_response["workflow_state"] == "plan_ready"
    assert apply_response["workflow_state"] == "applied_pending_verify"
    assert verify_response["workflow_state"] == "remove_ready"
    assert finish_response["workflow_state"] == "completed_original_retained"
    assert clear_response["cleared"] is True
    assert len(FakeRuntimeRepairClient.restore_from_calls) == 2
    assert len(FakeRuntimeRepairClient.restore_verify_calls) == 2


def test_variant3_primary_photo_service_can_explicitly_revert_to_thumbnail(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    response = asyncio.run(
        hass.services.handler(const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO)(
            SimpleNamespace(data={"archive_id": 101, "photo_path": ""})
        )
    )

    assert response["primary_photo_selection"]["photo_path"] == ""
    assert response["primary_photo_selection"]["cleared"] is True
    assert response["archive"]["primary_photo_path"] == ""
    assert response["archive"]["selected_primary_photo_path"] == ""
    assert response["archive"]["has_primary_photo_override"] is True


def test_variant3_append_event_hydrates_missing_archive_from_api(tmp_path: Path) -> None:
    const_module, query_module, manager_module, init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={
            "base_url": "http://example.local",
            "api_key": "token",
            "runtime_repair_base_url": "http://repair.local",
            "runtime_repair_token": "repair-token",
        },
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    FakeApiClient.archives = [
        {
            "id": 303,
            "printer_id": 1,
            "print_name": "Fresh Archive",
            "actual_time_seconds": 1200,
            "print_time_seconds": 1200,
            "filament_used_grams": 9.5,
            "filament_type": "PLA",
            "filament_color": "#778899",
            "status": "completed",
            "started_at": "2026-04-10T11:00:00Z",
            "completed_at": "2026-04-10T11:20:00Z",
            "created_at": "2026-04-10T10:58:00Z",
            "cost": 0.42,
            "duplicate_count": 1,
            "duplicate_sequence": 0,
            "original_archive_id": 303,
            "object_count": 1,
            "layer_height": 0.2,
            "designer": "Taylor",
            "is_favorite": False,
            "tags": "new",
            "notes": "",
            "thumbnail_path": "/api/v1/archives/303/thumbnail",
            "extra_data": {
                "filament_slots": [
                    {"tray": "A1", "name": "Gray PLA", "color": "#778899", "used_grams": 9.5}
                ]
            },
        }
    ]
    FakeApiClient.printers = [{"id": 1, "name": "P1S"}]
    FakeApiClient.projects = []
    FakeApiClient.archive_stats = {}

    original_manager_api_client = manager_module.BambuddyApiClient
    manager_module.BambuddyApiClient = FakeApiClient

    try:
        asyncio.run(init_module.async_setup(hass, {}))
        append_event_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_APPEND_PRINT_HISTORY_EVENT)(
                SimpleNamespace(
                    data={
                        "archive_id": 303,
                        "event_type": "enrichment_applied",
                        "event_source": "ha_automation",
                        "event_time": "2026-04-10T11:21:00Z",
                        "event_status": "complete",
                        "payload": {"source": "automation"},
                    }
                )
            )
        )
    finally:
        manager_module.BambuddyApiClient = original_manager_api_client

    hydrated_archive = manager.store.load_archive(303)

    assert hydrated_archive is not None
    assert hydrated_archive["printer_name"] == "P1S"
    assert append_event_response["archive_id"] == 303


def test_variant3_refresh_archive_detail_updates_photo_list_after_upload(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()

    refreshed_raw_archive = dict(_projected_archives(query_module.project_archive)[0])
    refreshed_raw_archive["photos"] = [
        "finish-overview.webp",
        {"path": "topdown-closeup.jpg", "role": "finish"},
        {"path": "phone-upload.jpg", "role": "manual"},
    ]
    FakeApiClient.archives = [refreshed_raw_archive]
    FakeApiClient.printers = [{"id": 1, "name": "Workshop P1S"}]

    original_manager_api_client = manager_module.BambuddyApiClient
    manager_module.BambuddyApiClient = FakeApiClient

    try:
        refreshed = asyncio.run(
            manager.async_refresh_archive_detail(
                101,
                operation="upload_archive_photo",
                extra_details={"file_name": "phone-upload.jpg"},
            )
        )
    finally:
        manager_module.BambuddyApiClient = original_manager_api_client

    assert refreshed is not None
    assert refreshed["photos"] == ["finish-overview.webp", "topdown-closeup.jpg", "phone-upload.jpg"]
    assert manager.mutation_stats["last_operation"] == "upload_archive_photo"


def test_variant3_refresh_archive_detail_applies_live_current_plate_id_to_matching_archive(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager._recompute_query()

    FakeApiClient.archives = [
        {
            "id": 101,
            "printer_id": 1,
            "printer_name": "Workshop P1S",
            "print_name": "Hueforge Batman - Plate 2",
            "actual_time_seconds": 7200,
            "print_time_seconds": 7200,
            "filament_used_grams": 42.5,
            "filament_type": "PLA",
            "filament_color": "#101010",
            "status": "printing",
            "started_at": "2026-04-20T10:00:00Z",
            "completed_at": "",
            "created_at": "2026-04-20T09:58:00Z",
            "cost": 1.5,
            "layer_height": 0.2,
            "is_favorite": False,
            "tags": "",
            "notes": "",
            "photos": [],
        }
    ]
    FakeApiClient.printers = [
        {"id": 1, "name": "Workshop P1S", "current_archive_id": 101, "current_plate_id": 7}
    ]

    original_manager_api_client = manager_module.BambuddyApiClient
    manager_module.BambuddyApiClient = FakeApiClient

    try:
        refreshed = asyncio.run(manager.async_refresh_archive_detail(101, operation="refresh_archive_detail"))
    finally:
        manager_module.BambuddyApiClient = original_manager_api_client

    assert refreshed is not None
    assert refreshed["plate_id"] == 7


def test_variant3_manager_records_helper_recompute_diagnostics(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()

    manager._async_handle_helper_state_change(SimpleNamespace(data={"entity_id": "input_text.print_history_search"}))

    assert manager.recompute_stats["count"] >= 1
    assert manager.recompute_stats["last_reason"] == "state:input_text.print_history_search"
    assert manager.diagnostics()["recent_operations"][0]["type"] == "recompute"


def test_variant3_manager_debounces_helper_recomputes_when_loop_available(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_boolean.print_history_debug_instrumentation"] = "on"
    hass = FakeHass(tmp_path, state_map)
    hass.loop = FakeLoop()
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.archives = manager.store.load_archives()

    manager._async_handle_helper_state_change(SimpleNamespace(data={"entity_id": "input_text.print_history_search"}))
    manager._async_handle_helper_state_change(SimpleNamespace(data={"entity_id": "input_select.print_history_sort"}))

    assert manager.recompute_stats["count"] == 0
    assert manager._scheduled_recompute_handle is not None
    assert manager.recompute_scheduler_stats["request_count"] == 2
    assert manager.recompute_scheduler_stats["scheduled_count"] == 1
    assert manager.recompute_scheduler_stats["coalesced_count"] == 1

    manager._scheduled_recompute_handle.fire()

    assert manager.recompute_stats["count"] == 1
    assert manager.recompute_stats["last_reason"] == (
        "state_batch[2]:state:input_text.print_history_search|state:input_select.print_history_sort"
    )
    assert manager.recompute_scheduler_stats["executed_count"] == 1
    assert manager.diagnostics()["recompute_scheduler_stats"]["last_batch_size"] == 2


def test_variant3_manager_coalesces_service_refresh_requests(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_boolean.print_history_debug_instrumentation"] = "on"
    hass = FakeHass(tmp_path, state_map)
    hass.loop = FakeLoop()
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    refresh_reasons: list[str] = []

    async def fake_refresh(reason: str) -> None:
        refresh_reasons.append(reason)

    manager.async_refresh = fake_refresh
    hass.async_create_task = lambda coro: asyncio.run(coro)

    asyncio.run(manager.async_request_refresh("service", delay_seconds=1.0))
    asyncio.run(manager.async_request_refresh("service:save", delay_seconds=1.0))

    assert len(hass.loop.handles) == 1
    assert manager._scheduled_refresh_handle is hass.loop.handles[0]
    assert manager.refresh_scheduler_stats["request_count"] == 2
    assert manager.refresh_scheduler_stats["scheduled_count"] == 1
    assert manager.refresh_scheduler_stats["coalesced_count"] == 1

    hass.loop.handles[0].fire()

    assert refresh_reasons == ["refresh_batch[2]:service|service:save"]
    assert manager.refresh_scheduler_stats["executed_count"] == 1
    assert manager.diagnostics()["refresh_scheduler_stats"]["last_batch_size"] == 2


def test_variant3_manager_refresh_backfills_printer_names_from_printers_api(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()

    FakeApiClient.archives = [
        {
            "id": 101,
            "printer_id": 1,
            "print_name": "Hueforge Batman",
            "actual_time_seconds": 14400,
            "print_time_seconds": 15000,
            "filament_used_grams": 42.5,
            "filament_type": "PLA",
            "filament_color": "#112233,#ffffff",
            "status": "completed",
            "started_at": "2026-04-08T10:00:00Z",
            "completed_at": "2026-04-08T14:00:00Z",
            "created_at": "2026-04-08T09:58:00Z",
            "cost": 2.35,
            "object_count": 2,
            "layer_height": 0.16,
            "designer": "Jane",
            "is_favorite": True,
            "tags": "display,hueforge,s:123",
            "notes": "User note",
            "project_name": "Wall Art",
        }
    ]
    FakeApiClient.printers = [{"id": 1, "name": "Workshop P1S"}]
    FakeApiClient.projects = [{"id": 77, "name": "Wall Art", "status": "active"}]
    FakeApiClient.archive_stats = {"total_prints": 1}

    original_client = manager_module.BambuddyApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    try:
        asyncio.run(manager.async_refresh("test"))
    finally:
        manager_module.BambuddyApiClient = original_client

    assert manager.archives[0]["printer_name"] == "Workshop P1S"
    assert manager.project_options == [{"id": "77", "name": "Wall Art", "status": "active", "color": "", "label": "Wall Art"}]
    assert manager.last_refresh_archive_total_count == 1
    printer_option_calls = [
        call for call in hass.services.calls if call[0] == "input_select" and call[1] == "set_options"
    ]
    printer_options = next(
        call[2]["options"]
        for call in printer_option_calls
        if call[2]["entity_id"] == "input_select.print_history_filter_printer"
    )
    assert printer_options == ["All", "Workshop P1S"]


def test_variant3_manager_refresh_passes_date_bounds_to_archive_fetch(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_text.print_history_filter_start_date"] = "2026-04-01"
    state_map["input_text.print_history_filter_end_date"] = "2026-04-30"
    state_map["input_number.print_history_max_archives"] = "25"
    hass = FakeHass(tmp_path, state_map)
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()

    FakeApiClient.archives = []
    FakeApiClient.printers = []
    FakeApiClient.projects = []
    FakeApiClient.archive_stats = {"total_prints": 0}
    FakeApiClient.last_fetch_archives_kwargs = {}

    original_client = manager_module.BambuddyApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    try:
        asyncio.run(manager.async_refresh("test"))
    finally:
        manager_module.BambuddyApiClient = original_client

    assert FakeApiClient.last_fetch_archives_kwargs == {
        "limit": 25,
        "date_from": "2026-04-01",
        "date_to": "2026-04-30",
    }


def test_variant3_manager_refresh_does_not_reload_archives_from_store(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()

    FakeApiClient.archives = [
        {
            "id": 101,
            "printer_id": 1,
            "print_name": "Hueforge Batman",
            "actual_time_seconds": 14400,
            "print_time_seconds": 15000,
            "filament_used_grams": 42.5,
            "filament_type": "PLA",
            "filament_color": "#112233,#ffffff",
            "status": "completed",
            "started_at": "2026-04-08T10:00:00Z",
            "completed_at": "2026-04-08T14:00:00Z",
            "created_at": "2026-04-08T09:58:00Z",
            "cost": 2.35,
            "object_count": 2,
            "layer_height": 0.16,
            "designer": "Jane",
            "is_favorite": True,
            "tags": "display,hueforge,s:123",
            "notes": "User note",
            "project_name": "Wall Art",
        }
    ]
    FakeApiClient.printers = [{"id": 1, "name": "Workshop P1S"}]
    FakeApiClient.projects = []
    FakeApiClient.archive_stats = {"total_prints": 1}

    original_client = manager_module.BambuddyApiClient
    original_load_archives = manager.store.load_archives
    manager_module.BambuddyApiClient = FakeApiClient
    manager.store.load_archives = lambda: (_ for _ in ()).throw(AssertionError("load_archives should not run during refresh"))
    try:
        asyncio.run(manager.async_refresh("test"))
    finally:
        manager_module.BambuddyApiClient = original_client
        manager.store.load_archives = original_load_archives

    assert manager.archives[0]["printer_name"] == "Workshop P1S"
    assert manager.last_refresh_store_load_ms == 0.0
    assert manager.last_refresh_store_total_count == 1


def test_variant3_manager_limit_notice_reports_truncated_history(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_number.print_history_max_archives"] = "2"
    hass = FakeHass(tmp_path, state_map)
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(manager_module.project_archive))
    manager.archives = manager.store.load_archives()
    manager.last_refresh_archive_total_count = 5

    notice = manager.limit_notice

    assert notice["show"] is True
    assert notice["state"] == "truncated"
    assert notice["chip_label"] == "2 of 5"
    assert notice["missing_count"] == 3
    assert "not included in the local browser cache" in notice["popup_markdown"]


def test_variant3_manager_limit_notice_reports_incomplete_history(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_number.print_history_max_archives"] = "20"
    hass = FakeHass(tmp_path, state_map)
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    template_archives = _projected_archives(manager_module.project_archive)
    archives: list[dict[str, object]] = []
    for index in range(10):
        source = dict(template_archives[index % len(template_archives)])
        source["id"] = 2000 + index
        archives.append(source)
    manager.store.replace_archives(archives)
    manager.archives = manager.store.load_archives()
    manager.last_refresh_archive_total_count = 12

    notice = manager.limit_notice

    assert notice["show"] is True
    assert notice["state"] == "incomplete"
    assert notice["chip_label"] == "10 of 12"
    assert notice["expected_cached_count"] == 12
    assert "expected cache entries are missing" in notice["popup_markdown"]


def test_variant3_manager_limit_notice_reports_near_limit(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    state_map = _default_state_map()
    state_map["input_number.print_history_max_archives"] = "20"
    hass = FakeHass(tmp_path, state_map)
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    template_archives = _projected_archives(manager_module.project_archive)
    archives: list[dict[str, object]] = []
    for index in range(18):
        source = dict(template_archives[index % len(template_archives)])
        source["id"] = 1000 + index
        archives.append(source)
    manager.store.replace_archives(archives)
    manager.archives = manager.store.load_archives()
    manager.last_refresh_archive_total_count = 18

    notice = manager.limit_notice

    assert notice["show"] is True
    assert notice["state"] == "near_limit"
    assert notice["chip_label"] == "18 of 20"
    assert "Only **2** cache slots remain" in notice["popup_markdown"]


def test_variant3_manager_refresh_cools_down_after_store_open_failure(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()

    FakeApiClient.archives = _projected_archives(manager_module.project_archive)
    FakeApiClient.printers = []

    original_client = manager_module.BambuddyApiClient
    original_replace_archives = manager.store.replace_archives
    calls = {"count": 0}

    def failing_replace_archives(_archives: list[dict]) -> None:
        calls["count"] += 1
        raise sqlite3.OperationalError("unable to open database file (db_path=/config/.storage/bambuddy_print_history_browser.db)")

    manager_module.BambuddyApiClient = FakeApiClient
    manager.store.replace_archives = failing_replace_archives
    try:
        asyncio.run(manager.async_refresh("test"))
        asyncio.run(manager.async_refresh("retry"))
    finally:
        manager_module.BambuddyApiClient = original_client
        manager.store.replace_archives = original_replace_archives

    assert calls["count"] == 1
    assert manager.status_state == "error"
    assert "cooldown remaining" in manager.status_message


def test_variant3_manager_detail_response_includes_normalized_event_timeline(tmp_path: Path) -> None:
    _const_module, query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)
    manager.store.initialize()
    manager.store.replace_archives(_projected_archives(query_module.project_archive))
    manager.store.append_archive_event(
        101,
        event_type="objects_skipped",
        event_source="ha_script",
        event_time="2026-04-08T12:00:00Z",
        event_status="printing",
        payload={"skipped_ids": [7]},
    )
    manager.store.append_archive_event(
        101,
        event_type="enrichment_applied",
        event_source="ha_script",
        event_time="2026-04-08T12:05:00Z",
        event_status="completed",
    )
    manager.store.save_archive_skip_overlay_state(
        101,
        {
            "overlay_version": "v1",
            "plate_number": 2,
            "pick_image_asset_path": "Metadata/pick_2.png",
            "skipped_ids": [7],
        },
    )

    detail = manager.build_archive_detail_response(101)

    assert detail is not None
    assert detail["event_timeline"][0]["type"] == "objects_skipped"
    assert detail["event_timeline"][0]["label"] == "Objects skipped"
    assert detail["event_timeline"][0]["color_key"] == "neutral"
    assert detail["event_timeline"][1]["type"] == "enrichment_applied"
    assert detail["event_timeline"][1]["label"] == "Enrichment applied"
    assert detail["event_timeline"][1]["color_key"] == "enrichment"
    assert detail["skip_overlay_state"]["pick_image_asset_path"] == "/api/bambuddy/print-history/archive/101/pick-image?plate=2"


def test_live_enrichment_automation_appends_timeline_events() -> None:
    automation_content = (
        HOMEASSISTANT_ROOT
        / "packages"
        / "3d_printing"
        / "print_history"
        / "automations"
        / "bambuddy_enrich_archive_on_complete.yaml"
    ).read_text("utf-8")

    assert "- action: bambuddy.append_print_history_event" in automation_content
    assert "event_type: enrichment_applied" in automation_content
    assert "enrichment_applied:{{ archive_id }}:{{ 'terminal_reconciliation' if is_terminal_trigger else 'during_print' }}" in automation_content
    assert "mode: \"{{ 'terminal_reconciliation' if is_terminal_trigger else 'during_print' }}\"" in automation_content
    assert 'terminal_noop_reconciliation' in automation_content
    assert 'Skipped duplicate enrichment write and timeline event.' in automation_content


def test_variant3_manager_project_options_disambiguate_duplicate_names(tmp_path: Path) -> None:
    _const_module, _query_module, manager_module, _init_module = _import_component_modules()

    hass = FakeHass(tmp_path, _default_state_map())
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        entry_id="entry-1",
        data={"base_url": "http://example.local", "api_key": "token"},
        options={},
    )
    manager = manager_module.PrintHistoryBrowserManager(hass, entry)

    options = manager._project_options_from_projects(
        [
            {"id": 100, "name": "Controller Box", "status": "active"},
            {"id": 200, "name": "Controller Box", "status": "archived"},
            {"id": 300, "name": "Moon Lamp", "status": "active"},
        ]
    )

    assert options == [
        {"id": "100", "name": "Controller Box", "status": "active", "color": "", "label": "Controller Box [100]"},
        {"id": "200", "name": "Controller Box", "status": "archived", "color": "", "label": "Controller Box [200]"},
        {"id": "300", "name": "Moon Lamp", "status": "active", "color": "", "label": "Moon Lamp"},
    ]