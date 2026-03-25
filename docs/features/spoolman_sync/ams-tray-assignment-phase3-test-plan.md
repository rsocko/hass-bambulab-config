# AMS Tray Assignment Phase 3 — UI Integration Test Plan

## Scope

Validate Phase 3 UI integration behavior for:

- **"Set on Printer" chip** in the AMS tray popup (`ams_tray_popup.yaml`)
- **Assignment status chip** in the filament tag view (`view_filament_tags.yaml`)
- **Inline tray picker** in the filament tag view for pending assignments
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

### Section A: "Set on Printer" Chip in Tray Popup

#### T1 — Chip visible for matched spool with valid material

1. Open the AMS tray popup for a tray that has a matched spool (via UUID, pin, or auto-match).
2. Confirm the spool has valid `filament_material` (not `Unknown` or empty).
3. **Expected**: A green chip labeled **"Set on Printer"** with a `mdi:printer-3d-nozzle` icon appears below the pin/UUID chip area, above the Material/Vendor/Location chips.

#### T2 — Chip hidden when no spool matched

1. Open the AMS tray popup for a tray with **no matched spool** (the "No Spool" popup variant).
2. **Expected**: The "Set on Printer" chip does **not** appear. The popup shows the unmatched tray view with pin selection controls.

#### T3 — Chip hidden when material is Unknown

1. Open the tray popup for a tray matched to **Spool C** (missing material data).
2. **Expected**: The "Set on Printer" chip does **not** appear (canSetOnPrinter is false because material is 'Unknown').

#### T4 — Tap "Set on Printer" for non-Bambu spool

1. Open the tray popup for a tray matched to **Spool A** (non-Bambu, complete data).
2. Tap the **"Set on Printer"** chip.
3. **Expected**:
   - `script.assign_spool_to_printer_tray` is called with:
     - `spool_id` = Spool A's numeric ID
     - `tray_entity_id` = the tray's sensor entity
     - `force_write` = `true`
   - After ~2 seconds, the popup closes automatically.
   - `sensor.last_tray_assignment_result` state becomes `success`.
   - A persistent notification appears: "Tray Assignment Successful" with material, tray, and profile info.
4. Verify tray attributes:
   - Check `state_attr(tray_entity, 'type')` matches Spool A's material.
   - Check `state_attr(tray_entity, 'color')` matches expected RGBA hex.

#### T5 — Tap "Set on Printer" for Bambu spool (force_write bypass)

1. Open the tray popup for a tray matched to **Spool B** (Bambu Lab spool with UUID).
2. Tap the **"Set on Printer"** chip.
3. **Expected**:
   - `force_write: true` bypasses the RFID-skip guard.
   - `assign_spool_to_printer_tray` runs the full assignment flow.
   - Result is `success` (not `skipped`).
   - This verifies the design decision: explicit manual action overrides RFID non-interference.

#### T6 — Tap "Set on Printer" when tray has different filament data

1. Manually set a tray to have different filament info (e.g., via Bambu Studio or a previous assignment).
2. Open the popup for that tray (now showing a different matched spool).
3. Tap "Set on Printer."
4. **Expected**:
   - `force_write: true` bypasses the overwrite-confirmation guard.
   - The tray data is overwritten with the new spool's parameters.
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
     - Content: "⚠ Overwrite needed — use Set on Printer"

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

## Pass Criteria

Phase 3 is validated when:

- **All T1–T20 pass** with expected UI behavior and state changes
- No YAML parsing errors in HA logs for the modified dashboard files
- No JavaScript console errors in the browser during popup/view rendering
- The Phase 2 automated flow (T17, T18) still works end-to-end with the new UI enhancements
- The `conditional` card correctly shows/hides the status chip and tray picker based on entity states

## Troubleshooting Checks

- **Chips don't render**: Confirm `card-mod` and `mushroom-chips-card` HACS integrations are installed and updated.
- **config-template-card errors**: Check browser console for JS errors in `${}` template evaluation. Verify `entities` list includes all entities referenced in `variables`.
- **conditional card not hiding/showing**: Verify the entity state value is exactly as expected (e.g., empty string `""` not `null`). Use Developer Tools → States to inspect `input_text.pending_tray_assignment_spool_id` and `sensor.last_tray_assignment_result`.
- **"Set on Printer" chip missing in popup**: Verify `spoolId` is truthy and `material` is not `'Unknown'`. Add `console.log(canSetOnPrinter, spoolId, material)` temporarily in the popup JS to debug.
- **Tray picker buttons not calling script**: Verify `perform-action` syntax is correct for the Bubble Card version. Check that `script.assign_spool_to_printer_tray` accepts the `spool_id` as a string from the template expression.
- **Status chip not updating**: Verify `sensor.last_tray_assignment_result` updates when `spoolman_tray_assignment_result` event fires. Check Developer Tools → Events → listen for the event.
