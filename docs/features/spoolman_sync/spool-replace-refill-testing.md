# Spool Replace / Refill — Phase 1 Testing Plan

> **Created:** 2026-03-26  
> **Companion to:** [spool-replace-refill-design.md](spool-replace-refill-design.md)  
> **Status:** Ready for execution

---

## Automated Tests (Completed)

These tests were executed automatically via Python scripts and all passed.

### Test 1: YAML Syntax Validation — 17/17 PASSED

All Phase 1 files parse as valid YAML:
- 3 scripts, 6 input_booleans, 2 input_selects, 2 input_texts, 4 wizard steps

### Test 2: Helper Entity Schema Validation — ALL PASSED

- All `input_boolean` helpers have correct `initial`, `name`, and `icon` fields
- `input_select.spool_replace_desiccant_mode` has correct 3 options and default `"Reset to today"`
- `input_select.spool_replace_target_picker` has `"No sealed spools found"` fallback
- Both `input_text` helpers have `max: 10`, `initial: ""`

### Test 3: Script Structure Validation — ALL PASSED

**spool_replace_execute:**
- Has `alias`, `description`, `icon`, `sequence`
- Uses `spoolman.patch_spool`, `homeassistant.reload_config_entry`, `system_log.write`, `logbook.log`, `input_text.set_value`
- Implements read-merge-write pattern for extra fields (critical)
- Validates spool IDs before proceeding (`src_id <= 0 or tgt_id <= 0`)
- Clears workflow state helpers at end

**spool_replace_populate_candidates:**
- Has required `filament_id` input field
- Filters by `extra_sealed`, `archived`, and `filament_id`
- Has "No sealed spools found" fallback for empty results

**spool_replace_sync_target_from_picker:**
- Extracts numeric spool ID from `"#ID — ..."` format using split/replace

### Test 4: Wizard Popup Chain Integrity — ALL PASSED

- Step 1 → Step 2 → Step 3 → Step 4 chain is intact
- All steps have Cancel button and close_popup action
- Transition delays (500ms) present between all steps
- Step 4 references `script.spool_replace_execute`

### Test 5: Catalog Popup Launch Sequence — ALL PASSED

The Replace button in `catalog_spool_popup.yaml`:
- Sets `input_text.spool_replace_source_spool_id`
- Clears `input_text.spool_replace_target_spool_id`
- Resets all 6 `input_boolean` helpers to design defaults
- Resets `input_select.spool_replace_desiccant_mode` to `"Reset to today"`
- Calls `script.spool_replace_populate_candidates`
- Opens `spool_replace_wizard_step1`

### Test 6: Wizard Step Content Validation — ALL PASSED

**Step 1:** Reads source spool ID, shows `remaining_weight`, handles positive/negative/zero weight with appropriate banners, shows color swatch + location  
**Step 2:** References target picker dropdown, shows source spool summary, shows filament name  
**Step 3:** Includes all 7 transfer option entities, shows source → target header  
**Step 4:** Uses markdown summary, references all option helpers, green Execute button, calls execute script

### Test 7: Existing Test Suite Regression — 26/26 PASSED

All 26 existing `spool_matching` tests continue to pass, confirming Phase 1 changes don't break existing functionality.

---

## Manual / Coordinated Tests

These tests require running against a live Home Assistant instance with Spoolman integration and browser_mod. Execute in the order listed.

### Prerequisites

- [ ] HA instance is running with Spoolman integration active
- [ ] `browser_mod` is installed and configured
- [ ] At least one **unsealed** spool in Spoolman with `remaining_weight = 0` (or close to it)
- [ ] At least one **sealed** spool of the **same filament_id** as the unsealed spool
- [ ] Filament Catalog dashboard is accessible at `/3d-printing`
- [ ] Custom `button-card` LOVELACE component installed

### Test Setup (Do Once)

If you don't have the test spools already, create them in Spoolman:
1. **Source spool** (to be replaced): Any unsealed spool, note its `spool_id` and `filament_id`
2. **Target spool** (replacement): A sealed spool of the SAME `filament_id`, with `extra.sealed = "true"`

---

### M1: Replace Button Visibility — Spool Popup

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open the Filament Catalog dashboard | Catalog loads normally |
| 2 | Click any **unsealed** spool to open its popup | Spool popup opens |
| 3 | Check the bottom action row | **♻ Replace** button is the LEFT-MOST button |
| 4 | Verify button order | Replace → Spoolman → Reload → Close |
| 5 | Check that there is NO standalone "Location" button in the bottom row | Location is only in the "Change Location" dropdown row above |
| 6 | Click a **sealed** spool to open its popup | Verify Replace button behavior (may differ for sealed spools in future phases) |

**Result:** [X] Pass / [ ] Fail  
**Notes:** ___

---

### M2: Qty to Order — Spool Popup

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open an unsealed spool popup | Popup opens |
| 2 | Find the "Qty to Order" KPI card (right of "Total") | Card shows current qty value |
| 3 | If qty is 0, check `-` button | `-` button should be visually dimmed (opacity 0.6) and non-functional |
| 4 | Click `+` button | Qty increments to 1 (may require popup reopen to see update) |
| 5 | Click `+` again | Qty increments to 2 |
| 6 | Click `-` | Qty decrements to 1 |
| 7 | Click `-` again | Qty goes to 0, `-` becomes dimmed again |
| 8 | Verify in Spoolman the `extra.purchase_qty` field matches | Spoolman reflects the correct value |

**Result:** [X] Pass / [ ] Fail  
**Notes:** ___

---

### M3: Qty to Order — AMS Tray Popup

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open an AMS tray popup with a matched spool | Popup opens |
| 2 | Find the "Qty to Order" KPI card | Card shows current qty value |
| 3 | Test `+` and `-` buttons (same as M2 steps 3-7) | Same behavior as spool popup |
| 4 | Verify Spoolman sync | Values match Spoolman `extra.purchase_qty` |

**Result:** [X] Pass / [ ] Fail  
**Notes:** ___

---

### M4: Wizard Step 1 — Empty Spool (0g)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open a spool popup for a spool with **0g remaining** | Popup opens |
| 2 | Click **♻ Replace** button | Current popup closes, Step 1 popup opens after 500ms |
| 3 | Verify popup title | "♻ Replace Spool — Step 1 of 4" |
| 4 | Verify source spool info card | Shows spool name, ID, location, color swatch, "0.0 g remaining" |
| 5 | Verify banner | **Green** "Spool is confirmed empty" banner (no warning) |
| 6 | Click **"Continue to Step 2"** | Step 1 closes, Step 2 opens |
| 7 | Click **"Cancel"** instead (relaunch wizard first) | Popup closes, no state changes |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M5: Wizard Step 1 — Spool With Weight (>0g)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open a spool popup for a spool with **>0g remaining** (e.g., 50g) | Popup opens |
| 2 | Click **♻ Replace** | Step 1 popup opens |
| 3 | Verify banner | **Orange/amber** warning: "This spool still shows {X}g remaining. Are you sure it's empty?" |
| 4 | Verify "will be reset to 0g" text | Present in the warning |
| 5 | Click **"Yes, It's Empty — Continue"** | Step 2 opens |

**Result:** [X] Pass / [ ] Fail  
**Notes:** ___

---

### M6: Wizard Step 1 — Negative Weight Spool

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open a spool with **negative remaining weight** | Popup opens |
| 2 | Click **♻ Replace** | Step 1 popup opens |
| 3 | Verify banner | **Blue** info banner: "This spool shows {X}g (negative). Weight will be reset to 0g before archiving." |
| 4 | Click **Continue** | Step 2 opens |

> **Note:** To test this, you may need to manually set a spool's remaining_weight to a negative value in Spoolman.

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M7: Wizard Step 2 — Select Replacement (Candidates Available)

| Step | Action                                                     | Expected Result                                                          |
| ---- | ---------------------------------------------------------- | ------------------------------------------------------------------------ |
| 1    | Ensure at least 1 sealed spool of the same filament exists | Ready                                                                    |
| 2    | Complete Step 1 to reach Step 2                            | Step 2 popup opens                                                       |
| 3    | Verify title                                               | "♻ Replace Spool — Step 2 of 4"                                          |
| 4    | Verify subtitle                                            | "Showing sealed spools of {filament} ({vendor})"                         |
| 5    | Verify source spool card                                   | Shows color swatch + "Replacing: {name} #{id}"                           |
| 6    | Verify picker dropdown                                     | Shows sealed candidate(s) in format "#ID — Name — 📍 Location — Wg"      |
| 7    | Select a different candidate (if multiple exist)           | Dropdown changes selection                                               |
| 8    | Click **"Continue to Step 3"**                             | Step 3 opens, `input_text.spool_replace_target_spool_id` updated         |
| 9    | Verify in Developer Tools → States                         | `input_text.spool_replace_target_spool_id` = selected spool's numeric ID |

**Result:** [X] Pass / [ ] Fail  
**Notes:** ___

---

### M8: Wizard Step 2 — No Sealed Candidates

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Pick a spool whose filament has NO sealed spools (or temporarily unseal all) | Ready |
| 2 | Navigate to Step 2 | Step 2 opens |
| 3 | Verify picker dropdown | Shows "No sealed spools found" as only option |
| 4 | Click **"Continue to Step 3"** | Behavior should handle gracefully (target_spool_id = "0") |

> **Note:** The wizard should ideally prevent proceeding when no valid candidate is selected. If it proceeds with ID "0", the execute script will catch this with its validation guard and show a persistent_notification error.

**Result:** [X] Pass / [ ] Fail  
**Notes:** ___

---

### M9: Wizard Step 3 — Configure Transfer Options

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Complete Steps 1-2 to reach Step 3 | Step 3 opens |
| 2 | Verify title | "♻ Replace Spool — Step 3 of 4" |
| 3 | Verify source → target header | Shows "#SRC ... → #TGT ..." with color swatches |
| 4 | Verify default toggle states | Copy Spool Type: ON, Copy Clip Type: ON, Copy Desiccant Present: ON, Copy Location: ON, Mark Used: OFF, Archive: ON |
| 5 | Verify desiccant mode dropdown | Shows "Reset to today" as default |
| 6 | Toggle each boolean OFF and back ON | All toggles respond immediately |
| 7 | Change desiccant mode to "Copy from old spool" | Dropdown updates |
| 8 | Change desiccant mode to "Skip" | Dropdown updates |
| 9 | Click **"Review & Execute"** | Step 4 opens |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M10: Wizard Step 4 — Review Summary

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Complete Steps 1-3 with **all options ON** | Step 4 opens |
| 2 | Verify title | "♻ Replace Spool — Step 4 of 4" |
| 3 | Verify Source section | Shows spool name + ID, "Weight will be reset to 0g", "Will be archived" |
| 4 | Verify Target section | Shows "unsealed", copy spool type, copy clip type, desiccant mode text, copy desiccant present, set location |
| 5 | Verify "Mark as used now" | Present if you toggled it ON in Step 3 |
| 6 | Verify Execute button | Green (#4CAF50), labeled "Execute" |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M11: Full End-to-End Execution — All Options ON

> **WARNING:** This test modifies Spoolman data. Use test spools or be prepared to undo changes.

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Note the source spool's current state in Spoolman (weight, extra fields, location) | Recorded |
| 2 | Note the target spool's current state (extra fields, archived status, location) | Recorded |
| 3 | Run the full wizard: source (>0g) → select target → all options ON + desiccant "Reset to today" → Execute | Script runs |
| 4 | Wait 2-3 seconds for execution | Popup should close after ~2s |
| 5 | Open Developer Tools → States | |
| 6 | Check `input_text.spool_replace_source_spool_id` | Should be empty `""` (cleared) |
| 7 | Check `input_text.spool_replace_target_spool_id` | Should be empty `""` (cleared) |
| 8 | **In Spoolman:** Check source spool | `remaining_weight = 0`, `archived = true` |
| 9 | **In Spoolman:** Check target spool extra fields | `sealed = "false"`, `date_opened` = today's ISO date |
| 10 | **In Spoolman:** Check target spool type / clip type | Copied from source spool |
| 11 | **In Spoolman:** Check target desiccant_filled | Set to today's ISO date ("Reset to today") |
| 12 | **In Spoolman:** Check target desiccant_in_spool | Copied from source |
| 13 | **In Spoolman:** Check target location | Copied from source spool's location |
| 14 | **In HA:** Check that source spool entity has disappeared | Entity `sensor.spoolman_spool_{src_id}` no longer exists (archived) |
| 15 | **In HA:** Check logbook | Entry: "Replaced spool #SRC with spool #TGT" |
| 16 | **In HA:** Check system log | Entry from `homeassistant.components.bambulab.spool_replace` |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M12: Execution — Archive OFF

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Run wizard with **Archive Empty Spool = OFF** | Execute |
| 2 | Check source spool in Spoolman | `remaining_weight = 0` but `archived = false` (still active) |
| 3 | Check source entity in HA | Still exists |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M13: Execution — All Options OFF (Minimum)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Run wizard with ALL booleans OFF, desiccant mode "Skip" | Execute |
| 2 | Check target spool in Spoolman | Only `sealed = "false"` and `date_opened` should change |
| 3 | Verify no spool type, clip type, desiccant changes on target | Only sealed/date_opened changed |
| 4 | Verify source spool not archived | `archived = false` |
| 5 | Verify source weight still reset to 0 | `remaining_weight = 0` (always happens) |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M14: Cancel at Each Step — No Side Effects

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Launch wizard, cancel at Step 1 | Only `input_text.spool_replace_source_spool_id` is set (expected) |
| 2 | Launch wizard, proceed to Step 2, cancel | Source ID set, target picker populated (also expected — no Spoolman changes) |
| 3 | Launch wizard, proceed to Step 3, cancel | Same — no Spoolman changes |
| 4 | Verify in Spoolman | No spool data was modified in any of the above |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M15: Execute Script Validation Guard

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | In Developer Tools → Services, call `script.spool_replace_execute` directly | Script runs |
| 2 | With `input_text.spool_replace_source_spool_id = ""` and target = "" | |
| 3 | Verify a persistent notification appears | Title: "Spool Replace Error", message: "Invalid source or target spool ID" |
| 4 | Verify the script stopped (no Spoolman changes) | No spool modifications |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M16: Read-Merge-Write Extra Field Preservation

> **CRITICAL TEST** — Validates that the execution script doesn't overwrite unrelated extra fields on the target spool.

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Before running wizard, note ALL extra fields on the target spool (e.g., `purchase_qty`, `humidity_percent`, custom fields) | Recorded |
| 2 | Run the full wizard → Execute | Script runs |
| 3 | Check target spool in Spoolman | ALL pre-existing extra fields should still be present |
| 4 | Only `sealed`, `date_opened`, and the explicitly copied fields should have changed | Verified |
| 5 | Any unrelated extra fields (e.g., `purchase_qty`) should be unchanged | Verified |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M17: Desiccant Mode — "Copy from old spool"

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Ensure source spool has `extra.desiccant_filled` set to a specific date | Ready |
| 2 | Run wizard with desiccant mode = "Copy from old spool" | Execute |
| 3 | Check target spool in Spoolman | `extra.desiccant_filled` = source spool's original value (not today) |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M18: Desiccant Mode — "Skip"

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Run wizard with desiccant mode = "Skip" | Execute |
| 2 | Check target spool | `extra.desiccant_filled` is unchanged from its pre-wizard value |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

### M19: Mobile UI (iPhone / HA Companion App)

| Step | Action | Expected Result |
|------|--------|----------------|
| 1 | Open Filament Catalog on iPhone | Dashboard loads |
| 2 | Tap a spool → popup opens | Popup renders correctly on mobile |
| 3 | Tap **♻ Replace** | Wizard Step 1 opens as a modal |
| 4 | Navigate through all 4 steps | Popups render correctly, buttons have adequate tap targets |
| 5 | Verify all toggles in Step 3 are usable | Toggles respond to taps |
| 6 | Verify Step 4 summary is readable | No text overflow or clipping |
| 7 | Execute the flow | Completes successfully |

**Result:** [ ] Pass / [ ] Fail  
**Notes:** ___

---

## Post-Test Cleanup

After testing, if you used test/expendable spools:
1. Un-archive any source spools via Spoolman UI if needed
2. Re-seal any target spools if needed (`extra.sealed = "true"`)
3. Reset `extra.date_opened` on target spools if desired

---

## Summary

| Category | Tests | Status |
|----------|-------|--------|
| Automated: YAML Syntax | 17/17 | PASSED |
| Automated: Schema Validation | 10/10 | PASSED |
| Automated: Script Structure | 15/15 | PASSED |
| Automated: Chain Integrity | 20/20 | PASSED |
| Automated: Launch Sequence | 11/11 | PASSED |
| Automated: Content Validation | 22/22 | PASSED |
| Automated: Regression Suite | 26/26 | PASSED |
| Manual: M1-M19 | 19 tests | PENDING |
