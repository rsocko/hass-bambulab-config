# Archive Detail Popup Design (Issue #753)

## Purpose

Define the phased interaction model for print-history cards so each visible archive becomes its own tap target and opens an archive-specific popup instead of falling through to a single generic more-info dialog.

This document covers the Home Assistant interaction model and rollout sequence for issue #753.

## Problem Statement

The current `print_history` browser renders the visible page slice as one large HTML blob inside a single `custom:button-card`.

That creates two UX problems:

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

### Current renderer

- source: `sensor.print_history_page_archives`
- current implementation: one `custom:button-card` with `custom_fields.history_grid`
- result: one Lovelace card surface, one default tap target

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
- link or button to open the archive directly in Bambuddy

### Data behavior

- no extra archive-detail fetch required for popup open
- popup uses the same projected archive payload already loaded for the page
- if a field is not present in the projected payload, Phase 1 omits it instead of adding a new network dependency

### Exit Criteria

1. each visible archive has its own tap target
2. tapping a print opens an archive-specific popup
3. the popup is materially more informative than the card itself
4. no edit actions are exposed yet

## Phase 2: Edit Key Fields

Phase 2 keeps the same popup entry point and adds a controlled edit area for fields that map cleanly to the existing `PATCH /archives/{id}` contract.

### Initial edit scope

- `print_name`
- `notes`
- `tags`
- `is_favorite`

### Why these first

- they already fit the existing Bambuddy update semantics
- they are high-value operator metadata
- they do not require a separate object model or multi-step workflow

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

### Popup content strategy

- Phase 1 popup content can be snapshot-rendered from the archive payload
- later edit controls should prefer server-side scripts or REST commands for mutations
- if a later phase needs fresher live data, add that reactivity in the popup content, not on the main archive grid

## Recommended Delivery Sequence

1. ship per-archive tap targets and read-only popup content
2. validate that card layout modes still behave correctly on desktop and mobile
3. add key-field editing in a second pass using the same popup entry point
4. attach future issue-specific actions only after their own design docs define payloads and workflows
