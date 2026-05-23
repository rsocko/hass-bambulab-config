# Batch 3 Detailed Matrix: error_alerts

Source scope: docs/features/error_alerts/**/*.md
Row count: 5

Label alignment: this detailed matrix maps to global `C3` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/error_alerts/README.md,error_alerts,root-readme,Active,docs/features/error_alerts/README.md,No,Primary feature entrypoint
docs/features/error_alerts/error-alerts-unified-design.md,error_alerts,design,Active,docs/features/error_alerts/design/error-alerts-unified-design.md,Yes,Unified architecture and phased design
docs/features/error_alerts/hms-error-ui-mockup.md,error_alerts,design,Active,docs/features/error_alerts/design/hms-error-ui-mockup.md,Yes,Visual behavior and layout guide
docs/features/error_alerts/hms-error-alert-implementation.md,error_alerts,reference,Active,docs/features/error_alerts/reference/hms-error-alert-implementation.md,Yes,Technical implementation details
docs/features/error_alerts/hms-error-testing-guide.md,error_alerts,reference,Active,docs/features/error_alerts/reference/hms-error-testing-guide.md,Yes,Test procedures and troubleshooting
