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

    aiohttp_module.ClientResponseError = ClientResponseError
    aiohttp_module.ClientSession = ClientSession
    aiohttp_module.ClientTimeout = ClientTimeout

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

    homeassistant_module.components = components_module
    homeassistant_module.config_entries = config_entries_module
    homeassistant_module.const = const_module
    homeassistant_module.core = core_module
    homeassistant_module.helpers = helpers_module
    homeassistant_module.util = util_module
    components_module.websocket_api = websocket_api_module

    sys.modules["voluptuous"] = voluptuous_module
    sys.modules["aiohttp"] = aiohttp_module
    sys.modules["homeassistant"] = homeassistant_module
    sys.modules["homeassistant.components"] = components_module
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


class FakeApiClient:
    archives: list[dict] = []
    printers: list[dict] = []

    def __init__(self, _session, _base_url: str, _api_key: str, _timeout_seconds: int) -> None:
        pass

    async def async_fetch_archives(self, *, limit: int) -> list[dict[str, object]]:
        return [dict(item) for item in self.archives[:limit]]

    async def async_fetch_printers(self) -> list[dict[str, object]]:
        return [dict(item) for item in self.printers]


class FakeRuntimeRepairClient:
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
        self.data: dict[str, object] = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        return coro


def _default_state_map() -> dict[str, str]:
    return {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
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
    manager._recompute_query()
    hass.data[const_module.DOMAIN] = {entry.entry_id: {const_module.DATA_MANAGER: manager}}

    asyncio.run(init_module.async_setup(hass, {}))

    registered = set(hass.services._handlers)
    assert (const_module.DOMAIN, const_module.SERVICE_REFRESH_PRINT_HISTORY_BROWSER) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_QUERY_PRINT_HISTORY_BROWSER) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_APPEND_PRINT_HISTORY_EVENT) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REVIEW_STATE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE) in registered
    assert (const_module.DOMAIN, const_module.SERVICE_ESTIMATE_PARTIAL_USAGE) in registered

    original_runtime_repair_client = init_module.BambuddyRuntimeRepairClient
    init_module.BambuddyRuntimeRepairClient = FakeRuntimeRepairClient

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

    assert query_response["entry_id"] == "entry-1"
    assert query_response["archives"][0]["id"] == 101
    assert len(activity_query_response["activity_rows"]) == 2
    assert detail_response["archive_id"] == 101
    assert detail_response["archive"]["print_name"] == "Hueforge Batman"
    assert append_event_response["event_timeline"][0]["type"] == "photo_captured"
    assert append_event_response["event_timeline"][0]["label"] == "Photo captured"
    assert review_response["review_state"]["review_status"] == "reviewed"
    assert review_response["review_state"]["mismatch_flags"] == "color_mismatch"
    assert lineage_response["repair_lineage"][0]["relation_type"] == "derived_from"
    assert delete_response["deleted"] == 1
    assert estimate_response["success"] is True
    assert estimate_response["estimate"]["totals"]["estimated_used_g_total"] == 12.5
    assert estimate_response["estimate"]["dedupe"]["dedupe_key"] == "101:failed:4:42.5"


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

    original_client = manager_module.BambuddyApiClient
    manager_module.BambuddyApiClient = FakeApiClient
    try:
        asyncio.run(manager.async_refresh("test"))
    finally:
        manager_module.BambuddyApiClient = original_client

    assert manager.archives[0]["printer_name"] == "Workshop P1S"
    printer_option_calls = [
        call for call in hass.services.calls if call[0] == "input_select" and call[1] == "set_options"
    ]
    printer_options = next(
        call[2]["options"]
        for call in printer_option_calls
        if call[2]["entity_id"] == "input_select.print_history_filter_printer"
    )
    assert printer_options == ["All", "Workshop P1S"]


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
        event_type="print_finished",
        event_source="bambuddy_webhook",
        event_time="2026-04-08T14:00:00Z",
        event_status="completed",
    )

    detail = manager.build_archive_detail_response(101)

    assert detail is not None
    assert detail["event_timeline"][0]["type"] == "print_finished"
    assert detail["event_timeline"][0]["label"] == "Print finished"
    assert detail["event_timeline"][0]["color_key"] == "success"