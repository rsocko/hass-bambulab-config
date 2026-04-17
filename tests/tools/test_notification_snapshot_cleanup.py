from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NOTIFICATIONS = ROOT / "homeassistant" / "packages" / "3d_printing" / "notifications"


class TestNotificationSnapshotCleanup(unittest.TestCase):
    def test_notifications_loader_includes_shell_commands(self):
        content = (NOTIFICATIONS / "notifications_loader.yaml").read_text("utf-8")
        self.assertIn("shell_command: !include_dir_merge_named shell_commands", content)

    def test_cleanup_shell_command_targets_local_snapshot_directory(self):
        content = (NOTIFICATIONS / "shell_commands" / "cleanup_printer_snapshots.yaml").read_text("utf-8")
        self.assertIn("/config/www/printer_snapshots", content)
        self.assertIn("retention_days", content)
        self.assertIn("max_files", content)
        self.assertIn("path.unlink", content)

    def test_cleanup_automation_runs_periodically(self):
        content = (NOTIFICATIONS / "automations" / "snapshot_retention_cleanup.yaml").read_text("utf-8")
        self.assertIn('at: "03:30:00"', content)
        self.assertIn("event: start", content)
        self.assertIn("shell_command.cleanup_printer_snapshots", content)

    def test_snapshot_producing_notifications_trigger_cleanup(self):
        complete = (NOTIFICATIONS / "automations" / "print_complete_notification.yaml").read_text("utf-8")
        errors = (NOTIFICATIONS / "automations" / "error_alert_notification.yaml").read_text("utf-8")
        self.assertIn("shell_command.cleanup_printer_snapshots", complete)
        self.assertIn("shell_command.cleanup_printer_snapshots", errors)

    def test_retention_helpers_exist(self):
        retention_days = (NOTIFICATIONS / "helpers" / "input_number" / "input_number_3dprinter_snapshot_retention_days.yaml").read_text("utf-8")
        keep_max = (NOTIFICATIONS / "helpers" / "input_number" / "input_number_3dprinter_snapshot_keep_max.yaml").read_text("utf-8")
        self.assertIn("initial: 7", retention_days)
        self.assertIn("initial: 150", keep_max)


if __name__ == "__main__":
    unittest.main()