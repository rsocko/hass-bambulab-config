# Archive Detail Popup Design (Issue #753)

## Purpose

Define the phased interaction model for print-history cards so each visible archive becomes its own tap target and opens an archive-specific popup instead of falling through to a single generic more-info dialog.

This document covers the Home Assistant interaction model and rollout sequence for issue #753.

## Current Implementation Status

### Shipped now

- each visible archive is now its own Lovelace card and opens an archive-specific `browser_mod.popup`
- the active implementation is YAML-only and follows the same pattern used by the filament catalog:
	1. `custom:auto-entities` reads `sensor.print_history_page_archives.attributes.archives`
	2. one `custom:button-card` is generated per archive
	3. shared button-card templates render the `Compact`, `Media`, and `Detail` card bodies
	4. a shared popup template opens a read-only detail popup using the projected archive payload already present on the page
- the active popup is reusable and defined once through shared button-card templates rather than duplicated in each layout variant

### Phase tracking as of the live implementation

- Phase 0 remains deferred, and that is still accurate: the live archive popup/card templates are still owned by `common/dashboard_cards/card_templates`, and `button_card_templates` are still loaded from the shared dashboard definition under `common/dashboards/3d_printing.yaml`
- Phase 1 is shipped for all three archive card variants: `Compact`, `Media`, and `Detail`
- Phase 2 has now started in an initial form: favorites can be toggled from both the cards and the popup, and the popup supports helper-backed `tags` / `notes` edits

### Not shipped yet

- edit action for `print_name`
- future issue-specific popup actions for `#744`, `#747`, `#748`, `#750`, `#755`, and `#783`
- feature-local ownership of the popup/card templates under `print_history`; the live implementation still uses the shared button-card template registry under `common`

### Design adjustment from the earlier draft

An intermediate custom Lovelace JavaScript card was attempted and then removed. The current implementation intentionally avoids a new frontend resource dependency and instead uses the existing repository pattern that already works in the filament catalog.

## Problem Statement

The original `print_history` browser rendered the visible page slice as one large HTML blob inside a single `custom:button-card`.

That original approach created two UX problems:

1. the entire print section behaves like one card
2. taps resolve to one default more-info target instead of the specific print the user intended to inspect

That architecture is acceptable for presentation-only browsing, but it is the wrong foundation for per-archive drilldown and later per-archive actions.

## Goals

1. make each archive independently tappable
2. ship a Phase 1 popup that displays richer archive details without mutating data
3. preserve one stable entry point so later edit phases do not require another dashboard redesign
4. reserve space for future archive actions tied to later issues

## Non-Goals

1. do not add editing in the first implementation pass
2. do not require a per-archive API fetch just to open the first popup
3. do not redesign filter, paging, or activity controls as part of this issue
4. do not commit to the exact action semantics of later issues before those issue-specific docs exist

## Verified Constraints

### Historical renderer that motivated this issue

- source: `sensor.print_history_page_archives`
- original implementation: one `custom:button-card` with `custom_fields.history_grid`
- result: one Lovelace card surface, one default tap target

### Current renderer

- source: `sensor.print_history_page_archives`
- current implementation: `custom:auto-entities` generates one `custom:button-card` per archive and applies shared templates for `Compact`, `Media`, and `Detail`
- result: each visible archive is its own tap target and opens its own popup

### Current projected archive shape

The existing page sensor already projects enough fields for a useful read-only popup:

- `id`
- `printer_id`
- `print_name`
- `status`
- `started_at`
- `completed_at`
- `created_at`
- `actual_time_seconds`
- `filament_used_grams`
- `filament_type`
- `filament_color`
- `cost`
- `object_count`
- `layer_height`
- `total_layers`
- `nozzle_diameter`
- `designer`
- `is_favorite`
- `tags`
- `notes`
- `failure_reason`
- `thumbnail_path`

That means Phase 1 can stay entirely within the existing dashboard payload contract.

## Recommended Architecture

### Template ownership

The archive popup/card templates are logically part of `print_history`, not true shared `common` infrastructure.

They may initially live under the shared button-card template registry if that is the current dashboard loading constraint, but the intended end state is:

1. `print_history` owns its archive card and popup templates
2. the dashboard template-loading model allows feature-local template registration without routing feature-specific templates through `common`

This should be treated as a small architectural refactor tied to the popup rollout, not as permanent placement.

Current status:

- this ownership refactor is still a valid target architecture
- it is not part of the currently shipped implementation
- the live templates remain in `common/dashboard_cards/card_templates` because that is the active shared button-card registry path

### Phase 1 rendering model

Replace the single HTML-blob renderer with generated per-archive cards.

Recommended structure:

1. `custom:auto-entities` generates one `custom:button-card` per archive from `sensor.print_history_page_archives.attributes.archives`
2. a shared button-card template renders the archive card body
3. that same template provides the per-card `tap_action` that opens a popup for the selected archive
4. popup content is computed on demand from the projected archive payload

Why this is the right first move:

- fixes the tap-target bug at the root cause
- keeps archive cards visually rich
- avoids introducing many new helper entities just to support popup launch
- provides a clean extension point for future per-archive action buttons

### Popup model

Use a `browser_mod.popup` opened by the tapped archive card.

The popup should have two layers:

1. a read-only detail surface rendered from the archive payload snapshot
2. a bottom action area reserved for future mutation actions

This matches the existing repository pattern used by spool and AMS popups: lightweight card trigger, heavier popup content on demand.

## Phase Plan

## Phase 0: Template Ownership Refactor

### Purpose

Decouple `print_history`-specific button-card templates from the `common` feature group so feature ownership matches feature behavior.

### Scope

1. adjust the 3D-printing dashboard template-loading approach so feature packages can supply their own button-card templates
2. move archive popup/card templates into the `print_history` package
3. keep the rendered UX unchanged

### Why this phase exists

Without this step, issue #753 lands as functionally correct but structurally misleading: a print-history-specific template appears to be reusable shared infrastructure when it is not.

### Exit Criteria

1. archive popup/card templates are loaded from `print_history`
2. `common` no longer owns print-history-specific template definitions
3. no behavior change in the archive browser

### Current status

Deferred, and still accurate. The popup feature shipped first using the existing shared template registry so the interaction model could be stabilized before moving template ownership. The live templates remain under `common/dashboard_cards/card_templates`, and the current dashboard wiring still loads button-card templates from the shared `common` dashboard definition.

## Phase 1: Read-Only Archive Detail Popup

### User behavior

- tapping any archive card opens a popup for that archive only
- there is no generic card-level more-info fallback on the whole print section
- the popup focuses on inspection, not editing

### Content

Phase 1 popup should show:

- archive title
- thumbnail if available
- status and favorite state
- start and completion timestamps
- duration, filament used, cost, object count
- material, layer height, nozzle diameter, total layers
- printer identifier
- designer
- tags
- notes
- failure reason when present

### Data behavior

- no extra archive-detail fetch required for popup open
- popup uses the same projected archive payload already loaded for the page
- if a field is not present in the projected payload, Phase 1 omits it instead of adding a new network dependency

### Exit Criteria

1. each visible archive has its own tap target
2. tapping a print opens an archive-specific popup
3. the popup is materially more informative than the card itself
4. no edit actions are exposed yet

### Current status

Implemented, with ongoing layout refinement.

What is live now:

- per-archive tap targets in `Compact`, `Media`, and `Detail`
- read-only popup content rendered from the projected archive payload already present on the page
- thumbnail, status, timestamps, duration, filament used, cost, object count, material, layer height, nozzle, total layers, printer, designer, tags, notes, and failure reason

What is still being tuned inside Phase 1:

- responsive column counts for `Compact` and `Media`
- full-width behavior for `Detail`
- card density and visual polish compared with the earlier single-renderer layout

## Recommended Next Stage

The next stage should remain Phase 2, not Phase 0.

Why:

- the current popup entry point is already stable and shipped across all three card variants
- the remaining user-visible gap is the unfinished portion of archive actions, not tap-target behavior or popup launch
- the lowest-risk next increment is to continue the existing action area by adding the remaining missing edit scope and follow-on drilldown actions

Recommended sequencing:

1. finish the remaining initial edit scope by adding `print_name`
2. refine the current `tags` / `notes` editing UX if the helper-backed flow proves too clunky in practice
3. return to Phase 0 only if the dashboard template-loading model is being changed anyway, or if feature-local template ownership becomes operationally important enough to justify the refactor on its own

That keeps the next work aligned with the shipped UX while preserving the ownership refactor as a cleanup/architecture follow-on rather than a blocker.

## Phase 2: Edit Key Fields

Phase 2 keeps the same popup entry point and adds a controlled edit area for fields that map cleanly to the existing `PATCH /archives/{id}` contract.

### Initial edit scope

- `print_name`
- `notes`
- `tags`
- `is_favorite`

### Scope boundary

Bambuddy itself supports a broader archive update contract than the initial HA popup edit scope. Additional mutable fields include `project_id`, `status`, `failure_reason`, `quantity`, `external_url`, and `cost`.

Those fields are intentionally out of the first editable popup slice unless they support a clear print-history workflow. This keeps the initial popup focused and avoids implying that unrelated Bambuddy archive fields are spare storage for enrichment metadata.

### Why these first

- they already fit the existing Bambuddy update semantics
- they are high-value operator metadata
- they do not require a separate object model or multi-step workflow

### Current implementation slice

- `is_favorite` is toggleable from both the archive cards and the popup action bar
- `tags` and `notes` are editable from the popup through helper-backed fields plus a save action
- `print_name` is still deferred

### UI shape

Recommended pattern:

1. keep the top of the popup read-only
2. add a separate `Edit` action area below the details
3. launch either an inline editable section or a focused edit popup from that action area

This keeps Phase 1 stable while allowing editing to arrive without reworking the inspection layout.

## Future Extension Slots

The popup must reserve room for additional archive actions without needing another entry-point redesign.

### Confirmed future consumer

- issue `#744`: assign archive to a project

### Reserved future consumer set

- issue `#747`
- issue `#748`
- issue `#750`
- issue `#755`
- issue `#783`

Because those issues define their own behaviors, this document does not guess their final UX. Instead it defines the integration boundary they should use.

### Integration boundary

Future issue-specific actions should attach to the archive popup through one of these slots:

1. primary action row under the detail content
2. secondary metadata section for archive relationships and provenance
3. optional follow-on popup flows when an action needs more than one step

### Guardrail

Do not add future issue actions directly to the archive card face unless the action is both high-frequency and low-risk. The card tap should remain the stable detail entry point.

## Implementation Notes

### Rendering approach

- per-archive cards should remain driven by `sensor.print_history_page_archives`
- card visuals can continue using button-card HTML/CSS for layout richness
- the archive grid wrapper should remain responsive across `Compact`, `Media`, and `Detail`
- the active implementation should prefer the existing `auto-entities` + button-card template pattern over introducing a new custom frontend resource unless a later requirement clearly justifies it

### Popup content strategy

- Phase 1 popup content can be snapshot-rendered from the archive payload
- later edit controls should prefer server-side scripts or REST commands for mutations
- if a later phase needs fresher live data, add that reactivity in the popup content, not on the main archive grid

## Recommended Delivery Sequence

1. stabilize the shipped Phase 1 renderer and popup behavior across desktop and mobile
2. decide whether template ownership should move from `common` into `print_history` as a cleanup refactor or remain deferred
3. add key-field editing in a second pass using the same popup entry point
4. attach future issue-specific actions only after their own design docs define payloads and workflows
