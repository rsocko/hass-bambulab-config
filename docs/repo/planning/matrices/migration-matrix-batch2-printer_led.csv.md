# Batch 2 Detailed Matrix: printer_led

Source scope: docs/features/printer_led/*.md
Row count: 12

Label alignment: this detailed matrix maps to global `C2` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/printer_led/README.md,printer_led,root-readme,Active,docs/features/printer_led/README.md,No,Primary entry point
docs/features/printer_led/AUTOMATIONS.md,printer_led,reference,Active,docs/features/printer_led/reference/automations.md,Yes,Operator guide for optional automations
docs/features/printer_led/customization-examples.md,printer_led,reference,Active,docs/features/printer_led/reference/customization-examples.md,Yes,Advanced customization examples
docs/features/printer_led/esp32-integration.md,printer_led,reference,Active,docs/features/printer_led/reference/esp32-integration.md,Yes,ESPHome and touchscreen integration guide
docs/features/printer_led/implementation-summary.md,printer_led,archive,Historical,docs/features/printer_led/archive/interior-light-reset-implementation-summary.md,Yes,Historical delivery summary
docs/features/printer_led/led-controls.md,printer_led,reference,Active,docs/features/printer_led/reference/led-controls/overview.md,Yes,Canonical expanded controls documentation
docs/features/printer_led/led-controls-implementation-summary.md,printer_led,archive,Historical,docs/features/printer_led/archive/led-controls-implementation-summary.md,Yes,Historical delivery summary
docs/features/printer_led/led-controls-integration-examples.md,printer_led,reference,Active,docs/features/printer_led/reference/led-controls/integration-examples.md,Yes,Dashboard integration patterns
docs/features/printer_led/led-controls-readme.md,printer_led,reference,Active,docs/features/printer_led/reference/led-controls/quick-start.md,Yes,Quick start for expanded controls
docs/features/printer_led/led-controls-visual.md,printer_led,reference,Active,docs/features/printer_led/reference/led-controls/visual-reference.md,Yes,Visual behavior reference
docs/features/printer_led/physical-button-integration.md,printer_led,reference,Active,docs/features/printer_led/reference/physical-button-integration.md,Yes,Hardware button integration guide
docs/features/printer_led/visual-examples.md,printer_led,design,Active,docs/features/printer_led/design/visual-examples.md,Yes,Conceptual layout mockups and examples
