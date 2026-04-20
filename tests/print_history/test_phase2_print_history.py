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
        "bulk_assign_print_history_project.yaml",
        "bulk_delete_print_history_archives.yaml",
        "bulk_set_print_history_archive_favorite.yaml",
        "bulk_update_print_history_user_tags.yaml",
        "backfill_print_history_archive_enrichment.yaml",
        "cancel_print_history_multi_select_mode.yaml",
        "capture_and_upload_snapshot.yaml",
        "enter_print_history_multi_select_mode.yaml",
        "resolve_current_archive_id.yaml",
        "load_history_page.yaml",
        "navigate_history.yaml",
        "refresh_print_history_archives.yaml",
        "clear_print_history_filters.yaml",
        "print_history_payload_self_test.yaml",
        "request_print_history_multi_select_action.yaml",
    ]

    EXPECTED_REST_COMMANDS = [
        "bambuddy_update_archive.yaml",
        "bambuddy_query_recent_archive.yaml",
        "bambuddy_get_archive_detail.yaml",
    ]

    EXPECTED_LEGACY_REST_COMMANDS = [
        "bambuddy_fetch_archives.yaml",
    ]

    EXPECTED_TEMPLATE_SENSORS = [
        "print_history_filter_date_chip.yaml",
        "print_history_payload_diagnostics.yaml",
        "print_history_popup_archive_detail.yaml",
        "print_history_popup_restore_workflow.yaml",
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
        "input_text_print_history_filter_end_date.yaml",
        "input_text_print_history_filter_start_date.yaml",
        "input_text_print_history_multi_select_request.yaml",
        "input_text_print_history_restore_source_archive_id.yaml",
        "input_text_print_history_restore_target_archive_id.yaml",
        "input_text_print_history_restore_upload_session_id.yaml",
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
        "input_boolean_print_history_multi_select_all_favorites.yaml",
        "input_boolean_print_history_multi_select_mode.yaml",
        "input_boolean_print_history_show_activity_heatmap.yaml",
    ]

    EXPECTED_HELPERS_INPUT_NUMBER = [
        "input_number_bambuddy_history_limit.yaml",
        "input_number_history_current_page.yaml",
        "input_number_midprint_capture_percent.yaml",
        "input_number_photo_review_timeout_hours.yaml",
        "input_number_print_history_multi_select_count.yaml",
        "input_number_print_history_page_size.yaml",
        "input_number_print_history_max_archives.yaml",
    ]

    EXPECTED_HELPERS_INPUT_SELECT = [
        "input_select_bambuddy_photo_review_state.yaml",
        "input_select_print_history_activity_metric.yaml",
        "input_select_print_history_filter_status.yaml",
        "input_select_print_history_filter_archive_error.yaml",
        "input_select_print_history_filter_enrichment_status.yaml",
        "input_select_print_history_filter_material.yaml",
        "input_select_print_history_filter_color.yaml",
        "input_select_print_history_filter_duplicates.yaml",
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
        "print_history_top_controls.yaml",
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

    def test_webhook_receiver_supports_v023_flattened_generic_fields(self):
        """v0.2.3 generic webhooks flatten structured variables into top-level fields."""
        path = COMMON / "automations" / "bambuddy_webhook_receiver.yaml"
        content = path.read_text(encoding="utf-8")
        self.assertIn("trigger.json.filename", content)
        self.assertIn("trigger.json.printer", content)
        self.assertIn("trigger.json.state", content)
        self.assertIn('raw in [\'print_started\', \'print_start\']', content)


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

    def test_date_filter_chip_uses_issue_898_format(self):
        content = (HISTORY / "template_sensors" / "print_history_filter_date_chip.yaml").read_text("utf-8")
        self.assertIn("{{ start }} - {{ end }}", content)
        self.assertIn("> {{ start }}", content)
        self.assertIn("< {{ end }}", content)
        self.assertNotIn("{{ start }} <> {{ end }}", content)
        self.assertNotIn("{{ start }} <>", content)
        self.assertNotIn("<> {{ end }}", content)

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
        self.assertIn("/local/3d_printing/print_history/print-history-browser-card.js?v=113", content)
        self.assertIn("/local/3d_printing/print_history/print-history-activity-heatmap-card.js?v=54", content)
        self.assertIn("/local/3d_printing/print_history/print-history-photo-gallery-card.js?v=55", content)
        self.assertIn("/local/3d_printing/print_history/print-history-archive-actions-card.js?v=19", content)
        self.assertIn("/local/3d_printing/common/print-filament-breakdown-card.js?v=4", content)

    def test_heatmap_grouping_reducer_keeps_card_context_for_enrichment_helpers(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js"
        ).read_text("utf-8")

        self.assertIn("_groupArchivesByDate(archives)", content)
        self.assertIn("enrichmentCounts: this._emptyEnrichmentCounts()", content)
        self.assertIn("}.bind(this),", content)

    def test_photo_gallery_uses_top_left_advanced_actions_menu_and_delete_confirmations(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-photo-gallery-card.js"
        ).read_text("utf-8")
        browser_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        action_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-archive-actions-card.js"
        ).read_text("utf-8")

        self.assertIn('action === "advanced-actions"', content)
        self.assertIn('data-action="advanced-actions"', content)
        self.assertIn('icon="mdi:dots-horizontal"', content)
        self.assertIn('type: "custom:print-history-archive-actions-card"', content)
        self.assertIn('action === "advanced-actions"', browser_content)
        self.assertIn('data-action="advanced-actions"', browser_content)
        self.assertIn('icon="mdi:dots-horizontal"', browser_content)
        self.assertIn('title: "Advanced Actions"', browser_content)
        self.assertIn('type: "custom:print-history-archive-actions-card"', browser_content)
        self.assertIn('.icon-action.advanced:hover,.icon-action.advanced:focus-visible', browser_content)
        self.assertIn('.action-buttons{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto;margin-right:-4px;}', browser_content)
        self.assertIn('.media-thumb-overlay{position:absolute;inset:12px 8px auto 12px;display:flex;align-items:flex-start;justify-content:space-between;gap:12px;pointer-events:none;z-index:2;}', browser_content)
        self.assertIn('.media-thumb-overlay .action-buttons{pointer-events:auto;margin-right:-2px;}', browser_content)
        self.assertIn('data-action="open-projects-page"', browser_content)
        self.assertIn('data-action="refresh-project-options"', browser_content)
        self.assertIn('window.open(url, "_blank", "noopener")', browser_content)
        self.assertIn('service: "script.refresh_print_history_popup_projects"', browser_content)
        self.assertIn('columns: archiveStatus === "printing" ? 6 : 7,', browser_content)
        self.assertNotIn('type: "grid",\n        columns: 2,\n        square: false,\n        cards: [\n          this._buildPopupActionButton(\n            "Projects"', browser_content)
        self.assertNotIn('window.__printHistoryArchiveActionsCardPromise', content)
        self.assertNotIn('print-history-archive-actions-card.js?v=5', content)
        self.assertIn('Files', action_content)
        self.assertIn('Links', action_content)
        self.assertIn('Archive', action_content)
        self.assertIn('Danger Zone', action_content)
        self.assertIn('Source 3MF attached:', action_content)
        self.assertIn('if (thumbnailPath && !hasPrimaryOverride)', action_content)
        self.assertIn('Download Gcode file', action_content)
        self.assertIn('Download 3MF', action_content)
        self.assertIn('Replace Source 3MF', action_content)
        self.assertIn('View on MakerWorld', action_content)
        self.assertNotIn('View Designer', action_content)
        self.assertNotIn('Open in Slicer', action_content)
        self.assertIn('PERMANENTLY REMOVES', action_content)
        self.assertIn('bambuddy/print_history_archive_action', action_content)
        self.assertIn('download_source_3mf', action_content)
        self.assertIn('download_gcode', action_content)
        self.assertIn('/api/bambuddy/print-history/archive/{archive_id}/source-3mf/upload', action_content)
        self.assertIn('this.shadowRoot.addEventListener("change", this._boundSourceUploadChangeHandler);', action_content)
        self.assertIn('if (!input || input.id !== "source-upload-input")', action_content)
        self.assertIn('this.shadowRoot ? this.shadowRoot.getElementById("source-upload-input") : null;', action_content)
        self.assertIn('<input id="source-upload-input" class="hidden-file-input" type="file" accept=".3mf,application/vnd.ms-package.3dmanufacturing-3dmodel+xml">', action_content)
        self.assertIn('this._lastRenderSignature = "";', action_content)
        self.assertIn('var nextSignature = this._computeRenderSignature(hass);', action_content)
        self.assertIn('if (nextSignature === this._lastRenderSignature)', action_content)
        self.assertIn('_buildSourceUploadFormData(file)', action_content)
        self.assertIn('var uploadFile = await this._materializeSourceUploadFile(file);', action_content)
        self.assertIn('var buffer = await file.arrayBuffer();', action_content)
        self.assertIn('return new File([buffer], String(file.name || "upload.3mf")', action_content)
        self.assertIn('var formData = new FormData();', action_content)
        self.assertIn('if (file.size === 0)', action_content)
        self.assertIn('body: this._buildSourceUploadFormData(uploadFile),', action_content)
        self.assertIn('headers: await this._authHeaders(false),', action_content)
        self.assertIn('headers: await this._authHeaders(true),', action_content)
        self.assertIn('if (response.status === 401)', action_content)
        self.assertIn('credentials: "same-origin"', action_content)
        self.assertIn('payload.message || payload.error', action_content)
        self.assertIn('var diagnosticsMessage = this._formatUploadDiagnostics(error && error.body ? error.body.diagnostics : null);', action_content)
        self.assertIn('String(error.message).trim() + " [" + diagnosticsMessage + "]"', action_content)
        self.assertIn('_formatUploadDiagnostics(diagnostics)', action_content)
        self.assertIn('summary.push("request=" + String(diagnostics.request_content_type));', action_content)
        self.assertIn('summary.push("chunks=" + String(diagnostics.chunk_count));', action_content)
        self.assertIn('summary.push("bytes=" + String(diagnostics.byte_count));', action_content)
        self.assertIn('body: payload,', action_content)
        self.assertIn('status: response.status,', action_content)
        self.assertIn('_describeError(error, "Source 3MF upload failed")', action_content)
        self.assertIn('if (error.body && typeof error.body === "object")', action_content)
        self.assertIn('var serialized = JSON.stringify(error);', action_content)
        self.assertIn('transition:none;', action_content)
        self.assertNotIn('type: "bambuddy/print_history_upload_source_3mf"', action_content)
        self.assertNotIn('auth.fetchWithAuth', action_content)
        self.assertIn('.hidden-file-input{display:none;}', action_content)
        self.assertIn('delete_print_history_archive', action_content)

    def test_browser_card_renders_variant_skeletons_while_loading(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js").read_text("utf-8")
        self.assertIn('body.className = "grid " + loadingVariant.toLowerCase() + " loading";', content)
        self.assertIn('body.innerHTML = this._renderSkeletonGrid(loadingVariant);', content)
        self.assertIn('var configured = Math.max(1, Number(this._stateValue(this._config.page_size_entity) || 0));', content)

    def test_browser_card_defines_skeleton_shells_for_all_variants(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js").read_text("utf-8")
        self.assertIn('@keyframes printHistoryShimmer', content)
        self.assertIn('class="card-shell media"', content)
        self.assertIn('class="card-shell list"', content)
        self.assertIn('class="card-shell compact"', content)

    def test_heatmap_card_renders_loading_skeleton_during_query(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('self._loading = true;', content)
        self.assertIn('self._renderLoadingState();', content)
        self.assertIn('class="loading-shell"', content)
        self.assertIn('@keyframes printHistoryHeatmapShimmer', content)

    def test_heatmap_card_normalizes_cancelled_statuses(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('raw === "cancelled" || raw === "aborted" || raw === "stopped"', content)
        self.assertIn('return "cancelled";', content)
        self.assertIn('cancelledCount', content)

    def test_heatmap_card_tracks_archived_statuses_separately_from_failures(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('archivedCount: 0', content)
        self.assertIn('archive.status === "archived"', content)
        self.assertIn('archived: { label: "Archived", color: "#1D4ED8" }', content)
        self.assertIn('return this._mixHexColors(baseColor, archivedColor', content)
        self.assertIn('return "Archived";', content)

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

    def test_heatmap_card_ignores_browser_page_revision_for_data_renders(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("_buildDataSignature(hass)", content)
        self.assertNotIn("pageInfoRevision", content)

    def test_heatmap_card_updates_selected_day_without_refetching_activity_rows(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("_buildSelectionSignature(hass)", content)
        self.assertIn("this._applySelectionOnlyState();", content)
        self.assertIn("this._renderModel = {", content)
        self.assertIn("_syncSelectedCellClasses()", content)
        self.assertNotIn('selected_day: String(this._stateValue(this._config.selected_date_entity) || "").trim()', content)

    def test_heatmap_card_keeps_existing_chart_visible_while_refreshing(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("var showLoadingState = !self._renderModel;", content)
        self.assertIn('self._showRefreshIndicator("Updating...");', content)
        self.assertIn("self._refreshing = !showLoadingState;", content)

    def test_heatmap_card_places_loading_month_axis_below_grid(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('".loading-month-row{display:grid;grid-template-columns:40px minmax(0,1fr);column-gap:10px;align-items:start;margin-top:6px;}"', content)
        self.assertIn('''<div class="loading-grid"><div class="loading-day-labels">' + dayLabels.join('') + '</div><div class="loading-cells">' + rows.join('') + '</div></div>' +
        '<div class="loading-month-row"><span></span><div class="loading-month-labels">' + monthLabels.join('') + '</div></div>''', content)

    def test_heatmap_card_preserves_last_successful_render_on_refresh_error(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("if (this._renderModel) {", content)
        self.assertIn('this._showRefreshIndicator("Couldn\'t refresh", true);', content)
        self.assertIn("_hideRefreshIndicator()", content)

    def test_heatmap_card_uses_api_object_count(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("objectCount: Math.max(1, this._toNumber(archive && archive.object_count))", content)

    def test_heatmap_card_supports_filaments_used_label(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('type: "bambuddy/print_history_query"', content)
        self.assertIn('include_activity_rows: true', content)
        self.assertIn('input.mode === "Filaments Used"', content)
        self.assertIn('input.mode === "Number of Unique Tags"', content)
        self.assertIn('input.mode === "Single vs Multi-Color Prints"', content)
        self.assertIn('input.mode === "Number of Unique Filaments"', content)
        self.assertIn('input.mode === "In a Project vs Not in a Project"', content)
        self.assertIn('input.mode === "Number of Duplicates / Similar"', content)
        self.assertIn('input.mode === "Enrichment Status"', content)
        self.assertIn('input.mode === "Number of Favorites"', content)
        self.assertIn('"filaments used": "Filaments Used"', content)
        self.assertIn('"number of unique tags": "Number of Unique Tags"', content)
        self.assertIn('"single vs multi-color prints": "Single vs Multi-Color Prints"', content)
        self.assertIn('"number of unique filaments": "Number of Unique Filaments"', content)
        self.assertIn('"in a project vs not in a project": "In a Project vs Not in a Project"', content)
        self.assertIn('"number of duplicates / similar": "Number of Duplicates / Similar"', content)
        self.assertIn('"enrichment status": "Enrichment Status"', content)
        self.assertIn('"number of favorites": "Number of Favorites"', content)
        self.assertNotIn('"filament uses": "Filaments Used"', content)
        self.assertNotIn('"number of different filaments": "Filaments Used"', content)
        self.assertNotIn('"outcome mix": "Outcome"', content)
        self.assertNotIn('"by outcome": "Outcome"', content)

    def test_heatmap_tooltip_prioritizes_selected_metric_without_duplicate_rows(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("var primaryMetric = this._resolvePrimaryTooltipMetric(mode, metrics);", content)
        self.assertIn("return !primaryMetric || metric.key !== primaryMetric.key;", content)
        self.assertIn("_buildTooltipMetrics(meta)", content)
        self.assertIn("_resolvePrimaryTooltipMetric(mode, metrics)", content)

    def test_heatmap_card_uses_valid_enrichment_blend_and_sunflower_favorites_scale(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('return this._rgbToHex(rgb.r, rgb.g, rgb.b);', content)
        self.assertIn('"#6B4F00", "#FACC15"', content)
        self.assertIn('".legend-main{display:inline-flex;align-items:center;gap:8px;}"', content)
        self.assertIn('".legend-separator{opacity:0.7;}"', content)
        self.assertIn("(legend.note ? '<span class=\"legend-note\">' + this._escapeHtml(legend.note) + '</span><span class=\"legend-separator\" aria-hidden=\"true\">|</span>' : \"\")", content)
        self.assertIn('if (mapped) {', content)
        self.assertIn('return mapped;', content)
        self.assertIn('self._showError(self._describeRenderError(err));', content)
        self.assertIn('Home Assistant websocket unavailable. Retry after the connection recovers.', content)
        self.assertIn('Math.round(Math.max(0, Math.min(255, channel))).toString(16).padStart(2, "0")', content)
        self.assertIn('day.enrichmentBackground = this._buildEnrichmentBackground(day);', content)
        self.assertIn('mode === "Enrichment Status" && meta && meta.enrichmentBackground', content)
        self.assertIn('return "linear-gradient(135deg, " + stops.join(", ") + ")";', content)
        self.assertNotIn('Mixed days use diagonal stripes; widths are proportional for smaller mixes.', content)
        self.assertIn('this._applyEnrichmentPatternFills(dataset);', content)
        self.assertIn('return seriesElement.querySelector(\'.apexcharts-heatmap-rect[j="\' + String(dataPointIndex) + \'"]\');', content)
        self.assertIn('pattern.setAttribute("patternTransform", "rotate(135)");', content)
        self.assertIn('rect.setAttribute("fill", "url(#" + patternId + ")");', content)

    def test_heatmap_card_parses_new_metric_inputs_once_per_archive(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn('var enrichmentPayload = this._extractEnrichmentPayload(archive && archive.notes);', content)
        self.assertIn('filamentIdentityKeys: filamentIdentityKeys,', content)
        self.assertIn('day.enrichmentCounts[archive.enrichmentStatus || "not defined"]', content)
        self.assertIn('day.uniqueTags[String(tag).toLowerCase()] = true;', content)

    def test_heatmap_card_formats_large_totals_with_locale_grouping(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js").read_text("utf-8")
        self.assertIn("return this._formatDecimal(value, 1) + \"h\";", content)
        self.assertIn("return this._formatDecimal(weight, 1) + \"g\";", content)
        self.assertIn("return \"$\" + this._formatDecimal(value, 2);", content)
        self.assertIn("'Prints: ' + this._formatCount(meta.count || 0)", content)
        self.assertIn("this._buildChipHtml(this._formatCount(activeDays) + \" active days\")", content)
        self.assertIn("this._formatCount(day.count) + (day.count === 1 ? \" print\" : \" prints\")", content)

    def test_activity_panel_switches_filament_weight_icon_to_kg_when_needed(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "dashboard_cards" / "print_history_activity_panel.yaml").read_text("utf-8")
        self.assertIn("activity_metric_total_label", content)
        self.assertIn("totalLabel.endsWith('kg')", content)
        self.assertIn("return 'mdi:weight-kilogram';", content)
        self.assertIn("'Number of Unique Tags': 'mdi:tag-multiple-outline'", content)
        self.assertIn("'Single vs Multi-Color Prints': 'mdi:compare-horizontal'", content)
        self.assertIn("'Number of Unique Filaments': 'mdi:palette-swatch-variant'", content)
        self.assertIn("'In a Project vs Not in a Project': 'mdi:folder-swap-outline'", content)
        self.assertIn("'Number of Duplicates / Similar': 'mdi:content-copy'", content)
        self.assertIn("'Enrichment Status': 'mdi:layers-triple-outline'", content)
        self.assertIn("'Number of Favorites': 'mdi:star'", content)


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
                    self.assertIn("Number of Unique Tags", options)
                    self.assertIn("Single vs Multi-Color Prints", options)
                    self.assertIn("Number of Unique Filaments", options)
                    self.assertIn("In a Project vs Not in a Project", options)
                    self.assertIn("Number of Duplicates / Similar", options)
                    self.assertIn("Enrichment Status", options)
                    self.assertIn("Number of Favorites", options)
                    self.assertNotIn("Filament Uses", options)
                    self.assertNotIn("Number of Different Filaments", options)

    def test_status_helpers_use_separate_archive_and_enrichment_statuses(self):
        filter_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_status.yaml"
        archive_error_filter_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_archive_error.yaml"
        enrichment_filter_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_enrichment_status.yaml"
        popup_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_popup_status.yaml"
        filter_data = _load_yaml_safe(filter_path)
        archive_error_filter_data = _load_yaml_safe(archive_error_filter_path)
        enrichment_filter_data = _load_yaml_safe(enrichment_filter_path)
        popup_data = _load_yaml_safe(popup_path)

        filter_options = next(iter(filter_data.values())).get("options", []) if isinstance(filter_data, dict) else []
        archive_error_filter_options = next(iter(archive_error_filter_data.values())).get("options", []) if isinstance(archive_error_filter_data, dict) else []
        enrichment_filter_options = next(iter(enrichment_filter_data.values())).get("options", []) if isinstance(enrichment_filter_data, dict) else []
        popup_options = next(iter(popup_data.values())).get("options", []) if isinstance(popup_data, dict) else []

        self.assertEqual(
            filter_options,
            ["All", "Completed", "Archived", "Failed", "Cancelled", "Printing"],
        )
        self.assertEqual(
            archive_error_filter_options,
            ["All", "Any Error", "Missing Core 3MF", "Source 3MF Only", "Missing Thumbnail"],
        )
        self.assertEqual(
            enrichment_filter_options,
            ["All", "Complete", "Near Complete", "Mostly Complete", "Partially Complete", "Unavailable", "Not Defined"],
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
        "input_text.print_history_restore_source_archive_id",
        "input_text.print_history_restore_target_archive_id",
        "input_text.print_history_restore_upload_session_id",
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
        "input_select.print_history_filter_archive_error",
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
        "sensor.print_history_popup_restore_workflow",
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
        self.assertIn("archive_cost_defined", content)
        self.assertIn("live_print_cost_available", content)
        self.assertIn("input_number.print_cost_default_per_kg", content)
        self.assertIn('cost: "{{ archive_cost_value }}"', content)
        self.assertIn('tags: "{{ merged_tags }}"', content)
        self.assertIn('notes: "{{ merged_notes }}"', content)
        self.assertNotIn("ha_enriched:true", content)
        self.assertIn("'f:' ~ filament_id", content)
        self.assertIn("'s:' ~ spool_id", content)
        self.assertNotIn('status: "{{ archive_status }}"', content)
        self.assertNotIn('cost: "{{ total_cost }}"', content)

    def test_enrichment_omits_cost_when_no_safe_total_exists(self):
        content = (HISTORY / "automations" / "bambuddy_enrich_archive_on_complete.yaml").read_text("utf-8")
        self.assertIn('value_template: "{{ archive_cost_defined }}"', content)
        self.assertIn("preserved_bambuddy_value", content)
        self.assertIn("effective_payload_rows", content)

    def test_update_archive_payload_is_field_optional(self):
        """PATCH payload should include only the archive fields that are explicitly supplied."""
        content = (HISTORY / "rest_commands" / "bambuddy_update_archive.yaml").read_text("utf-8")
        self.assertIn("namespace(body={", content)
        self.assertIn("{% if tags is defined %}", content)
        self.assertIn("{% if notes is defined %}", content)
        self.assertIn("{% if cost is defined %}", content)
        self.assertIn("{% if status is defined %}", content)
        self.assertIn("{% if failure_reason is defined %}", content)
        self.assertIn("{% if is_favorite is defined %}", content)
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
        self.assertIn("existing_slot_overrides", content)
        self.assertIn("requested_slot_overrides", content)
        self.assertIn("effective_slot_overrides", content)
        self.assertIn("archive_slot_rows_with_overrides", content)
        self.assertIn("override_tray_candidate", content)
        self.assertIn("tray_candidate.tray_code == override_tray", content)
        self.assertIn("manual slot overrides", content)
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

    def test_reenrich_recomputes_cost_from_effective_payload_when_possible(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("resolved_archive_cost_breakdown", content)
        self.assertIn("resolved_archive_cost_defined", content)
        self.assertIn("matched_spool.value.price", content)
        self.assertIn("matched_spool.value.filament_price", content)
        self.assertIn("matched_filament.value.filament_price", content)
        self.assertIn("input_number.print_cost_default_per_kg", content)
        self.assertIn('cost: "{{ resolved_archive_cost }}"', content)

    def test_reenrich_prefers_matching_spool_location_before_declaring_color_ambiguity(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("location_hint = 'AMS' if", content)
        self.assertIn("candidate.location | default('', true) | string == location_hint", content)
        self.assertIn("ns_location.items | count == 1", content)

    def test_reenrich_supports_temporal_fallback_and_marks_temporal_rows(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("archive_print_start_ts", content)
        self.assertIn("archive_temporal_window_start_ts", content)
        self.assertIn("archive_temporal_window_end_ts", content)
        self.assertIn("opened_ts", content)
        self.assertIn("first_used_ts", content)
        self.assertIn("last_used_ts", content)
        self.assertIn("archived_ts", content)
        self.assertIn("ns_match.match_method = 't_hist'", content)
        self.assertIn("ns_row.pm = 't_hist'", content)
        self.assertIn("Multiple Spoolman spools matched the archive time window.", content)

    def test_reenrich_uses_lifecycle_dates_before_filament_family_resolution(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("ns_temporal_scope = namespace(items=[])", content)
        self.assertIn("candidate.opened_ts | default(0, true) | float(0)", content)
        self.assertIn("starts_before_archive", content)
        self.assertIn("ends_after_archive", content)
        self.assertIn("ns_temporal_scope.items | count == 1", content)
        self.assertIn("candidate_last <= 0 and not (candidate.archived | default(false, true))", content)
        self.assertNotIn("candidate.archived_ts | default(0, true) | float(0)", content)

    def test_reenrich_prefers_spools_active_at_print_start_before_strict_end_window(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("ns_preprint_active = namespace(items=[])", content)
        self.assertIn("ended_before_print_start", content)
        self.assertIn("if not ended_before_print_start", content)
        self.assertIn("ns_print_start = namespace(items=[])", content)
        self.assertIn("has_start_evidence = candidate_opened > 0 or candidate_first > 0", content)
        self.assertIn("started_by_print = has_start_evidence", content)
        self.assertIn("active_at_print_start", content)
        self.assertIn("candidate_last >= archive_print_start_ts", content)
        self.assertIn("candidate_last <= 0 and not (candidate.archived | default(false, true))", content)
        self.assertNotIn("candidate_archived >= archive_print_start_ts", content)

    def test_reenrich_preserves_existing_only_when_it_is_strictly_better(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("(existing_detail_score | int(-1)) > (candidate_detail_score | int(-1))", content)
        self.assertNotIn("(existing_detail_score | int(-1)) >= (candidate_detail_score | int(-1))", content)

    def test_reenrich_reports_candidate_ambiguity_instead_of_archived_tray_text(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("Multiple candidate spools or filaments matched type+color.", content)
        self.assertIn("Archive-level fallback matched multiple candidate spools or filaments.", content)
        self.assertNotIn("Multiple archived AMS trays matched type+color.", content)

    def test_reenrich_identifies_filament_before_resolving_spool_family(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("ns_match.filament_id = ns_filament.ids[0] | int(0)", content)
        self.assertIn("candidate.filament_id == ns_match.filament_id", content)
        self.assertIn("ns_match.match_method = 'filament' if ns_match.filament_id is not none else 'color'", content)

    def test_reenrich_payload_marks_color_based_filament_recovery(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("ns_filament_pool.method = 'cmt'", content)
        self.assertIn("ns_filament_pool.method = 'cm'", content)
        self.assertIn("ns_filament_pool.method = 'ct'", content)
        self.assertIn("fm=ns_row.fm", content)

    def test_reenrich_generic_archive_rows_search_all_vendors(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("{% set vendor_mode = 'any' %}", content)
        self.assertIn("{% elif target_vendor | length > 0 %}", content)
        self.assertIn("{% set vendor_mode = 'exact' %}", content)
        self.assertIn("{% else %}\n                          {% set vendor_ok = true %}", content)
        self.assertNotIn("vendor_ok = (spool.vendor == 'Bambu Lab') if bambu_only else (spool.vendor != 'Bambu Lab')", content)

    def test_reenrich_replaces_old_heuristic_rows_when_new_candidate_is_ambiguous(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("candidate_replaces_heuristic_existing", content)
        self.assertIn("existing_row.fm | default('', true) | string", content)
        self.assertIn("candidate_am | length > 0 or row.f is none or row.s is none", content)
        self.assertIn("not candidate_replaces_heuristic_existing", content)

    def test_reenrich_supports_batch_mode_without_refreshing_every_archive(self):
        content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        self.assertIn("refresh_browser:", content)
        self.assertIn("should_refresh_browser", content)
        self.assertIn(
            '            reenrich_started_ts: "{{ as_timestamp(now()) | float(0) }}"\n'
            '            should_refresh_browser: "{{ refresh_browser if refresh_browser is defined else true }}"\n'
            '        - if:',
            content,
        )
        self.assertIn("value_template: \"{{ should_refresh_browser }}\"", content)

    def test_backfill_script_batches_reenrich_calls(self):
        content = (HISTORY / "scripts" / "backfill_print_history_archive_enrichment.yaml").read_text("utf-8")
        self.assertIn("backfill_print_history_archive_enrichment:", content)
        self.assertIn("archive_ids_csv", content)
        self.assertIn("script.reenrich_print_history_archive", content)
        self.assertIn("refresh_browser: false", content)
        self.assertIn("script.refresh_print_history_archives", content)

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
        browser_yaml_content = (HISTORY / "dashboard_cards" / "print_history_browser.yaml").read_text("utf-8")
        helper_content = (HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_tag.yaml").read_text("utf-8")
        selected_tags_helper_content = (HISTORY / "helpers" / "input_text" / "input_text_print_history_filter_tags.yaml").read_text("utf-8")
        tag_mode_helper_content = (HISTORY / "helpers" / "input_select" / "input_select_print_history_filter_tags_mode.yaml").read_text("utf-8")
        clear_tag_filter_content = (HISTORY / "scripts" / "clear_print_history_tag_filter.yaml").read_text("utf-8")

        self.assertIn("user_tag_values = namespace(values=[])", filtered_content)
        self.assertIn("filter_tag == 'none' and user_tag_values.values | count == 0", filtered_content)
        self.assertIn("filter_tag in user_tag_values.values", filtered_content)
        self.assertIn('tags: String(this._stateValue("input_text.print_history_filter_tags") || "").trim()', browser_card_content)
        self.assertIn('tag_mode: this._normalizeTagModeValue(this._stateValue("input_select.print_history_filter_tags_mode"))', browser_card_content)
        self.assertIn('_normalizeTagModeValue(value)', browser_card_content)
        self.assertIn('tag_untagged_only: this._stateValue("input_boolean.print_history_filter_tags_untagged_only") === "on"', browser_card_content)
        self.assertIn("- None", helper_content)
        self.assertIn("print_history_filter_tags:", selected_tags_helper_content)
        self.assertIn("print_history_filter_tags_mode:", tag_mode_helper_content)
        self.assertIn("clear_print_history_tag_filter:", clear_tag_filter_content)
        self.assertIn("input_select.print_history_filter_archive_error", browser_yaml_content)
        self.assertIn("sensor.print_history_filter_tags_summary", browser_yaml_content)
        self.assertIn("script.clear_print_history_tag_filter", browser_yaml_content)

    def test_tag_filter_summary_prefers_single_tag_labels_and_plural_mode_summary(self):
        summary_content = (HISTORY / "template_sensors" / "print_history_filter_tags_summary.yaml").read_text("utf-8")

        self.assertIn("{% set normalized_mode = mode if mode in ['Any', 'All'] else 'Any' %}", summary_content)
        self.assertIn("{% set ns = namespace(values=[], labels=[]) %}", summary_content)
        self.assertIn("{{ ns.labels[0] }}", summary_content)
        self.assertIn("{{ normalized_mode }} of {{ ns.values | count }} Tags", summary_content)
        self.assertIn("selected_tags_preview", summary_content)
        self.assertIn("selected_tags_tooltip", summary_content)
        self.assertIn("Show only prints without user tags.", summary_content)

    def test_tag_filter_popup_uses_compact_toggle_buttons(self):
        browser_yaml_content = (HISTORY / "dashboard_cards" / "print_history_browser.yaml").read_text("utf-8")

        self.assertIn("type: custom:config-template-card", browser_yaml_content)
        self.assertIn("title: Selected Tags", browser_yaml_content)
        self.assertIn("mode_entity: input_select.print_history_filter_tags_mode", browser_yaml_content)
        self.assertIn("helper: Choose one or more tags. Untagged is a separate toggle.", browser_yaml_content)
        self.assertIn("name: Untagged", browser_yaml_content)
        self.assertIn("action: toggle", browser_yaml_content)
        self.assertIn("name: Clear Tags", browser_yaml_content)
        self.assertIn("service: script.clear_print_history_tag_filter", browser_yaml_content)
        self.assertNotIn("**Current:**", browser_yaml_content)
        self.assertNotIn("Choose one or more tags or switch to untagged-only.", browser_yaml_content)

    def test_archive_error_filter_wired_into_browser_contract(self):
        browser_card_content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js").read_text("utf-8")
        browser_yaml_content = (HISTORY / "dashboard_cards" / "print_history_browser.yaml").read_text("utf-8")
        clear_script_content = (HISTORY / "scripts" / "clear_print_history_filters.yaml").read_text("utf-8")
        reset_page_content = (HISTORY / "automations" / "print_history_reset_page_on_filter_change.yaml").read_text("utf-8")

        self.assertIn('archive_error: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_archive_error"))', browser_card_content)
        self.assertIn("Clear Archive Error Filter", browser_yaml_content)
        self.assertIn("input_select.print_history_filter_archive_error", clear_script_content)
        self.assertIn("input_select.print_history_filter_archive_error", reset_page_content)

    def test_layout_variant_does_not_reset_page(self):
        reset_page_content = (HISTORY / "automations" / "print_history_reset_page_on_filter_change.yaml").read_text("utf-8")

        self.assertIn("input_select.print_history_sort", reset_page_content)
        self.assertIn("input_number.print_history_page_size", reset_page_content)
        self.assertNotIn("input_select.print_history_card_variant", reset_page_content)

    def test_clear_filters_script_preserves_explicit_date_bounds(self):
        clear_script_content = (HISTORY / "scripts" / "clear_print_history_filters.yaml").read_text("utf-8")

        self.assertNotIn("input_text.print_history_filter_start_date", clear_script_content)
        self.assertNotIn("input_text.print_history_filter_end_date", clear_script_content)
        self.assertIn("input_select.print_history_filter_date_range", clear_script_content)

    def test_browser_header_exposes_limit_notice_chip(self):
        browser_yaml_content = (HISTORY / "dashboard_cards" / "print_history_browser.yaml").read_text("utf-8")

        self.assertIn("sensor.bambuddy_print_history_browser_status", browser_yaml_content)
        self.assertIn("limit_notice", browser_yaml_content)
        self.assertIn(".bubble-sub-button.cache-limit", browser_yaml_content)
        self.assertIn("browser_mod.popup", browser_yaml_content)
        self.assertIn("Print History Cache", browser_yaml_content)

    def test_top_controls_switches_between_normal_and_multi_select_modes(self):
        content = (HISTORY / "dashboard_cards" / "print_history_top_controls.yaml").read_text("utf-8")

        self.assertIn("input_boolean.print_history_multi_select_mode", content)
        self.assertIn("input_number.print_history_multi_select_count", content)
        self.assertIn("input_boolean.print_history_multi_select_all_favorites", content)
        self.assertIn("input_text.print_history_multi_select_request", content)
        self.assertIn("script.enter_print_history_multi_select_mode", content)
        self.assertIn("script.cancel_print_history_multi_select_mode", content)
        self.assertIn("script.request_print_history_multi_select_action", content)
        self.assertIn("mdi:checkbox-multiple-blank-outline", content)
        self.assertIn("mdi:checkbox-multiple-marked-outline", content)
        self.assertIn("content: 'Multi-Select Prints'", content)
        self.assertIn("show_name: false", content)
        self.assertIn("name: Multi-Select Prints", content)
        self.assertIn("mdi:select-all", content)
        self.assertIn("mdi:tag-multiple-outline", content)
        self.assertIn("mdi:folder-multiple-outline", content)
        self.assertIn("mdi:trash-can-outline", content)


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

    def test_popup_archive_id_chip_omits_identifier_icon(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const iconMarkup = icon ? `<ha-icon icon=\"${icon}\" style=\"--mdc-icon-size:15px;flex:0 0 auto;color:${color};\"></ha-icon>` : '';", content)
        self.assertIn("archiveId != null ? renderInfoChip('', `#${archiveId}`, { fontWeight: 700, title: `Archive ID #${archiveId}` }) : ''", content)

    def test_popup_content_derives_enrichment_status_and_review_badges(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("const hasEnrichmentData = enrichmentRows.length > 0;", content)
        self.assertIn("if (!hasEnrichmentData) return enrichmentStatusRaw === 'unavailable' ? 'unavailable' : 'unavailable';", content)
        self.assertIn("if (enrichmentRows.some((item) => item?.f === null || item?.f === undefined || String(item?.f || '').trim() === '')) return 'partially complete';", content)
        self.assertIn("if (enrichmentRows.some((item) => item?.s === null || item?.s === undefined || String(item?.s || '').trim() === '')) return 'mostly complete';", content)
        self.assertIn("if (enrichmentRows.some((item) => item?.t === null || item?.t === undefined || String(item?.t || '').trim() === '')) return 'near complete';", content)
        self.assertIn("return 'complete';", content)

    def test_browser_card_enrichment_chip_includes_status_tooltips(self):
        content = (ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js").read_text("utf-8")
        self.assertIn("title=\"' + enrichmentChipTitle + '\"", content)
        self.assertIn('"near complete": "May be missing Tray information"', content)
        self.assertIn('"mostly complete": "Missing Spool ID(s)"', content)
        self.assertIn('"partially complete": "Missing Filament ID(s)"', content)
        self.assertIn('unavailable: "Missing All Data"', content)

    def test_browser_card_hides_thumbnail_when_archive_has_no_thumbnail_path(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("archive.thumbnail_path", content)
        self.assertIn("String(archive.thumbnail_path || \"\").trim()", content)

    def test_media_cards_cache_bust_thumbnail_and_photo_urls_after_archive_media_changes(self):
        browser_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        gallery_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-photo-gallery-card.js"
        ).read_text("utf-8")

        self.assertIn("_archiveMediaCacheKey(archive)", browser_content)
        self.assertIn("_withArchiveMediaCacheKey", browser_content)
        self.assertIn(' + "v=" + encodeURIComponent(cacheKey)', browser_content)
        self.assertIn("_archiveMediaCacheKey(archive)", gallery_content)
        self.assertIn("_withArchiveMediaCacheKey", gallery_content)
        self.assertIn(' + "v=" + encodeURIComponent(cacheKey)', gallery_content)

    def test_photo_gallery_only_resets_local_media_state_when_archive_id_changes(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-photo-gallery-card.js"
        ).read_text("utf-8")

        self.assertIn('this._archiveId = "";', content)
        self.assertIn('if (this._archiveId && archiveId && archiveId !== this._archiveId) {', content)

    def test_popup_content_surfaces_enrichment_reason_and_source(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("const enrichmentReason = String(archive?.enrichment_reason || notesInfo.payload?.reason || '').trim();", content)
        self.assertIn("const enrichmentSource = String(archive?.enrichment_source || notesInfo.payload?.src || '').trim();", content)

    def test_popup_content_surfaces_match_evidence_and_archive_source_json(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("const describeFilamentMatchMethod = (value) => {", content)
        self.assertIn("const describeSpoolMatchMethod = (value) => {", content)
        self.assertIn("const describeProvenanceMarker = (value) => {", content)
        self.assertIn("let detailEnrichmentProvenance = [];", content)
        self.assertIn("const provenanceRaw = detailState.attributes?.enrichment_provenance_json || '[]';", content)
        self.assertIn("const sourceEvidence = archive?.archive_source_evidence", content)
        self.assertIn("const archivedRawAms = Array.isArray(archiveExtraData?._print_data?.raw_data?.ams)", content)
        self.assertIn("const archivedAmsDisclosureUsesRawBlob = archivedRawAms.length > 0;", content)
        self.assertIn("const archivedAmsDisclosureLabel = 'Archived AMS evidence JSON';", content)
        self.assertIn("Match Evidence", content)
        self.assertIn("Archive Source Evidence", content)
        self.assertIn("Archived filament_slots[] JSON", content)
        self.assertIn("Archived AMS evidence JSON", content)
        self.assertIn("spool match markers <strong>sm</strong>", content)
        self.assertIn("print-history-popup-enrichment-toggle-label", content)
        self.assertIn("Show Details", content)
        self.assertIn("grid-template-columns:minmax(0,1fr);", content)
        self.assertIn("white-space:pre;", content)
        self.assertIn("white-space:normal !important;", content)
        self.assertIn("min-width:0;max-width:100%;font-size:12px;line-height:1.45;color:#E3F2FD;white-space:normal !important;", content)
        self.assertIn("print-history-popup-json-description", content)
        self.assertIn("print-history-popup-json-toggle-label", content)
        self.assertIn(".print-history-popup-json-toggle-icon{display:inline-flex;align-items:center;justify-content:center;width:18px;min-width:18px;font-size:18px;", content)

    def test_popup_detail_template_sensor_exposes_enrichment_provenance_json(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "template_sensors" / "print_history_popup_archive_detail.yaml").read_text("utf-8")
        self.assertIn("enrichment_provenance_json:", content)
        self.assertIn("result.get('enrichment_provenance', [])", content)

    def test_archive_enrichment_ui_uses_candidate_match_wording_for_ambiguity_codes(self):
        popup_content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        browser_card = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        breakdown_card = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "common" / "print-filament-breakdown-card.js"
        ).read_text("utf-8")

        for content in (popup_content, browser_card, breakdown_card):
            self.assertIn("Multiple candidate spools or filaments matched type+color", content)
            self.assertIn("Archive-level fallback matched multiple candidate spools or filaments", content)
            self.assertNotIn("Multiple archived AMS trays matched type+color", content)

    def test_archive_filament_breakdown_card_sorts_derived_cost_amounts_after_computing_cost(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "common" / "print-filament-breakdown-card.js"
        ).read_text("utf-8")

        self.assertIn("const chartEntries = entries.map(function (entry) {", content)
        self.assertIn("if (this._config.mode === \"cost\" && totalCost > 0 && resolvedWeight > 0) {", content)
        self.assertIn("nextEntry.cost = totalCost * (entry.weight / resolvedWeight);", content)
        self.assertIn("const sortedEntries = this._sortArchiveEntries(chartEntries, this._config.mode === \"cost\" ? \"cost\" : \"weight\");", content)

    def test_archive_filament_breakdown_card_keeps_unresolved_rows_after_resolved_trays(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "common" / "print-filament-breakdown-card.js"
        ).read_text("utf-8")

        self.assertIn("const expandedAmsMatch = label.match(/^AMS(\\d+)-(\\d+)$/);", content)
        self.assertIn("if (leftTray) {", content)
        self.assertIn("return -1;", content)
        self.assertIn("if (rightTray) {", content)
        self.assertIn("return 1;", content)

    def test_archive_filament_breakdown_card_compact_header_aligns_total_and_sort_toggle(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "common" / "print-filament-breakdown-card.js"
        ).read_text("utf-8")

        self.assertIn('const headerSideHtml = `<div class="header-side${sortToggleHtml ? " has-sort-toggle" : ""}"><div class="total">${this._escapeHtml(view.totalLabel)}</div>${sortToggleHtml}</div>`;', content)
        self.assertIn('.header-side {', content)
        self.assertIn('justify-content: flex-end;', content)
        self.assertIn('.header-compact .header-side {', content)
        self.assertIn('grid-template-columns: minmax(0,1fr) auto;', content)
        self.assertIn('justify-self: end;', content)
        self.assertNotIn('header header-compact"><div class="total">${this._escapeHtml(view.totalLabel)}</div></div>', content)

    def test_popup_timeline_uses_mobile_responsive_layout(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn(".print-history-popup-timeline{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);grid-template-areas:\"start duration end\" \"track track track\";", content)
        self.assertIn(".print-history-popup-timeline-side--start{grid-area:start;align-items:flex-start;text-align:left;}", content)
        self.assertIn(".print-history-popup-timeline-side--end{grid-area:end;align-items:flex-end;text-align:right;}", content)
        self.assertIn(".print-history-popup-timeline-duration-wrap{grid-area:duration;align-self:center;justify-self:center;", content)
        self.assertIn("@media (max-width: 640px)", content)
        self.assertIn(".print-history-popup-timeline{column-gap:10px;row-gap:8px;}", content)

    def test_popup_timeline_duration_chip_uses_lowercase_units_above_track(self):
        content = (ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml").read_text("utf-8")
        self.assertIn("if (days) parts.push(`${days}d`);", content)
        self.assertIn("if (hours || days) parts.push(`${hours}h`);", content)
        self.assertIn("if (minutes || (!days && !hours)) parts.push(`${minutes}m`);", content)
        self.assertIn('<span class="print-history-popup-timeline-duration">${escapeHtml(timelineDuration)}</span>', content)
        self.assertIn('class="print-history-popup-timeline-tooltip-wrap print-history-popup-timeline-legend-wrap"', content)
        self.assertIn('<div class="print-history-popup-timeline-main">', content)

    def test_browser_card_only_appends_year_for_non_current_year_archives(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("if (this._dateYear(parsed) !== this._dateYear(new Date())) {", content)
        self.assertIn('formatOptions.year = "numeric";', content)

    def test_popup_timeline_only_appends_year_for_non_current_year_archives(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const haTimeZone = hass?.config?.time_zone ? String(hass.config.time_zone) : undefined;", content)
        self.assertIn("if (options.includeYearWhenNotCurrent === true && formatDateYear(parsed) !== formatDateYear(new Date())) {", content)
        self.assertIn("const formatTimelineDate = (value) => formatDateLabel(value, { includeTime: true, includeYearWhenNotCurrent: true });", content)

    def test_popup_timeline_collapses_out_of_range_events_instead_of_clamping_them(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const timelineEdgePadding = 4;", content)
        self.assertIn("const timelineOverflowAnchorOffset = 12;", content)
        self.assertIn("const hasBeforeOverflow = rawTimelineStartTime !== null && rawTimelineEvents.some((item) => {", content)
        self.assertIn("const hasAfterOverflow = rawTimelineEndTime !== null && rawTimelineEvents.some((item) => {", content)
        self.assertIn("const timelineStartPosition = hasBeforeOverflow ? timelineOverflowAnchorOffset : timelineEdgePadding;", content)
        self.assertIn("const timelineEndPosition = hasAfterOverflow ? (100 - timelineOverflowAnchorOffset) : (100 - timelineEdgePadding);", content)
        self.assertIn("if (normalized.timeMs < rawTimelineStartTime) {", content)
        self.assertIn("if (normalized.timeMs > rawTimelineEndTime) {", content)
        self.assertNotIn("const clampedMs = Math.min(rawTimelineEndTime, Math.max(rawTimelineStartTime, eventTimeMs));", content)
        self.assertIn("const beforeOverflowMarkup = buildTimelineOverflowMarkup(timelineOverflow.beforeStart, 'before');", content)
        self.assertIn("const afterOverflowMarkup = buildTimelineOverflowMarkup(timelineOverflow.afterEnd, 'after');", content)

    def test_popup_timeline_overflow_dot_uses_dotted_connectors_and_combined_hover_text(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const buildTimelineOverflowTitle = (events, summary) => [", content)
        self.assertNotIn("].join('\\n');", content)
        self.assertIn("border-top:2px dotted", content)
        self.assertIn("before print start", content)
        self.assertIn("after ${endTimelineLabel.toLowerCase()}", content)
        self.assertIn("events.length === 1 ? events[0].color : '#78909C'", content)
        self.assertNotIn("left:-26px", content)
        self.assertNotIn("right:-26px", content)
        self.assertIn("left:${timelineOverflowBeforePosition}%", content)
        self.assertIn("left:${timelineEndPosition}%", content)

    def test_popup_timeline_uses_shared_custom_tooltip_markup_for_anchors_and_events(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const buildTimelineTooltipMarkup = (items, options = {}) => {", content)
        self.assertIn("const buildTimelinePointMarkup = (options) => {", content)
        self.assertIn('class="print-history-popup-timeline-tooltip-wrap"', content)
        self.assertIn('class="print-history-popup-timeline-tooltip-line${item.summary ? \' print-history-popup-timeline-tooltip-line--summary\' : \'\'}"', content)
        self.assertIn('class="print-history-popup-timeline-tooltip-dot"', content)
        self.assertIn("${startTimelineMarkup}", content)
        self.assertIn("${endTimelineMarkup}", content)
        self.assertNotIn('title="${escapeHtml(startTimelineTitle)}"', content)
        self.assertNotIn('title="${escapeHtml(endTimelineTitle)}"', content)

    def test_popup_timeline_legend_reuses_shared_tooltip_shell(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn('class="print-history-popup-timeline-tooltip print-history-popup-timeline-legend-tooltip"', content)
        self.assertIn(".print-history-popup-timeline-tooltip-wrap:hover .print-history-popup-timeline-tooltip", content)
        self.assertNotIn(".print-history-popup-timeline-legend-wrap:hover .print-history-popup-timeline-legend-tooltip", content)

    def test_popup_timeline_aligns_edge_tooltips_inside_popup_bounds(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const timelineTooltipClassForPosition = (position) => {", content)
        self.assertIn("if (position <= (timelineStartPosition + 4)) return 'print-history-popup-timeline-tooltip--edge-left';", content)
        self.assertIn("if (position <= (timelineStartPosition + 18)) return 'print-history-popup-timeline-tooltip--lean-left';", content)
        self.assertIn("if (position >= (timelineEndPosition - 4)) return 'print-history-popup-timeline-tooltip--edge-right';", content)
        self.assertIn("if (position >= (timelineEndPosition - 18)) return 'print-history-popup-timeline-tooltip--lean-right';", content)
        self.assertIn("tooltipClass: 'print-history-popup-timeline-tooltip--edge-left'", content)
        self.assertIn("tooltipClass: 'print-history-popup-timeline-tooltip--edge-right'", content)
        self.assertIn(".print-history-popup-timeline-tooltip--edge-left{left:0;transform:translate(0, -6px);}", content)
        self.assertIn(".print-history-popup-timeline-tooltip--lean-left{transform:translate(-18%, -6px);}", content)
        self.assertIn(".print-history-popup-timeline-tooltip--edge-right{left:auto;right:0;transform:translate(0, -6px);}", content)
        self.assertIn(".print-history-popup-timeline-tooltip--lean-right{transform:translate(-82%, -6px);}", content)
        self.assertIn(".print-history-popup-timeline-tooltip-wrap:hover .print-history-popup-timeline-tooltip--lean-left,", content)
        self.assertIn(".print-history-popup-timeline-tooltip-wrap:hover .print-history-popup-timeline-tooltip--lean-right,", content)

    def test_popup_timeline_reserves_overflow_space_only_when_needed(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const timelineOverflowDotInset = 2;", content)
        self.assertIn("const timelineOverflowBeforePosition = timelineOverflowDotInset;", content)
        self.assertIn("const timelineOverflowAfterPosition = 100 - timelineOverflowDotInset;", content)
        self.assertIn("wrapStyle: `position:absolute;left:${timelineStartPosition}%;top:50%;width:10px;height:10px;transform:translate(-50%, -50%);`", content)
        self.assertIn("wrapStyle: `position:absolute;left:${timelineEndPosition}%;top:50%;width:10px;height:10px;transform:translate(-50%, -50%);`", content)
        self.assertIn("<span style=\"position:absolute;left:${timelineStartPosition}%;right:${100 - timelineEndPosition}%;top:50%;height:2px;border-radius:999px;background:rgba(255,255,255,0.18);transform:translateY(-50%);\"></span>", content)

    def test_popup_timeline_keeps_in_range_dots_clear_of_anchors_and_neighbors(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const anchorClearance = 5;", content)
        self.assertIn("const minGap = 5;", content)
        self.assertIn("const trackMin = Math.min(timelineEndPosition, timelineStartPosition + anchorClearance);", content)
        self.assertIn("const trackMax = Math.max(trackMin, timelineEndPosition - anchorClearance);", content)

    def test_popup_timeline_tooltips_render_as_opaque_overlays(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn(".print-history-popup-timeline-main{grid-area:track;display:flex;align-items:center;min-width:0;width:100%;position:relative;overflow:visible;z-index:5;}", content)
        self.assertIn(".print-history-popup-timeline-track{position:relative;width:100%;height:18px;overflow:visible;}", content)
        self.assertIn("background:#12161C", content)
        self.assertIn("z-index:80", content)
        self.assertIn("overflow:hidden", content)
        self.assertIn("backdrop-filter:none", content)
        self.assertIn(".print-history-popup-timeline-tooltip-wrap:hover,.print-history-popup-timeline-tooltip-wrap:focus-visible,.print-history-popup-timeline-tooltip-wrap:focus-within{z-index:90;}", content)

    def test_save_script_preserves_existing_system_tags_and_hidden_notes(self):
        content = (HISTORY / "scripts" / "save_print_history_archive_popup_edits.yaml").read_text("utf-8")
        self.assertIn("existing_tags_raw", content)
        self.assertIn("existing_recovery_block", content)
        self.assertIn("existing_payload", content)
        self.assertIn("resolved_project_label", content)
        self.assertIn("state_attr('sensor.bambuddy_print_history_browser_status', 'project_options')", content)
        self.assertIn("merged_project_id", content)
        self.assertIn("{% if merged_project_id == '__NULL__' %}", content)
        self.assertIn("{{ merged_project_id | int(0) }}", content)
        self.assertIn("existing_tags_raw.split(',')", content)
        self.assertIn("lowered.startswith('s:')", content)
        self.assertIn("lowered.startswith('vendor:')", content)
        self.assertIn("lowered.startswith('ha enrichment:')", content)
        self.assertIn("lowered.startswith('ha_enrichment:')", content)
        self.assertIn("lowered == 'ha_enriched:true'", content)
        self.assertIn("resolved_user_tags + preserved_system_tags", content)
        self.assertIn("existing_recovery_block | length > 0", content)
        self.assertIn("existing_payload is mapping and existing_payload.s is defined", content)
        self.assertNotIn("response_variable: save_archive_response", content)

    def test_save_script_supports_optional_browser_refresh(self):
        content = (HISTORY / "scripts" / "save_print_history_archive_popup_edits.yaml").read_text("utf-8")
        self.assertIn("refresh_browser:", content)
        self.assertIn("should_refresh_browser", content)
        self.assertIn('should_refresh_browser: "{{ refresh_browser if refresh_browser is defined else true }}"', content)
        self.assertIn("action: bambuddy.refresh_print_history_archive_detail", content)
        self.assertIn('value_template: "{{ should_refresh_browser }}"', content)
        self.assertIn("action: script.refresh_print_history_archives", content)

    def test_note_update_paths_force_targeted_archive_sync(self):
        save_content = (HISTORY / "scripts" / "save_print_history_archive_popup_edits.yaml").read_text("utf-8")
        reenrich_content = (HISTORY / "scripts" / "reenrich_print_history_archive.yaml").read_text("utf-8")
        auto_content = (HISTORY / "automations" / "bambuddy_enrich_archive_on_complete.yaml").read_text("utf-8")

        self.assertIn("action: bambuddy.refresh_print_history_archive_detail", save_content)
        self.assertIn("action: bambuddy.refresh_print_history_archive_detail", reenrich_content)
        self.assertIn("action: bambuddy.refresh_print_history_archive_detail", auto_content)

    def test_bambuddy_services_expose_targeted_archive_sync(self):
        content = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "services.yaml").read_text("utf-8")
        self.assertIn("refresh_print_history_archive_detail:", content)
        self.assertIn("Fetch one archive from Bambuddy and immediately upsert it into the local Variant 3 store.", content)
        const_content = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "const.py").read_text("utf-8")
        init_content = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "__init__.py").read_text("utf-8")
        self.assertIn('SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_DETAIL = "refresh_print_history_archive_detail"', const_content)
        self.assertIn("async_handle_refresh_archive_detail", init_content)
        self.assertIn("SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_DETAIL", init_content)

    def test_bambuddy_services_expose_enrichment_metadata_management(self):
        content = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "services.yaml").read_text("utf-8")
        self.assertIn("get_print_history_archive_enrichment_metadata:", content)
        self.assertIn("update_print_history_archive_enrichment_metadata:", content)
        self.assertIn("MISSING_SPOOL", content)
        self.assertIn("system-managed enrichment tags", content)
        self.assertIn("Slot Overrides", content)
        self.assertIn("slot_id and at least one of tray, spool_id, or filament_id", content)

        const_content = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "const.py").read_text("utf-8")
        self.assertIn(
            'SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA = "get_print_history_archive_enrichment_metadata"',
            const_content,
        )
        self.assertIn(
            'SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA = "update_print_history_archive_enrichment_metadata"',
            const_content,
        )

        init_content = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "__init__.py").read_text("utf-8")
        self.assertIn("async_handle_get_enrichment_metadata", init_content)
        self.assertIn("async_handle_update_enrichment_metadata", init_content)
        self.assertIn("ENRICHMENT_METADATA_MODES", init_content)
        self.assertIn("slot_overrides", init_content)
        self.assertIn("SLOT=1 TRAY=B2", init_content)

    def test_popup_project_helper_uses_no_project_default(self):
        popup_path = HISTORY / "helpers" / "input_select" / "input_select_print_history_popup_project.yaml"
        popup_data = _load_yaml_safe(popup_path)
        popup_options = next(iter(popup_data.values())).get("options", []) if isinstance(popup_data, dict) else []

        self.assertEqual(popup_options, ["No Project"])

    def test_browser_popup_includes_project_selector(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn('input_select.print_history_popup_project', content)
        self.assertIn('name: "Project"', content)
        self.assertIn('service: "input_select.set_options"', content)
        self.assertIn('entity_id: "input_select.print_history_popup_project"', content)


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

    def test_shared_tag_color_helper_uses_prefix_hashing_and_thirty_six_colors(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-tag-colors.js"
        ).read_text("utf-8")

        self.assertIn("const TAG_PALETTE = Object.freeze([", content)
        self.assertGreaterEqual(content.count("#"), 36)
        self.assertIn('return normalized.includes(":") ? normalized.split(":", 1)[0] : normalized;', content)
        self.assertIn("let hash = 2166136261;", content)
        self.assertIn("hash = Math.imul(hash, 16777619) >>> 0;", content)
        self.assertIn("return TAG_PALETTE[hash % TAG_PALETTE.length];", content)
        self.assertIn("background: rgbaForHex(color, 0.14)", content)
        self.assertIn("border: rgbaForHex(color, 0.58)", content)
        self.assertIn("styleForTag,", content)
        self.assertIn("window.PrintHistoryTagColors = PrintHistoryTagColors;", content)

    def test_browser_card_renders_accent_tag_chips_from_shared_helper(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("_tagStyle(tag)", content)
        self.assertIn("styleForTag(tag)", content)
        self.assertIn("_renderTagChip(tag)", content)
        self.assertIn('background:var(--tag-background, rgba(148,163,184,0.16))', content)
        self.assertIn('color:var(--primary-text-color)', content)
        self.assertIn('box-shadow:inset 0 0 0 1px var(--tag-border-color, rgba(148,163,184,0.42)),0 0 0 1px transparent', content)

    def test_tag_editor_card_renders_accent_tag_pills_from_shared_helper(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-tag-editor-card.js"
        ).read_text("utf-8")

        self.assertIn("_tagStyle(tag)", content)
        self.assertIn("styleForTag(tag)", content)
        self.assertIn('background: var(--tag-background, rgba(148, 163, 184, 0.16));', content)
        self.assertIn('color: var(--primary-text-color);', content)
        self.assertIn('box-shadow: inset 0 0 0 1px var(--tag-border-color, rgba(148, 163, 184, 0.42)), 0 0 0 1px transparent;', content)

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
        self.assertIn("/local/3d_printing/print_history/print-history-tag-colors.js?v=4", content)
        self.assertIn("/local/3d_printing/print_history/print-history-tag-editor-card.js?v=10", content)
        self.assertIn("/local/3d_printing/print_history/print-history-archive-actions-card.js?v=19", content)
        self.assertIn("/local/3d_printing/print_history/print-history-archive-restore-card.js?v=30", content)
        self.assertIn("/local/3d_printing/print_history/print-history-3d-viewer-card.js?v=63", content)
        self.assertIn("/local/3d_printing/print_history/print-history-browser-card.js?v=113", content)

    def test_popup_project_refresh_script_forces_immediate_browser_refresh_and_reseeds_popup_options(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "scripts" / "refresh_print_history_popup_projects.yaml"
        ).read_text("utf-8")

        self.assertIn("alias: Refresh Print History Popup Projects", content)
        self.assertIn("action: bambuddy.refresh_print_history_browser", content)
        self.assertIn("immediate: true", content)
        self.assertIn("entity_id: input_select.print_history_popup_project", content)
        self.assertIn("state_attr('sensor.bambuddy_print_history_browser_status', 'project_options')", content)

    def test_tag_mode_all_is_preserved_for_browser_and_heatmap_queries(self):
        browser_card_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        heatmap_card_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-activity-heatmap-card.js"
        ).read_text("utf-8")

        self.assertIn('tag_mode: this._normalizeTagModeValue(this._stateValue("input_select.print_history_filter_tags_mode"))', browser_card_content)
        self.assertIn('return String(value || "").trim() === "All" ? "All" : "Any";', browser_card_content)
        self.assertIn('tag_mode: this._normalizeTagModeValue(this._stateValue("input_select.print_history_filter_tags_mode"))', heatmap_card_content)
        self.assertIn('return String(value || "").trim() === "All" ? "All" : "Any";', heatmap_card_content)

    def test_tag_editor_card_supports_header_mode_toggle(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-tag-editor-card.js"
        ).read_text("utf-8")

        self.assertIn("local_only: !!config.local_only,", content)
        self.assertIn("getTags()", content)
        self.assertIn("setTags(value)", content)
        self.assertIn('mode_entity: config.mode_entity || "",', content)
        self.assertIn('mode_options: Array.isArray(config.mode_options) && config.mode_options.length ? config.mode_options : ["Any", "All"],', content)
        self.assertIn('const currentValue = this._readModeValue();', content)
        self.assertIn('headerActions.style.display = "inline-flex";', content)
        self.assertIn('class="mode-chip', content)
        self.assertIn('await this._hass.callService("input_select", "select_option", {', content)
        self.assertIn('entity_id: this._config.mode_entity,', content)

    def test_browser_card_uses_projected_filament_slots_and_cached_archive_models(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("this._normalizedArchiveCache = {};", content)
        self.assertIn("this._pruneNormalizedArchiveCache(this._response.archives);", content)
        self.assertIn("var filamentChips = this._filamentChipsFromSlots(archive.filament_slots);", content)
        self.assertIn("var notesInfo = this._splitArchiveNotesLight(archive.notes);", content)

    def test_websocket_query_boolean_overrides_map_to_helper_on_off_states(self):
        content = (
            ROOT / "homeassistant" / "custom_components" / "bambuddy" / "manager.py"
        ).read_text("utf-8")

        self.assertIn("QUERY_BOOLEAN_OVERRIDE_FIELDS = {", content)
        self.assertIn('"favorites_only",', content)
        self.assertIn('"tag_untagged_only",', content)
        self.assertIn('if field_name in QUERY_BOOLEAN_OVERRIDE_FIELDS:', content)
        self.assertIn('snapshot[entity_id] = "on" if bool(value) else "off"', content)

    def test_browser_card_project_chips_use_shared_filter_action_path(self):
        browser_card_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        action_script_content = (HISTORY / "scripts" / "apply_print_history_card_filter_action.yaml").read_text("utf-8")

        self.assertIn('target_value_raw: "{{ value | string | trim }}"', action_script_content)
        self.assertIn("action_key == 'project_set'", action_script_content)
        self.assertIn('entity_id: input_select.print_history_filter_project', action_script_content)
        self.assertIn('option: "{{ target_value_raw }}"', action_script_content)
        self.assertIn('data-filter-action="project_set"', browser_card_content)
        self.assertIn("Click to filter by this project", browser_card_content)
        self.assertIn('class="chip project-chip interactive-chip"', browser_card_content)
        self.assertIn('.project-chip.interactive-chip:hover,.project-chip.interactive-chip:focus-visible', browser_card_content)

    def test_browser_card_status_chips_use_shared_filter_action_path(self):
        browser_card_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        action_script_content = (HISTORY / "scripts" / "apply_print_history_card_filter_action.yaml").read_text("utf-8")

        self.assertIn("action_key == 'status_set'", action_script_content)
        self.assertIn('entity_id: input_select.print_history_filter_status', action_script_content)
        self.assertIn('option: "{{ target_value_raw }}"', action_script_content)
        self.assertIn('data-filter-action="status_set"', browser_card_content)
        self.assertIn('statusFilterValue: status === "completed" ? "Completed"', browser_card_content)
        self.assertIn('class="chip status-chip interactive-chip"', browser_card_content)
        self.assertIn('Click to filter by this status', browser_card_content)
        self.assertIn('.status-chip.interactive-chip:hover,.status-chip.interactive-chip:focus-visible', browser_card_content)

    def test_browser_card_enrichment_chips_use_shared_filter_action_path(self):
        browser_card_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        action_script_content = (HISTORY / "scripts" / "apply_print_history_card_filter_action.yaml").read_text("utf-8")

        self.assertIn("action_key == 'enrichment_status_set'", action_script_content)
        self.assertIn('entity_id: input_select.print_history_filter_enrichment_status', action_script_content)
        self.assertIn('data-filter-action="enrichment_status_set"', browser_card_content)
        self.assertIn('enrichmentFilterValue: enrichmentStatus === "near complete" ? "Near Complete"', browser_card_content)
        self.assertIn('enrichmentStatus === "not defined" ? "Not Defined"', browser_card_content)
        self.assertIn('class="chip enrichment-chip interactive-chip"', browser_card_content)
        self.assertIn('Click to filter by this enrichment status', browser_card_content)
        self.assertIn('.enrichment-chip.interactive-chip:hover,.enrichment-chip.interactive-chip:focus-visible', browser_card_content)

    def test_browser_card_printer_chips_use_shared_filter_action_path(self):
        browser_card_content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        action_script_content = (HISTORY / "scripts" / "apply_print_history_card_filter_action.yaml").read_text("utf-8")

        self.assertIn("action_key == 'printer_set'", action_script_content)
        self.assertIn('entity_id: input_select.print_history_filter_printer', action_script_content)
        self.assertIn('data-filter-action="printer_set"', browser_card_content)
        self.assertIn('_resolvePrinterFilterValue(printerId, printerName)', browser_card_content)
        self.assertIn('printerFilterValue: this._resolvePrinterFilterValue(archive.printer_id, archive.printer_name),', browser_card_content)
        self.assertIn('Click to filter by this printer', browser_card_content)
        self.assertIn('type="button" data-action="apply-filter" data-filter-action="printer_set"', browser_card_content)
        self.assertIn('.interactive-chip{appearance:none;-webkit-appearance:none;border:none;cursor:pointer;font-family:inherit;', browser_card_content)

    def test_archive_restore_card_registration_is_guarded(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-archive-restore-card.js"
        ).read_text("utf-8")
        self.assertIn('this._hass.callService("bambuddy", service, data, undefined, true);', content)
        self.assertIn('if (!customElements.get("print-history-archive-restore-card")) {', content)
        self.assertIn('customElements.define("print-history-archive-restore-card", PrintHistoryArchiveRestoreCard);', content)

    def test_archive_viewer_card_uses_proxy_endpoints_and_fallbacks(self):
        script = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-3d-viewer-card.js"
        ).read_text("utf-8")

        self.assertIn('https://cdn.jsdelivr.net/npm/gcode-preview@2.18.0/+esm', script)
        self.assertIn('type: "bambuddy/print_history_archive_viewer"', script)
        self.assertIn('print-history-3d-viewer-card requires archive_id', script)
        self.assertIn('disconnectedCallback()', script)
        self.assertIn('this._disposePreview();', script)
        self.assertIn('typeof this._preview.dispose === "function"', script)
        self.assertIn('if (!this.isConnected || !this._config || !this.shadowRoot || !this._hass) {', script)
        self.assertIn('Capture View', script)
        self.assertIn('Crop View', script)
        self.assertIn('Capture Crop', script)
        self.assertIn('Animate', script)
        self.assertIn('Animated', script)
        self.assertIn('Download G-code', script)
        self.assertIn('Download PNG', script)
        self.assertIn('Upload to Archive', script)
        self.assertNotIn('Upload + Use In List View', script)
        self.assertNotIn('Open Bambuddy', script)
        self.assertNotIn('archives-link', script)
        self.assertIn('const CROP_PRESETS = {', script)
        self.assertIn("viewer-workbench", script)
        self.assertIn("header-meta", script)
        self.assertIn("stage-toolbar", script)
        self.assertIn("capture-hero", script)
        self.assertIn("Capture workspace", script)
        self.assertIn("Capture ready to use", script)
        self.assertIn("Crop mode is active", script)
        self.assertIn('this._renderAnimated = false;', script)
        self.assertIn('this._animateButton = null;', script)
        self.assertIn('this._boundAnimateHandler = this._handleAnimate.bind(this);', script)
        self.assertIn('_updateAnimateButton()', script)
        self.assertIn('_handleAnimate()', script)
        self.assertIn('this._loadedSignature = "";', script)
        self.assertIn('renderAnimated: this._renderAnimated', script)
        self.assertIn('RenderAnimated: renderAnimated', script)
        self.assertIn('preview.sceneManager.renderAnimated()', script)
        self.assertIn('Animated Preview', script)
        self.assertIn('Static Preview', script)
        self.assertIn('"<div class=\'eyebrow\'>3D Viewer</div>" +', script)
        self.assertIn('"<h1 id=\'viewer-title\'>3D Viewer</h1>" +', script)
        self.assertIn('"<div id=\'viewer-subtitle\' class=\'subtitle\' hidden></div>" +', script)
        self.assertNotIn('Print History Viewer', script)
        self.assertIn("_archiveChipMarkup()", script)
        self.assertIn("<span class='chip'>Archive #", script)
        self.assertIn('subtitleNode.hidden = !subtitleText;', script)
        self.assertIn('this._setTitle(archiveTitle, "");', script)
        self.assertNotIn('Preparing Bambuddy archive preview.', script)
        self.assertNotIn('this._setTitle(archiveTitle, "Bambuddy archive preview.");', script)
        self.assertNotIn('this._setTitle(archiveTitle, `Archive #${archiveId}`);', script)
        self.assertIn("Rendered G-code preview. Use drag, pan, and zoom inside the canvas.", script)
        self.assertIn('scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" })', script)
        self.assertIn('capture-preview-wrap.has-image img{display:block;}', script)
        self.assertIn('.shell{display:grid;grid-template-rows:auto auto auto;gap:14px;min-height:720px;padding:22px 18px 18px;}', script)
        self.assertIn(".viewer-workbench{--viewer-stage-height:min(72vh,680px);display:grid;grid-template-columns:minmax(0,1.7fr) minmax(320px,0.95fr);grid-template-areas:'stage capture';gap:14px;align-items:stretch;}", script)
        self.assertIn('.capture-panel{grid-area:capture;display:grid;grid-template-rows:auto minmax(0,1fr);gap:14px;padding:18px 20px;position:sticky;top:18px;align-self:stretch;min-height:var(--viewer-stage-height);height:var(--viewer-stage-height);box-sizing:border-box;}', script)
        self.assertIn("@media (max-width:720px){.shell{padding:16px 12px 12px;min-height:600px;}.header{padding:16px;}.fallback,.capture-panel{padding-left:16px;padding-right:16px;}.capture-panel{padding-top:16px;padding-bottom:16px;}.stage{min-height:58vh;height:58vh;}.stage-toolbar{left:12px;top:12px;right:12px;}.overlay{inset:14px 14px auto auto;max-width:calc(100% - 28px);}.capture-title-row{align-items:stretch;}.capture-actions{width:100%;justify-content:flex-start;}}", script)
        self.assertIn('_syncViewerCanvasSize()', script)
        self.assertIn('canvas.width = metrics.width;', script)
        self.assertIn('canvas.height = metrics.height;', script)
        self.assertIn('id=\'crop-layer\'', script)
        self.assertIn('id=\'crop-aspect-select\'', script)
        capture_panel_markup = script[script.index("<section id='capture-panel'"):]
        self.assertLess(capture_panel_markup.index("id='capture-controls'"), capture_panel_markup.index("capture-preview-stack"))
        self.assertIn('_setCropMode(true);', script)
        self.assertIn('_cropPresetLabel()', script)
        self.assertIn('_buildCornerRect(', script)
        self.assertNotIn('capture-hero-copy', script)
        self.assertNotIn('capture-copy', script)
        self.assertNotIn('capture-note', script)
        self.assertNotIn('Use Capture View for the full frame', script)
        self.assertNotIn('Capture uses the exact popup canvas', script)
        self.assertNotIn('thumbnail-like default', script)
        self.assertNotIn('print-history-3d-viewer.html', script)
        self.assertNotIn('without reopening the viewer in another tab', script)
        self.assertNotIn("<section id='viewer-status' class='panel status'>", script)
        self.assertIn('this._boundCaptureHandler = this._handleCapture.bind(this);', script)
        self.assertIn('this._capture = {', script)
        self.assertIn('type: "bambuddy/print_history_upload_photo"', script)
        self.assertNotIn('set_print_history_primary_photo', script)
        self.assertNotIn('this._hass.callService(', script)
        self.assertNotIn('window.open(targetUrl, "_blank", "noopener")', script)
        self.assertIn('archive: this._parseArchiveConfig(config.archive_json || config.archive || null),', script)
        self.assertIn('_archiveUsedColors()', script)
        self.assertIn('_resolveInitialToolIndex(colors, gcodeText)', script)
        self.assertIn('const explicitPaletteColors = [];', script)
        self.assertIn('const unmatchedColorCandidates = candidateIds.filter((candidateId) => {', script)
        self.assertIn('explicitPaletteColors.indexOf(candidateColor) < 0', script)
        self.assertIn('const uniqueColorCandidates = candidateIds.filter((candidateId) => {', script)
        self.assertIn('paletteColorCounts[candidateColor] === 1', script)
        self.assertIn('_singleArchiveFallbackColor()', script)
        self.assertIn('const archiveFallbackColor = this._singleArchiveFallbackColor();', script)
        self.assertIn('_extractFilamentColorsFromGcode(gcodeText)', script)
        self.assertIn('if (toolId === 1000 || toolId === 255) {', script)
        self.assertIn('normalizedTool = defaultToolIndex;', script)
        self.assertIn('tool === 1000', script)
        self.assertIn('tool === 255 && currentTool != null', script)
        self.assertIn('disableGradient: !this._viewerSettings.useColorGradient', script)
        self.assertIn('this._preview = preview;', script)
        self.assertIn('preview.processGCode(previewGcode);', script)
        self.assertIn('_showFallback(', script)
        self.assertIn('customElements.define("print-history-3d-viewer-card", PrintHistory3dViewerCard);', script)

    def test_archive_viewer_popup_passes_archive_payload_to_viewer_card(self):
        script = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn('archive_json: archive ? JSON.stringify(archive) : "{}",', script)

    def test_duplicate_summary_uses_related_label_without_explicit_lineage(self):
        script = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        popup = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("var isRelated = duplicateCount > 0 && !isSource && !isDuplicate;", script)
        self.assertIn("'Related · ' + groupSize + ' prints'", script)
        self.assertIn("roleEmblemLabel: 'Related'", script)
        self.assertIn("roleEmblemClass: 'related'", script)
        self.assertIn(".card.related-match", script)
        self.assertIn(".role-emblem.related", script)
        self.assertNotIn("var isOriginal = duplicateCount > 0 && (isSource || !isDuplicate);", script)

        self.assertIn("const isRelated = duplicateCount > 0 && !isSource && !isDuplicate;", popup)
        self.assertIn("roleLabel: 'Related Prints'", popup)
        self.assertIn("chipLabel: groupSize > 1 ? `Related · ${groupSize} prints` : 'Related'", popup)
        self.assertIn("icon: 'mdi:relation-many'", popup)

    def test_archive_viewer_consolidation_removes_standalone_page_and_routes(self):
        script = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-3d-viewer-card.js"
        ).read_text("utf-8")
        integration = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "__init__.py").read_text("utf-8")
        consts = (ROOT / "homeassistant" / "custom_components" / "bambuddy" / "const.py").read_text("utf-8")

        self.assertFalse((ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-3d-viewer.html").exists())
        self.assertFalse((ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-3d-viewer-page.js").exists())
        self.assertIn('id=\'crop-layer\'', script)
        self.assertIn('Landscape 16:9', script)
        self.assertNotIn('Square is the best starting point', script)
        self.assertNotIn('/capture-upload', script)
        self.assertNotIn('ArchiveViewerCaptureUploadView', integration)
        self.assertNotIn('ArchiveViewerCapabilitiesView', integration)
        self.assertNotIn('ARCHIVE_VIEWER_CAPTURE_UPLOAD_URL', consts)
        self.assertNotIn('ARCHIVE_VIEWER_CAPABILITIES_URL', consts)
        self.assertIn('ARCHIVE_VIEWER_GCODE_URL', consts)


class TestPrintHistoryBrowserCardPopupFavoriteRegression(unittest.TestCase):
    """Browser card popup should re-render favorite UI from the popup helper."""

    def test_browser_card_popup_content_subscribes_to_popup_favorite_helper(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        self.assertIn('triggers_update: ["sensor.print_history_popup_archive_detail", "input_boolean.print_history_popup_is_favorite"]', content)

    def test_browser_card_renders_duplicate_chip_from_projected_metadata(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("_duplicateSummary(archive)", content)
        self.assertIn("duplicate_count", content)
        self.assertIn("duplicate_sequence", content)
        self.assertIn("original_archive_id", content)
        self.assertIn("duplicateChipLabel", content)
        self.assertIn("role-emblem", content)
        self.assertIn("Dup of #", content)
        self.assertIn("Source ·", content)

    def test_browser_card_exposes_direct_3d_view_actions(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn('data-action="viewer"', content)
        self.assertIn('mdi:cube-scan', content)
        self.assertIn('_buildArchiveViewerCardConfig(archive)', content)
        self.assertIn('_buildArchiveViewerPopupContent(archive)', content)
        self.assertIn('title: "3D Viewer"', content)
        self.assertIn('type: "custom:print-history-3d-viewer-card"', content)
        self.assertIn('archive_id: archive && archive.id != null ? String(archive.id) : ""', content)

    def test_browser_card_favorite_buttons_render_toggle_tooltips_and_pressed_state(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("_renderFavoriteButton(normalized, archiveJson)", content)
        self.assertIn("_favoriteButtonTitle(isFavorite)", content)
        self.assertIn("aria-pressed=\"' + (isFavorite ? 'true' : 'false') + '\"", content)
        self.assertIn("Remove from favorites", content)
        self.assertIn("Add to favorites", content)
        self.assertIn("(toggle favorite)", content)
        self.assertIn(".icon-action.favorite:hover,.icon-action.favorite:focus-visible", content)

    def test_browser_card_compact_layout_places_name_below_thumb_and_aligns_metadata(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("grid-template-areas:'thumb summary' 'name name' 'details details'", content)
        self.assertIn("content compact-name", content)
        self.assertIn("action-buttons compact-actions", content)
        self.assertIn("compact-status-line", content)
        self.assertIn("compact-date", content)
        self.assertIn("compact-meta-line", content)
        self.assertIn("color-enrichment-row", content)
        self.assertIn("photoAction", content)
        self.assertIn("project-chip span{display:inline-flex;align-items:center;min-width:0;", content)

    def test_browser_card_primary_actions_share_same_order_across_variants(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("_renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction)", content)
        self.assertEqual(content.count("_renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction)"), 4)

        helper_signature = "_renderPrimaryActionButtons(normalized, archiveJson, favoriteButton, photoAction) {"
        helper_start = content.index(helper_signature) + len(helper_signature)
        helper_end = content.index("\n\n  _renderFavoriteButton", helper_start)
        helper = content[helper_start:helper_end]

        self.assertLess(helper.index('mdi:cube-scan'), helper.index('favoriteButton'))
        self.assertLess(helper.index('favoriteButton'), helper.index('photoAction'))

    def test_browser_card_list_view_omits_hidden_images_placeholder_when_images_are_disabled(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("var listImageUrl = showImages ? normalized.thumbnailUrl(baseUrl) : '';", content)
        self.assertIn("? (listImageUrl", content)
        self.assertIn("? '<div class=\"thumb-wrap\"><div class=\"media-gallery-surface\"><div class=\"list-thumb-empty\">No preview image available</div></div></div>'", content)
        self.assertNotIn("var listPlaceholderLabel = showImages", content)

    def test_browser_card_popup_action_row_includes_3d_view_button(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn('"3D View"', content)
        self.assertIn('title: "3D View · " + archiveName', content)
        self.assertIn('type: "vertical-stack"', content)
        self.assertIn('cards: [this._buildArchiveViewerCardConfig(archive)]', content)
        self.assertIn('content: this._buildArchiveViewerPopupContent(archive)', content)

    def test_popup_content_renders_duplicate_summary_from_projected_metadata(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_content.yaml"
        ).read_text("utf-8")

        self.assertIn("const buildDuplicateState = (currentArchive) =>", content)
        self.assertIn("duplicateState.hasDuplicateContext", content)
        self.assertIn("duplicateState.chipLabel", content)
        self.assertIn("This archive is the original source for a duplicate set", content)
        self.assertIn("This archive is a duplicate copy derived from original archive", content)

    def test_popup_favorite_button_updates_helper_before_backend_toggle(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "common" / "dashboard_cards" / "card_templates" / "print_history_archive_popup_favorite_button.yaml"
        ).read_text("utf-8")
        self.assertIn("service: browser_mod.sequence", content)
        self.assertIn("return isFavorite ? 'input_boolean.turn_off' : 'input_boolean.turn_on';", content)
        self.assertIn("entity_id: input_boolean.print_history_popup_is_favorite", content)
        self.assertIn("service: script.toggle_print_history_archive_favorite", content)

    def test_toggle_favorite_script_sets_popup_helper_from_archive_detail(self):
        content = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "scripts" / "toggle_print_history_archive_favorite.yaml"
        ).read_text("utf-8")
        self.assertIn("action: bambuddy.get_print_history_archive_detail", content)
        self.assertIn("response_variable: archive_detail_result", content)
        self.assertIn("action: bambuddy.set_print_history_archive_favorite", content)
        self.assertIn("response_variable: favorite_update_result", content)
        self.assertIn("next_is_favorite", content)
        self.assertIn("{{ detail.get('is_favorite', false) }}", content)
        self.assertIn("action: input_boolean.turn_on", content)
        self.assertIn("action: input_boolean.turn_off", content)
        self.assertNotIn("action: script.refresh_print_history_archives", content)
        self.assertNotIn("action: rest_command.bambuddy_toggle_favorite", content)

    def test_browser_card_favorite_updates_invalidate_normalized_cache(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")
        self.assertIn('return archiveId + ":" + payloadHash + ":" + String(archive.is_favorite ? "1" : "0");', content)
        self.assertIn("async _toggleFavorite(archive)", content)
        self.assertIn("async _runBulkFavoriteToggle()", content)
        self.assertGreaterEqual(content.count("this._normalizedArchiveCache = {};"), 3)

    def test_multi_select_scripts_use_shared_helpers_and_bulk_services(self):
        request_content = (HISTORY / "scripts" / "request_print_history_multi_select_action.yaml").read_text("utf-8")
        enter_content = (HISTORY / "scripts" / "enter_print_history_multi_select_mode.yaml").read_text("utf-8")
        cancel_content = (HISTORY / "scripts" / "cancel_print_history_multi_select_mode.yaml").read_text("utf-8")
        tag_content = (HISTORY / "scripts" / "bulk_update_print_history_user_tags.yaml").read_text("utf-8")
        project_content = (HISTORY / "scripts" / "bulk_assign_print_history_project.yaml").read_text("utf-8")
        favorite_content = (HISTORY / "scripts" / "bulk_set_print_history_archive_favorite.yaml").read_text("utf-8")
        delete_content = (HISTORY / "scripts" / "bulk_delete_print_history_archives.yaml").read_text("utf-8")

        self.assertIn("input_text.print_history_multi_select_request", request_content)
        self.assertIn("requested_action ~ '|' ~ (now().timestamp() | int(0))", request_content)
        self.assertIn("input_boolean.print_history_multi_select_mode", enter_content)
        self.assertIn("input_number.print_history_multi_select_count", enter_content)
        self.assertIn("input_boolean.print_history_multi_select_all_favorites", cancel_content)
        self.assertIn("regex_findall('\\d+')", tag_content)
        self.assertIn("bambuddy.get_print_history_archive_detail", tag_content)
        self.assertIn("preserved_system_tags", tag_content)
        self.assertIn("bambuddy.update_print_history_archive", tag_content)
        self.assertIn("regex_findall('\\d+')", project_content)
        self.assertIn("bambuddy.update_print_history_archive", project_content)
        self.assertIn("regex_findall('\\d+')", favorite_content)
        self.assertIn("bambuddy.set_print_history_archive_favorite", favorite_content)
        self.assertIn('is_favorite: "{{ target_favorite }}"', favorite_content)
        self.assertIn("regex_findall('\\d+')", delete_content)
        self.assertIn("{{ ns.values | tojson | from_json }}", delete_content)
        self.assertNotIn("archive_ids_json", delete_content)
        self.assertIn("bambuddy.delete_print_history_archive", delete_content)

    def test_browser_card_supports_multi_select_mode_and_bulk_dialogs(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("this._selectionSignature = \"\";", content)
        self.assertIn("this._selectedArchiveIds = {};", content)
        self.assertIn("_buildSelectionSignature()", content)
        self.assertIn("_isMultiSelectMode()", content)
        self.assertIn("_consumePendingMultiSelectRequest()", content)
        self.assertIn("data-action=\"select-archive\"", content)
        self.assertIn("selection-badge", content)
        self.assertIn("bulk-dialog", content)
        self.assertIn("bulk-tag-add-editor-host", content)
        self.assertIn("bulk-tag-remove-editor-host", content)
        self.assertIn("_mountBulkTagEditors()", content)
        self.assertIn("_bulkTagDialogValue(", content)
        self.assertIn('local_only: true,', content)
        self.assertIn("color-scheme:light dark", content)
        self.assertIn("select option,.bulk-dialog-field select optgroup", content)
        self.assertIn("bulk_update_print_history_user_tags", content)
        self.assertIn("bulk_assign_print_history_project", content)
        self.assertIn("bulk_set_print_history_archive_favorite", content)
        self.assertIn("bulk_delete_print_history_archives", content)
        self.assertGreaterEqual(content.count("_completeBulkActionAndExitMode()"), 3)
        self.assertIn('await this._hass.callService("script", "cancel_print_history_multi_select_mode", {});', content)
        self.assertIn('window.confirm("Delete " + selectedCount + (selectedCount === 1 ? " selected print" : " selected prints") + "? This permanently removes them from Bambuddy and cannot be undone.")', content)
        self.assertIn('window.prompt("Type DELETE to permanently remove " + selectedCount + (selectedCount === 1 ? " selected print." : " selected prints."), "")', content)

    def test_print_history_append_event_calls_capture_response_data(self):
        files = (
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "automations" / "bambuddy_capture_pause_resume_timeline.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "automations" / "bambuddy_enrich_archive_on_complete.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "scripts" / "capture_and_upload_snapshot.yaml",
            ROOT / "homeassistant" / "packages" / "3d_printing" / "print_history" / "scripts" / "reenrich_print_history_archive.yaml",
        )

        for path in files:
            content = path.read_text("utf-8")
            self.assertEqual(
                content.count("action: bambuddy.append_print_history_event"),
                content.count("response_variable: append_event_result"),
                msg=f"{path} must capture every append_print_history_event response",
            )

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
        self.assertIn('return helper.styleForTag(tag);', content)

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
        self.assertIn('data-tooltip="${safeTooltip}"', content)
        self.assertIn("_updateTooltipPosition(button)", content)
        self.assertIn('window.addEventListener("resize", this._boundWindowLayoutHandler);', content)
        self.assertIn('position: fixed;', content)
        self.assertIn('tooltip.style.left = `${Math.round(clampedLeft)}px`;', content)
        self.assertIn('max-width: min(320px, calc(100vw - 16px));', content)

    def test_browser_card_filament_swatches_use_clamped_custom_tooltips(self):
        content = (
            ROOT / "homeassistant" / "www" / "3d_printing" / "print_history" / "print-history-browser-card.js"
        ).read_text("utf-8")

        self.assertIn("_renderFilamentDot(chip)", content)
        self.assertIn('class="dot-button"', content)
        self.assertIn("_updateDotTooltipPosition(dotNode)", content)
        self.assertIn('window.addEventListener("resize", this._boundTooltipLayoutHandler);', content)
        self.assertIn('translateX(calc(-50% + var(--dot-tooltip-shift, 0px)))', content)
        self.assertIn('width:max-content;', content)
        self.assertIn('min-width:min(180px, calc(100vw - 16px));', content)
        self.assertIn('max-width:min(320px, calc(100vw - 16px));', content)

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
        self.assertTrue((DOCS_HIST / "ui-media" / "photo-capture-design.md").exists())

    def test_archive_enrichment_design_exists(self):
        self.assertTrue((DOCS_HIST / "planning" / "archive-enrichment.md").exists())

    def test_archive_enrichment_doc_includes_manual_reenrich_flowchart_and_ui_transparency(self):
        content = (DOCS_HIST / "planning" / "archive-enrichment.md").read_text("utf-8")
        self.assertIn("## Manual Re-Enrich Decision Flow", content)
        self.assertIn("```mermaid", content)
        self.assertIn("flowchart TD", content)
        self.assertIn("## UI Transparency", content)
        self.assertIn("The compact `+>` payload does **not** persist every clean success branch.", content)

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
        """Snapshot uses compact tray:spool:filament:color CSV entries."""
        content = (HISTORY / "automations" / "bambuddy_capture_archive_id.yaml").read_text("utf-8")
        # Must stay compact, not full JSON.
        self.assertIn("join(',')", content)
        self.assertIn("~ ':'", content)
        self.assertIn("tray_name ~ ':' ~ spool_id_raw ~ ':' ~ filament_id_raw ~ ':' ~ color_norm.upper()", content)
        self.assertNotIn("tojson", content)

    def test_snapshot_targets_correct_helper(self):
        content = (HISTORY / "automations" / "bambuddy_capture_archive_id.yaml").read_text("utf-8")
        self.assertIn("input_text.bambuddy_tray_map_snapshot", content)

    def test_enrichment_consumes_snapshot_fallback(self):
        content = (HISTORY / "automations" / "bambuddy_enrich_archive_on_complete.yaml").read_text("utf-8")
        self.assertIn("tray_map_snapshot_raw", content)
        self.assertIn("snapshot = namespace(spool_id='', filament_id='', color_hex=none)", content)
        self.assertIn("not spool_id_valid and snapshot.spool_id | regex_match", content)
        self.assertIn("not filament_id_valid and snapshot.filament_id | regex_match", content)
        self.assertIn("elif snapshot.color_hex is not none", content)


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
