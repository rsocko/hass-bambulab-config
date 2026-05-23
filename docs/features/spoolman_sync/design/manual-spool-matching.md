# Manual Spool Matching - Design Document

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/manual-spool-matching-design.md
Replaced By: none

> Status: Implemented
> Updated: 2026-03-22
> Scope: User-controlled pin/unpin matching for trays

## Purpose

This document defines the manual pinning feature: a user can explicitly pick which spool should be used for a tray, and that pinned match stays active until logical tray-content changes clear it.

## Implementation Status

Implemented in this repository:
- Per-tray override helpers are now loaded under `spoolman_sync/helpers/input_text/`.
- Per-tray search-query helpers are now loaded under `spoolman_sync/helpers/input_text/` for word-filtered pin picking.
- `sensor.spoolman_tray_map` now evaluates manual pin overrides after UUID and before automatic fallback tiers.
- Tray-map payload includes pin/ambiguity metadata:
	- `match_state`
	- `match_tier`
	- `candidate_count`
	- `candidate_spool_ids`
	- `pin_active`
	- `pin_spool_id`
	- `pin_applied`
- Auto-clear automation clears tray pin overrides on logical spool-change transitions.
- Popup/detail UI surfaces pin state, pin/unpin actions, and ambiguity candidate pin actions.
- Searchable selector-based tray pin pickers are available for all 9 tray targets (8 AMS + external), backed by canonical `sensor.spoolman_spool_<id>` entities.

Automatic matching and multi-color matching design are documented in:
- [Multicolor Spool Matching](/docs/features/spoolman_sync/design/multicolor-spool-matching.md)

## Core Concept

Manual pinning introduces a persistent per-tray override that can be set by the operator when automatic matching is ambiguous or wrong.

Expected behavior:
- user selects a spool for a tray (Pin)
- pinned spool is used for matching-sensitive consumers
- pin is automatically cleared when tray content logically changes

This is intentionally different from one-shot manual re-match actions.

## Functional Requirements

### 1. Per-tray pin helpers

Create one helper per tray slot (9 total):
- input_text.ams_1_tray_1_spool_override ... input_text.ams_2_tray_4_spool_override
- input_text.external_spool_spool_override

Rules:
- value is Spoolman spool ID or empty string
- no initial value (preserve recorder restore behavior)
- empty string means no pin

### 2. Matching precedence

Pinning applies after UUID matching and before automatic color/material fallback:

1. UUID exact match
2. Manual pin override (if valid)
3. Automatic matching fallback tiers
4. Unmatched

Implemented tier name in tray-map output:
- `manual_pin`

Rationale:
- UUID remains highest confidence source
- pinning is user-authoritative when UUID does not resolve

UX constraint tied to precedence:
- when match tier is UUID exact match, Pin/Unpin controls should be hidden or disabled because manual pin is not applied in that state

### 3. Auto-clear behavior (critical)

Pinned override must clear when tray content meaningfully changes:
- tray UUID changes to a different non-empty UUID
- tray type becomes Empty
- tray transitions from populated to empty-equivalent external spool state

Pinned override should not clear for non-content telemetry updates:
- remain percentage changes
- non-identity status fields
- temporary noise that does not indicate spool replacement

### 4. Dashboard UX

In tray popup/detail experiences:
- add Pin Spool action
- show pinned state indicator
- add Unpin action
- present pinning as a primary action for ambiguous/unmatched trays

When tray is currently resolved by UUID exact match:
- hide Pin/Unpin controls, or render them disabled with explanatory text
- explanatory copy should make clear that UUID is authoritative and must not be overridden by standard pin mode

Implemented behavior:
- Tray popup uses a compact Match-row action chip:
	- `Pin Spool` (accent background) when not pinned and UUID is not active.
	- `Unpin` (red background) when pinned.
- Pin action opens a dedicated pin-management popup with search and filtered selector controls.
- Selecting a spool in the pin-management popup closes the popup automatically.
- No-match tray popup no longer includes the legacy `Match Inserted Spool` action; matching is authoritative in `sensor.spoolman_tray_map`.
- Tray popup provides searchable `mushroom-select-card` pin pickers for all tray targets, showing descriptive spool labels from spool `friendly_name` and location.
- Search query filtering matches all typed words against spool ID, friendly name, and location.
- Search query helper is cleared automatically after a pin selection to avoid stale filters on subsequent opens.

### 5. Ambiguity UX

When automatic matching yields multiple candidates:
- mark tray as ambiguous
- provide candidate list
- allow one-tap pin from candidate row

Suggested tray-map metadata:
- match_state
- match_tier
- candidate_count
- candidate_spool_ids
- pin_active
- pin_spool_id

Implemented ambiguity behavior:
- When automatic matching yields unresolved multiple candidates, tray-map marks `match_state: ambiguous` and exposes candidate spool IDs for one-tap pin actions in popup UI.

## Architecture Alignment

Pinning should be implemented as an extension of the authoritative tray-map matcher, not a separate matching engine.

Design constraints:
- keep sensor.spoolman_tray_map as the single source of truth
- expose pin-aware result in tray_map payload
- keep script.resolve_matching_spool_from_tray_map as the canonical consumer contract
- ensure automations and manual workflows all consume the same resolved spool

## Integration Plan

### Phase A - Core pin storage and resolution

1. Add per-tray input_text override helpers.
2. Read helper values in spoolman_tray_map and apply override precedence.
3. Validate pinned spool exists and is eligible before use.
4. Emit pin state metadata in tray_map result.

### Phase B - Consumer alignment

1. Ensure active_tray_changed_update_spoolman consumes pin-aware resolution via resolver script.
2. Ensure print_complete-update_filament_usage consumes pin-aware resolution via resolver script.
3. Ensure manual matching actions can set and clear pin state intentionally.

### Phase C - Auto-clear and UX

1. Add automation(s) to clear pin on logical tray-content transitions.
2. Add pin/unpin controls to tray popup/detail templates.
3. Add ambiguity candidate rendering with pin action.

## Risks

| Scenario | Risk | Mitigation |
|---|---|---|
| Pin remains set after spool swap | High | auto-clear on UUID and Empty transitions |
| Pin references deleted/invalid spool | Medium | validate and ignore/clear invalid pin |
| Pin references sealed spool | Medium | eligibility check before applying pin |
| UUID and pin disagree | Low | keep UUID precedence |
| Consumer drift across scripts/automations | High | tray_map-authoritative resolution for all consumers |

## Future Consideration

Current policy is intentionally UUID-first:
- UUID > Pin > Auto fallback

Future optional mode (option 3) may be considered:
- Hybrid/Force Pin: allow an explicit user opt-in to override UUID only when deliberately enabled
- this must be explicit, reversible, and clearly indicated in UX to avoid accidental UUID bypass

## Test Matrix

| Scenario | Expected result |
|---|---|
| Pin set, UUID missing | pinned spool chosen |
| Pin set, UUID valid and unique | UUID wins |
| Pin set, spool removed | pin rejected or cleared; fallback/unknown behavior logged |
| Tray emptied | pin cleared |
| New spool inserted with new UUID | pin cleared |
| Ambiguous auto match | candidates shown; pin action resolves |

## Affected Files

| File | Change |
|---|---|
| homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/ | add per-tray pin helpers |
| homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/input_text_manual_spool_search_queries.yaml | add per-tray search query helpers for pin picker filtering |
| homeassistant/packages/3d_printing/spoolman_sync/template_sensors/template_select_tray_spool_pin_selectors.yaml | add 9 searchable tray pin select entities |
| homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml | add pin override tier and pin metadata |
| homeassistant/packages/3d_printing/spoolman_sync/scripts/resolve_matching_spool_from_tray_map-script.yaml | expose pin-aware response fields |
| homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml | consume pin-aware resolution |
| homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml | consume pin-aware resolution |
| homeassistant/packages/3d_printing/spoolman_sync/automations/clear_manual_spool_override_on_tray_change.yaml | clear pin on logical tray-content change |
| homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml | compact pin action chip, dedicated pin popup, and ambiguity actions |
| homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_detail.yaml | pin indicator rendering |
