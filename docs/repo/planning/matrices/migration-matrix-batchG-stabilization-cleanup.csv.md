# Batch G Detailed Matrix: stabilization_cleanup

Source scope: whole-repo active docs stabilization (link audits, pointer cleanup, final index pass)
Row count: 7

Post-cleanup interpretation note (2026-05-23):
1. current_path is an audit/remediation source field for stabilization actions.
2. target_path is the canonical active destination after cleanup.

Label alignment: this detailed matrix maps to owner-area G (stabilization and cleanup) in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/infrastructure/dev-home-assistant-bambuddy-strategy.md,stabilization_cleanup,pointer-cleanup,Active,docs/infrastructure/design/dev-home-assistant-bambuddy-strategy.md,No,Removed duplicate root file; canonical design-lane copy retained
docs/repo/reference/deployment-workflow-reference.md,stabilization_cleanup,reference-fix,Active,docs/repo/reference/deployment-workflow-reference.md,No,Fixed related-doc links to active files
docs/features/model_catalog/planning/external-competitive-backlog.md,stabilization_cleanup,planning-link-fix,Active,docs/features/model_catalog/planning/external-competitive-backlog.md,No,Corrected malformed self-referential links
docs/features/model_catalog/planning/external-alternatives-review.md,stabilization_cleanup,planning-link-fix,Active,docs/features/model_catalog/planning/external-alternatives-review.md,No,Removed duplicate stale path and kept canonical relative link
docs/features/model_catalog/planning/external-competitor-review.md,stabilization_cleanup,planning-link-fix,Active,docs/features/model_catalog/planning/external-competitor-review.md,No,Corrected tmp/sidecar/homeassistant relative links
docs/features/model_catalog/planning/index.md,stabilization_cleanup,planning-link-fix,Active,docs/features/model_catalog/planning/index.md,No,Fixed related-doc links and removed broken CODEOWNERS link
repo-wide active docs link sweep,stabilization_cleanup,validation,Active,repo-wide active docs link sweep,No,Verified targeted stale/broken path patterns cleared in active non-archive docs
