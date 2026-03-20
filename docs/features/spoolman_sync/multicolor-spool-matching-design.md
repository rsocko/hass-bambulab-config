# Multi-Color Spool Matching - Design Document

> Status: Design (split from manual matching)
> Updated: 2026-03-20
> Scope: Automatic matching behavior for multi-color spools only

## Purpose

This document defines the automatic matching design for multi-color filament spools.

Manual pin/unpin behavior, per-tray override helpers, and override UX are documented separately in:
- [manual-spool-matching-design.md](manual-spool-matching-design.md)

The split is intentional so automatic multi-color matching can be implemented and deployed independently.

## Problem Statement

Spoolman supports multi-color filament spools (gradient/rainbow) using comma-separated hex values in `filament_multi_color_hexes` instead of single-value `filament_color_hex`.

Current color fallback paths in matching logic primarily assume single-color metadata. Result:

1. Multi-color spools can become unmatchable when UUID matching is unavailable.
2. Multi-color Bambu spools usually work only when UUID matching succeeds first.
3. Automatic fallback behavior is less deterministic for multi-color entries than single-color entries.

## How Multi-Color Data Is Stored

Spoolman integration exposes mutually exclusive color fields:

| Spool type | `filament_color_hex` | `filament_multi_color_hexes` | `filament_multi_color_direction` |
|---|---|---|---|
| Single-color | Present | Absent | Absent |
| Multi-color | Absent | Present | Present |

Observed examples:
- Dusk Glare: `ffa11f,ff5900`
- Rainbow 04: `e292fe,fff994,6ef785,93e3fd`
- Rainbow 02: `982abc,e63b7a,00a1d8`

## Existing Display Behavior (Already Working)

Multi-color attributes are already consumed by dashboard rendering paths (gradients/chips/popups). The design gap is matching and sync logic, not visual rendering.

Reference card templates:
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_detail.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml`

## Bambu Studio Constraint

Bambu tray entities expose one color value (RGB + alpha), not a multi-color set.

Recommended convention for multi-color spools in Bambu Studio:
- Set tray color to the first hex in `filament_multi_color_hexes`.

Examples:

| Spool | `filament_multi_color_hexes` | Recommended tray color |
|---|---|---|
| Dusk Glare | `ffa11f,ff5900` | `#FFA11F` |
| Rainbow 04 | `e292fe,fff994,6ef785,93e3fd` | `#E292FE` |
| Rainbow 02 | `982abc,e63b7a,00a1d8` | `#982ABC` |

Rationale:
- Deterministic convention for users and logic.
- Minimal user friction (single color picker in Bambu Studio).
- Enables stable first-hex fallback tier.

## Current Matching Logic Gaps

### `spoolman_tray_map` template sensor

File:
- `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml`

Current structure is UUID-first, then single-color fallback. Multi-color entries without `filament_color_hex` can be skipped by fallback unless explicit multi-color handling is added.

### `find_matching_spool_in_spoolman` script

File:
- `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml`

Current normalized spool payload focuses on `color_hex_lower`. For multi-color filaments, that value can be empty, so exact color lookup may never match.

## Proposed Matching Cascade (Automatic Scope)

1. UUID exact match
2. Single-color exact match (`filament_color_hex`)
3. Multi-color first-hex match (`filament_multi_color_hexes[0]`)
4. Multi-color any-hex contains tray color (optional fallback)
5. Unmatched

Design notes:
- Keep existing disambiguators (material, profile name, location preference, sealed status).
- Preserve current ambiguity handling semantics where practical.
- Manual override remains out of scope here and is defined in [manual-spool-matching-design.md](manual-spool-matching-design.md).

## Required Logic Changes

### 1. Template matcher: `spoolman_tray_map`

Add multi-color-aware color fallback tiers after UUID miss:
- Continue into color matching when UUID is absent/unresolved.
- Compare tray color to `filament_color_hex` first.
- Then compare to first hex from `filament_multi_color_hexes`.
- Optionally attempt any-hex containment if first-hex yields no candidates.

### 2. Legacy script matcher: `find_matching_spool_in_spoolman`

Enrich normalized spool model with:
- `multi_color_hexes`
- `first_multi_color_hex`

Then apply fallback sequence:
- Exact single-color match first.
- First-hex multi-color match second.
- Any-hex containment fallback optionally third.

### 3. Documentation update

Update custom field documentation to codify first-color convention for operator setup.

## Edge Cases and Scenarios

| Scenario | Current tendency | Expected after multi-color design |
|---|---|---|
| Bambu multi-color spool with UUID | Usually matches by UUID | UUID still wins |
| Non-Bambu multi-color spool without UUID | Often unmatchable | First-hex (or any-hex fallback) can match |
| Two multi-color spools share first hex | Higher ambiguity risk | Existing disambiguators + ambiguity response |
| Single-color spool shares same hex as multi first hex | Possible collision | Single-color exact remains higher priority |
| User chooses non-first tray color for multi-color spool | First-hex may miss | Any-hex fallback can recover (if enabled) |
| External spool uses multi-color filament | Same gap as AMS | Same multi-color fallback behavior applies |

## Risk Assessment

| Scenario | Risk | Mitigation |
|---|---|---|
| User sets arbitrary tray color not equal to first multi-color hex | Medium | Any-hex fallback and setup guidance |
| Shared first hex across many spools | Medium | Existing disambiguators and ambiguity output |
| Single-color and multi-color overlap on same hex | Low | Keep single-color exact prioritized |
| Any-hex fallback creates overmatching | Medium | Keep optional; only run after stricter tiers |

## Test Matrix

| Scenario | Expected result |
|---|---|
| UUID match exists | UUID wins |
| UUID missing, single-color exact exists | Single-color match |
| UUID missing, no single-color, first multi-color exists | First-hex match |
| UUID missing, first-hex miss, any-hex hit | Any-hex match (if enabled) |
| Multiple candidates remain after filters | Ambiguous/unmatched response |
| No candidates | Unmatched response |

## Deployment Independence

This multi-color design can ship independently if:
- No new `input_text.*_spool_override` helpers are introduced in this workstream.
- No pin/unpin UI controls are introduced in this workstream.
- Existing automation consumers continue to accept current ambiguity behavior.

Manual override/pinning work can follow separately using:
- [manual-spool-matching-design.md](manual-spool-matching-design.md)

## Affected Files

| File | Change |
|---|---|
| `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml` | Add multi-color fallback tiers |
| `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml` | Add normalized multi-color fields and fallback matching |
| `docs/features/spoolman_sync/spoolman-custom-fields.md` | Document first-color setup convention |
