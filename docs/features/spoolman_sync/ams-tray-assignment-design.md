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
| **Where does tray_info_idx come from?** | Profile-name-to-idx lookup table (see [Data Mapping](#data-mapping-tray_info_idx-resolution)) | `bambu_lab.get_filament_data` provides the mapping; cache it for efficient lookup |
| **How to detect Spoolman location changes?** | Monitor `sensor.spoolman_spool_*` location attribute changes via state trigger | Spoolman integration updates entities when spool data changes |
| **What if tray can't be inferred?** | Persistent notification + actionable HA dashboard prompt | User picks the tray from a UI selector; notification links to it |
| **Overwrite Bambu RFID spools?** | Never in AMS trays; always for External Spool | AMS has RFID reader; External Spool never does |
| **Where to store filament ID lookup?** | `input_text` helper with cached JSON from `get_filament_data` | Call once at startup/manual refresh; store for template access |
| **Nozzle temp when only single value?** | Use ±10°C range from `filament_settings_extruder_temp`, or use Bambu profile defaults from lookup table | Safe default; overridden by profile match if found |
| **Feature placement** | New files in `spoolman_sync/` (automations, scripts) + new helpers | This is an extension of the tray-map / spool-sync domain |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    TRIGGER SOURCES                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  (A) Spoolman location change        (B) Manual action    │
│      sensor.spoolman_spool_*             from HA UI       │
│      location → "AMS" / "External"       (button/popup)   │
│                                                           │
└────────────┬──────────────────────────────┬──────────────┘
             │                              │
             ▼                              ▼
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
- `"AMS"` — spool placed into one of the AMS units
- `"AMS 2"` — spool placed into AMS unit 2 (if present)
- `"External Spool"` — spool placed on the external spool holder

> **Open Question 1**: The current Spoolman location vocabulary has `"AMS"` and `"AMS 2"` but no `"External Spool"` value. Options:
> - **(a)** Add `"External Spool"` to the Spoolman location vocabulary (requires updating `sync_filter_options` and location preference list)
> - **(b)** Use a different trigger for External Spool (e.g., dedicated button, or detect when the `external_spool` sensor changes from empty to populated)
> - **(c)** Both — location change is the primary path, but also react to printer-side external spool loading events
>
> **Recommendation**: Option (a) — add `"External Spool"` as a recognized location. This keeps the trigger uniform and the Spoolman data truthful about where the spool physically is.

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
    ├─ Target is "External Spool"?
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

> **Open Question 3**: When location is `"AMS"` (not `"AMS 2"`), should we only check AMS 1 trays, or all AMS units?
>
> **Recommendation**: Map `"AMS"` → AMS 1 trays, `"AMS 2"` → AMS 2 trays. This requires the user to set the correct location value. If ambiguity is common, a future enhancement could add per-tray location values (e.g., `"AMS 1 Tray 3"`), but that's overly granular for most users.

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

**Hardcoded generic fallback table** (for when `get_filament_data` is unavailable or profile name doesn't match):

| Material | Generic `tray_info_idx` | Profile Name |
|---|---|---|
| PLA | `GFL99` | Generic PLA |
| PETG | `GFG99` | Generic PETG |
| ABS | `GFA99` | Generic ABS |
| ASA | `GFS99` | Generic ASA |
| TPU | `GFU99` | Generic TPU |
| PA (Nylon) | `GFN99` | Generic PA |
| PC | `GFC99` | Generic PC |
| PVA | `GFV99` | Generic PVA |
| PLA-CF | `GFL98` | Generic PLA-CF |
| PETG-CF | `GFG98` | Generic PETG-CF |
| PA-CF | `GFN98` | Generic PA-CF |

> **Open Question 4**: The exact `tray_info_idx` codes for generic profiles need to be validated against `bambu_lab.get_filament_data` output. The codes above are illustrative. Implementation should call `get_filament_data` at startup and build the real mapping dynamically.
>
> **Recommendation**: Store the `get_filament_data` response in a helper at startup. Use that as the primary source. Maintain a small hardcoded fallback only for cases where the service call fails.

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

### 7. Spoolman Location Update for External Spool

Currently, the location vocabulary does not include "External Spool". This needs to be added:

#### Changes Required

1. **Add "External Spool" to the preferred location order** in `sync_filter_options.yaml` and wherever location preference lists are defined
2. **Update `filament_catalog_filter_location` options** to include "External Spool" (happens automatically via sync automation)
3. **Document in `spoolman-custom-fields.md`** the new expected location value

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

---

## Implementation Plan

### Phase 1: Core Infrastructure

| Task | Deliverable | Location |
|---|---|---|
| Filament ID lookup cache | Script to call `get_filament_data` and store in helper | `spoolman_sync/scripts/` |
| Filament ID lookup helper | `input_text.bambu_filament_lookup_cache` | `spoolman_sync/helpers/` |
| Startup automation | Call lookup script at HA start | `spoolman_sync/automations/` |
| Data mapping script | `script.resolve_bambu_filament_params` — spool → set_filament params | `spoolman_sync/scripts/` |
| Assignment orchestrator script | `script.assign_spool_to_printer_tray` — validates + calls set_filament | `spoolman_sync/scripts/` |
| Pending assignment helper | `input_text.pending_tray_assignment_spool_id` | `spoolman_sync/helpers/` |

### Phase 2: Automated Flow

| Task | Deliverable | Location |
|---|---|---|
| Location change detection automation | Monitors `sensor.spoolman_spool_*` location changes | `spoolman_sync/automations/` |
| Tray inference logic | Within the automation or as a sub-script | `spoolman_sync/scripts/` |
| External Spool location value | Add "External Spool" to Spoolman location vocabulary | `filament_catalog/automations/sync_filter_options.yaml` |
| Non-interference checks | Pre-call validation (UUID skip, already-correct skip) | Within assignment script |
| Error handling | Persistent notifications for failures, auth issues | Within assignment script |

### Phase 3: UI Integration

| Task | Deliverable | Location |
|---|---|---|
| "Set on Printer" button in tray popup | New action chip in `ams_tray_popup.yaml` | `common/dashboard_cards/card_templates/` |
| Pending assignment tray picker | Notification-linked card for tray selection | `common/dashboard_cards/` or `spoolman_sync/dashboard_cards/` |
| Confirmation feedback | Toast or brief notification on success | Within assignment script |

### Phase 4: Refinement

| Task | Deliverable | Location |
|---|---|---|
| Tray state change correlation | Monitor tray transitions to confirm inference | `spoolman_sync/automations/` |
| Batch assignment | Handle multiple spool location changes at once | Enhancement to Phase 2 automation |
| Lookup cache refresh | Periodic or on-demand refresh of `get_filament_data` cache | Enhancement to Phase 1 |

---

## Affected Files

### New Files

| File | Purpose |
|---|---|
| `spoolman_sync/scripts/assign_spool_to_printer_tray-script.yaml` | Orchestrator: validate, map, call `set_filament` |
| `spoolman_sync/scripts/resolve_bambu_filament_params-script.yaml` | Data mapping: spool attrs → `set_filament` params |
| `spoolman_sync/scripts/refresh_bambu_filament_lookup-script.yaml` | Call `get_filament_data` and cache result |
| `spoolman_sync/automations/spool_location_change_assign_tray.yaml` | Trigger on location change → assignment flow |
| `spoolman_sync/automations/refresh_bambu_filament_lookup_startup.yaml` | Refresh lookup cache at HA start |
| `spoolman_sync/helpers/input_text/input_text_bambu_filament_lookup_cache.yaml` | Cached `get_filament_data` JSON |
| `spoolman_sync/helpers/input_text/input_text_pending_tray_assignment.yaml` | Pending assignment spool ID |
| `docs/features/spoolman_sync/ams-tray-assignment-data-mapping.md` | Supplemental doc: data mapping details |

### Modified Files

| File | Change |
|---|---|
| `common/dashboard_cards/card_templates/ams_tray_popup.yaml` | Add "Set on Printer" action chip |
| `filament_catalog/automations/sync_filter_options.yaml` | Add "External Spool" to location vocabulary |
| `spoolman_sync/helpers/` (loader) | Register new helpers |
| `docs/features/spoolman_sync/spoolman-custom-fields.md` | Document "External Spool" location value |

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
| `input_text` max length exceeded for filament cache | Low | Medium | `input_text` max is 255 chars; JSON blob may exceed this. Consider alternative storage (e.g., file, or multiple helpers partitioned by material) |

> **Open Question 6**: `input_text` has a 255-character `max` limit by default (configurable up to 255 in HA). The full `get_filament_data` response could easily exceed this. Alternatives:
> - **(a)** Store only the generic-profile subset (much smaller)
> - **(b)** Use a `local_file` or `command_line` sensor to store the full mapping
> - **(c)** Don't cache — call `get_filament_data` at assignment time and extract what's needed
> - **(d)** Use multiple `input_text` helpers partitioned by material type
>
> **Recommendation**: Option (c) for simplicity — call `get_filament_data` inline during the assignment script. The service call is local and fast. Maintain the hardcoded generic fallback table for offline resilience. If performance is an issue, revisit with option (a).

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

---

## Open Questions Summary

| # | Question | Recommendation | Status |
|---|---|---|---|
| 1 | Add "External Spool" to Spoolman location vocabulary? | Yes — add it | Pending decision |
| 2 | Use timing heuristics for tray inference? | Defer — start with empty-tray-count | Pending decision |
| 3 | How to map "AMS" vs "AMS 2" locations? | "AMS" → AMS 1, "AMS 2" → AMS 2 | Pending decision |
| 4 | How to validate `tray_info_idx` codes? | Call `get_filament_data` at runtime; hardcoded fallback | Pending decision |
| 5 | Check if tray already has correct data before writing? | Yes — skip if already correct | Pending decision |
| 6 | How to store filament lookup cache? | Don't cache; call `get_filament_data` inline | Pending decision |
| 7 | Should "Set on Printer" work for Bambu spools too? | Yes — as explicit override when user initiates manually | Pending decision |
| 8 | Should assignment be deferred if printer is printing? | Yes — queue and apply after print completes | Pending decision |

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| `ha-bambulab` integration | v2.2.x+ — requires `bambu_lab.set_filament` and `bambu_lab.get_filament_data` services |
| Spoolman integration | Must expose `location` attribute on `sensor.spoolman_spool_*` entities |
| Printer firmware | Must support write operations (LAN Mode or pre-auth-lockdown firmware) |
| `sensor.spoolman_tray_map` | Existing — unchanged; used for read-side matching and spool data access |
| `sensor.smart_status` | Existing — used to check if printer is actively printing |

---

## Related Documents

- [Manual Spool Matching Design](manual-spool-matching-design.md) — Pin/unpin system this feature complements
- [Find Matching Spools](find-matching-spools.md) — Spool matching algorithm (read-side)
- [Spoolman Custom Fields](spoolman-custom-fields.md) — Required Spoolman schema setup
- [Multicolor Spool Matching](multicolor-spool-matching-design.md) — Multi-color matching rules
- [AMS Tray Assignment Data Mapping](ams-tray-assignment-data-mapping.md) — Supplemental: detailed mapping tables
