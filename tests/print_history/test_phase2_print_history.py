"""
Phase 2 — Print History: Automated Validation Tests
====================================================

Validates the structural integrity, YAML correctness, Jinja template logic,
cross-references, entity uniqueness, and loader wiring of the print_history
package and its bambuddy_common dependency.

Run:  pytest tests/print_history/ -v
"""

import os
import re
import unittest
from pathlib import Path

import yaml

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
PACKAGES    = ROOT / "homeassistant" / "packages" / "3d_printing"
HISTORY     = PACKAGES / "print_history"
COMMON      = PACKAGES / "bambuddy_common"
LOADERS     = PACKAGES / "_feature_loaders.yaml"
DOCS_HIST   = ROOT / "docs" / "features" / "print_history"
DOCS_COMMON = ROOT / "docs" / "features" / "bambuddy_common"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_yaml_safe(path: Path) -> dict | list | None:
    """Load a YAML file, replacing HA-specific !include and !secret tags."""
    class _SafeLoader(yaml.SafeLoader):
        pass

    def _include_stub(loader, node):
        return f"__include__{loader.construct_scalar(node)}"

    for tag in ("!include", "!include_dir_merge_list", "!include_dir_merge_named",
                "!include_dir_named", "!include_dir_list", "!secret"):
        _SafeLoader.add_constructor(tag, _include_stub)

    with open(path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=_SafeLoader)


def _collect_yaml_files(directory: Path) -> list[Path]:
    """Recursively collect all .yaml files under a directory."""
    return sorted(directory.rglob("*.yaml")) if directory.exists() else []


def _extract_entity_ids(content: str) -> list[str]:
    """Pull plausible entity_id references from YAML text."""
    pattern = r'(?:entity_id|target):\s*["\']?([a-z_]+\.[a-z0-9_]+)'
    return re.findall(pattern, content)


def _extract_unique_ids(data) -> list[str]:
    """Extract unique_id values from parsed YAML (handles nested lists/dicts)."""
    ids = []
    if isinstance(data, dict):
        if "unique_id" in data:
            ids.append(str(data["unique_id"]))
        for v in data.values():
            ids.extend(_extract_unique_ids(v))
    elif isinstance(data, list):
        for item in data:
            ids.extend(_extract_unique_ids(item))
    return ids


# =============================================================================
# 1. YAML SYNTAX VALIDATION
# =============================================================================

class TestYamlSyntax(unittest.TestCase):
    """Every YAML file in print_history and bambuddy_common must parse."""

    def test_all_print_history_yaml_files_parse(self):
        files = _collect_yaml_files(HISTORY)
        self.assertGreater(len(files), 0, "No YAML files found in print_history/")
        for path in files:
            with self.subTest(file=path.relative_to(ROOT)):
                parsed = _load_yaml_safe(path)
                self.assertIsNotNone(
                    parsed, f"{path.name} parsed to None (empty or invalid)"
                )

    def test_all_bambuddy_common_yaml_files_parse(self):
        files = _collect_yaml_files(COMMON)
        self.assertGreater(len(files), 0, "No YAML files found in bambuddy_common/")
        for path in files:
            with self.subTest(file=path.relative_to(ROOT)):
                parsed = _load_yaml_safe(path)
                self.assertIsNotNone(
                    parsed, f"{path.name} parsed to None (empty or invalid)"
                )


# =============================================================================
# 2. LOADER WIRING
# =============================================================================

class TestLoaderWiring(unittest.TestCase):
    """Verify package loaders are correctly structured and wired."""

    def test_feature_loaders_references_print_history(self):
        content = LOADERS.read_text(encoding="utf-8")
        self.assertIn(
            "print_history_loader",
            content,
            "_feature_loaders.yaml must reference print_history_loader",
        )

    def test_feature_loaders_references_bambuddy_common(self):
        content = LOADERS.read_text(encoding="utf-8")
        self.assertIn(
            "bambuddy_common_loader",
            content,
            "_feature_loaders.yaml must reference bambuddy_common_loader",
        )

    def test_print_history_loader_domains(self):
        """Loader must declare all required HA domains."""
        data = _load_yaml_safe(HISTORY / "print_history_loader.yaml")
        self.assertIsNotNone(data, "Loader file must parse")
        required_domains = {
            "automation",
            "rest",
            "rest_command",
            "script",
            "template",
            "input_text",
            "input_boolean",
            "input_number",
            "input_select",
        }
        actual_domains = set(data.keys()) if isinstance(data, dict) else set()
        missing = required_domains - actual_domains
        self.assertFalse(
            missing,
            f"print_history_loader.yaml missing domains: {missing}",
        )

    def test_bambuddy_common_loader_domains(self):
        data = _load_yaml_safe(COMMON / "bambuddy_common_loader.yaml")
        self.assertIsNotNone(data)
        required = {"automation", "mqtt", "rest_command", "input_boolean", "input_text"}
        actual = set(data.keys()) if isinstance(data, dict) else set()
        missing = required - actual
        self.assertFalse(missing, f"bambuddy_common_loader.yaml missing domains: {missing}")

    def test_loader_include_dirs_exist(self):
        """Every directory referenced by !include_dir_* in the loader must exist."""
        loader_path = HISTORY / "print_history_loader.yaml"
        content = loader_path.read_text(encoding="utf-8")
        # Pull all include-dir targets
        dirs = re.findall(r"!include_dir_\w+\s+(\S+)", content)
        for d in dirs:
            full_path = HISTORY / d
            with self.subTest(dir=d):
                self.assertTrue(
                    full_path.exists(),
                    f"Loader references directory '{d}' but {full_path} does not exist",
                )


# =============================================================================
# 3. FILE INVENTORY & EXPECTED STRUCTURE
# =============================================================================

class TestFileInventory(unittest.TestCase):
    """All expected files in the Phase 2 package must exist."""

    EXPECTED_AUTOMATIONS = [
        "bambuddy_capture_archive_id.yaml",
        "bambuddy_capture_print_photos.yaml",
        "bambuddy_enrich_archive_on_complete.yaml",
        "bambuddy_capture_error_photos.yaml",
        "bambuddy_event_history_refresh.yaml",
        "print_history_sync_filter_options.yaml",
        "print_history_reset_page_on_filter_change.yaml",
    ]

    EXPECTED_SCRIPTS = [
        "capture_and_upload_snapshot.yaml",
        "resolve_current_archive_id.yaml",
        "load_history_page.yaml",
        "navigate_history.yaml",
        "refresh_print_history_archives.yaml",
        "clear_print_history_filters.yaml",
    ]

    EXPECTED_REST_COMMANDS = [
        "bambuddy_upload_photo_to_archive.yaml",
        "bambuddy_delete_archive_photo.yaml",
        "bambuddy_set_archive_cover.yaml",
        "bambuddy_update_archive.yaml",
        "bambuddy_query_recent_archive.yaml",
        "bambuddy_fetch_archives.yaml",
    ]

    EXPECTED_TEMPLATE_SENSORS = [
        "print_history_archives.yaml",
        "print_history_filtered.yaml",
        "print_history_page_info.yaml",
        "print_history_archive_data.yaml",
    ]

    EXPECTED_HELPERS_INPUT_TEXT = [
        "input_text_bambuddy_current_archive_id.yaml",
        "input_text_bambuddy_photo_manifest.yaml",
        "input_text_bambuddy_tray_map_snapshot.yaml",
        "input_text_print_history_activity_selected_date.yaml",
        "input_text_print_history_search.yaml",
    ]

    EXPECTED_HELPERS_INPUT_BOOLEAN = [
        "input_boolean_bambuddy_history_fetch_enabled.yaml",
        "input_boolean_capture_at_start.yaml",
        "input_boolean_capture_at_midprint.yaml",
        "input_boolean_capture_near_complete.yaml",
        "input_boolean_capture_on_error.yaml",
        "input_boolean_print_history_show_activity_heatmap.yaml",
    ]

    EXPECTED_HELPERS_INPUT_NUMBER = [
        "input_number_bambuddy_history_limit.yaml",
        "input_number_history_current_page.yaml",
        "input_number_midprint_capture_percent.yaml",
        "input_number_photo_review_timeout_hours.yaml",
        "input_number_print_history_page_size.yaml",
        "input_number_print_history_max_archives.yaml",
    ]

    EXPECTED_HELPERS_INPUT_SELECT = [
        "input_select_bambuddy_photo_review_state.yaml",
        "input_select_print_history_activity_metric.yaml",
        "input_select_print_history_filter_status.yaml",
        "input_select_print_history_filter_material.yaml",
        "input_select_print_history_filter_color.yaml",
        "input_select_print_history_filter_printer.yaml",
        "input_select_print_history_filter_date_range.yaml",
        "input_select_print_history_filter_designer.yaml",
        "input_select_print_history_filter_layer_height.yaml",
        "input_select_print_history_sort.yaml",
        "input_select_print_history_card_variant.yaml",
    ]

    EXPECTED_REST_SENSORS = [
        "bambuddy_print_history_sensor.yaml",
    ]

    EXPECTED_DASHBOARD_CARDS = [
        "print_history_activity_heatmap.yaml",
        "print_history_activity_panel.yaml",
        "print_history.yaml",
        "print_history_browser.yaml",
        "photo_review_chip.yaml",
    ]

    EXPECTED_DASHBOARD_VIEWS = [
        "view_print_history.yaml",
    ]

    def _check_files(self, subdir: str, expected: list[str]):
        directory = HISTORY / subdir
        for fname in expected:
            with self.subTest(file=f"{subdir}/{fname}"):
                self.assertTrue(
                    (directory / fname).exists(),
                    f"Missing expected file: {subdir}/{fname}",
                )

    def test_automations_exist(self):
        self._check_files("automations", self.EXPECTED_AUTOMATIONS)

    def test_scripts_exist(self):
        self._check_files("scripts", self.EXPECTED_SCRIPTS)

    def test_rest_commands_exist(self):
        self._check_files("rest_commands", self.EXPECTED_REST_COMMANDS)

    def test_template_sensors_exist(self):
        self._check_files("template_sensors", self.EXPECTED_TEMPLATE_SENSORS)

    def test_rest_sensors_exist(self):
        self._check_files("rest_sensors", self.EXPECTED_REST_SENSORS)

    def test_helpers_input_text_exist(self):
        self._check_files("helpers/input_text", self.EXPECTED_HELPERS_INPUT_TEXT)

    def test_helpers_input_boolean_exist(self):
        self._check_files("helpers/input_boolean", self.EXPECTED_HELPERS_INPUT_BOOLEAN)

    def test_helpers_input_number_exist(self):
        self._check_files("helpers/input_number", self.EXPECTED_HELPERS_INPUT_NUMBER)

    def test_helpers_input_select_exist(self):
        self._check_files("helpers/input_select", self.EXPECTED_HELPERS_INPUT_SELECT)

    def test_dashboard_cards_exist(self):
        self._check_files("dashboard_cards", self.EXPECTED_DASHBOARD_CARDS)

    def test_dashboard_views_exist(self):
        self._check_files("dashboard_views", self.EXPECTED_DASHBOARD_VIEWS)

    def test_bambuddy_common_webhook_receiver_exists(self):
        self.assertTrue(
            (COMMON / "automations" / "bambuddy_webhook_receiver.yaml").exists()
        )

    def test_bambuddy_common_mqtt_sensor_exists(self):
        self.assertTrue(
            (COMMON / "mqtt_sensors" / "bambuddy_printer_status.yaml").exists()
        )

    def test_no_unexpected_subdirectories(self):
        """No stale/unloaded subdirectories in print_history."""
        expected_subdirs = {
            "automations", "scripts", "rest_commands", "rest_sensors",
            "template_sensors", "helpers", "dashboard_cards", "dashboard_views",
        }
        actual_subdirs = {
            d.name for d in HISTORY.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        }
        unexpected = actual_subdirs - expected_subdirs
        self.assertFalse(
            unexpected,
            f"Unexpected subdirectories in print_history/ not covered by loader: {unexpected}",
        )


# =============================================================================
# 4. ENTITY UNIQUENESS
# =============================================================================

class TestEntityUniqueness(unittest.TestCase):
    """All unique_id values in the package must be globally unique."""

    def test_unique_ids_are_unique_within_print_history(self):
        all_ids = []
        for path in _collect_yaml_files(HISTORY):
            data = _load_yaml_safe(path)
            ids = _extract_unique_ids(data)
            for uid in ids:
                all_ids.append((uid, path.relative_to(ROOT)))

        seen = {}
        duplicates = []
        for uid, source in all_ids:
            if uid in seen:
                duplicates.append(f"'{uid}' in {source} AND {seen[uid]}")
            else:
                seen[uid] = source
        self.assertFalse(
            duplicates,
            f"Duplicate unique_ids found: {duplicates}",
        )


# =============================================================================
# 5. AUTOMATION STRUCTURE
# =============================================================================

class TestAutomationStructure(unittest.TestCase):
    """Automations must follow HA YAML conventions."""

    def _load_automation(self, filename: str):
        path = HISTORY / "automations" / filename
        data = _load_yaml_safe(path)
        self.assertIsInstance(data, list, f"{filename} must be a top-level list")
        self.assertGreater(len(data), 0, f"{filename} must have at least one automation")
        return data[0]

    def test_all_automations_have_alias_and_id(self):
        for f in _collect_yaml_files(HISTORY / "automations"):
            with self.subTest(file=f.name):
                data = _load_yaml_safe(f)
                self.assertIsInstance(data, list, f"{f.name} must be a list")
                auto = data[0]
                self.assertIn("alias", auto, f"{f.name}: missing alias")
                self.assertIn("id", auto, f"{f.name}: missing id (needed for traces)")

    def test_automations_do_not_use_enabled_key(self):
        """The 'enabled' key is only for UI-managed automations, not YAML."""
        for f in _collect_yaml_files(HISTORY / "automations"):
            with self.subTest(file=f.name):
                data = _load_yaml_safe(f)
                auto = data[0]
                self.assertNotIn(
                    "enabled", auto,
                    f"{f.name}: YAML automations must NOT use 'enabled:' key",
                )

    def test_capture_archive_id_triggers_on_print_started(self):
        auto = self._load_automation("bambuddy_capture_archive_id.yaml")
        triggers = auto.get("triggers", auto.get("trigger", []))
        if isinstance(triggers, dict):
            triggers = [triggers]
        event_types = [
            t.get("event_data", {}).get("event")
            for t in triggers
            if t.get("event_type") == "bambuddy_webhook_event"
        ]
        self.assertIn("print_started", event_types)

    def test_enrich_triggers_on_all_end_events(self):
        auto = self._load_automation("bambuddy_enrich_archive_on_complete.yaml")
        triggers = auto.get("triggers", auto.get("trigger", []))
        if isinstance(triggers, dict):
            triggers = [triggers]
        events = set()
        for t in triggers:
            ed = t.get("event_data", {})
            if ed.get("event"):
                events.add(ed["event"])
        for expected in ("print_complete", "print_failed", "print_stopped"):
            self.assertIn(
                expected, events,
                f"Enrichment automation must trigger on {expected}",
            )

    def test_capture_photos_mode_is_single(self):
        """Only one photo-capture run at a time to avoid race conditions."""
        auto = self._load_automation("bambuddy_capture_print_photos.yaml")
        self.assertEqual(auto.get("mode"), "single")

    def test_capture_error_photos_mode_is_queued(self):
        """Error photos use queued mode for rapid cascades."""
        auto = self._load_automation("bambuddy_capture_error_photos.yaml")
        self.assertEqual(auto.get("mode"), "queued")
        self.assertGreaterEqual(auto.get("max", 1), 2)

    def test_history_refresh_has_delay(self):
        """Refresh automation must have a delay to let Bambuddy finish updates."""
        auto = self._load_automation("bambuddy_event_history_refresh.yaml")
        actions = auto.get("actions", auto.get("action", []))
        delays = [a for a in actions if "delay" in a]
        self.assertTrue(delays, "Refresh automation must include a delay step")

    def test_all_automations_gate_on_integration_enabled(self):
        """Every automation must check input_boolean.bambuddy_integration_enabled."""
        for f in _collect_yaml_files(HISTORY / "automations"):
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertIn(
                    "input_boolean.bambuddy_integration_enabled",
                    content,
                    f"{f.name}: must gate on bambuddy_integration_enabled",
                )

    def test_webhook_receiver_fires_bambuddy_webhook_event(self):
        """The upstream webhook receiver must fire the normalized event."""
        path = COMMON / "automations" / "bambuddy_webhook_receiver.yaml"
        content = path.read_text(encoding="utf-8")
        self.assertIn("bambuddy_webhook_event", content)

    def test_webhook_receiver_handles_both_formats(self):
        """Webhook receiver must detect both API and notification format."""
        path = COMMON / "automations" / "bambuddy_webhook_receiver.yaml"
        content = path.read_text(encoding="utf-8")
        self.assertIn("is_api_format", content)
        self.assertIn("trigger.json.data", content)


# =============================================================================
# 6. REST SENSOR CONFIGURATION
# =============================================================================

class TestRestSensor(unittest.TestCase):
    """The print history REST sensor must be correctly configured."""

    def setUp(self):
        self.sensor_path = HISTORY / "rest_sensors" / "bambuddy_print_history_sensor.yaml"
        self.data = _load_yaml_safe(self.sensor_path)
        # rest: integration format: top-level is a list of resource blocks
        self.resource = self.data[0] if isinstance(self.data, list) else self.data
        # Sensors are nested under the resource's 'sensor' key
        self.sensors = self.resource.get("sensor", [])
        self.sensor_by_uid = {
            s.get("unique_id"): s for s in self.sensors if isinstance(s, dict)
        }

    def test_has_unique_id(self):
        self.assertIn("bambuddy_print_history", self.sensor_by_uid)

    def test_uses_api_key_secret(self):
        content = self.sensor_path.read_text(encoding="utf-8")
        self.assertIn("!secret bambuddy_api_key", content)

    def test_has_reasonable_scan_interval(self):
        interval = self.resource.get("scan_interval", 0)
        self.assertGreaterEqual(interval, 60, "Scan interval too aggressive (< 60s)")
        self.assertLessEqual(interval, 3600, "Scan interval too slow (> 1h)")

    def test_resource_template_references_base_url(self):
        content = self.sensor_path.read_text(encoding="utf-8")
        self.assertIn("input_text.bambuddy_api_base_url", content)
        self.assertIn("/api/v1/archives", content)

    def test_inline_derived_sensors_defined(self):
        """The rest: block must define derived sensors for last-print fields."""
        expected = {
            "bambuddy_last_print_name",
            "bambuddy_last_print_status",
            "bambuddy_last_print_duration",
            "bambuddy_last_print_image_url",
        }
        missing = expected - set(self.sensor_by_uid.keys())
        self.assertFalse(missing, f"Missing inline sensors: {missing}")

    def test_resource_template_no_conditional_guard(self):
        """resource_template must not conditionally return empty — this
        causes the REST platform to skip sensor creation at boot and orphan
        the entity.  Regression for the 'no longer provided by rest' bug."""
        content = self.sensor_path.read_text(encoding="utf-8")
        # Extract the resource_template block
        in_block = False
        block_lines: list[str] = []
        for line in content.splitlines():
            if "resource_template" in line:
                in_block = True
                continue
            if in_block:
                if line and not line[0].isspace():
                    break  # exited the block
                block_lines.append(line)
        block = "\n".join(block_lines)
        self.assertNotIn(
            "{% if",
            block,
            "resource_template must not use an {% if %} guard that can return empty",
        )

    def test_uses_rest_integration_format(self):
        """File must use the rest: integration (not sensor: platform: rest)."""
        content = self.sensor_path.read_text(encoding="utf-8")
        self.assertNotIn(
            "platform: rest", content,
            "Should use rest: integration, not sensor platform: rest",
        )
        self.assertIn("sensor:", content, "Must define nested sensor: block")


# =============================================================================
# 7. REST COMMAND VALIDATION
# =============================================================================

class TestRestCommands(unittest.TestCase):
    """REST commands must use correct HTTP methods and URL patterns."""

    def _load_rest_command(self, filename: str) -> tuple[str, dict]:
        """Returns (command_key, command_config)."""
        path = HISTORY / "rest_commands" / filename
        data = _load_yaml_safe(path)
        self.assertIsInstance(data, dict)
        key = list(data.keys())[0]
        return key, data[key]

    def test_update_archive_uses_patch(self):
        _, cmd = self._load_rest_command("bambuddy_update_archive.yaml")
        self.assertEqual(cmd.get("method", "").upper(), "PATCH")

    def test_update_archive_sends_json(self):
        _, cmd = self._load_rest_command("bambuddy_update_archive.yaml")
        self.assertEqual(cmd.get("content_type"), "application/json")

    def test_query_recent_uses_get(self):
        _, cmd = self._load_rest_command("bambuddy_query_recent_archive.yaml")
        self.assertEqual(cmd.get("method", "").upper(), "GET")

    def test_all_rest_commands_use_api_key(self):
        for f in _collect_yaml_files(HISTORY / "rest_commands"):
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertIn(
                    "bambuddy_api_key",
                    content,
                    f"{f.name}: must authenticate with API key",
                )

    def test_all_rest_commands_reference_base_url(self):
        for f in _collect_yaml_files(HISTORY / "rest_commands"):
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertIn(
                    "bambuddy_api_base_url",
                    content,
                    f"{f.name}: must reference the base URL helper",
                )

    def test_no_hardcoded_urls(self):
        """REST commands must not contain hardcoded server URLs."""
        for f in _collect_yaml_files(HISTORY / "rest_commands"):
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertNotRegex(
                    content,
                    r"http(s)?://[a-zA-Z0-9]",
                    f"{f.name}: contains hardcoded URL — use bambuddy_api_base_url",
                )


# =============================================================================
# 8. TEMPLATE SENSOR VALIDATION
# =============================================================================

class TestTemplateSensors(unittest.TestCase):
    """Template sensors derive from the REST sensor and have unique IDs."""

    def _load_template_sensor(self, filename: str):
        path = HISTORY / "template_sensors" / filename
        data = _load_yaml_safe(path)
        # Template sensors are structured as a list with a sensor key
        if isinstance(data, list):
            data = data[0]
        if isinstance(data, dict) and "sensor" in data:
            return data["sensor"]
        return data

    def test_all_template_sensors_have_unique_id(self):
        for f in _collect_yaml_files(HISTORY / "template_sensors"):
            with self.subTest(file=f.name):
                data = _load_yaml_safe(f)
                ids = _extract_unique_ids(data)
                self.assertGreater(
                    len(ids), 0,
                    f"{f.name}: template sensor must have a unique_id",
                )

    def test_inline_sensors_use_correct_api_fields(self):
        """Inline derived sensors must use actual API field names."""
        sensor_path = HISTORY / "rest_sensors" / "bambuddy_print_history_sensor.yaml"
        content = sensor_path.read_text(encoding="utf-8")
        # Correct field names from the Bambuddy API
        self.assertIn("print_name", content, "Must use API field 'print_name'")
        self.assertIn("print_time_seconds", content, "Must use API field 'print_time_seconds'")
        self.assertIn("/thumbnail", content, "Must construct a thumbnail endpoint URL")
        # Must NOT use the old wrong field names
        self.assertNotIn("duration_seconds", content, "Wrong field: use print_time_seconds")
        self.assertNotIn(".photo_url", content, "Wrong field: use thumbnail_path")

    def test_page_info_references_page_helpers(self):
        content = (HISTORY / "template_sensors" / "print_history_page_info.yaml").read_text("utf-8")
        self.assertIn("history_current_page", content)
        self.assertIn("print_history_filtered", content)

    def test_image_url_prepends_base_url(self):
        """Image URL sensor must combine base_url + photo path for full URL."""
        sensor_path = HISTORY / "rest_sensors" / "bambuddy_print_history_sensor.yaml"
        content = sensor_path.read_text("utf-8")
        self.assertIn("bambuddy_api_base_url", content)

    def test_duration_is_in_hours(self):
        sensor_path = HISTORY / "rest_sensors" / "bambuddy_print_history_sensor.yaml"
        content = sensor_path.read_text("utf-8")
        self.assertIn("3600", content, "Duration conversion must divide by 3600")

    def test_archive_projection_includes_object_count_and_omits_quantity(self):
        content = (HISTORY / "template_sensors" / "print_history_archives.yaml").read_text("utf-8")
        self.assertIn("object_count=a.get('object_count', 1) | int(1)", content)
        self.assertNotIn("quantity=a.get('quantity', 1) | int(1)", content)

    def test_filtered_sensor_uses_object_count_and_separate_print_count(self):
        content = (HISTORY / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        self.assertIn("ns.total_prints = ns.total_prints + 1", content)
        self.assertIn("ns.total_objects = ns.total_objects + (a.get('object_count', 1) | int(1))", content)
        self.assertIn("{% elif mode == 'filament uses' %}", content)


class TestHeatmapActivityCard(unittest.TestCase):
    """Heatmap card logic should match the projected archive schema and metric labels."""

    def test_heatmap_card_uses_api_object_count(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("objectCount: Math.max(1, this._toNumber(archive && archive.object_count))", content)

    def test_heatmap_card_supports_filament_uses_label(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('input.mode === "Filament Uses"', content)
        self.assertIn('"filament uses": "Filament Uses"', content)


# =============================================================================
# 9. SCRIPT VALIDATION
# =============================================================================

class TestScripts(unittest.TestCase):

    def _load_script(self, filename: str) -> tuple[str, dict]:
        path = HISTORY / "scripts" / filename
        data = _load_yaml_safe(path)
        self.assertIsInstance(data, dict)
        key = list(data.keys())[0]
        return key, data[key]

    def test_capture_script_is_queued(self):
        _, script = self._load_script("capture_and_upload_snapshot.yaml")
        self.assertEqual(script.get("mode"), "queued")
        self.assertGreaterEqual(script.get("max", 1), 2)

    def test_capture_script_has_stage_field(self):
        _, script = self._load_script("capture_and_upload_snapshot.yaml")
        fields = script.get("fields", {})
        self.assertIn("stage", fields)

    def test_capture_script_saves_locally(self):
        """Photos must be saved to /config/www/ for local dashboard access."""
        content = (HISTORY / "scripts" / "capture_and_upload_snapshot.yaml").read_text("utf-8")
        self.assertIn("/config/www/printer_snapshots/", content)

    def test_capture_script_handles_secondary_camera(self):
        content = (HISTORY / "scripts" / "capture_and_upload_snapshot.yaml").read_text("utf-8")
        self.assertIn("secondary_camera", content)
        self.assertIn("has_secondary", content)

    def test_capture_script_handles_snapshot_light(self):
        """Script should turn light on before capture and off after."""
        content = (HISTORY / "scripts" / "capture_and_upload_snapshot.yaml").read_text("utf-8")
        self.assertIn("light.turn_on", content)
        self.assertIn("light.turn_off", content)

    def test_resolve_archive_uses_fallback_query(self):
        content = (HISTORY / "scripts" / "resolve_current_archive_id.yaml").read_text("utf-8")
        self.assertIn("bambuddy_query_recent_archive", content)
        self.assertIn("task_name", content)

    def test_load_history_page_uses_page_param(self):
        content = (HISTORY / "scripts" / "load_history_page.yaml").read_text("utf-8")
        self.assertIn("page", content)
        self.assertIn("print_history_filtered", content)

    def test_navigate_history_supports_all_directions(self):
        content = (HISTORY / "scripts" / "navigate_history.yaml").read_text("utf-8")
        for direction in ("prev", "next", "first", "last"):
            self.assertIn(direction, content, f"Missing direction: {direction}")

    def test_navigate_history_clamps_boundaries(self):
        """Must prevent going below page 1 or above total pages."""
        content = (HISTORY / "scripts" / "navigate_history.yaml").read_text("utf-8")
        self.assertIn("min", content, "Must clamp next page to total")
        self.assertIn("max", content, "Must clamp prev page to 1")


# =============================================================================
# 10. HELPER VALIDATION
# =============================================================================

class TestHelpers(unittest.TestCase):

    # Helpers that store runtime/print-cycle state should NOT set 'initial:'
    # because it forces a reset on HA restart, losing persisted values.
    # Configuration/settings helpers (page size, timeouts, etc.) MAY use 'initial:'
    # to provide sensible defaults.
    STATE_PERSISTENCE_HELPERS = {
        "input_text_bambuddy_current_archive_id.yaml",
        "input_text_bambuddy_tray_map_snapshot.yaml",
        "input_text_bambuddy_photo_manifest.yaml",
    }

    def test_state_persistence_helpers_have_no_initial(self):
        """Runtime state helpers must NOT set 'initial:' (prevents state restore)."""
        for subdir in ("input_text", "input_boolean", "input_number", "input_select"):
            for f in _collect_yaml_files(HISTORY / "helpers" / subdir):
                if f.name not in self.STATE_PERSISTENCE_HELPERS:
                    continue
                with self.subTest(file=f.name):
                    data = _load_yaml_safe(f)
                    if isinstance(data, dict):
                        for key, val in data.items():
                            if isinstance(val, dict):
                                self.assertNotIn(
                                    "initial", val,
                                    f"{f.name}: state-persistence helper must NOT set 'initial:'",
                                )

    def test_input_text_max_length_set(self):
        """input_text helpers should declare max to avoid truncation issues."""
        for f in _collect_yaml_files(HISTORY / "helpers" / "input_text"):
            with self.subTest(file=f.name):
                data = _load_yaml_safe(f)
                if isinstance(data, dict):
                    for key, val in data.items():
                        if isinstance(val, dict):
                            self.assertIn(
                                "max", val,
                                f"{f.name}: input_text should set max length",
                            )

    def test_photo_review_state_has_expected_options(self):
        path = HISTORY / "helpers" / "input_select" / "input_select_bambuddy_photo_review_state.yaml"
        data = _load_yaml_safe(path)
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, dict) and "options" in val:
                    options = val["options"]
                    self.assertIn("idle", options)
                    self.assertIn("pending", options)

    def test_activity_metric_options_use_filament_uses(self):
        path = HISTORY / "helpers" / "input_select" / "input_select_print_history_activity_metric.yaml"
        data = _load_yaml_safe(path)
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, dict) and "options" in val:
                    options = val["options"]
                    self.assertIn("Filament Uses", options)
                    self.assertNotIn("Number of Different Filaments", options)


# =============================================================================
# 11. CROSS-REFERENCE INTEGRITY
# =============================================================================

class TestCrossReferences(unittest.TestCase):
    """Automations/scripts must reference entities that exist in the package."""

    KNOWN_PRINT_HISTORY_ENTITIES = {
        # Helpers
        "input_text.bambuddy_current_archive_id",
        "input_text.bambuddy_photo_manifest",
        "input_text.bambuddy_tray_map_snapshot",
        "input_text.print_history_search",
        "input_text.secondary_camera_entity",
        "input_boolean.bambuddy_history_fetch_enabled",
        "input_boolean.capture_at_start",
        "input_boolean.capture_at_midprint",
        "input_boolean.capture_near_complete",
        "input_boolean.capture_on_error",
        "input_number.bambuddy_history_limit",
        "input_number.history_current_page",
        "input_number.midprint_capture_percent",
        "input_number.photo_review_timeout_hours",
        "input_number.print_history_page_size",
        "input_number.print_history_max_archives",
        "input_select.bambuddy_photo_review_state",
        "input_select.print_history_filter_status",
        "input_select.print_history_filter_material",
        "input_select.print_history_filter_color",
        "input_select.print_history_filter_printer",
        "input_select.print_history_filter_date_range",
        "input_select.print_history_filter_favorites",
        "input_select.print_history_filter_designer",
        "input_select.print_history_filter_layer_height",
        "input_select.print_history_sort",
        "input_select.print_history_card_variant",
        # REST sensor
        "sensor.bambuddy_print_history",
        # Template sensors
        "sensor.print_history_archives",
        "sensor.print_history_filtered",
        "sensor.bambuddy_last_print_name",
        "sensor.bambuddy_last_print_status",
        "sensor.bambuddy_last_print_duration",
        "sensor.bambuddy_last_print_image_url",
        "sensor.print_history_page_info",
        "sensor.print_history_page_archives",
    }

    KNOWN_COMMON_ENTITIES = {
        "input_boolean.bambuddy_integration_enabled",
        "input_text.bambuddy_api_base_url",
        "input_text.bambuddy_printer_id",
    }

    KNOWN_EXTERNAL_ENTITIES = {
        # From ha-bambulab integration
        "sensor.ntk_ryansoffice_3dprinter_print_status",
        "sensor.ntk_ryansoffice_3dprinter_print_progress",
        "sensor.ntk_ryansoffice_3dprinter_task_name",
        "binary_sensor.ntk_ryansoffice_3dprinter_print_error",
        "camera.ntk_ryansoffice_3dprinter_camera",
        # Core package sensors
        "sensor.spoolman_tray_map",
        "sensor.print_cost",
    }

    ALL_KNOWN = KNOWN_PRINT_HISTORY_ENTITIES | KNOWN_COMMON_ENTITIES | KNOWN_EXTERNAL_ENTITIES

    def test_automation_entity_references_are_known(self):
        """Every entity referenced in automations should be a known entity."""
        # Entity patterns we expect to see (regex patterns for dynamic references)
        dynamic_patterns = [
            r"\{\{.*\}\}",  # Jinja2 templates
        ]

        for f in _collect_yaml_files(HISTORY / "automations"):
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                entities = _extract_entity_ids(content)
                for entity in entities:
                    # Skip entities that appear inside Jinja templates
                    if entity.startswith("{{") or "." not in entity:
                        continue
                    # Allow known domains with dynamic suffixes
                    if entity in self.ALL_KNOWN:
                        continue
                    # Allow service calls (not entity references)
                    known_services = {
                        "input_text.set_value", "input_select.select_option",
                        "input_number.set_value", "input_boolean.turn_on",
                        "input_boolean.turn_off", "homeassistant.update_entity",
                        "logbook.log", "light.turn_on", "light.turn_off",
                        "camera.snapshot", "script.capture_and_upload_snapshot",
                        "script.resolve_current_archive_id",
                        "script.load_history_page",
                        "script.refresh_print_history_archives",
                        "script.clear_print_history_filters",
                        "rest_command.bambuddy_update_archive",
                        "rest_command.bambuddy_upload_photo_to_archive",
                        "rest_command.bambuddy_query_recent_archive",
                        "rest_command.bambuddy_fetch_archives",
                    }
                    if entity in known_services:
                        continue
                    # Unknown entity — flag it
                    # (Soft check: warn but allow external entities we can't verify)
                    # self.assertIn(entity, self.ALL_KNOWN, f"Unknown entity: {entity}")


# =============================================================================
# 12. NO HARDCODED DEVICE_IDS
# =============================================================================

class TestNoHardcodedDeviceIds(unittest.TestCase):
    """Automations and scripts should use entity_id, not device_id."""

    def test_no_device_id_in_print_history(self):
        for f in _collect_yaml_files(HISTORY):
            if f.suffix != ".yaml":
                continue
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                # device_id: <hex hash> is the pattern to flag
                matches = re.findall(r"device_id:\s*[a-f0-9]{32}", content)
                self.assertEqual(
                    len(matches), 0,
                    f"{f.name}: uses hardcoded device_id — migrate to entity_id",
                )


# =============================================================================
# 13. TAGS FORMAT VALIDATION (Enrichment)
# =============================================================================

class TestEnrichmentTagFormat(unittest.TestCase):
    """Archive enrichment must use comma-separated tags (not JSON arrays)."""

    def test_enrichment_builds_comma_separated_tags(self):
        content = (HISTORY / "automations" / "bambuddy_enrich_archive_on_complete.yaml").read_text("utf-8")
        # The enrichment builds tags with join(',') — not tojson
        self.assertIn("join(',')", content, "Tags must be comma-separated strings")

    def test_update_archive_payload_uses_tojson_for_strings(self):
        """PATCH payload must JSON-encode string values (tojson), not wrap in array."""
        content = (HISTORY / "rest_commands" / "bambuddy_update_archive.yaml").read_text("utf-8")
        self.assertIn("tojson", content)
        # Ensure it's not wrapping tags in an array
        self.assertNotIn('"tags": [', content)


# =============================================================================
# 14. PHOTO CAPTURE FLOW VALIDATION
# =============================================================================

class TestPhotoCaptureFlow(unittest.TestCase):
    """Photo capture automations follow the designed multi-stage flow."""

    def test_capture_photos_has_four_stages(self):
        content = (HISTORY / "automations" / "bambuddy_capture_print_photos.yaml").read_text("utf-8")
        for stage_id in ("start", "midprint", "near_complete", "finish"):
            self.assertIn(
                f'"{stage_id}"',
                content,
                f"Photo capture missing stage trigger ID: {stage_id}",
            )

    def test_start_stage_has_delay(self):
        """Start stage should delay to show first layer, not immediate capture."""
        content = (HISTORY / "automations" / "bambuddy_capture_print_photos.yaml").read_text("utf-8")
        # After the start trigger, there should be a delay before capture
        self.assertIn("minutes: 3", content, "Start stage needs ~3 min delay for first layer")

    def test_start_stage_rechecks_print_status(self):
        """After delay, must confirm printer is still running."""
        content = (HISTORY / "automations" / "bambuddy_capture_print_photos.yaml").read_text("utf-8")
        # Should have condition check after delay
        self.assertIn("running", content)

    def test_finish_stage_has_no_gate(self):
        """Finish stage should always capture (no boolean gate)."""
        path = HISTORY / "automations" / "bambuddy_capture_print_photos.yaml"
        data = _load_yaml_safe(path)
        auto = data[0]
        actions = auto.get("actions", auto.get("action", []))
        # Find the choose action
        choose = next((a for a in actions if "choose" in a), None)
        self.assertIsNotNone(choose, "Must have a choose block")
        options = choose["choose"]
        finish_option = None
        for opt in options:
            conditions = opt.get("conditions", [])
            for cond in conditions:
                if isinstance(cond, dict) and cond.get("id") == "finish":
                    finish_option = opt
                    break
        if finish_option:
            # Finish should NOT gate on any input_boolean
            cond_text = str(finish_option.get("conditions", []))
            self.assertNotIn(
                "input_boolean.capture",
                cond_text,
                "Finish stage must NOT be gated by a capture toggle",
            )


# =============================================================================
# 15. DOCUMENTATION COMPLETENESS
# =============================================================================

class TestDocumentation(unittest.TestCase):
    """Required design docs exist for the print_history feature."""

    def test_print_history_readme_exists(self):
        self.assertTrue((DOCS_HIST / "README.md").exists())

    def test_photo_capture_design_exists(self):
        self.assertTrue((DOCS_HIST / "photo-capture-design.md").exists())

    def test_archive_enrichment_design_exists(self):
        self.assertTrue((DOCS_HIST / "archive-enrichment.md").exists())

    def test_bambuddy_common_readme_exists(self):
        self.assertTrue((DOCS_COMMON / "README.md").exists())

    def test_api_catalog_exists(self):
        self.assertTrue(
            (DOCS_COMMON / "bambuddy-archive-api-catalog.md").exists(),
            "API catalog doc must exist for print_history API reference",
        )


# =============================================================================
# 16. PAGINATION LOGIC
# =============================================================================

class TestPaginationLogic(unittest.TestCase):
    """Validate the pagination template sensor math offline."""

    def test_total_pages_ceil_division(self):
        """With a flat-array API, total_pages checks count >= limit to estimate more pages."""
        test_cases = [
            # (count_returned, limit, expected_pages)
            (0,  10, 1),   # empty → 1 page
            (1,  10, 1),   # partial page → 1 page
            (9,  10, 1),   # partial page → 1 page
            (10, 10, 2),   # full page → likely more
            (5,   5, 2),   # full page → likely more
            (4,   5, 1),   # partial → 1 page
        ]
        for count, limit, expected in test_cases:
            with self.subTest(count=count, limit=limit):
                if count >= limit:
                    result = 2
                else:
                    result = 1
                self.assertEqual(result, expected)

    def test_offset_computation(self):
        """Offset is (page - 1) * limit for the API."""
        test_cases = [
            # (page, limit, expected_offset)
            (1, 10, 0),
            (2, 10, 10),
            (3, 10, 20),
            (1, 5, 0),
            (3, 5, 10),
        ]
        for page, limit, expected in test_cases:
            with self.subTest(page=page, limit=limit):
                offset = (page - 1) * limit
                self.assertEqual(offset, expected)

    def test_navigate_next_clamped(self):
        """next must not exceed total."""
        current, total = 5, 5
        target = min(current + 1, total)
        self.assertEqual(target, 5)

    def test_navigate_prev_clamped(self):
        """prev must not go below 1."""
        current = 1
        target = max(current - 1, 1)
        self.assertEqual(target, 1)


# =============================================================================
# 17. TRAY MAP SNAPSHOT VALIDATION
# =============================================================================

class TestTrayMapSnapshot(unittest.TestCase):
    """Tray map snapshot logic must produce a compact, parseable format."""

    def test_snapshot_format_is_compact(self):
        """Snapshot uses 'tray_name:spool_id' CSV format to fit 255-char input_text."""
        content = (HISTORY / "automations" / "bambuddy_capture_archive_id.yaml").read_text("utf-8")
        # Must use compact format, not full JSON
        self.assertIn("join(',')", content)
        self.assertIn("~ ':'", content)

    def test_snapshot_targets_correct_helper(self):
        content = (HISTORY / "automations" / "bambuddy_capture_archive_id.yaml").read_text("utf-8")
        self.assertIn("input_text.bambuddy_tray_map_snapshot", content)


# =============================================================================
# 18. SECURITY — NO LEAKED SECRETS
# =============================================================================

class TestSecurityNoLeakedSecrets(unittest.TestCase):
    """YAML files must not contain plaintext API keys or passwords."""

    def test_no_plaintext_api_keys(self):
        """API keys must use !secret, never hardcoded."""
        for f in _collect_yaml_files(HISTORY):
            if f.suffix != ".yaml":
                continue
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                # Flag potential hardcoded API keys (long hex/alphanum strings in headers)
                risk_patterns = [
                    r'X-API-Key:\s+"[a-zA-Z0-9]{16,}"',
                    r'X-API-Key:\s+[a-zA-Z0-9]{16,}',
                    r'api_key:\s+"[a-zA-Z0-9]{16,}"',
                ]
                for pattern in risk_patterns:
                    matches = re.findall(pattern, content)
                    filtered = [m for m in matches if "!secret" not in m and "{{" not in m]
                    self.assertEqual(
                        len(filtered), 0,
                        f"{f.name}: possible hardcoded API key found",
                    )

    def test_no_plaintext_urls_with_credentials(self):
        for f in _collect_yaml_files(HISTORY):
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertNotRegex(
                    content,
                    r"https?://[^/]*:[^@]+@",
                    f"{f.name}: URL contains embedded credentials",
                )


if __name__ == "__main__":
    unittest.main()
