# Card Chip Filter Actions

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/browser/card-chip-filter-actions-design.md
Replaced By: none

Issue #860 breaks into a small family of similar UI behaviors: a user clicks a chip or dot on a print-history card, and the browser updates the current filter state without discarding the rest of the active filters.

This document defines the shared contract for the remaining filter-oriented subissues:

- #933 Tag -> add that tag to the active tag filter
- #934 Color circle -> toggle that color in the active color set
- #935 Project -> set project filter to that project
- #936 Status -> set status filter to that status
- #937 Enrichment status -> set enrichment-status filter to that status
- #938 Printer -> set printer filter to that printer

Deferred for later:

- #939 Source lineage filter
- #940 Duplicate lineage filter

Those two are intentionally deferred because they need lineage-aware semantics, not just a direct helper mutation. They should reuse the same UI affordance and dispatch shape, but their backend behavior should be designed against the duplicate/source filter contract separately.

## Goals

- Keep card-driven filtering concise and consistent across all clickable metadata chips.
- Reuse one mutation path instead of adding bespoke logic per chip.
- Preserve the existing Layer 1 / Layer 2 / Layer 3 split.
- Make clickable chips visually obvious before click, not only after discovery.

## Layering

No Layer 1 changes are needed.

- Layer 1 stays focused on normalized archive data.
- Layer 2 continues to own filter state and derived option sets through the Variant 3 browser helpers and query pipeline.
- Layer 3 owns click affordances, hover wording, and chip-specific action mapping.

That means tooltip wording such as `Click to filter by project` stays in the frontend, not in the projected archive payload.

## Shared Interaction Contract

Every clickable archive-card chip should follow the same pattern:

1. Render as an actual button, not a passive span.
2. Use the shared interactive chip styling class so hover/focus behavior is consistent.
3. Dispatch through one shared browser-card action path.
4. Call one shared Home Assistant script that mutates helper-backed filter state.

Frontend payload shape:

- `data-action="apply-filter"`
- `data-filter-action="tag_add" | "color_toggle" | "project_set" | "status_set" | "enrichment_status_set" | "printer_set"`
- `data-filter-value="..."`

Backend script shape:

- `script.apply_print_history_card_filter_action`
- fields: `action`, `value`

The browser card should not directly hardcode helper entity updates per chip. It only maps a rendered chip to the shared action payload.

## Hover And Tooltip Behavior

Clickable chips should be visually distinct from passive chips.

Required affordances:

- pointer cursor
- subtle lift / stronger outline on hover and focus
- keyboard focus visibility
- explicit tooltip hint that the chip is interactive

Tooltip wording should be two-part:

- first line: the chip meaning
- second line: the action hint

Examples:

- `Tag: hueforge` then `Click to add this tag to filters`
- `Project: Desk Organizer` then `Click to filter by this project`
- `Printer: P1S` then `Click to filter by this printer`
- `Bambu PLA Matte (A1) | #FFFFFF` then `Click to filter on this color`

For the first pass, native multiline `title` tooltips are acceptable on chips that do not already use a custom tooltip system. Color dots already have a custom tooltip overlay and should extend that overlay when #934 is implemented.

## Filter Mutation Rules

All card-driven actions keep the rest of the browser state intact.

- Tag adds to the current multi-select tag list and does not clear other filters.
- Color toggles only that color within the current selected color set.
- Project, status, enrichment status, and printer replace only their own single-select helper.
- Applying a direct chip filter should not clear search text, date range, favorites-only, or other unrelated filters.

Tag-specific rules:

- add the clicked tag into `input_text.print_history_filter_tags`
- preserve the current tag mode (`Any` vs `All`)
- clear the legacy single-tag helper back to `All`
- turn off `input_boolean.print_history_filter_tags_untagged_only` when adding a concrete tag

## Implementation Order

Implement one subissue at a time in this order:

1. #933 Tag
2. #934 Color
3. #935 Project
4. #936 Status
5. #937 Enrichment status
6. #938 Printer

This order starts with the one multi-select case that proves the shared mutation path, then moves through the simpler single-select cases.

## Validation

Each subissue should be validated with:

- a focused browser-card regression test for the rendered action markers or tooltip strings
- a script-level test when a new backend mutation path is added
- manual validation in Lovelace that the clicked chip updates filters without breaking card open actions