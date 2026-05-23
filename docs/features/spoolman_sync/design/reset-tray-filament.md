# Reset Tray Filament Info — Design Document

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/reset-tray-filament-design.md
Replaced By: none

> **Status**: Implementation
> **Created**: 2026-03-26
> **Parent**: [AMS Tray Assignment Design](design/ams-tray-assignment.md)
> **Scope**: Clear/reset filament metadata on any AMS tray or external spool via HA UI

## Problem Statement

When a spool is physically removed from an AMS tray or the external spool holder, the printer retains the previous filament metadata (type, color, profile name, nozzle temps). This causes two issues:

1. **Stale matching**: `sensor.spoolman_tray_map` sees non-empty tray metadata and continuously tries to match it against Spoolman spools, showing "No matching spool" rather than "Empty."
2. **No HA-side reset**: The only way to clear this stale data is through Bambu Studio's "Reset" button (AMS Materials Setting → Reset) or Bambu Handy. There is no equivalent action in the HA dashboard.

Bambu Studio's Reset button exists on both AMS tray dialogs and the external spool dialog, and prompts "Are you sure you want to clear the filament information?" before executing.

## Goals

1. **Parity with Bambu Studio** — Provide a "Reset Tray" action in the HA tray popup UI that clears filament metadata, equivalent to Bambu Studio's Reset button
2. **Confirmation dialog** — Match Bambu Studio's UX with a confirmation prompt before clearing
3. **Both popup paths** — Available in the matched-spool popup (bottom row) AND the no-spool popup (for stale, unmatched trays)
4. **Pin cleanup** — Automatically clear any manual spool pin on the tray being reset
5. **Both tray types** — Works for AMS trays and external spool

## Non-Goals

- Physically unloading filament from the extruder (that's `bambu_lab.unload_filament`)
- Removing spool data from Spoolman (Spoolman state is untouched)
- Auto-resetting trays when spools are removed (future automation concern)

---

## Background: How Reset Works

### Bambu Studio Reset Button

The Reset button in Bambu Studio's "AMS Materials Setting" dialog sends the `ams_filament_setting` MQTT command with empty/zeroed values:

- `tray_info_idx`: `""` (empty string)
- `tray_color`: `"00000000"` (transparent black = empty marker)
- `tray_type`: `""` (empty string)
- `nozzle_temp_min`: `0`
- `nozzle_temp_max`: `0`

### ha-bambulab Integration

The `bambu_lab.set_filament` service wraps the same `ams_filament_setting` MQTT command. The service does **not** enforce non-empty validation on its parameters — empty strings and zero temperatures are passed through to the printer. This means `set_filament` with empty values is functionally identical to Bambu Studio's Reset.

**Guard condition**: The integration's `_service_call_set_filament` checks `ams_tray.empty` for AMS trays and returns early if the tray is already empty. This is a no-op guard — you'd only reset a tray that currently has filament info. For external spool, the empty check uses a different entity path, but the same principle applies.

**No dedicated service**: There is no `bambu_lab.reset_tray` or `bambu_lab.clear_filament` service. The reset operation is accomplished by calling `set_filament` with empty values.

---

## Implementation

### 1. New Script: `script.reset_tray_filament`

**File**: `spoolman_sync/scripts/reset_tray_filament-script.yaml`

A self-contained script that:

1. Validates the `tray_entity_id` input
2. Checks that the tray is not already empty (based on `type` attribute for AMS, `name` attribute for external spool)
3. Calls `bambu_lab.set_filament` with empty/zeroed values to clear the tray
4. Clears any active manual spool pin for the tray
5. Fires a `spoolman_tray_assignment_result` event with status `success` to update the status chip
6. Creates a persistent notification confirming the reset

**Service call payload**:

```yaml
action: bambu_lab.set_filament
data:
  entity_id: "{{ tray_entity_id }}"
  tray_info_idx: ""
  tray_color: "00000000"
  tray_type: ""
  nozzle_temp_min: 0
  nozzle_temp_max: 0
```

**Pin cleanup**: Uses the same `tray_key → input_text.*_spool_override` mapping used by `clear_manual_spool_override_on_tray_change.yaml`.

### 2. UI: Confirmation Popup

Both tray popup paths (matched spool and no-spool) will include a "Reset Tray" button that opens a nested `browser_mod.popup` confirmation dialog before executing.

**Confirmation dialog contents**:

- Warning icon (`mdi:alert`) with orange color
- Text: "Are you sure you want to clear the filament information?"
- Secondary text with tray label for context
- Two buttons: **OK** (calls the reset script, closes popup) and **Cancel** (closes popup)

This matches the Bambu Studio UX shown in the attached screenshots.

### 3. UI: Matched-Spool Popup (Bottom Row)

In the existing bottom row (`Details | Spoolman | Reload | Close`), a **Reset** button is added between Reload and Close. It is **conditionally visible** — hidden when `matchState === 'empty'` (tray already empty).

**Button styling**: Uses a warning color (`#c62828`, dark red) to distinguish it as a destructive action, matching the visual weight of the Unpin button.

### 4. UI: No-Spool Popup

A **Reset Tray** card is added after the pin control cards and before the error/missing helper cards. It is hidden when `matchState === 'empty'` (tray already empty — no point resetting an empty tray).

Uses `custom:button-card` styled as a full-width action button with `mdi:delete-sweep` icon.

---

## Visibility Logic

| Popup Path | Condition to Show Reset | Rationale |
|---|---|---|
| Matched spool (bottom row) | `matchState !== 'empty'` | Tray has filament info; user may want to clear it after removing the spool |
| No-spool popup | `matchState !== 'empty'` | Tray has stale metadata with no Spoolman match; clearing makes it truly empty |
| Either popup, tray already empty | Hidden | No-op — tray is already clear |

---

## Affected Files

### New Files

| File | Purpose |
|---|---|
| `spoolman_sync/scripts/reset_tray_filament-script.yaml` | Script: validates tray, calls `set_filament` with empty values, clears pin, fires result event |
| `docs/features/spoolman_sync/reset-tray-filament-design.md` | This design document |

### Modified Files

| File | Change |
|---|---|
| `common/dashboard_cards/card_templates/ams_tray_popup.yaml` | Add `resetTrayAction` variable (confirmation popup); add Reset button to matched-spool bottom row; add Reset Tray card to no-spool popup |
| `docs/features/spoolman_sync/design/ams-tray-assignment.md` | Reference this document in Phase 5 or add a new phase entry |
| `docs/features/printer_dashboards/reference/ams-tray-popup.md` | Document the new Reset Tray button in popup sections |

---

## Test Plan

### T1 — Reset external spool with filament info

1. External spool has non-empty filament metadata (type, color, profile).
2. Open external spool tray popup → bottom row shows "Reset" button.
3. Tap Reset → confirmation popup appears: "Are you sure you want to clear the filament information?"
4. Tap OK → popup closes, tray info is cleared.
5. Re-open popup → tray now shows as Empty (no-spool path, `matchState === 'empty'`).
6. Reset button is no longer visible.

### T2 — Reset AMS tray with matched spool

1. AMS tray has a matched spool in `spoolman_tray_map`.
2. Open tray popup → full matched-spool popup with bottom row.
3. Tap Reset → confirmation popup → OK.
4. Tray metadata is cleared; spool match is lost; tray reports Empty.

### T3 — Reset from no-spool popup (stale metadata)

1. AMS tray has filament metadata but no matching Spoolman spool.
2. Open tray popup → no-spool popup shows "No matching spool found."
3. Reset Tray button is visible below pin controls.
4. Tap Reset → confirmation → OK → tray is cleared to Empty.

### T4 — Already-empty tray (no Reset shown)

1. Tray is already Empty (`matchState === 'empty'`).
2. Open popup → no-spool popup shows.
3. Reset Tray button is NOT visible (hidden by `matchState` check).

### T5 — Pin cleanup on reset

1. Tray has an active manual spool pin (`input_text.*_spool_override` is set).
2. Reset the tray via the popup.
3. After reset, the pin helper value is cleared (empty string).

### T6 — Reset while printing (blocked)

1. Printer is actively printing.
2. Open tray popup → tap Reset → confirmation → OK.
3. Script checks printer status; if busy, shows deferred/blocked notification rather than calling `set_filament`.
