# Spool Replace / Refill — Popup Wireframes & Implementation Checklist

> **Companion to:** [spool-replace-refill-design.md](spool-replace-refill-design.md)

---

## Popup Wireframes

### Spool Popup — "Replace / Refill" Button Placement

```
┌─────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────────────┐ │
│ │  [COLOR BANNER]  Bambu Lab PLA Basic White  │ │ ← existing
│ │  Spool #42 · AMS                            │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│  Material: PLA  ·  Vendor: Bambu Lab  ·  AMS   │ ← existing chips
│                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ ┌───────────────┐│
│  │ 123.4 g  │ │ $0.098/g │ │ 856.2g (4 pools) │ │ Qty to Order  ││ ← existing + NEW KPI
│  │Remaining │ │Cost per g│ │ Total            │ │      2        ││
│  └──────────┘ └──────────┘ └──────────────────┘ │   [+]   [-]   ││
│                                                  └───────────────┘│
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
│  │ [♻ Replace] [🧵 Spoolman] [🔄 Reload] [✕]   ││   all bubble
│  └─────────────────────────────────────────────┘│   card style
└─────────────────────────────────────────────────┘
```

**For sealed spools**, the Replace button is replaced by a direct **"Unseal & Use"** sub-button in the bottom bubble card row.

### AMS Tray Popup — "Replace Spool" Button Placement

> **Note:** This button is only visible when the tray has a matched spool (`match_state === 'matched'`). When a spool runs out mid-print, the Bambu Lab integration clears the tray data, so `spoolman_tray_map` reports `match_state: 'empty'` and the button will not appear. In that scenario, the user is guided via a **Filament Runout Notification** (Phase 3) to find the spool in the Filament Catalog.

```
┌─────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────────────┐ │
│ │  [COLOR BANNER]  AMS 1 Tray 2               │ │
│ │  Bambu Lab PLA Basic White  ·  Matched       │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│  [Weight: 123.4g] [This Print: 45.2g] [Total all spools] [Qty]   │
│                                                [Qty to Order]      │
│                                                [current value]      │
│                                                [+] [-]              │
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
│  │ [♻ Replace Spool] [🧵 Spoolman] [🔄 Reload] ││   all bubble
│  │ [✕ Close]                                   ││   card style
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

> **Action Row Simplification:** The AMS popup action row intentionally excludes **More Details** and **Pin/Unpin**. Replace Spool is left-most to match the Spool popup order and keep the primary action consistent.

---

### HMS Error Banner — "Replace Spool Now" Button (Phase 3)

> **Note:** This button only appears when a filament-runout HMS error is active AND the `filament_runout_capture_and_notify` automation has populated `input_text.spool_replace_source_spool_id`. It renders as an additional card inside the existing HMS error details panel, below the error cards.

```
╔═════════════════════════════════════════════════════════╤════╗
║  🔴  HMS ERROR ALERT                                    │ ▲  ║
║      AMS B Slot 3 filament has run out. Please insert…  │    ║
╠═════════════════════════════════════════════════════════╧════╣
║                                                              ║
║  ┌── 🔴 Error 1 (Serious) ─────────────────────────────┐   ║
║  │  AMS B Slot 3 filament has run out.                   │   ║
║  │  Code: HMS_0701_2200_0002_0001 · Wiki ↗              │   ║
║  └───────────────────────────────────────────────────────┘   ║
║                                                              ║
║  ┌── ♻ Replace Spool Now ──────────────────────────────┐   ║
║  │  🔄 PLA Basic White #42 ran out                      │   ║
║  │     Tap to start the replace wizard                  │   ║
║  └  (green left border, light green bg)  ───────────────┘   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**Button card details:**
- Green accent: `rgba(76,175,80,0.12)` background, `#4CAF50` left border — visually distinct from red error cards
- Icon: `mdi:swap-horizontal` (green)
- Primary: **"♻ Replace Spool Now"** (bold)
- Secondary: spool name + ID + "ran out · Tap to start wizard" (smaller, secondary color)
- Tap action: populate candidates → open wizard popup
- Auto-hidden when source spool ID is cleared (wizard complete) or HMS error clears

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
│  ☑ Copy Spool Type:  Bambu Spool                 │
│                      ^^^^^^^^^^  (smaller, gray) │
│  ☑ Copy Clip Type:  Slot Insert v2               │
│                     ^^^^^^^^^^^^^^  (same style) │
│  ☑ Copy Desiccant Present:  Yes                  │
│                             ^^^  (smaller, gray) │
│                                                  │
│  Desiccant Fill Date:                            │
│  [ Reset to today     ▼]     ← left-aligned     │
│    · Copy from old spool                         │
│    · Reset to today                              │
│    · Skip                                        │
│                                                  │
│  ☑ Copy Location:  AMS                           │
│                    ^^^  (smaller, gray)          │
│  ☐ Mark Used in Current Print                    │
│  ☑ Archive Empty Spool                           │
│                                                  │
│      [ Continue to Review ]  [ Back ]  [ Cancel ]│
└──────────────────────────────────────────────────┘
```

**Value styling:** The values after each label (e.g., "Bambu Spool", "Slot Insert v2",
"Yes", "AMS") are rendered in a slightly smaller font (`0.88em`) with
`var(--secondary-text-color)` to visually distinguish them from the label text.

**Desiccant combo box:** Left-aligned via `card_mod` on the `entities` card to match
the overall left-aligned layout of the popup.

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
│  • Mark as unsealed (Date Opened set to today)   │
│  • Copy spool type: Bambu Spool                  │
│                      ^^^^^^^^^^  (gray, 0.92em)  │
│  • Copy clip type: Slot Insert v2                │
│                    ^^^^^^^^^^^^^^  (gray, 0.92em)│
│  • Copy desiccant present                        │
│  • Reset desiccant fill date to today            │
│  • Set location: AMS                             │
│                  ^^^  (gray, 0.92em)             │
│                                                  │
│  ⏱ After execution, the Spoolman integration     │
│    will reload to reflect the changes.           │
│                                                  │
│        [ ✅ Execute ]    [ Back ]    [ Cancel ]   │
└──────────────────────────────────────────────────┘
```

**Left alignment:** All text is left-aligned via `card_mod` on the markdown card.

**Value styling:** Copied values (spool type, clip type, location) are rendered with
`var(--secondary-text-color)` at `0.92em` via inline `<span>` styles to visually
distinguish them from the action labels.

**"Date Opened":** The field `date_opened` is displayed as the user-friendly
"Date Opened" in all UI text.

---

## Implementation Checklist

### Phase 1: Core Replace Flow ✅ COMPLETE (2026-03-26)

- [x] **Helpers**
  - [x] Create `input_text.spool_replace_source_spool_id`
  - [x] Create `input_text.spool_replace_target_spool_id`
  - [x] Create `input_boolean.spool_replace_copy_spool_type` (default ON)
  - [x] Create `input_boolean.spool_replace_copy_clip_type` (default ON)
  - [x] Create `input_boolean.spool_replace_copy_desiccant_present` (default ON)
  - [x] Create `input_boolean.spool_replace_copy_location` (default ON)
  - [x] Create `input_boolean.spool_replace_mark_used` (default OFF)
  - [x] Create `input_boolean.spool_replace_archive_source` (default ON)
  - [x] Create `input_select.spool_replace_desiccant_mode` (3 options)
  - [x] Create `input_select.spool_replace_target_picker`

- [x] **Archive Support**
  - [x] ~~Create `rest_command.spoolman_archive_spool`~~ — Not needed; `spoolman.patch_spool` with `archived: true` confirmed working
  - [x] ~~Test `spoolman.patch_spool` with `archived: true`~~ — Confirmed via source review (Spoolman API + HA integration `services.yaml` + `__init__.py`)

- [x] **Scripts**
  - [x] Create `script.spool_replace_populate_candidates`
  - [x] Create `script.spool_replace_execute` (read-merge-write pattern for extra fields — see design doc §7.4)
  - [x] Create `script.spool_replace_sync_target_from_picker` (extracts spool ID from picker selection)
  - [x] Add logbook + system_log entries

- [x] **Dashboard — Spool Popup**
  - [x] Add "Replace / Refill Spool" button as the left-most action in `catalog_spool_popup.yaml`
  - [x] Add "Qty to Order" stacked KPI card to `catalog_spool_popup.yaml` (to the right of `Total (all spools)`)
  - [x] Add `+` / `-` qty adjust buttons in the stacked card, with `-` disabled at `0`
  - [x] Remove bottom-row "Location" button in `catalog_spool_popup.yaml` (location control remains in the Change Location row)
  - [x] Implement Step 1 popup (validate empty spool)
  - [x] Implement Step 2 popup (select replacement)
  - [x] Implement Step 3 popup (configure transfer options)
  - [x] Implement Step 4 popup (review & execute)
  - [x] Wire popup chain (close → delay → open next)

- [x] **Dashboard — AMS Tray Popup**
  - [x] Add "Qty to Order" stacked KPI card to `ams_tray_popup.yaml` (to the right of `Total (all spools)`)
  - [x] Add `+` / `-` qty adjust buttons in the stacked card, with `-` disabled at `0`

**Qty field fallback note:** If a spool does not yet have `extra_purchase_qty`, both popups render qty as `0` and allow `+` to initialize the field on first update.

- [ ] **Testing** — See [spool-replace-refill-testing.md](spool-replace-refill-testing.md)
  - [ ] Test: spool at 0g → full flow → verify Spoolman state
  - [ ] Test: spool at >0g → warning shown → continue → weight reset
  - [ ] Test: spool at <0g → info shown → weight reset
  - [ ] Test: no sealed candidates → empty state displayed
  - [ ] Test: all transfer options ON → verify all fields copied
  - [ ] Test: all transfer options OFF → verify only unseal performed
  - [ ] Test: archive step → verify spool entity disappears after reload
  - [ ] Test: cancel at each step → verify no Spoolman changes

### Phase 2: AMS Tray Popup + NFC Tag View Integration

- [x] **AMS Tray Popup**
  - [x] Add "Replace Spool" button to `ams_tray_popup.yaml`
  - [x] Place "Replace Spool" as the left-most action in the bottom action row
  - [x] Remove "More Details" button from bottom action row in `ams_tray_popup.yaml`
  - [x] Remove "Pin/Unpin" action from bottom action row design (pin status remains informational at top)
  - [x] Wire button to same wizard (set `source_spool_id` from tray context)
  - [x] Conditional visibility: only when `match_state === 'matched'` (no button on empty trays)
- [x] **NFC Filament Tag View (Mobile)**
  - [x] Add "Replace / Refill Spool" button to "Other Actions" section in `view_filament_tags.yaml`
  - [x] Wire button: write spool ID → call `script.spool_replace_populate_candidates` → open Step 1 popup
  - [x] Conditional enable: only when `sensor.selected_spool` resolves to a valid spool entity
  - [ ] Test: full wizard flow on iPhone (HA Companion App) via NFC tag scan
  - [ ] Test: popup chain (close → delay → open next) works correctly on mobile Safari

### Phase 3: Filament Runout Detection, Notification & HMS Banner ✅ COMPLETE (2026-03-27)

- [x] **Automation**
  - [x] Create `filament_runout_capture_and_notify` automation
  - [x] Trigger on `sensor.ntk_ryansoffice_3dprinter_current_stage` → `paused_filament_runout`
  - [x] Resolve last-known spool from `spoolman_tray_map` (primary) + `print_job_ams_tray_storage` UUID fallback
  - [x] Write spool ID to `input_text.spool_replace_source_spool_id`
  - [x] Create persistent notification with spool name, ID, tray, and link to dashboard
  - [x] Send mobile notification (same pattern as `print_fault_notification.yaml`)
- [x] **HMS Banner — Replace Spool Now Button**
  - [x] Add conditional `button-card` inside `hms-error-alert-section.yaml`
  - [x] Green accent styling (rgba(76,175,80,0.12) bg, #4CAF50 left border)
  - [x] Shows spool name + ID from `input_text.spool_replace_source_spool_id`
  - [x] Launches replace wizard popup via `browser_mod.popup`
  - [x] Auto-hidden when source spool ID is cleared (wizard complete) or HMS error clears
- [ ] **Testing**
  - [ ] Test: simulate `paused_filament_runout` → verify notification created with correct spool
  - [ ] Test: verify `spool_replace_source_spool_id` is populated
  - [ ] Test: verify notification link navigates to dashboard
  - [ ] Test: active tray sensor still available at runout vs. already cleared
  - [ ] Test: HMS banner button visible when source spool ID is set
  - [ ] Test: HMS banner button launches wizard popup correctly
  - [ ] Test: HMS banner button hidden after wizard completes

### Phase 4: Reverse Flow (Unseal & Use) — Complete (2026-03-27)

- [x] Create `script.spool_unseal_setup`
- [x] Add "Unseal & Use" button (conditional on `extra_sealed`) in spool popup
- [x] Simplified popup flow (configure → execute, no source spool required)
- [x] Optional: link empty spool for archiving
- [x] Verify `date_opened` extra field is populated on unseal

### Phase 5: Enhancements

- [x] Add Back button in the wizard workflow (Steps 2, 3, 4)
- [ ] Toast notifications (browser_mod.notification) after execute
- [ ] Spool type / clip type picker (instead of copy-only)
- [ ] Undo capability (un-archive within timeout)
- [ ] Auto-open wizard from notification deep link
- [ ] Batch replace for multi-spool runout scenarios
