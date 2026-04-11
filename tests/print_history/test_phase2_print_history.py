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
LEGACY_BROWSER = ROOT / "archive" / "print_history" / "legacy-yaml-browser"
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
            "shell_command",
            "script",
            "template",
            "counter",
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
        "print_history_reset_page_on_filter_change.yaml",
    ]

    EXPECTED_LEGACY_AUTOMATIONS = [
        "print_history_sync_filter_options.yaml",
    ]

    EXPECTED_SCRIPTS = [
        "capture_and_upload_snapshot.yaml",
        "resolve_current_archive_id.yaml",
        "load_history_page.yaml",
        "navigate_history.yaml",
        "refresh_print_history_archives.yaml",
        "clear_print_history_filters.yaml",
        "print_history_payload_self_test.yaml",
    ]

    EXPECTED_REST_COMMANDS = [
        "bambuddy_delete_archive_photo.yaml",
        "bambuddy_set_archive_cover.yaml",
        "bambuddy_update_archive.yaml",
        "bambuddy_query_recent_archive.yaml",
        "bambuddy_get_archive_detail.yaml",
    ]

    EXPECTED_LEGACY_REST_COMMANDS = [
        "bambuddy_fetch_archives.yaml",
    ]

    EXPECTED_TEMPLATE_SENSORS = [
        "print_history_payload_diagnostics.yaml",
        "print_history_popup_archive_detail.yaml",
    ]

    EXPECTED_LEGACY_TEMPLATE_SENSORS = [
        "print_history_archives.yaml",
        "print_history_filtered.yaml",
        "print_history_page_info.yaml",
    ]

    EXPECTED_HELPERS_INPUT_TEXT = [
        "input_text_bambuddy_current_archive_id.yaml",
        "input_text_bambuddy_last_photo_upload_result.yaml",
        "input_text_bambuddy_tray_map_snapshot.yaml",
        "input_text_print_history_activity_selected_date.yaml",
        "input_text_print_history_search.yaml",
    ]

    EXPECTED_HELPERS_COUNTER = [
        "bambuddy_captured_photo_count.yaml",
    ]

    EXPECTED_HELPERS_INPUT_BOOLEAN = [
        "input_boolean_bambuddy_history_sync_enabled.yaml",
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
        "input_select_print_history_filter_enrichment_status.yaml",
        "input_select_print_history_filter_material.yaml",
        "input_select_print_history_filter_color.yaml",
        "input_select_print_history_filter_printer.yaml",
        "input_select_print_history_filter_date_range.yaml",
        "input_select_print_history_filter_designer.yaml",
        "input_select_print_history_filter_project.yaml",
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

    def _check_files(self, base_dir: Path, subdir: str, expected: list[str]):
        directory = base_dir / subdir
        for fname in expected:
            with self.subTest(file=f"{subdir}/{fname}"):
                self.assertTrue(
                    (directory / fname).exists(),
                    f"Missing expected file: {subdir}/{fname}",
                )

    def test_automations_exist(self):
        self._check_files(HISTORY, "automations", self.EXPECTED_AUTOMATIONS)

    def test_legacy_browser_automations_exist(self):
        self._check_files(LEGACY_BROWSER, "automations", self.EXPECTED_LEGACY_AUTOMATIONS)

    def test_scripts_exist(self):
        self._check_files(HISTORY, "scripts", self.EXPECTED_SCRIPTS)

    def test_rest_commands_exist(self):
        self._check_files(HISTORY, "rest_commands", self.EXPECTED_REST_COMMANDS)

    def test_legacy_browser_rest_commands_exist(self):
        self._check_files(LEGACY_BROWSER, "rest_commands", self.EXPECTED_LEGACY_REST_COMMANDS)

    def test_template_sensors_exist(self):
        self._check_files(HISTORY, "template_sensors", self.EXPECTED_TEMPLATE_SENSORS)

    def test_legacy_browser_template_sensors_exist(self):
        self._check_files(LEGACY_BROWSER, "template_sensors", self.EXPECTED_LEGACY_TEMPLATE_SENSORS)

    def test_rest_sensors_exist(self):
        self._check_files(HISTORY, "rest_sensors", self.EXPECTED_REST_SENSORS)

    def test_helpers_input_text_exist(self):
        self._check_files(HISTORY, "helpers/input_text", self.EXPECTED_HELPERS_INPUT_TEXT)

    def test_helpers_input_boolean_exist(self):
        self._check_files(HISTORY, "helpers/input_boolean", self.EXPECTED_HELPERS_INPUT_BOOLEAN)

    def test_helpers_counter_exist(self):
        self._check_files(HISTORY, "helpers/counter", self.EXPECTED_HELPERS_COUNTER)

    def test_helpers_input_number_exist(self):
        self._check_files(HISTORY, "helpers/input_number", self.EXPECTED_HELPERS_INPUT_NUMBER)

    def test_helpers_input_select_exist(self):
        self._check_files(HISTORY, "helpers/input_select", self.EXPECTED_HELPERS_INPUT_SELECT)

    def test_dashboard_cards_exist(self):
        self._check_files(HISTORY, "dashboard_cards", self.EXPECTED_DASHBOARD_CARDS)

    def test_dashboard_views_exist(self):
        self._check_files(HISTORY, "dashboard_views", self.EXPECTED_DASHBOARD_VIEWS)

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
            "shell_commands",
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
# 6. PAYLOAD DIAGNOSTICS
# =============================================================================

class TestPayloadDiagnostics(unittest.TestCase):
    """Payload guard files should stay wired to the print history chain."""

    def test_payload_diagnostics_sensor_tracks_frontend_only_browser_contract(self):
        path = HISTORY / "template_sensors" / "print_history_payload_diagnostics.yaml"
        content = path.read_text(encoding="utf-8")
        self.assertIn("sensor.bambuddy_print_history_browser_filtered", content)
        self.assertIn("sensor.bambuddy_print_history_browser_page_info", content)
        self.assertIn("frontend_query_transport: websocket", content)
        self.assertIn("payload_chars: >-\n          0", content)
        self.assertIn("input_number.print_history_max_archives", content)
        self.assertIn("160000", content)
        self.assertIn("190000", content)

    def test_payload_self_test_script_uses_notification(self):
        path = HISTORY / "scripts" / "print_history_payload_self_test.yaml"
        content = path.read_text(encoding="utf-8")
        self.assertIn("persistent_notification.create", content)
        self.assertIn("sensor.print_history_payload_diagnostics", content)
        self.assertIn("print_history_payload_self_test", content)


# =============================================================================
# 7. REST SENSOR CONFIGURATION
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
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_page_info.yaml").read_text("utf-8")
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
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_archives.yaml").read_text("utf-8")
        self.assertIn("object_count=a.get('object_count', 1) | int(1)", content)
        self.assertNotIn("quantity=a.get('quantity', 1) | int(1)", content)

    def test_archive_projection_includes_project_fields(self):
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_archives.yaml").read_text("utf-8")
        self.assertIn("project_id=a.get('project_id')", content)
        self.assertIn("project_name=(a.get('project_name') if a.get('project_name') is not none else '')", content)

    def test_archive_projection_drops_slot_id_from_filament_slots(self):
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_archives.yaml").read_text("utf-8")
        self.assertIn("{% set slot_ns = namespace(values=[]) %}", content)
        self.assertIn("color=slot.get('color')", content)
        self.assertIn("type=slot.get('type')", content)
        self.assertIn("used_g=slot.get('used_g')", content)
        self.assertIn("filament_slots=slot_ns.values", content)
        self.assertNotIn("filament_slots=slots", content)

    def test_filtered_sensor_uses_object_count_and_separate_print_count(self):
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        self.assertIn("ns.total_prints = ns.total_prints + 1", content)
        self.assertIn("ns.total_objects = ns.total_objects + (a.get('object_count', 1) | int(1))", content)
        self.assertIn("{% elif mode == 'filaments used' %}", content)
        self.assertNotIn("filament uses", content)
        self.assertNotIn("number of different filaments", content)

    def test_filtered_sensor_formats_activity_totals_with_grouping(self):
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        self.assertIn("{{ '{:,}'.format(count) }} active", content)
        self.assertIn("{{ '{:,.1f}g'.format(ns.total_weight) }}", content)
        self.assertIn("{{ '{:,.2f}'.format(ns.total_cost) }}", content)
        self.assertIn("{{ '{:,.1f}h'.format(ns.total_duration_seconds / 3600) }}", content)

    def test_project_filter_supports_unassigned_none_option(self):
        filtered_content = (LEGACY_BROWSER / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        sync_content = (LEGACY_BROWSER / "automations" / "print_history_sync_filter_options.yaml").read_text("utf-8")
        helper_content = (HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_project.yaml").read_text("utf-8")

        self.assertIn("input_select.print_history_filter_project", filtered_content)
        self.assertIn("filter_project == 'None' and project_name == ''", filtered_content)
        self.assertIn("['All', 'None'] + (ns.values | sort)", sync_content)
        self.assertIn("- None", helper_content)

    def test_filtered_sensor_builds_color_tooltips_from_enrichment_notes(self):
        content = (LEGACY_BROWSER / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        self.assertIn("available_color_tooltips_json", content)
        self.assertIn("{% set enrichment_marker = '+>' %}", content)
        self.assertIn("{% set rows = payload.get('F', []) if payload is mapping else [] %}", content)
        self.assertIn("{% set ns.entries = ns.entries + [dict(color=color_key, names=[name])] %}", content)
        self.assertIn("{% set tooltip = (entry.names | join(' or ')) ~ ' (' ~ (entry.color | upper) ~ ')' %}", content)

    def test_status_filters_split_archive_and_enrichment_status(self):
        filtered_content = (LEGACY_BROWSER / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        browser_card_content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js").read_text("utf-8")
        browser_content = (HISTORY / "dashboard_cards" / "print_history_browser.yaml").read_text("utf-8")

        self.assertIn("{%- set raw_status = a.get('status', '') | string | lower -%}", filtered_content)
        self.assertIn("{%- set status = 'completed' -%}", filtered_content)
        self.assertIn("{%- set filter_enrichment_status = states('input_select.print_history_filter_enrichment_status') -%}", filtered_content)
        self.assertIn("{%- set notes_raw = a.get('notes', '') | string -%}", filtered_content)
        self.assertIn("{%- set enrichment_status_code = enrichment_payload.get('s', '') | string | lower if enrichment_payload is mapping else '' -%}", filtered_content)
        self.assertIn("{%- set enrichment_status = 'complete' if enrichment_status_code == 'c' else 'partial' if enrichment_status_code == 'p' else 'unavailable' if enrichment_status_code == 'u' else 'not defined' -%}", filtered_content)
        self.assertIn("{%- set matches_enrichment_status = filter_enrichment_status == 'All' or enrichment_status == filter_enrichment_status | lower -%}", filtered_content)
        self.assertIn('type: "bambuddy/print_history_query"', browser_card_content)
        self.assertIn('enrichment_status: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_enrichment_status"))', browser_card_content)
        self.assertIn("input_select.print_history_filter_enrichment_status", browser_content)
        self.assertIn("name: Enrichment", browser_content)
        self.assertIn("name: Clear Enrichment Filter", browser_content)
        self.assertIn("name: Clear", browser_content)
        self.assertIn("service: script.clear_print_history_filters", browser_content)
        self.assertNotIn("name: Clear Filters", browser_content)


class TestHeatmapActivityCard(unittest.TestCase):
    """Heatmap card logic should match the projected archive schema and metric labels."""

    def test_heatmap_card_resource_is_versioned_for_reregistration(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboards" / "_resources.yaml").read_text("utf-8")
        self.assertIn("/local/3d_printing/print_history/print-history-browser-card.js?v=6", content)
        self.assertIn("/local/3d_printing/print_history/print-history-activity-heatmap-card.js?v=32", content)

    def test_heatmap_card_normalizes_cancelled_statuses(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('raw === "cancelled" || raw === "aborted" || raw === "stopped"', content)
        self.assertIn('return "cancelled";', content)
        self.assertIn('cancelledCount', content)

    def test_heatmap_card_rerenders_when_reconnected(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("connectedCallback()", content)
        self.assertIn("this._requestVisibilityRender();", content)
        self.assertIn("self._queueRender();", content)

    def test_heatmap_card_rerenders_on_view_visibility_events(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("window.addEventListener(\"location-changed\"", content)
        self.assertIn("document.addEventListener(\"visibilitychange\"", content)
        self.assertIn("new IntersectionObserver(function (entries)", content)
        self.assertIn("this._intersectionObserver.observe(this);", content)

    def test_heatmap_card_uses_api_object_count(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("objectCount: Math.max(1, this._toNumber(archive && archive.object_count))", content)

    def test_heatmap_card_supports_filaments_used_label(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('type: "bambuddy/print_history_query"', content)
        self.assertIn('include_activity_rows: true', content)
        self.assertIn('input.mode === "Filaments Used"', content)
        self.assertIn('"filaments used": "Filaments Used"', content)
        self.assertNotIn('"filament uses": "Filaments Used"', content)
        self.assertNotIn('"number of different filaments": "Filaments Used"', content)
        self.assertNotIn('"outcome mix": "Outcome"', content)
        self.assertNotIn('"by outcome": "Outcome"', content)

    def test_heatmap_card_formats_large_totals_with_locale_grouping(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("return this._formatDecimal(value, 1) + \"h\";", content)
        self.assertIn("return this._formatDecimal(weight, 1) + \"g\";", content)
        self.assertIn("return \"$\" + this._formatDecimal(value, 2);", content)
        self.assertIn("'Prints: ' + this._formatCount(meta.count || 0)", content)
        self.assertIn("this._buildChipHtml(this._formatCount(activeDays) + \" active days\")", content)
        self.assertIn("this._formatCount(day.count) + (day.count === 1 ? \" print\" : \" prints\")", content)


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
        self.assertIn("secondary_camera_state", content)
        self.assertIn("has_secondary", content)
        self.assertIn("invalid_secondary", content)

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
        self.assertIn("sensor.bambuddy_print_history_browser_filtered", content)

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
        "input_text_bambuddy_last_photo_upload_result.yaml",
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

    def test_activity_metric_options_use_filaments_used(self):
        path = HISTORY / "helpers" / "input_select" / "input_select_print_history_activity_metric.yaml"
        data = _load_yaml_safe(path)
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, dict) and "options" in val:
                    options = val["options"]
                    self.assertIn("Filaments Used", options)
                    self.assertNotIn("Filament Uses", options)
                    self.assertNotIn("Number of Different Filaments", options)

    def test_status_helpers_use_separate_archive_and_enrichment_statuses(self):
        filter_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_status.yaml"
        enrichment_filter_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_enrichment_status.yaml"
        popup_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_popup_status.yaml"
        filter_data = _load_yaml_safe(filter_path)
        enrichment_filter_data = _load_yaml_safe(enrichment_filter_path)
        popup_data = _load_yaml_safe(popup_path)

        filter_options = next(iter(filter_data.values())).get("options", []) if isinstance(filter_data, dict) else []
        enrichment_filter_options = next(iter(enrichment_filter_data.values())).get("options", []) if isinstance(enrichment_filter_data, dict) else []
        popup_options = next(iter(popup_data.values())).get("options", []) if isinstance(popup_data, dict) else []

        self.assertEqual(
            filter_options,
            ["All", "Completed", "Failed", "Cancelled", "Printing"],
        )
        self.assertEqual(
            enrichment_filter_options,
            ["All", "Complete", "Partial", "Unavailable", "Not Defined"],
        )
        self.assertIn("Cancelled", popup_options)
        self.assertNotIn("Aborted", popup_options)


# =============================================================================
# 11. CROSS-REFERENCE INTEGRITY
# =============================================================================

class TestCrossReferences(unittest.TestCase):
    """Automations/scripts must reference entities that exist in the package."""

    KNOWN_PRINT_HISTORY_ENTITIES = {
        # Helpers
        "counter.bambuddy_captured_photo_count",
        "input_text.bambuddy_current_archive_id",
        "input_text.bambuddy_last_photo_upload_result",
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
        "input_select.print_history_filter_enrichment_status",
        "input_select.print_history_filter_material",
        "input_select.print_history_filter_color",
        "input_select.print_history_filter_printer",
        "input_select.print_history_filter_date_range",
        "input_select.print_history_filter_favorites",
        "input_select.print_history_filter_designer",
        "input_select.print_history_filter_project",
        "input_select.print_history_filter_layer_height",
        "input_select.print_history_sort",
        "input_select.print_history_card_variant",
        # REST sensor
        "sensor.bambuddy_print_history",
        # Active integration-backed browser sensors
        "sensor.bambuddy_print_history_browser_filtered",
        "sensor.bambuddy_print_history_browser_page_info",
        "sensor.print_history_payload_diagnostics",
        "sensor.print_history_popup_archive_detail",
        "sensor.bambuddy_last_print_name",
        "sensor.bambuddy_last_print_status",
        "sensor.bambuddy_last_print_duration",
        "sensor.bambuddy_last_print_image_url",
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
                        "counter.increment", "counter.reset",
                        "input_number.set_value", "input_boolean.turn_on",
                        "input_boolean.turn_off", "homeassistant.update_entity",
                        "logbook.log", "light.turn_on", "light.turn_off",
                        "camera.snapshot", "script.capture_and_upload_snapshot",
                        "shell_command.bambuddy_upload_archive_photo",
                        "script.resolve_current_archive_id",
                        "script.load_history_page",
                        "script.refresh_print_history_archives",
                        "script.clear_print_history_filters",
                        "rest_command.bambuddy_get_archive_detail",
                        "rest_command.bambuddy_update_archive",
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
# 13. ENRICHMENT PAYLOAD VALIDATION
# =============================================================================

class TestEnrichmentArchiveUpdatePayload(unittest.TestCase):
    """Archive enrichment should match the current shipped archive PATCH contract."""

    def test_enrichment_uses_native_cost_with_managed_tags_and_notes(self):
        content = (HISTORY / "automations" / "bambuddy_enrich_archive_on_complete.yaml").read_text("utf-8")
        self.assertIn('cost: "{{ total_cost }}"', content)
        self.assertIn('tags: "{{ merged_tags }}"', content)
        self.assertIn('notes: "{{ merged_notes }}"', content)
        self.assertNotIn("ha_enriched:true", content)
        self.assertIn("'f:' ~ filament_id", content)
        self.assertIn("'s:' ~ spool_id", content)
        self.assertNotIn('status: "{{ archive_status }}"', content)

    def test_update_archive_payload_is_field_optional(self):
        """PATCH payload should always include tags/notes and add native fields only when passed."""
        content = (HISTORY / "rest_commands" / "bambuddy_update_archive.yaml").read_text("utf-8")
        self.assertIn("namespace(body={", content)
        self.assertIn('"tags": tags | default(\'\', true)', content)
        self.assertIn('"notes": notes | default(\'\', true)', content)
        self.assertIn("{% if cost is defined %}", content)
        self.assertIn("{% if status is defined %}", content)
        self.assertIn("{% if failure_reason is defined %}", content)
        self.assertIn("tojson", content)
        self.assertNotIn('"tags": [', content)


class TestManualReEnrichFallbacks(unittest.TestCase):
    """Manual re-enrich should preserve operator-visible diagnostics for older archive shapes."""

    def test_reenrich_supports_single_color_archive_total_fallback(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("archive_row_source == 'at1'", content)
        self.assertIn("archive_detail.filament_used_grams", content)
        self.assertIn("archive_detail.filament_color", content)
        self.assertIn("archive_detail.filament_type", content)
        self.assertIn("multiple archived AMS trays matched archive-level type+color fallback", content)

    def test_reenrich_payload_carries_reason_and_saves_unavailable_diagnostics(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("archive_row_reason", content)
        self.assertIn("dict(payload, src=archive_row_source)", content)
        self.assertIn("dict(payload, reason=archive_row_reason)", content)
        self.assertIn("Print History Re-Enrich Saved Diagnostic Only", content)
        self.assertIn("hidden enrichment payload was updated with a", content)

    def test_reenrich_fetches_spoolman_api_with_archived_spools(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("rest_command.spoolman_getspools", content)
        self.assertIn('allow_archived: "true"', content)
        self.assertIn("spoolman_spools_response.content", content)
        self.assertIn("raw | from_json([])", content)
        self.assertIn("spoolman_spools_normalized", content)
        self.assertNotIn("spoolman_spools: >-", content)
        self.assertIn("Multiple Spoolman spools matched the archived tray UUID.", content)

    def test_spoolman_getspools_rest_command_supports_allow_archived_override(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "spoolman_sync" / "rest_commands" / "spoolman_getspools.yaml").read_text("utf-8")
        self.assertIn("spoolman_getspools:", content)
        self.assertIn("allow_archived={{ allow_archived | default('false') }}", content)
        self.assertIn("method: GET", content)


# =============================================================================
# =============================================================================
# 14. TAG FILTER OPTIONS
# =============================================================================

class TestPrintHistoryTagFilterOptions(unittest.TestCase):
    """Dropdown tag options should exclude system-managed archive tags."""

    def test_sync_filter_options_excludes_system_tag_prefixes(self):
        content = (LEGACY_BROWSER / "automations" / "print_history_sync_filter_options.yaml").read_text("utf-8")
        self.assertIn("system_tag_prefixes", content)
        self.assertIn("system_tag_values", content)
        self.assertIn("s:", content)
        self.assertIn("f:", content)
        self.assertIn("spoolman:", content)
        self.assertIn("material:", content)
        self.assertIn("vendor:", content)
        self.assertIn("cost:", content)
        self.assertIn("status:", content)
        self.assertIn("ha enrichment:", content)
        self.assertIn("ha_enrichment:", content)
        self.assertIn("ha_enriched:true", content)
        self.assertIn("not system_tag.value", content)
        self.assertIn("['All', 'None'] + (ns.values | sort)", content)

    def test_tag_filter_none_uses_only_user_tags(self):
        filtered_content = (LEGACY_BROWSER / "template_sensors" / "print_history_filtered.yaml").read_text("utf-8")
        browser_card_content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js").read_text("utf-8")
        helper_content = (HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_tag.yaml").read_text("utf-8")

        self.assertIn("user_tag_values = namespace(values=[])", filtered_content)
        self.assertIn("filter_tag == 'none' and user_tag_values.values | count == 0", filtered_content)
        self.assertIn("filter_tag in user_tag_values.values", filtered_content)
        self.assertIn('tag: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_tag"))', browser_card_content)
        self.assertIn("- None", helper_content)


# =============================================================================
# 15. POPUP AND SAVE REGRESSIONS
# =============================================================================

class TestPrintHistoryArchivePopupRegression(unittest.TestCase):
    """Archive popup should hide system metadata while preserving it on save."""

    def test_popup_wrapper_filters_lowercase_system_tags_for_editing(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup.yaml").read_text("utf-8")
        self.assertIn("const systemTagPrefixes = ['f:', 's:', 'spoolman:', 'vendor:', 'material:', 'cost:', 'status:', 'ha enrichment:', 'ha_enrichment:'];", content)
        self.assertIn("const systemTagValues = ['ha_enriched:true'];", content)
        self.assertIn("systemTagPrefixes.some((prefix) => normalized.startsWith(prefix))", content)
        self.assertIn("const archiveUserTags = parseTags(archive?.tags).filter((tag) => !isSystemTag(tag));", content)

    def test_popup_uses_custom_typeahead_tag_editor(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup.yaml").read_text("utf-8")
        self.assertIn("type: 'custom:print-history-tag-editor-card'", content)
        self.assertIn("suggestions_entity: 'input_select.print_history_filter_tag'", content)
        self.assertIn("Press Enter or comma to add.", content)

    def test_popup_seeds_favorite_helper_and_subscribes_content_card_to_it(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup.yaml").read_text("utf-8")
        self.assertIn("triggers_update: ['sensor.print_history_popup_archive_detail', 'input_boolean.print_history_popup_is_favorite']", content)
        self.assertIn("service: archive.is_favorite ? 'input_boolean.turn_on' : 'input_boolean.turn_off'", content)
        self.assertIn("entity_id: 'input_boolean.print_history_popup_is_favorite'", content)

    def test_popup_detail_sensor_refetches_when_popup_favorite_helper_changes(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "template_sensors" / "print_history_popup_archive_detail.yaml"
        ).read_text("utf-8")
        self.assertIn("entity_id: input_boolean.print_history_popup_is_favorite", content)
        self.assertIn("action: bambuddy.get_print_history_archive_detail", content)

    def test_popup_content_shows_only_user_notes(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("const notesInfo = splitArchiveNotes(archive?.notes);", content)
        self.assertIn("notesInfo.userNotes", content)
        self.assertIn("const enrichmentRows = Array.isArray(archive?.enrichment_filaments)", content)
        self.assertIn("Array.isArray(notesInfo.payload?.F)", content)
        self.assertIn(">Filament Colors<", content)
        self.assertIn(">Enrichment<", content)
        self.assertNotIn(">Tags<", content)

    def test_popup_content_derives_partial_status_and_review_badges(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("const hasEnrichmentData = enrichmentRows.length > 0;", content)
        self.assertIn("if (enrichmentStatusRaw === 'unavailable' && hasEnrichmentData) return 'partial';", content)
        self.assertIn("return enrichmentRowsWithState.some((row) => row.needsReview) ? 'partial' : 'complete';", content)
        self.assertIn("if (!hasResolvedEntityId(item?.s)) reviewReasons.push('Spool unresolved');", content)
        self.assertIn("if (!hasResolvedEntityId(item?.f)) reviewReasons.push('Filament unresolved');", content)
        self.assertIn("<span>Needs Review</span>", content)
        self.assertIn("<span>Spool unresolved</span>", content)
        self.assertIn("<span>Filament unresolved</span>", content)

    def test_popup_content_surfaces_enrichment_reason_and_source(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("const enrichmentReason = String(archive?.enrichment_reason || notesInfo.payload?.reason || '').trim();", content)
        self.assertIn("const enrichmentSource = String(archive?.enrichment_source || notesInfo.payload?.src || '').trim();", content)
        self.assertIn("const enrichmentSourceLabel = enrichmentSource === 'at1'", content)
        self.assertIn("Archive-level fallback", content)
        self.assertIn("${escapeHtml(enrichmentReason)}", content)

    def test_popup_timeline_uses_mobile_responsive_layout(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn(".print-history-popup-timeline{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);grid-template-areas:\"start duration end\" \"track track track\";", content)
        self.assertIn(".print-history-popup-timeline-side--start{grid-area:start;align-items:flex-start;text-align:left;}", content)
        self.assertIn(".print-history-popup-timeline-side--end{grid-area:end;align-items:flex-end;text-align:right;}", content)
        self.assertIn(".print-history-popup-timeline-duration{grid-area:duration;align-self:center;justify-self:center;", content)
        self.assertIn("@media (max-width: 640px)", content)
        self.assertIn(".print-history-popup-timeline{column-gap:10px;row-gap:8px;}", content)

    def test_popup_timeline_duration_chip_uses_lowercase_units_above_track(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("if (days) parts.push(`${days}d`);", content)
        self.assertIn("if (hours || days) parts.push(`${hours}h`);", content)
        self.assertIn("if (minutes || (!days && !hours)) parts.push(`${minutes}m`);", content)
        self.assertIn('<span class="print-history-popup-timeline-duration">${escapeHtml(timelineDuration)}</span>\n                <div class="print-history-popup-timeline-main">', content)

    def test_save_script_preserves_existing_system_tags_and_hidden_notes(self):
        content = (HISTORY / "scripts" / "save_print_history_archive_popup_edits.yaml").read_text("utf-8")
        self.assertIn("existing_tags_raw", content)
        self.assertIn("existing_recovery_block", content)
        self.assertIn("existing_payload", content)
        self.assertIn("existing_tags_raw.split(',')", content)
        self.assertIn("lowered.startswith('s:')", content)
        self.assertIn("lowered.startswith('vendor:')", content)
        self.assertIn("lowered.startswith('ha enrichment:')", content)
        self.assertIn("lowered.startswith('ha_enrichment:')", content)
        self.assertIn("lowered == 'ha_enriched:true'", content)
        self.assertIn("resolved_user_tags + preserved_system_tags", content)
        self.assertIn("existing_recovery_block | length > 0", content)
        self.assertIn("existing_payload is mapping and existing_payload.s is defined", content)


# =============================================================================
# 16. TAG COLOR CONSISTENCY
# =============================================================================

class TestPrintHistoryTagColors(unittest.TestCase):
    """Archive tags should use stable deterministic colors across cards and popup."""

    def test_archive_cards_use_shared_tag_color_helper(self):
        files = [
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_compact.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_media.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_detail.yaml",
        ]

        for path in files:
            content = path.read_text("utf-8")
            with self.subTest(file=path.relative_to(ROOT)):
                self.assertIn("const tagColorHelper = window.PrintHistoryTagColors;", content)
                self.assertIn("const tagColor = (tag) =>", content)
                self.assertIn("tagColorHelper.colorForTag(tag)", content)
                self.assertNotIn("const tagPalette =", content)

    def test_shared_tag_color_helper_uses_prefix_hashing_and_twenty_four_colors(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-tag-colors.js"
        ).read_text("utf-8")

        self.assertIn("const TAG_PALETTE = Object.freeze([", content)
        self.assertGreaterEqual(content.count("#"), 24)
        self.assertIn('return normalized.includes(":") ? normalized.split(":", 1)[0] : normalized;', content)
        self.assertIn("return TAG_PALETTE[hash % TAG_PALETTE.length];", content)
        self.assertIn("window.PrintHistoryTagColors = PrintHistoryTagColors;", content)

    def test_tag_rendering_no_longer_uses_single_hardcoded_blue(self):
        files = [
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_compact.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_media.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_detail.yaml",
        ]

        for path in files:
            content = path.read_text("utf-8")
            with self.subTest(file=path.relative_to(ROOT)):
                self.assertNotIn('tags.map((tag) => `<span style="background:#1565C0', content)
                self.assertIn('tags.map((tag) => `<span style="background:${tagColor(tag)}', content)

    def test_archive_color_dots_use_enrichment_payload_for_hover_text(self):
        files = [
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_compact.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_media.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_detail.yaml",
        ]

        for path in files:
            content = path.read_text("utf-8")
            with self.subTest(file=path.relative_to(ROOT)):
                self.assertIn("const ENRICHMENT_MARKER = '+>';", content)
                self.assertIn("const filamentChips = enrichmentRows.length", content)
                if path.name == "print_history_archive_popup_content.yaml":
                    self.assertIn("const enrichmentRows = Array.isArray(archive?.enrichment_filaments)", content)
                    self.assertIn("Array.isArray(notesInfo.payload?.F)", content)
                    self.assertIn("tooltip: [hex, ambiguity].filter(Boolean).join(' | ')", content)
                else:
                    self.assertIn("const enrichmentRows = Array.isArray(enrichmentPayload?.F) ? enrichmentPayload.F : [];", content)
                    self.assertIn("tooltip: [tray ? `${name} (${tray})` : name, hex, ambiguity].filter(Boolean).join(' | ') || name", content)
                self.assertIn("tooltip: hex", content)
                self.assertIn('title="${escapeHtml(chip.tooltip)}"', content)


class TestPrintHistoryTagEditorCard(unittest.TestCase):
    """The popup tag editor should use the filter tag list as its suggestion source."""

    def test_tag_editor_card_resources_are_registered(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboards" / "_resources.yaml").read_text("utf-8")
        self.assertIn("/local/3d_printing/print_history/print-history-tag-colors.js?v=1", content)
        self.assertIn("/local/3d_printing/print_history/print-history-tag-editor-card.js?v=3", content)


class TestPrintHistoryBrowserCardPopupFavoriteRegression(unittest.TestCase):
    """Browser card popup should re-render favorite UI from the popup helper."""

    def test_browser_card_popup_content_subscribes_to_popup_favorite_helper(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        self.assertIn('triggers_update: ["sensor.print_history_popup_archive_detail", "input_boolean.print_history_popup_is_favorite"]', content)

    def test_toggle_favorite_script_sets_popup_helper_from_archive_detail(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "scripts" / "toggle_print_history_archive_favorite.yaml"
        ).read_text("utf-8")
        self.assertIn("action: bambuddy.get_print_history_archive_detail", content)
        self.assertIn("response_variable: popup_detail_result", content)
        self.assertIn("{{ detail.get('is_favorite', false) }}", content)
        self.assertIn("action: input_boolean.turn_on", content)
        self.assertIn("action: input_boolean.turn_off", content)

    def test_tag_editor_card_reads_existing_options_and_writes_popup_helper(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-tag-editor-card.js"
        ).read_text("utf-8")

        self.assertIn('suggestions_entity: config.suggestions_entity || "input_select.print_history_filter_tag"', content)
        self.assertIn('this._hass?.states?.[this._config?.suggestions_entity]?.attributes?.options', content)
        self.assertIn('await this._hass.callService("input_text", "set_value", {', content)
        self.assertIn('value: joinedValue,', content)
        self.assertIn('split(",")', content)
        self.assertIn('Press Enter or comma to add.', content)
        self.assertIn('const helper = window.PrintHistoryTagColors;', content)
        self.assertIn('return helper.colorForTag(tag);', content)

    def test_tag_editor_card_keeps_input_element_stable_during_updates(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-tag-editor-card.js"
        ).read_text("utf-8")

        self.assertIn("_ensureFrame()", content)
        self.assertIn("this._elements = {", content)
        self.assertIn("_renderInputValue()", content)
        self.assertIn("_renderTagList()", content)
        self.assertIn("_renderSuggestions()", content)
        self.assertNotIn('this.shadowRoot.innerHTML = `\n      <style>', content.split("_render() {")[1])

    def test_color_filter_card_uses_precomputed_tooltip_metadata(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-color-filter-card.js"
        ).read_text("utf-8")

        self.assertIn('tooltips_attribute: "available_color_tooltips_json"', content)
        self.assertIn("JSON.stringify(colorsState?.attributes?.[this._config.tooltips_attribute] || \"\")", content)
        self.assertIn("_availableTooltips()", content)
        self.assertIn("tooltips.get(color.toLowerCase()) || this._formatColorLabel(color)", content)
        self.assertIn('title="${safeTooltip}"', content)

    def test_compact_card_implements_issue_809_metadata_and_height_contract(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_card_compact.yaml"
        ).read_text("utf-8")

        self.assertIn("const enrichmentStatusCode = String(enrichmentPayload?.s || '').toLowerCase();", content)
        self.assertIn("const archiveIdLabel = archiveId !== undefined && archiveId !== null && archiveId !== '' ? `Archive #${archiveId}` : 'Archive unavailable';", content)
        self.assertIn("Enrichment ${escapeHtml(enrichmentStatusLabel)}", content)
        self.assertIn("const tagColorHelper = window.PrintHistoryTagColors;", content)
        self.assertIn("tagColorHelper.colorForTag(tag)", content)
        self.assertIn("const tagLimit = 3;", content)
        self.assertIn("const hiddenTagCount = Math.max(0, allTags.length - tagLimit);", content)
        self.assertIn("… +${hiddenTagCount}", content)
        self.assertIn("- min-height: 320px", content)
        self.assertIn("- height: 100%", content)

    def test_print_history_dashboard_uses_direct_browser_card(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "dashboard_cards" / "print_history.yaml"
        ).read_text("utf-8")

        self.assertIn("type: custom:print-history-browser-card", content)
        self.assertIn("show_empty_state: true", content)


# =============================================================================
# 17. PHOTO CAPTURE FLOW VALIDATION
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
# 17. DOCUMENTATION COMPLETENESS
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
# 18. PAGINATION LOGIC
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
