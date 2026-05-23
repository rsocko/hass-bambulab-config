# Batch D Detailed Matrix: docs_root_spillover

Source scope: docs/*.md (excluding docs/README.md)
Row count: 10

Post-cleanup interpretation note (2026-05-23):
1. `current_path` is a migration-source field and may reference paths removed by lane migration cleanup.
2. `target_path` is the canonical destination for active docs.

Label alignment: this detailed matrix maps to owner-area `D` (docs root spillover files) in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/CATALOG-REDESIGN-2026-05-UPDATES.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/design/catalog-redesign-2026-05-updates.md,Yes,Model catalog design updates
docs/MODEL_CATALOG_ARCHITECTURE.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/reference/model-catalog-sidecar-architecture.md,Yes,Model catalog architecture reference
docs/MODEL_CATALOG_MIGRATION_GUIDE.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/reference/model-catalog-migration-guide.md,Yes,Migration guidance
docs/MODEL_CATALOG_PHASE_2_DESIGN.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/planning/model-catalog-phase-2-design.md,Yes,Phase 2 design plan
docs/MODEL_CATALOG_PHASE_2_COMPLETION_REVIEW.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/archive/model-catalog-phase-2-completion-review.md,Yes,Historical completion review
docs/MODEL_CATALOG_PHASE_2_COMPLETION_STATUS.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/archive/model-catalog-phase-2-completion-status.md,Yes,Historical completion status
docs/PHASE-2.1-INTAKE-DECOMPOSITION-COMPLETE.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/archive/phase-2.1-intake-decomposition-complete.md,Yes,Historical phase milestone
docs/PHASE_1_COMPLETION_SUMMARY.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/archive/phase-1-completion-summary.md,Yes,Historical phase summary
docs/PHASE_2_GITHUB_ISSUES_TEMPLATE.md,docs_root_spillover,feature-relocation,Active,docs/features/model_catalog/planning/phase-2-github-issues-template.md,Yes,Planning issue template
docs/I’m extracting the full per-archive `t_h.md,docs_root_spillover,archive,Active,docs/archive/root-history/model-catalog-root-fragment-t_h.md,Yes,Malformed root file name quarantined to archive
