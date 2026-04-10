from __future__ import annotations

from datetime import timedelta
from pathlib import Path
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


class PrintHistoryBrowserManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = PrintHistoryStore(Path(hass.config.path(".storage", STORE_FILENAME)))
        self.archives: list[dict[str, Any]] = []
        self.result = query_archives([], self._state_snapshot())
        self.status_state = "initializing"
        self.status_message = "Initializing Bambuddy print history browser"
        self.last_refresh: str | None = None
        self.last_error = ""
        self.loaded_at: str | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribers: list[Callable[[], None]] = []

    async def async_initialize(self) -> None:
        await self.hass.async_add_executor_job(self.store.initialize)
        self.archives = await self.hass.async_add_executor_job(self.store.load_archives)
        self._recompute_query()

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
            projected = [project_archive(item) for item in raw_archives]
            await self.hass.async_add_executor_job(self.store.replace_archives, projected)
            self.archives = await self.hass.async_add_executor_job(self.store.load_archives)
            self.last_refresh = dt_util.utcnow().isoformat()
            self.last_error = ""
            self._recompute_query()
            await self._async_sync_options()
            self._set_status("ready", f"Refreshed Bambuddy print history browser ({reason})")
        except Exception as error:  # noqa: BLE001
            self.last_error = str(error)
            self._set_status("error", str(error))

        self._notify_listeners()

    def _state_snapshot(self) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for entity_id in BROWSER_HELPER_ENTITY_IDS:
            state = self.hass.states.get(entity_id)
            snapshot[entity_id] = "" if state is None else state.state
        return snapshot

    def _recompute_query(self) -> None:
        self.result = query_archives(self.archives, self._state_snapshot())
        self.loaded_at = dt_util.utcnow().isoformat()

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

        self._recompute_query()
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