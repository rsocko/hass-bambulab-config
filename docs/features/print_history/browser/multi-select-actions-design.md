# Print History Browser Multi-Select Actions Design (Issue #919)

## Purpose

Document the shipped multi-select interaction for the print-history browser toolbar and archive cards.

This document covers both the design intent and the current implementation contract so future refinements do not regress selection behavior, bulk actions, or the shared toolbar/card coordination model.

## Current Status

The first multi-select action slice is implemented and active.

Shipped scope:

- toolbar entry point for `Select Prints`
- toolbar mode swap from normal navigation controls to multi-select controls
- selection behavior across `Compact`, `Media`, and `List` archive cards
- visible-page `Select All`
- bulk `Tags`, `Project`, `Favorite` / `Unfavorite`, and `Delete`
- helper-backed coordination between the YAML toolbar and the browser custom card

This is intentionally a browser action workflow, not a general compare/query-builder surface.

## Design Goals

1. keep the default browser state optimized for browsing, not bulk editing
2. make multi-select explicit, reversible, and visually obvious
3. preserve the existing top-controls density outside selection mode
4. scope `Select All` to the visible page only so the action matches what the user can currently inspect
5. keep destructive operations clearly separated and harder to trigger accidentally
6. avoid pushing a large selected-ID payload into Home Assistant helper state

## Architecture Decision

The implementation uses a split state model.

### Shared Home Assistant state

Shared helpers coordinate mode and summary state between the toolbar and the browser card:

- `input_boolean.print_history_multi_select_mode`
- `input_number.print_history_multi_select_count`
- `input_boolean.print_history_multi_select_all_favorites`
- `input_text.print_history_multi_select_request`

These helpers exist so the YAML control strip and the custom browser card can stay synchronized even though they render separately.

### Local browser-card state

The actual selected archive IDs remain local to `print-history-browser-card.js`.

Reasoning:

- selection is page-scoped UI state, not durable operator state
- serializing up to 50 selected IDs into helpers would add avoidable HA-side churn
- the toolbar only needs mode, count, favorite-summary, and one-shot requests

This split is the core implementation choice and should be preserved unless the selection model becomes cross-surface or cross-session.

## Toolbar Contract

Normal mode includes the standard browser controls plus a `Select Prints` action.

When multi-select mode is active, the normal controls are hidden and replaced by:

1. selected count
2. `Cancel`
3. `Select All`
4. `Tags`
5. `Project`
6. `Favorite` or `Unfavorite`
7. `Delete`

### Request Flow

The toolbar does not directly mutate selected archives.

Instead it writes one-shot requests through `script.request_print_history_multi_select_action`, which sets `input_text.print_history_multi_select_request` to `action|timestamp`.

The browser card consumes that request, applies the action locally or opens the relevant bulk dialog, and then clears the helper.

This keeps the toolbar stateless and avoids embedding archive-specific logic into the bubble-card YAML.

## Card Interaction Contract

When multi-select mode is off:

- clicking a card opens the archive popup
- favorite and viewer actions keep their normal behavior
- media cards can still use gallery navigation and swipe gestures

When multi-select mode is on:

- card click toggles selection instead of opening the popup
- keyboard `Enter` / `Space` toggles selection instead of opening
- cards render a selection badge and selected outline state
- favorite/viewer/open interactions are suppressed in favor of selection
- media gallery next/previous controls and swipe navigation are disabled

The requirement is simple: while selection mode is active, the card surface behaves like a selectable list item, not like a detail launcher.

## Bulk Action Semantics

### Select All

`Select All` only selects the archives on the currently visible page.

It does not select every archive matching the current filter set across all pages.

This matches the visible UI and avoids creating hidden off-screen destructive scope.

### Tags

Bulk tag editing is additive/subtractive for user tags only.

The shipped dialog supports:

- `Add User Tags`
- `Remove User Tags`

It does not replace the full tag set.

System-managed tags are preserved, including prefixes such as:

- `f:`
- `s:`
- `spoolman:`
- `vendor:`
- `material:`
- `cost:`
- `status:`
- `ha enrichment:`
- `ha_enrichment:`
- `ha_enriched:true`

Implementation path:

- `script.bulk_update_print_history_user_tags`
- `bambuddy.get_print_history_archive_detail`
- `rest_command.bambuddy_update_archive`

### Project

Bulk project assignment replaces the current project for each selected archive.

The dialog offers existing Bambuddy projects plus `No Project`, which clears `project_id`.

Implementation path:

- `script.bulk_assign_print_history_project`
- `rest_command.bambuddy_update_archive`

### Favorite / Unfavorite

The toolbar label is summary-driven:

- if all selected archives are already favorites, show `Unfavorite`
- otherwise show `Favorite`

The action then writes one boolean favorite target across the whole selection.

Implementation path:

- `script.bulk_set_print_history_archive_favorite`
- `rest_command.bambuddy_update_archive`

### Delete

Bulk delete is intentionally high-friction.

The shipped flow requires:

1. confirmation dialog
2. typed `DELETE` confirmation prompt

Only then does the browser call the HA bulk delete script.

Implementation path:

- `script.bulk_delete_print_history_archives`
- `bambuddy.delete_print_history_archive`

Delete remains page-selection scoped because the browser card owns the selected IDs.

## Update-Safety Requirement

Bulk actions depend on partial archive PATCH behavior.

`rest_command.bambuddy_update_archive` must remain field-optional so bulk `project_id` or `is_favorite` updates do not accidentally clear `tags` or `notes`.

That partial-update rule is now part of the multi-select action contract, not just a rest-command implementation detail.

## Mobile Behavior

The toolbar keeps one row and stays horizontally scrollable on smaller widths.

Mobile behavior for this slice:

- normal mobile pagination still hides `First`, `Last`, and `Matches`
- in multi-select mode, the selected-count label can collapse its text on narrow widths
- actions remain icon-driven and horizontally scrollable rather than wrapping into a second dense row

This keeps selection mode usable on mobile without redesigning the browser header footprint.

## Key Files

Primary implementation files:

- `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`
- `homeassistant/packages/3d_printing/print_history/dashboard_cards/print_history_top_controls.yaml`
- `homeassistant/packages/3d_printing/print_history/rest_commands/bambuddy_update_archive.yaml`

Support helpers and scripts:

- `homeassistant/packages/3d_printing/print_history/helpers/input_boolean/input_boolean_print_history_multi_select_mode.yaml`
- `homeassistant/packages/3d_printing/print_history/helpers/input_boolean/input_boolean_print_history_multi_select_all_favorites.yaml`
- `homeassistant/packages/3d_printing/print_history/helpers/input_number/input_number_print_history_multi_select_count.yaml`
- `homeassistant/packages/3d_printing/print_history/helpers/input_text/input_text_print_history_multi_select_request.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/enter_print_history_multi_select_mode.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/cancel_print_history_multi_select_mode.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/request_print_history_multi_select_action.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/bulk_update_print_history_user_tags.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/bulk_assign_print_history_project.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/bulk_set_print_history_archive_favorite.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/bulk_delete_print_history_archives.yaml`

## Regression Guardrails

Do not regress these behaviors:

1. card click must not open the popup while multi-select mode is active
2. media gallery swipe and nav buttons must remain disabled during multi-select mode
3. `Select All` must stay visible-page scoped
4. tag bulk edits must preserve system tags and only modify user tags
5. bulk favorite/project updates must rely on partial PATCH payloads and must not clear unrelated fields
6. delete must remain explicitly destructive with double confirmation
7. the toolbar must fully swap modes rather than mixing normal paging and bulk-edit actions in one crowded row

## Relationship To Other Browser Docs

- Use `filter-sort-design.md` for the broader browser architecture and layering contract.
- Use `top-controls-contract.md` for row-order, icon-selector, and mobile guardrails for the shared toolbar component.
- Use `../design/archive-compare-similar.md` for compare-oriented multi-selection ideas that are broader than this shipped bulk-mutation slice.