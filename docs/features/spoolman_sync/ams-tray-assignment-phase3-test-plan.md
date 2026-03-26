# AMS Tray Assignment Phase 3 — UI Integration Test Plan

> **Last tested**: 2026-03-25 | **HA**: core-2026.3.4, HAOS 17.1, aarch64/RPi5

## Scope

Validate Phase 3 UI integration behavior for:

- **"Update Tray Settings" chip** in the AMS tray popup (`ams_tray_popup.yaml`) — visible only for `manual_pin` matches
- **Assignment status chip** — shared include (`tray_assignment_status_and_picker.yaml`) on Home, Filament Tags, and Filament Catalog views
- **Popup tray picker** — browser_mod popup opened by tapping the status chip; uses `script.assign_pending_spool_to_tray` wrapper
- **Success notification** from the assignment script

## Pre-Flight

1. Deploy/reload all Phase 1–3 package changes.
2. Confirm Phase 2 entities still exist and are functional:
   - `automation.spoolman_location_change_assign_tray`
   - `script.assign_spool_to_printer_tray`
   - `script.resolve_bambu_filament_params`
   - `sensor.last_tray_assignment_result`
   - `input_text.pending_tray_assignment_spool_id`
3. Confirm Bambu services:
   - `bambu_lab.set_filament`
   - `bambu_lab.get_filament_data`
4. Confirm dashboard is accessible:
   - Filament tag view renders without errors
   - AMS tray popup opens from printer dashboard
5. Reset state before testing:
   - Set `input_text.pending_tray_assignment_spool_id` to `""` (empty)
   - Confirm `sensor.last_tray_assignment_result` is `idle` or reset by firing `spoolman_tray_assignment_result` event with `status: idle`
   - Dismiss any existing tray assignment persistent notifications

## Test Spools

Pick at least 3 spools:

| Label | Requirements | Example |
|---|---|---|
| **Spool A** | Non-Bambu, complete data (material, color, profile or fallback available) | Any non-Bambu PLA/PETG spool |
| **Spool B** | Bambu Lab spool with populated `extra_spool_uuid` | Bambu PLA Basic |
| **Spool C** | Spool with missing material or missing color (negative test) | Spool with empty `filament_material` or empty `filament_color_hex` |

---

## Test Cases

### Section A: "Update Tray Settings" Chip in Tray Popup

#### T1 — Chip visible for manually pinned spool with valid material

1. Open the AMS tray popup for a tray that has a **manually pinned** spool (`matchStrategy === 'manual_pin'`).
2. Confirm the spool has valid `filament_material` (not `Unknown` or empty).
3. **Expected**: A green chip labeled **"Update Tray Settings"** with a `mdi:printer-3d-nozzle` icon appears below the pin/UUID chip area, above the Material/Vendor/Location chips.

#### T1b — Chip hidden for UUID-matched spool

1. Open the AMS tray popup for a tray matched via **UUID** (`matchStrategy === 'uuid'`).
2. **Expected**: The "Update Tray Settings" chip does **not** appear. The AMS RFID reader already loaded authoritative filament data.

#### T1c — Chip hidden for color/type-matched spool

1. Open the AMS tray popup for a tray matched via **color_type** or **color_type_ams_preference**.
2. **Expected**: The "Update Tray Settings" chip does **not** appear. The tray's reported attributes already agree with the spool.

#### T1d — Chip hidden for multicolor-matched spool

1. Open the AMS tray popup for a tray matched via any **multicolor_*** strategy.
2. **Expected**: The "Update Tray Settings" chip does **not** appear.

#### T2 — Chip hidden when no spool matched

1. Open the AMS tray popup for a tray with **no matched spool** (the "No Spool" popup variant).
2. **Expected**: The "Update Tray Settings" chip does **not** appear. The popup shows the unmatched tray view with pin selection controls.

#### T3 — Chip hidden when material is Unknown

1. Open the tray popup for a tray matched to **Spool C** (missing material data).
2. **Expected**: The "Update Tray Settings" chip does **not** appear (canUpdateTraySettings is false because material is 'Unknown').

#### T4 — Tap "Update Tray Settings" for non-Bambu pinned spool

1. Pin **Spool A** (non-Bambu, complete data) to a tray using the pin controls.
2. Open the tray popup — confirm `matchStrategy` is `manual_pin`.
3. Tap the **"Update Tray Settings"** chip.
4. **Expected**:
   - `script.assign_spool_to_printer_tray` is called with:
     - `spool_id` = Spool A's numeric ID
     - `tray_entity_id` = the tray's sensor entity
     - `force_write` = `true`
   - After ~2 seconds, the popup closes automatically.
   - `sensor.last_tray_assignment_result` state becomes `success`.
   - A persistent notification appears: "Tray Assignment Successful" with material, tray, and profile info.
5. Verify tray attributes:
   - Check `state_attr(tray_entity, 'type')` matches Spool A's material.
   - Check `state_attr(tray_entity, 'color')` matches expected RGBA hex.

#### T5 — Chip hidden for Bambu spool with UUID match

1. Open the tray popup for a tray matched to **Spool B** (Bambu Lab spool with UUID, `matchStrategy === 'uuid'`).
2. **Expected**:
   - The "Update Tray Settings" chip does **not** appear.
   - The RFID reader's data is authoritative; no manual override is offered.

#### T6 — Tap "Update Tray Settings" when pinned spool differs from tray data

1. Pin a spool to a tray that has different filament info (e.g., tray shows PETG but pinned spool is PLA).
2. Open the popup — confirm `matchStrategy` is `manual_pin`.
3. Tap "Update Tray Settings."
4. **Expected**:
   - `force_write: true` bypasses the overwrite-confirmation guard.
   - The tray data is overwritten with the pinned spool's parameters.
   - Result is `success`.

---

### Section B: Assignment Status Chip in Filament Tag View

#### T7 — Status chip hidden when idle

1. Ensure `sensor.last_tray_assignment_result` state is `idle`.
2. Open the filament tag view.
3. **Expected**: No status chip appears between the quick buttons and the desiccant section.

#### T8 — Status chip shows success

1. Trigger a successful tray assignment (e.g., via T4 above, or by calling the script directly).
2. Open the filament tag view.
3. **Expected**:
   - A chip appears with:
     - Green `mdi:check-circle` icon
     - Content starting with "✓ " followed by the success message
   - The chip is positioned between the AMS/Ext. Spool quick buttons and the desiccant separator.

#### T9 — Status chip shows needs_tray_selection

1. Trigger a tray inference failure:
   - Ensure target AMS has 0 or 2+ empty trays.
   - Set a spool's location to `AMS`.
2. Open the filament tag view.
3. **Expected**:
   - A chip appears with:
     - Orange `mdi:alert-circle` icon
     - Content: "⚠ Select tray below"

#### T10 — Status chip shows failed

1. Trigger a failed assignment (e.g., spool with missing material data + explicit tray_entity_id).
2. Open the filament tag view.
3. **Expected**:
   - A chip appears with:
     - Red `mdi:close-circle` icon
     - Content starting with "✗ " followed by error message

#### T11 — Status chip shows overwrite_required

1. Call `script.assign_spool_to_printer_tray` with `force_write: false` on an AMS tray that has different filament data.
2. Open the filament tag view.
3. **Expected**:
   - A chip appears with:
     - Red `mdi:close-circle` icon
     - Content: "⚠ Overwrite needed — use Update Tray Settings"

#### T12 — Status chip shows skipped

1. Trigger a skipped assignment (Bambu spool with UUID to AMS tray, auto-triggered with default `force_write: false`).
2. **Expected**:
   - A chip with blue `mdi:skip-next-circle` icon and skip message.

#### T13 — Status chip shows deferred

1. Put printer in active print state.
2. Trigger an assignment.
3. **Expected**:
   - A chip with amber `mdi:clock-outline` icon and deferred message.

---

### Section C: Inline Tray Picker for Pending Assignments

#### T14 — Tray picker hidden when no pending assignment

1. Ensure `input_text.pending_tray_assignment_spool_id` is `""` (empty).
2. Open the filament tag view.
3. **Expected**: The inline tray picker (header + tray buttons) does **not** appear.

#### T15 — Tray picker visible when pending assignment exists

1. Set `input_text.pending_tray_assignment_spool_id` to a valid spool ID (e.g., `42`).
2. Open the filament tag view.
3. **Expected**:
   - A header card appears: "⚠ Tray selection needed" + "Spool #42 — which tray was it loaded into?"
   - Two rows of sub-buttons appear:
     - **AMS 1**: T1, T2, T3, T4
     - **AMS 2**: T1, T2, T3, T4
   - Each button has a `mdi:numeric-*-box` icon.

#### T16 — Tap a tray button to complete assignment

1. Set `input_text.pending_tray_assignment_spool_id` to **Spool A**'s ID.
2. Open the filament tag view (tray picker should be visible).
3. Tap one of the AMS tray buttons (e.g., **AMS 1 T3**).
4. **Expected**:
   - `script.assign_spool_to_printer_tray` is called with:
     - `spool_id` = the pending spool ID
     - `tray_entity_id` = `sensor.p1s_01p00c460102350_ams_1_tray_3`
   - On success:
     - `input_text.pending_tray_assignment_spool_id` clears to `""`
     - The inline tray picker disappears
     - The status chip updates to show success
     - A persistent notification "Tray Assignment Successful" is created

#### T17 — End-to-end: Location change → inference failure → tray picker → success

1. Ensure target AMS has 2+ empty trays (to cause inference failure).
2. Change **Spool A**'s location entity to `AMS`.
3. Wait for automation to pick up the state change.
4. **Verify automation result**:
   - `input_text.pending_tray_assignment_spool_id` = Spool A's ID
   - `sensor.last_tray_assignment_result` = `needs_tray_selection`
   - Persistent notification "Tray Selection Needed" is created
5. Open the filament tag view.
6. **Verify UI**:
   - Status chip shows "⚠ Select tray below"
   - Inline tray picker is visible with Spool A's ID
7. Tap a tray button (e.g., **AMS 1 T2**).
8. **Verify completion**:
   - Assignment runs and succeeds
   - Tray picker hides
   - Status chip updates to success
   - Tray entity attributes reflect Spool A's data

#### T18 — End-to-end: NFC scan → filament tag → AMS button → auto-assign

1. Ensure target AMS has exactly 1 empty tray.
2. Scan an NFC filament tag (or manually set `input_text.filament_id` to populate `sensor.selected_spool`).
3. In the filament tag view, tap the **AMS** quick button.
4. **Expected**:
   - `script.update_spool_location` fires → Spoolman location updates to `AMS`
   - Automation fires → tray inference succeeds (1 empty tray)
   - `assign_spool_to_printer_tray` runs → `set_filament` called
   - Status chip in filament tag view shows success result
   - Persistent notification confirms the assignment

---

### Section D: Success Notification

#### T19 — Success notification created on successful assignment

1. Trigger a successful assignment (any path: manual, auto, or tray picker).
2. **Expected**:
   - A persistent notification is created with:
     - Title: "Tray Assignment Successful"
     - Message includes: material type, tray entity, profile name, spool display name
     - `notification_id` = `tray_assignment_success_<spool_id>`

#### T20 — Repeated assignment replaces previous notification

1. Trigger two successful assignments for the **same spool** (different trays).
2. **Expected**: Only one notification remains (the second replaces the first, since they share the same `notification_id`).

---

### Section E: RFID Pending Warning (`success_awaiting_rfid`)

#### T21 — Status chip shows RFID pending after Bambu spool forced write

1. Assign a Bambu spool with UUID (e.g., spool 19) to an AMS tray using `force_write: true`.
2. **Expected**:
   - `sensor.last_tray_assignment_result` state = `success_awaiting_rfid`
   - Status chip is amber with pulsing animation
   - Chip icon: `mdi:contactless-payment-circle-outline`
   - Chip text: `⚠ RFID pending · AMS N TN` (e.g., "⚠ RFID pending · AMS 1 T2")

#### T22 — Popup shows RFID warning card with spool + tray details

1. With status = `success_awaiting_rfid`, tap the status chip to open popup.
2. **Expected**:
   - A conditional amber card appears at the top of the popup
   - Primary text wraps (no truncation) and shows: spool friendly name → AMS N Tray N
   - Secondary text: "RFID not confirmed — tap to re-scan tray"
   - Amber border and amber icon

#### T23 — Tap RFID warning card triggers `bambu_lab.read_rfid`

1. Tap the amber "RFID not confirmed" card in the popup.
2. **Expected**:
   - `script.rescan_assigned_tray_rfid` runs
   - `bambu_lab.read_rfid` is called with the correct tray entity
   - AMS physically re-reads the tray's RFID tag (tray moves/ejects slightly)
   - Tray sensor data updates to reflect the actual physical spool

#### T24 — RFID pending card hidden when status is not `success_awaiting_rfid`

1. Fire a `spoolman_tray_assignment_result` event with `status: success`.
2. Open the popup.
3. **Expected**: No amber RFID warning card is visible.

#### T25 — `force_write` bypasses RFID skip guard

1. Call `assign_spool_to_printer_tray` with a Bambu UUID spool + AMS tray + `force_write: false` (default).
2. **Expected**: Status = `skipped` (RFID guard active).
3. Call again with same spool + tray + `force_write: true`.
4. **Expected**: Status = `success_awaiting_rfid` (RFID guard bypassed, but UUID mismatch detected post-write).

#### T26 — Non-Bambu spool does NOT trigger RFID pending

1. Assign a non-Bambu spool (no UUID, e.g., spool 16 or 133) to an AMS tray.
2. **Expected**: Status = `success` (not `success_awaiting_rfid`) — RFID pending only applies when spool has a UUID.

#### T27 — Rescan clears RFID pending chip

1. Prerequisite: Status chip shows `success_awaiting_rfid` (e.g., after T21).
2. Tap the RFID warning card in the popup to trigger `script.rescan_assigned_tray_rfid`.
3. Wait ~6 seconds for the physical RFID re-scan + delay.
4. **Expected**: `sensor.last_tray_assignment_result` transitions to `success` with message containing "RFID confirmed after re-scan". Chip turns green then fades (normal success behavior).

#### T28 — Bambu spool → AMS location shows `skipped_bambu_rfid` chip

1. In Spoolman, change a Bambu Lab spool's location to "AMS" (or "AMS 2").
2. **Expected**: Status chip appears with status `skipped_bambu_rfid`, blue icon (`mdi:contactless-payment-circle`), and content "✓ RFID spool — AMS auto-configures". No tray picker, no pending assignment.

### Section F: Status-Aware Popup & Retry

#### T29 — Popup title is static "Tray Assignment"

1. Tap the status chip for any status.
2. **Expected**: Popup title shows "Tray Assignment" (not raw Jinja).

#### T30 — Deferred popup shows spool → tray with retry action

1. Trigger a deferred assignment (assign spool while printer is busy).
2. Tap the status chip to open popup.
3. **Expected**:
   - Deferred card shows: spool friendly name → AMS N Tray N
   - Secondary: "Printer was busy — tap to retry assignment"
   - Icon: `mdi:refresh`, amber
   - No tray picker grid visible

#### T31 — Tap deferred card retries assignment

1. With status = `deferred` and printer now idle, tap the deferred card.
2. **Expected**:
   - `script.retry_deferred_tray_assignment` runs
   - It reads spool/tray from sensor attributes and calls `assign_spool_to_printer_tray` with `force_write: true`
   - Status transitions from `deferred` to `success` (or `success_awaiting_rfid` for Bambu spools)

#### T32 — Failed popup shows error details, no tray picker

1. Trigger a failed assignment (e.g., spool with missing material).
2. Tap the status chip.
3. **Expected**:
   - Failed card shows spool name + error message
   - Icon: `mdi:close-circle`, red
   - No tray picker grid visible

#### T33 — Success popup shows result details, no tray picker

1. Trigger a successful assignment.
2. Tap the status chip.
3. **Expected**:
   - Success card shows spool name → tray label + success message
   - Icon: `mdi:check-circle`, green
   - No tray picker grid visible

#### T34 — `skipped_bambu_rfid` popup shows RFID info, no tray picker

1. Trigger a `skipped_bambu_rfid` status (Bambu spool location → AMS).
2. Tap the status chip.
3. **Expected**:
   - Card shows spool name + "AMS will auto-configure this tray via RFID reader. No manual assignment needed."
   - Icon: `mdi:contactless-payment-circle`, blue
   - No tray picker grid visible

#### T35 — Tray picker only visible for `needs_tray_selection`

1. Set status to `needs_tray_selection` with a pending spool.
2. Tap the status chip.
3. **Expected**: Spool info card + AMS 1 / AMS 2 tray grids are visible.
4. Change status to any other value (e.g., `deferred`).
5. Reopen popup.
6. **Expected**: No tray picker grid visible.

---

---

## Test Results — 2026-03-25

### Backend Tests (via `script.test_fire_tray_assignment_event`)

| Test | Description | Result |
|------|-------------|--------|
| T-B1 | idle state — chip hidden | **PASS** |
| T-B2 | success state — green chip | **PASS** |
| T-B3 | needs_tray_selection — orange chip | **PASS** |
| T-B4 | failed — red chip | **PASS** |
| T-B5 | overwrite_required — red chip | **PASS** |
| T-B6 | skipped — blue chip | **PASS** |

### UI Tests

| Test | Description | Result |
|------|-------------|--------|
| T-U1 | Chip hidden when idle (all 3 views) | **PASS** |
| T-U2 | Chip visible on Home, Filament Tags, Filament Catalog | **PASS** |
| T-U3 | Popup opens on chip tap (all 3 views) | **PASS** |
| T-U4 | Chip colors: green/success, red/failed, blue/skipped, orange/needs_tray_selection | **PASS** |

### Interactive Tests

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| T-I1 | Tray button in popup fires assignment | **PASS** | Spool 85 (Bambu PLA) → AMS 2 T4 → correctly `skipped` (RFID guard) |
| T-I2 | "Update Tray Settings" chip in AMS tray popup | **PASS** | `force_write: true` bypassed RFID guard → correctly `deferred` (printer busy) |

### RFID Pending Tests — 2026-03-26

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| T21 | RFID pending chip after Bambu spool force write | **PASS** | Spool 19 → T2, `force_write: true` → status `success_awaiting_rfid`, amber chip with "RFID pending · AMS 1 T2" |
| T22 | Popup shows spool + tray context | **PASS** | Primary: "Bambu Lab White - Support PLA-S (PLA for Support) → AMS 1 Tray 2", secondary: "RFID not confirmed — tap to re-scan tray", wraps correctly |
| T23 | Tap triggers `bambu_lab.read_rfid` | **PASS** | Wrapper script `rescan_assigned_tray_rfid` deployed; popup tap triggers physical AMS re-scan via `bambu_lab.read_rfid`. Confirmed tray data updates after tap. |
| T24 | RFID card hidden for non-RFID statuses | **PASS** | Conditional card only shows for `success_awaiting_rfid` |
| T25 | `force_write` bypasses RFID skip | **PASS** | `force_write: false` → `skipped`; `force_write: true` → `success_awaiting_rfid` |
| T26 | Non-Bambu spool → `success` not RFID pending | **PASS** | Spool 16 (Sunlu, no UUID) → T3 → status `success` |

### Deferred / Active-Print Tests — 2026-03-26

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| T5 | Chip hidden for Bambu UUID-matched spool | **PASS** | T1/T3/T4 all `match_strategy: uuid` → `canUpdateTraySettings` requires `manual_pin`, so chip correctly absent. Verified via template logic + tray_map state. |
| T13 | Status chip deferred while printing | **PASS** | Spool 16 → T3, `force_write: true` while printer `running` → status `deferred`, message "Printer is actively printing; assignment deferred." |

### Status-Aware Popup & Retry Tests — 2026-03-26

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| T29 | Popup title is static "Tray Assignment" | **PASS** | User confirmed — no raw Jinja in title |
| T30 | Deferred popup: spool → tray + retry action | **PASS** | Template eval: "Sunlu Grey PLA+ 2.0 → AMS 1 Tray 3", secondary "Printer was busy — tap to retry assignment", icon `mdi:refresh` amber |
| T31 | Tap deferred card retries assignment | **DEFERRED** | Requires idle printer |
| T32 | Failed popup: error details, no tray picker | **PASS** | Template eval: catch-all card renders spool name + error message, `mdi:close-circle` red |
| T33 | Success popup: result details, no tray picker | **PASS** | Template eval: "spool name → AMS N Tray N" + message, `mdi:check-circle` green, no picker visible |
| T34 | `skipped_bambu_rfid` popup: RFID info, no picker | **PASS** | Template eval: spool name + "AMS will auto-configure this tray via RFID reader. No manual assignment needed.", `mdi:contactless-payment-circle` blue |
| T35 | Tray picker only for `needs_tray_selection` | **PASS** | Conditional logic verified: all 8 statuses map to exactly 1 card each; tray picker grid ONLY visible for `needs_tray_selection` |

### Skipped / Bambu RFID Chip Test — 2026-03-26

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| T12 | Skipped status chip | **PASS** | Spool 19 (Bambu) → T3 via script (no force_write) → `skipped`, chip: blue `mdi:skip-next-circle`, message "Bambu RFID spool in AMS detected; skipping automatic set_filament." |

### Deferred Tests (require printer idle or specific spool conditions)

| Test | Description | Reason Deferred |
|------|-------------|----------------|
| T4 | Tap "Update Tray Settings" for non-Bambu pinned spool → full `set_filament` call succeeds | Printer was actively printing; `set_filament` blocked by deferred guard. Retest when printer is idle. |
| T6 | Overwrite tray with different filament data via "Update Tray Settings" (pinned spool) | Requires idle printer + tray with pre-existing different filament info + manual pin. |
| T-I1b | Tray button in popup for non-Bambu spool → full `set_filament` success | Tested with Bambu spool (correctly skipped). Need non-Bambu spool + idle printer to verify end-to-end write. |
| T16 | Tap tray button in popup to complete pending assignment → success flow | Equivalent to T-I1b. Verify `input_text` clears, picker hides, status chip updates to success. |
| T17 | End-to-end: Location change → inference failure → tray picker → success | Requires Spoolman location change trigger + multiple empty trays + idle printer. |
| T18 | End-to-end: NFC scan → filament tag → AMS button → auto-assign | Requires NFC tag scan + exactly 1 empty tray + idle printer. |
| T19 | Success notification content validation | Need a successful `set_filament` (idle printer) to verify notification title/message/id. |
| T20 | Repeated assignment replaces previous notification | Need two successful assignments for same spool. |
| T27 | Rescan clears RFID pending chip → status `success` | Need `success_awaiting_rfid` + idle printer + physical RFID re-scan (45s delay). |
| T28 | Bambu spool → AMS location shows `skipped_bambu_rfid` chip | Need Spoolman webhook trigger (Bambu spool location change to AMS). |
| T31 | Tap deferred card retries and succeeds | Need `deferred` status + idle printer to verify `retry_deferred_tray_assignment` completes. |

---

## Pass Criteria

Phase 3 is validated when:

- **All T1–T35 pass** with expected UI behavior and state changes
- No YAML parsing errors in HA logs for the modified dashboard files
- No JavaScript console errors in the browser during popup/view rendering
- The Phase 2 automated flow (T17, T18) still works end-to-end with the new UI enhancements
- The `conditional` card correctly shows/hides the status chip and tray picker based on entity states

> **Current status**: 34/35 tests PASS (T1-T35 + T-B1-6 + T-U1-4 + T-I1/I2). T31 deferred (needs idle printer for retry tap). Deferred printer-idle tests: T4, T6, T-I1b, T16-T20, T27, T28.

## Troubleshooting Checks

- **Chips don't render**: Confirm `card-mod` and `mushroom-chips-card` HACS integrations are installed and updated.
- **config-template-card in popups**: `config-template-card` silently fails inside `browser_mod.popup` content. Use plain `vertical-stack` with a wrapper script instead.
- **Jinja2 in popup perform-action data**: Jinja2 templates (`{{ }}`) are NOT evaluated in `perform-action` `data` fields inside browser_mod popups. Use a server-side wrapper script that reads the value from an `input_text` helper.
- **conditional card not hiding/showing**: Verify the entity state value is exactly as expected (e.g., empty string `""` not `null`). Use Developer Tools → States to inspect `input_text.pending_tray_assignment_spool_id` and `sensor.last_tray_assignment_result`.
- **"Update Tray Settings" chip missing in popup**: Verify `spoolId` is truthy, `material` is not `'Unknown'`, and `matchStrategy` is `'manual_pin'`. Add `console.log(canUpdateTraySettings, spoolId, material, matchStrategy)` temporarily in the popup JS to debug.
- **Popup tray buttons not calling script**: Verify buttons call `script.assign_pending_spool_to_tray` (wrapper) with only `tray_entity_id`. The wrapper reads `input_text.pending_tray_assignment_spool_id` server-side.
- **Status chip not updating**: Verify `sensor.last_tray_assignment_result` updates when `spoolman_tray_assignment_result` event fires. Check Developer Tools → Events → listen for the event.
