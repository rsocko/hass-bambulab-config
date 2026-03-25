# AMS Tray Assignment from Spoolman — Design Document

> **Status**: Design
> **Created**: 2026-03-24
> **Scope**: Push filament metadata from Spoolman to Bambu printer trays via `bambu_lab.set_filament`

## Problem Statement

When a non-Bambu spool is loaded into an AMS tray — or **any** spool (Bambu or not) is loaded into the External Spool holder — the printer has no RFID data to auto-detect the filament profile. The user must currently open Bambu Studio and manually set the Material Type, Profile, and Color for that tray.

This repo already has a comprehensive **read-side** system: `sensor.spoolman_tray_map` matches printer trays to Spoolman spools using UUID, color, material, and profile. But there is no **write-side** capability — no automation or UI pushes spool metadata *back* to the printer when a new spool is loaded.

The objective is to close this gap: when a spool is assigned to an AMS tray or the External Spool (either via a Spoolman location change or a manual user action), derive the correct filament parameters from Spoolman data and call `bambu_lab.set_filament` to configure the printer tray.

## Goals

1. **Automated tray configuration** — When a non-Bambu spool is loaded into an AMS tray, or any spool is loaded to External Spool, automatically push the correct filament info to the printer
2. **Spoolman-triggered flow** — Detect when a spool's Spoolman `location` changes to an AMS tray or External Spool and initiate the assignment
3. **Tray inference** — When possible, automatically determine which AMS tray the spool was loaded into
4. **Guided fallback** — When the target tray cannot be inferred, present a UI for the user to select it
5. **Non-interference** — Preserve filament info set directly via Bambu Studio; don't overwrite Bambu RFID-tagged spools in AMS trays
6. **Manual trigger** — Allow the user to trigger tray assignment on-demand from the existing AMS tray popup UI
7. **Visibility** — Surface confirmation or actionable notifications when tray assignment succeeds or needs user input

## Non-Goals

- Replacing the existing `sensor.spoolman_tray_map` matching system (read-side is unchanged)
- Automating physical spool loading/unloading (AMS motor control)
- Supporting printers without `bambu_lab.set_filament` capability (firmware/auth limitations)
- Auto-updating Bambu RFID-tagged spools in AMS (the RFID reader handles these)

---

## Background: Available Services

### `bambu_lab.set_filament`

Sets filament type and metadata for an AMS tray or external spool tray. This is the core write mechanism.

```yaml
action: bambu_lab.set_filament
data:
  entity_id: sensor.p1s_01p00c460102350_ams_1_tray_3   # or external_spool entity
  tray_info_idx: GFL96          # Bambu filament profile ID (e.g. GFL96 = Generic PLA Silk)
  tray_color: FF0000FF          # RGBA hex color
  tray_type: PLA                # Material type string
  nozzle_temp_min: 190          # Min recommended nozzle temp (°C)
  nozzle_temp_max: 240          # Max recommended nozzle temp (°C)
```

**All fields are required.** Parameters:

| Parameter | Type | Description |
|---|---|---|
| `entity_id` | string | AMS tray or external spool sensor entity ID |
| `tray_info_idx` | string | Bambu's internal filament profile ID (e.g. `GFL96`, `GFL99`, `GFB60`) |
| `tray_color` | string | 8-char RGBA hex color (e.g. `FF0000FF` = opaque red) |
| `tray_type` | string | Material type key (e.g. `PLA`, `PETG`, `ABS`, `TPU`, `ASA`, `PA`, `PC`) |
| `nozzle_temp_min` | number | Minimum print temp in °C |
| `nozzle_temp_max` | number | Maximum print temp in °C |

### `bambu_lab.get_filament_data`

Returns a JSON blob of all known Bambu filament profiles. This provides the mapping between `tray_info_idx` codes and their human-readable names + properties.

```yaml
action: bambu_lab.get_filament_data
data:
  device_id: <printer_device_id>
```

This is critical for resolving the `tray_info_idx` value from Spoolman data.

### Existing Spoolman Data Available Per-Spool

From `sensor.spoolman_spool_*` entity attributes:

| Spoolman Attribute | Maps To | Notes |
|---|---|---|
| `filament_material` | `tray_type` | Direct map for common types (PLA, PETG, ABS, etc.) |
| `filament_color_hex` | `tray_color` | 6-char hex; must append `FF` alpha for RGBA |
| `filament_extra_profile_name` | `tray_info_idx` lookup key | JSON-quoted; strip outer quotes. Maps to Bambu profile name. |
| `filament_settings_extruder_temp` | `nozzle_temp_min` / `nozzle_temp_max` | May be a single value; need min/max derivation strategy |
| `filament_vendor_name` | (Bambu vs non-Bambu determination) | "Bambu Lab" = Bambu path |
| `extra_spool_uuid` | (skip assignment logic) | If UUID present → RFID-tagged Bambu spool in AMS; no assignment needed |

---

## Design Decisions

| Question | Decision | Rationale |
|---|---|---|
| **When to trigger?** | Spoolman location change to AMS/External + manual on-demand | Both automated and manual flows cover the key scenarios |
| **Where does tray_info_idx come from?** | Profile-name-to-idx lookup via `bambu_lab.get_filament_data` (called inline at assignment time) + hardcoded generic fallback table | `get_filament_data` returns `filaments_detail.json` merged with slicer custom profiles; no caching needed |
| **How to detect Spoolman location changes?** | Monitor `sensor.spoolman_spool_*` location attribute changes via state trigger | Spoolman integration updates entities when spool data changes |
| **What if tray can't be inferred?** | Persistent notification + inline tray picker in filament tag view + tray picker in ams_tray_popup | User picks the tray from the UI they're currently in |
| **Overwrite Bambu RFID spools?** | Never in AMS trays; always for External Spool | AMS has RFID reader; External Spool never does |
| **Filament data storage strategy** | No caching — call `get_filament_data` inline at assignment time | Local service call is fast; hardcoded generic fallback for offline resilience |
| **Nozzle temp when only single value?** | Use ±10°C range from `filament_settings_extruder_temp`, or use Bambu profile defaults from lookup table | Safe default; overridden by profile match if found |
| **Feature placement** | New files in `spoolman_sync/` (automations, scripts) + view modifications in `filament_tag/` and `common/` | Core logic in spoolman_sync domain; UI touchpoints in filament tag view and AMS tray popup |
| **Filament tag view role** | Primary real-world trigger source; enhanced with feedback + inline tray picker | NFC scan → tap AMS → location change → automation fires. View gets status feedback in Phase 3. |
| **Two-phase vs. combined action** | Start with two-phase (location change → automation); combined script deferred to Phase 4 | Two-phase is more robust: handles all trigger sources, is idempotent, maintains separation of concerns |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         TRIGGER SOURCES                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  (A) Spoolman location change         (B) Manual action from HA UI   │
│      sensor.spoolman_spool_*              "Set on Printer" in         │
│      location → "AMS" / "AMS 2"           ams_tray_popup.yaml        │
│                / "External Spool Holder"                             │
│                                                                      │
│      Primary real-world source:        (C) Filament Tag view         │
│      NFC scan → filament tag view          (future: combined         │
│      → tap AMS / AMS 2 button              location + tray assign)   │
│      → script.update_spool_location                                  │
│      → spoolman.patch_spool                                          │
│                                                                      │
└───────────┬──────────────────┬─────────────────────┬────────────────┘
            │                  │                     │
            ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────┐
│              ASSIGNMENT ORCHESTRATOR                      │
│         script.assign_spool_to_printer_tray               │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  1. Validate spool data completeness                      │
│  2. Determine if assignment is needed:                    │
│     - Non-Bambu spool in AMS → YES                       │
│     - Any spool on External → YES                        │
│     - Bambu spool in AMS (has UUID) → SKIP               │
│  3. Resolve target tray entity:                           │
│     - If explicit tray provided → use it                  │
│     - If external → use external_spool entity             │
│     - If AMS → attempt tray inference                     │
│  4. Map Spoolman data → set_filament parameters           │
│  5. Call bambu_lab.set_filament                           │
│  6. Confirm / notify user                                 │
│                                                           │
└─────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│              DATA MAPPING LAYER                           │
│         script.resolve_bambu_filament_params               │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Inputs: spool entity ID                                  │
│                                                           │
│  Outputs:                                                 │
│    tray_info_idx  ← profile_name → Bambu ID lookup        │
│    tray_color     ← filament_color_hex + "FF" alpha       │
│    tray_type      ← filament_material                     │
│    nozzle_temp_min ← from lookup table or spool data      │
│    nozzle_temp_max ← from lookup table or spool data      │
│                                                           │
│  Fallback: Generic profile (e.g. GFL99 for Generic PLA)  │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### 1. Trigger: Spoolman Location Change (Automated Flow)

#### Trigger Mechanism

An automation monitors all `sensor.spoolman_spool_*` entities for `location` attribute changes. When a spool's location changes **to** a value indicating AMS or External Spool placement, the assignment flow begins.

**Location values that trigger assignment:**
- `"AMS"` — spool placed into AMS unit 1
- `"AMS 2"` — spool placed into AMS unit 2 (if present)
- `"External Spool Holder"` — spool placed on the external spool holder

> **Resolved (Q1)**: `"External Spool Holder"` already exists as a Spoolman location value. No vocabulary changes needed. The `sync_filter_options` automation dynamically discovers locations from spool entities, so it will appear in filters automatically.

**Important note on Spoolman location field behavior:**

The Spoolman `location` field is freeform text. The Spoolman API only returns location values that are currently assigned to at least one spool. This means:

- **Trigger automation**: No issue — the automation watches the `location` attribute on `sensor.spoolman_spool_*` entities for specific string values regardless of any dropdown.
- **User setting the location**: If no spool currently has `"External Spool Holder"` as its location, the value will not appear as an auto-suggest option in the Spoolman UI. The user must type it manually the first time. Once at least one spool has the value, it will appear in location dropdowns and filter options.
- **First-use bootstrapping**: Consider documenting the exact location strings (`"AMS"`, `"AMS 2"`, `"External Spool Holder"`) in user-facing setup docs or as a tooltip/helper text so users know the expected values. Alternatively, a one-time setup script could assign and then unassign these location values to a dummy spool to seed the Spoolman auto-suggest list.

#### Conditions

Before proceeding with assignment:

1. **Spool is non-Bambu OR target is External Spool**
   - If `filament_vendor_name == "Bambu Lab"` AND `extra_spool_uuid` is non-empty AND target is an AMS tray → **skip** (RFID will handle it)
   - If target is External Spool → **always proceed** (no RFID reader)
   
2. **Spool data is sufficient**
   - `filament_material` is present
   - `filament_color_hex` is present
   - At least one of: `filament_extra_profile_name` or `filament_settings_extruder_temp` is present

3. **Printer is reachable and not printing**
   - Check `sensor.smart_status` is not in an active printing state
   - `bambu_lab.set_filament` should not be called mid-print

#### Flow After Trigger

```
Location changes to AMS/AMS 2/External Spool
    │
    ├─ Target is "External Spool Holder"?
    │   └─ YES → tray_entity = external_spool sensor
    │            → proceed to data mapping + set_filament
    │
    ├─ Target is "AMS" or "AMS 2"?
    │   ├─ Spool is Bambu Lab with UUID?
    │   │   └─ YES → SKIP (RFID handles it)
    │   │
    │   └─ Non-Bambu (or Bambu without UUID)?
    │       ├─ Attempt tray inference (see §2)
    │       │
    │       ├─ Inference succeeds → single tray identified
    │       │   └─ proceed to data mapping + set_filament
    │       │
    │       └─ Inference fails → user intervention needed
    │           └─ send notification with tray picker
    │               (see §4: Guided Tray Selection UI)
    │
    └─ Other location → no action
```

### 2. Tray Inference Logic

When a spool is placed in "AMS" (or "AMS 2") and the specific tray isn't known, attempt to infer it.

#### Strategy: Empty Tray Detection

Read the current state of all trays in the target AMS unit from the ha-bambulab tray sensors:

```
For AMS 1: sensor.{printer}_ams_1_tray_1 through _tray_4
For AMS 2: sensor.{printer}_ams_2_tray_1 through _tray_4
```

A tray is **empty** when:
- `state_attr(tray, 'type') == 'Empty'`

**Inference rules:**

| Scenario | Result |
|---|---|
| Exactly 1 empty tray in the target AMS | **Infer**: the spool goes in that tray |
| 0 empty trays (all occupied) | **Cannot infer**: user must specify which tray was replaced |
| 2+ empty trays | **Cannot infer**: ambiguous which tray was filled |
| Location is "AMS" but multiple AMS units exist | Check both AMS units; if exactly 1 empty tray across all units → infer; otherwise → ambiguous |

> **Open Question 2**: Should we also use timing heuristics? For example, if a tray transitions from Empty to populated within a short window after the Spoolman location change, that confirms the tray. This would require monitoring tray state changes after the location trigger.
>
> **Recommendation**: Start with the simpler empty-tray-count approach. Add timing correlation as a future enhancement if empty-count inference proves too unreliable.

> **Resolved (Q3)**: `"AMS"` maps to AMS 1 trays (`ams_1_tray_1` through `ams_1_tray_4`). `"AMS 2"` maps to AMS 2 trays (`ams_2_tray_1` through `ams_2_tray_4`). The user sets the correct location value in Spoolman.

#### Alternative: Tray State Change Correlation

A more robust (but complex) alternative monitors the printer-side tray entities for changes that correlate with the Spoolman location change:

1. Spoolman location changes to "AMS"
2. Within a configurable time window (e.g., 60 seconds), an AMS tray sensor transitions from `type: Empty` to a non-empty state
3. That tray is the assignment target

This approach is **deferred to a future phase** because:
- It requires coordinating two independent event sources with timing
- The simpler empty-tray approach handles the majority case (user loads spool into a known empty slot)
- Race conditions with multiple simultaneous spool changes would need handling

### 3. Data Mapping: `tray_info_idx` Resolution

This is the most complex mapping challenge. Bambu's `set_filament` requires a `tray_info_idx` — an internal code like `GFL96` that identifies a specific filament profile in Bambu's system.

#### Approach: Profile Name Lookup Table

1. **At startup** (or on demand), call `bambu_lab.get_filament_data` to retrieve all known Bambu filament profiles
2. **Parse and cache** the response into a lookup structure: `profile_name → tray_info_idx`
3. **At assignment time**, look up the spool's `filament_extra_profile_name` in this table

**Lookup precedence:**

| Step | Condition | Result |
|---|---|---|
| 1 | `filament_extra_profile_name` matches a Bambu profile name exactly | Use that profile's `tray_info_idx` |
| 2 | No exact match; `filament_material` matches a generic Bambu profile | Use the generic profile ID (e.g., `GFL99` for Generic PLA) |
| 3 | No match at all | Use a hardcoded fallback map by material type (see below) |

**Hardcoded generic fallback table** (validated against `filaments_detail.json` bundled with ha-bambulab):

| Material | Generic `tray_info_idx` | Profile Name |
|---|---|---|
| PLA | `GFL99` | Generic PLA |
| PETG | `GFG99` | Generic PETG |
| ABS | `GFB99` | Generic ABS |
| ASA | `GFB98` | Generic ASA |
| TPU | `GFU99` | Generic TPU |
| PA (Nylon) | `GFN99` | Generic PA |
| PC | `GFC99` | Generic PC |
| PVA | `GFS99` | Generic PVA |
| PLA-CF | `GFL98` | Generic PLA-CF |
| PETG-CF | `GFG98` | Generic PETG-CF |
| PA-CF | `GFN98` | Generic PA-CF |

> **Note**: These codes were validated against the static `filaments_detail.json` in ha-bambulab. The `get_filament_data` service returns these merged with any custom slicer profiles. Key corrections from initial placeholders: ABS is `GFB99` (not GFA99), ASA is `GFB98` (not GFS99), PVA is `GFS99` (not GFV99).

> **Open Question 4**: ~~The exact `tray_info_idx` codes for generic profiles need to be validated against `bambu_lab.get_filament_data` output.~~
>
> **Resolved**: Codes validated against `filaments_detail.json`. Implementation should still call `get_filament_data` at runtime for profile-name matching (covers third-party profiles like `GFL00` = PolyLite PLA, `GFL03` = eSUN PLA+, etc.) and use this hardcoded table only as offline fallback.

#### Color Mapping

Straightforward:

```
tray_color = filament_color_hex (6-char) + "FF" (opaque alpha)
```

Example: Spoolman `filament_color_hex = "da291c"` → `tray_color = "DA291CFF"`

For multi-color spools, use the first/primary color hex.

#### Temperature Mapping

| Source | Strategy |
|---|---|
| Bambu profile match found | Use `nozzle_temp_min` and `nozzle_temp_max` from the matched Bambu profile |
| Only `filament_settings_extruder_temp` available | Use `temp - 10` as min, `temp + 10` as max |
| No temperature data | Use material-type defaults from the hardcoded table |

**Material-type default temperatures** (fallback):

| Material | Min (°C) | Max (°C) |
|---|---|---|
| PLA | 190 | 230 |
| PETG | 220 | 260 |
| ABS | 230 | 270 |
| ASA | 230 | 270 |
| TPU | 200 | 240 |
| PA | 260 | 300 |
| PC | 250 | 300 |

### 4. Guided Tray Selection UI

When the target tray cannot be inferred automatically, the user needs a UI to complete the assignment.

#### Notification Flow

```
Tray inference fails
    │
    ├─ Create persistent_notification:
    │   "Spool 'Sunlu PLA Matte (Black)' moved to AMS but target tray
    │    is unclear. Please select the tray."
    │   [Link to tray assignment dashboard/popup]
    │
    └─ Set pending assignment state:
        input_text.pending_tray_assignment_spool_id = "<spool_id>"
```

#### Tray Assignment UI Options

**Option A: Dedicated "Assign Spool to Tray" popup (within existing AMS card area)**

Add a new button/chip to the AMS section of the printer dashboard that appears when a pending assignment exists:

- Shows: spool name, color swatch, material
- Presents: 4 tray buttons for each AMS unit + External Spool button
- On tray selection: calls `script.assign_spool_to_printer_tray` with the selected tray entity
- Clears pending state after successful assignment

**Option B: Enhanced AMS tray popup**

Add an "Assign Spoolman Spool" action to the existing `ams_tray_popup.yaml`:

- New chip/button in the tray popup (alongside existing Pin Spool)
- Opens a spool picker (reusing the existing searchable pin-picker pattern)
- On selection: calls `script.assign_spool_to_printer_tray` with the selected spool + current tray
- Difference from pinning: this actually writes to the printer, not just the local tray map

**Option C: Input select + button card**

A simpler approach using existing card patterns:
- `input_select.tray_assignment_target` — dropdown of tray entities
- `input_text.tray_assignment_spool_id` — set by automation or manually
- Button card: "Apply Tray Assignment" triggers the assignment script

> **Recommendation**: Implement **Option A** as the primary flow (notification-driven with a simple tray picker) and **Option B** as a supplementary manual trigger (assign any spool to the current tray from the popup). Option C is too disconnected from context.

### 5. Manual Trigger: From AMS Tray Popup

Independent of the Spoolman-location-change flow, users should be able to manually push spool info to a tray from the existing popup UI.

#### Integration Point

In the existing `ams_tray_popup.yaml`, add a new action alongside the existing "Pin Spool" and "Weight Editor" actions:

**"Set on Printer" button**

- **Visible when**: Tray has a matched spool (via UUID, pin, or auto-match) AND the matched spool has sufficient data for `set_filament`
- **Hidden when**: Tray is empty or no spool is matched
- **Action**: Calls `script.assign_spool_to_printer_tray` with the matched spool ID and current tray entity
- **Confirmation**: Brief toast/notification "Set PLA Matte (Black) on AMS 1 Tray 3"

This allows the user to re-push filament info at any time — useful after firmware updates, AMS resets, or when Bambu Studio info drifts.

### 6. Non-Interference Rules

#### Bambu RFID Spools in AMS

When a Bambu Lab spool with a valid UUID is loaded into an AMS tray:
- The AMS RFID reader detects the spool automatically
- The printer sets the correct filament profile from Bambu's database
- **This system must not overwrite** that information

Check: `extra_spool_uuid` is non-empty AND target is AMS tray → skip assignment.

Exception: If the user explicitly triggers "Set on Printer" from the popup, allow it even for Bambu spools. This handles edge cases where RFID reading failed or data is stale.

#### Bambu Studio Concurrent Edits

If a user has already set filament info via Bambu Studio:
- The automated Spoolman-location-change flow checks printer state before writing
- If the tray already has non-empty type/color/profile that differs from what we'd set → option to skip or warn
- The manual "Set on Printer" action always writes (user explicitly chose to do it)

> **Open Question 5**: Should the automation check if the tray already has correct/recent data before overwriting?
>
> **Recommendation**: Yes. Before calling `set_filament`, check if the tray's current `type`, `color`, and `name` already match the Spoolman spool data (within tolerance for color hex). If they match, skip the call and log "Tray already configured correctly." This prevents unnecessary writes and preserves Bambu Studio edits.

### 7. Spoolman Location Values

The required location values already exist in Spoolman:

| Location Value | Maps To |
|---|---|
| `"AMS"` | AMS 1 (trays 1–4) |
| `"AMS 2"` | AMS 2 (trays 1–4) |
| `"External Spool Holder"` | External spool sensor |

The `sync_filter_options` automation dynamically discovers locations from spool entities. No changes required to the location vocabulary or filter infrastructure.

### 8. Authorization and Firmware Considerations

The `bambu_lab.set_filament` service requires **write access** to the printer, which depends on firmware and connection mode:

| Mode | Write Access | Notes |
|---|---|---|
| LAN Mode (Developer LAN Mode enabled) | Full write | Recommended setup for this feature |
| Hybrid mode (older firmware) | Full write | Works before authorization lockdown |
| Hybrid mode (newer firmware with Bambu Auth) | **Light only** | `set_filament` will fail; only chamber light controllable |
| Bambu Cloud only | Varies | Depends on firmware version |

**Design implication**: The assignment script must handle `set_filament` failures gracefully:
- Log the failure
- Create a persistent notification explaining the issue
- Suggest firmware/connection mode changes if the error indicates authorization failure

### 9. Filament Tag View Integration

The **filament tag view** (`view_filament_tags.yaml`) is designed for mobile phone use: the user scans an NFC tag on a filament swatch, the view resolves the matching Spoolman spool, and presents quick-action buttons to update the spool's location. This view is the **primary real-world entry point** for the Spoolman location changes that trigger AMS tray assignment.

#### Current Filament Tag Flow

```
Phone NFC scan → input_text.filament_id populated
    │
    ▼
sensor.selected_spool resolves matching Spoolman spool
(prefers unsealed spools; falls back to first match)
    │
    ▼
view_filament_tags.yaml shows:
  ┌──────────────────────────────────────┐
  │ Spool name + color + location        │
  │                                      │
  │  [  AMS  ]    [  AMS 2  ]           │  ← quick-action buttons
  │                                      │
  │  Desiccant / Drying tracking         │
  │  Full location dropdown              │
  └──────────────────────────────────────┘
    │
    ▼ (user taps AMS or AMS 2)
script.update_spool_location
    │
    ▼
spoolman.patch_spool(id, location: "AMS")
    │
    ▼
sensor.spoolman_spool_* location attribute updates
    │
    ▼ (THIS is the event that triggers the §1 automation)
spool_location_change_assign_tray automation fires
```

#### Key Observations

1. **The filament tag view IS the primary trigger source.** The "AMS" and "AMS 2" buttons call `script.update_spool_location`, which patches the spool's Spoolman location. That location change fires the `spool_location_change_assign_tray` automation from §1. No special integration is needed for the basic automated flow — it works as designed.

2. **The view currently lacks an "External Spool Holder" quick button.** Only "AMS" and "AMS 2" have dedicated buttons. Users must use the full location dropdown to set "External Spool Holder." A third quick-action button should be added for parity.

3. **No "Remove from AMS" quick action exists.** The user mentioned a core use case: marking a spool as *no longer* in the AMS. Currently the user must open the location dropdown and pick a shelf location. A "Remove from AMS" button (sets location to empty/shelf) would save taps.

4. **After tapping AMS, the user has no feedback about tray assignment.** The current flow completes the Spoolman location update silently. The user has no way to know whether the automation successfully assigned the tray, whether inference failed, or whether a notification was sent — they just see the location change.

5. **The filament tag view knows the spool identity** — all the data needed for `set_filament` is available in the view context (spool entity, material, color, profile). This opens the door for a combined action.

#### Proposed Enhancements

##### Enhancement A: Add "External Spool" Quick Button

Add a third quick-action button alongside "AMS" and "AMS 2":

```yaml
- tap_action:
    action: "${ spool_id ? 'perform-action' : 'none' }"
    perform_action: script.update_spool_location
    target: {}
    data:
      spool_id: ${ spool_id }
      location: External Spool Holder
  name: Ext. Spool
  icon: fas:arrow-right-to-bracket
```

This ensures all three AMS-adjacent locations have quick buttons.

##### Enhancement B: Tray Assignment Feedback

After the user taps "AMS" / "AMS 2" / "Ext. Spool", show inline feedback about the tray assignment result. Two approaches:

**B1: Passive feedback via status sensor**

Create a template sensor (`sensor.last_tray_assignment_result`) that the assignment automation updates after each attempt:

```
state: "success" | "needs_tray_selection" | "failed" | "skipped"
attributes:
  spool_name: "Sunlu PLA Matte (Black)"
  tray_entity: "sensor.p1s_..._ams_1_tray_3"
  message: "Set PLA on AMS 1 Tray 3"
  timestamp: "2026-03-24T12:00:00"
```

A conditional card in the filament tag view shows the result:
- Green chip: "✓ Set on AMS 1 Tray 3"
- Orange chip: "⚠ Select tray →" (links to tray picker)
- Red chip: "✗ Assignment failed" (links to notification)

**B2: Combined action script (future enhancement)**

Replace the two-phase flow (update location → automation fires) with a single script that does both:

```yaml
script.assign_spool_to_ams:
  fields:
    spool_id: ...
    location: ...    # "AMS", "AMS 2", "External Spool Holder"
    tray_entity: ... # optional — if omitted, infer
  sequence:
    - action: spoolman.patch_spool  # update Spoolman location
    - action: script.assign_spool_to_printer_tray  # push to printer
```

The filament tag view buttons would call this combined script instead of `script.update_spool_location`. The automation from §1 would still exist as a safety net for location changes made outside the filament tag view (e.g., from the Spoolman UI directly).

> **Recommendation**: Start with **Enhancement A** (External Spool button) in Phase 2 and **Enhancement B1** (passive feedback sensor) in Phase 3. Defer **B2** (combined action) to Phase 4 — it's cleaner but requires validating the automation-driven flow first.

##### Enhancement C: Inline Tray Picker on Inference Failure

When the automated tray inference fails after a filament tag location change, the current design sends a persistent notification. But the user is likely **still on the filament tag view** on their phone. Instead of (or in addition to) the notification, the view could display an inline tray picker:

```
┌──────────────────────────────────────┐
│ ⚠ Spool moved to AMS —              │
│   which tray did you load it into?   │
│                                      │
│ [ T1 ] [ T2 ] [ T3 ] [ T4 ]         │
└──────────────────────────────────────┘
```

The pending-assignment state from the automation (stored in `input_text.pending_tray_assignment_spool_id`) makes this conditional card visible. Tapping a tray button calls `script.assign_spool_to_printer_tray` with the explicit tray and clears the pending state.

> **Recommendation**: Include this in Phase 3 alongside the tray popup UI changes. The same pending-assignment helper drives both the notification and the inline tray picker.

##### Enhancement D: "Remove from AMS" Quick Action

Add a conditional button that appears when the spool's current location is "AMS", "AMS 2", or "External Spool Holder":

```yaml
# Only visible when spool is currently in an AMS location
- tap_action:
    action: "${ spool_id && isInAms ? 'perform-action' : 'none' }"
    perform_action: script.update_spool_location
    target: {}
    data:
      spool_id: ${ spool_id }
      location: ""    # clears location in Spoolman
  name: Remove
  icon: fas:arrow-right-from-bracket
```

This addresses the use case of "spool is no longer in the AMS." When the location changes away from an AMS value, no tray assignment automation fires (the automation only triggers on changes **to** AMS locations).

> **Open question**: Should removing a spool from AMS also clear the printer tray info? The printer doesn't have a "clear tray" action per se — the AMS detects physical removal. This is likely a no-op on the printer side, but could be useful for the External Spool holder.

#### Impact on Two-Phase vs. Combined Architecture

The filament tag view creates a natural opportunity for a **combined** flow (update location + assign tray in one action). However, the two-phase approach (location change → automation → assignment) is more robust because:

1. **It handles all trigger sources** — location changes from the Spoolman web UI, other HA automations, or the filament catalog view all fire the same automation.
2. **It's idempotent** — the automation can re-evaluate if triggered again.
3. **The filament tag view doesn't need to know about printer details** — separation of concerns.

The combined approach (Enhancement B2) should be a **future optimization**, not the initial architecture. The automation-driven flow is the correct foundation.

---

## Implementation Plan

### Phase 1: Core Infrastructure

| Task | Deliverable | Location |
|---|---|---|
| Data mapping script | `script.resolve_bambu_filament_params` — spool → set_filament params; calls `get_filament_data` inline for profile lookup; hardcoded generic fallback table for offline resilience | `spoolman_sync/scripts/` |
| Assignment orchestrator script | `script.assign_spool_to_printer_tray` — validates, resolves params, calls set_filament | `spoolman_sync/scripts/` |
| Pending assignment helper | `input_text.pending_tray_assignment_spool_id` | `spoolman_sync/helpers/` |
| Assignment result sensor | `sensor.last_tray_assignment_result` — tracks success/failure/pending for UI feedback | `spoolman_sync/template_sensors/` |

### Phase 2: Automated Flow

| Task | Deliverable | Location |
|---|---|---|
| Location change detection automation | Monitors `sensor.spoolman_spool_*` location changes | `spoolman_sync/automations/` |
| Tray inference logic | Within the automation or as a sub-script | `spoolman_sync/scripts/` |
| Non-interference checks | Pre-call validation (UUID skip, already-correct skip) | Within assignment script |
| Error handling | Persistent notifications for failures, auth issues | Within assignment script |
| Filament tag view: "Ext. Spool" button | Third quick-action button for External Spool Holder | `common/dashboard_views/view_filament_tags.yaml` |
| Filament tag view: "Remove" button | Conditional button to clear AMS location (visible when spool is in AMS) | `common/dashboard_views/view_filament_tags.yaml` |

### Phase 3: UI Integration

| Task | Deliverable | Location |
|---|---|---|
| "Set on Printer" button in tray popup | New action chip in `ams_tray_popup.yaml` | `common/dashboard_cards/card_templates/` |
| Pending assignment tray picker (notification) | Notification-linked card for tray selection when inference fails | `common/dashboard_cards/` or `spoolman_sync/dashboard_cards/` |
| Filament tag view: inline tray picker | Conditional card in filament tag view showing tray buttons when pending assignment exists | `common/dashboard_views/view_filament_tags.yaml` |
| Filament tag view: assignment status | Conditional chip showing last assignment result (success/pending/failed) | `common/dashboard_views/view_filament_tags.yaml` |
| Confirmation feedback | Toast or brief notification on success | Within assignment script |

### Phase 4: Refinement

| Task | Deliverable | Location |
|---|---|---|
| Tray state change correlation | Monitor AMS tray Empty→non-empty transitions within a time window after Spoolman location change to confirm which tray a spool was loaded into (see §2: Tray State Change Correlation) | `spoolman_sync/automations/` |
| Combined location + assign script | `script.assign_spool_to_ams` — single script that updates Spoolman location AND pushes to printer tray; filament tag view calls this instead of `update_spool_location` for a tighter feedback loop (see §9: Enhancement B2) | `spoolman_sync/scripts/` |
| Batch assignment | Handle multiple spool location changes at once | Enhancement to Phase 2 automation |

---

## Affected Files

### New Files

| File | Purpose |
|---|---|
| `spoolman_sync/scripts/assign_spool_to_printer_tray-script.yaml` | Orchestrator: validate, map, call `set_filament` |
| `spoolman_sync/scripts/resolve_bambu_filament_params-script.yaml` | Data mapping: spool attrs → `set_filament` params (calls `get_filament_data` inline) |
| `spoolman_sync/automations/spool_location_change_assign_tray.yaml` | Trigger on location change → assignment flow |
| `spoolman_sync/helpers/input_text/input_text_pending_tray_assignment.yaml` | Pending assignment spool ID |
| `spoolman_sync/template_sensors/template_sensor_last_tray_assignment_result.yaml` | Assignment result status for UI feedback |
| `docs/features/spoolman_sync/ams-tray-assignment-data-mapping.md` | Supplemental doc: data mapping details |

### Modified Files

| File | Change |
|---|---|
| `common/dashboard_cards/card_templates/ams_tray_popup.yaml` | Add "Set on Printer" action chip |
| `common/dashboard_views/view_filament_tags.yaml` | Add "Ext. Spool" + "Remove" quick buttons; add assignment status chip; add inline tray picker for pending assignments |
| `filament_tag/scripts/update_spool_location-script.yaml` | No change needed — existing script patches Spoolman; the location change triggers the new automation |
| `docs/features/spoolman_sync/spoolman-custom-fields.md` | Document "External Spool Holder" as a trigger location |

---

## Risks

| Scenario | Risk | Severity | Mitigation |
|---|---|---|---|
| `bambu_lab.set_filament` fails silently | High | Medium | Check tray state after call; verify attributes changed |
| Firmware auth blocks write access | High | High | Detect failure, notify user with firmware guidance |
| `tray_info_idx` mapping is wrong/stale | Medium | Medium | Dynamic lookup from `get_filament_data`; hardcoded fallback table |
| `get_filament_data` response format changes | Medium | Low | Version-check; fallback to hardcoded table |
| Spool loaded during active print | Medium | High | Check printer status before calling `set_filament`; defer if printing |
| Race condition: location change + tray state change timing | Medium | Medium | Simple empty-tray-count approach avoids timing dependency |
| Overwriting user's Bambu Studio edits | Medium | Medium | Pre-check tray state; skip if already correct |
| Filament tag view user doesn't see tray assignment result | Medium | Medium | Assignment result sensor + conditional status chip in filament tag view (Phase 3) |
| Combined script bypasses automation safeguards | Low | Low | Automation remains as safety net; combined script is an optimization in Phase 4 |

---

## Test Matrix

| Scenario | Expected Result |
|---|---|
| Non-Bambu spool location → "AMS", 1 empty tray | Auto-infer tray, set_filament called, confirmation shown |
| Non-Bambu spool location → "AMS", 0 empty trays | Notification: "Please select tray"; pending assignment created |
| Non-Bambu spool location → "AMS", 2+ empty trays | Notification: "Multiple empty trays — please select"; pending assignment created |
| Bambu spool (with UUID) location → "AMS" | Skipped — RFID handles it; no set_filament call |
| Bambu spool (with UUID) location → "External Spool" | set_filament called (external has no RFID reader) |
| Any spool location → "External Spool" | set_filament called on external_spool entity |
| Spool missing `filament_material` | Assignment blocked; notification: "Incomplete spool data" |
| `set_filament` fails (auth error) | Persistent notification with firmware guidance |
| Printer is actively printing when spool loaded | Assignment deferred; notification: "Will assign after print completes" |
| Manual "Set on Printer" from tray popup | set_filament called for matched spool + current tray |
| Tray already has correct filament info | Skip set_filament; log "Already configured" |
| Profile name matches Bambu profile exactly | Use matched profile's `tray_info_idx` and temp range |
| Profile name has no Bambu match | Use generic profile for the material type |
| Location change to non-AMS/non-External | No action taken |
| **Filament Tag View scenarios** | |
| NFC scan → tap "AMS" button in filament tag view | Spoolman location updated → automation fires → tray assignment attempted |
| NFC scan → tap "AMS 2" button | Same as above, targeting AMS 2 trays |
| NFC scan → tap "Ext. Spool" button (new) | Spoolman location updated → automation fires → external spool assignment (no tray inference needed) |
| NFC scan → tap "Remove" button (new, spool currently in AMS) | Spoolman location cleared → no tray assignment automation fires |
| Tray inference fails after filament tag AMS tap | Inline tray picker shown in filament tag view + notification sent |
| Assignment succeeds after filament tag AMS tap | Status chip shows "✓ Set on AMS 1 Tray 3" in filament tag view |
| Filament tag view with no spool selected | All quick-action buttons disabled/hidden |

---

## Open Questions Summary

| # | Question | Recommendation | Status |
|---|---|---|---|
| 1 | ~~Add "External Spool" to Spoolman location vocabulary?~~ | N/A — `"External Spool Holder"` already exists | **Resolved** |
| 2 | Use timing heuristics for tray inference? | Defer — start with empty-tray-count; timing-based correlation deferred to Phase 4 | Pending decision |
| 3 | ~~How to map "AMS" vs "AMS 2" locations?~~ | `"AMS"` → AMS 1, `"AMS 2"` → AMS 2 | **Resolved** |
| 4 | ~~How to validate `tray_info_idx` codes?~~ | Validated against `filaments_detail.json` bundled with ha-bambulab. `get_filament_data` returns this merged with slicer custom profiles. Generic fallback codes confirmed: GFL99=PLA, GFG99=PETG, GFB99=ABS, GFB98=ASA, GFU99=TPU, GFN99=PA, GFC99=PC, GFS99=PVA | **Resolved** |
| 5 | Check if tray already has correct data before writing? | Yes — skip if already correct | Pending decision |
| 6 | ~~How to store filament lookup cache?~~ | No caching. Call `get_filament_data` inline at assignment time (local call, fast). Hardcoded generic fallback table for offline resilience. | **Resolved** |
| 7 | Should "Set on Printer" work for Bambu spools too? | Yes — as explicit override when user initiates manually | Pending decision |
| 8 | Should assignment be deferred if printer is printing? | Yes — queue and apply after print completes | Pending decision |
| 9 | Should the filament tag view use a combined script (location + assign) or rely on the automation? | Start with automation-driven flow (two-phase); combined script deferred to Phase 4 (see §9: Enhancement B2) | Pending decision |
| 10 | Should removing a spool from AMS also clear the printer tray info? | Likely no-op — the AMS detects physical removal. May be relevant for External Spool. | Pending decision |

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| `ha-bambulab` integration | v2.2.x+ — requires `bambu_lab.set_filament` and `bambu_lab.get_filament_data` services |
| Spoolman integration | Must expose `location` attribute on `sensor.spoolman_spool_*` entities |
| Printer firmware | Must support write operations (LAN Mode or pre-auth-lockdown firmware) |
| `sensor.spoolman_tray_map` | Existing — unchanged; used for read-side matching and spool data access |
| `sensor.smart_status` | Existing — used to check if printer is actively printing |
| Filament Tag package | Existing — `view_filament_tags.yaml`, `script.update_spool_location`, `sensor.selected_spool` are modified/referenced |

---

## Related Documents

- [Manual Spool Matching Design](manual-spool-matching-design.md) — Pin/unpin system this feature complements
- [Find Matching Spools](find-matching-spools.md) — Spool matching algorithm (read-side)
- [Spoolman Custom Fields](spoolman-custom-fields.md) — Required Spoolman schema setup
- [Multicolor Spool Matching](multicolor-spool-matching-design.md) — Multi-color matching rules
- [AMS Tray Assignment Data Mapping](ams-tray-assignment-data-mapping.md) — Supplemental: detailed mapping tables
- [Filament Tag README](../filament_tag/README.md) — NFC tag scanning + spool location management (primary trigger source)
