import ast
import json
import re
from pathlib import Path

import jinja2
import yaml
from jinja2.nativetypes import NativeEnvironment


ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "homeassistant" / "packages" / "3d_printing"
TOTALS_TEMPLATE = (
    PACKAGES
    / "core"
    / "trigger_template_sensors"
    / "spoolman_filament_totals.yaml"
)


class FakeState:
    def __init__(self, entity_id, state="ok", attributes=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        self.name = self.attributes.get("friendly_name", entity_id)


def _template_source(attribute):
    sensors = yaml.safe_load(TOTALS_TEMPLATE.read_text(encoding="utf-8"))
    return sensors[0]["attributes"][attribute]


def _render_totals(health, spool_states, health_registered=True):
    state_by_id = {state.entity_id: state for state in spool_states}
    expand_calls = []

    def states(entity_id):
        if entity_id == "sensor.spoolman_health":
            return health
        return state_by_id.get(entity_id, FakeState(entity_id, "unknown")).state

    def integration_entities(domain):
        assert domain == "spoolman"
        entities = list(state_by_id)
        if health_registered:
            entities.append("sensor.spoolman_health")
        return entities

    def expand(entity_ids):
        expand_calls.append(list(entity_ids))
        return [state_by_id[entity_id] for entity_id in entity_ids]

    environment = NativeEnvironment(undefined=jinja2.StrictUndefined)
    environment.tests["match"] = lambda value, pattern: re.match(pattern, value) is not None
    environment.filters["combine"] = lambda value, other: {**value, **other}
    environment.filters["from_json"] = json.loads
    rendered = environment.from_string(_template_source("totals")).render(
        states=states,
        integration_entities=integration_entities,
        expand=expand,
    )
    return ast.literal_eval(rendered.strip()), expand_calls


def test_totals_template_handles_healthy_partial_and_unavailable_entities():
    totals, expand_calls = _render_totals(
        "ok",
        [
            FakeState(
                "sensor.spoolman_spool_1",
                attributes={
                    "filament_id": 10,
                    "remaining_weight": 100,
                    "archived": False,
                    "extra_sealed": False,
                },
            ),
            FakeState("sensor.spoolman_spool_2", "unavailable"),
            FakeState(
                "sensor.spoolman_spool_3",
                attributes={"remaining_weight": 999},
            ),
            FakeState("sensor.spoolman_spool_4", "unknown"),
            FakeState(
                "sensor.spoolman_spool_5",
                attributes={
                    "filament_id": 10,
                    "remaining_weight": 50,
                    "extra_sealed": True,
                },
            ),
            FakeState(
                "sensor.spoolman_spool_5_remaining_weight",
                attributes={"filament_id": 999, "remaining_weight": 999},
            ),
        ],
    )

    assert totals == {
        "10": {
            "count": 2,
            "preferred_spool_entity_id": "sensor.spoolman_spool_1",
            "weight": 150,
        }
    }
    assert expand_calls == [
        [
            "sensor.spoolman_spool_1",
            "sensor.spoolman_spool_2",
            "sensor.spoolman_spool_3",
            "sensor.spoolman_spool_4",
            "sensor.spoolman_spool_5",
        ]
    ]


def test_totals_template_fails_closed_without_scanning_during_outage():
    totals, expand_calls = _render_totals(
        "unavailable",
        [FakeState("sensor.spoolman_spool_1", "unavailable")],
    )

    assert totals == {}
    assert expand_calls == []


def test_totals_template_handles_empty_inventory_and_recovery():
    empty_totals, _ = _render_totals("ok", [])
    recovered_totals, _ = _render_totals(
        "ok",
        [
            FakeState(
                "sensor.spoolman_spool_7",
                attributes={"filament_id": 22, "remaining_weight": 75},
            )
        ],
    )

    assert empty_totals == {}
    assert recovered_totals["22"]["weight"] == 75


def test_totals_template_supports_integrations_without_health_entity():
    totals, _ = _render_totals(
        "unknown",
        [
            FakeState(
                "sensor.spoolman_spool_9",
                attributes={"filament_id": 30, "remaining_weight": 25},
            )
        ],
        health_registered=False,
    )

    assert totals["30"]["weight"] == 25


def test_spoolman_templates_avoid_broad_sensor_dependency_and_unsafe_access():
    active_yaml = [
        path
        for path in PACKAGES.rglob("*.yaml")
        if "backups" not in path.parts
    ]
    unsafe = []
    broad_spool_scans = []
    for path in active_yaml:
        content = path.read_text(encoding="utf-8")
        if ".attributes.filament_id" in content:
            unsafe.append(path.relative_to(ROOT).as_posix())
        if any(
            pattern in content
            for pattern in (
                "set spool_entities = states.sensor",
                "for s in states.sensor",
                "for spool in states.sensor",
            )
        ):
            broad_spool_scans.append(path.relative_to(ROOT).as_posix())

    assert unsafe == []
    assert broad_spool_scans == []


def test_inventory_cache_is_trigger_based_and_debounced():
    cache = (
        PACKAGES / "core" / "spoolman_inventory_cache.yaml"
    ).read_text(encoding="utf-8")
    core_loader = (PACKAGES / "core" / "core_loader.yaml").read_text(encoding="utf-8")

    assert "event_type: spoolman_inventory_cache_refresh" in cache
    assert "mode: restart" in cache
    assert "seconds: 3" in cache
    assert "ams_[12]_tray_[1-4]" in cache
    assert "external_spool)_spool_override" in cache
    assert "trigger_template_sensors" in cache
    assert "spoolman_filament_totals.yaml" not in core_loader


def test_service_guards_preserve_explicit_unavailable_value():
    guarded_files = [
        PACKAGES / "filament_tag" / "scripts" / "update_spool_location-script.yaml",
        PACKAGES / "spoolman_sync" / "automations" / "print_complete-update_filament_usage.yaml",
        PACKAGES / "spoolman_sync" / "scripts" / "spool_replace_execute-script.yaml",
        PACKAGES / "print_history" / "scripts" / "reenrich_print_history_archive.yaml",
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in guarded_files)

    assert "default(true, true)" not in content
    assert (
        "state_attr('sensor.spoolman_filament_totals', 'available') is true"
        in content
    )
    assert (
        "state_attr('sensor.spoolman_filament_totals', 'available') is not true"
        in content
    )
