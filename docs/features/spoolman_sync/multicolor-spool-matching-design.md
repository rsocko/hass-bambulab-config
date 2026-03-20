# Multi-Color Spool Matching - Design Document

> Status: Active design aligned to current Option A matcher architecture
> Updated: 2026-03-20
> Scope: Automatic multi-color matching behavior for Spoolman sync

## Purpose

This document defines how multi-color filament matching should extend the currently deployed spool matching logic.

Current deployed architecture and matching authority:
- `sensor.spoolman_tray_map` is the authoritative matcher.
- Automation and manual actions consume tray-map results via `script.resolve_matching_spool_from_tray_map`.
- `script.find_matching_spool_in_spoolman` is retained as a legacy comparator and parity check path.

Related manual interaction design is documented in:
- [manual-spool-matching-design.md](manual-spool-matching-design.md)

## Current Baseline (Implemented)

The deployed matcher in `spoolman_tray_map` currently does the following:

1. Detects empty trays (AMS + external spool heuristics).
2. Attempts UUID match first.
3. Falls through to color + material fallback when UUID is unavailable or unresolved.
4. Uses vendor-aware fallback behavior:
	 - UUID-attempt path searches Bambu vendor candidates.
	 - non-UUID path searches non-Bambu candidates.
5. Uses profile-name matching on Bambu path when profile attributes are available.
6. Applies AMS location disambiguation when multiple candidates remain.
7. Excludes sealed spools from candidate pool.

This baseline came from the spool-matching analysis and Option A implementation.

## Multi-Color Problem

Spoolman multi-color spools use `filament_multi_color_hexes` and may not have a single-value `filament_color_hex` suitable for current fallback matching.

Result with current baseline:
- UUID path still works.
- color/material fallback can miss multi-color spools when only multi-color hex metadata is present.

## Data Model Notes

Spoolman integration fields relevant to color matching:

| Spool type | filament_color_hex | filament_multi_color_hexes | filament_multi_color_direction |
|---|---|---|---|
| Single-color | Present | Absent | Absent |
| Multi-color | Often empty/absent | Present | Present |

Observed multi-color examples:
- Dusk Glare: ffa11f,ff5900
- Rainbow 04: e292fe,fff994,6ef785,93e3fd
- Rainbow 02: 982abc,e63b7a,00a1d8

## Matching Cascade For Multi-Color Extension

Multi-color support should be added without changing existing precedence semantics:

1. UUID exact match
2. Single-color exact match (`filament_color_hex`)
3. Multi-color first-hex match (first item in `filament_multi_color_hexes`)
4. Optional multi-color any-hex containment fallback
5. Unmatched

All existing disambiguators must remain in effect for tiers 2-4:
- material/type check
- vendor-aware pathing (Bambu-aware on UUID path)
- profile-name matching when available
- AMS location tie-break
- sealed spool exclusion

## Bambu Studio Operator Convention

Bambu tray entities expose one color value, not a list.

Operator convention for multi-color spools:
- set tray color to the first color in `filament_multi_color_hexes`

Examples:

| Spool | filament_multi_color_hexes | Recommended tray color |
|---|---|---|
| Dusk Glare | ffa11f,ff5900 | #FFA11F |
| Rainbow 04 | e292fe,fff994,6ef785,93e3fd | #E292FE |
| Rainbow 02 | 982abc,e63b7a,00a1d8 | #982ABC |

This keeps matching deterministic and minimizes user setup friction.

## Implementation Touchpoints

Primary matcher changes:
- `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml`
	- add multi-color color tiers after UUID attempt using the same disambiguation pipeline

Legacy comparator parity updates (recommended):
- `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml`
	- normalize multi-color fields and mirror fallback tiers for parity validation

Validation and docs:
- `homeassistant/packages/3d_printing/spoolman_sync/scripts/spool_matching_logic_self_test-script.yaml`
	- extend parity checks with at least one multi-color fixture path
- `tests/spool_matching/test_option_a_matching.py`
	- add deterministic scenarios for first-hex and any-hex behavior
- `docs/features/spoolman_sync/spoolman-custom-fields.md`
	- codify first-color setup guidance

## Scenarios

| Scenario | Expected behavior |
|---|---|
| Bambu multi-color spool with known UUID | UUID path wins |
| UUID missing, single-color hex exists | single-color tier may match |
| UUID missing, no single-color, first multi-color hex matches tray color | first-hex tier matches |
| first-hex misses, any-hex enabled and contains tray color | any-hex tier matches |
| Multiple candidates after filtering | ambiguity handled by current disambiguation semantics |
| No candidates | unmatched with reason |

## Risks

| Scenario | Risk | Mitigation |
|---|---|---|
| User selects non-first tray color | Medium | optional any-hex fallback + setup guidance |
| Shared first hex across many spools | Medium | existing material/profile/vendor/AMS disambiguation |
| Any-hex overmatching | Medium | keep any-hex optional and last-tier only |
| Single-color and multi-color overlap | Low | keep single-color tier ahead of multi-color tiers |

## Status Summary

- Option A matcher alignment is implemented.
- Multi-color display rendering already works in dashboard cards.
- Multi-color matching tiers described here are the remaining extension for matching logic.
