from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import BambuddyApiClient
from .const import (
    BROWSER_HELPER_ENTITY_IDS,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_FETCH_TIMEOUT_SECONDS,
    CONF_SCAN_INTERVAL_SECONDS,
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    EVENT_BAMBUDDY_WEBHOOK,
    OPTION_SET_HELPERS,
    REFRESH_TRIGGER_HELPERS,
    REFRESH_WEBHOOK_EVENTS,
    STORE_FILENAME,
)
from .print_history.query import QueryResult, option_sets, project_archive, query_archives
from .print_history.store import PrintHistoryStore


_LOGGER = logging.getLogger(__name__)


QUERY_OVERRIDE_ENTITY_MAP = {
    "status": "input_select.print_history_filter_status",
    "enrichment_status": "input_select.print_history_filter_enrichment_status",
    "material": "input_select.print_history_filter_material",
    "printer": "input_select.print_history_filter_printer",
    "date_range": "input_select.print_history_filter_date_range",
    "designer": "input_select.print_history_filter_designer",
    "project": "input_select.print_history_filter_project",
    "layer_height": "input_select.print_history_filter_layer_height",
    "tag": "input_select.print_history_filter_tag",
    "favorites_only": "input_boolean.print_history_filter_favorites_only",
    "search": "input_text.print_history_search",
    "colors": "input_text.print_history_filter_colors",
    "selected_day": "input_text.print_history_activity_selected_date",
    "activity_metric": "input_select.print_history_activity_metric",
    "sort": "input_select.print_history_sort",
    "page": "input_number.history_current_page",
    "page_size": "input_number.print_history_page_size",
}


class PrintHistoryBrowserManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = PrintHistoryStore(Path(hass.config.path(".storage", STORE_FILENAME)))
        self.archives: list[dict[str, Any]] = []
        self.result = query_archives([], self._state_snapshot())
        self.activity_summary: dict[str, Any] = {"archive_count": 0, "active_day_count": 0, "latest_archive_id": 0}
        self.browser_revision = 0
        self.status_state = "initializing"
        self.status_message = "Initializing Bambuddy print history browser"
        self.last_refresh: str | None = None
        self.last_error = ""
        self.loaded_at: str | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribers: list[Callable[[], None]] = []

    async def async_initialize(self) -> None:
        await self.hass.async_add_executor_job(self.store.initialize)
        _LOGGER.info("Initialized Bambuddy local store at %s", self.store._db_path)
        self.archives = await self.hass.async_add_executor_job(self.store.load_archives)
        if self._recompute_query():
            self.browser_revision += 1

        self._unsubscribers.append(
            async_track_state_change_event(self.hass, BROWSER_HELPER_ENTITY_IDS, self._async_handle_helper_state_change)
        )
        self._unsubscribers.append(self.hass.bus.async_listen(EVENT_BAMBUDDY_WEBHOOK, self._async_handle_webhook_event))
        self._unsubscribers.append(
            async_track_time_interval(
                self.hass,
                self._async_handle_interval_refresh,
                timedelta(seconds=self._scan_interval_seconds),
            )
        )

        await self._async_sync_options()
        self._set_status("ready" if self.archives else "refreshing", "Loaded local print history cache")
        self._notify_listeners()
        self.hass.async_create_task(self.async_refresh("startup"))

    async def async_shutdown(self) -> None:
        _LOGGER.debug("Shutting down Bambuddy print history browser manager")
        while self._unsubscribers:
            self._unsubscribers.pop()()
        self._listeners.clear()

    @property
    def enabled(self) -> bool:
        integration_enabled = self.hass.states.get("input_boolean.bambuddy_integration_enabled")
        history_sync_enabled = self.hass.states.get("input_boolean.bambuddy_history_sync_enabled")
        if integration_enabled is None and history_sync_enabled is None:
            return True
        if integration_enabled is None:
            return history_sync_enabled.state == "on"
        if history_sync_enabled is None:
            return integration_enabled.state == "on"
        return integration_enabled.state == "on" and history_sync_enabled.state == "on"

    @property
    def max_archives(self) -> int:
        state = self.hass.states.get("input_number.print_history_max_archives")
        if state is None:
            return 500
        try:
            return max(1, int(float(state.state)))
        except (TypeError, ValueError):
            return 500

    @property
    def fetch_timeout_seconds(self) -> int:
        return int(
            self.entry.options.get(
                CONF_FETCH_TIMEOUT_SECONDS,
                self.entry.data.get(CONF_FETCH_TIMEOUT_SECONDS, DEFAULT_FETCH_TIMEOUT_SECONDS),
            )
        )

    @property
    def scan_interval_seconds(self) -> int:
        return int(
            self.entry.options.get(
                CONF_SCAN_INTERVAL_SECONDS,
                self.entry.data.get(CONF_SCAN_INTERVAL_SECONDS, DEFAULT_SCAN_INTERVAL_SECONDS),
            )
        )

    @property
    def base_url(self) -> str:
        return str(self.entry.options.get(CONF_BASE_URL, self.entry.data.get(CONF_BASE_URL, "")))

    @property
    def api_key(self) -> str:
        return str(self.entry.options.get(CONF_API_KEY, self.entry.data.get(CONF_API_KEY, "")))

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    async def async_refresh(self, reason: str) -> None:
        if not self.enabled:
            self._set_status("disabled", "Bambuddy print history browser is disabled by helper")
            self._notify_listeners()
            return

        _LOGGER.info("Refreshing Bambuddy print history browser (%s)", reason)
        self._set_status("refreshing", f"Refreshing Bambuddy print history browser ({reason})")
        self._notify_listeners()

        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = BambuddyApiClient(
                session,
                self.base_url,
                self.api_key,
                self.fetch_timeout_seconds,
            )
            raw_archives = await client.async_fetch_archives(limit=self.max_archives)
            raw_printers: list[dict[str, Any]] = []
            try:
                raw_printers = await client.async_fetch_printers()
            except Exception as error:  # noqa: BLE001
                _LOGGER.warning(
                    "Unable to fetch Bambuddy printers while refreshing print history; falling back to archive payload names: %s",
                    error,
                )
            enriched_archives = self._enrich_archives_with_printer_names(raw_archives, raw_printers)
            projected = [project_archive(item) for item in enriched_archives]
            archives_changed = projected != self.archives
            await self.hass.async_add_executor_job(self.store.replace_archives, projected)
            self.archives = await self.hass.async_add_executor_job(self.store.load_archives)
            self.last_refresh = dt_util.utcnow().isoformat()
            self.last_error = ""
            query_changed = self._recompute_query()
            if archives_changed or query_changed:
                self.browser_revision += 1
            await self._async_sync_options()
            self._set_status("ready", f"Refreshed Bambuddy print history browser ({reason})")
            _LOGGER.info("Refreshed Bambuddy print history browser (%s) with %s archives", reason, len(self.archives))
        except Exception as error:  # noqa: BLE001
            self.last_error = str(error)
            self._set_status("error", str(error))
            _LOGGER.exception("Failed to refresh Bambuddy print history browser (%s)", reason)

        self._notify_listeners()

    def build_query_response(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        merged_overrides = dict(overrides or {})
        include_activity_rows = bool(merged_overrides.pop("include_activity_rows", False))
        states = self._merged_state_snapshot(merged_overrides)
        debug_enabled = states.get("input_boolean.print_history_debug_instrumentation", "off") == "on"

        total_started = perf_counter()
        query_started = perf_counter()
        result = self.store.load_query_result(states)
        query_ms = round((perf_counter() - query_started) * 1000, 1)

        archive_ids = [int(archive.get("id")) for archive in result.page_items if int(archive.get("id") or 0) > 0]

        annotations_started = perf_counter()
        annotations = self.store.load_query_annotations(archive_ids)
        annotations_ms = round((perf_counter() - annotations_started) * 1000, 1)

        response = {
            "archive_count": self.activity_summary.get("archive_count", len(self.archives)),
            "query": {
                "filtered_count": result.filtered_count,
                "total_pages": result.total_pages,
                "current_page": result.current_page,
                "page_info": result.page_info,
                "has_active_filters": result.has_active_filters,
                "active_filters": result.active_filters,
                "available_colors": result.available_colors,
                "available_color_tooltips": result.available_color_tooltips,
                "activity_active_days_label": result.activity_active_days_label,
                "activity_metric_total_label": result.activity_metric_total_label,
            },
            "archives": result.page_items,
            **annotations,
            "store": self.store.load_store_stats(),
        }
        activity_rows_ms = 0.0
        activity_row_count = 0
        if include_activity_rows:
            activity_states = dict(states)
            activity_states["input_text.print_history_activity_selected_date"] = ""
            activity_started = perf_counter()
            response["activity_rows"] = self.store.load_activity_rows(activity_states)
            activity_rows_ms = round((perf_counter() - activity_started) * 1000, 1)
            activity_row_count = len(response["activity_rows"])

        if debug_enabled:
            response["debug"] = {
                "enabled": True,
                "query_ms": query_ms,
                "annotations_ms": annotations_ms,
                "activity_rows_ms": activity_rows_ms,
                "total_ms": round((perf_counter() - total_started) * 1000, 1),
                "include_activity_rows": include_activity_rows,
                "page_item_count": len(result.page_items),
                "filtered_count": result.filtered_count,
                "activity_row_count": activity_row_count,
                "timestamp": dt_util.utcnow().isoformat(),
            }
        return response

    def build_archive_detail_response(self, archive_id: int) -> dict[str, Any] | None:
        archive = self.store.load_archive(archive_id)
        if archive is None:
            return None
        return {
            "archive": archive,
            "note_payload_rows": self.store.load_note_payload_rows(archive_id),
            "review_state": self.store.load_review_state(archive_id),
            "repair_lineage": self.store.load_repair_lineage(archive_id),
            "sync": self.store.load_sync_metadata(archive_id),
            "store": self.store.load_store_stats(),
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "status_state": self.status_state,
            "status_message": self.status_message,
            "last_refresh": self.last_refresh,
            "last_error": self.last_error,
            "enabled": self.enabled,
            "archive_count": len(self.archives),
            "query": {
                "filtered_count": self.result.filtered_count,
                "total_pages": self.result.total_pages,
                "current_page": self.result.current_page,
            },
            "store": self.store.load_store_stats(),
        }

    def _state_snapshot(self) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for entity_id in BROWSER_HELPER_ENTITY_IDS:
            state = self.hass.states.get(entity_id)
            snapshot[entity_id] = "" if state is None else state.state
        return snapshot

    def _enrich_archives_with_printer_names(
        self,
        raw_archives: list[dict[str, Any]],
        raw_printers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        printer_names = self._printer_name_by_id(raw_printers)
        if not printer_names:
            return list(raw_archives)

        enriched_archives: list[dict[str, Any]] = []
        for archive in raw_archives:
            printer_name = str(archive.get("printer_name") or "").strip()
            printer_id = str(archive.get("printer_id") or "").strip()
            resolved_printer_name = printer_names.get(printer_id, "")
            if printer_name or not resolved_printer_name:
                enriched_archives.append(archive)
                continue

            enriched_archive = dict(archive)
            enriched_archive["printer_name"] = resolved_printer_name
            enriched_archives.append(enriched_archive)

        return enriched_archives

    def _printer_name_by_id(self, raw_printers: list[dict[str, Any]]) -> dict[str, str]:
        printer_names: dict[str, str] = {}
        for printer in raw_printers:
            printer_id = str(printer.get("id") or printer.get("printer_id") or "").strip()
            printer_name = str(printer.get("name") or printer.get("printer_name") or "").strip()
            if not printer_id or not printer_name or printer_id in printer_names:
                continue
            printer_names[printer_id] = printer_name
        return printer_names

    def _recompute_query(self) -> bool:
        next_result = self.store.load_query_result(self._state_snapshot())
        next_activity_summary = self.store.load_activity_summary()
        changed = next_result != self.result or next_activity_summary != self.activity_summary
        self.result = next_result
        self.activity_summary = next_activity_summary
        if changed:
            self.loaded_at = dt_util.utcnow().isoformat()
        return changed

    def _merged_state_snapshot(self, overrides: dict[str, Any]) -> dict[str, str]:
        snapshot = self._state_snapshot()
        for field_name, entity_id in QUERY_OVERRIDE_ENTITY_MAP.items():
            if field_name not in overrides or overrides[field_name] is None:
                continue
            value = overrides[field_name]
            if field_name == "favorites_only":
                snapshot[entity_id] = "on" if bool(value) else "off"
                continue
            if field_name in {"page", "page_size"}:
                snapshot[entity_id] = str(int(value))
                continue
            if field_name == "colors" and isinstance(value, list):
                snapshot[entity_id] = ",".join(str(item).strip() for item in value if str(item).strip())
                continue
            snapshot[entity_id] = str(value)
        return snapshot

    async def _async_sync_options(self) -> None:
        for entity_id, options in option_sets(self.archives).items():
            if entity_id not in OPTION_SET_HELPERS:
                continue
            if self.hass.states.get(entity_id) is None:
                continue
            await self.hass.services.async_call(
                "input_select",
                "set_options",
                {"entity_id": entity_id, "options": options},
                blocking=True,
            )

    @callback
    def _async_handle_helper_state_change(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        if entity_id in REFRESH_TRIGGER_HELPERS:
            self.hass.async_create_task(self.async_refresh(f"state:{entity_id}"))
            return

        if entity_id in OPTION_SET_HELPERS and self.archives:
            self.hass.async_create_task(self._async_sync_options())

        if self._recompute_query():
            self.browser_revision += 1
        self._notify_listeners()

    @callback
    def _async_handle_webhook_event(self, event: Event) -> None:
        event_type = str((event.data or {}).get("event", "")).strip().lower()
        if event_type in REFRESH_WEBHOOK_EVENTS:
            self.hass.async_create_task(self.async_refresh(f"webhook:{event_type}"))

    @callback
    def _async_handle_interval_refresh(self, _now: Any) -> None:
        self.hass.async_create_task(self.async_refresh("interval"))

    def _set_status(self, state: str, message: str) -> None:
        self.status_state = state
        self.status_message = message

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    @property
    def _scan_interval_seconds(self) -> int:
        return max(1, self.scan_interval_seconds)