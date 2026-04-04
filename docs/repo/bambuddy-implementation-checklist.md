# Bambuddy Implementation Checklist

Purpose: provide one repo-level checklist that separates what is already built, what is partially built, and what still needs implementation across the Bambuddy feature split.

Canonical sources:

- design: `docs/repo/` and `docs/features/`
- implementation: `homeassistant/packages/3d_printing/`
- legacy prototype only: root `bambuddy/` and superseded `bambuddy_integration`

## Current State Summary

### Built now

- [x] `bambuddy_common` shared helpers, webhook receiver, and printer refresh command
- [x] `print_history` loader, archive browser, paging/filter state, and enrichment flow
- [x] local photo capture in `print_history`
- [x] first-phase multipart photo upload bridge via `shell_command`
- [x] read-only archive detail popup for `print_history` cards
- [x] repo/docs alignment that treats root `bambuddy/` as legacy prototype only

### Partially built

- [ ] `print_history` upload hardening
  Current state: Python-based shell bridge plus archive-detail verification exists, but richer per-photo metadata and retries do not.
- [ ] `print_history` photo review UX
  Current state: status chip exists, but popup/actions are not implemented.
- [ ] `print_history` archive detail actions
  Current state: favorites are toggleable from both the cards and popup, popup-backed `print_name` / `tags` / `notes` / `status` / `failure_reason` edits are implemented, and manual re-enrich is available. Compare and richer follow-on actions are not yet implemented.
- [ ] `print_history` manual re-enrich hardening
  Current state: popup-triggered re-enrich exists, already compares archive-slot vs AMS-tray candidates, preserves richer existing payloads, and surfaces duplicate `type + color` ambiguity. Remaining work is UUID-first matching and UX polish.
- [ ] cleanup of superseded Bambuddy artifacts
  Current state: docs are now mostly redirect/stub oriented, but legacy package/code remains in repo.

### Not built yet

- [ ] `print_queue` feature package implementation
- [ ] `print_statistics` feature package implementation
- [ ] `printer_maintenance` feature package implementation
- [ ] external Python upload worker
- [ ] archive-detail workflows such as compare and richer deep links

## Package Checklist

### Phase 1: bambuddy_common

- [x] Active package under `homeassistant/packages/3d_printing/bambuddy_common/`
- [x] Feature doc under `docs/features/bambuddy_common/README.md`
- [x] Loader registered in `_feature_loaders.yaml`
- [x] API key handled via `!secret bambuddy_api_key`

### Phase 2: print_history

- [x] Active package under `homeassistant/packages/3d_printing/print_history/`
- [x] Feature doc under `docs/features/print_history/README.md`
- [x] Archive browser/dashboard shipped
- [x] Archive enrichment shipped in initial form
- [x] Local snapshot capture shipped
- [x] Shell-based multipart upload bridge shipped
- [x] Archive-detail verification for photo uploads
- [x] Read-only archive detail popup shipped
- [ ] Archive detail compare actions and richer deep links
- [ ] Extend enrichment beyond the shipped `[HA_ENRICHMENT_V1]` payload toward richer provenance and optional native archive-status integration
- [ ] Upgrade enrichment resolution toward the UUID-first design without requiring sidecar storage
- [ ] Ship manual re-enrich matching contract against archive `filament_slots[]` plus archived `ams[].tray[]`
- [ ] Ship duplicate `type + color` ambiguity handling so re-enrich refuses guessed spool IDs and surfaces operator review instead
- [ ] Add payload/status coverage for `complete`, `partial`, and ambiguous re-enrich outcomes
- [ ] Rich per-photo upload metadata and retries
- [ ] Photo review delete/replace/set-cover scripts
- [ ] Photo review popup and dismissal flow


### Phase 3: print_queue

- [ ] Loader and package structure
- [ ] REST sensor and template sensors
- [ ] Lifecycle control commands: add/remove/start/stop/cancel/update/reorder/bulk
- [ ] Dashboard cards and docs

### Phase 4: print_statistics

- [ ] Loader and package structure
- [ ] `/archives/stats` sensor
- [ ] Derived statistics templates
- [ ] Dashboard cards and docs

### Phase 5: printer_maintenance

- [ ] Loader and package structure
- [ ] Maintenance REST sensor and mark-complete command
- [ ] Derived health/due sensors
- [ ] Dashboard cards and docs

### Phase 6: cleanup

- [ ] Remove root `bambuddy/` prototype directory
- [ ] Remove superseded `homeassistant/packages/3d_printing/bambuddy_integration/`
- [ ] Remove superseded `docs/features/bambuddy_integration/`
- [ ] Remove old commented loader references when migration is complete
- [ ] Update remaining cross-references

## Next Implementation Order

1. Document and harden the shipped enrichment contract: managed tags + native cost + hidden `[HA_ENRICHMENT_V1]` notes payload.
2. Finish manual re-enrich hardening: archive `filament_slots[]` plus archived `ams[].tray[]`, duplicate `type + color` ambiguity handling, and operator-visible partial outcomes.
3. Harden `print_history` upload handling or move to the Python worker.
4. Build `print_queue` core lifecycle controls.
5. Build `print_statistics` core sensors and cards.
6. Build `printer_maintenance` core read/react package.
7. Return to advanced `print_history` review/detail workflows.
