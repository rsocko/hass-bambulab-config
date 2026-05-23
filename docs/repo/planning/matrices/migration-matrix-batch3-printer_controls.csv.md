# Batch 3 Detailed Matrix: printer_controls

Source scope: docs/features/printer_controls/**/*.md
Row count: 6

Label alignment: this detailed matrix maps to global `C3` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/printer_controls/README.md,printer_controls,root-readme,Active,docs/features/printer_controls/README.md,No,Primary feature entrypoint
docs/features/printer_controls/fan-controls.md,printer_controls,reference,Active,docs/features/printer_controls/reference/fan-controls.md,Yes,Fan control behavior and setup
docs/features/printer_controls/fan-controls-visual.md,printer_controls,design,Active,docs/features/printer_controls/design/fan-controls-visual.md,Yes,Visual states and responsive layout
docs/features/printer_controls/skip-objects.md,printer_controls,reference,Active,docs/features/printer_controls/reference/skip-objects.md,Yes,Skip-objects behavior and implementation guide
docs/features/printer_controls/printer-status-card-features.md,printer_controls,reference,Active,docs/features/printer_controls/reference/printer-status-card-features.md,Yes,Print status card capability research
docs/features/printer_controls/skip-objects-integration-options.md,printer_controls,planning,Active,docs/features/printer_controls/planning/skip-objects-integration-options.md,Yes,Integration option analysis and rollout guidance
