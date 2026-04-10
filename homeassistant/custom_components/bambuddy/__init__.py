from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DATA_MANAGER, DOMAIN, PLATFORMS, SERVICE_REFRESH_PRINT_HISTORY_BROWSER
from .manager import PrintHistoryBrowserManager


CONF_ENTRY_ID = "entry_id"


SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Optional(CONF_ENTRY_ID): str})


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

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_PRINT_HISTORY_BROWSER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_PRINT_HISTORY_BROWSER,
            async_handle_refresh,
            schema=SERVICE_REFRESH_SCHEMA,
        )
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    manager = PrintHistoryBrowserManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {DATA_MANAGER: manager}
    await manager.async_initialize()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: PrintHistoryBrowserManager = hass.data[DOMAIN][entry.entry_id][DATA_MANAGER]
        await manager.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok