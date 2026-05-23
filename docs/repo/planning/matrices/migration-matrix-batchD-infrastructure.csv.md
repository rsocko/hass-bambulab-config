# Batch D Detailed Matrix: infrastructure_docs

Source scope: docs/infrastructure/*.md
Row count: 5

Post-cleanup interpretation note (2026-05-23):
1. `current_path` is a migration-source field and may reference paths removed by lane migration cleanup.
2. `target_path` is the canonical destination for active docs.

Label alignment: this detailed matrix maps to owner-area `D` (infrastructure docs) in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/infrastructure/github-runner-README.md,infrastructure_docs,reference,Active,docs/infrastructure/reference/github-runner-README.md,Yes,Runner setup and deployment reference
docs/infrastructure/gh-actions-dashboard.md,infrastructure_docs,reference,Active,docs/infrastructure/reference/gh-actions-dashboard.md,Yes,Dashboard tooling reference
docs/infrastructure/dev-home-assistant-bambuddy-strategy.md,infrastructure_docs,design,Active,docs/infrastructure/design/dev-home-assistant-bambuddy-strategy.md,Yes,Environment strategy and architecture
docs/infrastructure/ha-error-assessment-2026-03-16.md,infrastructure_docs,archive,Active,docs/infrastructure/archive/diagnostics/ha-error-assessment-2026-03-16.md,Yes,Dated diagnostic assessment
docs/infrastructure/ha-restart-diagnosis-2026-04-13.md,infrastructure_docs,archive,Active,docs/infrastructure/archive/diagnostics/ha-restart-diagnosis-2026-04-13.md,Yes,Dated restart diagnosis
