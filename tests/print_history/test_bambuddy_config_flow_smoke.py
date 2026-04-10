from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_ROOT = REPO_ROOT / "homeassistant" / "custom_components" / "bambuddy"
INIT_PATH = COMPONENT_ROOT / "__init__.py"
CONFIG_FLOW_PATH = COMPONENT_ROOT / "config_flow.py"
DIAGNOSTICS_PATH = COMPONENT_ROOT / "diagnostics.py"


def _install_homeassistant_stubs() -> None:
    voluptuous_module = ModuleType("voluptuous")
    aiohttp_module = ModuleType("aiohttp")
    homeassistant_module = ModuleType("homeassistant")
    components_module = ModuleType("homeassistant.components")
    components_diagnostics_module = ModuleType("homeassistant.components.diagnostics")
    config_entries_module = ModuleType("homeassistant.config_entries")
    const_module = ModuleType("homeassistant.const")
    core_module = ModuleType("homeassistant.core")
    exceptions_module = ModuleType("homeassistant.exceptions")
    helpers_module = ModuleType("homeassistant.helpers")
    aiohttp_client_module = ModuleType("homeassistant.helpers.aiohttp_client")
    helpers_event_module = ModuleType("homeassistant.helpers.event")
    util_module = ModuleType("homeassistant.util")
    util_dt_module = ModuleType("homeassistant.util.dt")

    class ConfigFlow:
        def __init_subclass__(cls, *, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            cls._configured_domain = domain

    class OptionsFlow:
        pass

    class ConfigEntry:
        pass

    class Platform:
        SENSOR = "sensor"

    class HomeAssistant:
        pass

    class ServiceCall:
        data = {}
        return_response = True

    class SupportsResponse:
        ONLY = "only"

    class HomeAssistantError(Exception):
        pass

    class Event:
        def __init__(self, data=None) -> None:
            self.data = data or {}

    class ClientResponseError(Exception):
        def __init__(self, status: int = 0) -> None:
            self.status = status
            super().__init__(status)

    class ClientSession:
        pass

    class ClientTimeout:
        def __init__(self, total=None) -> None:
            self.total = total

    voluptuous_module.Schema = lambda value: value
    voluptuous_module.Required = lambda key, default=None: key
    voluptuous_module.Optional = lambda key, default=None: key
    voluptuous_module.All = lambda *validators: validators
    voluptuous_module.Range = lambda **kwargs: kwargs
    voluptuous_module.Any = lambda *validators: validators
    voluptuous_module.Coerce = lambda type_: type_

    aiohttp_module.ClientResponseError = ClientResponseError
    aiohttp_module.ClientSession = ClientSession
    aiohttp_module.ClientTimeout = ClientTimeout

    components_diagnostics_module.async_redact_data = lambda value, to_redact: value
    config_entries_module.ConfigFlow = ConfigFlow
    config_entries_module.OptionsFlow = OptionsFlow
    config_entries_module.ConfigEntry = ConfigEntry
    const_module.Platform = Platform
    core_module.HomeAssistant = HomeAssistant
    core_module.ServiceCall = ServiceCall
    core_module.ServiceResponse = dict
    core_module.SupportsResponse = SupportsResponse
    core_module.Event = Event
    core_module.callback = lambda func: func
    exceptions_module.HomeAssistantError = HomeAssistantError
    aiohttp_client_module.async_get_clientsession = lambda hass: object()
    helpers_event_module.async_track_state_change_event = lambda *args, **kwargs: (lambda: None)
    helpers_event_module.async_track_time_interval = lambda *args, **kwargs: (lambda: None)
    util_dt_module.utcnow = lambda: None
    helpers_module.aiohttp_client = aiohttp_client_module
    util_module.dt = util_dt_module

    homeassistant_module.config_entries = config_entries_module
    homeassistant_module.components = components_module
    homeassistant_module.const = const_module
    homeassistant_module.core = core_module
    homeassistant_module.helpers = helpers_module
    homeassistant_module.util = util_module

    sys.modules["voluptuous"] = voluptuous_module
    sys.modules["aiohttp"] = aiohttp_module
    sys.modules["homeassistant"] = homeassistant_module
    sys.modules["homeassistant.components"] = components_module
    sys.modules["homeassistant.components.diagnostics"] = components_diagnostics_module
    sys.modules["homeassistant.config_entries"] = config_entries_module
    sys.modules["homeassistant.const"] = const_module
    sys.modules["homeassistant.core"] = core_module
    sys.modules["homeassistant.exceptions"] = exceptions_module
    sys.modules["homeassistant.helpers"] = helpers_module
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_module
    sys.modules["homeassistant.helpers.event"] = helpers_event_module
    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = util_dt_module


def _install_component_package_stubs() -> None:
    custom_components_module = ModuleType("custom_components")
    custom_components_module.__path__ = [str(COMPONENT_ROOT.parent)]

    bambuddy_package = ModuleType("custom_components.bambuddy")
    bambuddy_package.__path__ = [str(COMPONENT_ROOT)]

    sys.modules["custom_components"] = custom_components_module
    sys.modules["custom_components.bambuddy"] = bambuddy_package


def _exec_module(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_bambuddy_config_flow_imports_without_home_assistant_runtime() -> None:
    _install_homeassistant_stubs()
    _install_component_package_stubs()

    package_module = _exec_module("custom_components.bambuddy", INIT_PATH)
    package_module.__path__ = [str(COMPONENT_ROOT)]
    module = _exec_module("custom_components.bambuddy.config_flow", CONFIG_FLOW_PATH)
    diagnostics_module = _exec_module("custom_components.bambuddy.diagnostics", DIAGNOSTICS_PATH)

    assert module.DOMAIN == "bambuddy"
    assert module.BambuddyConfigFlow._configured_domain == "bambuddy"
    assert issubclass(module.BambuddyOptionsFlow, sys.modules["homeassistant.config_entries"].OptionsFlow)
    assert hasattr(diagnostics_module, "async_get_config_entry_diagnostics")