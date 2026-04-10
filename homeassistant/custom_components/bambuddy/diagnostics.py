from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DATA_MANAGER, DOMAIN


TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    manager_entry = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    manager = manager_entry.get(DATA_MANAGER)

    diagnostics: dict[str, Any] = {
        "entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT),
        "loaded": manager is not None,
    }

    if manager is not None:
        diagnostics["manager"] = manager.diagnostics()

    return diagnostics