# Batch 2 Detailed Matrix: wled

Source scope: docs/features/wled/*.md
Row count: 21

Label alignment: this detailed matrix maps to global `C2` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/wled/README.md,wled,root-readme,Active,docs/features/wled/README.md,No,Primary entry point
docs/features/wled/backup-and-restore.md,wled,reference,Active,docs/features/wled/reference/backup-and-restore.md,Yes,Operational backup and restore runbook
docs/features/wled/controller-allocation.md,wled,reference,Active,docs/features/wled/reference/controller-allocation.md,Yes,Controller allocation recommendation
docs/features/wled/digquad-led-segments.md,wled,reference,Active,docs/features/wled/reference/digquad-led-segments.md,Yes,Physical segment and GPIO mapping
docs/features/wled/ha-automation-preset-based.md,wled,design,Active,docs/features/wled/design/preset-based-automation-examples.md,Yes,Future preset-based automation design
docs/features/wled/hardware-constraint.md,wled,reference,Active,docs/features/wled/reference/hardware-constraint.md,Yes,Hardware capacity constraints
docs/features/wled/ha-state-machine-package.md,wled,reference,Active,docs/features/wled/reference/ha-state-machine-package.md,Yes,Canonical HA state machine package contract
docs/features/wled/home-assistant-automations.md,wled,archive,Historical,docs/features/wled/archive/home-assistant-automations-legacy.md,Yes,Legacy automation examples pre-state-machine
docs/features/wled/INDEX.md,wled,planning,Active,docs/features/wled/planning/index.md,Yes,Feature documentation index
docs/features/wled/light-scenarios.md,wled,design,Active,docs/features/wled/design/light-scenarios.md,Yes,Scenario catalog and target behavior design
docs/features/wled/phased-implementation-guide.md,wled,planning,Active,docs/features/wled/planning/phased-implementation-guide.md,Yes,Phased rollout plan
docs/features/wled/preset-based-segments.md,wled,design,Active,docs/features/wled/design/preset-based-segments.md,Yes,Preset-based segmentation design
docs/features/wled/preset-based-visual-guide.md,wled,design,Active,docs/features/wled/design/preset-based-visual-guide.md,Yes,Visual design guide for preset-based approach
docs/features/wled/preset-specification.md,wled,archive,Historical,docs/features/wled/archive/preset-specification-legacy.md,Yes,Legacy preset specification not deployed
docs/features/wled/quick-reference.md,wled,reference,Active,docs/features/wled/reference/quick-reference.md,Yes,Current architecture quick reference
docs/features/wled/quick-start.md,wled,reference,Active,docs/features/wled/reference/quick-start-legacy.md,Yes,Legacy quick-start setup guide
docs/features/wled/quick-start-preset-based.md,wled,planning,Active,docs/features/wled/planning/quick-start-preset-based.md,Yes,Phase-3 quick-start planning guide
docs/features/wled/segment-reference.md,wled,reference,Active,docs/features/wled/reference/segment-reference.md,Yes,Segment allocation quick reference
docs/features/wled/summary.md,wled,archive,Historical,docs/features/wled/archive/summary-2026-03-13.md,Yes,Dated status snapshot
docs/features/wled/visual-installation-guide.md,wled,reference,Active,docs/features/wled/reference/visual-installation-guide.md,Yes,Visual installation/runbook reference
docs/features/wled/wiring-diagram.md,wled,reference,Active,docs/features/wled/reference/wiring-diagram.md,Yes,Wiring and configuration reference
