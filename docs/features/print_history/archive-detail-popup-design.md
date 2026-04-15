# Archive Detail Popup Design (Issue #753)

## Purpose

Define the phased interaction model for print-history cards so each visible archive becomes its own tap target and opens an archive-specific popup instead of falling through to a single generic more-info dialog.

This document covers the Home Assistant interaction model and rollout sequence for issue #753.

## Current Implementation Status

### Shipped now

- each visible archive is now its own interactive card inside `custom:print-history-browser-card` and opens an archive-specific `browser_mod.popup`
- the active implementation is the custom browser card resource plus helper-backed popup content:
	1. `custom:print-history-browser-card` queries Bambuddy directly over websocket with `bambuddy/print_history_query`
	2. the card renders the `Compact`, `Media`, and `Detail` variants directly in JavaScript
	3. card clicks run a `browser_mod.sequence` flow that populates popup helpers and opens the popup
	4. popup content is composed from the photo gallery card, a popup-summary button-card template, a shared tabbed filament-breakdown card, the tag editor card, and helper-backed edit rows
- the active popup is reusable and driven from the browser card rather than duplicated in each layout variant

### Phase tracking as of the live implementation

- Phase 0 remains deferred, and that is still accurate: the live archive popup/card templates are still owned by `common/dashboard_cards/card_templates`, and `button_card_templates` are still loaded from the shared dashboard definition under `common/dashboards/3d_printing.yaml`
- Phase 1 is shipped for all three archive card variants: `Compact`, `Media`, and `Detail`
- Phase 2 now covers the initial operator-edit slice: favorites can be toggled from both the cards and the popup, and the popup supports helper-backed edits for `print_name`, `tags`, `notes`, `status`, and `failure_reason` within Home Assistant's current helper limits

### Not shipped yet

- compare/deep-link actions and future issue-specific popup actions for `#744`, `#747`, `#748`, `#750`, `#755`, and `#783`; issue `#757` compare/similar workflow design now lives in `archive-compare-similar-design.md`
- origin/provenance badges that distinguish native Bambuddy archives from recovered replacements or historical imports
- duplicate-review actions and suspicious-same-hash workflows in the popup action area
- inferred-timing review and `update to inferred times` actions for imports or recovered records
- feature-local ownership of the popup/card templates under `print_history`; the live implementation still uses the shared button-card template registry under `common`

### Design adjustment from the earlier draft

The final shipped path does use a custom Lovelace JavaScript card. The browser card now owns row rendering and popup launch behavior because that proved more reliable than keeping the archive-grid interaction in shared YAML templates.

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

- source: legacy `sensor.print_history_page_archives`
- original implementation: one `custom:button-card` with `custom_fields.history_grid`
- result: one Lovelace card surface, one default tap target

### Current renderer

- source: `sensor.bambuddy_print_history_browser_page_archives`
- current implementation: `custom:print-history-browser-card` renders one interactive archive surface per result and opens the popup directly
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

That means Phase 1 can stay entirely within the current integration-owned dashboard payload contract.

Important current gap:

- the active page payload does **not** yet carry a compact origin/provenance summary, duplicate metadata, or inferred-timing review fields
- those should be added as a compact summary or fetched through popup detail flows, not by dumping full provenance blobs into the main page payload

Update as of issue `#737` implementation:

- the active page payload now carries compact duplicate scalar fields (`duplicate_count`, `duplicate_sequence`, `original_archive_id`)
- the popup may render a read-only duplicate summary from those fields without a second detail fetch
- matching-item navigation and compare actions remain deferred to a later follow-up

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

1. `custom:auto-entities` generates one `custom:button-card` per archive from `sensor.bambuddy_print_history_browser_page_archives.attributes.archives`
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

1. refine the current helper-backed edit UX and verify it remains reliable for longer user notes/tags
2. add compact provenance and duplicate-review context so recovered/imported records are visibly distinct from native captures
3. add compare/deep-link actions and any higher-value archive follow-on workflows after that provenance contract is stable; issue `#757` now has a dedicated workflow design in `archive-compare-similar-design.md`
4. return to Phase 0 only if the dashboard template-loading model is being changed anyway, or if feature-local template ownership becomes operationally important enough to justify the refactor on its own

That keeps the next work aligned with the shipped UX while preserving the ownership refactor as a cleanup/architecture follow-on rather than a blocker.

## Phase 2: Edit Key Fields

Phase 2 keeps the same popup entry point and adds a controlled edit area for fields that map cleanly to the existing `PATCH /archives/{id}` contract.

### Initial edit scope

- `print_name`
- `notes`
- `tags`
- `is_favorite`

Status and failure-reason editing are now also in scope for the HA popup because they support a concrete archive-triage workflow: correcting an outcome after manual review, and aligning archived result metadata with Bambuddy's own failure categorization.

### Scope boundary

Bambuddy itself supports a broader archive update contract than the initial HA popup edit scope. Additional mutable fields include `project_id`, `status`, `failure_reason`, `quantity`, `external_url`, and `cost`.

The remaining deferred fields are `project_id`, `quantity`, `external_url`, and `cost`. Those stay out of the current popup slice because they are not required for the first archive-review workflow and would push the popup toward a full archive-admin form.

### Why these first

- they already fit the existing Bambuddy update semantics
- they are high-value operator metadata
- they do not require a separate object model or multi-step workflow
- `status` and `failure_reason` support a real post-print operator workflow instead of being generic metadata storage

### Current implementation slice

- `is_favorite` is toggleable from both the archive cards and the popup action bar
- `print_name`, `tags`, and `notes` are editable from the popup through helper-backed fields plus a save action, with current inline editing capped by Home Assistant helper limits
- `status` is editable from the popup
- `failure_reason` is editable from the popup, but only when the selected status is `failed` or `cancelled`
- manual `Re-Enrich` is exposed from the popup for older archives and preserves hidden enrichment metadata while rebuilding managed tags/notes when possible

### Upstream Bambuddy behavior verified against source

- backend `PATCH /archives/{id}` accepts `failure_reason` as `string | null`, so the API contract itself allows arbitrary custom strings
- the shipped Bambuddy frontend does not expose a free-text failure-reason field; it uses a fixed dropdown list in `EditArchiveModal.tsx`
- the shipped Bambuddy frontend only shows that dropdown for failure/cancel-style outcomes; our HA popup normalizes stored `cancelled`, `aborted`, and legacy `stopped` values into a single `Cancelled` option
- the HA popup status list is `Completed`, `Failed`, `Cancelled`, and `Printing`, while still accepting legacy raw values from stored archives
- the HA popup preserves an existing non-standard stored failure reason as a selectable option if one already exists on the archive

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

## Provenance And Duplicate Context Extension

This is the next popup/card addition that most directly supports restore and historical-import workflows.

### Card-level behavior for `Compact`, `Media`, and `Detail`

Each archive card variant should keep the current layout, but add a small secondary origin badge only when the archive is not a plain native Bambuddy capture.

Recommended badge states:

- `Recovered` — archive was created or finalized through replacement/restore workflow
- `Imported` — archive came from historical SD-card or file import with no original Bambuddy row
- `Timing Inferred` — canonical timestamps were updated from approved inferred evidence
- `Potential Duplicate` — same archived file exists elsewhere and the case still needs operator review

Guardrail:

- keep this as a compact badge, not a large card banner
- do not show both a duplicate badge and a provenance badge if they communicate the same underlying state; prefer the more actionable one

### Popup provenance block

The popup should gain a dedicated metadata section for:

- `origin_kind`
- original archive link or replacement link when one exists
- whether the record was captured natively, restored, or historically imported
- whether canonical timing came from native Bambuddy capture, copied source runtime, or inferred evidence
- duplicate-review state and related archive IDs when relevant

Current shipped duplicate slice:

- card variants may show a compact duplicate chip when the archive is an original in a duplicate set or a duplicate child row
- the popup may show a read-only duplicate summary using the compact duplicate fields already present on the page payload
- no duplicate compare or matching-archive jump action should be added in this phase

### Timeline presentation rule

When provenance exists, the popup should present timeline fields in two tiers:

1. canonical archive timestamps
2. preserved original or inferred timing context

Examples:

- `Archive created in Bambuddy: Apr 5, 2026 9:17 PM`
- `Original print completed: Mar 31, 2026 9:47 PM`
- `Start time inferred from recorder + sliced estimate (medium confidence)`

The UI should not imply that a recovery-time `created_at` is the actual print date when provenance says otherwise.

Issue `#868` extends this section with a durable event timeline rendered directly in the popup track. The detailed contract for event types, overlap handling, hover behavior, and legend behavior lives in [archive-popup-timeline-design.md](archive-popup-timeline-design.md).

### Data-loading rule

Do not bloat the main browser page payload with the full provenance record.

Preferred shape:

- main page payload gets a compact summary such as `origin_kind`, `timing_confidence`, and `duplicate_review_state`
- popup detail entity or on-demand detail service provides the heavier lineage, duplicate-chain, and timing-source explanation
- popup detail hydration also owns the normalized archive `event_timeline` payload used by the popup track; the archive page payload should not carry serialized timeline rows

### Guardrail

Do not add future issue actions directly to the archive card face unless the action is both high-frequency and low-risk. The card tap should remain the stable detail entry point.

## Implementation Notes

### Rendering approach

- per-archive cards should remain driven by `sensor.bambuddy_print_history_browser_page_archives`
- card visuals can continue using button-card HTML/CSS for layout richness
- the archive grid wrapper should remain responsive across `Compact`, `Media`, and `Detail`
- the archive list interaction still belongs in the browser card, but shared visualizations can justify their own frontend resource when that removes duplicated rendering logic across popup and dashboard surfaces
- the current justified exception is `custom:print-filament-breakdown-card`, which is shared by the live print-weight/cost tabs and the archive popup

### Popup content strategy

- Phase 1 popup content can be snapshot-rendered from the archive payload
- later edit controls should prefer server-side scripts or REST commands for mutations
- if a later phase needs fresher live data, add that reactivity in the popup content, not on the main archive grid
- the current popup keeps its status/metadata summary in the button-card template, but the heavier filament visualization now lives in the shared breakdown custom card and reads the popup archive detail entity directly

## Recommended Delivery Sequence

1. stabilize the shipped Phase 1 renderer and popup behavior across desktop and mobile
2. decide whether template ownership should move from `common` into `print_history` as a cleanup refactor or remain deferred
3. add origin/provenance badges plus popup provenance detail using compact summary fields first
4. add duplicate-review and inferred-timing actions using the same popup entry point
5. attach future issue-specific actions only after their own design docs define payloads and workflows
