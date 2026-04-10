from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from appdaemon.plugins.hass.hassapi import Hass

from print_history_browser_core import option_sets, project_archive, query_archives


HELPER_ENTITY_IDS = [
    "input_select.print_history_filter_status",
    "input_select.print_history_filter_enrichment_status",
    "input_select.print_history_filter_material",
    "input_select.print_history_filter_printer",
    "input_select.print_history_filter_date_range",
    "input_select.print_history_filter_designer",
    "input_select.print_history_filter_project",
    "input_select.print_history_filter_layer_height",
    "input_select.print_history_filter_tag",
    "input_boolean.print_history_filter_favorites_only",
    "input_text.print_history_search",
    "input_text.print_history_filter_colors",
    "input_text.print_history_activity_selected_date",
    "input_select.print_history_activity_metric",
    "input_select.print_history_sort",
    "input_number.print_history_page_size",
    "input_number.history_current_page",
    "input_number.print_history_max_archives",
    "input_boolean.bambuddy_integration_enabled",
    "input_boolean.bambuddy_history_sync_enabled",
    "input_text.bambuddy_api_base_url",
]
REFRESH_WEBHOOK_EVENTS = {"print_complete", "print_failed", "print_stopped", "print_started"}


class PrintHistoryBrowserApp(Hass):
    def initialize(self) -> None:
        self._archives: list[dict[str, Any]] = []
        self._last_refresh: str | None = None
        self._last_error: str = ""
        self._helper_retry_seconds = int(self.args.get("helper_retry_seconds", 5))
        self._fetch_timeout_seconds = int(self.args.get("fetch_timeout_seconds", 30))
        self._refresh_interval_seconds = int(self.args.get("refresh_interval_seconds", 300))
        self._browser_status_entity = self.args.get("browser_status_entity", "sensor.print_history_browser_status")
        self._filtered_entity = self.args.get("filtered_entity", "sensor.print_history_browser_filtered")
        self._page_entity = self.args.get("page_entity", "sensor.print_history_browser_page_archives")
        self._page_info_entity = self.args.get("page_info_entity", "sensor.print_history_browser_page_info")
        self._activity_entity = self.args.get("activity_entity", "sensor.print_history_browser_activity")
        self._base_url_arg = str(self.args.get("bambuddy_api_base_url", "")).rstrip("/")
        self._api_key = str(self.args.get("bambuddy_api_key", "")).strip()
        self._helpers_ready = False

        self.listen_event(self._handle_manual_refresh, "print_history_refresh_requested")
        self.listen_event(self._handle_webhook_refresh, "bambuddy_webhook_event")

        self._publish_status("initializing", message="Waiting for print history helper entities")
        self.run_in(self._startup_refresh, 2)

    def _startup_refresh(self, kwargs: dict[str, Any]) -> None:
        if not self._ensure_helpers_ready():
            return
        self._refresh_cache(reason="startup")

    def _handle_manual_refresh(self, event_name: str, data: dict[str, Any], kwargs: dict[str, Any]) -> None:
        if not self._ensure_helpers_ready():
            return
        self._refresh_cache(reason="manual_event")

    def _handle_webhook_refresh(self, event_name: str, data: dict[str, Any], kwargs: dict[str, Any]) -> None:
        event_type = str((data or {}).get("event", "")).strip().lower()
        if event_type not in REFRESH_WEBHOOK_EVENTS:
            return
        self.run_in(self._delayed_webhook_refresh, 5, reason=event_type)

    def _delayed_webhook_refresh(self, kwargs: dict[str, Any]) -> None:
        if not self._ensure_helpers_ready():
            return
        self._refresh_cache(reason=str(kwargs.get("reason", "webhook")))

    def _scheduled_refresh(self, kwargs: dict[str, Any]) -> None:
        if not self._ensure_helpers_ready():
            return
        self._refresh_cache(reason="interval")

    def _handle_state_change(self, entity: str, attribute: str, old: Any, new: Any, kwargs: dict[str, Any]) -> None:
        if not self._helpers_ready:
            return
        if entity in {
            "input_number.print_history_max_archives",
            "input_boolean.bambuddy_integration_enabled",
            "input_boolean.bambuddy_history_sync_enabled",
            "input_text.bambuddy_api_base_url",
        }:
            self._refresh_cache(reason=f"state:{entity}")
            return
        self._publish_entities()

    def _is_enabled(self) -> bool:
        return self.get_state("input_boolean.bambuddy_integration_enabled") == "on" and self.get_state(
            "input_boolean.bambuddy_history_sync_enabled"
        ) == "on"

    def _current_base_url(self) -> str:
        helper_base_url = str(self.get_state("input_text.bambuddy_api_base_url") or "").strip().rstrip("/")
        return helper_base_url or self._base_url_arg

    def _max_archives(self) -> int:
        raw = self.get_state("input_number.print_history_max_archives")
        try:
            value = int(float(raw)) if raw not in (None, "") else 500
        except (TypeError, ValueError):
            value = 500
        return max(1, value)

    def _state_snapshot(self) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for entity_id in HELPER_ENTITY_IDS:
            snapshot[entity_id] = str(self.get_state(entity_id) or "")
        return snapshot

    def _missing_helper_entities(self) -> list[str]:
        missing: list[str] = []
        for entity_id in HELPER_ENTITY_IDS:
            if self.get_state(entity_id, attribute="all") is None:
                missing.append(entity_id)
        return missing

    def _ensure_helpers_ready(self) -> bool:
        if self._helpers_ready:
            return True

        missing = self._missing_helper_entities()
        if missing:
            self._publish_status(
                "waiting_for_helpers",
                message=f"Waiting for {len(missing)} helper entities",
                missing_helpers=missing,
            )
            self.run_in(self._startup_refresh, self._helper_retry_seconds)
            return False

        for entity_id in HELPER_ENTITY_IDS:
            self.listen_state(self._handle_state_change, entity_id)

        if self._refresh_interval_seconds > 0:
            self.run_every(self._scheduled_refresh, "now", self._refresh_interval_seconds)

        self._helpers_ready = True
        self.log("Print history helper entities are available; enabling listeners")
        self._publish_status("refreshing", message="Initial AppDaemon browser warmup")
        return True

    def _publish_status(self, state: str, *, message: str = "", missing_helpers: list[str] | None = None) -> None:
        snapshot = self._state_snapshot()
        self.set_state(
            self._browser_status_entity,
            state=state,
            attributes={
                "backend": "appdaemon",
                "message": message,
                "archive_count": len(self._archives),
                "current_limit": self._max_archives(),
                "last_refresh": self._last_refresh,
                "last_error": self._last_error,
                "enabled": self._is_enabled(),
                "helpers_ready": self._helpers_ready,
                "missing_helpers": missing_helpers or [],
                "bambuddy_api_base_url": self._current_base_url(),
                "page_size": snapshot.get("input_number.print_history_page_size", "10"),
                "current_page": snapshot.get("input_number.history_current_page", "1"),
            },
        )

    def _fetch_archives(self) -> list[dict[str, Any]]:
        base_url = self._current_base_url()
        if not base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        response = requests.get(
            f"{base_url}/api/v1/archives/?limit={self._max_archives()}",
            headers={"X-API-Key": self._api_key},
            timeout=self._fetch_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Bambuddy archive response was not a JSON array")
        return [project_archive(item) for item in payload if isinstance(item, dict)]

    def _sync_options(self) -> None:
        for entity_id, options in option_sets(self._archives).items():
            self.call_service("input_select/set_options", entity_id=entity_id, options=options)

    def _refresh_cache(self, *, reason: str) -> None:
        if not self._is_enabled():
            self._publish_status("disabled", message="Print history AppDaemon browser disabled")
            return

        self._publish_status("refreshing", message=f"Refreshing AppDaemon browser cache ({reason})")
        try:
            self._archives = self._fetch_archives()
            self._last_refresh = datetime.now(timezone.utc).isoformat()
            self._last_error = ""
            self._sync_options()
            self._publish_entities()
            self._publish_status("ready", message=f"Cache refreshed ({reason})")
        except Exception as error:  # noqa: BLE001
            self._last_error = str(error)
            self.error(f"Print history AppDaemon refresh failed: {error}")
            self._publish_entities()
            self._publish_status("error", message=str(error))

    def _publish_entities(self) -> None:
        snapshot = self._state_snapshot()
        result = query_archives(self._archives, snapshot)
        self.set_state(
            self._filtered_entity,
            state=str(result.filtered_count),
            attributes={
                "backend": "appdaemon",
                "archive_count": len(self._archives),
                "filtered_count": result.filtered_count,
                "total_pages": result.total_pages,
                "current_page": result.current_page,
                "page_info": result.page_info,
                "page_json": result.page_items,
                "has_active_filters": result.has_active_filters,
                "active_filters": result.active_filters,
                "available_colors_json": result.available_colors,
                "available_color_tooltips_json": result.available_color_tooltips,
                "activity_active_days_label": result.activity_active_days_label,
                "activity_metric_total_label": result.activity_metric_total_label,
                "last_refresh": self._last_refresh,
                "last_error": self._last_error,
            },
        )
        self.set_state(
            self._page_entity,
            state=str(result.current_page),
            attributes={
                "backend": "appdaemon",
                "archives": result.page_items,
                "page": result.current_page,
                "count": result.filtered_count,
                "has_more": result.current_page < result.total_pages,
                "loaded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.set_state(
            self._page_info_entity,
            state=result.page_info,
            attributes={
                "backend": "appdaemon",
                "current_page": result.current_page,
                "total_pages": result.total_pages,
            },
        )
        self.set_state(
            self._activity_entity,
            state=str(len(self._archives)),
            attributes={
                "backend": "appdaemon",
                "archives_json": self._archives,
                "archive_count": len(self._archives),
                "last_refresh": self._last_refresh,
                "last_error": self._last_error,
            },
        )
