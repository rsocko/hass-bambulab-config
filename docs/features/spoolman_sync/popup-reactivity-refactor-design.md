# Popup Reactivity Refactor Design (AMS + Filament Catalog)

## 1. Purpose

Define a safe, incremental refactor path to improve in-popup data freshness for:

- AMS tray popup (`ams_tray_popup`)
- Filament catalog popup (`catalog_spool_popup` + `catalog_spool_popup_content`)

while preserving current UX and avoiding render regressions on pages that always show:

- 9 tray cards on main dashboard
- 150+ spool cards in filament catalog

## 2. Current Architecture (Verified)

### 2.1 AMS popup

- `ams_tray_popup` is a JS-heavy `tap_action` builder that computes popup content from tray and spool context at open time.
- Popup content includes many computed fields and action payloads produced in one run of button-card JS.

Source:
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml`

### 2.2 Catalog popup

- `catalog_spool_popup` is intentionally split into:
  - lightweight trigger (evaluated on each spool card render)
  - heavy popup content (`catalog_spool_popup_content`) rendered on-demand when popup opens
- Existing docs explicitly state this split is for catalog grid performance.

Sources:
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml`
- `docs/features/filament_catalog/filament-catalog.md`

### 2.3 Why some popup elements appear live today

- Cards that are entity-bound (for example `apexcharts-card` series, templated entity cards) can update while popup is open.
- Fields that are computed once in open-time JS can remain stale until close/reopen.

Implication:
- This is not a strict `browser_mod` limitation.
- It is a rendering model choice (snapshot-computed vs entity-reactive content).

## 3. Goals / Non-Goals

### 3.1 Goals

- Improve perceived and actual freshness of key popup values while popup remains open.
- Keep catalog/main page render performance at least equal to current baseline.
- Support side-by-side legacy and refactored popup behavior during rollout.
- Preserve current visual layout and action semantics unless explicitly changed.

### 3.2 Non-Goals

- No immediate full UI redesign.
- No forced migration of every popup field in first pass.
- No removal of existing popup path until reactive path is validated.

## 4. Performance Constraints

1. Catalog page cannot regress due to per-card heavy computation.
2. Popup-only complexity is acceptable if it runs only for open popup(s).
3. Avoid introducing broad `triggers_update` patterns on 150+ cards.
4. Prefer server-side scripts for read-modify-write operations to avoid stale client snapshots.

## 5. Refactor Strategies Considered

### Strategy A: Keep snapshot model + explicit refresh action

- Add `Refresh Popup` sequence: update entities -> close popup -> reopen same popup.

Pros:
- Lowest engineering effort.
- No architectural changes.

Cons:
- Visual jump.
- Does not deliver true live reactivity.

### Strategy B: Reactive Qty-only pilot (recommended Phase 1)

- Keep current popup architecture.
- Move Qty display and +/- state to entity-reactive rendering.
- Use a server-side delta script/service for +/- so each tap uses current backend value.

Pros:
- High UX gain for most interactive control.
- Low perf risk (small surface area).
- Good proving ground for wider refactor.

Cons:
- Mixed model (some fields reactive, some snapshot).

### Strategy C: Full reactive popup content

- Convert most/all display sections to entity-bound cards/templates.

Pros:
- Best consistency for live updates.

Cons:
- Highest migration/testing effort.
- More moving parts and potential edge cases.

## 6. Recommended Architecture

## 6.1 Dual-path popup mode (side-by-side build)

Introduce a runtime mode flag helper:

- `input_select.popup_render_mode`
  - `legacy`
  - `reactive_pilot`
  - `reactive`

Routing behavior:
- Existing entry points remain unchanged.
- Popup opener chooses content template based on mode.
- Legacy and new templates coexist until cutover.

## 6.2 Template split pattern

Keep lightweight trigger pattern in catalog and mirror for AMS where practical:

- Legacy:
  - `catalog_spool_popup` -> `catalog_spool_popup_content`
  - `ams_tray_popup` (current)
- New (side-by-side):
  - `catalog_spool_popup_reactive` -> `catalog_spool_popup_content_reactive`
  - `ams_tray_popup_reactive`

Important: The legacy templates stay intact for rollback and comparison.

## 6.3 Server-side mutation scripts for interactive controls

For mutable controls (starting with Qty):

- Replace client-side merged-extra write logic with a script that:
  1. resolves spool/filament identifiers
  2. reads current value from entity/API state
  3. applies delta (+1/-1 with clamp)
  4. writes canonical payload type to Spoolman
  5. requests entity refresh

Benefits:
- Prevents stale-client race conditions.
- Keeps value semantics centralized.

## 7. Unknowns (Do Not Guess) and Discovery Tasks

These must be validated before broader rollout.

1. Update propagation latency
- Unknown: typical delay from REST write -> filament entity update -> spool attribute mirror update.
- Task: capture p50/p95 latency across 30 updates in both AMS and catalog contexts.

2. Attribute source of truth for Qty rendering
- Unknown: whether `sensor.spoolman_filament_*` or `sensor.spoolman_spool_*` mirrors update first and more reliably.
- Task: instrument update order and choose primary display binding.

3. Concurrent popup behavior
- Unknown: behavior when multiple popups are open in separate browser sessions/devices.
- Task: validate script idempotency and no cross-popup state pollution.

4. Card-level reactive overhead
- Unknown: cost of additional reactive cards in popup on low-power clients.
- Task: profile FPS and script time with reactive pilot enabled.

5. browser_mod close/reopen transition quality
- Unknown: acceptable delay/flicker threshold if fallback refresh is used.
- Task: measure user-perceived transition time on desktop and mobile.

## 8. Phased Implementation Plan

### Phase 0: Baseline + Instrumentation

Deliverables:
- Performance baseline doc for:
  - main dashboard first render
  - filament catalog first render and scroll smoothness
  - popup open latency (AMS and catalog)
- Trace/log helpers for popup update latency (write -> entity reflect).

Exit criteria:
- Baseline numbers captured and committed.

### Phase 1: Side-by-side scaffolding

Deliverables:
- `input_select.popup_render_mode` helper.
- New reactive template placeholders and routing logic.
- No behavior change in `legacy` mode.

Exit criteria:
- Mode switch toggles which popup implementation opens.
- Legacy path parity confirmed.

### Phase 2: Qty reactive pilot (AMS + Catalog)

Deliverables:
- Reactive Qty display binding.
- +/- wired to server-side delta script.
- Visual layout preserved (same pill controls and spacing).

Exit criteria:
- Qty updates while popup remains open.
- No catalog or dashboard render regression beyond thresholds.

### Phase 3: High-value reactive fields

Candidate fields:
- Remaining weight
- Filament total weight/spool count
- Desiccant age/status

Deliverables:
- Convert selected fields to reactive bindings.
- Keep complex derived sections snapshot if not worth converting.

Exit criteria:
- Most user-visible mutable/volatile values refresh live.

### Phase 4: Evaluate full reactive conversion

Decision gate:
- Compare complexity and measured gain.
- If low ROI, stop at hybrid model.

Possible outcomes:
- Stay hybrid long-term.
- Complete full reactive migration.

### Phase 5: Cutover + cleanup

Deliverables:
- Set default mode to reactive after soak period.
- Remove legacy path only after rollback window expires.

Exit criteria:
- Stable for agreed duration with no major regressions.

## 9. Performance Guardrails and Acceptance Thresholds

Set explicit pass/fail gates before merge to default path.

Recommended initial thresholds (tune after baseline):

1. Catalog initial load
- No worse than +5% script time vs baseline in legacy mode.

2. Catalog scroll performance
- No visible jank increase in steady-state scroll through 150+ cards.

3. Popup open latency
- No worse than +10% for AMS and catalog popup open.

4. Update responsiveness
- Qty visual confirmation <= 1.5s p95 after tap (including backend refresh).

5. Error behavior
- Failed writes show non-silent feedback and no stale optimistic lock-in.

## 10. Testing Strategy

### 10.1 Functional testing

Matrix:
- Contexts: AMS popup, catalog popup
- Modes: legacy, reactive_pilot, reactive
- Entities: spool with full metadata, minimal metadata, unavailable entities
- Actions: +, -, desiccant actions, open/close, reload, pin/unpin interactions

### 10.2 Performance testing

- Measure page render and interaction with 9 trays and 150+ catalog spools.
- Capture browser performance traces (desktop + mobile).
- Repeat with warm cache and cold cache.

### 10.3 Reliability testing

- Network delay simulation where possible.
- Repeated rapid taps (+/- burst) to verify race handling and clamping.
- Multi-client concurrent interactions.

### 10.4 Regression testing

- Confirm legacy mode unchanged.
- Validate no change in spool matching, pinning, or popup action semantics.

## 11. Risks and Mitigations

1. Risk: Performance regression in catalog grid
- Mitigation: keep heavy logic popup-only; no extra per-card heavy JS.

2. Risk: Data races on rapid +/- clicks
- Mitigation: server-side delta script with serialized update and clamp.

3. Risk: Divergent behavior between AMS and catalog implementations
- Mitigation: shared script/action helpers and mirrored template structure.

4. Risk: Migration fatigue / partial rollout confusion
- Mitigation: explicit mode flag, rollout checklist, and rollback plan.

5. Risk: Hidden unknowns in update timing
- Mitigation: discovery tasks required before phase expansion.

## 12. Rollback Plan

- Keep legacy templates untouched and selectable by mode flag.
- If any regression appears:
  1. switch `popup_render_mode` to `legacy`
  2. capture issue details and traces
  3. fix in reactive path without user-facing outage

## 13. Recommended First Implementation Slice

Start with Phase 1 + Phase 2 only:

- side-by-side mode flag
- Qty reactive pilot in both AMS and catalog
- server-side delta script
- performance + reliability validation

Reason:
- Maximum UX benefit per unit effort
- Minimal risk to 150+ card catalog rendering model
- Strong foundation for deciding whether full migration is worth it

## 14. JS-Heavy vs Modular Composition (Pros/Cons)

This section captures the architecture tradeoff discussed during planning.

### 14.1 JS-heavy popup assembly (current style)

Definition:
- Large button-card JS blocks compute most display values and action payloads at popup open.

Pros:
- Very flexible for dynamic context resolution (tray/spool/filament matching and branching).
- Easy to keep logic colocated in a single template file.
- Works well for one-shot snapshot rendering.

Cons:
- Values computed at open time can become stale while popup remains open.
- Large files are harder to review, test, and maintain.
- Reuse across AMS/catalog is harder when logic is embedded in long JS blocks.
- Higher risk of client-side race/staleness in read-modify-write actions.

### 14.2 Modular, card-composed popup architecture (target direction)

Definition:
- Keep minimal JS for context resolution/routing.
- Compose popup body from reusable card templates and file-level includes.
- Move mutation logic into HA scripts/services.

Pros:
- Better modularity and reuse (shared KPI/action/qty blocks).
- Cleaner separation of concerns (UI rendering vs mutation logic).
- Improved maintainability and safer incremental refactors.
- Easier side-by-side rollout (legacy and reactive templates coexist).

Cons:
- Requires upfront extraction and naming conventions.
- May still need small JS adapters for context injection.
- Full migration effort is non-trivial; hybrid mode may be the practical endpoint.

### 14.3 Recommendation

Use a hybrid model:
- Keep minimal JS in openers for context routing.
- Build popup content from modular card templates.
- Centralize writes in scripts/services.

This preserves dynamic behavior without locking the whole popup into snapshot-only rendering.

## 15. File-Level Modularization Plan

Goal:
- Introduce modular popup composition while preserving current behavior and performance.

Naming note:
- Paths below are proposed additions. Legacy files remain in place until cutover.

### 15.1 Keep as legacy entry points

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml`

### 15.2 New routing helpers (side-by-side)

- `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_select/input_select_popup_render_mode.yaml`
  - Adds `input_select.popup_render_mode` (`legacy`, `reactive_pilot`, `reactive`).

- `homeassistant/packages/3d_printing/spoolman_sync/scripts/popup_open_router-script.yaml`
  - Optional central router script if we decide to route popup opens via script instead of inline branching.

### 15.3 New reactive popup templates

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup_reactive.yaml`
  - Reactive AMS popup shell.

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_reactive.yaml`
  - Lightweight reactive trigger for catalog card.

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content_reactive.yaml`
  - Reactive catalog popup body.

### 15.4 Shared popup section templates

Create reusable section blocks under a shared folder:

- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_header_identity.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_kpis_primary.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_qty_to_order.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_desiccant_status.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_other_spools.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_weight_history_chart.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/popup_sections/section_actions_footer.yaml`

Design intent:
- AMS and catalog popups assemble these sections in different orders as needed.
- Shared visual behavior and action semantics are defined once.

### 15.5 Action/mutation scripts

- `homeassistant/packages/3d_printing/spoolman_sync/scripts/spoolman_qty_adjust-script.yaml`
  - Delta-based Qty adjust (+/-), clamps at 0, writes canonical payload type.

- `homeassistant/packages/3d_printing/spoolman_sync/scripts/spoolman_popup_refresh_entities-script.yaml`
  - Centralized entity refresh sequence for popup use cases.

Optional later:
- `homeassistant/packages/3d_printing/spoolman_sync/scripts/spoolman_desiccant_mark-script.yaml`
  - Consolidate desiccant/dried actions if desired.

### 15.6 Documentation updates

- Update: `docs/features/spoolman_sync/popup-reactivity-refactor-design.md` (this file)
- Update: `docs/features/filament_catalog/filament-catalog.md`
- Update: `docs/features/spoolman_sync/README.md`

### 15.7 Migration order (file-level)

1. Add `input_select_popup_render_mode` helper.
2. Add `spoolman_qty_adjust-script.yaml`.
3. Add `section_qty_to_order.yaml` and wire it into new reactive templates.
4. Add reactive AMS/catalog popup shell templates and mode routing.
5. Validate pilot, then incrementally extract additional shared sections.
6. Flip default mode only after performance and regression gates pass.

### 15.8 Modularity outcome

After this plan:
- Popup UI can be composed from reusable section files.
- AMS and catalog share core modules but keep context-specific wrappers.
- Legacy path remains available during build/test, then retired when stable.
