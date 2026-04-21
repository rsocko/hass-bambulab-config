"""
Print Statistics — Package Validation Tests
===========================================

Validates the structural integrity and wiring of the print_statistics package.
"""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "homeassistant" / "packages" / "3d_printing"
STATS = PACKAGES / "print_statistics"
LOADERS = PACKAGES / "_feature_loaders.yaml"
DASHBOARD = PACKAGES / "common" / "dashboards" / "3d_printing.yaml"
RESOURCES = PACKAGES / "common" / "dashboards" / "_resources.yaml"
WWW_STATS = ROOT / "homeassistant" / "www" / "3d_printing" / "print_statistics"


def _load_yaml_safe(path: Path):
    class _SafeLoader(yaml.SafeLoader):
        pass

    def _include_stub(loader, node):
        return f"__include__{loader.construct_scalar(node)}"

    for tag in (
        "!include",
        "!include_dir_merge_list",
        "!include_dir_merge_named",
        "!include_dir_named",
        "!include_dir_list",
        "!secret",
    ):
        _SafeLoader.add_constructor(tag, _include_stub)

    with open(path, "r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=_SafeLoader)


class TestPrintStatisticsPackage(unittest.TestCase):
    def test_feature_loader_references_print_statistics(self):
        content = LOADERS.read_text(encoding="utf-8")
        self.assertIn("print_statistics_loader", content)

    def test_dashboard_includes_statistics_view(self):
        content = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("view_print_statistics.yaml", content)

    def test_loader_domains(self):
        data = _load_yaml_safe(STATS / "print_statistics_loader.yaml")
        self.assertIsInstance(data, dict)
        self.assertTrue({"automation", "sensor", "template", "recorder"}.issubset(data.keys()))

    def test_loader_include_dirs_exist(self):
        content = (STATS / "print_statistics_loader.yaml").read_text(encoding="utf-8")
        dirs = re.findall(r"!include_dir_\w+\s+(\S+)", content)
        for directory in dirs:
            with self.subTest(directory=directory):
                self.assertTrue((STATS / directory).exists())

    def test_expected_files_exist(self):
        expected = [
            STATS / "automations" / "bambuddy_event_stats_refresh.yaml",
            STATS / "rest_sensors" / "bambuddy_statistics_sensor.yaml",
            STATS / "template_sensors" / "bambuddy_statistics_derived.yaml",
            STATS / "dashboard_cards" / "statistics_overview.yaml",
            STATS / "dashboard_cards" / "statistics_insights.yaml",
            STATS / "dashboard_cards" / "insights" / "chart_prints_by_filament_type.yaml",
            STATS / "dashboard_cards" / "insights" / "chart_prints_by_printer.yaml",
            STATS / "dashboard_cards" / "insights" / "chart_failure_reasons.yaml",
            STATS / "dashboard_cards" / "insights" / "chart_failure_rate_trend.yaml",
            STATS / "dashboard_cards" / "insights" / "chart_failures_by_filament_type.yaml",
            STATS / "dashboard_cards" / "insights" / "failure_recent_summary.yaml",
            STATS / "dashboard_cards" / "insights" / "chart_time_accuracy_by_printer.yaml",
            STATS / "dashboard_views" / "view_print_statistics.yaml",
            WWW_STATS / "print-statistics-failure-analysis-card.js",
        ]
        for path in expected:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.exists())

    def test_all_yaml_files_parse(self):
        for path in sorted(STATS.rglob("*.yaml")):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNotNone(_load_yaml_safe(path))

    def test_failure_analysis_sensor_uses_current_bambuddy_contract(self):
        content = (STATS / "rest_sensors" / "bambuddy_statistics_sensor.yaml").read_text(encoding="utf-8")
        self.assertIn("{{ value_json.failure_rate | default(0) | float(0) | round(1) }}", content)
        self.assertIn("- recent_failures", content)
        self.assertIn("- trend", content)
        self.assertIn("- period_days", content)
        self.assertNotIn("weekly_trend", content)
        self.assertNotIn("* 100", content)

    def test_failure_analysis_metrics_passthrough_exists(self):
        content = (STATS / "template_sensors" / "bambuddy_statistics_derived.yaml").read_text(encoding="utf-8")
        self.assertIn("failures_by_filament_json", content)
        self.assertIn("failures_by_printer_json", content)
        self.assertIn("failure_trend_json", content)
        self.assertIn("recent_failures_json", content)
        self.assertIn("state_attr('sensor.bambuddy_failure_analysis', 'failures_by_filament')", content)
        self.assertIn("state_attr('sensor.bambuddy_failure_analysis', 'failures_by_printer')", content)
        self.assertIn("state_attr('sensor.bambuddy_failure_analysis', 'trend')", content)
        self.assertIn("state_attr('sensor.bambuddy_failure_analysis', 'recent_failures')", content)

    def test_failure_trend_chart_exists(self):
        content = (STATS / "dashboard_cards" / "insights" / "chart_failure_rate_trend.yaml").read_text(encoding="utf-8")
        self.assertIn("custom:apexcharts-card", content)
        self.assertIn("entity?.attributes?.trend", content)
        self.assertIn("Failure Rate Trend", content)

    def test_statistics_overview_includes_failure_handoff_card(self):
        content = (STATS / "dashboard_cards" / "statistics_overview.yaml").read_text(encoding="utf-8")
        self.assertIn("custom:print-statistics-failure-analysis-card", content)
        self.assertIn("default_days: 30", content)

    def test_failure_handoff_card_resource_is_registered(self):
        content = RESOURCES.read_text(encoding="utf-8")
        self.assertIn("/local/3d_printing/print_statistics/print-statistics-failure-analysis-card.js?v=1", content)

    def test_failure_handoff_card_uses_query_params_and_websocket(self):
        content = (WWW_STATS / "print-statistics-failure-analysis-card.js").read_text(encoding="utf-8")
        self.assertIn('new URLSearchParams(window.location.search)', content)
        self.assertIn('type: "bambuddy/failure_analysis_query"', content)
        self.assertIn('printer_id', content)
        self.assertIn('project_id', content)


if __name__ == "__main__":
    unittest.main()