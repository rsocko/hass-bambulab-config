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
| `filament_color_hex` | `tray_color` | Single-color fallback; 6-char hex normalized and converted to RGBA |
| `filament_multi_color_hexes` | `tray_color` | For multi-color spools, use the first hex in the comma-separated list as primary tray color |
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
| **How to detect Spoolman location changes?** | Monitor `select.spoolman_spool_*_location` state changes via state trigger | Location is the primary state of the dedicated Spoolman location entity |
| **What if tray can't be inferred?** | Persistent notification + inline tray picker in filament tag view + tray picker in ams_tray_popup | User picks the tray from the UI they're currently in |
| **Overwrite Bambu RFID spools?** | Never in AMS trays; always for External Spool | AMS has RFID reader; External Spool never does |
| **Filament data storage strategy** | No caching — call `get_filament_data` inline at assignment time | Local service call is fast; hardcoded generic fallback for offline resilience |
| **Nozzle temp when only single value?** | Use ±10°C range from `filament_settings_extruder_temp`, or use Bambu profile defaults from lookup table | Safe default; overridden by profile match if found |
| **Feature placement** | New files in `spoolman_sync/` (automations, scripts) + view modifications in `filament_tag/` and `common/` | Core logic in spoolman_sync domain; UI touchpoints in filament tag view and AMS tray popup |
| **Filament tag view role** | Primary real-world trigger source; enhanced with feedback + inline tray picker | NFC scan → tap AMS → location change → automation fires. View gets status feedback in Phase 3. |
| **Two-phase vs. combined action** | Start with two-phase (location change → automation); combined script deferred to Phase 6 | Two-phase is more robust: handles all trigger sources, is idempotent, maintains separation of concerns |
| **Concurrent spool assignments** | Single-spool-at-a-time for Phases 1–4; multi-spool queuing added in Phase 5 | Primary workflow is single-spool (NFC scan → tap AMS); queuing is a reliability enhancement, not a day-one requirement |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         TRIGGER SOURCES                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  (A) Spoolman location change         (B) Manual action from HA UI   │
│      select.spoolman_spool_*_location     "Set on Printer" in         │
│      state → "AMS" / "AMS 2"              ams_tray_popup.yaml        │
│             / "External Spool Holder"      (direct assign action)     │
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

An automation monitors all `select.spoolman_spool_*_location` entities for state changes. When a spool's location state changes **to** a value indicating AMS or External Spool placement, the assignment flow begins.

**Location values that trigger assignment:**
- `"AMS"` — spool placed into AMS unit 1
- `"AMS 2"` — spool placed into AMS unit 2 (if present)
- `"External Spool Holder"` — spool placed on the external spool holder

> **Resolved (Q1)**: `"External Spool Holder"` already exists as a Spoolman location value. No vocabulary changes needed. The `sync_filter_options` automation dynamically discovers locations from spool entities, so it will appear in filters automatically.

**Important note on Spoolman location field behavior:**

The Spoolman `location` field is freeform text. The Spoolman API only returns location values that are currently assigned to at least one spool. This means:

- **Trigger automation**: No issue — the automation watches the state of `select.spoolman_spool_*_location` entities for specific string values regardless of any dropdown.
- **User setting the location**: If no spool currently has `"External Spool Holder"` as its location, the value will not appear as an auto-suggest option in the Spoolman UI. The user must type it manually the first time. Once at least one spool has the value, it will appear in location dropdowns and filter options.
- **First-use bootstrapping**: Consider documenting the exact location strings (`"AMS"`, `"AMS 2"`, `"External Spool Holder"`) in user-facing setup docs or as a tooltip/helper text so users know the expected values. Alternatively, a one-time setup script could assign and then unassign these location values to a dummy spool to seed the Spoolman auto-suggest list.

#### Conditions

Before proceeding with assignment:

1. **Spool is non-Bambu OR target is External Spool**
   - If `filament_vendor_name == "Bambu Lab"` AND `extra_spool_uuid` is non-empty AND target is an AMS tray → **skip** (RFID will handle it)
   - If target is External Spool → **always proceed** (no RFID reader)
   
2. **Spool data is sufficient**
   - `filament_material` is present
  - At least one color source is present:
    - `filament_multi_color_hexes` with a valid first hex entry, or
    - `filament_color_hex`
  - If neither color source is usable, block assignment and notify: "Incomplete spool data: missing usable color"
  - `filament_extra_profile_name` and `filament_settings_extruder_temp` are optional when material defaults exist
  - If both are missing and no material default exists, block assignment and notify: "Incomplete spool data: missing profile/temp and unsupported material"

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

Use this precedence:

1. If `filament_multi_color_hexes` is non-empty, parse the first comma-separated hex value and use it.
2. Otherwise, use `filament_color_hex`.
3. If neither is usable, block assignment with an actionable notification.

```
tray_color = selected_hex (6-char RGB) + "FF" (opaque alpha)
```

Examples:

- Single-color: `filament_color_hex = "da291c"` → `tray_color = "DA291CFF"`
- Multi-color: `filament_multi_color_hexes = "ff0000,00ff00,0000ff"` → first hex `FF0000` → `tray_color = "FF0000FF"`

#### Temperature Mapping

| Source | Strategy |
|---|---|
| Bambu profile match found | Use `nozzle_temp_min` and `nozzle_temp_max` from the matched Bambu profile |
| Only `filament_settings_extruder_temp` available | Use `temp - 10` as min, `temp + 10` as max |
| No temperature data | Use material-type defaults from the hardcoded table |
| No temperature data and material not in defaults | Block assignment and create actionable notification |

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

> **Future Idea (Out of Scope for Initial Implementation)**
>
> Add an optional combined manual action mode in the tray popup:
>
> - **Current behavior (default)**: "Set on Printer" only calls `script.assign_spool_to_printer_tray`
> - **Future optional mode**: "Set on Printer + Update Location" also updates the spool's Spoolman location based on the selected tray context
>
> This is intentionally deferred so the initial implementation keeps a clear separation between:
>
> - location-driven automation (A-path)
> - explicit manual printer write (B-path)

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
- Preserve existing tray data only when it matches the computed Spoolman target **exactly** (`type`, `color`, and `name`)
- If any of those fields differ, do not silently keep existing values: create a warning/informational notification and require explicit user override
- The manual "Set on Printer" action always writes (user explicitly chose to do it)
- Users can still adjust individual attributes manually in the Bambu AMS Card UI when partial edits are preferred

> **Open Question 5**: Should the automation check if the tray already has correct/recent data before overwriting?
>
> **Recommendation**: Yes. Before calling `set_filament`, compare the tray's current `type`, `color`, and `name` against the computed Spoolman target using exact equality. If all three match, skip the call and log "Tray already configured correctly." If any field differs, issue a warning/informational notification and require explicit user action (for example, "Set on Printer") to apply Spoolman values.

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
select.spoolman_spool_*_location state updates
    │
    ▼ (THIS is the event that triggers the §1 automation)
spool_location_change_assign_tray automation fires
```

#### Key Observations

1. **The filament tag view IS the primary trigger source.** The "AMS" and "AMS 2" buttons call `script.update_spool_location`, which patches the spool's Spoolman location. That location change fires the `spool_location_change_assign_tray` automation from §1. No special integration is needed for the basic automated flow — it works as designed.

2. **The view currently lacks an "External Spool Holder" quick button.** Only "AMS" and "AMS 2" have dedicated buttons. Users must use the full location dropdown to set "External Spool Holder." A third quick-action button should be added for parity.

3. **After tapping AMS, the user has no feedback about tray assignment.** The current flow completes the Spoolman location update silently. The user has no way to know whether the automation successfully assigned the tray, whether inference failed, or whether a notification was sent — they just see the location change.

4. **The filament tag view knows the spool identity** — all the data needed for `set_filament` is available in the view context (spool entity, material, color, profile). This opens the door for a combined action.

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

> **Recommendation**: Start with **Enhancement A** (External Spool button) in Phase 2 and **Enhancement B1** (passive feedback sensor) in Phase 3. Defer **B2** (combined action) to Phase 6 — it's cleaner but requires validating the automation-driven flow first.

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

#### Impact on Two-Phase vs. Combined Architecture

The filament tag view creates a natural opportunity for a **combined** flow (update location + assign tray in one action). However, the two-phase approach (location change → automation → assignment) is more robust because:

1. **It handles all trigger sources** — location changes from the Spoolman web UI, other HA automations, or the filament catalog view all fire the same automation.
2. **It's idempotent** — the automation can re-evaluate if triggered again.
3. **The filament tag view doesn't need to know about printer details** — separation of concerns.

The combined approach (Enhancement B2) should be a **future optimization**, not the initial architecture. The automation-driven flow is the correct foundation.

### 10. Label-Based Entity Discovery and Trigger Enhancement

#### Problem

The Phase 2 trigger automation (`spool_location_change_assign_tray`) uses `platform: event, event_type: state_changed`, which fires for **every entity state change** in the entire HA instance. While the `mode: parallel` fix (applied in Phase 2 bugfix) prevents queue saturation, the automation still evaluates a condition check for every state change — even from completely unrelated integrations. Additionally, the regex pattern used to filter spool entities (`select\.spoolman_spool_\d+_location`) must be manually maintained and is brittle if the Spoolman integration ever changes its entity naming convention.

A second issue arises as the user purchases new spools: Spoolman creates new `select.spoolman_spool_*_location` entities that the automation should immediately monitor. The regex pattern handles this automatically today, but a more maintainable label-based approach offers benefits for both the trigger condition and broader service targeting.

#### Solution: HA Labels for Spool Entity Targeting

Use Home Assistant [labels](https://www.home-assistant.io/docs/organizing/labels/) (available since HA 2024.4) to tag all Spoolman spool location entities. The automation condition then checks label membership instead of regex matching.

**Label definition:**

| Property | Value |
|---|---|
| Name | `Spoolman Spool Location` |
| Label ID | `spoolman_spool_location` |
| Icon | `mdi:label-variant` |
| Color | (optional, user preference) |

**Applies to:** All `select.spoolman_spool_*_location` entities created by the Spoolman integration.

#### Trigger Automation Condition Update

Replace the regex-based condition in `spool_location_change_assign_tray.yaml` with a label-based check:

**Current (regex-based):**
```yaml
condition:
  - condition: template
    value_template: >-
      {{ trigger.event.data.entity_id is match('select\\.spoolman_spool_\\d+_location') }}
```

**Proposed (label-based):**
```yaml
condition:
  - condition: template
    value_template: >-
      {{ trigger.event.data.entity_id in label_entities('spoolman_spool_location') }}
```

**Benefits:**
- `label_entities()` is evaluated at **runtime** for each trigger — no automation reload needed when new entities are labeled
- Semantically clear: the label declares intent ("this entity is a spool location selector")
- Decoupled from entity naming convention — works even if entity ID format changes
- Can be reused across other automations, scripts, and service targets (e.g., batch operations on all spool location entities)

**Performance note:** `label_entities()` is a fast registry lookup (in-memory), comparable to the regex evaluation it replaces. The `platform: event` trigger still fires for all state changes, but the condition exits almost immediately for non-labeled entities.

#### Auto-Labeling New Spool Entities

When new spools are purchased and added to Spoolman, the integration creates new `select.spoolman_spool_*_location` entities. These need the `spoolman_spool_location` label applied.

**Strategy A: REST-Based Auto-Labeling Automation (Recommended)**

An automation that runs periodically discovers unlabeled Spoolman spool location entities and applies the label via the HA entity registry REST API.

```yaml
automation:
  alias: "Auto-Label Spoolman Spool Location Entities"
  id: auto_label_spoolman_spool_location_entities
  description: >-
    Discovers select.spoolman_spool_*_location entities that are missing the
    spoolman_spool_location label and applies it via the entity registry API.
    Runs on HA start and periodically to catch newly added spools.
  triggers:
    - trigger: homeassistant
      event: start
    - trigger: time_pattern
      hours: "/6"
  mode: single
  action:
    - variables:
        labeled: "{{ label_entities('spoolman_spool_location') }}"
        all_spoolman: >-
          {{ states.select
             | selectattr('entity_id', 'match', 'select\\.spoolman_spool_\\d+_location')
             | map(attribute='entity_id')
             | list }}
        unlabeled: "{{ all_spoolman | reject('in', labeled) | list }}"
    - condition: template
      value_template: "{{ unlabeled | length > 0 }}"
    - repeat:
        for_each: "{{ unlabeled }}"
        sequence:
          - action: rest_command.label_spoolman_entity
            data:
              entity_id_to_label: "{{ repeat.item }}"
              current_labels: "{{ labels(repeat.item) | list }}"
    - action: logbook.log
      data:
        name: "Spoolman Label Sync"
        message: "Applied spoolman_spool_location label to {{ unlabeled | length }} new entities: {{ unlabeled | join(', ') }}"
        entity_id: automation.auto_label_spoolman_spool_location_entities
```

**Supporting REST command:**

```yaml
rest_command:
  label_spoolman_entity:
    url: "http://localhost:8123/api/config/entity_registry"
    method: POST
    headers:
      Authorization: !secret ha_long_lived_token_bearer
      Content-Type: application/json
    payload: >-
      {
        "entity_id": "{{ entity_id_to_label }}",
        "labels": {{ (current_labels + ['spoolman_spool_location']) | unique | list | to_json }}
      }
```

> **Note**: This requires a [long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile) stored in `secrets.yaml` as `ha_long_lived_token_bearer: "Bearer <token>"`. The token is only used for local entity registry updates and never leaves the HA instance.

**Strategy B: Notification-Based Manual Labeling (Simpler Alternative)**

For users who prefer not to store a long-lived token, a simpler approach notifies the user when new unlabeled entities are detected:

```yaml
automation:
  alias: "Notify: Unlabeled Spoolman Spool Entities"
  triggers:
    - trigger: homeassistant
      event: start
    - trigger: time_pattern
      hours: "/6"
  mode: single
  action:
    - variables:
        labeled: "{{ label_entities('spoolman_spool_location') }}"
        all_spoolman: >-
          {{ states.select
             | selectattr('entity_id', 'match', 'select\\.spoolman_spool_\\d+_location')
             | map(attribute='entity_id')
             | list }}
        unlabeled: "{{ all_spoolman | reject('in', labeled) | list }}"
    - condition: template
      value_template: "{{ unlabeled | length > 0 }}"
    - action: persistent_notification.create
      data:
        title: "New Spoolman Spools Need Labeling"
        notification_id: spoolman_unlabeled_entities
        message: >-
          {{ unlabeled | length }} new spool location entities need the
          `spoolman_spool_location` label applied:
          {% for e in unlabeled %}
          - {{ e }}
          {% endfor %}
          Go to Settings → Devices & Services → Entities tab, filter by
          "spoolman", select the unlabeled entities, and apply the
          "Spoolman Spool Location" label.
```

**Strategy comparison:**

| Aspect | Strategy A (REST auto-label) | Strategy B (Notify) |
|---|---|---|
| User intervention | None after initial token setup | Manual label application each time |
| Complexity | Medium — requires REST command + token | Low — standard automation |
| New spool delay | Up to 6 hours (or next HA restart) | Same, but user must act on notification |
| Security consideration | Long-lived token in `secrets.yaml` | None |
| Recommended for | Users with many spools or frequent purchases | Users with stable spool inventory |

> **Recommendation**: Start with **Strategy B** for simplicity. Migrate to **Strategy A** if manual labeling becomes tedious (more than ~2 new spools/month).

#### Future: State Trigger Migration

The HA `platform: state` trigger currently accepts only a **static list** of entity IDs. It does not support `label_entities()` in the `entity_id` parameter (which would require [limited template](https://www.home-assistant.io/docs/configuration/templating/#limited-templates) support for `label_entities()`, which is not available as of HA 2026.3).

If/when HA adds native label-based entity targeting for state triggers, the automation trigger could migrate from:

```yaml
# Current: event-based (fires for ALL entity changes)
triggers:
  - trigger: event
    event_type: state_changed
```

To:

```yaml
# Future: state-based with label targeting (fires only for labeled entities)
triggers:
  - trigger: state
    entity_id: "{{ label_entities('spoolman_spool_location') }}"
    to:
      - "AMS"
      - "AMS 2"
      - "External Spool Holder"
```

This would eliminate the need for any condition-based filtering — the trigger itself would only fire for relevant entities transitioning to relevant states. Until this is supported, the `platform: event` + label condition approach is the recommended pattern.

> **Tracking**: Watch the [HA architecture discussions](https://github.com/home-assistant/architecture/discussions) and [core release notes](https://www.home-assistant.io/blog/) for label-based trigger support. This would likely appear as an enhancement to the state trigger platform.

#### Migration Path Summary

| Phase | Trigger | Condition | Label Usage |
|---|---|---|---|
| Phase 2 (current) | `platform: event, event_type: state_changed` | Regex: `select\.spoolman_spool_\d+_location` | None |
| Phase 4 (label adoption) | `platform: event, event_type: state_changed` | `label_entities('spoolman_spool_location')` | Condition check + auto-labeling automation |
| Future (HA label triggers) | `platform: state` with label entity targeting | Built into trigger | Trigger targeting + auto-labeling automation |

### 11. Known Limitation: Multi-Spool Concurrent Assignment

#### Current State (Phases 1–4)

The tray assignment system is designed around a **single-spool-at-a-time workflow**: scan an NFC tag, tap "AMS" in the filament tag view, and the automation assigns the spool to a tray. This covers the primary real-world use case. However, several components have single-value bottlenecks that cause data loss when multiple spool location changes overlap.

#### Concurrency Weak Points

| Component | Behavior | Data Loss Risk |
|---|---|---|
| **Automation mode** (`spool_location_change_assign_tray`) | No explicit `mode:` — defaults to `single`. If the automation is still executing when a second location change fires, the second trigger is **silently dropped**. In practice, back-to-back changes seconds apart both fire (the automation is fast), but near-simultaneous changes can lose one. | Possible — depends on timing |
| **Pending spool ID** (`input_text.pending_tray_assignment_spool_id`) | Stores a **single spool ID** (scalar, max 32 chars). When the "needs_tray_selection" path fires for spool A, then spool B triggers the same path, the helper is **overwritten** with spool B. Spool A's pending assignment is silently lost. The tray picker popup only shows spool B. | **Yes** — last write wins |
| **Deferred (printer busy)** | When the printer is actively printing, the assign script returns status `deferred` with a persistent notification and **stops**. There is no retry queue or "run when print finishes" mechanism. The assignment is fire-and-forget — whether it is one spool or five. | **Yes** — all deferred spools lost |

#### What IS Queued Today

The orchestrator script (`script.assign_spool_to_printer_tray`) is `mode: queued`. If multiple calls enter the script **and** the printer is idle **and** tray inference succeeds for each, they execute in FIFO order. This is the happy path — e.g., two spools moved to different AMS units where each has exactly one empty tray.

#### Scenario Matrix

| Scenario | Behavior | Data Loss? |
|---|---|---|
| Two spools, both trays auto-inferred, printer idle | Queued in script — both succeed | No |
| Two spools, both need manual tray selection | Last write wins on `input_text` — first spool lost | **Yes** |
| Two spools while printer is busy | Both get `deferred` + notification, neither retried | **Yes** (both) |
| Two spools fired near-simultaneously | Automation `single` mode may drop one trigger | **Possible** |

#### Design Rationale

The single-spool design is intentional for Phases 1–4. The primary workflow — NFC scan a single spool, tap AMS, wait for assignment — is inherently sequential. Multi-spool queuing adds complexity (list-based helpers, queue drain automation, deferred retry logic) that is not justified until the core flow is validated. Phase 5 introduces queuing as a reliability enhancement.

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
| Location change detection automation | Monitors `select.spoolman_spool_*_location` state changes | `spoolman_sync/automations/` |
| Tray inference logic | Within the automation or as a sub-script | `spoolman_sync/scripts/` |
| Non-interference checks | Pre-call validation (UUID skip, already-correct skip) | Within assignment script |
| Error handling | Persistent notifications for failures, auth issues | Within assignment script |
| Filament tag view: "Ext. Spool" button | Third quick-action button for External Spool Holder | `common/dashboard_views/view_filament_tags.yaml` |

### Phase 3: UI Integration

| Task | Deliverable | Location |
|---|---|---|
| "Set on Printer" chip in tray popup | Action chip in `ams_tray_popup.yaml` — calls `assign_spool_to_printer_tray` with `force_write: true` via `browser_mod.sequence`; auto-closes popup after 2 s | `common/dashboard_cards/card_templates/` |
| Shared status chip + popup tray picker | `tray_assignment_status_and_picker.yaml` — reusable `!include` shared across Home, Filament Tags, and Filament Catalog views. Conditional chip (hidden when idle) shows color-coded status. On tap, opens a `browser_mod.popup` with AMS 1 / AMS 2 tray buttons. | `spoolman_sync/dashboard_cards/` |
| Dashboard wrapper script | `script.assign_pending_spool_to_tray` — reads `input_text.pending_tray_assignment_spool_id` server-side and delegates to `assign_spool_to_printer_tray`. Required because browser_mod popup `perform-action` data fields cannot evaluate Jinja2 templates or `config-template-card` JS. | `spoolman_sync/scripts/` |
| View includes | `!include` of the shared status/picker card added to `view_main.yaml`, `view_filament_tags.yaml`, and `view_filament_catalog.yaml` | `common/dashboard_views/`, `filament_catalog/dashboard_views/` |
| Confirmation feedback | Persistent notification on success | Within assignment script |

> **Implementation Note (Phase 3)**: The original design proposed an inline tray picker rendered directly in the filament tag view. During implementation, rendering issues with `config-template-card` inside conditional cards and grid layouts led to a refactor: the tray picker is now presented as a **browser_mod popup** triggered by tapping the status chip. This approach is layout-agnostic, works identically on all three views, and avoids client-side template evaluation constraints. A dedicated wrapper script (`assign_pending_spool_to_tray`) bridges the gap between the popup's client-side tap actions and the server-side pending spool ID.

### Phase 4: Label-Based Entity Discovery

| Task | Deliverable | Location |
|---|---|---|
| Create `spoolman_spool_location` label | One-time label creation via HA UI (Settings → Areas, Labels & Zones → Labels) | HA entity registry |
| Apply label to existing spool location entities | Bulk-select all `select.spoolman_spool_*_location` entities and apply label | HA UI (Settings → Devices & Services → Entities) |
| Unlabeled entity notification automation | `automation.notify_unlabeled_spoolman_spool_entities` — runs on HA start + every 6h; notifies when new spool entities are missing the label (Strategy B from §10) | `spoolman_sync/automations/` |
| Trigger condition migration | Update `spool_location_change_assign_tray.yaml` condition from regex to `label_entities('spoolman_spool_location')` | `spoolman_sync/automations/` |
| (Optional) REST auto-labeling | `rest_command.label_spoolman_entity` + `automation.auto_label_spoolman_spool_location_entities` — Strategy A from §10; requires long-lived token | `spoolman_sync/automations/` + `spoolman_sync/rest_commands/` |

### Phase 5: Multi-Spool Queuing

Addresses the concurrency limitations documented in §11. Converts the single-spool pending assignment model into a multi-spool queue with deferred retry.

| Task | Deliverable | Location |
|---|---|---|
| Automation mode upgrade | Change `spool_location_change_assign_tray` from implicit `single` to `mode: queued` (or `mode: parallel` with `max: 4`). Ensures back-to-back location changes are not silently dropped. | `spoolman_sync/automations/` |
| Pending assignment queue helper | Replace scalar `input_text.pending_tray_assignment_spool_id` with a list-capable store. **Option A**: JSON array in an `input_text` (e.g., `[{"spool_id": "42", "location": "AMS", "ts": "..."}]`). **Option B**: Trigger-based template sensor that appends to an attribute list on `spoolman_tray_assignment_queued` events and removes entries on `spoolman_tray_assignment_result` events. Option B is preferred — it avoids max-length limits and supports atomic add/remove without read-modify-write races. | `spoolman_sync/helpers/` or `spoolman_sync/template_sensors/` |
| Queue-aware tray picker UI | Update `tray_assignment_status_and_picker.yaml` to show all queued spools (not just the latest). Chip content changes from "Tap to select tray" to "2 spools awaiting tray selection". Popup lists each pending spool with its own tray picker row. | `spoolman_sync/dashboard_cards/` |
| Dashboard wrapper update | Update `script.assign_pending_spool_to_tray` to accept a `spool_id` field (or read from popup context) instead of always reading the scalar helper. Supports assigning a specific spool from the multi-spool popup. | `spoolman_sync/scripts/` |
| Deferred assignment retry | New automation: triggers on `sensor.ntk_ryansoffice_3dprinter_print_status` transitioning **out of** active states (`running`, `pause`, `prepare` → `idle`, `finish`, `failed`). On trigger, drains all queued deferred assignments by re-calling `script.assign_spool_to_printer_tray` for each entry. Entries that were deferred due to printer-busy are replayed; entries needing tray selection remain in the queue. | `spoolman_sync/automations/` |
| Queue cleanup | Entries older than a configurable threshold (e.g., 24 hours) are pruned automatically. Stale entries get a persistent notification before removal so the user is aware. | Within queue drain automation |
| Backward compatibility | `input_text.pending_tray_assignment_spool_id` retained (but deprecated) during transition. Phase 3 UI and `assign_pending_spool_to_tray` script continue to work if queue sensor is unavailable. | `spoolman_sync/scripts/` |

> **Implementation Note**: The queue-based template sensor pattern is similar to `sensor.print_job_ams_tray_storage` — a trigger-based sensor that stores structured data in attributes. The same append/clear pattern applies.

### Phase 6: Refinement

| Task | Deliverable | Location |
|---|---|---|
| Tray state change correlation | Monitor AMS tray Empty→non-empty transitions within a time window after Spoolman location change to confirm which tray a spool was loaded into (see §2: Tray State Change Correlation) | `spoolman_sync/automations/` |
| Combined location + assign script | `script.assign_spool_to_ams` — single script that updates Spoolman location AND pushes to printer tray; filament tag view calls this instead of `update_spool_location` for a tighter feedback loop (see §9: Enhancement B2) | `spoolman_sync/scripts/` |
| State trigger migration | When HA supports label-based entity targeting in `platform: state` triggers, migrate from `platform: event` + label condition to native label trigger (see §10: Future Migration) | `spoolman_sync/automations/` |

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
| `spoolman_sync/automations/notify_unlabeled_spoolman_spool_entities.yaml` | Phase 4: notifies when new spool entities need labeling |
| `spoolman_sync/automations/auto_label_spoolman_spool_location_entities.yaml` | Phase 4 (optional): auto-applies label via REST API |
| `spoolman_sync/rest_commands/label_spoolman_entity.yaml` | Phase 4 (optional): REST command for entity registry label update |
| `spoolman_sync/scripts/assign_pending_spool_to_tray-script.yaml` | Phase 3: Dashboard wrapper — reads pending spool ID server-side, delegates to `assign_spool_to_printer_tray` |
| `spoolman_sync/dashboard_cards/tray_assignment_status_and_picker.yaml` | Phase 3: Shared include — conditional status chip + browser_mod popup tray picker |
| `spoolman_sync/template_sensors/template_sensor_pending_tray_assignment_queue.yaml` | Phase 5: Trigger-based queue sensor — appends on `spoolman_tray_assignment_queued` events, removes on `spoolman_tray_assignment_result` events |
| `spoolman_sync/automations/drain_deferred_assignments_on_print_complete.yaml` | Phase 5: Retry deferred assignments when printer transitions from active to idle/finish/failed |

### Modified Files

| File | Change |
|---|---|
| `common/dashboard_cards/card_templates/ams_tray_popup.yaml` | Add "Set on Printer" action chip |
| `common/dashboard_views/view_main.yaml` | Add `!include` of shared status chip + popup tray picker |
| `common/dashboard_views/view_filament_tags.yaml` | Add "Ext. Spool" quick button; add `!include` of shared status chip + popup tray picker |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | Add `!include` of shared status chip + popup tray picker |
| `filament_tag/scripts/update_spool_location-script.yaml` | No change needed — existing script patches Spoolman; the location change triggers the new automation |
| `spoolman_sync/automations/spool_location_change_assign_tray.yaml` | Phase 4: migrate condition from regex to `label_entities('spoolman_spool_location')` |
| `docs/features/spoolman_sync/spoolman-custom-fields.md` | Document "External Spool Holder" as a trigger location |
| `spoolman_sync/automations/spool_location_change_assign_tray.yaml` | Phase 5: change `mode` from implicit `single` to `queued`; emit `spoolman_tray_assignment_queued` event on deferred/needs_tray_selection paths |
| `spoolman_sync/scripts/assign_spool_to_printer_tray-script.yaml` | Phase 5: emit queue event instead of writing scalar `input_text`; support queue-aware deferred status |
| `spoolman_sync/scripts/assign_pending_spool_to_tray-script.yaml` | Phase 5: accept explicit `spool_id` field; fall back to scalar helper for backward compatibility |
| `spoolman_sync/dashboard_cards/tray_assignment_status_and_picker.yaml` | Phase 5: show list of queued spools in popup instead of single pending spool |

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
| Overwriting user's Bambu Studio edits | Medium | Medium | Exact-match pre-check (`type`/`color`/`name`); auto-skip only on exact match, otherwise notify and require explicit override |
| Filament tag view user doesn't see tray assignment result | Medium | Medium | Assignment result sensor + conditional status chip in filament tag view (Phase 3) |
| Combined script bypasses automation safeguards | Low | Low | Automation remains as safety net; combined script is an optimization in Phase 6 |
| Multiple spools moved to AMS before Phase 5 queuing | Medium | Medium | Only latest spool retained in pending state; earlier spools silently lost. Documented limitation in §11; resolved by Phase 5 queuing |
| Queue sensor grows unbounded if user never completes assignments | Low | Low | 24-hour TTL prune with notification before removal (Phase 5) |

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
| Multi-color spool with `filament_multi_color_hexes` and empty `filament_color_hex` | Use first multi-color hex for `tray_color` and continue |
| Spool missing both `filament_color_hex` and usable `filament_multi_color_hexes` | Assignment blocked; notification: "Incomplete spool data: missing usable color" |
| `set_filament` fails (auth error) | Persistent notification with firmware guidance |
| Printer is actively printing when spool loaded | Assignment deferred; notification: "Will assign after print completes" |
| Manual "Set on Printer" from tray popup | set_filament called for matched spool + current tray |
| Tray already has correct filament info | Skip set_filament; log "Already configured" |
| Tray has non-empty filament info that differs from computed Spoolman target | Do not auto-overwrite; create warning/informational notification and require explicit override |
| Profile name matches Bambu profile exactly | Use matched profile's `tray_info_idx` and temp range |
| Profile name has no Bambu match | Use generic profile for the material type |
| Missing profile name and missing extruder temp, material has defaults | Proceed using generic profile + material default temp range |
| Missing profile name and missing extruder temp, material unsupported | Assignment blocked; notification: "Unsupported material for default temp fallback" |
| Location change to non-AMS/non-External | No action taken |
| **Filament Tag View scenarios** | |
| NFC scan → tap "AMS" button in filament tag view | Spoolman location updated → automation fires → tray assignment attempted |
| NFC scan → tap "AMS 2" button | Same as above, targeting AMS 2 trays |
| NFC scan → tap "Ext. Spool" button (new) | Spoolman location updated → automation fires → external spool assignment (no tray inference needed) |

| Tray inference fails after filament tag AMS tap | Inline tray picker shown in filament tag view + notification sent |
| Assignment succeeds after filament tag AMS tap | Status chip shows "✓ Set on AMS 1 Tray 3" in filament tag view |
| Filament tag view with no spool selected | All quick-action buttons disabled/hidden |
| **Multi-spool concurrent assignment scenarios (Phase 5)** | |
| Two spools moved to AMS within seconds, both auto-inferred | Both assignments succeed (script `mode: queued` handles FIFO) |
| Two spools moved to AMS, both need manual tray selection | Both appear in queue; tray picker popup lists both spools with independent tray selectors |
| Spool moved to AMS while printer is busy, print finishes | Deferred assignment auto-retried by queue drain automation; spool assigned after print completes |
| Three spools moved while printing, print finishes | All three deferred entries replayed in FIFO order by queue drain automation |
| Spool queued for tray selection, user never selects tray | Entry pruned after 24h; persistent notification sent before removal |
| Spool A queued for tray selection, spool B queued for tray selection, user selects tray for B | Spool B assigned; spool A remains in queue awaiting selection |
| Near-simultaneous location changes with `mode: queued` automation | Both triggers queued by HA automation engine; neither dropped |

---

## Open Questions Summary

| # | Question | Recommendation | Status |
|---|---|---|---|
| 1 | ~~Add "External Spool" to Spoolman location vocabulary?~~ | N/A — `"External Spool Holder"` already exists | **Resolved** |
| 2 | Use timing heuristics for tray inference? | Defer — start with empty-tray-count; timing-based correlation deferred to Phase 6 | Pending decision |
| 3 | ~~How to map "AMS" vs "AMS 2" locations?~~ | `"AMS"` → AMS 1, `"AMS 2"` → AMS 2 | **Resolved** |
| 4 | ~~How to validate `tray_info_idx` codes?~~ | Validated against `filaments_detail.json` bundled with ha-bambulab. `get_filament_data` returns this merged with slicer custom profiles. Generic fallback codes confirmed: GFL99=PLA, GFG99=PETG, GFB99=ABS, GFB98=ASA, GFU99=TPU, GFN99=PA, GFC99=PC, GFS99=PVA | **Resolved** |
| 5 | ~~Check if tray already has correct data before writing?~~ | Resolved: use exact match on `type`/`color`/`name`; auto-skip only on exact match, otherwise notify and require explicit override | **Resolved** |
| 6 | ~~How to store filament lookup cache?~~ | No caching. Call `get_filament_data` inline at assignment time (local call, fast). Hardcoded generic fallback table for offline resilience. | **Resolved** |
| 7 | Should "Set on Printer" work for Bambu spools too? | Yes — as explicit override when user initiates manually | Pending decision |
| 8 | Should assignment be deferred if printer is printing? | Yes — queue and apply after print completes | Pending decision |
| 9 | Should the filament tag view use a combined script (location + assign) or rely on the automation? | Start with automation-driven flow (two-phase); combined script deferred to Phase 6 (see §9: Enhancement B2) | Pending decision |
| 10 | Should removing a spool from AMS also clear the printer tray info? | Likely no-op — the AMS detects physical removal. May be relevant for External Spool. | Pending decision |
| 11 | Auto-labeling strategy: REST API (Strategy A) vs manual notification (Strategy B)? | Start with Strategy B (notification). Migrate to Strategy A if manual labeling becomes tedious (>2 new spools/month). See §10. | Pending decision |
| 12 | When will HA support label-based entity targeting in `platform: state` triggers? | Unknown. Monitor HA architecture discussions and release notes. Until then, use `platform: event` + `label_entities()` condition. See §10: Future Migration. | Tracking |
| 13 | Multi-spool queue storage: JSON `input_text` (Option A) vs trigger-based template sensor (Option B)? | Option B (template sensor) preferred — no max-length limits, atomic add/remove via events, pattern already proven with `sensor.print_job_ams_tray_storage`. See §11 and Phase 5. | Pending decision |
| 14 | Should deferred assignments auto-retry or require manual re-trigger? | Auto-retry via queue drain automation when print finishes. Manual re-trigger available as fallback from tray picker UI. See Phase 5. | Pending decision |

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| `ha-bambulab` integration | v2.2.x+ — requires `bambu_lab.set_filament` and `bambu_lab.get_filament_data` services |
| Spoolman integration | Must expose `select.spoolman_spool_*_location` entities |
| HA Labels feature | HA 2024.4+ — required for `label_entities()` template function and entity label management (Phase 4) |
| HA long-lived access token | Only required for Strategy A auto-labeling (Phase 4 optional); stored in `secrets.yaml` |
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
