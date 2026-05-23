# Batch 2 Detailed Matrix: air_quality

Source scope: docs/features/air_quality/*.md
Row count: 13

Label alignment: this detailed matrix maps to global `C2` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/air_quality/README.md,air_quality,root-readme,Active,docs/features/air_quality/README.md,No,Primary entry point
docs/features/air_quality/air-quality-cards-visual-reference.md,air_quality,reference,Active,docs/features/air_quality/reference/air-quality-cards-visual-reference.md,Yes,Card behavior and layout reference
docs/features/air_quality/bento-box-enhancement-summary.md,air_quality,archive,Historical,docs/features/air_quality/archive/bento-box-enhancement-summary.md,Yes,Historical implementation summary
docs/features/air_quality/bento-box-fan-filament-control.md,air_quality,reference,Active,docs/features/air_quality/reference/bento-box-fan-filament-control.md,Yes,Filament-aware control logic reference
docs/features/air_quality/bento-box-fan-quick-config.md,air_quality,reference,Active,docs/features/air_quality/reference/bento-box-fan-quick-config.md,Yes,Quick configuration runbook
docs/features/air_quality/bento-box-filter-tracking.md,air_quality,reference,Active,docs/features/air_quality/reference/bento-box-filter-tracking.md,Yes,Filter tracking behavior and maintenance guide
docs/features/air_quality/configuration-examples.md,air_quality,reference,Active,docs/features/air_quality/reference/configuration-examples.md,Yes,Concrete setup examples
docs/features/air_quality/entity-relationship-diagram.md,air_quality,design,Active,docs/features/air_quality/design/entity-relationship-diagram.md,Yes,Architecture and boundary model
docs/features/air_quality/filter-tracking-quick-setup.md,air_quality,reference,Active,docs/features/air_quality/reference/filter-tracking-quick-setup.md,Yes,Quick setup runbook for filter tracking
docs/features/air_quality/implementation-summary.md,air_quality,archive,Historical,docs/features/air_quality/archive/implementation-summary.md,Yes,Historical implementation summary
docs/features/air_quality/pr-summary.md,air_quality,archive,Historical,docs/features/air_quality/archive/pr-summary.md,Yes,Pull request summary and delivery snapshot
docs/features/air_quality/quick-setup.md,air_quality,reference,Active,docs/features/air_quality/reference/quick-setup.md,Yes,Primary operator quick-start guide
docs/features/air_quality/visual-preview.md,air_quality,reference,Active,docs/features/air_quality/reference/visual-preview.md,Yes,UI preview and expected visual states
