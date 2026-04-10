from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_ROOT = REPO_ROOT / "homeassistant" / "custom_components" / "bambuddy"
CONFIG_FLOW_PATH = COMPONENT_ROOT / "config_flow.py"


def _install_homeassistant_stubs() -> None:
    voluptuous_module = ModuleType("voluptuous")
    aiohttp_module = ModuleType("aiohttp")
    homeassistant_module = ModuleType("homeassistant")
    config_entries_module = ModuleType("homeassistant.config_entries")
    const_module = ModuleType("homeassistant.const")
    helpers_module = ModuleType("homeassistant.helpers")
    aiohttp_client_module = ModuleType("homeassistant.helpers.aiohttp_client")

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
    voluptuous_module.All = lambda *validators: validators
    voluptuous_module.Range = lambda **kwargs: kwargs

    aiohttp_module.ClientResponseError = ClientResponseError
    aiohttp_module.ClientSession = ClientSession
    aiohttp_module.ClientTimeout = ClientTimeout

    config_entries_module.ConfigFlow = ConfigFlow
    config_entries_module.OptionsFlow = OptionsFlow
    config_entries_module.ConfigEntry = ConfigEntry
    const_module.Platform = Platform
    aiohttp_client_module.async_get_clientsession = lambda hass: object()
    helpers_module.aiohttp_client = aiohttp_client_module

    homeassistant_module.config_entries = config_entries_module
    homeassistant_module.const = const_module
    homeassistant_module.helpers = helpers_module

    sys.modules["voluptuous"] = voluptuous_module
    sys.modules["aiohttp"] = aiohttp_module
    sys.modules["homeassistant"] = homeassistant_module
    sys.modules["homeassistant.config_entries"] = config_entries_module
    sys.modules["homeassistant.const"] = const_module
    sys.modules["homeassistant.helpers"] = helpers_module
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_module


def _install_component_package_stubs() -> None:
    custom_components_module = ModuleType("custom_components")
    custom_components_module.__path__ = [str(COMPONENT_ROOT.parent)]

    bambuddy_package = ModuleType("custom_components.bambuddy")
    bambuddy_package.__path__ = [str(COMPONENT_ROOT)]

    sys.modules["custom_components"] = custom_components_module
    sys.modules["custom_components.bambuddy"] = bambuddy_package


def test_bambuddy_config_flow_imports_without_home_assistant_runtime() -> None:
    _install_homeassistant_stubs()
    _install_component_package_stubs()

    spec = importlib.util.spec_from_file_location(
        "custom_components.bambuddy.config_flow",
        CONFIG_FLOW_PATH,
        submodule_search_locations=[str(COMPONENT_ROOT)],
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.DOMAIN == "bambuddy"
    assert module.BambuddyConfigFlow._configured_domain == "bambuddy"
    assert issubclass(module.BambuddyOptionsFlow, sys.modules["homeassistant.config_entries"].OptionsFlow)