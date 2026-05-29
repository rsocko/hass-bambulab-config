# Dashboard/View Strategy Modularization Guide

Status: Draft
Last Reviewed: 2026-05-29
Owner: printer_dashboards

## Purpose

This guide describes how to adopt Home Assistant custom dashboard strategies with dashboard + view separation in this repo, without breaking the current Lovelace resource deployment contract.

Primary goals:

1. Improve modularity and separation of concerns across dashboard features.
2. Reduce first-load work by moving heavy view generation behind per-view strategy boundaries.
3. Keep existing deploy/restart/cache-bust safety behavior intact.

Primary non-goals:

1. Replacing `_resources.yaml` workflow contracts.
2. Migrating all views at once.
3. Rewriting existing custom cards during strategy introduction.

## Baseline: Current Dashboard Architecture

Current dashboard composition:

- Dashboard registration: `homeassistant/packages/3d_printing/common/dashboards/_dashboards.yaml`
- Root dashboard YAML: `homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml`
- View include chain: feature-level `dashboard_views/*.yaml`

Current resource/deploy contract (must remain):

- Source-of-truth manifest: `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`
- Cache-bust/version guard: `.github/scripts/check_lovelace_resource_versions.py`
- Storage reconciliation: `.github/scripts/sync_lovelace_resources.sh`
- Workflow enforcement and restart checks: `.github/workflows/deploy-homeassistant-template.yml`

See also:

- `docs/repo/reference/dashboard-deployment-behavior.md`
- `docs/repo/reference/deployment-workflow-reference.md`

## What Dashboard + View Separation Changes

### Dashboard strategy responsibilities

A dashboard strategy should only do top-level work:

1. Name/icon suggestions.
2. View list creation (title/path/icon/strategy pointer).
3. Optional global options to pass into view strategies.

### View strategy responsibilities

A view strategy should do per-page composition:

1. Build that view's card tree.
2. Resolve per-view defaults.
3. Optionally fetch only data needed by that view.

### What does NOT change

1. Custom JS resources still need registration as Lovelace resources.
2. `_resources.yaml` still needs version bumps when tracked JS changes.
3. Existing cache-bust guard and resource sync pipeline still applies.

## Conversion Scope by Current View

Measured from current YAML footprint (direct + transitive `!include` surface):

| Current view | Direct lines | Direct includes | Transitive include files | Transitive include lines | Complexity | Strategy conversion effort |
|---|---:|---:|---:|---:|---|---|
| `common/dashboard_views/view_main.yaml` | 485 | 15 | 24 | 4678 | Very High | High (3-5 weeks)
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | 199 | 4 | 13 | 1818 | High | High (2-4 weeks)
| `print_history/dashboard_views/view_print_history.yaml` | 36 | 6 | 6 | 1744 | High (wrapper over heavy cards) | Medium-High (2-3 weeks)
| `common/dashboard_views/view_filament_tags.yaml` | 510 | 1 | 1 | 611 | Medium-High | Medium (1-2 weeks)
| `model_catalog/dashboard_views/view_model_catalog.yaml` | 547 | 0 | 0 | 0 | Medium-High (single large view file) | Medium (1-2 weeks)
| `print_statistics/dashboard_views/view_print_statistics.yaml` | 14 | 2 | 9 | 423 | Medium | Medium (4-7 days)
| `common/dashboard_views/view_deploy_validation.yaml` | 194 | 0 | 0 | 0 | Low-Medium | Low (2-4 days)
| `print_queue/dashboard_views/print_queue_board.yaml` | 23 | 0 | 0 | 0 | Low | Low (1-2 days)

Notes:

- `print_history` looks small at the top-level view file, but it is include-heavy and backed by JS-heavy cards.
- `model_catalog` is include-light but internally large and style-dense in one file.

## Conversion Scope by Feature

| Feature | Primary view(s) | Existing shape | Recommended strategy target | Effort | Risk |
|---|---|---|---|---|---|
| Common shell | `3d_printing.yaml` + dashboard registration | Dashboard + view includes | New dashboard strategy shell only | Low | Low |
| Main dashboard feature aggregation | `view_main.yaml` | Many includes across features | Keep YAML first; defer strategy conversion | High | High |
| Model catalog | `view_model_catalog.yaml` + JS cards | JS-heavy with complex navigation controls | Good first heavy view-strategy candidate | Medium | Medium |
| Print history | `view_print_history.yaml` + heavy card includes | Wrapper over multiple custom cards | Strong view-strategy candidate after model catalog | Medium-High | Medium |
| Filament catalog | `view_filament_catalog.yaml` + templated auto-entities | Complex templating and responsive behavior | Later-phase conversion | High | High |
| Print statistics | `view_print_statistics.yaml` | Mostly include-driven | Good low-risk strategy pilot | Medium | Low-Medium |
| Print queue | `print_queue_board.yaml` | Small and isolated | Good low-risk strategy pilot | Low | Low |
| Deploy validation | `view_deploy_validation.yaml` | Isolated operational view | Optional low-risk pilot | Low | Low |

## Recommended Migration Sequence

### Phase 0: Prepare strategy scaffolding (no behavior change)

1. Add a strategy module resource for dashboard shell + one pilot view strategy.
2. Keep current dashboard YAML as production path.
3. Add docs and rollback instructions.

Deliverables:

- New strategy JS file(s) under `homeassistant/www/3d_printing/...`.
- Resource entry in `_resources.yaml` with `?v=`.

### Phase 1: Introduce dashboard strategy shell only

1. Dashboard strategy returns same view list currently defined in `3d_printing.yaml`.
2. Keep all current view YAML files unchanged.
3. Validate no deploy contract regressions.

Why this first:

- High learning value.
- Minimal blast radius.
- No forced conversion of existing feature cards.

### Phase 2: Convert one low-risk view strategy

Preferred order:

1. `print_queue`
2. `view_deploy_validation`
3. `print_statistics`

Success criteria:

- No change to resource sync/cache-bust behavior.
- No restart/reload workflow regressions.
- No UI regressions on mobile/desktop.

### Phase 3: Convert one heavy JS-backed view

Preferred order:

1. `model_catalog`
2. `print_history`

Approach:

- Preserve existing custom card usage.
- Only move page composition/orchestration to view strategy.
- Keep card internals in existing JS modules.

### Phase 4: Re-evaluate high-complexity views

Candidates:

- `view_main`
- `view_filament_catalog`

Decision gate:

- Convert only if measurable gains justify churn (maintainability, startup latency, repeated composition logic).

## Suggested File Layout for Strategies

A practical layout that matches current package organization:

- `homeassistant/www/3d_printing/strategies/3d-printing-dashboard-strategy.js`
- `homeassistant/www/3d_printing/strategies/views/model-catalog-view-strategy.js`
- `homeassistant/www/3d_printing/strategies/views/print-history-view-strategy.js`
- `homeassistant/www/3d_printing/strategies/views/print-queue-view-strategy.js`
- `homeassistant/www/3d_printing/strategies/views/print-statistics-view-strategy.js`

Guideline:

- Keep strategy files orchestration-only.
- Keep heavy UI/logic in existing card modules.

## Deployment and Cache-Bust Rules During Migration

These rules stay unchanged:

1. Any tracked JS edit under `homeassistant/www/**` requires matching `?v=` bump chain.
2. `_resources.yaml` remains repo source of truth.
3. Deploy workflow checks and reconciles resources in HA storage.
4. Recommend hard refresh after JS resource updates.

Operationally, strategy adoption is additive to existing contracts, not a replacement.

## Testing Requirements Per Converted View

Minimum acceptance checklist:

1. Resource URL added/bumped in `_resources.yaml`.
2. `check_lovelace_resource_versions.py` passes.
3. `sync_lovelace_resources.sh --dry-run --strict` shows no drift after deploy.
4. Desktop + mobile layout parity validated.
5. Existing automations/helpers/entities referenced by the view still resolve.
6. Hard-refresh behavior documented for release notes.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Partial migration creates dual maintenance burden | Medium | Migrate complete views, not mixed partial fragments |
| Hidden dependency on include ordering | Medium | Convert one view at a time with visual diff checklist |
| Breaks deploy cache-bust contract | High | Preserve `_resources.yaml` + CI checks unchanged |
| Over-centralized strategy file becomes monolith | Medium | Enforce one view strategy file per feature/view |
| Performance does not improve materially | Medium | Gate each conversion with before/after load metrics |

## Recommended First Two Implementations

1. Dashboard shell strategy + `print_queue` view strategy (low risk, fast feedback).
2. `model_catalog` view strategy (high-value heavy surface, moderate risk).

This sequence gives:

- quick validation of strategy wiring,
- measurable modularity gains,
- minimal disruption to deploy contracts.

## Estimated Total Program Effort

Two realistic tracks:

1. Conservative (recommended): 5-8 weeks
   - Shell + 3-4 view conversions
   - Keep highest complexity views (`view_main`, filament catalog) as YAML for now

2. Aggressive full conversion: 10-16 weeks
   - All 8 views + stabilization
   - Higher regression and maintenance risk during transition

## Decision Summary

Recommended now:

1. Adopt dashboard strategy shell.
2. Convert low-risk and one high-value heavy view.
3. Keep current resource/deploy/caching contracts unchanged.
4. Reassess full conversion only after measured gains are proven.
