# Print History Top Controls Contract

## Purpose

Define the layout and regression guardrails for `print_history_top_controls.yaml`, which is rendered above and below the archive browser grid.

This document exists because repeated regressions were introduced when the control strip was implemented as one large `custom:bubble-card` row and then styled through generated DOM positions such as `.bubble-sub-button:nth-child(...)`.

That approach is fragile. Small card-structure changes can silently swap button visibility, move the wrong control, or hide unrelated actions.

## Current Structure

`print_history_top_controls.yaml` is intentionally split into two separate sections:

1. **Pagination bar**
   - Implemented with an explicit `horizontal-stack` of `custom:button-card` buttons.
   - Button order is fixed in YAML: `First`, `Previous`, `Page Info`, `Next`, `Last`.
   - Mobile behavior is controlled per button, not by hiding positional children from a generated DOM.

2. **Utility bar**
   - Implemented as a separate `custom:bubble-card` row.
   - Contains non-navigation controls only: `Layout`, `Matches`, `PpP`, `Images`, `Refresh`.
   - The `Layout` control remains a real select/dropdown so mobile does not depend on hidden alternate buttons.

## Mobile Contract

At mobile widths (`<= 720px`):

- Show `Previous`, `Page Info`, and `Next` in the pagination bar.
- Hide `First` and `Last` in the pagination bar.
- Show page info as icon + `X/Y`.
- Keep the utility bar horizontally scrollable if needed.
- Keep the `Layout` select visible on mobile.

At desktop/tablet widths (`> 720px`):

- Show `First`, `Previous`, `Page Info`, `Next`, and `Last`.
- Show page info as `Page X of Y`.

## Hardening Rules

Do not reintroduce these patterns into `print_history_top_controls.yaml`:

- `nth-child(...)` selectors to hide or reveal pagination controls.
- Mixed navigation and utility controls in a single bubble-card row.
- Hidden duplicate controls whose visibility depends on generated child order.
- Layout-mode quick buttons that replace the canonical `Layout` select on some breakpoints.

Preferred change patterns:

- If pagination changes, edit the explicit `button-card` entries in order.
- If utility controls change, add or remove them only in the utility bubble row.
- If mobile behavior changes, update per-button visibility or labels directly rather than remapping child indices.

## Validation Checklist

When modifying the top controls, verify all of the following:

1. Desktop shows `First`, `Previous`, `Page Info`, `Next`, `Last` in that order.
2. Mobile hides `First` and `Last` but still shows `Previous` and `Next`.
3. Mobile still shows the `Layout` dropdown.
4. Page info reads `Page X of Y` on desktop and `X/Y` on mobile.
5. The same control strip works in both the top and bottom placements in `view_print_history.yaml`.
6. No CSS depends on bubble-card child index for navigation behavior.