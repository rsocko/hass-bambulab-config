# Print History Top Controls Contract

## Purpose

Define the layout and regression guardrails for `print_history_top_controls.yaml`, which is rendered above and below the archive browser grid.

This document exists because repeated regressions were introduced when the control strip was implemented as one large `custom:bubble-card` row and then styled through generated DOM positions such as `.bubble-sub-button:nth-child(...)`.

That approach is fragile. Small card-structure changes can silently swap button visibility, move the wrong control, or hide unrelated actions.

## Current Structure

`print_history_top_controls.yaml` is a single-row `custom:bubble-card` with one fixed sub-button group.

The implementation still uses `nth-child(...)` selectors, but only against a documented, repo-owned order contract. The point is not to avoid `nth-child` entirely; the point is to make it deterministic and reviewable.

### Fixed Child Order Contract

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

The YAML file duplicates this mapping in an inline `buttonIndex` object. If the YAML order changes, that mapping and the mobile CSS rules must be updated in the same edit.

## Mobile Contract

At mobile widths (`<= 720px`):

- Show `Previous`, `Page Info`, and `Next` in the pagination bar.
- Hide `First`, `Last`, and `Matches`.
- Show page info as icon + `X/Y`.
- Keep the `Layout` select visible on mobile.
- Keep the whole strip as one horizontally scrollable row if needed.
- Allow `PpP`, `Images`, and `Refresh` to compress by hiding their labels before hiding the controls themselves.

At desktop/tablet widths (`> 720px`):

- Show all controls in the fixed order above.
- Show page info as `Page X of Y`.

## Hardening Rules

Do not reintroduce these patterns into `print_history_top_controls.yaml`:

- Hidden duplicate controls whose visibility depends on generated child order.
- Extra temporary buttons that shift the fixed child order without updating the contract.
- Layout-mode quick buttons that replace the canonical `Layout` select on some breakpoints.
- Refactors that remove the inline `buttonIndex` mapping or make it diverge from YAML order.

Preferred change patterns:

- If a control is added or removed, update the YAML order, the inline `buttonIndex` map, and this document together.
- If mobile behavior changes, update the documented `nth-child` targets by semantic name, not by guessing raw numbers in CSS.
- Keep `Layout` as the canonical layout control across all breakpoints.

## Validation Checklist

When modifying the top controls, verify all of the following:

1. Desktop shows `First`, `Previous`, `Page Info`, `Next`, `Last` in that order.
2. Mobile hides `First`, `Last`, and `Matches` but still shows `Previous`, `Page Info`, `Layout`, and `Next`.
3. Mobile still shows the `Layout` dropdown.
4. Page info reads `Page X of Y` on desktop and `X/Y` on mobile.
5. The same control strip works in both the top and bottom placements in `view_print_history.yaml`.
6. The inline `buttonIndex` map still matches the YAML group order exactly.