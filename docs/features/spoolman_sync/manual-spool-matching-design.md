# Manual Spool Matching - Design Document

> Status: Design split for independent delivery
> Updated: 2026-03-20
> Scope: User-controlled pin/unpin matching for trays

## Purpose

This document defines manual spool matching behavior (pinning a specific spool to a tray), independent from automatic multi-color matching.

Automatic multi-color matching design lives in:
- [multicolor-spool-matching-design.md](multicolor-spool-matching-design.md)

## Problem Statement

Automatic matching can still be ambiguous or fail in real setups:
- Similar colors across multiple spools
- Incomplete metadata
- Temporary state drift

Users need an explicit, reliable way to select the spool in a tray.

## Functional Requirements

### 1. Per-tray override helpers

Create one helper per tray slot (9 total):
- `input_text.ams_1_tray_1_spool_override` ... `input_text.ams_2_tray_4_spool_override`
- `input_text.external_spool_spool_override`

Rules:
- Value is Spoolman spool ID or empty string
- Do not set `initial` (preserve recorder restore behavior)

### 2. Matching precedence

Manual override applies after UUID matching and before color-based matching:

1. UUID exact match
2. Manual override
3. Automatic color-based matching (single and multi-color tiers)
4. Unmatched

Rationale:
- UUID remains highest confidence source.
- Manual override is the operator-selected fallback.

### 3. Auto-clear behavior

Clear override when tray content meaningfully changes:
- `tray_uuid` changes to a new non-empty value
- `type` becomes `Empty`

Do not clear for informational changes:
- Remaining percentage
- Color updates
- Other telemetry noise

### 4. Dashboard UX

In tray popup and tray detail views:
- Add `Pin Spool` action
- Show active override indicator
- Add `Unpin` action
- Promote pinning as primary CTA when tray is unmatched

### 5. Ambiguity resolution UX

When automatic matching returns multiple candidates:
- Mark tray as `ambiguous`
- Provide candidate list in popup
- Allow one-tap pin from candidate row

Suggested payload fields:
- `match_state`
- `match_tier`
- `candidate_count`
- `candidate_spool_ids`

## Implementation Plan

### Phase A - Helpers and core logic

1. Add override helpers in spoolman sync helpers.
2. Wire helper lookup into `spoolman_tray_map`.
3. Support optional `override_spool_id` in legacy script path where still used.

### Phase B - Automation integration

1. Read per-tray override in `active_tray_changed_update_spoolman`.
2. Read per-tray override in `print_complete-update_filament_usage`.
3. Ensure deduction/update operations use overridden spool ID.

### Phase C - UX and auto-clear

1. Add pin/unpin controls in popup.
2. Add override badge/chip in tray detail.
3. Add auto-clear automation for tray content transitions.
4. Add ambiguity candidate rendering and pin action.

## Out of Scope

This document does not define multi-color detection logic, first-hex rules, or color fallback tiers.

Those are defined in:
- [multicolor-spool-matching-design.md](multicolor-spool-matching-design.md)

## Risks

| Scenario | Risk | Mitigation |
|---|---|---|
| Override left active after spool swap | High | Auto-clear automation on UUID/type transitions |
| Override points to deleted spool ID | Medium | Validate override ID and ignore invalid target |
| UI can pin sealed/ineligible spool | Medium | Filter pin candidates to valid unsealed set |
| UUID and override disagree | Low | Keep UUID precedence over override |

## Test Matrix

| Scenario | Expected result |
|---|---|
| Override set, UUID missing | Override spool chosen |
| Override set, UUID valid and unique | UUID wins |
| Override set, spool removed | Override ignored and reported invalid |
| Tray emptied | Override cleared |
| New spool inserted with new UUID | Override cleared |
| Ambiguous automatic match | Candidate list shown and pin action available |

## Deployment Independence

This manual design can be built and deployed separately from multi-color logic if:
- Existing automatic matching remains unchanged
- New helper entities and UI controls are introduced behind this feature only
- Automations consuming match results accept override-aware resolution

## Affected Files

| File | Change |
|---|---|
| `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/` | Add per-tray override helpers |
| `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml` | Add override tier and optional ambiguity metadata |
| `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml` | Optional override parameter support |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml` | Pass override into resolution path |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml` | Pass override into resolution path |
| `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml` | Pin/unpin controls and ambiguity candidate actions |
| `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_detail.yaml` | Override indicator rendering |
