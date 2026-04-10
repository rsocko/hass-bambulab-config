from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import BambuddyApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_FETCH_TIMEOUT_SECONDS,
    CONF_SCAN_INTERVAL_SECONDS,
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    values = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL, default=values.get(CONF_BASE_URL, "")): str,
            vol.Required(CONF_API_KEY, default=values.get(CONF_API_KEY, "")): str,
            vol.Required(
                CONF_FETCH_TIMEOUT_SECONDS,
                default=values.get(CONF_FETCH_TIMEOUT_SECONDS, DEFAULT_FETCH_TIMEOUT_SECONDS),
            ): vol.All(int, vol.Range(min=5, max=120)),
            vol.Required(
                CONF_SCAN_INTERVAL_SECONDS,
                default=values.get(CONF_SCAN_INTERVAL_SECONDS, DEFAULT_SCAN_INTERVAL_SECONDS),
            ): vol.All(int, vol.Range(min=30, max=3600)),
        }
    )


async def _validate_input(hass, data: dict[str, Any]) -> None:
    session = aiohttp_client.async_get_clientsession(hass)
    client = BambuddyApiClient(
        session,
        str(data[CONF_BASE_URL]),
        str(data[CONF_API_KEY]),
        int(data[CONF_FETCH_TIMEOUT_SECONDS]),
    )
    await client.async_fetch_archives(limit=1)


class BambuddyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._async_current_entries():
                return self.async_abort(reason="single_instance_allowed")

            normalized_url = str(user_input[CONF_BASE_URL]).strip().rstrip("/")
            user_input[CONF_BASE_URL] = normalized_url
            await self.async_set_unique_id(DOMAIN)

            try:
                await _validate_input(self.hass, user_input)
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Bambuddy", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return BambuddyOptionsFlow(config_entry)


class BambuddyOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        defaults = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            normalized_url = str(user_input[CONF_BASE_URL]).strip().rstrip("/")
            user_input[CONF_BASE_URL] = normalized_url
            try:
                await _validate_input(self.hass, user_input)
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=_schema(defaults), errors=errors)