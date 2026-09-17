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
METRICS_TEMPLATE = (
    PACKAGES
    / "filament_catalog"
    / "template_sensors"
    / "filament_catalog_metrics.yaml"
)
SAFE_RENDERED_SIZE = 200_000


class FakeState:
    def __init__(self, entity_id, state="ok", attributes=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        self.name = self.attributes.get("friendly_name", entity_id)

    def __repr__(self):
        return (
            f"<state {self.entity_id}={self.state}; "
            f"{self.attributes!r}>"
        )


def _template_source(attribute):
    sensors = yaml.safe_load(TOTALS_TEMPLATE.read_text(encoding="utf-8"))
    return sensors[0]["attributes"][attribute]


def _metric_attribute_source(attribute):
    config = yaml.safe_load(METRICS_TEMPLATE.read_text(encoding="utf-8"))[0]
    return config["sensor"][0]["attributes"][attribute]


def _render_projection(attribute, health, spool_states, health_registered=True):
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
    rendered = environment.from_string(_template_source(attribute)).render(
        states=states,
        integration_entities=integration_entities,
        expand=expand,
    )
    return ast.literal_eval(rendered.strip()), expand_calls


def _render_totals(health, spool_states, health_registered=True):
    return _render_projection(
        "totals", health, spool_states, health_registered
    )


def _render_metric_variables(spool_count, filament_count):
    config = yaml.safe_load(METRICS_TEMPLATE.read_text(encoding="utf-8"))[0]
    variables = config["variables"]
    entity_ids = [
        *(f"sensor.spoolman_spool_{index}" for index in range(spool_count)),
        *(
            f"sensor.spoolman_filament_{index}"
            for index in range(filament_count)
        ),
    ]

    environment = NativeEnvironment(undefined=jinja2.StrictUndefined)
    environment.tests["match"] = lambda value, pattern: (
        re.match(pattern, value) is not None
    )
    rendered = {}
    for name, source in variables.items():
        rendered[name] = environment.from_string(source).render(
            integration_entities=lambda domain: entity_ids,
            **rendered,
        )
    return variables, rendered


def _render_metric_attribute(attribute, spool_states, parse_json=True):
    state_by_id = {state.entity_id: state for state in spool_states}
    environment = NativeEnvironment(undefined=jinja2.StrictUndefined)
    environment.tests["match"] = lambda value, pattern: (
        re.match(pattern, value) is not None
    )
    environment.filters["combine"] = lambda value, other: {**value, **other}
    environment.filters["tojson"] = json.dumps
    rendered = environment.from_string(
        _metric_attribute_source(attribute)
    ).render(
        spool_ids=list(state_by_id),
        filament_ids=[],
        spool_source_count=len(state_by_id),
        filament_source_count=0,
        expand=lambda entity_ids: [
            state_by_id[entity_id] for entity_id in entity_ids
        ],
        states=lambda _entity_id: "0",
        is_state=lambda _entity_id, _state: False,
        now=lambda: None,
        as_timestamp=lambda _value, default=0: default,
    )
    return json.loads(rendered) if parse_json else rendered


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


def test_spoolman_projection_payloads_stay_below_home_assistant_limit():
    rich_attributes = {
        f"attribute_{index}": "x" * 64
        for index in range(32)
    }
    current_spools = [
        FakeState(
            f"sensor.spoolman_spool_{index}",
            attributes={
                **rich_attributes,
                "filament_id": index,
                "remaining_weight": 1000,
                "friendly_name": f"Production spool {index} " + ("n" * 120),
                "location": "Production storage " + ("l" * 80),
            },
        )
        for index in range(184)
    ]
    assert len(str(current_spools).encode()) > 262_144

    current_options, _ = _render_projection(
        "spool_options", "ok", current_spools
    )
    assert len(current_options) == 184
    assert len(json.dumps(current_options).encode()) < SAFE_RENDERED_SIZE
    empty_labels, _ = _render_projection(
        "spool_options",
        "ok",
        [
            FakeState(
                "sensor.spoolman_spool_999",
                attributes={"friendly_name": None, "location": ""},
            )
        ],
    )
    assert empty_labels == [
        {
            "id": "999",
            "name": "sensor.spoolman_spool_999",
            "location": "Unknown",
        }
    ]

    boundary_spools = [
        FakeState(
            f"sensor.spoolman_spool_{index}",
            attributes={
                "filament_id": index,
                "remaining_weight": 1000,
                "friendly_name": f"Boundary spool {index} " + ("n" * 120),
                "location": "Boundary storage " + ("l" * 80),
            },
        )
        for index in range(5000)
    ]
    boundary_options, _ = _render_projection(
        "spool_options", "ok", boundary_spools
    )
    boundary_totals, _ = _render_totals("ok", boundary_spools)

    assert len(boundary_options) == 750
    assert len(json.dumps(boundary_options).encode()) < SAFE_RENDERED_SIZE
    assert len(boundary_totals) == 1500
    assert len(json.dumps(boundary_totals).encode()) < SAFE_RENDERED_SIZE


def test_metrics_trigger_variables_never_render_full_state_objects():
    current_variables, current_rendered = _render_metric_variables(184, 184)
    boundary_variables, boundary_rendered = _render_metric_variables(5000, 5000)

    assert "spool_entities" not in current_variables
    assert "filament_entities" not in current_variables
    assert all(
        len(str(value).encode()) < SAFE_RENDERED_SIZE
        for value in current_rendered.values()
    )
    assert len(boundary_rendered["spool_ids"]) == 500
    assert len(boundary_rendered["filament_ids"]) == 500
    assert all(
        len(str(value).encode()) < SAFE_RENDERED_SIZE
        for value in boundary_rendered.values()
    )


def test_metrics_large_list_outputs_are_bounded_and_report_truncation():
    boundary_spools = [
        FakeState(
            f"sensor.spoolman_spool_{index}",
            attributes={
                "archived": False,
                "filament_id": index,
                "remaining_weight": 1,
                "extra_sealed": False,
                "extra_desiccant_in_spool": False,
                "filament_vendor_name": "Bambu Lab",
                "extra_spool_uuid": "",
                "extra_tag": "t" * 200,
                "filament_extra_profile_name": "",
                "filament_color_hex": "abcdef",
            },
        )
        for index in range(500)
    ]

    alerts = _render_metric_attribute(
        "alert_entity_ids_json", boundary_spools
    )
    quality = _render_metric_attribute("data_quality_json", boundary_spools)

    assert alerts["_truncated"] is True
    assert quality["_truncated"] is True
    assert all(
        len(entity_ids) <= 100
        for name, entity_ids in alerts.items()
        if name != "_truncated"
    )
    assert all(
        len(issues) <= 100
        for name, issues in quality.items()
        if name != "_truncated"
    )
    assert len(json.dumps(alerts).encode()) < SAFE_RENDERED_SIZE
    assert len(json.dumps(quality).encode()) < SAFE_RENDERED_SIZE
    metric_attributes = yaml.safe_load(
        METRICS_TEMPLATE.read_text(encoding="utf-8")
    )[0]["sensor"][0]["attributes"]
    for attribute in metric_attributes:
        rendered = _render_metric_attribute(
            attribute, boundary_spools, parse_json=False
        )
        assert len(str(rendered).encode()) < SAFE_RENDERED_SIZE, attribute


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


def test_pin_selector_state_uses_the_same_bounded_labels_as_options():
    selectors = (
        PACKAGES
        / "spoolman_sync"
        / "template_sensors"
        / "template_select_tray_spool_pin_selectors.yaml"
    ).read_text(encoding="utf-8")

    assert selectors.count("string)[:96]") == 9
    assert selectors.count("string)[:48]") == 9


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
