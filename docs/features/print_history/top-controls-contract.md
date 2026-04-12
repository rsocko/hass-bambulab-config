# Print History Top Controls Contract

## Purpose

Define the layout and regression guardrails for `print_history_top_controls.yaml`, which is rendered above and below the archive browser grid.

This document exists because repeated regressions were introduced when the control strip was implemented as one large `custom:bubble-card` row and then styled through generated DOM positions such as `.bubble-sub-button:nth-child(...)`.

That approach is fragile. Small card-structure changes can silently swap button visibility, move the wrong control, or hide unrelated actions.

## Current Structure

`print_history_top_controls.yaml` is a single-row `custom:bubble-card` with one fixed sub-button group.

The active implementation now hardens visibility rules with icon-based selectors first, and treats YAML order as a secondary readability contract rather than the main mechanism.

### Semantic Control Contract

The sub-buttons must remain in this exact order:

1. `First`
2. `Previous`
3. `Page Info`
4. `Matches`
5. `PpP`
6. `Layout`
7. `Images`
8. `Refresh`
9. `Next`
10. `Last`

Each control in this row is also identified by a unique semantic icon, and the mobile CSS targets those icons directly:

- `mdi:page-first` → `First`
- `mdi:chevron-left` → `Previous`
- `mdi:book-open-page-variant-outline` → `Page Info`
- `mdi:counter` → `Matches`
- `mdi:format-list-numbered` → `Prints / Page`
- `mdi:view-grid-outline` / `mdi:image-multiple-outline` / `mdi:format-list-bulleted` / `mdi:view-dashboard-outline` → `Layout`
- `mdi:image-outline` → `Images`
- `mdi:refresh` → `Refresh`
- `mdi:chevron-right` → `Next`
- `mdi:page-last` → `Last`

If a control icon changes, the selector contract in `print_history_top_controls.yaml` must be updated in the same edit.

The `Layout` control is a single icon-only selector launcher that opens the `input_select.print_history_card_variant` picker on both desktop and mobile.

## Mobile Contract

At mobile widths (`<= 720px`):

- Show `Previous`, `Page Info`, and `Next` in the pagination bar.
- Hide `First`, `Last`, and `Matches`.
- Show page info as icon + `X/Y`.
- Show `PpP` as the page-size label.
- Show `Layout` as an icon-only selector launcher.
- Show `Images` and `Refresh` as icon-only controls.
- Keep the `Layout` selector launcher visible on mobile.
- Keep the whole strip as one horizontally scrollable row if needed.
- Allow `PpP`, `Images`, and `Refresh` to compress by hiding their labels before hiding the controls themselves.

At desktop/tablet widths (`> 720px`):

- Show all controls in the fixed order above.
- Show page info as `Page X of Y`.
- Show page size as `Prints / Page`.
- Keep `Images` and `Refresh` icon-only.
- Keep `Layout` as an icon-only selector launcher with a dynamic icon that reflects the active variant.

## Hardening Rules

Do not reintroduce these patterns into `print_history_top_controls.yaml`:

- Hidden duplicate controls whose visibility depends on generated child order.
- Extra temporary buttons that shift the fixed child order without updating the contract.
- Layout-mode quick buttons that replace the canonical `Layout` selector on some breakpoints.
- Refactors that make mobile visibility depend primarily on raw child indices when unique icon selectors can be used.
- Reusing one of the semantic icons above for a different action inside this same row.

Preferred change patterns:

- If a control is added or removed, update the YAML order, the icon-selector mapping, and this document together.
- If mobile behavior changes, target controls by semantic icon selector first rather than by guessed raw child indices.
- Keep `Layout` as the canonical layout selector across all breakpoints.

## Validation Checklist

When modifying the top controls, verify all of the following:

1. Desktop shows `First`, `Previous`, `Page Info`, `Next`, `Last` in that order.
2. Mobile hides `First`, `Last`, and `Matches` but still shows `Previous`, `Page Info`, `Layout`, and `Next`.
3. Mobile still shows the `Layout` selector.
4. Page info reads `Page X of Y` on desktop and `X/Y` on mobile.
5. The same control strip works in both the top and bottom placements in `view_print_history.yaml`.
6. The icon selector contract still matches the icons used in the YAML group.
7. `Prints / Page` collapses to `PpP` on mobile.
8. `Images` and `Refresh` stay icon-only on both desktop and mobile.
9. `Layout` uses a variant-specific icon on both desktop and mobile.