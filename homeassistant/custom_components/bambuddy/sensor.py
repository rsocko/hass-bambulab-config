from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_MANAGER,
    DOMAIN,
    ENTITY_ACTIVITY,
    ENTITY_FILTERED,
    ENTITY_PAGE_ARCHIVES,
    ENTITY_PAGE_INFO,
    ENTITY_STATUS,
)
from .manager import PrintHistoryBrowserManager


@dataclass(frozen=True, kw_only=True)
class BambuddyBrowserSensorDescription(SensorEntityDescription):
    entity_id: str


DESCRIPTIONS = [
    BambuddyBrowserSensorDescription(
        key=ENTITY_STATUS,
        entity_id=f"sensor.{ENTITY_STATUS}",
        name="Bambuddy Print History Browser Status",
        icon="mdi:database-search-outline",
    ),
    BambuddyBrowserSensorDescription(
        key=ENTITY_FILTERED,
        entity_id=f"sensor.{ENTITY_FILTERED}",
        name="Bambuddy Print History Browser Filtered",
        icon="mdi:filter-variant",
    ),
    BambuddyBrowserSensorDescription(
        key=ENTITY_PAGE_ARCHIVES,
        entity_id=f"sensor.{ENTITY_PAGE_ARCHIVES}",
        name="Bambuddy Print History Browser Page Archives",
        icon="mdi:book-open-page-variant-outline",
    ),
    BambuddyBrowserSensorDescription(
        key=ENTITY_PAGE_INFO,
        entity_id=f"sensor.{ENTITY_PAGE_INFO}",
        name="Bambuddy Print History Browser Page Info",
        icon="mdi:book-open-variant",
    ),
    BambuddyBrowserSensorDescription(
        key=ENTITY_ACTIVITY,
        entity_id=f"sensor.{ENTITY_ACTIVITY}",
        name="Bambuddy Print History Browser Activity",
        icon="mdi:chart-box-outline",
    ),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager: PrintHistoryBrowserManager = hass.data[DOMAIN][entry.entry_id][DATA_MANAGER]
    async_add_entities(BambuddyBrowserSensor(manager, description) for description in DESCRIPTIONS)


class BambuddyBrowserSensor(SensorEntity):
    _attr_has_entity_name = False

    def __init__(self, manager: PrintHistoryBrowserManager, description: BambuddyBrowserSensorDescription) -> None:
        self.manager = manager
        self.entity_description = description
        self._attr_unique_id = description.key
        self.entity_id = description.entity_id

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.manager.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> Any:
        if self.entity_description.key == ENTITY_STATUS:
            return self.manager.status_state
        if self.entity_description.key == ENTITY_FILTERED:
            return self.manager.result.filtered_count
        if self.entity_description.key == ENTITY_PAGE_ARCHIVES:
            return self.manager.result.current_page
        if self.entity_description.key == ENTITY_PAGE_INFO:
            return self.manager.result.page_info
        return len(self.manager.archives)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        backend = "custom_integration_local_store"
        if self.entity_description.key == ENTITY_STATUS:
            store_stats = self.manager.store.load_store_stats()
            limit_notice = self.manager.limit_notice
            attributes = {
                "backend": backend,
                "browser_revision": self.manager.browser_revision,
                "message": self.manager.status_message,
                "archive_count": len(self.manager.archives),
                "current_limit": self.manager.max_archives,
                "archive_total_count": self.manager.last_refresh_archive_total_count,
                "limit_notice": limit_notice,
                "limit_notice_show": limit_notice.get("show", False),
                "limit_notice_state": limit_notice.get("state", "hidden"),
                "limit_notice_chip_label": limit_notice.get("chip_label", ""),
                "limit_notice_popup_title": limit_notice.get("popup_title", "Print History Cache"),
                "limit_notice_popup_markdown": limit_notice.get("popup_markdown", "The print history cache is healthy."),
                "last_refresh": self.manager.last_refresh,
                "last_refresh_reason": self.manager.last_refresh_reason,
                "last_refresh_started_at": self.manager.last_refresh_started_at,
                "last_refresh_duration_ms": self.manager.last_refresh_duration_ms,
                "last_refresh_fetch_ms": self.manager.last_refresh_fetch_ms,
                "last_refresh_store_replace_ms": self.manager.last_refresh_store_replace_ms,
                "last_refresh_store_load_ms": self.manager.last_refresh_store_load_ms,
                "last_refresh_archive_count": self.manager.last_refresh_archive_count,
                "last_refresh_archive_total_count": self.manager.last_refresh_archive_total_count,
                "last_refresh_printer_count": self.manager.last_refresh_printer_count,
                "last_refresh_project_count": self.manager.last_refresh_project_count,
                "last_error": self.manager.last_error,
                "enabled": self.manager.enabled,
                "store_path": str(self.manager.store._db_path),
                "store_db_size_bytes": store_stats.get("db_size_bytes", 0),
                "store_last_synced_at": store_stats.get("last_synced_at", ""),
                "store_event_timeline_count": store_stats.get("event_timeline_count", 0),
                "store_note_payload_row_count": store_stats.get("note_payload_row_count", 0),
                "store_connection_open_count": store_stats.get("connection_open_count", 0),
                "store_connection_open_error_count": store_stats.get("connection_open_error_count", 0),
                "store_connection_current_open_count": store_stats.get("connection_current_open_count", 0),
                "store_connection_max_open_count": store_stats.get("connection_max_open_count", 0),
                "store_connection_last_error": store_stats.get("connection_last_error", ""),
                "store_connection_last_open_duration_ms": store_stats.get("connection_last_open_duration_ms", 0.0),
                "store_connection_max_open_duration_ms": store_stats.get("connection_max_open_duration_ms", 0.0),
                "store_proc_fd_count": store_stats.get("proc_fd_count"),
                "store_proc_fd_max_count": store_stats.get("proc_fd_max_count"),
                "store_db_fd_count": store_stats.get("db_fd_count"),
                "store_db_fd_max_count": store_stats.get("db_fd_max_count"),
                "page_size": self.manager.hass.states.get("input_number.print_history_page_size").state if self.manager.hass.states.get("input_number.print_history_page_size") else "10",
                "current_page": self.manager.result.current_page,
                "query_request_count": self.manager.query_stats.get("count", 0),
                "query_slow_count": self.manager.query_stats.get("slow_count", 0),
                "query_last_source": self.manager.query_stats.get("last_source", ""),
                "query_last_total_ms": self.manager.query_stats.get("last_total_ms", 0.0),
                "query_max_total_ms": self.manager.query_stats.get("max_total_ms", 0.0),
                "query_last_filtered_count": self.manager.query_stats.get("last_filtered_count", 0),
                "query_last_matching_archive_count": self.manager.query_stats.get("last_matching_archive_count", 0),
                "query_last_page_item_count": self.manager.query_stats.get("last_page_item_count", 0),
                "query_last_metric_archive_count": self.manager.query_stats.get("last_metric_archive_count", 0),
                "query_last_metric_aggregate_ms": self.manager.query_stats.get("last_metric_aggregate_ms", 0.0),
                "query_last_activity_row_count": self.manager.query_stats.get("last_activity_row_count", 0),
                "query_last_include_activity_rows": self.manager.query_stats.get("last_include_activity_rows", False),
                "recompute_count": self.manager.recompute_stats.get("count", 0),
                "recompute_slow_count": self.manager.recompute_stats.get("slow_count", 0),
                "recompute_last_reason": self.manager.recompute_stats.get("last_reason", ""),
                "recompute_last_duration_ms": self.manager.recompute_stats.get("last_duration_ms", 0.0),
                "recompute_last_changed": self.manager.recompute_stats.get("last_changed", False),
                "recompute_max_duration_ms": self.manager.recompute_stats.get("max_duration_ms", 0.0),
                "mutation_count": self.manager.mutation_stats.get("count", 0),
                "mutation_slow_count": self.manager.mutation_stats.get("slow_count", 0),
                "mutation_last_operation": self.manager.mutation_stats.get("last_operation", ""),
                "mutation_last_archive_id": self.manager.mutation_stats.get("last_archive_id", 0),
                "mutation_last_duration_ms": self.manager.mutation_stats.get("last_duration_ms", 0.0),
                "mutation_max_duration_ms": self.manager.mutation_stats.get("max_duration_ms", 0.0),
                "project_options": list(self.manager.project_options),
                "recent_operations": list(self.manager._recent_operations),
            }
            if self.manager.debug_enabled:
                attributes.update(
                    {
                        "debug_enabled": True,
                        "refresh_store": {
                            "total_count": self.manager.last_refresh_store_total_count,
                            "inserted_count": self.manager.last_refresh_store_inserted_count,
                            "updated_count": self.manager.last_refresh_store_updated_count,
                            "unchanged_count": self.manager.last_refresh_store_unchanged_count,
                            "removed_count": self.manager.last_refresh_store_removed_count,
                            "fast_unchanged_count": self.manager.last_refresh_store_fast_unchanged_count,
                            "serialized_count": self.manager.last_refresh_store_serialized_count,
                        },
                        "refresh_scheduler": self.manager._scheduler_diagnostics(
                            self.manager.refresh_scheduler_stats,
                            self.manager._scheduled_refresh_reasons,
                        ),
                        "recompute_scheduler": self.manager._scheduler_diagnostics(
                            self.manager.recompute_scheduler_stats,
                            self.manager._scheduled_recompute_reasons,
                        ),
                    }
                )
            return attributes
        if self.entity_description.key == ENTITY_FILTERED:
            return {
                "backend": backend,
                "browser_revision": self.manager.browser_revision,
                "archive_count": len(self.manager.archives),
                "filtered_count": self.manager.result.filtered_count,
                "total_pages": self.manager.result.total_pages,
                "current_page": self.manager.result.current_page,
                "page_info": self.manager.result.page_info,
                "has_active_filters": self.manager.result.has_active_filters,
                "active_filters": self.manager.result.active_filters,
                "available_colors_json": self.manager.result.available_colors,
                "available_color_tooltips_json": self.manager.result.available_color_tooltips,
                "activity_active_days_label": self.manager.result.activity_active_days_label,
                "activity_active_days_compact_label": self.manager.result.activity_active_days_compact_label,
                "activity_metric_total_label": self.manager.result.activity_metric_total_label,
                "activity_metric_total_compact_label": self.manager.result.activity_metric_total_compact_label,
            }
        if self.entity_description.key == ENTITY_PAGE_ARCHIVES:
            return {
                "backend": backend,
                "browser_revision": self.manager.browser_revision,
                "page": self.manager.result.current_page,
                "count": self.manager.result.filtered_count,
                "total_pages": self.manager.result.total_pages,
                "has_more": self.manager.result.current_page < self.manager.result.total_pages,
                "loaded_at": self.manager.loaded_at,
            }
        if self.entity_description.key == ENTITY_PAGE_INFO:
            return {
                "backend": backend,
                "browser_revision": self.manager.browser_revision,
                "current_page": self.manager.result.current_page,
                "total_pages": self.manager.result.total_pages,
            }
        return {
            "backend": backend,
            "browser_revision": self.manager.browser_revision,
            "archive_count": self.manager.activity_summary.get("archive_count", len(self.manager.archives)),
            "active_day_count": self.manager.activity_summary.get("active_day_count", 0),
            "latest_archive_id": self.manager.activity_summary.get("latest_archive_id", 0),
            "activity_active_days_label": self.manager.result.activity_active_days_label,
            "activity_active_days_compact_label": self.manager.result.activity_active_days_compact_label,
            "activity_metric_total_label": self.manager.result.activity_metric_total_label,
            "activity_metric_total_compact_label": self.manager.result.activity_metric_total_compact_label,
        }
