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
            return {
                "backend": backend,
                "browser_revision": self.manager.browser_revision,
                "message": self.manager.status_message,
                "archive_count": len(self.manager.archives),
                "current_limit": self.manager.max_archives,
                "last_refresh": self.manager.last_refresh,
                "last_error": self.manager.last_error,
                "enabled": self.manager.enabled,
                "store_path": str(self.manager.store._db_path),
                "page_size": self.manager.hass.states.get("input_number.print_history_page_size").state if self.manager.hass.states.get("input_number.print_history_page_size") else "10",
                "current_page": self.manager.result.current_page,
            }
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
                "activity_metric_total_label": self.manager.result.activity_metric_total_label,
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
            "activity_metric_total_label": self.manager.result.activity_metric_total_label,
        }