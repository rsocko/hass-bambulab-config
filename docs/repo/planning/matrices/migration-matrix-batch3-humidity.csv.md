# Batch 3 Detailed Matrix: humidity

Source scope: docs/features/humidity/**/*.md
Row count: 4

Label alignment: this detailed matrix maps to global `C3` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/humidity/README.md,humidity,root-readme,Active,docs/features/humidity/README.md,No,Primary feature entrypoint
docs/features/humidity/quick-start.md,humidity,reference,Active,docs/features/humidity/reference/quick-start.md,Yes,Operator quick-start guide
docs/features/humidity/visual-guide.md,humidity,design,Active,docs/features/humidity/design/visual-guide.md,Yes,Visual layout and interaction design guide
docs/features/humidity/implementation-summary.md,humidity,archive,Historical,docs/features/humidity/archive/implementation-summary.md,Yes,Historical implementation delivery summary
