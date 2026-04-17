from __future__ import annotations

import asyncio
from collections import deque
from datetime import timedelta
import logging
from pathlib import Path
import sqlite3
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
from .print_history.query import QueryResult, as_int, as_text, normalize_filter_date_value, normalize_status, option_sets, project_archive, query_archives
from .print_history.store import PrintHistoryStore


_LOGGER = logging.getLogger(__name__)

SLOW_QUERY_THRESHOLD_MS = 500.0
SLOW_RECOMPUTE_THRESHOLD_MS = 250.0
SLOW_MUTATION_THRESHOLD_MS = 200.0
RECENT_OPERATION_LIMIT = 15
HELPER_RECOMPUTE_DEBOUNCE_SECONDS = 0.2
SERVICE_REFRESH_COALESCE_SECONDS = 1.0

EVENT_LABELS = {
    "print_started": "Print started",
    "print_paused": "Print paused",
    "print_resumed": "Print resumed",
    "print_finished": "Print finished",
    "print_failed": "Print failed",
    "print_stopped": "Print stopped",
    "photo_captured": "Photo captured",
    "enrichment_applied": "Enrichment applied",
    "repair_applied": "Repair applied",
}

EVENT_COLOR_KEYS = {
    "print_started": "start",
    "print_paused": "pause",
    "print_resumed": "resume",
    "print_finished": "success",
    "print_failed": "failure",
    "print_stopped": "failure",
    "photo_captured": "media",
    "enrichment_applied": "enrichment",
    "repair_applied": "repair",
}


QUERY_OVERRIDE_ENTITY_MAP = {
    "status": "input_select.print_history_filter_status",
    "archive_error": "input_select.print_history_filter_archive_error",
    "enrichment_status": "input_select.print_history_filter_enrichment_status",
    "material": "input_select.print_history_filter_material",
    "duplicates": "input_select.print_history_filter_duplicates",
    "printer": "input_select.print_history_filter_printer",
    "date_range": "input_select.print_history_filter_date_range",
    "start_date": "input_text.print_history_filter_start_date",
    "end_date": "input_text.print_history_filter_end_date",
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
        self.last_refresh_reason = ""
        self.last_refresh_started_at: str | None = None
        self.last_refresh_duration_ms: float = 0.0
        self.last_refresh_fetch_ms: float = 0.0
        self.last_refresh_store_replace_ms: float = 0.0
        self.last_refresh_store_load_ms: float = 0.0
        self.last_refresh_store_total_count: int = 0
        self.last_refresh_store_inserted_count: int = 0
        self.last_refresh_store_updated_count: int = 0
        self.last_refresh_store_unchanged_count: int = 0
        self.last_refresh_store_removed_count: int = 0
        self.last_refresh_store_fast_unchanged_count: int = 0
        self.last_refresh_store_serialized_count: int = 0
        self.last_refresh_archive_count: int = 0
        self.last_refresh_archive_total_count: int | None = None
        self.last_refresh_printer_count: int = 0
        self.last_refresh_project_count: int = 0
        self.project_options: list[dict[str, str]] = []
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribers: list[Callable[[], None]] = []
        self._refresh_lock = asyncio.Lock()
        self._store_unavailable_until = None
        self._scheduled_refresh_handle: asyncio.TimerHandle | None = None
        self._scheduled_refresh_reasons: list[str] = []
        self._scheduled_recompute_handle: asyncio.TimerHandle | None = None
        self._scheduled_recompute_reasons: list[str] = []
        self.query_stats: dict[str, Any] = {
            "count": 0,
            "slow_count": 0,
            "last_source": "",
            "last_total_ms": 0.0,
            "last_query_ms": 0.0,
            "last_annotations_ms": 0.0,
            "last_metric_aggregate_ms": 0.0,
            "last_activity_rows_ms": 0.0,
            "last_filtered_count": 0,
            "last_matching_archive_count": 0,
            "last_page_item_count": 0,
            "last_metric_archive_count": 0,
            "last_activity_row_count": 0,
            "last_include_activity_rows": False,
            "last_timestamp": "",
            "max_total_ms": 0.0,
        }
        self.recompute_stats: dict[str, Any] = {
            "count": 0,
            "slow_count": 0,
            "last_reason": "",
            "last_duration_ms": 0.0,
            "last_changed": False,
            "last_timestamp": "",
            "max_duration_ms": 0.0,
        }
        self.mutation_stats: dict[str, Any] = {
            "count": 0,
            "slow_count": 0,
            "last_operation": "",
            "last_archive_id": 0,
            "last_duration_ms": 0.0,
            "last_timestamp": "",
            "max_duration_ms": 0.0,
        }
        self.refresh_scheduler_stats: dict[str, Any] = {
            "request_count": 0,
            "immediate_count": 0,
            "scheduled_count": 0,
            "coalesced_count": 0,
            "executed_count": 0,
            "rescheduled_while_locked_count": 0,
            "last_reason": "",
            "last_batch_reason": "",
            "last_batch_size": 0,
            "last_timestamp": "",
        }
        self.recompute_scheduler_stats: dict[str, Any] = {
            "request_count": 0,
            "immediate_count": 0,
            "scheduled_count": 0,
            "coalesced_count": 0,
            "executed_count": 0,
            "suppressed_due_refresh_count": 0,
            "last_reason": "",
            "last_batch_reason": "",
            "last_batch_size": 0,
            "last_timestamp": "",
        }
        self._recent_operations: deque[dict[str, Any]] = deque(maxlen=RECENT_OPERATION_LIMIT)

    async def async_initialize(self) -> None:
        await self.hass.async_add_executor_job(self.store.initialize)
        _LOGGER.info("Initialized Bambuddy local store at %s", self.store._db_path)
        self.archives = await self.hass.async_add_executor_job(self.store.load_archives)
        if self._recompute_query("initialize"):
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
    await self._async_sync_media_review_helper()
        self._set_status("ready" if self.archives else "refreshing", "Loaded local print history cache")
        self._notify_listeners()
        self.hass.async_create_task(self.async_refresh("startup"))

    async def async_shutdown(self) -> None:
        _LOGGER.debug("Shutting down Bambuddy print history browser manager")
        self._cancel_scheduled_refresh()
        self._cancel_scheduled_recompute()
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

    async def async_request_refresh(self, reason: str, *, delay_seconds: float = 0.0) -> None:
        self._record_scheduler_request(self.refresh_scheduler_stats, reason)
        self._cancel_scheduled_recompute()
        if delay_seconds <= 0 or self._scheduler_loop is None:
            self.refresh_scheduler_stats["immediate_count"] += 1
            await self.async_refresh(reason)
            return

        self._append_unique_reason(self._scheduled_refresh_reasons, reason)
        if self._scheduled_refresh_handle is not None:
            self.refresh_scheduler_stats["coalesced_count"] += 1
            self._record_debug_scheduler_event("refresh_coalesced", reason=reason, pending_reasons=list(self._scheduled_refresh_reasons))
            return

        self.refresh_scheduler_stats["scheduled_count"] += 1
        self._scheduled_refresh_handle = self._scheduler_loop.call_later(
            delay_seconds,
            self._async_execute_scheduled_refresh,
        )
        self._record_debug_scheduler_event(
            "refresh_scheduled",
            reason=reason,
            delay_seconds=delay_seconds,
            pending_reasons=list(self._scheduled_refresh_reasons),
        )

    async def async_refresh(self, reason: str) -> None:
        if not self.enabled:
            self._set_status("disabled", "Bambuddy print history browser is disabled by helper")
            self._notify_listeners()
            return

        now = dt_util.utcnow()
        if self._store_unavailable_until is not None and now < self._store_unavailable_until:
            remaining_seconds = max(
                1,
                int((self._store_unavailable_until - now).total_seconds()),
            )
            message = (
                "Skipping Bambuddy print history browser refresh while the local store is unavailable "
                f"({remaining_seconds}s cooldown remaining)"
            )
            self.last_error = message
            self._set_status("error", message)
            _LOGGER.warning("%s; reason=%s", message, reason)
            self._notify_listeners()
            return

        if self._refresh_lock.locked():
            _LOGGER.info("Skipping Bambuddy print history browser refresh (%s) because another refresh is already running", reason)
            if self._scheduler_loop is not None:
                self._append_unique_reason(self._scheduled_refresh_reasons, reason)
                if self._scheduled_refresh_handle is None:
                    self.refresh_scheduler_stats["scheduled_count"] += 1
                    self.refresh_scheduler_stats["rescheduled_while_locked_count"] += 1
                    self._scheduled_refresh_handle = self._scheduler_loop.call_later(
                        SERVICE_REFRESH_COALESCE_SECONDS,
                        self._async_execute_scheduled_refresh,
                    )
                    self._record_debug_scheduler_event(
                        "refresh_rescheduled_while_locked",
                        reason=reason,
                        delay_seconds=SERVICE_REFRESH_COALESCE_SECONDS,
                        pending_reasons=list(self._scheduled_refresh_reasons),
                    )
                else:
                    self.refresh_scheduler_stats["coalesced_count"] += 1
                    self._record_debug_scheduler_event(
                        "refresh_coalesced_while_locked",
                        reason=reason,
                        pending_reasons=list(self._scheduled_refresh_reasons),
                    )
            return

        async with self._refresh_lock:
            self._cancel_scheduled_recompute()
            _LOGGER.info("Refreshing Bambuddy print history browser (%s)", reason)
            self._set_status("refreshing", f"Refreshing Bambuddy print history browser ({reason})")
            self._notify_listeners()

            try:
                refresh_started = perf_counter()
                self.last_refresh_reason = reason
                self.last_refresh_started_at = dt_util.utcnow().isoformat()
                session = aiohttp_client.async_get_clientsession(self.hass)
                client = BambuddyApiClient(
                    session,
                    self.base_url,
                    self.api_key,
                    self.fetch_timeout_seconds,
                )
                refresh_states = self._state_snapshot()
                refresh_start_date = normalize_filter_date_value(
                    refresh_states.get("input_text.print_history_filter_start_date", "")
                )
                refresh_end_date = normalize_filter_date_value(
                    refresh_states.get("input_text.print_history_filter_end_date", "")
                )
                fetch_started = perf_counter()
                archives_result, printers_result, stats_result, projects_result = await asyncio.gather(
                    client.async_fetch_archives(
                        limit=self.max_archives,
                        date_from=refresh_start_date,
                        date_to=refresh_end_date,
                    ),
                    client.async_fetch_printers(),
                    client.async_fetch_archive_stats(),
                    client.async_fetch_projects(),
                    return_exceptions=True,
                )
                if isinstance(archives_result, Exception):
                    raise archives_result

                raw_archives = archives_result
                raw_printers: list[dict[str, Any]] = []
                raw_projects: list[dict[str, Any]] = []
                if isinstance(printers_result, Exception):
                    _LOGGER.warning(
                        "Unable to fetch Bambuddy printers while refreshing print history; falling back to archive payload names: %s",
                        printers_result,
                    )
                else:
                    raw_printers = printers_result

                if isinstance(projects_result, Exception):
                    _LOGGER.warning(
                        "Unable to fetch Bambuddy projects while refreshing print history; popup project assignment options may be incomplete: %s",
                        projects_result,
                    )
                else:
                    raw_projects = projects_result

                if isinstance(stats_result, Exception):
                    _LOGGER.warning(
                        "Unable to fetch Bambuddy archive stats while refreshing print history; limit warnings may be incomplete: %s",
                        stats_result,
                    )
                else:
                    self.last_refresh_archive_total_count = self._extract_total_prints(stats_result)

                self.last_refresh_fetch_ms = round((perf_counter() - fetch_started) * 1000, 1)
                self.last_refresh_archive_count = len(raw_archives)
                self.last_refresh_printer_count = len(raw_printers)
                self.last_refresh_project_count = len(raw_projects)
                self.project_options = self._project_options_from_projects(raw_projects)
                enriched_archives = self._enrich_archives_with_printer_names(raw_archives, raw_printers)
                projected = [project_archive(item) for item in enriched_archives]
                archives_changed = projected != self.archives
                store_replace_started = perf_counter()
                store_replace_result = await self.hass.async_add_executor_job(self.store.replace_archives, projected)
                self.last_refresh_store_replace_ms = round((perf_counter() - store_replace_started) * 1000, 1)
                self.last_refresh_store_load_ms = 0.0
                self.last_refresh_store_total_count = int(store_replace_result.get("total_count", 0))
                self.last_refresh_store_inserted_count = int(store_replace_result.get("inserted_count", 0))
                self.last_refresh_store_updated_count = int(store_replace_result.get("updated_count", 0))
                self.last_refresh_store_unchanged_count = int(store_replace_result.get("unchanged_count", 0))
                self.last_refresh_store_removed_count = int(store_replace_result.get("removed_count", 0))
                self.last_refresh_store_fast_unchanged_count = int(store_replace_result.get("fast_unchanged_count", 0))
                self.last_refresh_store_serialized_count = int(store_replace_result.get("serialized_count", 0))
                self.archives = projected
                self.last_refresh_duration_ms = round((perf_counter() - refresh_started) * 1000, 1)
                self.last_refresh = dt_util.utcnow().isoformat()
                self.last_error = ""
                self._store_unavailable_until = None
                query_changed = self._recompute_query(f"refresh:{reason}")
                if archives_changed or query_changed:
                    self.browser_revision += 1
                await self._async_sync_options()
                await self._async_sync_media_review_helper()
                self._set_status("ready", f"Refreshed Bambuddy print history browser ({reason})")
                _LOGGER.info("Refreshed Bambuddy print history browser (%s) with %s archives", reason, len(self.archives))
            except Exception as error:  # noqa: BLE001
                self.last_error = str(error)
                if isinstance(error, sqlite3.OperationalError) and "unable to open database file" in str(error).lower():
                    self._store_unavailable_until = dt_util.utcnow() + timedelta(seconds=30)
                    cooldown_message = (
                        f"{error} (refresh paused for 30s to avoid repeated local-store failures)"
                    )
                    self.last_error = cooldown_message
                    self._set_status("error", cooldown_message)
                else:
                    self._set_status("error", str(error))
                _LOGGER.exception("Failed to refresh Bambuddy print history browser (%s)", reason)

                self._scheduled_recompute_reasons.clear()
            self._notify_listeners()

    async def async_ensure_archive_loaded(self, archive_id: int) -> bool:
        normalized_archive_id = as_int(archive_id)
        if normalized_archive_id <= 0:
            return False

        existing = await self.hass.async_add_executor_job(self.store.load_archive, normalized_archive_id)
        if existing is not None:
            return True

        hydrated = await self.async_refresh_archive_detail(
            normalized_archive_id,
            operation="hydrate_archive",
        )
        return hydrated is not None

    async def async_refresh_archive_detail(
        self,
        archive_id: int,
        *,
        operation: str = "refresh_archive_detail",
        extra_details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized_archive_id = as_int(archive_id)
        if normalized_archive_id <= 0:
            return None

        started = perf_counter()
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = BambuddyApiClient(
            session,
            self.base_url,
            self.api_key,
            self.fetch_timeout_seconds,
        )

        raw_archive = await client.async_fetch_archive_detail(normalized_archive_id)
        enriched_archive = dict(raw_archive)
        printer_id = str(enriched_archive.get("printer_id") or "").strip()
        printer_name = str(enriched_archive.get("printer_name") or "").strip()
        if printer_id and not printer_name:
            known_printer_names = {
                str(archive.get("printer_id") or "").strip(): str(archive.get("printer_name") or "").strip()
                for archive in self.archives
                if str(archive.get("printer_id") or "").strip() and str(archive.get("printer_name") or "").strip()
            }
            resolved_printer_name = known_printer_names.get(printer_id, "")
            if not resolved_printer_name:
                raw_printers = await client.async_fetch_printers()
                resolved_printer_name = self._printer_name_by_id(raw_printers).get(printer_id, "")
            if resolved_printer_name:
                enriched_archive["printer_name"] = resolved_printer_name

        projected_archive = project_archive(enriched_archive)
        sync_result = await self.hass.async_add_executor_job(self.store.upsert_archive, projected_archive)
        self.archives = await self.hass.async_add_executor_job(self.store.load_archives)
        query_changed = self._recompute_query(f"{operation}:{normalized_archive_id}")
        if query_changed or int(sync_result.get("inserted_count", 0)) > 0 or int(sync_result.get("updated_count", 0)) > 0:
            self.browser_revision += 1
        mutation_details = {
            "inserted_count": int(sync_result.get("inserted_count", 0)),
            "updated_count": int(sync_result.get("updated_count", 0)),
            "unchanged_count": int(sync_result.get("unchanged_count", 0)),
        }
        if extra_details:
            mutation_details.update(extra_details)
        self.record_mutation(
            operation=operation,
            archive_id=normalized_archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details=mutation_details,
        )
        self._notify_listeners()
        hydrated = await self.hass.async_add_executor_job(self.store.load_archive, normalized_archive_id)
        return hydrated

    def _project_options_from_projects(self, raw_projects: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        name_counts: dict[str, int] = {}
        seen_ids: set[str] = set()

        for project in raw_projects:
            project_id = as_text(project.get("id")).strip()
            if not project_id or project_id in seen_ids:
                continue
            seen_ids.add(project_id)
            project_name = as_text(project.get("name")).strip()
            status = as_text(project.get("status")).strip().lower()
            if project_name:
                key = project_name.casefold()
                name_counts[key] = name_counts.get(key, 0) + 1
            normalized.append(
                {
                    "id": project_id,
                    "name": project_name,
                    "status": status,
                }
            )

        options: list[dict[str, str]] = []
        for project in normalized:
            project_name = project["name"]
            if project_name:
                label = project_name
                if name_counts.get(project_name.casefold(), 0) > 1:
                    label = f"{project_name} [{project['id']}]"
            else:
                label = f"Project [{project['id']}]"
            options.append(
                {
                    "id": project["id"],
                    "name": project_name,
                    "status": project["status"],
                    "label": label,
                }
            )

        options.sort(key=lambda item: (item["label"].casefold(), item["id"]))
        return options

    def build_query_response(self, overrides: dict[str, Any] | None = None, *, source: str = "unknown") -> dict[str, Any]:
        merged_overrides = dict(overrides or {})
        include_activity_rows = bool(merged_overrides.pop("include_activity_rows", False))
        states = self._merged_state_snapshot(merged_overrides)
        debug_enabled = states.get("input_boolean.print_history_debug_instrumentation", "off") == "on"

        total_started = perf_counter()
        query_started = perf_counter()
        bundle = self.store.load_query_bundle(states, include_activity_rows=include_activity_rows)
        query_ms = round((perf_counter() - query_started) * 1000, 1)
        result = bundle["result"]
        query_details = bundle["query_details"]
        annotations = bundle["annotations"]

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
                "activity_active_days_compact_label": result.activity_active_days_compact_label,
                "activity_metric_total_label": result.activity_metric_total_label,
                "activity_metric_total_compact_label": result.activity_metric_total_compact_label,
            },
            "archives": result.page_items,
            **annotations,
            "store": bundle["store"],
        }
        activity_rows_ms = 0.0
        activity_row_count = 0
        if include_activity_rows:
            response["activity_rows"] = bundle.get("activity_rows", [])
            activity_row_count = len(response["activity_rows"])

        if debug_enabled:
            response["debug"] = {
                "enabled": True,
                "query_ms": query_ms,
                "annotations_ms": 0.0,
                "metric_aggregate_ms": float(query_details.get("metric_aggregate_ms", 0.0)),
                "activity_rows_ms": activity_rows_ms,
                "total_ms": round((perf_counter() - total_started) * 1000, 1),
                "include_activity_rows": include_activity_rows,
                "matching_archive_count": int(query_details.get("matching_archive_count", result.filtered_count)),
                "page_item_count": len(result.page_items),
                "filtered_count": result.filtered_count,
                "metric_archive_count": int(query_details.get("metric_archive_count", result.filtered_count)),
                "activity_row_count": activity_row_count,
                "timestamp": dt_util.utcnow().isoformat(),
            }

        total_ms = round((perf_counter() - total_started) * 1000, 1)
        self._record_query_stats(
            source=source,
            total_ms=total_ms,
            query_ms=query_ms,
            annotations_ms=0.0,
            metric_aggregate_ms=float(query_details.get("metric_aggregate_ms", 0.0)),
            activity_rows_ms=activity_rows_ms,
            filtered_count=result.filtered_count,
            matching_archive_count=int(query_details.get("matching_archive_count", result.filtered_count)),
            page_item_count=len(result.page_items),
            metric_archive_count=int(query_details.get("metric_archive_count", result.filtered_count)),
            activity_row_count=activity_row_count,
            include_activity_rows=include_activity_rows,
        )
        return response

    def build_archive_detail_response(self, archive_id: int) -> dict[str, Any] | None:
        detail = self.store.load_archive_detail_bundle(archive_id)
        if detail is None:
            return None
        detail["event_timeline"] = [
            {
                "type": row["type"],
                "time": row["time"],
                "source": row["source"],
                "status": row["status"],
                "label": EVENT_LABELS.get(row["type"], row["type"].replace("_", " ").strip().title()),
                "color_key": EVENT_COLOR_KEYS.get(row["type"], "neutral"),
                "payload": row["payload"],
                "derived_from": row["derived_from"],
                "event_key": row["event_key"],
            }
            for row in detail["event_timeline"]
        ]
        return detail

    async def async_record_archive_event(
        self,
        archive_id: int,
        *,
        event_type: str,
        event_source: str,
        event_time: str | None = None,
        event_status: str = "",
        payload: Any | None = None,
        derived_from: str = "",
        event_key: str | None = None,
        notify: bool = True,
    ) -> dict[str, Any]:
        started = perf_counter()
        recorded = await self.hass.async_add_executor_job(
            lambda: self.store.append_archive_event(
                archive_id,
                event_type=event_type,
                event_source=event_source,
                event_time=event_time,
                event_status=event_status,
                payload=payload,
                derived_from=derived_from,
                event_key=event_key,
            )
        )
        self._record_mutation_stats(
            operation="append_event",
            archive_id=archive_id,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            details={
                "event_type": event_type,
                "event_source": event_source,
                "event_status": event_status,
            },
        )
        if notify:
            self._notify_listeners()
        return recorded

    def diagnostics(self) -> dict[str, Any]:
        return {
            "status_state": self.status_state,
            "status_message": self.status_message,
            "last_refresh": self.last_refresh,
            "last_refresh_reason": self.last_refresh_reason,
            "last_refresh_started_at": self.last_refresh_started_at,
            "last_refresh_duration_ms": self.last_refresh_duration_ms,
            "last_refresh_fetch_ms": self.last_refresh_fetch_ms,
            "last_refresh_store_replace_ms": self.last_refresh_store_replace_ms,
            "last_refresh_store_load_ms": self.last_refresh_store_load_ms,
            "last_refresh_store_total_count": self.last_refresh_store_total_count,
            "last_refresh_store_inserted_count": self.last_refresh_store_inserted_count,
            "last_refresh_store_updated_count": self.last_refresh_store_updated_count,
            "last_refresh_store_unchanged_count": self.last_refresh_store_unchanged_count,
            "last_refresh_store_removed_count": self.last_refresh_store_removed_count,
            "last_refresh_store_fast_unchanged_count": self.last_refresh_store_fast_unchanged_count,
            "last_refresh_store_serialized_count": self.last_refresh_store_serialized_count,
            "last_refresh_archive_count": self.last_refresh_archive_count,
            "last_refresh_archive_total_count": self.last_refresh_archive_total_count,
            "last_refresh_printer_count": self.last_refresh_printer_count,
            "last_error": self.last_error,
            "enabled": self.enabled,
            "archive_count": len(self.archives),
            "limit_notice": self.limit_notice,
            "query": {
                "filtered_count": self.result.filtered_count,
                "total_pages": self.result.total_pages,
                "current_page": self.result.current_page,
            },
            "query_stats": dict(self.query_stats),
            "recompute_stats": dict(self.recompute_stats),
            "mutation_stats": dict(self.mutation_stats),
            "refresh_scheduler_stats": self._scheduler_diagnostics(self.refresh_scheduler_stats, self._scheduled_refresh_reasons),
            "recompute_scheduler_stats": self._scheduler_diagnostics(self.recompute_scheduler_stats, self._scheduled_recompute_reasons),
            "recent_operations": list(self._recent_operations),
            "store": self.store.load_store_stats(),
            "store_connection": self.store.diagnostics_snapshot(),
        }

    @property
    def debug_enabled(self) -> bool:
        state = self.hass.states.get("input_boolean.print_history_debug_instrumentation")
        return state is not None and state.state == "on"

    @property
    def limit_notice(self) -> dict[str, Any]:
        limit = self.max_archives
        loaded_count = max(0, len(self.archives))
        total_prints = self.last_refresh_archive_total_count
        total_known = isinstance(total_prints, int) and total_prints >= 0
        threshold_count = min(limit, max(1, limit - 25, int(limit * 0.9)))
        is_truncated = bool(total_known and total_prints > limit)
        is_at_limit = loaded_count >= limit
        is_near_limit = loaded_count >= threshold_count and loaded_count < limit
        show = limit > 0 and (is_truncated or is_at_limit or is_near_limit)

        state = "hidden"
        chip_icon = "mdi:archive-outline"
        chip_label = ""
        popup_title = "Print History Cache"
        popup_markdown = "The print history cache is healthy."
        missing_count = 0

        if show:
            if is_truncated:
                state = "truncated"
                chip_icon = "mdi:archive-remove-outline"
                chip_label = f"{loaded_count:,} of {total_prints:,}"
                missing_count = max(0, total_prints - loaded_count)
                popup_title = "Print History Cache Limit Reached"
                popup_markdown = (
                    f"Home Assistant cached **{loaded_count:,}** archived prints out of your configured limit of **{limit:,}**.\n\n"
                    f"Bambuddy reports **{total_prints:,}** total prints, so **{missing_count:,}** older prints are not included in the local browser cache right now.\n\n"
                    "Increase `input_number.print_history_max_archives` if you want older prints to remain visible here."
                )
            elif is_at_limit:
                state = "at_limit"
                chip_icon = "mdi:archive-alert-outline"
                chip_label = (
                    f"{loaded_count:,} of {total_prints:,}"
                    if total_known
                    else f"{loaded_count:,} of {limit:,}"
                )
                popup_title = "Print History Cache At Max"
                if total_known and total_prints <= limit:
                    popup_markdown = (
                        f"Home Assistant cached **{loaded_count:,}** archived prints, which matches your configured limit of **{limit:,}**.\n\n"
                        f"Bambuddy currently reports **{total_prints:,}** total prints, so nothing appears to be missing yet.\n\n"
                        "If new prints arrive, older ones will start falling out of the cache unless you raise the max."
                    )
                else:
                    popup_markdown = (
                        f"Home Assistant cached **{loaded_count:,}** archived prints, which matches your configured limit of **{limit:,}**.\n\n"
                        "The integration could not confirm the full Bambuddy print count, so older prints may be missing once the browser reaches this cap.\n\n"
                        "Raise `input_number.print_history_max_archives` if you want more history retained locally."
                    )
            else:
                remaining_capacity = max(0, limit - loaded_count)
                state = "near_limit"
                chip_icon = "mdi:archive-clock-outline"
                chip_label = f"{loaded_count:,} of {limit:,}"
                popup_title = "Print History Cache Near Max"
                popup_markdown = (
                    f"Home Assistant cached **{loaded_count:,}** archived prints out of your configured limit of **{limit:,}**.\n\n"
                    f"Only **{remaining_capacity:,}** cache slots remain before older prints start dropping out of the local browser history.\n\n"
                    "If you want a deeper browser history, raise `input_number.print_history_max_archives` before you hit the cap."
                )

        return {
            "show": show,
            "state": state,
            "limit": limit,
            "threshold_count": threshold_count,
            "loaded_count": loaded_count,
            "total_prints": total_prints,
            "total_known": total_known,
            "missing_count": missing_count,
            "chip_icon": chip_icon,
            "chip_label": chip_label,
            "popup_title": popup_title,
            "popup_markdown": popup_markdown,
        }

    def _state_snapshot(self) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for entity_id in BROWSER_HELPER_ENTITY_IDS:
            state = self.hass.states.get(entity_id)
            snapshot[entity_id] = "" if state is None else state.state
        return snapshot

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

    def _recompute_query(self, reason: str = "internal") -> bool:
        started = perf_counter()
        with self.store._connect() as connection:
            next_result = self.store.load_query_result(self._state_snapshot(), connection=connection)
            next_activity_summary = self.store.load_activity_summary(connection=connection)
        changed = next_result != self.result or next_activity_summary != self.activity_summary
        self.result = next_result
        self.activity_summary = next_activity_summary
        if changed:
            self.loaded_at = dt_util.utcnow().isoformat()
        self._record_recompute_stats(
            reason=reason,
            duration_ms=round((perf_counter() - started) * 1000, 1),
            changed=changed,
        )
        return changed

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

    async def _async_sync_media_review_helper(self) -> None:
        entity_id = "input_select.bambuddy_photo_review_state"
        if self.hass.states.get(entity_id) is None:
            return

        summary = await self.hass.async_add_executor_job(self.store.load_media_review_summary)
        option = "idle"
        if int(summary.get("reviewing_count", 0) or 0) > 0:
            option = "reviewing"
        elif int(summary.get("pending_count", 0) or 0) > 0:
            option = "pending"

        current_state = self.hass.states.get(entity_id)
        if current_state is not None and str(current_state.state) == option:
            return

        await self.hass.services.async_call(
            "input_select",
            "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )

    @callback
    def _async_handle_helper_state_change(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        if entity_id in REFRESH_TRIGGER_HELPERS:
            self.hass.async_create_task(self.async_request_refresh(f"state:{entity_id}"))
            return

        if entity_id in OPTION_SET_HELPERS and self.archives:
            self.hass.async_create_task(self._async_sync_options())

        self._schedule_recompute(f"state:{entity_id}")

    @callback
    def _async_handle_webhook_event(self, event: Event) -> None:
        event_type = str((event.data or {}).get("event", "")).strip().lower()
        if event_type in REFRESH_WEBHOOK_EVENTS:
            self.hass.async_create_task(self.async_request_refresh(f"webhook:{event_type}"))

    @callback
    def _async_handle_interval_refresh(self, _now: Any) -> None:
        self.hass.async_create_task(self.async_request_refresh("interval"))

    def _set_status(self, state: str, message: str) -> None:
        self.status_state = state
        self.status_message = message

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    def _extract_total_prints(self, payload: dict[str, Any]) -> int | None:
        value = payload.get("total_prints")
        if value is None:
            return None
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return None

    @property
    def _scheduler_loop(self) -> asyncio.AbstractEventLoop | None:
        return getattr(self.hass, "loop", None)

    @callback
    def _schedule_recompute(self, reason: str) -> None:
        self._record_scheduler_request(self.recompute_scheduler_stats, reason)
        if self._refresh_lock.locked() or self._scheduled_refresh_handle is not None:
            self.recompute_scheduler_stats["suppressed_due_refresh_count"] += 1
            self._record_debug_scheduler_event(
                "recompute_suppressed",
                reason=reason,
                refresh_locked=self._refresh_lock.locked(),
                refresh_pending=self._scheduled_refresh_handle is not None,
            )
            return

        if self._scheduler_loop is None:
            self.recompute_scheduler_stats["immediate_count"] += 1
            if self._recompute_query(reason):
                self.browser_revision += 1
            self._notify_listeners()
            return

        self._append_unique_reason(self._scheduled_recompute_reasons, reason)
        if self._scheduled_recompute_handle is not None:
            self.recompute_scheduler_stats["coalesced_count"] += 1
            self._scheduled_recompute_handle.cancel()
        else:
            self.recompute_scheduler_stats["scheduled_count"] += 1

        self._scheduled_recompute_handle = self._scheduler_loop.call_later(
            HELPER_RECOMPUTE_DEBOUNCE_SECONDS,
            self._execute_scheduled_recompute,
        )
        self._record_debug_scheduler_event(
            "recompute_scheduled",
            reason=reason,
            delay_seconds=HELPER_RECOMPUTE_DEBOUNCE_SECONDS,
            pending_reasons=list(self._scheduled_recompute_reasons),
        )

    @callback
    def _execute_scheduled_recompute(self) -> None:
        self._scheduled_recompute_handle = None
        reasons = self._drain_reasons(self._scheduled_recompute_reasons)
        if not reasons:
            return
        if self._refresh_lock.locked() or self._scheduled_refresh_handle is not None:
            self.recompute_scheduler_stats["suppressed_due_refresh_count"] += 1
            self._record_debug_scheduler_event(
                "recompute_dropped_for_refresh",
                pending_reasons=reasons,
                refresh_locked=self._refresh_lock.locked(),
                refresh_pending=self._scheduled_refresh_handle is not None,
            )
            return

        batch_reason = self._summarize_reasons("state_batch", reasons)
        self.recompute_scheduler_stats["executed_count"] += 1
        self.recompute_scheduler_stats["last_batch_reason"] = batch_reason
        self.recompute_scheduler_stats["last_batch_size"] = len(reasons)
        self.recompute_scheduler_stats["last_timestamp"] = dt_util.utcnow().isoformat()
        self._record_debug_scheduler_event("recompute_executed", batch_reason=batch_reason, pending_reasons=reasons)
        if self._recompute_query(batch_reason):
            self.browser_revision += 1
        self._notify_listeners()

    @callback
    def _async_execute_scheduled_refresh(self) -> None:
        self._scheduled_refresh_handle = None
        reasons = self._drain_reasons(self._scheduled_refresh_reasons)
        if not reasons:
            return
        batch_reason = self._summarize_reasons("refresh_batch", reasons)
        self.refresh_scheduler_stats["executed_count"] += 1
        self.refresh_scheduler_stats["last_batch_reason"] = batch_reason
        self.refresh_scheduler_stats["last_batch_size"] = len(reasons)
        self.refresh_scheduler_stats["last_timestamp"] = dt_util.utcnow().isoformat()
        self._record_debug_scheduler_event("refresh_executed", batch_reason=batch_reason, pending_reasons=reasons)
        self.hass.async_create_task(self.async_refresh(batch_reason))

    @callback
    def _cancel_scheduled_refresh(self) -> None:
        if self._scheduled_refresh_handle is not None:
            self._scheduled_refresh_handle.cancel()
            self._scheduled_refresh_handle = None
        self._scheduled_refresh_reasons.clear()

    @callback
    def _cancel_scheduled_recompute(self) -> None:
        if self._scheduled_recompute_handle is not None:
            self._scheduled_recompute_handle.cancel()
            self._scheduled_recompute_handle = None
        self._scheduled_recompute_reasons.clear()

    def _record_scheduler_request(self, stats: dict[str, Any], reason: str) -> None:
        stats["request_count"] += 1
        stats["last_reason"] = reason
        stats["last_timestamp"] = dt_util.utcnow().isoformat()

    def _scheduler_diagnostics(self, stats: dict[str, Any], pending_reasons: list[str]) -> dict[str, Any]:
        data = dict(stats)
        data["pending_reason_count"] = len(pending_reasons)
        if self.debug_enabled:
            data["pending_reasons"] = list(pending_reasons)
        return data

    def _record_debug_scheduler_event(self, event_type: str, **details: Any) -> None:
        if not self.debug_enabled:
            return
        self._recent_operations.appendleft(
            {
                "type": "scheduler",
                "event": event_type,
                "details": details,
                "timestamp": dt_util.utcnow().isoformat(),
            }
        )

    def _append_unique_reason(self, target: list[str], reason: str) -> None:
        if reason not in target:
            target.append(reason)

    def _drain_reasons(self, target: list[str]) -> list[str]:
        reasons = list(target)
        target.clear()
        return reasons

    def _summarize_reasons(self, prefix: str, reasons: list[str]) -> str:
        if len(reasons) == 1:
            return reasons[0]
        return f"{prefix}[{len(reasons)}]:{'|'.join(reasons)}"

    def _record_query_stats(
        self,
        *,
        source: str,
        total_ms: float,
        query_ms: float,
        annotations_ms: float,
        metric_aggregate_ms: float,
        activity_rows_ms: float,
        filtered_count: int,
        matching_archive_count: int,
        page_item_count: int,
        metric_archive_count: int,
        activity_row_count: int,
        include_activity_rows: bool,
    ) -> None:
        timestamp = dt_util.utcnow().isoformat()
        self.query_stats["count"] += 1
        self.query_stats["last_source"] = source
        self.query_stats["last_total_ms"] = total_ms
        self.query_stats["last_query_ms"] = query_ms
        self.query_stats["last_annotations_ms"] = annotations_ms
        self.query_stats["last_metric_aggregate_ms"] = metric_aggregate_ms
        self.query_stats["last_activity_rows_ms"] = activity_rows_ms
        self.query_stats["last_filtered_count"] = filtered_count
        self.query_stats["last_matching_archive_count"] = matching_archive_count
        self.query_stats["last_page_item_count"] = page_item_count
        self.query_stats["last_metric_archive_count"] = metric_archive_count
        self.query_stats["last_activity_row_count"] = activity_row_count
        self.query_stats["last_include_activity_rows"] = include_activity_rows
        self.query_stats["last_timestamp"] = timestamp
        self.query_stats["max_total_ms"] = max(float(self.query_stats["max_total_ms"]), total_ms)
        slow = total_ms >= SLOW_QUERY_THRESHOLD_MS
        if slow:
            self.query_stats["slow_count"] += 1
            _LOGGER.warning(
                "Slow Bambuddy query: source=%s total_ms=%s filtered=%s page_items=%s activity_rows=%s include_activity_rows=%s",
                source,
                total_ms,
                filtered_count,
                page_item_count,
                activity_row_count,
                include_activity_rows,
            )
        self._recent_operations.appendleft(
            {
                "type": "query",
                "source": source,
                "duration_ms": total_ms,
                "filtered_count": filtered_count,
                "matching_archive_count": matching_archive_count,
                "page_item_count": page_item_count,
                "metric_archive_count": metric_archive_count,
                "metric_aggregate_ms": metric_aggregate_ms,
                "activity_row_count": activity_row_count,
                "include_activity_rows": include_activity_rows,
                "slow": slow,
                "timestamp": timestamp,
            }
        )

    def _record_recompute_stats(self, *, reason: str, duration_ms: float, changed: bool) -> None:
        timestamp = dt_util.utcnow().isoformat()
        self.recompute_stats["count"] += 1
        self.recompute_stats["last_reason"] = reason
        self.recompute_stats["last_duration_ms"] = duration_ms
        self.recompute_stats["last_changed"] = changed
        self.recompute_stats["last_timestamp"] = timestamp
        self.recompute_stats["max_duration_ms"] = max(float(self.recompute_stats["max_duration_ms"]), duration_ms)
        slow = duration_ms >= SLOW_RECOMPUTE_THRESHOLD_MS
        if slow:
            self.recompute_stats["slow_count"] += 1
            _LOGGER.warning(
                "Slow Bambuddy recompute: reason=%s duration_ms=%s changed=%s",
                reason,
                duration_ms,
                changed,
            )
        self._recent_operations.appendleft(
            {
                "type": "recompute",
                "reason": reason,
                "duration_ms": duration_ms,
                "changed": changed,
                "slow": slow,
                "timestamp": timestamp,
            }
        )

    def _record_mutation_stats(
        self,
        *,
        operation: str,
        archive_id: int,
        duration_ms: float,
        details: dict[str, Any] | None = None,
    ) -> None:
        timestamp = dt_util.utcnow().isoformat()
        self.mutation_stats["count"] += 1
        self.mutation_stats["last_operation"] = operation
        self.mutation_stats["last_archive_id"] = archive_id
        self.mutation_stats["last_duration_ms"] = duration_ms
        self.mutation_stats["last_timestamp"] = timestamp
        self.mutation_stats["max_duration_ms"] = max(float(self.mutation_stats["max_duration_ms"]), duration_ms)
        slow = duration_ms >= SLOW_MUTATION_THRESHOLD_MS
        if slow:
            self.mutation_stats["slow_count"] += 1
            _LOGGER.warning(
                "Slow Bambuddy mutation: operation=%s archive_id=%s duration_ms=%s details=%s",
                operation,
                archive_id,
                duration_ms,
                details or {},
            )
        entry = {
            "type": "mutation",
            "operation": operation,
            "archive_id": archive_id,
            "duration_ms": duration_ms,
            "slow": slow,
            "timestamp": timestamp,
        }
        if details:
            entry["details"] = details
        self._recent_operations.appendleft(entry)

    def record_mutation(
        self,
        *,
        operation: str,
        archive_id: int,
        duration_ms: float,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._record_mutation_stats(
            operation=operation,
            archive_id=archive_id,
            duration_ms=duration_ms,
            details=details,
        )

    def _normalized_event_timeline(self, archive_id: int) -> list[dict[str, Any]]:
        timeline = self.store.load_archive_event_timeline(archive_id)
        return [
            {
                "type": row["type"],
                "time": row["time"],
                "source": row["source"],
                "status": row["status"],
                "label": EVENT_LABELS.get(row["type"], row["type"].replace("_", " ").strip().title()),
                "color_key": EVENT_COLOR_KEYS.get(row["type"], "neutral"),
                "payload": row["payload"],
                "derived_from": row["derived_from"],
                "event_key": row["event_key"],
            }
            for row in timeline
        ]

    @property
    def _scan_interval_seconds(self) -> int:
        return max(1, self.scan_interval_seconds)