# Spool Replace / Refill — Popup Wireframes & Implementation Checklist

> **Companion to:** [spool-replace-refill-design.md](spool-replace-refill-design.md)

---

## Popup Wireframes

### Spool Popup — "More Actions" Button Placement

```
┌─────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────────────┐ │
│ │  [COLOR BANNER]  Bambu Lab PLA Basic White  │ │ ← existing
│ │  Spool #42 · AMS                            │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│  Material: PLA  ·  Vendor: Bambu Lab  ·  AMS   │ ← existing chips
│                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ 123.4 g  │ │ $0.098/g │ │ 856.2g (4 pools) ││ ← existing KPIs
│  │Remaining │ │Cost per g│ │ Total            ││
│  └──────────┘ └──────────┘ └──────────────────┘│
│                                                 │
│  ┌───────────────────────┐┌────────────────────┐│
│  │ 🌡️ Dried: Mar 1, 2026 │[🔥]│ 💧 Desiccant: 23d│[💦]│ ← bubble cards
│  │     (bubble card)      │    │   (bubble card)  │    │   50% each
│  └───────────────────────┘└────────────────────┘│   sub-btns: Mark
│                                                 │
│  📦 3 other spools of same filament (expand)    │ ← existing
│                                                 │
│  [chart: weight history]                        │ ← existing
│                                                 │
│  📍 Change Location: [AMS          ▼]          │ ← existing
│                                                 │
│  ┌─────────────────────────────────────────────┐│
│  │ bubble-card sub-buttons:                    ││ ← MODIFIED
│  │ [📍 Location] [🧵 Spoolman] [🔄 Reload] [✕] ││   all bubble
│  └─────────────────────────────────────────────┘│   card style
│                                                 │
│  ▼ MORE ACTIONS (expanded on tap)               │ ← NEW
│  ┌─────────────────────────────────────────────┐│
│  │ ♻  Replace / Refill Spool                   ││
│  │    Swap this spool for a sealed replacement  ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**For sealed spools**, the "More" button is replaced by a direct **"Unseal & Use"** sub-button in the bottom bubble card row.

### AMS Tray Popup — "Replace Spool" Button Placement

> **Note:** This button is only visible when the tray has a matched spool (`match_state === 'matched'`). When a spool runs out mid-print, the Bambu Lab integration clears the tray data, so `spoolman_tray_map` reports `match_state: 'empty'` and the button will not appear. In that scenario, the user is guided via a **Filament Runout Notification** (Phase 2) to find the spool in the Filament Catalog.

```
┌─────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────────────┐ │
│ │  [COLOR BANNER]  AMS 1 Tray 2               │ │
│ │  Bambu Lab PLA Basic White  ·  Matched       │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│  [Weight: 123.4g] [This Print: 45.2g]          │
│                                                 │
│  ┌───────────────────────┐┌────────────────────┐│
│  │ 🌡️ Dried: Mar 1, 2026 │[🔥]│ 💧 Desiccant: 12d│[💦]│ ← bubble cards
│  │     (bubble card)      │    │   (bubble card)  │    │   50% each
│  └───────────────────────┘└────────────────────┘│   sub-btns: Mark
│                                                 │
│  📦 3 other spools ... (expand)                  │
│                                                 │
│  [chart: weight history]                        │
│                                                 │
│  ┌─────────────────────────────────────────────┐│
│  │ bubble-card sub-buttons:                    ││ ← MODIFIED
│  │ [📌 Pin/Unpin] [ℹ Details] [🧵 Spoolman]   ││   all bubble
│  │ [🔄 Reload] [✕ Close]  [♻ Replace Spool]   ││   card style
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

> **Pin/Unpin Assessment:** The Pin Spool / Unpin Spool button was previously a styled mushroom chip in the UUID/match tier area. It has been moved to the bottom action row as a bubble card sub-button for visual consistency with the other action buttons. The match tier and pin status are still displayed as informational chips at the top, but the actionable pin/unpin control now lives alongside the other actions.

---

### Step 1 Popup: Validate Empty Spool

```
┌─────────────────────────────────────────────────┐
│  ♻ Replace Spool — Step 1 of 4                  │
│─────────────────────────────────────────────────│
│                                                 │
│  Source Spool:                                  │
│  ┌─────────────────────────────────────────────┐│
│  │ 🟡 Bambu Lab PLA Basic White  #42           ││
│  │ 📍 AMS  ·  56.3g remaining                  ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  ⚠️ WARNING                                     │
│  ┌─────────────────────────────────────────────┐│
│  │ This spool still shows 56.3g remaining.     ││
│  │ Are you sure it's empty?                    ││
│  │                                              ││
│  │ If you continue, the remaining weight will   ││
│  │ be reset to 0g before archiving.             ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│    [ Yes, It's Empty — Continue ]  [ Cancel ]   │
└─────────────────────────────────────────────────┘
```

**No warning variant** (0g or null):

```
┌─────────────────────────────────────────────────┐
│  ♻ Replace Spool — Step 1 of 4                  │
│─────────────────────────────────────────────────│
│                                                 │
│  Source Spool:                                  │
│  ┌─────────────────────────────────────────────┐│
│  │ 🟡 Bambu Lab PLA Basic White  #42           ││
│  │ 📍 AMS  ·  0.0g remaining  ✅               ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  ℹ️  Spool is confirmed empty. Ready to pick    │
│     a sealed replacement.                       │
│                                                 │
│         [ Continue to Step 2 ]  [ Cancel ]      │
└─────────────────────────────────────────────────┘
```

---

### Step 2 Popup: Select Replacement

```
┌─────────────────────────────────────────────────┐
│  ♻ Replace Spool — Step 2 of 4                  │
│─────────────────────────────────────────────────│
│                                                 │
│  Replacing: #42 Bambu Lab PLA Basic White       │
│  Showing sealed spools of PLA Basic (Bambu Lab) │
│                                                 │
│  ┌─────────────────────────────────────────────┐│
│  │  Pick Replacement Spool:                    ││
│  │  [ #78 — PLA Basic White — Closet Shelf 2 ▼]│
│  └─────────────────────────────────────────────┘│
│                                                 │
│  Or select from the list:                       │
│  ┌─────────────────────────────────────────────┐│
│  │ 🟡 #78  PLA Basic White     250g            ││
│  │    📍 Closet Shelf 2         [Select ►]     ││
│  ├─────────────────────────────────────────────┤│
│  │ 🟡 #91  PLA Basic White     250g            ││
│  │    📍 Closet Rack 3          [Select ►]     ││
│  ├─────────────────────────────────────────────┤│
│  │ 🟡 #104 PLA Basic White     1000g           ││
│  │    📍 Under Desk (Right)     [Select ►]     ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│              [ Back ]  [ Cancel ]               │
└─────────────────────────────────────────────────┘
```

**Empty state:**

```
│  ┌─────────────────────────────────────────────┐│
│  │ 📭 No sealed spools of this filament found  ││
│  │    in your inventory.                       ││
│  │                                              ││
│  │    [Open Spoolman to add one ↗]              ││
│  └─────────────────────────────────────────────┘│
│              [ Back ]  [ Cancel ]               │
```

---

### Step 3 Popup: Configure Transfer

```
┌──────────────────────────────────────────────────┐
│  ♻ Replace Spool — Step 3 of 4                   │
│──────────────────────────────────────────────────│
│                                                  │
│  #42 (empty)  ──►  #78 (sealed)                  │
│  PLA White · AMS    PLA White · Closet Shelf 2   │
│                                                  │
│  ─── Transfer Options ───────────────────────── │
│                                                  │
│  ☑ Copy Spool Type         "Bambu Spool"         │
│  ☑ Copy Clip Type          "Slot Insert v2"      │
│  ☑ Copy Desiccant Present  Yes                   │
│                                                  │
│  Desiccant Fill Date:  [ Reset to today     ▼]   │
│                         · Copy from old spool    │
│                         · Reset to today    ◄──  │
│                         · Skip                   │
│                                                  │
│  ☑ Set Location → AMS     (from source spool)    │
│  ☐ Mark Used in Current Print                    │
│  ☑ Archive Empty Spool                           │
│                                                  │
│      [ Continue to Review ]  [ Back ]  [ Cancel ]│
└──────────────────────────────────────────────────┘
```

---

### Step 4 Popup: Review & Execute

```
┌──────────────────────────────────────────────────┐
│  ♻ Replace Spool — Review & Confirm              │
│──────────────────────────────────────────────────│
│                                                  │
│  ── Source: #42 Bambu Lab PLA Basic White ──     │
│  • Reset remaining weight to 0g                  │
│  • Archive spool in Spoolman                     │
│                                                  │
│  ── Target: #78 Bambu Lab PLA Basic White ──     │
│  • Mark as unsealed                              │
│  • Set spool type: "Bambu Spool"                 │
│  • Set clip type: "Slot Insert v2"               │
│  • Set desiccant present: Yes                    │
│  • Reset desiccant fill date to today            │
│  • Set location: AMS                             │
│                                                  │
│  ⏱ After execution, the Spoolman integration     │
│    will reload to reflect the changes.           │
│                                                  │
│        [ ✅ Execute ]    [ Back ]    [ Cancel ]   │
└──────────────────────────────────────────────────┘
```

---

## Implementation Checklist

### Phase 1: Core Replace Flow

- [ ] **Helpers**
  - [ ] Create `input_text.spool_replace_source_spool_id`
  - [ ] Create `input_text.spool_replace_target_spool_id`
  - [ ] Create `input_boolean.spool_replace_copy_spool_type` (default ON)
  - [ ] Create `input_boolean.spool_replace_copy_clip_type` (default ON)
  - [ ] Create `input_boolean.spool_replace_copy_desiccant_present` (default ON)
  - [ ] Create `input_boolean.spool_replace_copy_location` (default ON)
  - [ ] Create `input_boolean.spool_replace_mark_used` (default OFF)
  - [ ] Create `input_boolean.spool_replace_archive_source` (default ON)
  - [ ] Create `input_select.spool_replace_desiccant_mode` (3 options)
  - [ ] Create `input_select.spool_replace_target_picker`

- [x] **Archive Support**
  - [x] ~~Create `rest_command.spoolman_archive_spool`~~ — Not needed; `spoolman.patch_spool` with `archived: true` confirmed working
  - [x] ~~Test `spoolman.patch_spool` with `archived: true`~~ — Confirmed via source review (Spoolman API + HA integration `services.yaml` + `__init__.py`)

- [ ] **Scripts**
  - [ ] Create `script.spool_replace_populate_candidates`
  - [ ] Create `script.spool_replace_execute` (read-merge-write pattern for extra fields — see design doc §7.4)
  - [ ] Add logbook + system_log entries

- [ ] **Dashboard — Spool Popup**
  - [ ] Add "More Actions" button to action row in `catalog_spool_popup.yaml`
  - [ ] Implement Step 1 popup (validate empty spool)
  - [ ] Implement Step 2 popup (select replacement)
  - [ ] Implement Step 3 popup (configure transfer options)
  - [ ] Implement Step 4 popup (review & execute)
  - [ ] Wire popup chain (close → delay → open next)

- [ ] **Testing**
  - [ ] Test: spool at 0g → full flow → verify Spoolman state
  - [ ] Test: spool at >0g → warning shown → continue → weight reset
  - [ ] Test: spool at <0g → info shown → weight reset
  - [ ] Test: no sealed candidates → empty state displayed
  - [ ] Test: all transfer options ON → verify all fields copied
  - [ ] Test: all transfer options OFF → verify only unseal performed
  - [ ] Test: archive step → verify spool entity disappears after reload
  - [ ] Test: cancel at each step → verify no Spoolman changes

### Phase 2: Filament Runout Detection & Notification

- [ ] **Automation**
  - [ ] Create `filament_runout_capture_and_notify` automation
  - [ ] Trigger on `sensor.ntk_ryansoffice_3dprinter_current_stage` → `paused_filament_runout`
  - [ ] Resolve last-known spool from `input_text.print_weight_backup` + active tray sensor
  - [ ] Write spool ID to `input_text.spool_replace_source_spool_id`
  - [ ] Create persistent notification with spool name, ID, tray, and link to dashboard
  - [ ] Send mobile notification (same pattern as `print_fault_notification.yaml`)
- [ ] **Testing**
  - [ ] Test: simulate `paused_filament_runout` → verify notification created with correct spool
  - [ ] Test: verify `spool_replace_source_spool_id` is populated
  - [ ] Test: verify notification link navigates to dashboard
  - [ ] Test: active tray sensor still available at runout vs. already cleared

### Phase 3: AMS Tray Popup + NFC Tag View Integration

- [ ] **AMS Tray Popup**
  - [ ] Add "Replace Spool" button to `ams_tray_popup.yaml`
  - [ ] Wire button to same wizard (set `source_spool_id` from tray context)
  - [ ] Conditional visibility: only when `match_state === 'matched'` (no button on empty trays)
- [ ] **NFC Filament Tag View (Mobile)**
  - [ ] Add "Replace / Refill Spool" button to "Other Actions" section in `view_filament_tags.yaml`
  - [ ] Wire button: write spool ID → call `script.spool_replace_populate_candidates` → open Step 1 popup
  - [ ] Conditional enable: only when `sensor.selected_spool` resolves to a valid spool entity
  - [ ] Test: full wizard flow on iPhone (HA Companion App) via NFC tag scan
  - [ ] Test: popup chain (close → delay → open next) works correctly on mobile Safari

### Phase 4: Reverse Flow (Unseal & Use)

- [ ] Create `script.spool_unseal_setup`
- [ ] Add "Unseal & Use" button (conditional on `extra_sealed`) in spool popup
- [ ] Simplified popup flow (configure → execute, no source spool required)
- [ ] Optional: link empty spool for archiving
- [ ] Verify `date_opened` extra field is populated on unseal

### Phase 5: Enhancements

- [ ] Toast notifications (browser_mod.notification) after execute
- [ ] Spool type / clip type picker (instead of copy-only)
- [ ] Undo capability (un-archive within timeout)
- [ ] Auto-open wizard from notification deep link
- [ ] Batch replace for multi-spool runout scenarios
