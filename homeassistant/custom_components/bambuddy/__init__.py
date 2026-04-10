from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DATA_MANAGER,
    DOMAIN,
    PLATFORMS,
    SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE,
    SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL,
    SERVICE_QUERY_PRINT_HISTORY_BROWSER,
    SERVICE_REFRESH_PRINT_HISTORY_BROWSER,
    SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE,
    SERVICE_SET_PRINT_HISTORY_REVIEW_STATE,
)
from .manager import PrintHistoryBrowserManager


CONF_ENTRY_ID = "entry_id"
CONF_ARCHIVE_ID = "archive_id"
CONF_RELATED_ARCHIVE_ID = "related_archive_id"
CONF_RELATION_TYPE = "relation_type"


_LOGGER = logging.getLogger(__name__)


SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): str})
SERVICE_QUERY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): str,
        vol.Optional("status"): str,
        vol.Optional("enrichment_status"): str,
        vol.Optional("material"): str,
        vol.Optional("printer"): str,
        vol.Optional("date_range"): str,
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
    }
)
SERVICE_DETAIL_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): str, vol.Required(CONF_ARCHIVE_ID): vol.Coerce(int)})
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


def _resolve_manager(hass: HomeAssistant, entry_id: str | None = None) -> tuple[str, PrintHistoryBrowserManager]:
    managers = hass.data.get(DOMAIN, {})
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


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})

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
            await manager.async_refresh("service")

    async def async_handle_query(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        response = manager.build_query_response({key: value for key, value in call.data.items() if key != CONF_ENTRY_ID})
        response[CONF_ENTRY_ID] = entry_id
        return response

    async def async_handle_detail(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        response = manager.build_archive_detail_response(archive_id)
        if response is None:
            raise HomeAssistantError(f"Archive {archive_id} was not found in the Bambuddy local store")
        response[CONF_ENTRY_ID] = entry_id
        response[CONF_ARCHIVE_ID] = archive_id
        return response

    async def async_handle_set_review_state(call: ServiceCall) -> ServiceResponse:
        entry_id, manager = _resolve_manager(hass, call.data.get(CONF_ENTRY_ID))
        archive_id = int(call.data[CONF_ARCHIVE_ID])
        mismatch_flags = call.data.get("mismatch_flags", "")
        if isinstance(mismatch_flags, list):
            mismatch_flags = ",".join(str(item).strip() for item in mismatch_flags if str(item).strip())
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
        try:
            deleted = await hass.async_add_executor_job(
                manager.store.delete_repair_lineage,
                archive_id,
                related_archive_id,
                str(call.data[CONF_RELATION_TYPE]),
            )
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error
        manager._notify_listeners()
        return {
            CONF_ENTRY_ID: entry_id,
            CONF_ARCHIVE_ID: archive_id,
            CONF_RELATED_ARCHIVE_ID: related_archive_id,
            CONF_RELATION_TYPE: str(call.data[CONF_RELATION_TYPE]),
            "deleted": deleted,
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
    if not hass.services.has_service(DOMAIN, SERVICE_SET_PRINT_HISTORY_REVIEW_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PRINT_HISTORY_REVIEW_STATE,
            async_handle_set_review_state,
            schema=SERVICE_REVIEW_STATE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
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
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    manager = PrintHistoryBrowserManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {DATA_MANAGER: manager}
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