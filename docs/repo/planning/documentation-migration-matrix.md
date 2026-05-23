# Documentation Migration Matrix

Status: Planned
Last Reviewed: 2026-05-23
Functional Owner: repo-docs
Replaces: none
Replaced By: none

## Matrix Use
This matrix is the execution tracker for documentation reorganization.

Two levels:
1. Owner-area batch queue for whole-repo sequencing.
2. Batch 1 row-per-document matrices for immediate execution.

## Matrix A: Owner-Area Batch Queue

| Batch | Owner Area | Complexity | Scope | Primary Actions | Depends On |
|---|---|---|---|---|---|
| A | docs global navigation and policy | High | docs/README.md, root nav | Establish lane policy, refresh global indexes | none |
| A | repo root navigation files | High | README.md, DELIVERABLES-INDEX.md | Align nav to lane model and migration flow | none |
| B | repo-root historical markdown | Medium | PHASE/ISSUE/test summary docs | Move historical docs into archive lanes | A |
| C1 | model_catalog | Very High | docs/features/model_catalog | Full lane split, root simplification, phase archive moves | A |
| C1 | print_history | Very High | docs/features/print_history | Preserve subdomains, enforce lifecycle placement, trim parent README | A |
| C1 | spoolman_sync | High | docs/features/spoolman_sync | Split mixed root docs into lifecycle lanes | A |
| C2 | wled | High | docs/features/wled | Hardware/reference/design separation | A |
| C2 | air_quality | High | docs/features/air_quality | README de-bloat, lane migration | A |
| C2 | printer_led | High | docs/features/printer_led | Separate runbook/design/history docs | A |
| C2 | logging | Medium | docs/features/logging | Keep integrations subtree, lane classify | A |
| C3 | filament_catalog | Medium | docs/features/filament_catalog | Formalize planning/design/reference boundaries | A |
| C3 | printer_dashboards | Medium | docs/features/printer_dashboards | Consolidate active references, archive stale docs | A |
| C3 | printer_temps | Medium | docs/features/printer_temps | Archive version snapshots, preserve active references | A |
| C3 | printer_controls | Medium | docs/features/printer_controls | Lane assignment and README reduction | A |
| C3 | error_alerts | Medium | docs/features/error_alerts | Lane assignment and historical cleanup | A |
| C3 | humidity | Medium | docs/features/humidity | Lane assignment and README reduction | A |
| C3 | print_queue | Medium | docs/features/print_queue | Move mockups to design, retain current reference docs | A |
| C4 | Small/stub feature group | Low-Med | print_progress, print_statistics, print_weight_and_cost, bambuddy_common, bambuddy_integration, core, common, api, notifications, filament_tag, power_monitoring, model_intake, openhasp_display, printer_maintenance | Minimal lane normalization and stub triage | A |
| D | repo shared docs | Medium | docs/repo | Split into reference/design/planning/archive and relocate feature-owned docs | A |
| D | infrastructure docs | Medium | docs/infrastructure | Keep active references, move dated diagnostics to archive | A |
| D | testing docs | Low | docs/testing | Keep active reference docs, archive milestone reports | A |
| D | docs root loose markdown | Medium | docs root spillover files | Move to owner lanes and triage malformed docs | A |
| E | screenshots docs | Low | docs/screenshots | Keep index/reference policy, archive stale planning docs | A |
| F | non-doc markdown policy | Medium | sidecars/tests/openhasp/wled backups/archive notes | Cross-link canonical docs and mark local vs historical | C1-C4 |
| G | stabilization and cleanup | High | whole repository | Link audits, pointer cleanup, final index pass | B-F |

## Matrix B: Batch 1 Detailed Row-Level Coverage

| Feature | Row Count | Detailed Matrix File |
|---|---:|---|
| model_catalog | 153 | docs/repo/planning/matrices/migration-matrix-batch1-model_catalog.csv.md |
| print_history | 73 | docs/repo/planning/matrices/migration-matrix-batch1-print_history.csv.md |
| spoolman_sync | 42 | docs/repo/planning/matrices/migration-matrix-batch1-spoolman_sync.csv.md |

Batch 1 total planned row-level items: 268

## Batch Execution Rules
1. Execute one owner area per PR where practical.
2. Update docs/README.md and affected feature README in same PR as moves.
3. Add compatibility pointer docs only for highly linked moved files.
4. Add metadata header to every moved/touched document.
5. Ensure archive folder README guardrail exists before moving docs into archive.
6. Remove temporary pointers when link audit confirms safe cleanup.

## Verification Checklist
1. Matrix rows exist before moves for that batch scope.
2. Root contract holds in each owner area.
3. Cross-links and indexes updated in same batch.
4. Archive is explicitly non-canonical.
5. No duplicated canonical API/contract docs remain active.
