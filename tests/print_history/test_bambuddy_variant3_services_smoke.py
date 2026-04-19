from __future__ import annotations

import asyncio
import importlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
HOMEASSISTANT_ROOT = REPO_ROOT / "homeassistant"


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
    websocket_api_module.async_register_command = lambda hass, handler: None
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
    last_fetch_archives_kwargs: dict[str, object] = {}
    uploaded_photos: list[dict[str, object]] = []
    uploaded_replacements: list[dict[str, object]] = []
    deleted_archives: list[int] = []
    updated_archives: list[dict[str, object]] = []
    toggled_favorites: list[int] = []

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

    async def async_fetch_projects(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.projects]

    async def async_fetch_archive_stats(self) -> dict[str, object]:
        return dict(self.archive_stats)

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
    restore_from_calls: list[dict[str, object]] = []
    restore_verify_calls: list[dict[str, object]] = []

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
        "input_boolean.bambuddy_integration_enabled": "on",
        "input_boolean.bambuddy_history_sync_enabled": "on",
    }


def _projected_archives(project_archive) -> list[dict]:
    raw = [
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
    state_map["input_select.print_history_filter_duplicates"] = "Duplicates Only"
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

    response = manager.build_query_response({"duplicates": "Duplicates Only"})

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
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_APPEND_PRINT_HISTORY_EVENT) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REVIEW_STATE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_ARCHIVE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_ESTIMATE_PARTIAL_USAGE) in registered
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
        update_response = asyncio.run(
            hass.services.handler(const_module.DOMAIN, const_module.SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE)(
                SimpleNamespace(data={"archive_id": 101, "tags": "display,verified"})
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
                        "event_type": "photo_captured",
                        "event_source": "ha_script",
                        "event_time": "2026-04-10T00:02:00Z",
                        "event_status": "verified",
                        "payload": {"stage": "finish"},
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
    assert activity_query_response["activity_rows"][0]["primary_photo_path"] == ""
    assert detail_response["archive_id"] == 101
    assert detail_response["archive"]["print_name"] == "Hueforge Batman"
    assert detail_response["archive"]["effective_duration_seconds"] == 14400
    assert detail_response["archive"]["primary_photo_path"] == ""
    assert update_response["archive"]["tags"] == "display,verified"
    assert favorite_response["archive"]["is_favorite"] is True
    assert primary_photo_response["primary_photo_selection"]["photo_path"] == "topdown-closeup.jpg"
    assert primary_photo_response["archive"]["primary_photo_path"] == "topdown-closeup.jpg"
    assert append_event_response["event_timeline"][0]["type"] == "photo_captured"
    assert append_event_response["event_timeline"][0]["label"] == "Photo captured"
    assert review_response["review_state"]["review_status"] == "reviewed"
    assert review_response["review_state"]["mismatch_flags"] == "color_mismatch"
    assert lineage_response["repair_lineage"][0]["relation_type"] == "derived_from"
    assert delete_response["deleted"] == 1
    assert delete_archive_response["deleted"] == 1
    assert FakeApiClient.deleted_archives == [202]
    assert FakeApiClient.updated_archives == [{"archive_id": 101, "payload": {"tags": "display,verified"}}]
    assert FakeApiClient.toggled_favorites == [202]
    assert manager.store.load_archive(202) is None
    assert manager.last_refresh_store_total_count == 1
    assert manager.last_refresh_archive_total_count == 1
    assert estimate_response["success"] is True
    assert estimate_response["estimate"]["totals"]["estimated_used_g_total"] == 12.5
    assert estimate_response["estimate"]["dedupe"]["dedupe_key"] == "101:failed:4:42.5"
    assert manager.query_stats["count"] == 2
    assert manager.query_stats["last_source"] == "service"
    assert manager.result.page_items[0]["primary_photo_path"] == "topdown-closeup.jpg"
    assert manager.mutation_stats["count"] == 11
    assert manager.mutation_stats["last_operation"] == "delete_print_history_archive"


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
    assert manager.project_options == [{"id": "77", "name": "Wall Art", "status": "active", "label": "Wall Art"}]
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
        event_type="photo_captured",
        event_source="ha_script",
        event_time="2026-04-08T12:00:00Z",
        event_status="printing",
    )
    manager.store.append_archive_event(
        101,
        event_type="enrichment_applied",
        event_source="ha_script",
        event_time="2026-04-08T12:05:00Z",
        event_status="completed",
    )

    detail = manager.build_archive_detail_response(101)

    assert detail is not None
    assert detail["event_timeline"][0]["type"] == "photo_captured"
    assert detail["event_timeline"][0]["label"] == "Photo captured"
    assert detail["event_timeline"][0]["color_key"] == "media"
    assert detail["event_timeline"][1]["type"] == "enrichment_applied"
    assert detail["event_timeline"][1]["label"] == "Enrichment applied"
    assert detail["event_timeline"][1]["color_key"] == "enrichment"


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
        {"id": "100", "name": "Controller Box", "status": "active", "label": "Controller Box [100]"},
        {"id": "200", "name": "Controller Box", "status": "archived", "label": "Controller Box [200]"},
        {"id": "300", "name": "Moon Lamp", "status": "active", "label": "Moon Lamp"},
    ]